"""LEVERAGE LADDER -- what 4x buying power actually buys, priced as RISK.

    python -m scripts.leverage_lab                       # today's seal, hack3
    python -m scripts.leverage_lab --book hack4
    python -m scripts.leverage_lab --variant AGGRESSIVE  # a shadow variant book
    python -m scripts.leverage_lab --day 2026-09-02 --sessions 45 --json

THE ONE SENTENCE THIS FILE EXISTS TO PUT IN FRONT OF A DECISION
===============================================================
Murat wants to explore the full 4x intraday buying power. The house rule is
that a leverage experiment targets RISK, not NOTIONAL, and the arithmetic
that makes those two different is short enough to say here:

    the 2026-09-02 book's measured market beta is 2.10 (RETRO_2026-09-02)
    4x NOTIONAL on a 2.10-beta book is an 8.4-BETA book

Nobody would write down "hold the S&P at 8.4x" as a plan. That is what "use
the buying power" means arithmetically, and it is why the ladder below reports
beta on every rung. A risk-targeted version of the same idea moves the gross
until the BETA is what was chosen -- which, at beta 2.10, means a multiplier
BELOW 1.0 to reach a 2x-market book, not above it.

WHAT THE HOUSE ALREADY LEARNED, AND THIS DOES NOT RE-LEARN
==========================================================
28 Aug: twelve names x 25% notional = 300% gross, and a 3% stop on 300% gross
is -9%. 29 Aug: the "fix" widened the stop to 8% and left the notional alone,
which made the worst case -24%. A WIDER STOP ON UNCAPPED GROSS IS A BIGGER
LOSS. So this file prints the worst case BEFORE any average, in dollars and in
percent, at every rung -- and it prints the ALL-GAP case beside the all-stop
case, because a stop does not survive a gap and the book's own modelled
downside_5pct averages roughly ten times its stop width.

TWO FINANCING REGIMES, AND WHY THE OVERNIGHT LADDER STOPS AT 2.0
================================================================
    INTRADAY   flat at the close. The payoff is open -> close; the overnight
               gap risk is zero by construction, and the price of that is a
               round trip EVERY session -- 2 x gross x spread per day, which at
               4x gross is roughly 8bps a day, ~20% a year, before any edge.
    OVERNIGHT  held through the close. Reg T maintenance margin is 25%-30%,
               which is 3-4x on paper, but Alpaca (like every US broker)
               allows only 2x of EQUITY overnight; a position above 2x at the
               close is a day-trading margin call and a forced liquidation at
               the broker's convenience, not ours. So the overnight ladder is
               CAPPED AT 2.0 and the 3.0/4.0 rungs are reported as REFUSED
               rather than computed -- a number computed for a position that
               cannot be held is a number that invites holding it.
    Overnight leverage is also FINANCED: (L-1) x equity of debit balance at
    the broker's margin rate, charged daily. `scripts/overnight_tradeable.py`
    once won an argument by not charging it; this one charges it.

THE WINDOW IS SHORT AND THAT IS THE HONEST HEADLINE
===================================================
The sealed books with per-book holdings begin on 2026-08-31. That is TWO
graded sessions for hack4 and ONE for hack3. There is no way to make that
number bigger by computing harder, and there is no daily book history to
replay: the eligible-universe day files start on 2026-08-30. So this reports
two windows and never blends them:

    PIT_SEALED     the sealed books, day by day, as sealed. Honest, and n<=2.
    STATIC_SET     TODAY's holdings held constant over the trailing window.
                   The names were chosen with data from the END of that window,
                   so this is a SELECTION-BIASED illustration of how the ladder
                   behaves on this kind of book -- NOT evidence about it. It is
                   labelled that way in the receipt and on every printed table.

READ-ONLY. Fetches daily bars through `alpha.lab.build_panel` (the house
backtester's cached data path) and writes a receipt. It imports no broker
module, sizes nothing and submits nothing.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alpha import config                                   # noqa: E402
from alpha import lab                                      # noqa: E402
from alpha import tracker as T                             # noqa: E402
from scripts import portfolio_variants as PV               # noqa: E402

OUT = Path(os.getenv("AAT_LEVERAGE_DIR") or (ROOT / "state" / "leverage_lab"))
BENCH = "SPY"

#: The rungs. 1.0 is the book as sealed.
LADDER = (1.0, 1.5, 2.0, 3.0, 4.0)

#: Alpaca allows 4x of equity INTRADAY for a pattern day trader above $25k, and
#: 2x overnight. A position above the overnight bound at the close is a
#: day-trading margin call, so the overnight ladder refuses those rungs.
INTRADAY_BUYING_POWER = 4.0
OVERNIGHT_BUYING_POWER = 2.0

#: Annual margin rate on the debit balance. Charged on (L-1) x equity, every
#: calendar day the position is held. Alpaca's published schedule is 5.75% at
#: the sizes this account trades; `--margin-rate` overrides it.
MARGIN_RATE = 0.0575

#: The book's measured market beta, from RETRO_2026-09-02 (aegis-finance
#: receipt month_retro_20260902.json). Quoted so the beta arithmetic can be
#: stated even on a window too short to measure a beta from, and printed
#: BESIDE the beta this run measures rather than instead of it.
HOUSE_BOOK_BETA = 2.10
HOUSE_BOOK_BETA_SOURCE = "RETRO_2026-09-02 (aegis-finance month_retro_20260902.json)"


# --------------------------------------------------------------------------
# Loading a book
# --------------------------------------------------------------------------

def _sha(payload: dict) -> str:
    import hashlib
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def sealed_book(day: str, book: str) -> dict:
    """The sealed book's holdings for one paper book, SHA-VERIFIED.

    A ladder computed from an unverified book is a ladder on whatever the file
    says today. The seal recomputes to its own `content_sha256` or this
    refuses; `prediction_book.verify` uses the same expression.
    """
    p = ROOT / "state" / "predictions" / f"{day}.json"
    if not p.exists():
        raise SystemExit(f"REFUSED: no sealed book at {p}")
    payload = json.loads(p.read_text(encoding="utf-8"))
    claimed = payload.pop("content_sha256", None)
    recomputed = _sha(payload)
    payload["content_sha256"] = claimed
    if claimed != recomputed:
        raise SystemExit(f"REFUSED: {p.name} sha mismatch -- claims {claimed}, "
                         f"recomputes {recomputed}. The file was edited after sealing.")
    port = (payload.get("portfolios") or {}).get(book)
    if not port:
        raise SystemExit(f"REFUSED: sealed book {day} carries no portfolios['{book}'] "
                         "(the 2026-08-30 seal predates the portfolios block).")
    return {
        "source": "sealed", "day": day, "book": book,
        "content_sha256": claimed, "sha_verified": True,
        "holdings": [{"symbol": h["symbol"], "notional": float(h["notional"]),
                      "sector": h.get("sector"),
                      "downside_5pct": h.get("downside_5pct"),
                      "exp_return": h.get("exp_return")}
                     for h in port["holdings"]],
        "n_selected": port["n_selected"],
        "max_notional_each": port["max_notional_each"],
        "personality": port.get("personality"),
        "worst_case_sealed": port.get("worst_case"),
    }


def variant_book(day: str, name: str) -> dict:
    p = PV.OUT / day / f"{name}.json"
    if not p.exists():
        raise SystemExit(f"REFUSED: no variant book at {p}. Run "
                         f"`python -m scripts.portfolio_variants --day {day}` first.")
    b = json.loads(p.read_text(encoding="utf-8"))
    return {
        "source": "variant", "day": day, "book": name,
        "content_sha256": None, "sha_verified": False,
        "holdings": [{"symbol": h["symbol"], "notional": float(h["notional"]),
                      "sector": h.get("sector"),
                      "downside_5pct": h.get("downside_5pct"),
                      "exp_return": h.get("exp_return")}
                     for h in b["holdings"]],
        "n_selected": b["n_selected"],
        "max_notional_each": b["max_notional_each"],
        "personality": b["variant"],
        "worst_case_sealed": b.get("worst_case"),
    }


def _join_dollar_volume(b: dict, day: str) -> None:
    """Put the tracker's median dollar volume on every holding, in place.

    The sealed `portfolios[...]` block does not carry it, and `capacity()`
    treats an absent dollar volume as UNREADABLE and flags it -- correctly, and
    uselessly, since it would flag all ten names for the same missing column
    and hide the names that are genuinely large relative to their volume. The
    join is against the same tracker day the book was sealed from.
    """
    from scripts import tracker as tracker_cli
    try:
        rows = {r["symbol"]: r for r in tracker_cli.load_day(day)}
    except (OSError, ValueError):
        rows = {}
    for h in b["holdings"]:
        t = rows.get(h["symbol"]) or {}
        h.setdefault("median_dollar_volume", t.get("median_dollar_volume"))
        h.setdefault("close", t.get("close"))


def _limits(book: str) -> tuple[float, float, str]:
    """(gross cap, stop fraction, profile) derived from the enforcing modules."""
    try:
        from scripts.tracker import _limits_for
        return _limits_for(book)
    except (Exception, SystemExit):
        # A variant book has no fleet mandate. The house DEFAULT is the honest
        # stand-in, and the receipt says which was used -- never a silent one.
        from alpha.engine import equity as _equity
        from alpha.engine import sizing as _sizing
        prof = _sizing.DEFAULT_PROFILE
        return float(_sizing.gross_cap(prof)), float(_equity.stop_fraction(prof)), prof


# --------------------------------------------------------------------------
# WORST CASE -- printed before any average, every time
# --------------------------------------------------------------------------

def worst_case_table(book: dict, *, equity: float, gross_cap: float,
                     stop: float, profile: str, beta: float = HOUSE_BOOK_BETA) -> list[dict]:
    """One row per rung. `n x notional x stop` and the all-gap case, in dollars.

    The gross cap is scaled with the rung: a 4x experiment that then clamps
    itself at the 1.0x book cap is not a 4x experiment, and pretending the cap
    binds would understate exactly the number this table exists to state.
    """
    n = book["n_selected"]
    notional = book["max_notional_each"]
    downs = [abs(float(h["downside_5pct"])) for h in book["holdings"]
             if h.get("downside_5pct") is not None]
    mean_down = (sum(downs) / len(downs)) if downs else None
    worst_down = max(downs) if downs else None

    rows = []
    for L in LADDER:
        wc = T.worst_case(n=n, notional_each=notional * L, stop_fraction=stop,
                          gross_cap=gross_cap * L)
        gross = wc["gross"]
        gap = (-gross * mean_down) if mean_down is not None else None
        gap_worst = (-gross * worst_down) if worst_down is not None else None
        rows.append({
            "multiplier": L,
            "gross_of_equity": gross,
            "gross_usd": round(gross * equity, 2),
            "binding": wc["binding"],
            "n_names": n,
            "notional_each": round(notional * L, 5),
            "stop_fraction": stop,
            "all_stop_loss_fraction": wc["worst_case_fraction"],
            "all_stop_loss_usd": round(wc["worst_case_fraction"] * equity, 2),
            "all_gap_loss_fraction": (round(gap, 5) if gap is not None else None),
            "all_gap_loss_usd": (round(gap * equity, 2) if gap is not None else None),
            "worst_single_name_gap_fraction": (round(gap_worst, 5)
                                               if gap_worst is not None else None),
            # RUIN IS A DIFFERENT WORD FROM LOSS, and a percentage past 100 is
            # the one number a reader is most likely to skim. A book whose
            # modelled all-gap case exceeds equity does not lose that much: it
            # is liquidated by the broker on the way there, at whatever price
            # the tape offers, and the account is gone.
            "exceeds_equity": bool(gap is not None and gap <= -1.0),
            "ruin_note": (("the modelled all-gap case is LARGER THAN THE ACCOUNT. This is not "
                           "a loss estimate, it is a RUIN case: the position is liquidated by "
                           "the broker before it gets there.") if (gap is not None and gap <= -1.0)
                          else None),
            "beta_equivalent": round(beta * gross, 3),
            "beta_used": beta,
            "intraday_margin_utilization": round(gross / INTRADAY_BUYING_POWER, 4),
            "overnight_margin_utilization": round(gross / OVERNIGHT_BUYING_POWER, 4),
            "overnight_permitted": bool(L <= OVERNIGHT_BUYING_POWER + 1e-9),
        })
    return rows


# --------------------------------------------------------------------------
# The replay
# --------------------------------------------------------------------------

def _panel(symbols: list[str], *, sessions: int, end: str | None) -> lab.Panel:
    """Daily bars through the house backtester's cached path."""
    start = (datetime.now(timezone.utc) - timedelta(days=int(sessions * 1.6) + 20)).date().isoformat()
    return lab.build_panel(sorted(set(symbols) | {BENCH}), start=start, end=end)


def _weights(panel: lab.Panel, holdings: list[dict]) -> tuple[np.ndarray, list[str]]:
    w = np.zeros(panel.n_symbols)
    missing = []
    for h in holdings:
        s = h["symbol"]
        if s in panel.symbols:
            w[panel.symbols.index(s)] = float(h["notional"])
        else:
            missing.append(s)
    return w, missing


def _legs(panel: lab.Panel, w: np.ndarray, i: int) -> dict[str, float | None]:
    """The three return legs of session i for a book weighted `w`.

    intraday   open(i)  -> close(i)      the flat-at-the-close payoff
    gap        close(i-1) -> open(i)     what the intraday book never holds
    session    close(i-1) -> close(i)    the held-through payoff
    A leg with no readable price on either end is None, never zero: a missing
    bar is not a flat session.
    """
    def leg(a: np.ndarray, b: np.ndarray) -> float | None:
        ok = np.isfinite(a) & np.isfinite(b) & (a > 0) & (w != 0)
        if not ok.any():
            return None
        r = np.zeros_like(w)
        r[ok] = b[ok] / a[ok] - 1.0
        # Weights on names with no price are dropped, not redistributed: the
        # book held cash there, and re-normalising would invent a position.
        return float(np.sum(w * r))

    out = {"intraday": leg(panel.open_[i], panel.close[i])}
    if i > 0:
        out["gap"] = leg(panel.close[i - 1], panel.open_[i])
        out["session"] = leg(panel.close[i - 1], panel.close[i])
    else:
        out["gap"] = out["session"] = None
    return out


def _bench_legs(panel: lab.Panel, i: int) -> dict[str, float | None]:
    if BENCH not in panel.symbols:
        return {"intraday": None, "gap": None, "session": None}
    j = panel.symbols.index(BENCH)
    w = np.zeros(panel.n_symbols)
    w[j] = 1.0
    return _legs(panel, w, i)


def _metrics(rets: list[float], bench: list[float], *, name: str,
             sessions_per_year: float = 252.0) -> dict:
    """Terminal wealth, geometric mean, max drawdown, worst session, beta, CVaR.

    Compounded, which is the point: a constant-leverage book rebalanced daily
    pays variance drag proportional to L^2, so the ladder's terminal wealth is
    NOT the ladder's mean return times L. Ranking on the mean is how a book
    with mean +0.147%/window came back at 0.1x terminal wealth (S17).
    """
    r = np.asarray([x for x in rets if x is not None and np.isfinite(x)], dtype=float)
    b = np.asarray([x for x in bench if x is not None and np.isfinite(x)], dtype=float)
    n = r.size
    if n == 0:
        return {"name": name, "n_sessions": 0, "note": "no readable session"}
    curve = np.cumprod(1.0 + r)
    wealth = float(curve[-1])
    peak = np.maximum.accumulate(np.concatenate([[1.0], curve]))
    dd = float(np.min(np.concatenate([[1.0], curve]) / peak - 1.0))
    geo = float(wealth ** (1.0 / n) - 1.0) if wealth > 0 else -1.0
    k = max(1, int(math.ceil(0.05 * n)))
    cvar = float(np.mean(np.sort(r)[:k]))
    beta = None
    if b.size == n and n > 2 and float(np.var(b)) > 0:
        beta = float(np.cov(r, b, ddof=1)[0, 1] / np.var(b, ddof=1))
    return {
        "name": name,
        "n_sessions": n,
        "terminal_wealth": round(wealth, 6),
        "total_return": round(wealth - 1.0, 6),
        "geometric_mean_per_session": round(geo, 6),
        "annualised_geometric": (round((1.0 + geo) ** sessions_per_year - 1.0, 4)
                                 if geo > -1 else None),
        "max_drawdown": round(dd, 6),
        "worst_session": round(float(np.min(r)), 6),
        "best_session": round(float(np.max(r)), 6),
        "realized_beta_vs_spy": (round(beta, 4) if beta is not None else None),
        "cvar_5pct": round(cvar, 6),
        "cvar_n_tail_sessions": k,
        "cvar_caveat": (f"the 5% tail of {n} sessions is {k} session(s). This is an "
                        "arithmetic restatement of the worst day, not a tail estimate."),
        "volatility_per_session": round(float(np.std(r, ddof=1)) if n > 1 else 0.0, 6),
    }


def levered_session(raw: float | None, *, regime: str, gross: float, scale: float,
                    cost_bps: float, margin_rate: float,
                    charge_round_trip: bool = True) -> float | None:
    """One session of one rung, net. The ONE expression both scripts use.

    `scale` converts the book's own weights into the rung's gross (it is L,
    clipped by the gross cap). Costs are a round trip on the traded gross;
    financing is charged only where the position is HELD, on the borrowed
    fraction, per calendar day. `None` in, `None` out -- a session with no
    readable price is not a flat session.
    """
    if raw is None:
        return None
    out = raw * scale
    if charge_round_trip:
        out -= 2.0 * gross * (cost_bps / 10_000.0)
    if regime != "intraday":
        out -= max(0.0, gross - 1.0) * margin_rate / 360.0
    return out


def ladder_arm(panel: lab.Panel, w: np.ndarray, idx: list[int], *, regime: str,
               L: float, cost_bps: float, margin_rate: float,
               gross_cap: float) -> dict:
    """One rung of one financing regime over the sessions in `idx`."""
    permitted = (L <= OVERNIGHT_BUYING_POWER + 1e-9) if regime == "overnight" else True
    gross = min(float(np.sum(np.abs(w))) * L, gross_cap * L)
    scale = (gross / float(np.sum(np.abs(w)))) if float(np.sum(np.abs(w))) else 0.0
    if not permitted:
        return {
            "regime": regime, "multiplier": L, "permitted": False,
            "refusal": (f"REFUSED: {L:.1f}x cannot be held overnight. US overnight margin "
                        f"is {OVERNIGHT_BUYING_POWER:.0f}x of equity; a position above it at "
                        "the close is a day-trading margin call and a liquidation at the "
                        "broker's convenience. No number is computed for a position that "
                        "cannot be held."),
            "gross_of_equity": round(gross, 4),
        }

    rets, bench = [], []
    for i in idx:
        legs = _legs(panel, w, i)
        bl = _bench_legs(panel, i)
        raw = legs["intraday"] if regime == "intraday" else legs["session"]
        bench.append(bl["intraday"] if regime == "intraday" else bl["session"])
        rets.append(levered_session(raw, regime=regime, gross=gross, scale=scale,
                                    cost_bps=cost_bps, margin_rate=margin_rate,
                                    charge_round_trip=(regime == "intraday")))

    if regime == "overnight" and rets:
        # A held book pays the round trip ONCE, at the two ends of the window.
        entry_exit = 2.0 * gross * (cost_bps / 10_000.0)
        first = next((k for k, v in enumerate(rets) if v is not None), None)
        last = next((k for k in range(len(rets) - 1, -1, -1) if rets[k] is not None), None)
        if first is not None:
            rets[first] -= entry_exit / 2.0
        if last is not None:
            rets[last] -= entry_exit / 2.0

    m = _metrics(rets, bench, name=f"{regime} {L:.1f}x")
    m.update({
        "regime": regime, "multiplier": L, "permitted": True,
        "gross_of_equity": round(gross, 4),
        "margin_utilization": round(gross / (INTRADAY_BUYING_POWER if regime == "intraday"
                                             else OVERNIGHT_BUYING_POWER), 4),
        "beta_equivalent_house": round(HOUSE_BOOK_BETA * gross, 3),
        "cost_bps_one_way": cost_bps,
        "financing": ("none -- flat at the close" if regime == "intraday"
                      else f"{margin_rate:.2%}/yr on {max(0.0, gross - 1.0):.2f}x of equity, "
                           "charged daily"),
        "turnover": ("round trip EVERY session" if regime == "intraday"
                     else "one round trip across the window"),
    })
    return m


# --------------------------------------------------------------------------
# The two windows
# --------------------------------------------------------------------------

def pit_sessions(panel: lab.Panel, day: str, book: str) -> list[dict]:
    """Each sealed day whose session has actually closed, with ITS OWN book.

    This is the only PIT evidence that exists. It is tiny, it is reported as
    tiny, and no rung's number from here is an estimate of anything.
    """
    out = []
    for p in sorted((ROOT / "state" / "predictions").glob("2026-*.json")):
        if "resealed" in p.name:
            continue
        d = p.stem
        if d > day:
            continue
        try:
            b = sealed_book(d, book)
        except SystemExit:
            continue
        if d not in panel.dates:
            continue
        i = panel.dates.index(d)
        w, missing = _weights(panel, b["holdings"])
        legs = _legs(panel, w, i)
        bl = _bench_legs(panel, i)
        out.append({"day": d, "sha256": b["content_sha256"][:10],
                    "n": b["n_selected"], "missing_bars": missing,
                    "book": legs, "spy": bl,
                    "symbols": [h["symbol"] for h in b["holdings"]]})
    return out


def run(*, day: str, book: str, variant: str | None, equity: float,
        sessions: int, cost_bps: float, margin_rate: float) -> dict:
    b = variant_book(day, variant) if variant else sealed_book(day, book)
    label = variant or book
    gross_cap, stop, profile = _limits(book)
    _join_dollar_volume(b, day)

    symbols = [h["symbol"] for h in b["holdings"]]
    panel = _panel(symbols, sessions=sessions, end=None)
    w, missing = _weights(panel, b["holdings"])

    # The STATIC_SET window: the last `sessions` CLOSED sessions on the panel.
    # `day` itself is excluded unless its bar exists -- a book sealed pre-open
    # has no close yet, and counting a session that has not happened is the
    # cheapest way to publish a number that cannot be reproduced tomorrow.
    usable = [i for i in range(panel.n_dates) if panel.dates[i] < day]
    idx = usable[-sessions:] if len(usable) > sessions else usable

    arms = []
    for regime in ("intraday", "overnight"):
        for L in LADDER:
            arms.append(ladder_arm(panel, w, idx, regime=regime, L=L, cost_bps=cost_bps,
                                   margin_rate=margin_rate, gross_cap=gross_cap))

    # THE HOUSE BETA IS QUOTED; THIS ONE IS MEASURED. They are different numbers
    # about different books and the receipt keeps them apart. 2.10 was measured
    # on what the fleet actually HELD over the graded sessions; this is today's
    # sealed basket regressed on SPY over the static window. If they disagree
    # the disagreement is the finding, not an error to be reconciled away.
    def _base(regime: str) -> dict:
        return next((a for a in arms if a["regime"] == regime and a["multiplier"] == 1.0), {})
    gross_1x = _base("overnight").get("gross_of_equity") or 1.0
    measured = {}
    for regime in ("intraday", "overnight"):
        beta = _base(regime).get("realized_beta_vs_spy")
        measured[regime] = {
            "beta_of_the_book_as_sized": beta,
            "beta_per_dollar_of_gross": (round(beta / gross_1x, 4) if beta is not None else None),
            "n_sessions": _base(regime).get("n_sessions"),
        }

    beta_used = max([HOUSE_BOOK_BETA]
                    + [v["beta_per_dollar_of_gross"] for v in measured.values()
                       if v["beta_per_dollar_of_gross"] is not None])
    wc = worst_case_table(b, equity=equity, gross_cap=gross_cap, stop=stop,
                          profile=profile, beta=beta_used)

    pit = pit_sessions(panel, day, book) if not variant else []

    cap = PV.capacity({"holdings": b["holdings"]}, equity=equity)
    cap_by_rung = {f"{L:.1f}x": PV.capacity({"holdings": b["holdings"]}, equity=equity,
                                            gross_multiplier=L)["n_flagged"]
                   for L in LADDER}

    return {
        "schema": "leverage-ladder-1",
        "day": day,
        "book": label,
        "source": b["source"],
        "sha_verified": b["sha_verified"],
        "content_sha256": b["content_sha256"],
        "computed_at_utc": datetime.now(timezone.utc).isoformat(),
        "licence": "PRODUCT_EXPERIMENT -- backtest and shadow. No order path reads this file.",
        "equity_usd": equity,
        "risk_profile": profile,
        "gross_cap_at_1x": gross_cap,
        "stop_fraction": stop,
        "cost_bps_one_way": cost_bps,
        "margin_rate": margin_rate,
        "holdings": b["holdings"],
        "symbols_without_bars": missing,
        "beta_arithmetic": {
            "house_book_beta": HOUSE_BOOK_BETA,
            "source": HOUSE_BOOK_BETA_SOURCE,
            "statement": (f"the book's measured market beta is {HOUSE_BOOK_BETA:.2f}. At 4x "
                          f"notional that is a {HOUSE_BOOK_BETA * 4:.1f}-beta book. A leverage "
                          "experiment that targets RISK rather than notional solves for the "
                          "multiplier that gives the chosen beta: to hold a 2.0-beta book from "
                          f"a {HOUSE_BOOK_BETA:.2f}-beta one the multiplier is "
                          f"{2.0 / HOUSE_BOOK_BETA:.2f}x, which is BELOW 1.0, not above it."),
            "risk_targeted_multiplier_for_beta": {
                f"beta_{t:.1f}": round(t / HOUSE_BOOK_BETA, 3) for t in (1.0, 2.0, 3.0, 4.0)},
            "measured_on_this_window": measured,
            "measured_note": ("the house number was measured on what the fleet HELD over the "
                              "graded sessions; this one is today's sealed basket regressed on "
                              "SPY over the static window, which is a different book over a "
                              "different period. Where they disagree, the disagreement is the "
                              "finding -- and the LADDER arithmetic uses the HIGHER of the two, "
                              "because a leverage bound that assumes the friendlier beta is a "
                              "bound that fails on the day it is needed."),
            "beta_used_for_the_ladder": beta_used,
        },
        "worst_case_first": wc,
        "windows": {
            "STATIC_SET": {
                "n_sessions": len(idx),
                "first": panel.dates[idx[0]] if idx else None,
                "last": panel.dates[idx[-1]] if idx else None,
                "what_it_is": (f"TODAY's {label} holdings held constant over the trailing "
                               f"{len(idx)} sessions."),
                "why_it_is_not_evidence": (
                    "THE NAMES WERE CHOSEN WITH DATA FROM THE END OF THIS WINDOW, and for "
                    "THIS rule the bias runs DOWNWARD, not upward -- which is the opposite of "
                    "the usual hindsight-basket warning and matters more. The book selects on "
                    "a high consensus-target-to-price ratio, and a name gets that ratio mostly "
                    "by FALLING: the 2026-09-02 hack3 holdings average -20.0% from their own "
                    "60-session high (AGGRESSIVE averages -35.8%). Replaying today's admitted "
                    "set backwards therefore reproduces the fall that made them admissible. "
                    "So the LEVEL of every wealth number below is mechanically negative and is "
                    "NOT evidence the book is bad; only the SHAPE is readable -- how fast "
                    "drawdown, variance drag and beta grow with the multiplier, which is what "
                    "the ladder was built to show."),
            },
            "PIT_SEALED": {
                "n_sessions": len(pit),
                "what_it_is": ("each sealed book graded on ITS OWN session. The only PIT "
                               "evidence that exists."),
                "why_it_is_short": (
                    "the portfolios block first appears in the 2026-08-31 seal and the "
                    "tracker day files begin 2026-08-30, so there is no daily book history "
                    "to replay further back. n is what it is; computing harder does not "
                    "make it larger."),
                "sessions": pit,
            },
        },
        "arms": arms,
        "capacity": cap,
        "capacity_flags_by_rung": cap_by_rung,
        "paper_fill_caveat": (
            "ALPACA PAPER FILLS IGNORE NBBO SIZE. Every levered number here assumes the "
            "whole position fills at the open and the close at no impact. At 4x, the "
            f"positions are 4x the sizes in `capacity`, and {cap_by_rung.get('4.0x')} of "
            f"{len(b['holdings'])} names cross {PV.CAPACITY_FLAG:.0%} of their own median "
            "daily dollar volume there. Any 4x result is OPTIMISTIC by an amount this "
            "receipt bounds and does not correct."),
    }


def _last_closed(panel: lab.Panel) -> str:
    return panel.dates[-1] if panel.dates else ""


# --------------------------------------------------------------------------
# Printing
# --------------------------------------------------------------------------

def _print(r: dict) -> None:
    eq = r["equity_usd"]
    print(f"\n{'=' * 78}")
    print(f"LEVERAGE LADDER   book {r['book']}   day {r['day']}   equity ${eq:,.0f}")
    print(f"source {r['source']}  sha {str(r['content_sha256'])[:10]}  "
          f"verified {r['sha_verified']}  profile {r['risk_profile']}")
    print("=" * 78)

    ba = r["beta_arithmetic"]
    print("\nTHE BETA ARITHMETIC (say it before the ladder, not after):")
    print(f"  {ba['statement']}")
    for regime, m in ba["measured_on_this_window"].items():
        b_ = m["beta_per_dollar_of_gross"]
        print(f"  measured here ({regime}, n={m['n_sessions']}): "
              + ("unmeasurable" if b_ is None else f"beta {b_:.2f} per dollar of gross")
              + f" vs the house {HOUSE_BOOK_BETA:.2f}")
    print(f"  the ladder's beta-equivalent column uses {ba['beta_used_for_the_ladder']:.2f} "
          "-- the higher of the two, because a bound that assumes the friendlier beta "
          "fails on the day it is needed.")

    print("\nWORST CASE FIRST -- computed before any average")
    print(f"  {'mult':>5} {'gross':>7} {'gross $':>12} {'all-stop':>10} {'  $':>12} "
          f"{'all-gap':>9} {'  $':>12} {'beta-eq':>8} {'intraday util':>14}")
    for row in r["worst_case_first"]:
        print(f"  {row['multiplier']:>4.1f}x {row['gross_of_equity']:>6.0%} "
              f"{row['gross_usd']:>12,.0f} {row['all_stop_loss_fraction']:>9.2%} "
              f"{row['all_stop_loss_usd']:>12,.0f} "
              f"{(row['all_gap_loss_fraction'] or 0):>8.2%} "
              f"{(row['all_gap_loss_usd'] or 0):>12,.0f} "
              f"{row['beta_equivalent']:>8.2f} "
              f"{row['intraday_margin_utilization']:>13.0%}")
    for row in r["worst_case_first"]:
        if row.get("exceeds_equity"):
            print(f"  RUIN at {row['multiplier']:.1f}x: {row['ruin_note']}")
    print(f"  stop {r['stop_fraction']:.0%} (profile {r['risk_profile']}); the all-gap column "
          f"is gross x the mean of the holdings' own modelled downside_5pct.")
    print("  A stop does not survive a gap. The right-hand column is the one to argue with.")

    w = r["windows"]["STATIC_SET"]
    print(f"\nWINDOW  STATIC_SET  {w['n_sessions']} sessions  {w['first']} -> {w['last']}")
    print("  SELECTION-BIASED, AND DOWNWARD: this book selects names by target/price, which a")
    print("  name earns mostly by FALLING, so replaying today's set backwards reproduces the")
    print("  fall that made it admissible. Read the SHAPE of the ladder here, never the level.")
    print(f"\n  {'regime':<10} {'mult':>5} {'gross':>6} {'wealth':>9} {'geo/sess':>10} "
          f"{'maxDD':>8} {'worst':>8} {'CVaR5':>8} {'beta':>7} {'util':>6}")
    for a in r["arms"]:
        if not a.get("permitted"):
            print(f"  {a['regime']:<10} {a['multiplier']:>4.1f}x {a['gross_of_equity']:>5.0%}  "
                  f"REFUSED -- above the {OVERNIGHT_BUYING_POWER:.0f}x overnight bound")
            continue
        if not a.get("n_sessions"):
            print(f"  {a['regime']:<10} {a['multiplier']:>4.1f}x  no readable session")
            continue
        print(f"  {a['regime']:<10} {a['multiplier']:>4.1f}x {a['gross_of_equity']:>5.0%} "
              f"{a['terminal_wealth']:>9.4f} {a['geometric_mean_per_session']:>9.3%} "
              f"{a['max_drawdown']:>8.2%} {a['worst_session']:>8.2%} {a['cvar_5pct']:>8.2%} "
              f"{(a['realized_beta_vs_spy'] if a['realized_beta_vs_spy'] is not None else float('nan')):>7.2f} "
              f"{a['margin_utilization']:>5.0%}")

    pit = r["windows"]["PIT_SEALED"]
    print(f"\nWINDOW  PIT_SEALED  {pit['n_sessions']} session(s) -- {pit['why_it_is_short'][:90]}...")
    for s in pit["sessions"]:
        ln = s["book"]
        sp = s["spy"]
        def f(x):
            return "   n/a " if x is None else f"{x:+7.2%}"
        print(f"  {s['day']}  sha {s['sha256']}  n={s['n']:<3} "
              f"intraday {f(ln['intraday'])} (SPY {f(sp['intraday'])})   "
              f"session {f(ln['session'])} (SPY {f(sp['session'])})   "
              f"gap {f(ln['gap'])}")
    if pit["n_sessions"] < 3:
        print("  n < 3. Nothing here is an estimate of anything; it is a record.")

    cap = r["capacity"]
    print(f"\nCAPACITY at 1x (${eq:,.0f} equity): worst "
          f"{cap['worst_pct_of_median_dollar_volume']:.2%} of median daily $ volume, "
          f"{cap['n_flagged']} name(s) above {cap['flag_threshold']:.0%}")
    print("  flags by rung: " + "  ".join(f"{k} {v}" for k, v in r["capacity_flags_by_rung"].items()))
    print(f"  {r['paper_fill_caveat'][:150]}...")
    if r["symbols_without_bars"]:
        print(f"\n  NO BARS (weight dropped, not redistributed): {r['symbols_without_bars']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--day", help="sealed day (default: the newest seal on disk)")
    ap.add_argument("--book", default="hack3", help="hack3 | hack4 | hack6")
    ap.add_argument("--variant", help="a shadow variant book name instead of a sealed book")
    ap.add_argument("--equity", type=float, default=PV.DEFAULT_EQUITY)
    ap.add_argument("--sessions", type=int, default=45)
    ap.add_argument("--cost-bps", type=float, default=lab.EQUITY_BPS,
                    help="one-way spread + impact, bps (house default from alpha.lab)")
    ap.add_argument("--margin-rate", type=float, default=MARGIN_RATE)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args(argv)

    config.load_env()
    day = args.day
    if not day:
        seals = sorted(p.stem for p in (ROOT / "state" / "predictions").glob("2026-*.json")
                       if "resealed" not in p.name)
        if not seals:
            raise SystemExit("REFUSED: no sealed books on disk.")
        day = seals[-1]

    r = run(day=day, book=args.book, variant=args.variant, equity=args.equity,
            sessions=args.sessions, cost_bps=args.cost_bps, margin_rate=args.margin_rate)
    if args.json:
        print(json.dumps(r, indent=1, ensure_ascii=False))
    else:
        _print(r)
    if not args.no_write:
        OUT.mkdir(parents=True, exist_ok=True)
        p = OUT / f"{day}_{r['book']}.json"
        p.write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"\nreceipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
