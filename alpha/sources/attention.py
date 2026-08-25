"""Public ATTENTION measures that answer without a login. Measured 2026-08-25.

    Wikipedia pageviews   200   daily views per article; lags ~1 day
    Alpaca news           200   Benzinga headlines per symbol, ~1s
    Google Trends RSS     200   US daily trending searches (not per-keyword)
    StockTwits            403   blocked
    Reddit .json          403   blocked without OAuth
    GDELT doc API         429   rate-limited on first call
    LunarCrush            paywall

Attention and sentiment are DIFFERENT variables (JFE 2024, "The Social Signal":
sentiment predicts positive next-day returns, attention predicts NEGATIVE ones).
So this module measures attention as a COUNT and never labels it good or bad.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

from alpha.sources.http import SourceRefusal, get_json

WIKI = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents"

#: Ticker -> Wikipedia article. Explicit, because a guess ("Broadcom") can land
#: on a disambiguation page and report zero views as low attention.
WIKI_ARTICLE = {
    "TSLA": "Tesla,_Inc.", "NVDA": "Nvidia", "AVGO": "Broadcom", "AMD": "AMD",
    "AAPL": "Apple_Inc.", "MSFT": "Microsoft", "GOOGL": "Google", "AMZN": "Amazon_(company)",
    "META": "Meta_Platforms", "NIO": "Nio_Inc.", "PANW": "Palo_Alto_Networks",
    "TTWO": "Take-Two_Interactive", "SPY": "SPDR_S&P_500_ETF_Trust", "QQQ": "Invesco_QQQ",
    "CIEN": "Ciena", "MU": "Micron_Technology", "SMH": "VanEck", "IWM": "Russell_2000_Index",
    "LI": "Li_Auto", "XPEV": "XPeng", "EA": "Electronic_Arts",
}


def wiki_views(symbol: str, *, days: int = 30) -> list[tuple[str, int]]:
    article = WIKI_ARTICLE.get(symbol)
    if not article:
        raise SourceRefusal(f"no Wikipedia article mapped for {symbol}")
    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    start = end - timedelta(days=days)
    data, _ = get_json(f"{WIKI}/{article}/daily/{start:%Y%m%d}/{end:%Y%m%d}")
    return [(it["timestamp"][:8], int(it["views"])) for it in data.get("items", [])]


def wiki_attention(symbol: str) -> dict[str, Any]:
    """Latest day's views against the trailing distribution: a z and a ratio.

    `velocity` is the ratio of the latest day to the trailing median;
    `acceleration` compares the last two days' ratios. Both are attention,
    neither is sentiment.
    """
    series = wiki_views(symbol)
    if len(series) < 8:
        raise SourceRefusal(f"{symbol}: only {len(series)} days of pageviews")
    views = [v for _, v in series]
    base = views[:-1]
    med = statistics.median(base)
    sd = statistics.pstdev(base) or 1.0
    latest = views[-1]
    prev = views[-2]
    return {
        "source": "wikipedia_pageviews", "symbol": symbol, "latest_day": series[-1][0],
        "latest_views": latest, "trailing_median": med,
        "velocity": latest / med if med else None,
        "acceleration": (latest / med - prev / med) if med else None,
        "z": (latest - statistics.mean(base)) / sd,
        "n_days": len(series),
        "lag_note": "daily aggregate, ~1 day late",
    }


def alpaca_news(client, symbols: list[str], *, limit: int = 50,
                start: str | None = None) -> list[dict[str, Any]]:
    """Benzinga headlines through Alpaca. Includes `symbols` per story."""
    from alpha import config

    params = {"symbols": ",".join(symbols), "limit": limit, "sort": "desc"}
    if start:
        params["start"] = start
    data = client._request("GET", "/v1beta1/news", base=config.data_url(), params=params)
    return (data or {}).get("news") or []


HN = "https://hn.algolia.com/api/v1/search_by_date"
MASTODON = "https://mastodon.social/api/v1/timelines/tag"


def hn_mentions(query: str, *, hours: int = 48) -> dict[str, Any]:
    """Hacker News stories + comments mentioning `query` in the window. Measured
    2026-08-25: 200, no auth. A developer-crowd attention count."""
    since = int((datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp())
    stories, _ = get_json(HN, {"query": query, "tags": "story", "numericFilters": f"created_at_i>{since}",
                               "hitsPerPage": 100})
    comments, _ = get_json(HN, {"query": query, "tags": "comment",
                                "numericFilters": f"created_at_i>{since}", "hitsPerPage": 100})
    hits = stories.get("hits") or []
    return {"source": "hn_algolia", "query": query, "hours": hours,
            "stories": stories.get("nbHits", len(hits)), "comments": comments.get("nbHits", 0),
            "points": sum(int(h.get("points") or 0) for h in hits),
            "top": [{"title": h.get("title"), "points": h.get("points"), "url": h.get("url")}
                    for h in sorted(hits, key=lambda h: -(h.get("points") or 0))[:5]]}


def mastodon_tag(tag: str, *, limit: int = 40) -> dict[str, Any]:
    """Public federated posts on a hashtag. Thin, but real-time and open."""
    posts, _ = get_json(f"{MASTODON}/{tag}", {"limit": limit})
    now = datetime.now(timezone.utc)
    ages = []
    for p in posts or []:
        try:
            ages.append((now - datetime.fromisoformat(p["created_at"].replace("Z", "+00:00"))).total_seconds() / 3600)
        except (KeyError, ValueError):
            pass
    return {"source": "mastodon_social", "tag": tag, "n": len(posts or []),
            "span_hours": (max(ages) if ages else None),
            "posts_per_hour": (len(ages) / max(ages)) if ages and max(ages) > 0 else None}


def probe() -> tuple[bool, float, str]:
    try:
        import time
        t0 = time.time()
        s = wiki_views("TSLA", days=7)
        return bool(s), time.time() - t0, f"{len(s)} days, latest {s[-1] if s else None}"
    except SourceRefusal as exc:
        return False, 0.0, str(exc)
