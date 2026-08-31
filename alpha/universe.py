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

# ---------------------------------------------------------------------------
# OBSERVATION IS NOT EXECUTION (2026-08-31)
#
# One constant used to do two different jobs. `MIN_DOLLAR_VOLUME` decided both
# "can we buy this at our size?" and "are we allowed to KNOW about this?", and
# a single `continue` in `build` deleted the name entirely.
#
# WBUY is what that costs. The news engine ranked it FIRST on 08-31 and wrote a
# real bet on it; the stock moved 20%. It trades ~$25k/day, so it failed the
# $3m floor 120x over -- and therefore never got a CompanyState row, never
# entered the tracker, and could never reach a seal. We did not decide against
# it. We arranged never to have an opinion.
#
# Those are separate questions and they now have separate constants. A name
# below the EXECUTE floor is still observed, still scored, still graded -- it
# simply carries `execution_authority = 0.0`, which is a fact about our size,
# not a fact about the company.
#
# `load()` still defaults to EXECUTE-grade, so every existing caller is
# unchanged. What changes is that being unbuyable is now a PROPERTY of a row
# rather than a reason the row does not exist.
#
# NOT YET TRUE: the stored universe file was BUILT at the execute floor, so
# `load(scope="observe")` returns the same names until `build(scope="observe")`
# is re-run against the venue. The structure is in place; the data is not.
# Stated here so nobody reads the constant and believes the coverage.
# ---------------------------------------------------------------------------

#: Low enough to see a nano-cap that moved on news. Not an invitation to trade
#: one -- see `execution_authority`.
MIN_OBSERVE_DOLLAR_VOLUME = 20_000.0
#: Unchanged. What we can actually transact at our size.
MIN_EXECUTE_DOLLAR_VOLUME = MIN_DOLLAR_VOLUME
#: Never take more than this share of a name's median daily dollar volume.
#: 1% of ADV is a conventional impact-tolerable ceiling; at WBUY's ~$25k/day
#: that is ~$250, which is the honest answer rather than a refusal.
MAX_ADV_PARTICIPATION = 0.01


def execution_authority(median_dollar_volume: float | None, equity: float | None = None) -> dict:
    """How much of THIS name may we buy, and why. Never a reason to stop looking.

    Returns the dollar cap, the same cap as a fraction of `equity` when one is
    given, and a `tier` a human can read. `None` in means UNKNOWN, which is
    reported as unknown and authorises nothing -- an absent dollar volume is
    not a dollar volume of zero and it is not a dollar volume of a million.
    """
    if median_dollar_volume is None:
        return {"tier": "UNKNOWN", "max_usd": 0.0, "max_fraction": 0.0,
                "reason": "no median dollar volume on the row; authority cannot be derived"}
    mdv = float(median_dollar_volume)
    cap = mdv * MAX_ADV_PARTICIPATION
    if mdv < MIN_OBSERVE_DOLLAR_VOLUME:
        tier, reason = "NONE", f"below the ${MIN_OBSERVE_DOLLAR_VOLUME:,.0f}/day observation floor"
    elif mdv < MIN_EXECUTE_DOLLAR_VOLUME:
        tier, reason = "OBSERVE_ONLY", (
            f"${mdv:,.0f}/day is under the ${MIN_EXECUTE_DOLLAR_VOLUME:,.0f} execute floor: "
            f"observable and gradeable, at most ${cap:,.0f} transactable")
    else:
        tier, reason = "FULL", f"${mdv:,.0f}/day clears the execute floor"
    if tier == "NONE":
        cap = 0.0
    return {"tier": tier, "max_usd": round(cap, 2),
            "max_fraction": (round(cap / equity, 6) if equity else 0.0),
            "reason": reason}
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


def build(client, *, lookback_sessions: int = VOL_WINDOW, max_symbols: int | None = None,
          scope: str = "execute") -> list[Member]:
    """Screen the venue's asset list against its own bars. One call per 200 symbols.

    `scope="observe"` screens at the OBSERVATION floor instead, keeping names we
    could never transact so they can still be studied and graded. The execute
    floor is then applied by `load()`, not by deletion here.
    """
    if scope not in ("execute", "observe"):
        raise ValueError(f"scope must be 'execute' or 'observe', not {scope!r}")
    floor = MIN_OBSERVE_DOLLAR_VOLUME if scope == "observe" else MIN_EXECUTE_DOLLAR_VOLUME
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
        if price < MIN_PRICE or med < floor:
            continue
        a = by_sym[sym]
        members.append(Member(
            symbol=sym, name=a.get("name") or "", exchange=a.get("exchange") or "", price=round(price, 4),
            median_dollar_volume=round(med, 0), sessions=len(b),
            shortable=bool(a.get("shortable")), easy_to_borrow=bool(a.get("easy_to_borrow")),
            fractionable=bool(a.get("fractionable")), etf_like=looks_like_etf(a.get("name") or ""),
            dv_bucket=dv_bucket(med),
        ))
    logger.info("universe[%s]: %d members after price>=%.0f and median $vol>=$%s over %d sessions",
                scope, len(members), MIN_PRICE, f"{floor:,.0f}", lookback_sessions)
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


def load(asof: str | None = None, *, scope: str = "execute") -> list[Member]:
    """Members of the stored universe. `scope` is EXECUTE by default.

    "execute" -- names we could transact at our size (the historical behaviour,
                 so every existing caller is unchanged).
    "observe" -- every name we are allowed to have an opinion about. Superset.

    A file built at the execute floor cannot contain observe-only names, so
    "observe" is honest about what is on disk rather than implying coverage it
    does not have: it returns what the file holds, and the file's own screen is
    the limit. Re-run `build(scope="observe")` to widen it.
    """
    if scope not in ("execute", "observe"):
        raise ValueError(f"scope must be 'execute' or 'observe', not {scope!r}")
    files = sorted(STORE.glob(f"{NAME}_*.json"))
    if not files:
        return []
    path = files[-1] if asof is None else STORE / f"{NAME}_{asof}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    members = [Member(**m) for m in data["members"]]
    if scope == "observe":
        return members
    return [m for m in members
            if (m.median_dollar_volume or 0.0) >= MIN_EXECUTE_DOLLAR_VOLUME]


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
