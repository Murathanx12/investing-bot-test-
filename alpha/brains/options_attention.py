"""OPTIONS_ATTENTION_v1 -- "someone cares", measured from the chain's own tape.

WHAT THE LITERATURE LICENSES, AND WHAT IT DOES NOT
==================================================
Pan & Poteshman (RFS 2006) found that buyer-initiated OPENING option volume
predicts underlying returns -- with a signed, open/close-tagged dataset the
public feed does not have. Alpaca's free options history gives us daily bars
(volume, trade count) and tick trades with NO side and NO open/close flag.

So this brain does NOT claim to see informed direction. It measures ATTENTION:

    volume_ratio        today's option volume / trailing median      (all strikes)
    trade_ratio         today's trade count  / trailing median
    call_share          call volume / total volume                   (activity, not intent)
    near_term_share     volume in the nearest expiry / total         (urgency)
    otm_share           volume at |delta| < 0.3 / total              (lottery-ness)

A spike in attention is evidence that the market is about to disagree with
itself -- it widens our distribution, it does not tilt it. The sign, if any,
belongs to a different brain.
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

from alpha import config
from alpha.brains.base import Forecast
from alpha.brains.vol_gap import _daily_bars, _ewma_sd
from alpha.data.chain import _decode_occ


class InsufficientTape(RuntimeError):
    pass


def option_bars(client, symbols: list[str], *, start: str, timeframe: str = "1Day") -> dict[str, list]:
    out: dict[str, list] = {}
    for i in range(0, len(symbols), 100):
        batch = symbols[i:i + 100]
        page = client._request(
            "GET", "/v1beta1/options/bars", base=config.data_url(),
            params={"symbols": ",".join(batch), "timeframe": timeframe, "start": start,
                    "limit": 10000},
        )
        out.update((page or {}).get("bars") or {})
    return out


def measure(client, symbol: str, *, expiries: list[str], lookback_days: int = 20,
            spot: float | None = None) -> dict[str, Any]:
    """Attention statistics for one underlying across the given expiries."""
    from alpha.data import chain as chain_mod

    snap = chain_mod.fetch(client, symbol, expiry_from=min(expiries), expiry_to=max(expiries),
                           spot=spot)
    symbols = [c.symbol for c in snap.contracts]
    if not symbols:
        raise InsufficientTape(f"{symbol}: empty chain")
    start = (datetime.now(timezone.utc) - timedelta(days=int(lookback_days * 1.6))).strftime("%Y-%m-%d")
    bars = option_bars(client, symbols, start=start)

    # Only contracts that traded on most of the lookback count. A weekly listed
    # last Thursday has zero volume before it existed, and comparing today
    # against that zero reads as a spike that is really a listing.
    n_days_seen = {occ: len({b["t"][:10] for b in series}) for occ, series in bars.items()}
    horizon_days = max(n_days_seen.values()) if n_days_seen else 0
    seasoned = {occ for occ, n in n_days_seen.items() if n >= 0.8 * horizon_days}
    by_day: dict[str, dict[str, float]] = {}
    for occ, series in bars.items():
        if occ not in seasoned:
            continue
        right, strike, expiry = _decode_occ(occ)
        delta = next((c.delta for c in snap.contracts if c.symbol == occ), None)
        for b in series:
            d = b["t"][:10]
            row = by_day.setdefault(d, {"v": 0, "n": 0, "call_v": 0, "near_v": 0, "otm_v": 0})
            v = float(b.get("v") or 0)
            row["v"] += v
            row["n"] += float(b.get("n") or 0)
            if right == "C":
                row["call_v"] += v
            if expiry == min(expiries):
                row["near_v"] += v
            if delta is not None and abs(delta) < 0.30:
                row["otm_v"] += v
    days = sorted(by_day)
    if len(days) < 6:
        raise InsufficientTape(f"{symbol}: {len(days)} days of option bars")
    latest = by_day[days[-1]]
    trailing_v = [by_day[d]["v"] for d in days[:-1]]
    trailing_n = [by_day[d]["n"] for d in days[:-1]]
    med_v, med_n = statistics.median(trailing_v), statistics.median(trailing_n)
    tot = latest["v"] or 1.0
    return {
        "source": "alpaca_option_bars", "symbol": symbol, "latest_day": days[-1],
        "n_days": len(days), "contracts": len(symbols), "contracts_seasoned": len(seasoned),
        "latest_volume": latest["v"], "trailing_median_volume": med_v,
        "volume_ratio": latest["v"] / med_v if med_v else None,
        "trade_ratio": latest["n"] / med_n if med_n else None,
        "call_share": latest["call_v"] / tot,
        "near_term_share": latest["near_v"] / tot,
        "otm_share": latest["otm_v"] / tot,
        "note": "unsigned volume: attention, not informed direction",
    }


#: How much attention widens the distribution. A 3x volume day adds ~20% to the
#: ordinary sigma; capped so a single print cannot make the brain claim a crash.
WIDEN_PER_LOG_RATIO = 0.18
MAX_WIDEN = 1.6


def forecast(client, symbol: str, horizon_days: float, *, expiries: list[str]) -> Forecast:
    att = measure(client, symbol, expiries=expiries)
    bars = _daily_bars(client, symbol, 90)
    closes = [float(b["c"]) for b in bars]
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    daily_sd = _ewma_sd(rets, 10.0)
    ratio = att["volume_ratio"] or 1.0
    widen = min(MAX_WIDEN, 1.0 + WIDEN_PER_LOG_RATIO * max(0.0, math.log(max(ratio, 1e-6))))
    sd = daily_sd * math.sqrt(max(horizon_days, 0.25)) * widen
    conviction = max(0.3, min(1.0, 0.4 + 0.2 * math.log(max(ratio, 1.0))))
    return Forecast(
        brain="options_attention", symbol=symbol, horizon_days=horizon_days,
        centre=0.0, sd=sd, conviction=conviction,
        rationale=(
            f"option volume {att['latest_volume']:.0f} vs trailing median {att['trailing_median_volume']:.0f} "
            f"({ratio:.2f}x); calls {att['call_share']:.0%}, near-term {att['near_term_share']:.0%}, "
            f"OTM {att['otm_share']:.0%}. Attention widens sigma x{widen:.2f}; no direction claimed."
        ),
        signal_shape="tail",
        evidence={**att, "daily_sd": daily_sd, "widen": widen, "last_close": closes[-1]},
    )
