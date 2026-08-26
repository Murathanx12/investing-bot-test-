"""HIGH_DISPERSION_US_v1 -- the whole listed market, not the names with good chains.

THE COMPLAINT THIS ANSWERS
==========================
Every book this engine has run held SPY, QQQ, NVDA, TSLA, AMD, META, AVGO. Not
because a search found them but because the search space was the fifteen names
in `scripts/run_pass.UNIVERSE`, chosen for their option chains. NVDA is ~8% of
SPY and information technology ~37% of it, so five of those symbols were one
and a half bets. The system had optimised for TRADABILITY, not for where the
mispricing is. With shares as a structure there is no longer a structural
excuse: a $400M name with a measured edge can simply be bought or shorted.

WHAT THIS FILE DOES
===================
Builds and caches the universe from the venue's own asset list plus its bars:

    every active, tradable US common equity on NYSE / NASDAQ / ARCA / AMEX / BATS
    price >= MIN_PRICE, median dollar volume over VOL_WINDOW sessions >= MIN_DOLLAR_VOLUME
    ETF-like names flagged (they are benchmarks and hedges, not alpha instruments)
    size bucket by DOLLAR VOLUME until a market cap is read for the candidates
    (Finnhub profile, called per candidate, never per universe)

and audits candidate-generation bias: a candidate report that is repeatedly
mega-cap / index-member heavy raises `UNIVERSE_COLLAPSE`. Membership of an
index, fame and a liquid chain add NO score anywhere in this module. Liquidity
decides whether and how a position can be executed; it does not decide whether
the idea deserves to exist.

Market cap is NOT in the venue's asset record, so the screen below is by dollar
volume and price -- stated plainly rather than pretending a cap screen ran.
"""

from __future__ import annotations

import json
import logging
import statistics
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

NAME = "HIGH_DISPERSION_US_v1"
STORE = Path(__file__).resolve().parent.parent / "state" / "universe"
EXCHANGES = frozenset({"NYSE", "NASDAQ", "ARCA", "AMEX", "BATS"})
MIN_PRICE = 2.0
MIN_DOLLAR_VOLUME = 3_000_000.0
VOL_WINDOW = 60
#: Dollar-volume buckets used until a market cap is read. Labelled as such.
DV_BUCKETS = (("micro", 0.0), ("small", 10e6), ("mid", 50e6), ("large", 300e6), ("mega", 2e9))
ETF_WORDS = ("ETF", "TRUST", "FUND", "INDEX", "ISHARES", "PROSHARES", "SPDR", "VANGUARD", "INVESCO",
             "DIREXION", "ETN", "PORTFOLIO", "STRATEGY SHARES", "BITCOIN", "ETHER")
#: Reference: the names the old universe was. Used ONLY to audit collapse.
OLD_UNIVERSE = frozenset({"SPY", "QQQ", "IWM", "NVDA", "AVGO", "AMD", "TSLA", "META", "AAPL", "MSFT",
                          "GOOGL", "AMZN", "NIO", "PANW", "SMH"})
#: Murat's own holdings: a CONTROL universe. Fed through the same ranking as
#: everything else, never preferred; the question is whether the engine would
#: have found them, prospectively, and why.
CONTROL_HOLDINGS = ("SLDP", "DKNG", "HUBS", "BHVN", "AMSC", "KYTX", "PRCH", "NTLA", "ABSI", "QUBT", "AARD", "SOC")


@dataclass
class Member:
    symbol: str
    name: str
    exchange: str
    price: float
    median_dollar_volume: float
    sessions: int
    shortable: bool
    easy_to_borrow: bool
    fractionable: bool
    etf_like: bool
    dv_bucket: str
    market_cap_usd: float | None = None
    industry: str | None = None


def dv_bucket(dollar_volume: float) -> str:
    out = DV_BUCKETS[0][0]
    for name, floor in DV_BUCKETS:
        if dollar_volume >= floor:
            out = name
    return out


def cap_bucket(market_cap_usd: float | None) -> str | None:
    if market_cap_usd is None:
        return None
    for name, floor in (("micro", 0.0), ("small", 300e6), ("mid", 2e9), ("large", 10e9), ("mega", 200e9)):
        if market_cap_usd >= floor:
            out = name
    return out


def looks_like_etf(name: str) -> bool:
    u = (name or "").upper()
    return any(w in u for w in ETF_WORDS)


def build(client, *, lookback_sessions: int = VOL_WINDOW, max_symbols: int | None = None) -> list[Member]:
    """Screen the venue's asset list against its own bars. One call per 200 symbols."""
    assets = client.assets()
    raw = [a for a in assets
           if a.get("tradable") and a.get("status") == "active"
           and (a.get("exchange") or "") in EXCHANGES
           and (a.get("class") or a.get("asset_class") or "us_equity") == "us_equity"
           and "." not in (a.get("symbol") or "") and "/" not in (a.get("symbol") or "")]
    logger.info("universe: %d active tradable US equities on %s", len(raw), sorted(EXCHANGES))
    symbols = sorted(a["symbol"] for a in raw)
    if max_symbols:
        symbols = symbols[:max_symbols]
    by_sym = {a["symbol"]: a for a in raw}
    start = (datetime.now(timezone.utc) - timedelta(days=int(lookback_sessions * 1.6))).strftime("%Y-%m-%d")
    bars = client.stock_bars_multi(symbols, start=start)
    members: list[Member] = []
    for sym in symbols:
        b = bars.get(sym) or []
        if len(b) < max(20, lookback_sessions // 2):
            continue
        b = b[-lookback_sessions:]
        dv = [float(x.get("c") or 0.0) * float(x.get("v") or 0.0) for x in b]
        price = float(b[-1].get("c") or 0.0)
        med = statistics.median(dv) if dv else 0.0
        if price < MIN_PRICE or med < MIN_DOLLAR_VOLUME:
            continue
        a = by_sym[sym]
        members.append(Member(
            symbol=sym, name=a.get("name") or "", exchange=a.get("exchange") or "", price=round(price, 4),
            median_dollar_volume=round(med, 0), sessions=len(b),
            shortable=bool(a.get("shortable")), easy_to_borrow=bool(a.get("easy_to_borrow")),
            fractionable=bool(a.get("fractionable")), etf_like=looks_like_etf(a.get("name") or ""),
            dv_bucket=dv_bucket(med),
        ))
    logger.info("universe: %d members after price>=%.0f and median $vol>=%.0fM over %d sessions",
                len(members), MIN_PRICE, MIN_DOLLAR_VOLUME / 1e6, lookback_sessions)
    return members


def save(members: list[Member], *, asof: str | None = None) -> Path:
    STORE.mkdir(parents=True, exist_ok=True)
    asof = asof or datetime.now(timezone.utc).date().isoformat()
    path = STORE / f"{NAME}_{asof}.json"
    path.write_text(json.dumps({
        "name": NAME, "asof": asof, "n": len(members),
        "screen": {"exchanges": sorted(EXCHANGES), "min_price": MIN_PRICE, "min_median_dollar_volume": MIN_DOLLAR_VOLUME,
                   "window_sessions": VOL_WINDOW, "market_cap_screen": "NOT APPLIED (no cap in the venue's asset record)"},
        "members": [asdict(m) for m in members],
    }, indent=0), encoding="utf-8")
    return path


def load(asof: str | None = None) -> list[Member]:
    files = sorted(STORE.glob(f"{NAME}_*.json"))
    if not files:
        return []
    path = files[-1] if asof is None else STORE / f"{NAME}_{asof}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Member(**m) for m in data["members"]]


def composition(members: list[Member]) -> dict:
    n = max(1, len(members))
    by_bucket: dict[str, int] = {}
    by_exch: dict[str, int] = {}
    for m in members:
        by_bucket[m.dv_bucket] = by_bucket.get(m.dv_bucket, 0) + 1
        by_exch[m.exchange] = by_exch.get(m.exchange, 0) + 1
    return {"n": len(members), "etf_like": sum(1 for m in members if m.etf_like),
            "by_dv_bucket": by_bucket, "by_exchange": by_exch,
            "shortable_etb": sum(1 for m in members if m.shortable and m.easy_to_borrow),
            "old_universe_present": sorted(m.symbol for m in members if m.symbol in OLD_UNIVERSE),
            "control_holdings_present": sorted(m.symbol for m in members if m.symbol in CONTROL_HOLDINGS),
            "control_holdings_missing": sorted(set(CONTROL_HOLDINGS) - {m.symbol for m in members})}


#: If more than this share of a candidate report is old-universe / mega names the
#: report says so. The threshold is deliberately low: the old universe is 15
#: names out of ~2,000, so anything above a few percent is the search collapsing.
COLLAPSE_SHARE = 0.30


def collapse_audit(candidates: list[str], members: list[Member] | None = None) -> dict:
    """UNIVERSE_COLLAPSE instrumentation for a candidate list."""
    if not candidates:
        return {"n": 0, "verdict": "EMPTY"}
    by = {m.symbol: m for m in (members or [])}
    old = [c for c in candidates if c in OLD_UNIVERSE]
    mega = [c for c in candidates if by.get(c) and by[c].dv_bucket == "mega"]
    etf = [c for c in candidates if by.get(c) and by[c].etf_like]
    buckets: dict[str, int] = {}
    for c in candidates:
        b = by[c].dv_bucket if c in by else "unknown"
        buckets[b] = buckets.get(b, 0) + 1
    share_old = len(old) / len(candidates)
    share_mega = len(mega) / len(candidates)
    verdict = "UNIVERSE_COLLAPSE" if (share_old > COLLAPSE_SHARE or share_mega > 0.5) else "OK"
    return {"n": len(candidates), "old_universe": old, "share_old_universe": round(share_old, 3),
            "mega": mega, "share_mega": round(share_mega, 3), "etf_like": etf, "by_dv_bucket": buckets,
            "control_holdings_in_candidates": [c for c in candidates if c in CONTROL_HOLDINGS],
            "verdict": verdict}


def enrich(members: list[Member], *, max_calls: int = 50) -> int:
    """Read market cap + industry for up to `max_calls` members (Finnhub, 60/min).
    For CANDIDATES. Returns how many were enriched."""
    from alpha.sources import finnhub
    from alpha.sources.http import SourceRefusal

    n = 0
    for m in members:
        if n >= max_calls:
            break
        if m.market_cap_usd is not None:
            continue
        try:
            p = finnhub.profile(m.symbol)
        except SourceRefusal as exc:
            logger.info("%s: profile not read (%s)", m.symbol, exc)
            continue
        cap = p.get("marketCapitalization")
        m.market_cap_usd = float(cap) * 1e6 if cap else None
        m.industry = p.get("finnhubIndustry")
        n += 1
    return n
