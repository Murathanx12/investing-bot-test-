"""COUNCIL_VECTOR -- the research council's synthesis, read as a forecast.

The council (`alpha/council/run.py`) writes one packet per printer per day to
`state/council/<day>/<SYM>.json`. Its SYNTHESIS step is a thesis VECTOR:
direction, magnitude, volatility_view, timing, p_already_priced, falsifier.
This brain reads the latest packet for a symbol and turns it into a
`direction` claim:

    centre = sign(direction) * magnitude * (1 - p_already_priced)
    sd     = the name's realised vol over the horizon (the runner integrates a
             direction claim against the CHAIN's width anyway)

WHAT REFUSES
============
No packet within `MAX_AGE_DAYS`; a packet whose verdict is not OK (light pass,
partial council, skeptic not independent); direction "none" (including a cube
with zero comparable cells -- the council forces none there); timing
"quarters" (nothing to collect in five sessions); p_already_priced above
`MAX_PRICED`. Every refusal names the field, so the census of refusals says
which stage of the council the account's cash is waiting on.

The council imports no broker code and this brain sends nothing; it is a reader.
"""

from __future__ import annotations

import json
import math
import os
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpha import config
from alpha.brains.base import Forecast

NAME = "council_vector"
MAX_AGE_DAYS = 2
MAX_PRICED = 0.7
STATE = Path(os.getenv("AAT_LEDGER_DIR") or "state")


from alpha.exits import session_day


class NoCouncil(RuntimeError):
    pass


def latest_packet(symbol: str, *, now: datetime | None = None, state: Path | None = None) -> dict:
    root = (state or STATE) / "council"
    now = now or datetime.now(timezone.utc)
    for back in range(MAX_AGE_DAYS + 1):
        day = session_day(now - timedelta(days=back))
        p = root / day / f"{symbol}.json"
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            d["_packet_day"] = day
            return d
    raise NoCouncil(f"{symbol}: no council packet in the last {MAX_AGE_DAYS} days")


def vector_from(packet: dict) -> tuple[float, dict]:
    if packet.get("verdict") != "OK":
        raise NoCouncil(f"{packet.get('symbol')}: council verdict {packet.get('verdict')!r}, not OK")
    if not packet.get("skeptic_independent"):
        raise NoCouncil(f"{packet.get('symbol')}: skeptic was not from an independent model family")
    syn = (packet.get("steps") or {}).get("synthesis") or {}
    direction = str(syn.get("direction", "none")).lower()
    if direction not in ("up", "down"):
        raise NoCouncil(f"{packet.get('symbol')}: synthesis direction {direction!r}"
                        + (" (forced: " + syn["forced_none"] + ")" if syn.get("forced_none") else ""))
    if str(syn.get("timing", "")).lower() == "quarters":
        raise NoCouncil(f"{packet.get('symbol')}: timing 'quarters' -- nothing resolves in five sessions")
    priced = float(syn.get("p_already_priced") or 0.0)
    if priced > MAX_PRICED:
        raise NoCouncil(f"{packet.get('symbol')}: p_already_priced {priced:.2f} > {MAX_PRICED}")
    mag = abs(float(syn.get("magnitude") or 0.0))
    if mag <= 0:
        raise NoCouncil(f"{packet.get('symbol')}: synthesis magnitude is zero")
    centre = (1.0 if direction == "up" else -1.0) * mag * (1.0 - priced)
    return centre, {"direction": direction, "magnitude": mag, "p_already_priced": priced,
                    "timing": syn.get("timing"), "falsifier": syn.get("falsifier"),
                    "families_used": packet.get("families_used"), "packet_day": packet.get("_packet_day"),
                    "causal_confidence": syn.get("causal_confidence")}


def _bars(client, symbol: str, days: int = 130) -> list[dict]:
    start = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    d = client._request("GET", f"/v2/stocks/{symbol}/bars", base=config.data_url(),
                        params={"timeframe": "1Day", "start": start, "limit": 200, "feed": config.stock_feed(),
                                "adjustment": "all"})
    return (d or {}).get("bars") or []


def forecast(client, symbol: str, horizon_days: float, *, bars: list[dict] | None = None,
             packet: dict | None = None) -> Forecast:
    pk = packet or latest_packet(symbol)
    centre, ev = vector_from(pk)
    bars = bars if bars is not None else _bars(client, symbol)
    closes = [float(b["c"]) for b in bars]
    if len(closes) < 30:
        raise NoCouncil(f"{symbol}: {len(closes)} bars < 30")
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    sd_h = statistics.pstdev(rets[-60:]) * math.sqrt(max(horizon_days, 1.0))
    if sd_h <= 0:
        raise NoCouncil(f"{symbol}: zero realised vol")
    conf = float(ev.get("causal_confidence") or 0.6)
    return Forecast(
        brain=NAME, symbol=symbol, horizon_days=horizon_days, centre=centre, sd=sd_h,
        conviction=max(0.2, min(1.2, conf)), claim="direction", signal_shape=None,
        rationale=f"council {ev['direction']} {ev['magnitude']:+.1%} x (1-{ev['p_already_priced']:.2f} priced); {ev['timing']}",
        evidence=ev,
    )
