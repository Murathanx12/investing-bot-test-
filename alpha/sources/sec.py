"""SEC EDGAR submissions -- EXACT earnings release dates, free, no auth.

An 8-K carrying Item 2.02 ("Results of Operations and Financial Condition")
IS the earnings release, and `acceptanceDateTime` says when it hit EDGAR:
~20:xx UTC is an after-close print, ~11:xx-13:xx UTC a before-open one. That
is a better event calendar than any paid feed for US filers, and it was one
GET away the whole time. Measured 2026-08-25: NVDA 25 prints back to 2020,
AMZN 24, each with the release time to the second.

Foreign private issuers (NIO, LI, XPEV, ...) file 6-K with no item codes, so
they are NOT covered here; the caller falls back to price-based inference and
says so on the row.

The UA is the form EDGAR's fair-access policy asks for. 10 req/s.
"""

from __future__ import annotations

import functools
from datetime import datetime, timezone
from typing import Any

from alpha.sources.http import SourceRefusal, get_json

UA = {"User-Agent": "AegisAlphaTerminal research mrthnabdullaev@gmail.com"}
TICKERS = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"


@functools.lru_cache(maxsize=1)
def _cik_map() -> dict[str, int]:
    data, _ = get_json(TICKERS, headers=UA)
    return {v["ticker"].upper(): int(v["cik_str"]) for v in data.values()}


def cik_for(symbol: str) -> int:
    m = _cik_map()
    if symbol.upper() not in m:
        raise SourceRefusal(f"{symbol}: not in SEC company_tickers.json")
    return m[symbol.upper()]


def earnings_releases(symbol: str) -> list[dict[str, Any]]:
    """Every 8-K with Item 2.02, newest first: date, accepted_utc, session."""
    data, _ = get_json(SUBMISSIONS.format(cik=cik_for(symbol)), headers=UA)
    f = (data.get("filings") or {}).get("recent") or {}
    forms, dates = f.get("form") or [], f.get("filingDate") or []
    accepted = f.get("acceptanceDateTime") or [None] * len(forms)
    items = f.get("items") or [""] * len(forms)
    out = []
    for i, form in enumerate(forms):
        if form != "8-K" or "2.02" not in (items[i] or ""):
            continue
        acc = accepted[i]
        session = "unknown"
        if acc:
            hh = datetime.fromisoformat(acc.replace("Z", "+00:00")).astimezone(timezone.utc).hour
            # 13:30 UTC is the 09:30 ET bell (EDT); 20:00 UTC the 16:00 close.
            session = "bmo" if hh < 13 or (hh == 13 and datetime.fromisoformat(
                acc.replace("Z", "+00:00")).minute < 30) else ("amc" if hh >= 20 else "intraday")
        out.append({"date": dates[i], "accepted_utc": acc, "session": session, "items": items[i],
                    "date_source": "sec_8k_item_2.02"})
    if not out:
        raise SourceRefusal(f"{symbol}: no 8-K Item 2.02 filings (foreign filer or not covered)")
    return out


def probe() -> tuple[bool, str]:
    try:
        r = earnings_releases("NVDA")
        return True, f"{len(r)} releases, latest {r[0]['date']} {r[0]['session']}"
    except SourceRefusal as exc:
        return False, str(exc)
