"""EVENT_MOVE_PRIOR_v1 -- what THIS name does on THIS kind of day.

WHY `vol_gap` IS NOT ENOUGH FOR EARNINGS
========================================
`vol_gap` compares an EWMA of ordinary days with what the chain implies. Around
a scheduled print the chain is not pricing ordinary days; it is pricing one
jump plus a few ordinary days, and the right comparison for the jump is the
name's OWN history of jumps on comparable days:

    implied move to expiry        (from the ATM straddle, real quotes)
        vs
    company-specific event-move distribution   (past prints, absolute close-
                                                to-close return spanning it)

If AVGO's chain implies 5% and AVGO has moved a median 9% on its last eight
prints, that is a different proposition from "realised vol > implied vol", and
it is the proposition the calendar in docs/STRATEGY.md is built around.

WHERE THE EVENT DATES COME FROM, HONESTLY
=========================================
Finnhub's free tier serves FUTURE report dates but not past ones. So past
event days are INFERRED: for each fiscal quarter end the name reported, the
trading day in the [+15d, +75d] window with the largest absolute close-to-close
return is taken as the print. For large caps this is almost always right and
occasionally wrong (a macro shock inside the window), and every inferred date is
written into `evidence["event_days"]` so a reader can check the list instead of
trusting the median -- print the DATES before trusting the statistic.

WHAT THE FORECAST IS
====================
Centre 0 (a print is not a directional forecast from this brain). Spread:

    sd_event    = sqrt(pi/2) * mean|event move|      (E|Z| = sd*sqrt(2/pi))
    sd_ordinary = ewma daily sd * sqrt(ordinary days in the horizon)
    sd          = sqrt(sd_event^2 + sd_ordinary^2)

Conviction falls with a short event history and with dispersion in it: eight
prints that moved 4-14% are a wider claim than eight that moved 8-10%.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

from alpha.brains.base import Forecast
from alpha.brains.vol_gap import _daily_bars, _ewma_sd
from alpha.sources import finnhub, sec
from alpha.sources.http import SourceRefusal

MIN_EVENTS = 4
#: Only the most recent prints set the width. The 2024-26 backtest on real
#: option prices (docs/FINDING_2026-08-25_STRADDLE_BACKTEST.md) found NVDA's
#: recent realised moves at a median 3.2% against a 7.0% implied -- and a
#: 14-print history reaching back to 2023 said 6.6%, which would have bought
#: the straddle that lost on all eight of the last prints. A print
#: distribution is not stationary across a regime; the last two years are
#: the evidence, the older prints are context.
RECENT_EVENTS = 8
WINDOW_AFTER_PERIOD = (15, 75)   # trading-calendar days after fiscal period end


class NotApplicable(RuntimeError):
    """No scheduled event inside the horizon -- this brain has nothing to say."""


def event_days_inferred(bars: list[dict], period_ends: list[str]) -> list[dict[str, Any]]:
    """For each fiscal period end, the largest |return| day in the report window."""
    closes = [(b["t"][:10], float(b["c"])) for b in bars]
    by_idx = {d: i for i, (d, _) in enumerate(closes)}
    out = []
    for pe in period_ends:
        p = date.fromisoformat(pe)
        lo, hi = p + timedelta(days=WINDOW_AFTER_PERIOD[0]), p + timedelta(days=WINDOW_AFTER_PERIOD[1])
        best = None
        for d, c in closes:
            dd = date.fromisoformat(d)
            if lo <= dd <= hi:
                i = by_idx[d]
                if i == 0:
                    continue
                r = math.log(c / closes[i - 1][1])
                if best is None or abs(r) > abs(best[1]):
                    best = (d, r)
        if best and hi <= date.today():
            out.append({"period_end": pe, "event_day": best[0], "move": best[1],
                        "date_source": "inferred_max_abs_return_in_window"})
    out.sort(key=lambda e: e["event_day"])
    return out


def event_days_from_sec(bars: list[dict], symbol: str) -> list[dict[str, Any]]:
    """EXACT prints from SEC 8-K Item 2.02 filings: the first close that reflects
    the release (same day for bmo, next trading day for amc/intraday), and the
    close-to-close move across it. Refuses for foreign filers (6-K, no items)."""
    days = [b["t"][:10] for b in bars]
    closes = [float(b["c"]) for b in bars]
    idx = {d: i for i, d in enumerate(days)}
    out = []
    for r in sec.earnings_releases(symbol):
        d = r["date"]
        if r["session"] == "bmo":
            target = d
        else:
            later = [x for x in days if x > d]
            if not later:
                continue
            target = later[0]
        if target not in idx or idx[target] == 0:
            continue
        i = idx[target]
        out.append({"period_end": None, "event_day": target, "release_date": d, "session": r["session"],
                    "move": math.log(closes[i] / closes[i - 1]), "date_source": r["date_source"]})
    out.sort(key=lambda e: e["event_day"])
    return out


def event_days(bars: list[dict], symbol: str) -> tuple[list[dict[str, Any]], str]:
    """SEC first; price-based inference only when SEC has nothing for the name."""
    try:
        ev = event_days_from_sec(bars, symbol)
        if len(ev) >= MIN_EVENTS:
            return ev, "sec_8k_item_2.02"
    except SourceRefusal:
        pass
    served = [p["period"] for p in finnhub.earnings_periods(symbol, limit=12) if p.get("period")]
    return event_days_inferred(bars, extend_periods(served, years=3)), "inferred_max_abs_return_in_window"


def extend_periods(served: list[str], *, years: int = 3) -> list[str]:
    """Finnhub's free tier serves ~4 fiscal quarter ends. Earlier ones are
    EXTRAPOLATED one quarter back at a time from the oldest served date -- the
    report window is 60 days wide, so a fiscal quarter that drifts a few days is
    still caught. Every extrapolated date is marked as such downstream."""
    if not served:
        return []
    dates = sorted(date.fromisoformat(p) for p in served)
    out = [d.isoformat() for d in dates]
    cursor = dates[0]
    floor = date.today() - timedelta(days=365 * years)
    while cursor > floor:
        # step back ~one quarter, snapping to a month end
        first_of_month = cursor.replace(day=1)
        cursor = (first_of_month - timedelta(days=1))          # previous month end
        cursor = (cursor.replace(day=1) - timedelta(days=1))    # two back
        cursor = (cursor.replace(day=1) - timedelta(days=1))    # three back
        out.append(cursor.isoformat())
    return out


def forecast(client, symbol: str, horizon_days: float, *, event_date: str | None = None,
             event_hour: str | None = None, lookback_days: int = 800) -> Forecast:
    """Distribution over the horizon when a scheduled print sits inside it."""
    today = datetime.now(timezone.utc).date()
    if event_date is None:
        end = (today + timedelta(days=int(math.ceil(horizon_days)) + 1)).isoformat()
        rows = finnhub.upcoming_earnings(symbol, start=today.isoformat(), end=end)
        if not rows:
            raise NotApplicable(f"{symbol}: no scheduled print inside {horizon_days:.0f} days")
        event_date, event_hour = rows[0]["date"], rows[0].get("hour") or ""

    bars = _daily_bars(client, symbol, lookback_days)
    if len(bars) < 120:
        raise NotApplicable(f"{symbol}: {len(bars)} bars, need a history to read events from")
    events, date_source = event_days(bars, symbol)
    if len(events) < MIN_EVENTS:
        raise NotApplicable(f"{symbol}: only {len(events)} inferable past prints (need {MIN_EVENTS})")

    all_abs = [abs(e["move"]) for e in events]
    events_recent = events[-RECENT_EVENTS:]
    abs_moves = [abs(e["move"]) for e in events_recent]
    mean_abs = sum(abs_moves) / len(abs_moves)
    med_abs = sorted(abs_moves)[len(abs_moves) // 2]
    disp = (max(abs_moves) - min(abs_moves)) / mean_abs if mean_abs else 9.0
    sd_event = mean_abs * math.sqrt(math.pi / 2.0)

    closes = [float(b["c"]) for b in bars]
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    # Ordinary-day sigma EXCLUDING the event days, otherwise the print is counted twice.
    ev_days = {e["event_day"] for e in events}
    ordinary = [r for r, b in zip(rets, bars[1:]) if b["t"][:10] not in ev_days]
    daily_sd = _ewma_sd(ordinary[-120:], 10.0)
    ordinary_days = max(horizon_days - 1.0, 0.0)
    sd_ordinary = daily_sd * math.sqrt(ordinary_days) if ordinary_days > 0 else 0.0
    sd = math.sqrt(sd_event ** 2 + sd_ordinary ** 2)

    # Confidence: more prints, tighter distribution -> more.
    conviction = max(0.3, min(1.0, 0.5 + 0.05 * len(events_recent) - 0.15 * max(disp - 1.0, 0.0)))

    return Forecast(
        brain="event_move",
        symbol=symbol,
        horizon_days=horizon_days,
        centre=0.0,
        sd=sd,
        conviction=conviction,
        rationale=(
            f"{symbol} prints {event_date} {event_hour or '?'}. Last {len(events_recent)} prints moved "
            f"mean {mean_abs:.1%} / median {med_abs:.1%} close-to-close (dates: {date_source}). "
            f"Event sd {sd_event:.1%} + {ordinary_days:.0f} ordinary days at {daily_sd:.2%}/day "
            f"= {sd:.1%} over {horizon_days:.1f}d. Centre 0: a print is not a direction."
        ),
        signal_shape="tail",
        evidence={
            "event_date": event_date, "event_hour": event_hour, "date_source": date_source,
            "event_days": events, "mean_abs_event_move": mean_abs,
            "n_recent": len(events_recent), "mean_abs_all_prints": sum(all_abs) / len(all_abs),
            "median_abs_event_move": med_abs, "event_dispersion": disp,
            "sd_event": sd_event, "sd_ordinary": sd_ordinary, "daily_sd_ordinary": daily_sd,
            "n_events": len(events), "last_close": closes[-1],
        },
    )
