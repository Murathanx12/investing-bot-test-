"""RELAY_v1 -- the originator's print, expressed through a peer.

`event_move` speaks only about the name that prints. This brain speaks about
the names that MOVE WHEN IT PRINTS: for a peer P of originator O with a
scheduled print inside the horizon, the forecast on P is

    centre 0
    sd     = sqrt( sd_relay^2 + sd_ordinary^2 )
    sd_relay = RMS of P's close-to-close move across O's last 8 prints

measured, not inferred from a causal graph. The forecast carries O's
`event_date` in its evidence so the runner's EVENT_NODE_CAP treats O + every
relay leg as ONE bet.

SHADOW, and after `scripts/relay_backtest.py` (2026-08-26) SHADOW WITH A REASON:
on 290 relay legs at real closes the peer straddle lost (mean -4.2%, hit 34%,
t -2.0) and the history/implied ratio did not sort the outcome -- the peers'
chains already widen for the originator's date, by more than the peers then
move (docs/FINDING_2026-08-26_RELAY_REFUTED.md). This brain keeps proposing so
the live ratio can be graded against that table; it does not execute.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from alpha.brains.base import Forecast
from alpha.brains import event_move
from alpha.brains.vol_gap import _daily_bars, _ewma_sd
from alpha.sources import finnhub

#: Which peers relay which originator. Measured co-movement decides the SIZE;
#: this table only decides who is asked. Kept small on purpose.
RELAY_MAP: dict[str, list[str]] = {
    "NVDA": ["AMD", "AVGO", "MU", "ARM", "TSM", "SMH", "SOXX"],
    "AVGO": ["NVDA", "AMD", "MRVL", "SMH"],
    "AMD": ["NVDA", "SMH", "MU"],
    "MU": ["WDC", "STX", "SMH"],
    "TSLA": ["RIVN", "NIO"],
    "META": ["SNAP", "PINS", "GOOGL"],
    "AAPL": ["QQQ"],
    "MSFT": ["QQQ"],
}
RECENT = 8
MIN_EVENTS = 4


class NotApplicable(RuntimeError):
    pass


def originators_for(peer: str) -> list[str]:
    return [o for o, peers in RELAY_MAP.items() if peer in peers]


def forecast(client, symbol: str, horizon_days: float, *, lookback_days: int = 800) -> Forecast:
    today = datetime.now(timezone.utc).date()
    end = (today + timedelta(days=int(math.ceil(horizon_days)) + 1)).isoformat()
    origs = originators_for(symbol)
    if not origs:
        raise NotApplicable(f"{symbol}: relays nobody")
    live = None
    for o in origs:
        rows = finnhub.upcoming_earnings(o, start=today.isoformat(), end=end)
        if rows:
            live = (o, rows[0]["date"], rows[0].get("hour") or "")
            break
    if live is None:
        raise NotApplicable(f"{symbol}: no originator in {origs} prints inside {horizon_days:.0f} days")
    orig, event_date, hour = live

    obars = _daily_bars(client, orig, lookback_days)
    events = event_move.event_days_from_sec(obars, orig)
    if len(events) < MIN_EVENTS:
        raise NotApplicable(f"{orig}: only {len(events)} SEC prints")
    days = [e["event_day"] for e in events][-RECENT:]

    bars = _daily_bars(client, symbol, lookback_days)
    idx = {b["t"][:10]: i for i, b in enumerate(bars)}
    closes = [float(b["c"]) for b in bars]
    moves = [math.log(closes[idx[d]] / closes[idx[d] - 1]) for d in days if d in idx and idx[d] > 0]
    if len(moves) < MIN_EVENTS:
        raise NotApplicable(f"{symbol}: only {len(moves)} sessions matched to {orig} prints")
    sd_relay = math.sqrt(sum(m * m for m in moves) / len(moves))

    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    ordinary = [r for r, b in zip(rets, bars[1:]) if b["t"][:10] not in set(days)]
    daily_sd = _ewma_sd(ordinary[-120:], 10.0)
    ordinary_days = max(horizon_days - 1.0, 0.0)
    sd_ordinary = daily_sd * math.sqrt(ordinary_days) if ordinary_days > 0 else 0.0
    sd = math.sqrt(sd_relay ** 2 + sd_ordinary ** 2)
    disp = (max(abs(m) for m in moves) - min(abs(m) for m in moves)) / sd_relay if sd_relay else 9.0
    conviction = max(0.3, min(1.0, 0.4 + 0.05 * len(moves) - 0.1 * max(disp - 1.5, 0.0)))
    return Forecast(
        brain="relay", symbol=symbol, horizon_days=horizon_days, centre=0.0, sd=sd, conviction=conviction,
        rationale=(f"{symbol} relays {orig}'s print on {event_date} {hour or '?'}: on {orig}'s last {len(moves)} "
                   f"prints {symbol} moved RMS {sd_relay:.1%}. Plus {ordinary_days:.0f} ordinary days at "
                   f"{daily_sd:.2%}/day = {sd:.1%}. Centre 0."),
        signal_shape="tail",
        evidence={"originator": orig, "event_date": event_date, "event_hour": hour, "relay_days": days,
                  "relay_moves": moves, "sd_relay": sd_relay, "sd_ordinary": sd_ordinary,
                  "daily_sd_ordinary": daily_sd, "last_close": closes[-1]},
    )
