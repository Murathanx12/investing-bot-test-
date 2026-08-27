"""WEALTH_LAB -- backtest the question the competition actually asks.

WHY THIS IS NOT ANOTHER BACKTESTER
==================================
Every backtest already in this repo answers "does mechanism X have alpha?" and
the honest answer has been no eight times running. The competition asks a
DIFFERENT question, and confusing the two is why two paper accounts are down
$37,337:

    "Over FIVE SESSIONS, which book has the highest terminal wealth?"

Five sessions is ~0.02 years. At that horizon:

  * annualised Sharpe is the wrong ruler -- nobody is compounding for a year;
  * the DRIFT term (equities rise ~0.04%/day) is a larger fraction of the
    expected move than any cross-sectional signal we have ever measured;
  * theta is a certainty and edge is a hypothesis, so any structure that pays
    premium starts the week behind;
  * and the MEDIAN path, not the mean, is what a single five-day draw returns.

So this module evaluates every candidate on the SAME footing: hold for H
sessions, walk forward one session at a time, report terminal wealth of the
repeated book alongside the mean, the median, the hit rate and the t.

DATA
====
Daily bars from the venue's SIP feed, cached to `state/lab/`. The cache is keyed
on (universe hash, start, end) so a re-run is free and an EDITED universe is a
cache MISS rather than a silently stale answer.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

LAB = Path(os.getenv("AAT_LAB_DIR") or "state/lab")

# Costs. A five-day book pays these ONCE in and ONCE out, so they are small in
# absolute terms and enormous relative to a five-day edge -- which is the point.
EQUITY_BPS = 1.0          # spread + impact on a liquid name, one way
OPTION_SPREAD_FRAC = 0.02  # 2% of premium one way; measured 3.2% on our own fills


# --------------------------------------------------------------------- panel
@dataclass
class Panel:
    """Aligned (date x symbol) matrices. Every strategy sees exactly this."""
    dates: list[str]
    symbols: list[str]
    close: np.ndarray          # adjusted close
    open_: np.ndarray
    high: np.ndarray
    low: np.ndarray
    volume: np.ndarray
    vwap: np.ndarray

    @property
    def n_dates(self) -> int:
        return len(self.dates)

    @property
    def n_symbols(self) -> int:
        return len(self.symbols)

    def dollar_volume(self) -> np.ndarray:
        return self.vwap * self.volume

    def index_of(self, date: str) -> int:
        """First index at or after `date`."""
        for i, d in enumerate(self.dates):
            if d >= date:
                return i
        return len(self.dates)

    def slice_from(self, date: str) -> int:
        return self.index_of(date)


def _key(symbols: Sequence[str], start: str, end: str | None) -> str:
    h = hashlib.sha256(("|".join(sorted(symbols)) + f"@{start}@{end}").encode()).hexdigest()[:16]
    return f"panel_{h}"


def build_panel(symbols: Sequence[str], *, start: str, end: str | None = None,
                client: Any = None, refresh: bool = False) -> Panel:
    """Fetch (or load) daily bars and align them onto one date axis.

    A symbol missing a bar on a date gets NaN, never a forward fill -- a forward
    fill on a halted or delisted name manufactures a flat return and flatters
    every risk number computed from it.
    """
    LAB.mkdir(parents=True, exist_ok=True)
    cache = LAB / f"{_key(symbols, start, end)}.npz"
    meta = LAB / f"{_key(symbols, start, end)}.json"
    if cache.exists() and meta.exists() and not refresh:
        z = np.load(cache, allow_pickle=False)
        m = json.loads(meta.read_text(encoding="utf-8"))
        return Panel(dates=m["dates"], symbols=m["symbols"],
                     close=z["close"], open_=z["open"], high=z["high"],
                     low=z["low"], volume=z["volume"], vwap=z["vwap"])

    if client is None:
        from alpha.broker.alpaca import AlpacaPaper
        client = AlpacaPaper()
    raw = client.stock_bars_multi(list(symbols), start=start, end=end, timeframe="1Day")

    all_dates = sorted({b["t"][:10] for bars in raw.values() for b in bars})
    syms = sorted(k for k, v in raw.items() if len(v) >= max(20, len(all_dates) // 3))
    di = {d: i for i, d in enumerate(all_dates)}
    shape = (len(all_dates), len(syms))
    close = np.full(shape, np.nan)
    open_ = np.full(shape, np.nan)
    high = np.full(shape, np.nan)
    low = np.full(shape, np.nan)
    vol = np.zeros(shape)
    vwap = np.full(shape, np.nan)
    for j, s in enumerate(syms):
        for b in raw[s]:
            i = di.get(b["t"][:10])
            if i is None:
                continue
            close[i, j] = b.get("c", np.nan)
            open_[i, j] = b.get("o", np.nan)
            high[i, j] = b.get("h", np.nan)
            low[i, j] = b.get("l", np.nan)
            vol[i, j] = b.get("v", 0.0) or 0.0
            vwap[i, j] = b.get("vw") or b.get("c") or np.nan

    np.savez_compressed(cache, close=close, open=open_, high=high, low=low,
                        volume=vol, vwap=vwap)
    meta.write_text(json.dumps({"dates": all_dates, "symbols": syms,
                                "start": start, "end": end}), encoding="utf-8")
    return Panel(dates=all_dates, symbols=syms, close=close, open_=open_,
                 high=high, low=low, volume=vol, vwap=vwap)


# ------------------------------------------------------------------ verdicts
@dataclass
class Result:
    name: str
    horizon: int
    n_windows: int              # overlapping draws
    n_blocks: int               # NON-overlapping -- the honest denominator
    mean: float                 # per-window arithmetic mean return
    median: float
    hit: float
    t: float                    # computed on BLOCKS, not on overlapping draws
    wealth: float               # terminal wealth of $1 compounded over blocks
    worst: float
    best: float
    ann: float                  # annualised from the block series
    turnover: float = 0.0
    note: str = ""
    curve: list[float] = field(default_factory=list)

    def line(self) -> str:
        return (f"{self.name:<34} {self.mean:+7.3%} {self.median:+7.3%} "
                f"{self.hit:5.1%} {self.t:+6.2f} {self.wealth:7.3f}x "
                f"{self.worst:+7.2%} {self.n_blocks:4d}")


def _blocks(rets: np.ndarray, horizon: int) -> np.ndarray:
    """Take every `horizon`-th window so the draws do not share days.

    A five-day return sampled daily overlaps 80% with its neighbour. Running a
    t-test on those 250 draws claims 250 independent observations and has
    roughly 50. Canon §58: n_effective counts DATE BLOCKS.
    """
    return rets[::horizon]


def summarise(name: str, rets: np.ndarray, horizon: int, *, turnover: float = 0.0,
              note: str = "") -> Result:
    rets = np.asarray([r for r in rets if np.isfinite(r)], dtype=float)
    if rets.size == 0:
        return Result(name, horizon, 0, 0, 0, 0, 0, 0, 1.0, 0, 0, 0, turnover,
                      note or "no finite windows")
    blk = _blocks(rets, horizon)
    n = blk.size
    sd = float(np.std(blk, ddof=1)) if n > 1 else 0.0
    t = float(np.mean(blk) / (sd / math.sqrt(n))) if (n > 1 and sd > 0) else 0.0
    curve = np.cumprod(1.0 + blk)
    wealth = float(curve[-1]) if n else 1.0
    years = (n * horizon) / 252.0
    ann = (wealth ** (1.0 / years) - 1.0) if (years > 0 and wealth > 0) else 0.0
    return Result(name=name, horizon=horizon, n_windows=int(rets.size), n_blocks=n,
                  mean=float(np.mean(rets)), median=float(np.median(rets)),
                  hit=float(np.mean(rets > 0)), t=t, wealth=wealth,
                  worst=float(np.min(rets)), best=float(np.max(rets)), ann=ann,
                  turnover=turnover, note=note, curve=[float(x) for x in curve])


# --------------------------------------------------------------- the harness
Selector = Callable[[Panel, int], np.ndarray]
"""Given the panel and an index `i` (the DECISION close), return a weight vector
over symbols. Must read NOTHING at index > i. Weights are dollar fractions and
may sum to less than 1 (cash) or more than 1 (leverage)."""


def run(panel: Panel, selector: Selector, *, horizon: int = 5, name: str = "?",
        start_i: int | None = None, cost_bps: float = EQUITY_BPS,
        note: str = "") -> Result:
    """Decide at the close of i, FILL AT THE OPEN of i+1, exit at the open of
    i+1+horizon. The one-session gap is not conservatism, it is the only fill we
    could actually have got: a signal computed from the close cannot transact at
    that close.
    """
    n = panel.n_dates
    lo = start_i if start_i is not None else 60
    rets, turn = [], []
    prev_w = np.zeros(panel.n_symbols)
    for i in range(lo, n - horizon - 1):
        w = selector(panel, i)
        if w is None or not np.any(np.isfinite(w)) or np.all(w == 0):
            rets.append(0.0)
            continue
        w = np.nan_to_num(w, nan=0.0, posinf=0.0, neginf=0.0)
        entry = panel.open_[i + 1]
        exit_ = panel.open_[i + 1 + horizon]
        ok = np.isfinite(entry) & np.isfinite(exit_) & (entry > 0) & (w != 0)
        if not ok.any():
            rets.append(0.0)
            continue
        leg = np.zeros_like(w)
        leg[ok] = exit_[ok] / entry[ok] - 1.0
        gross = float(np.sum(w * leg))
        tno = float(np.sum(np.abs(w - prev_w)))
        prev_w = w
        # in AND out on the traded fraction
        cost = (np.sum(np.abs(w)) * 2.0) * (cost_bps / 10_000.0)
        rets.append(gross - cost)
        turn.append(tno)
    return summarise(name, np.asarray(rets), horizon,
                     turnover=float(np.mean(turn)) if turn else 0.0, note=note)


# ------------------------------------------------------------- helper series
def _trailing_return(p: Panel, i: int, lookback: int, skip: int = 0) -> np.ndarray:
    a = i - skip
    b = a - lookback
    if b < 0:
        return np.full(p.n_symbols, np.nan)
    return p.close[a] / p.close[b] - 1.0


def _trailing_vol(p: Panel, i: int, lookback: int = 20) -> np.ndarray:
    if i - lookback - 1 < 0:
        return np.full(p.n_symbols, np.nan)
    w = p.close[i - lookback:i + 1]
    r = w[1:] / w[:-1] - 1.0
    return np.nanstd(r, axis=0)


def _liquid_mask(p: Panel, i: int, top: int = 200) -> np.ndarray:
    dv = np.nanmean(p.vwap[max(0, i - 20):i + 1] * p.volume[max(0, i - 20):i + 1], axis=0)
    dv = np.nan_to_num(dv, nan=0.0)
    if (dv > 0).sum() <= top:
        return dv > 0
    cut = np.partition(dv, -top)[-top]
    return dv >= cut


def _top_k(score: np.ndarray, k: int, mask: np.ndarray, *, long_only: bool = True,
           reverse: bool = False) -> np.ndarray:
    s = np.where(mask & np.isfinite(score), score, np.nan)
    if reverse:
        s = -s
    n_ok = int(np.sum(np.isfinite(s)))
    if n_ok < k:
        return np.zeros_like(s)
    order = np.argsort(np.where(np.isfinite(s), -s, np.inf))
    w = np.zeros_like(s)
    w[order[:k]] = 1.0 / k
    if not long_only:
        w[order[-k:]] = -1.0 / k
    return w


def hold(symbol: str) -> Selector:
    def f(p: Panel, i: int) -> np.ndarray:
        w = np.zeros(p.n_symbols)
        if symbol in p.symbols:
            w[p.symbols.index(symbol)] = 1.0
        return w
    return f


def levered(symbol: str, mult: float) -> Selector:
    base = hold(symbol)
    return lambda p, i: base(p, i) * mult


def equal_weight(top: int = 200) -> Selector:
    def f(p: Panel, i: int) -> np.ndarray:
        m = _liquid_mask(p, i, top)
        w = np.zeros(p.n_symbols)
        if m.sum():
            w[m] = 1.0 / m.sum()
        return w
    return f


def cross_sectional(lookback: int, skip: int, k: int, *, reverse: bool = False,
                    top: int = 200) -> Selector:
    def f(p: Panel, i: int) -> np.ndarray:
        return _top_k(_trailing_return(p, i, lookback, skip), k,
                      _liquid_mask(p, i, top), reverse=reverse)
    return f


def low_vol(k: int, *, reverse: bool = False, top: int = 200) -> Selector:
    def f(p: Panel, i: int) -> np.ndarray:
        return _top_k(-_trailing_vol(p, i), k, _liquid_mask(p, i, top), reverse=reverse)
    return f


def trend_filter(symbol: str, inner: Selector, window: int = 200) -> Selector:
    """Hold `inner` only while `symbol` is above its own moving average.

    The single most durable risk-management result in the public literature, and
    the cheapest thing we have never run: it does not need a cross-sectional
    signal, only the courage to be in cash.
    """
    def f(p: Panel, i: int) -> np.ndarray:
        if symbol not in p.symbols or i < window:
            return np.zeros(p.n_symbols)
        j = p.symbols.index(symbol)
        ma = float(np.nanmean(p.close[i - window:i + 1, j]))
        if not np.isfinite(ma) or p.close[i, j] < ma:
            return np.zeros(p.n_symbols)
        return inner(p, i)
    return f


def vol_targeted(inner: Selector, symbol: str, target: float = 0.15,
                 lookback: int = 20, cap: float = 3.0) -> Selector:
    """Scale gross exposure so realised vol sits near `target`.

    Moreira-Muir: the volatility-managed version of a factor beats the factor,
    because vol is FORECASTABLE at short horizons and return is not. Nothing in
    this repo has ever sized on that -- `vol_gap` sized on a vol OPINION.
    """
    def f(p: Panel, i: int) -> np.ndarray:
        w = inner(p, i)
        if symbol not in p.symbols or i < lookback + 1:
            return w
        j = p.symbols.index(symbol)
        r = p.close[i - lookback:i + 1, j]
        rv = float(np.nanstd(r[1:] / r[:-1] - 1.0)) * math.sqrt(252.0)
        if not np.isfinite(rv) or rv <= 0:
            return w
        return w * float(np.clip(target / rv, 0.0, cap))
    return f


def blend(parts: Sequence[tuple[Selector, float]]) -> Selector:
    def f(p: Panel, i: int) -> np.ndarray:
        w = np.zeros(p.n_symbols)
        for sel, wt in parts:
            w = w + sel(p, i) * wt
        return w
    return f


# --------------------------------------------------- what a leaderboard costs
def noise_max_t(n_blocks: int, n_strategies: int, *, trials: int = 4000,
                seed: int = 7) -> tuple[float, float]:
    """The largest |t| you EXPECT from `n_strategies` pure-noise books.

    Canon: the top row of a leaderboard is a MAXIMUM, and a maximum of many
    draws is biased upward. Comparing the winner's t to 2.0 asks whether ONE
    pre-registered strategy worked; comparing it to this asks whether the
    LEADERBOARD did. The second is the question a 22-row table poses.

    Returns (median max-t, 95th percentile max-t).
    """
    rng = np.random.default_rng(seed)
    draws = rng.standard_normal((trials, n_strategies, n_blocks))
    m = draws.mean(axis=2)
    s = draws.std(axis=2, ddof=1)
    t = m / (s / math.sqrt(n_blocks))
    mx = np.abs(t).max(axis=1)
    return float(np.median(mx)), float(np.percentile(mx, 95))


def rotate(candidates: Sequence[str], lookback: int, k: int = 1,
           *, skip: int = 0, reverse: bool = False) -> Selector:
    """Hold the `k` strongest of `candidates` by trailing return.

    This is the tradeable form of a hindsight winner. "Semis won last year" is
    not a strategy; "hold whichever sector led over the last N sessions" is one,
    and it can be run at every date in the sample without knowing the answer.
    If the rule does NOT recover the winner, the winner was hindsight.
    """
    def f(p: Panel, i: int) -> np.ndarray:
        idx = [p.symbols.index(c) for c in candidates if c in p.symbols]
        if not idx or i - lookback - skip < 0:
            return np.zeros(p.n_symbols)
        r = _trailing_return(p, i, lookback, skip)
        sc = np.full(p.n_symbols, np.nan)
        sc[idx] = r[idx]
        if reverse:
            sc = -sc
        mask = np.zeros(p.n_symbols, dtype=bool)
        mask[idx] = True
        return _top_k(sc, min(k, len(idx)), mask)
    return f
