"""Finnhub, free tier. MEASURED 2026-08-25:

    /stock/earnings          200  fiscal periods + EPS surprise (NO report date)
    /calendar/earnings       200  report dates with bmo/amc -- but only FUTURE
                                  dates on the free tier when filtered by symbol
    /company-news            200  headlines + summaries, per symbol, per day
    /stock/social-sentiment  403  premium
    /calendar/economic       403  premium

So historical EVENT DATES are not served here. `event_move` infers them from
fiscal period ends plus the price series, and says so on every row.
"""

from __future__ import annotations

import os
from typing import Any

from alpha.sources.http import SourceRefusal, get_json

BASE = "https://finnhub.io/api/v1"


def _token() -> str:
    tok = os.getenv("AAT_FINNHUB_API_KEY", "").strip()
    if not tok:
        raise SourceRefusal("AAT_FINNHUB_API_KEY is not set")
    return tok


def earnings_periods(symbol: str, limit: int = 16) -> list[dict[str, Any]]:
    """Fiscal quarter ends with EPS estimate/actual, newest first."""
    data, _ = get_json(f"{BASE}/stock/earnings", {"symbol": symbol, "limit": limit, "token": _token()})
    return data or []


def upcoming_earnings(symbol: str, *, start: str, end: str) -> list[dict[str, Any]]:
    """Future report dates with `hour` in {bmo, amc, ''}."""
    data, _ = get_json(f"{BASE}/calendar/earnings",
                       {"symbol": symbol, "from": start, "to": end, "token": _token()})
    return (data or {}).get("earningsCalendar") or []


def earnings_calendar(*, start: str, end: str) -> list[dict[str, Any]]:
    data, _ = get_json(f"{BASE}/calendar/earnings", {"from": start, "to": end, "token": _token()})
    return (data or {}).get("earningsCalendar") or []


def company_news(symbol: str, *, start: str, end: str) -> list[dict[str, Any]]:
    data, _ = get_json(f"{BASE}/company-news",
                       {"symbol": symbol, "from": start, "to": end, "token": _token()})
    return data or []


def probe() -> tuple[bool, float, str]:
    try:
        rows, dt = get_json(f"{BASE}/stock/earnings", {"symbol": "AAPL", "limit": 1, "token": _token()})
        return bool(rows), dt, f"{len(rows)} row(s)"
    except SourceRefusal as exc:
        return False, 0.0, str(exc)


def profile(symbol: str) -> dict[str, Any]:
    """Company profile: marketCapitalization ($M), finnhubIndustry, shareOutstanding, exchange.
    Free tier, 60/min. Called for CANDIDATES only, never for the whole universe."""
    data, _ = get_json(f"{BASE}/stock/profile2", {"symbol": symbol, "token": _token()})
    return data or {}


def recommendation_trends(symbol: str) -> list[dict[str, Any]]:
    """Monthly analyst recommendation counts (strongBuy/buy/hold/sell/strongSell), newest first.
    EVIDENCE, never authority: the parent project's Holm-surviving result is that
    short-horizon winner-chasing is an ANTI-signal; a change in the count is recorded
    beside the candidate so the ranker can be graded on it, not steered by it."""
    data, _ = get_json(f"{BASE}/stock/recommendation", {"symbol": symbol, "token": _token()})
    return data or []
