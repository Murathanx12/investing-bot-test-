"""PUBLIC BELIEF, priced: prediction markets and option-market positioning.

MEASURED 2026-08-25 (no auth, from a HK IP; re-probe from the deploy host):

    Polymarket Gamma   200   markets with outcome prices + 24h volume
    Polymarket CLOB    200   midpoint per token
    Kalshi v2          200   yes bid/ask in dollars, volume, close time
    CBOE daily stats   200   put/call ratios (total/index/equity/SPX/VIX), T+0 evening
    CBOE VIX csvs      200   VIX, VIX9D, VIX3M daily closes -> term structure

A prediction-market price is the closest thing to `market_belief` that exists as
a NUMBER rather than an LLM's guess, which is why it sits beside the LLM axes
rather than inside them: when the two disagree, that disagreement is a finding.
"""

from __future__ import annotations

import csv
import io
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from alpha.sources.http import SourceRefusal, UA, get_json

GAMMA = "https://gamma-api.polymarket.com"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
CBOE = "https://cdn.cboe.com"


# ------------------------------------------------------------------ Polymarket
def polymarket_search(q: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Open markets matching a phrase, with outcome prices."""
    data, _ = get_json(f"{GAMMA}/public-search", {"q": q, "limit_per_type": limit})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = []
    for ev in (data or {}).get("events") or []:
        for m in ev.get("markets") or []:
            row = _pm_row(m, ev.get("title"))
            # Resolved markets price at 0/1 and read as certainty about the
            # past; only OPEN markets with a future end date are belief.
            if row and not row["closed"] and (row["end_date"] or "9999") >= today:
                out.append(row)
    return sorted(out, key=lambda r: (r["end_date"] or "9999", -r["volume_24h"]))


def polymarket_top(*, limit: int = 100) -> list[dict[str, Any]]:
    data, _ = get_json(f"{GAMMA}/markets", {"closed": "false", "limit": limit,
                                          "order": "volume24hr", "ascending": "false"})
    return [r for r in (_pm_row(m) for m in data or []) if r]


def _pm_row(m: dict, event_title: str | None = None) -> dict[str, Any] | None:
    import json as _json

    try:
        outcomes = _json.loads(m.get("outcomes") or "[]")
        prices = [float(p) for p in _json.loads(m.get("outcomePrices") or "[]")]
    except (ValueError, TypeError):
        return None
    if not outcomes or not prices:
        return None
    return {
        "source": "polymarket", "event": event_title, "question": m.get("question"),
        "slug": m.get("slug"), "belief": dict(zip(outcomes, prices)),
        "volume_24h": float(m.get("volume24hr") or 0.0), "liquidity": float(m.get("liquidity") or 0.0),
        "end_date": m.get("endDate"), "closed": m.get("closed"),
    }


# ---------------------------------------------------------------------- Kalshi
KALSHI_SERIES = {
    "fed_decision": "KXFEDDECISION", "payrolls": "KXPAYROLLS", "cpi": "KXCPI",
    "recession": "KXRECSSNBER",
}


def kalshi_markets(series_ticker: str, *, status: str = "open", limit: int = 100,
                   closes_before: str | None = None) -> list[dict[str, Any]]:
    """`closes_before` (ISO date) keeps only markets resolving by then -- the
    August payrolls market closes 4 Sep, inside the window; November's does not."""
    data, _ = get_json(f"{KALSHI}/markets", {"series_ticker": series_ticker, "status": status, "limit": limit})
    rows = []
    for m in (data or {}).get("markets") or []:
        bid, ask = m.get("yes_bid_dollars"), m.get("yes_ask_dollars")
        rows.append({
            "source": "kalshi", "ticker": m.get("ticker"), "title": m.get("title"),
            "subtitle": m.get("subtitle") or m.get("yes_sub_title"),
            "yes_bid": float(bid) if bid is not None else None,
            "yes_ask": float(ask) if ask is not None else None,
            "last": float(m["last_price_dollars"]) if m.get("last_price_dollars") is not None else None,
            "volume": float(m.get("volume_fp") or m.get("volume") or 0.0),
            "close_time": m.get("close_time"),
        })
    if closes_before:
        rows = [r for r in rows if (r["close_time"] or "9999") <= closes_before + "T23:59:59Z"]
    return sorted(rows, key=lambda r: (r["close_time"] or "", r["ticker"] or ""))


# ------------------------------------------------------------------------ CBOE
def _csv(url: str) -> list[list[str]]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return list(csv.reader(io.StringIO(r.read().decode(errors="replace"))))
    except Exception as exc:                                     # noqa: BLE001
        raise SourceRefusal(f"GET {url} -> {exc}") from exc


def vix_term_structure() -> dict[str, Any]:
    """Last close of VIX9D, VIX, VIX3M. Backwardation (9D > 3M) is stress."""
    out: dict[str, Any] = {"source": "cboe"}
    for name in ("VIX9D", "VIX", "VIX3M"):
        rows = _csv(f"{CBOE}/api/global/us_indices/daily_prices/{name}_History.csv")
        last = [r for r in rows if r and r[0][:1].isdigit()][-1]
        out[name] = {"date": last[0], "close": float(last[-1])}
    v9, v30, v90 = out["VIX9D"]["close"], out["VIX"]["close"], out["VIX3M"]["close"]
    out["slope_9d_over_3m"] = v9 / v90 if v90 else None
    out["regime"] = "backwardation" if v9 > v90 else "contango"
    return out


def put_call_ratios(day: str | None = None) -> dict[str, Any]:
    """CBOE daily put/call ratios. `day` YYYY-MM-DD; defaults to the last weekday."""
    d = datetime.fromisoformat(day) if day else datetime.now(timezone.utc) - timedelta(days=1)
    for _ in range(5):
        if d.weekday() < 5:
            try:
                data, _ = get_json(f"{CBOE}/data/us/options/market_statistics/daily/{d:%Y-%m-%d}_daily_options")
                ratios = {r.get("name", "?"): float(r["value"]) for r in (data or {}).get("ratios") or [] if r.get("value") not in (None, "")}
                return {"source": "cboe", "date": f"{d:%Y-%m-%d}", "ratios": ratios}
            except SourceRefusal:
                pass
        d -= timedelta(days=1)
    raise SourceRefusal("no CBOE put/call file in the last five weekdays")


def probe() -> dict[str, tuple[bool, str]]:
    out = {}
    for name, fn in (("polymarket", lambda: polymarket_search("nvidia")),
                     ("kalshi", lambda: kalshi_markets("KXPAYROLLS")),
                     ("cboe_vix", vix_term_structure), ("cboe_pc", put_call_ratios)):
        try:
            r = fn()
            out[name] = (True, f"{len(r) if isinstance(r, list) else 'ok'}")
        except SourceRefusal as exc:
            out[name] = (False, str(exc))
    return out
