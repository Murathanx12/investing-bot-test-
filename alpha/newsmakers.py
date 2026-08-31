"""WHO IS THE WORLD TALKING ABOUT TODAY -- whole-market first, our list second.

THE INVERSION
=============
`premarket_digest.universe()` built a fixed list (window printers + theme names
+ SPY/QQQ/IWM, ~141 names) and then asked the news feed *"what has been written
about MY list"*. That answers the wrong question twice over:

  * a name making news today is invisible unless it was already on the list;
  * the list is fixed, so the digest cannot adapt to the day.

The feed will answer the other question -- omit the symbol filter and it
returns the whole market. Measured 2026-08-31: one 50-item page carried **79
distinct symbols**, including SPCX, WBUY, CANG and PXS, none of which the fixed
141 contained.

So: read the world, rank who is genuinely making news, put them first, and THEN
add our own candidate list. Nothing here is a fixed number.

WHY RAW ARTICLE COUNT IS THE WRONG RANKING
==========================================
Benzinga files 1,566 items on NVDA and 3 on a small biotech -- a 390:1 ratio
that is a fact about REPORTERS, not about companies. Ranking on raw count is
therefore a mega-cap filter wearing a number, and it is exactly what the tracker
exists to remove.

Murat's rule, stated repeatedly and implemented here:

    "less news doesn't mean this company is less secure. It just means we have
     less data ... normalize them"

So a name is ranked on **how unusual today's attention is FOR ITSELF**, not on
how much of it there is:

  * `attention_z`  -- today's article count against that name's OWN trailing
                      mean and spread. Ten articles is nothing for NVDA and an
                      event for a biotech.
  * `is_new`       -- we have never recorded news on this name. That is not a
                      zero; it is the coverage-initiation signal, and it gets a
                      real slot rather than last place.
  * `n_sources`    -- distinct outlets. Ten syndicated copies of one wire story
                      are one event with high corroboration, not ten events.

EVIDENCE DENSITY IS NOT EXPECTED UPSIDE. This module ranks ATTENTION only. It
says who to look at, never what to buy, and a name with two articles can
outrank a name with two hundred.
"""

from __future__ import annotations

import json
import statistics as st
from datetime import datetime, timezone
from pathlib import Path

#: Baseline history. One row per day per symbol; append-only, so the normaliser
#: gets better every session it runs and never silently loses a day.
BASELINE = Path("state") / "attention_baseline.jsonl"

#: Days of history behind a z-score. Below this a name is ranked as NEW rather
#: than against a mean of one observation, which is not a mean.
MIN_BASELINE_DAYS = 3

#: Instruments that are not equities we trade. Crypto pairs come through the
#: same feed and would otherwise dominate a whole-market attention ranking.
_NON_EQUITY_SUFFIXES = ("USD", "USDT", "BTC", "ETH")


def is_tradeable_symbol(sym: str) -> bool:
    """Equity tickers only. `BTCUSD` and `ZECUSD` arrive on the same feed."""
    s = (sym or "").strip().upper()
    if not s or not s.isalpha() or len(s) > 5:
        return False
    # `len(s) > len(x)` alone skips the EXACT match: "USDT" never got compared
    # against the "USDT" entry, so the crypto pair passed as an equity.
    return not any(s == x or (len(s) > len(x) and s.endswith(x))
                   for x in _NON_EQUITY_SUFFIXES)


def tally(items: list[dict]) -> dict[str, dict]:
    """Per-symbol attention for one batch of whole-market news items.

    Counts ARTICLES and DISTINCT SOURCES separately: a wire story republished by
    ten outlets is one event corroborated ten times, and collapsing those into
    one number is how 850 copies became 850 signals.
    """
    out: dict[str, dict] = {}
    for it in items:
        if "refusal" in it:
            continue
        syms = [s for s in (it.get("symbols") or []) if is_tradeable_symbol(s)]
        # A story tagged with fifteen tickers is a market wrap, not news about
        # any one of them. It still counts, but weighted down, or an index
        # round-up would nominate its whole tag list.
        weight = 1.0 / max(1, len(syms)) ** 0.5
        for s in syms:
            d = out.setdefault(s.upper(), {"symbol": s.upper(), "n_articles": 0,
                                           "weighted": 0.0, "sources": set(),
                                           "headlines": [], "first_at": None})
            d["n_articles"] += 1
            d["weighted"] += weight
            if it.get("source"):
                d["sources"].add(str(it["source"]))
            if len(d["headlines"]) < 3 and it.get("headline"):
                d["headlines"].append(str(it["headline"])[:160])
            at = it.get("at")
            if at and (d["first_at"] is None or str(at) < d["first_at"]):
                d["first_at"] = str(at)
    for d in out.values():
        d["n_sources"] = len(d["sources"])
        d["sources"] = sorted(d["sources"])[:6]
        d["weighted"] = round(d["weighted"], 3)
    return out


def load_baseline(path: Path = BASELINE) -> dict[str, list[float]]:
    """{symbol: [daily article counts]} from the append-only history."""
    if not path.exists():
        return {}
    hist: dict[str, list[float]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        for sym, n in (row.get("counts") or {}).items():
            hist.setdefault(sym.upper(), []).append(float(n))
    return hist


def append_baseline(day: str, counts: dict[str, int], path: Path = BASELINE) -> None:
    """One row per day. Append-only: the normaliser improves with every run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"day": day, "at": datetime.now(timezone.utc).isoformat(),
                             "counts": counts}) + "\n")


def score(today: dict[str, dict], baseline: dict[str, list[float]]) -> list[dict]:
    """Rank by how unusual today's attention is FOR EACH NAME.

    Never by raw count. A name with a long quiet history and four articles today
    outranks a name that gets forty every day, which is the entire point.
    """
    rows = []
    for sym, d in today.items():
        hist = baseline.get(sym) or []
        row = dict(d)
        row["baseline_days"] = len(hist)
        if len(hist) >= MIN_BASELINE_DAYS:
            mu = st.mean(hist)
            # A name whose history is perfectly flat has sd 0; a single extra
            # article would then be an infinite z. Floor the spread at 1 article
            # so "unusual" stays a statement about size, not about division.
            sd = max(st.pstdev(hist), 1.0)
            row["baseline_mean"] = round(mu, 2)
            row["attention_z"] = round((d["n_articles"] - mu) / sd, 2)
            row["basis"] = "z vs own trailing history"
            row["is_new"] = False
        else:
            row["attention_z"] = None
            row["basis"] = f"NEW: {len(hist)} prior days (< {MIN_BASELINE_DAYS})"
            row["is_new"] = True
        rows.append(row)

    # A NEW name cannot have a z-score, and ranking it last would rebuild the
    # fame filter this module exists to remove -- the never-covered biotech is
    # precisely the name we want to see. It is ranked on its own attention
    # relative to TODAY's cross-section instead, so it competes on the one
    # comparison that is available.
    known = [r for r in rows if not r["is_new"]]
    med_z = st.median([r["attention_z"] for r in known]) if known else 0.0
    counts = [r["n_articles"] for r in rows] or [1]
    hi = max(counts)
    for r in rows:
        if r["is_new"]:
            # Sits at the median of the known names, nudged by today's volume:
            # visible, never automatically first, never automatically last.
            r["rank_score"] = round(med_z + (r["n_articles"] / hi), 3)
        else:
            r["rank_score"] = round(r["attention_z"], 3)
    rows.sort(key=lambda r: (-r["rank_score"], -r["n_sources"], r["symbol"]))
    return rows


def adaptive_universe(*, newsmakers: list[dict], candidates: list[str],
                      always: list[str], extra: list[str] | None = None,
                      top_news: int | None = None) -> dict:
    """The day's list: who is making news FIRST, then our own candidates.

    `top_news=None` means take every name that made news -- adaptive by default.
    Returns the list AND where each name came from, because a universe that
    cannot say why a name is in it cannot be debugged.
    """
    news_syms = [r["symbol"] for r in newsmakers]
    if top_news is not None:
        news_syms = news_syms[:top_news]
    seen, ordered, origin = set(), [], {}

    def add(syms, tag):
        for s in syms:
            s = (s or "").strip().upper()
            if not s or s in seen:
                if s and s in seen:
                    origin[s] = origin[s] + "+" + tag if tag not in origin[s] else origin[s]
                continue
            seen.add(s)
            ordered.append(s)
            origin[s] = tag

    add(news_syms, "news")          # FIRST -- the day decides, not the list
    add(candidates, "candidate")    # then what our own screen likes
    add(always, "always")           # index proxies for context
    add(extra or [], "manual")
    return {"symbols": ordered, "origin": origin,
            "n_news": len(news_syms), "n_candidates": len(candidates),
            "n_total": len(ordered),
            "note": ("news-first, adaptive: no fixed universe size. A name is here "
                     "because the world spoke about it today, because our screen "
                     "likes it, or because it is an index proxy -- and `origin` "
                     "says which.")}
