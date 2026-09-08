"""Concentration by DRIVER -- what the book is actually betting on, not how
many tickers it spread that bet across.

WHAT FRIDAY COST, AND WHY THE GROSS CAP DOES NOT FINISH THE JOB
===============================================================
28 Aug, hack3: twelve names bought between 09:30:47 and 09:31:00, **eleven
stopped between 09:36 and 09:48**. Twelve tickers, one bet. `sizing.GROSS_
NOTIONAL_CAP` (2026-08-29) bounds Σ|notional| and turns a 300% book into a
100% book, which is most of the arithmetic -- but a 100% gross book that is
100% ONE driver still loses the whole stop width at once. The gross cap asks
"how much", this module asks "how many different things can go wrong", and
those are different questions with different answers.

`alpha/concentration.py` already measures the second question and says so in
its own docstring: *"Measuring is safe; gating changes what the account trades.
This module reports."* It reports on the book AFTER the fact, needs five
sessions of returns for every name, and returns None when it cannot measure.
None of that can sit in the per-order path. So this module is the gate and
that one stays the measurement: same idea, opposite failure mode. Where
`concentration` returns UNKNOWN, this one returns a SHARED bucket.

DECLARED FIRST, DERIVED ONLY TO MERGE
=====================================
Two ways to name a driver, and they fail in opposite directions:

* **DECLARED** -- `docs/seed/universe/THEMES_2026-08-28.json`, Murat's own
  seven themes, `stated_by_human: true`. Cheap, needs no data, and is exactly
  the taxonomy the basket book was built from. It is also a human's opinion
  about what moves together, which is the thing Friday disproved.
* **DERIVED** -- cluster the candidates by realised correlation. Honest, but
  it needs bars, it is silent when they are missing, and a clustering that
  runs in the order path is a new failure mode bolted to the one path that
  must not fail.

So: **declared is the floor, and measurement may only MERGE.** If two
declared-different names moved together over the trailing window they collapse
into one driver; nothing ever SPLITS a declared driver on the strength of a
correlation that happened to be low for sixty sessions. Measurement can only
make the book look MORE concentrated, never less -- the same direction
`concentration.measure` protects when it refuses to treat an unpriced name as
uncorrelated, because the other direction is the one that flatters the book.

A symbol nobody declared is `UNCLASSIFIED`, and every `UNCLASSIFIED` name
shares ONE bucket. That is deliberate and it is the conservative reading: not
knowing whether four names are independent is not evidence that they are.
It costs us breadth in exactly the case where we cannot justify breadth.

THE CAP
=======
`DRIVER_SHARE_OF_GROSS` (40%) of the profile's own gross authority, so the
number moves with the profile instead of being a second constant to keep in
sync. For `basket` (gross 100%, 10% per name) that is 40% of equity per
driver: four names per driver, three drivers to fill the book. Friday's twelve
names were three drivers (uranium, quantum, fuel-cell/solar); at this cap the
same twelve fit only if they really are three, and the worst case at the 8%
basket stop falls from -8% to -3.2% if they turn out to be one.
"""

from __future__ import annotations

import json
import logging
import math
import statistics as st
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

#: Fraction of a profile's GROSS notional authority that one driver may carry.
DRIVER_SHARE_OF_GROSS = 0.40

#: Correlation at or above which two DECLARED drivers are merged into one.
#: 0.60 is below the 0.538 average pairwise correlation of the $20bn book in
#: `concentration.SITUATIONAL_AWARENESS_Q2_2026_N_RISK` and above the level at
#: which two ordinary large caps co-move, so it merges themes, not the market.
MERGE_RHO = 0.60

#: Minimum overlapping sessions before a correlation is allowed to merge
#: anything. Below this the estimate is noise and noise must not create a
#: driver -- merging on noise refuses real breadth.
MIN_SESSIONS = 15

#: The bucket for a symbol no source names. Every unclassified name shares it.
UNCLASSIFIED = "UNCLASSIFIED"

#: Broad index / beta instruments are their own driver: they are the market,
#: not a theme, and lumping them into UNCLASSIFIED would make the anchor book's
#: SPY+QQQ+IWM core look like one undeclared cluster (which, for the purpose of
#: a cap, it is -- but it is a NAMED one, and a refusal must be able to say why).
INDEX_DRIVER = "index_beta"
_INDEX_SYMBOLS = frozenset({
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "MDY", "RSP", "SPXL", "TQQQ",
    "SSO", "UPRO", "SH", "PSQ", "SDS", "SQQQ", "VXX", "UVXY",
})

_THEMES_PATH = Path(__file__).resolve().parent.parent / "docs" / "seed" / "universe" / "THEMES_2026-08-28.json"


@lru_cache(maxsize=1)
def declared_map() -> dict[str, str]:
    """symbol -> declared theme, from the human-stated themes seed.

    Read once. A missing or malformed seed is a STATE, not a crash: every
    symbol then falls to `UNCLASSIFIED`, which shares one bucket, which is the
    safe direction. It is logged at WARNING because a silently empty taxonomy
    would turn this gate into a single-bucket gate without anyone noticing --
    the house failure mode (`silent-fragility-audit`).
    """
    out: dict[str, str] = {}
    try:
        blob = json.loads(_THEMES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("declared theme map unreadable at %s (%s); every symbol falls to "
                       "%s, which is ONE shared bucket -- the driver cap will bind hard",
                       _THEMES_PATH, exc, UNCLASSIFIED)
        return out
    for theme, body in (blob.get("themes") or {}).items():
        for sym in (body.get("symbols") or []):
            s = str(sym or "").strip().upper()
            if s:
                out.setdefault(s, theme)
    if not out:
        logger.warning("declared theme map at %s parsed to ZERO symbols; the driver cap "
                       "will treat every name as %s", _THEMES_PATH, UNCLASSIFIED)
    return out


#: The prefix for a driver taken from the sealed book's own sector field, so a
#: refusal can always say WHICH source named the driver it is refusing on.
SECTOR_PREFIX = "sector:"


@lru_cache(maxsize=8)
def sealed_sector_map(day: str) -> dict[str, str]:
    """symbol -> sector, as DECLARED by the sealed prediction book for `day`.

    WHY THIS EXISTS (2026-09-08). `declared_map()` reads a HUMAN-STATED theme
    seed written on 2026-08-28 and holding 70 symbols -- uranium, quantum,
    fuel-cell, solar. The tracker books have since moved to a screened universe
    of ~774 names that shares almost nothing with it: on the 2026-09-08 seal,
    10 of hack3's 10 names and 14 of hack6's 15 were `UNCLASSIFIED`.

    Every UNCLASSIFIED name shares ONE bucket, deliberately and correctly -- not
    knowing whether four names are independent is not evidence that they are.
    But the consequence was that the 40%-of-gross driver cap bound after roughly
    four names on EVERY tracker book, so a measured dry pass submitted 4 of 10
    and refused 6 with `DRIVER: ... 41% of equity on the single driver
    'UNCLASSIFIED'`. That is a guard binding on a DATA GAP rather than on risk,
    and a guard whose input is missing must derive it or refuse -- not quietly
    behave as though the missing value were the worst case for ever.

    The sector IS declared, and by a PIT artefact: `prediction_book` writes a
    `sector` on every holding and the book's own constraints already enforce
    `max_names_per_sector` (3) and `max_sector_share` (0.30). So this is a third
    DECLARED source, not a measurement, and it obeys this module's rule that
    "declared is the floor, and measurement may only MERGE": correlation can
    still collapse two sectors into one driver, and nothing here ever SPLITS.

    A missing or malformed seal is a STATE, not a crash: the map is empty and
    every symbol falls through to UNCLASSIFIED exactly as before.
    """
    path = Path(__file__).resolve().parent.parent / "state" / "predictions" / f"{day}.json"
    import os
    root = os.getenv("AAT_LEDGER_DIR")
    if root:
        path = Path(root) / "predictions" / f"{day}.json"
    out: dict[str, str] = {}
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("no readable sealed book at %s (%s); sector drivers unavailable and "
                       "unnamed symbols stay %s", path, exc, UNCLASSIFIED)
        return out
    for body in (blob.get("portfolios") or {}).values():
        for h in (body.get("holdings") or []):
            sym = str(h.get("symbol") or "").strip().upper()
            sec = str(h.get("sector") or "").strip()
            if sym and sec:
                out.setdefault(sym, SECTOR_PREFIX + sec.lower().replace(" ", "_"))
    if not out:
        logger.warning("sealed book %s named ZERO sectors; the driver cap will treat its "
                       "names as %s", path, UNCLASSIFIED)
    return out


def declared_driver(symbol: str, *, day: str | None = None) -> str:
    """The driver a symbol is DECLARED to belong to, most specific source first.

    index beta -> human theme seed -> the sealed book's own sector -> UNCLASSIFIED.
    """
    s = str(symbol or "").strip().upper()
    if not s:
        return UNCLASSIFIED
    if s in _INDEX_SYMBOLS:
        return INDEX_DRIVER
    hit = declared_map().get(s)
    if hit:
        return hit
    if day is None:
        try:
            from alpha import exits as _exits
            day = _exits.session_day()
        except Exception:                                               # noqa: BLE001
            return UNCLASSIFIED
    return sealed_sector_map(day).get(s, UNCLASSIFIED)


def _corr(a: list[float], b: list[float]) -> float | None:
    n = min(len(a), len(b))
    if n < MIN_SESSIONS:
        return None
    a, b = a[-n:], b[-n:]
    ma, mb = st.mean(a), st.mean(b)
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    if da <= 0 or db <= 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (da * db)


class _Union:
    def __init__(self, keys):
        self.parent = {k: k for k in keys}

    def find(self, k):
        while self.parent[k] != k:
            self.parent[k] = self.parent[self.parent[k]]
            k = self.parent[k]
        return k

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        # Deterministic: the lexically smaller root wins, so the merged driver's
        # NAME does not depend on dict ordering and a receipt is reproducible.
        lo, hi = (ra, rb) if ra <= rb else (rb, ra)
        self.parent[hi] = lo
        return True


def resolve(symbols, returns: dict[str, list[float]] | None = None,
            *, rho_min: float = MERGE_RHO) -> tuple[dict[str, str], str]:
    """(symbol -> driver, note). Declared taxonomy, merged where measured.

    `returns` are per-symbol log returns; pass None (or an empty dict) to get
    the declared answer alone. Merging is by MEDIAN cross-driver pairwise
    correlation, not by the maximum: one coincidentally-correlated pair should
    not collapse two themes, and the median of an all-moving-together cluster
    is high anyway. A pair whose overlap is under `MIN_SESSIONS` contributes
    nothing rather than a zero -- a zero would argue AGAINST merging on no
    evidence, which is the flattering direction.

    Returns the note so the refusal can say which taxonomy refused it. A gate
    that cannot say whether it measured anything is the gate this project keeps
    having to rewrite.
    """
    syms = sorted({str(s or "").strip().upper() for s in symbols if str(s or "").strip()})
    base = {s: declared_driver(s) for s in syms}
    groups = sorted(set(base.values()))
    if not returns or len(groups) < 2:
        return base, ("declared only" if not returns else
                      f"declared only ({len(groups)} driver(s); nothing to merge)")

    # Median pairwise correlation BETWEEN each pair of declared drivers.
    members: dict[str, list[str]] = {}
    for s, g in base.items():
        members.setdefault(g, []).append(s)
    u = _Union(groups)
    merged: list[str] = []
    pairs_seen = 0
    for i in range(len(groups)):
        for j in range(i + 1, len(groups)):
            ga, gb = groups[i], groups[j]
            rs = [r for a in members[ga] for b in members[gb]
                  if (r := _corr(returns.get(a) or [], returns.get(b) or [])) is not None]
            if not rs:
                continue
            pairs_seen += 1
            rho = st.median(rs)
            if rho >= rho_min and u.union(ga, gb):
                merged.append(f"{ga}+{gb} rho {rho:+.2f}")
    out = {s: u.find(g) for s, g in base.items()}
    if not pairs_seen:
        note = (f"declared only: no driver pair had {MIN_SESSIONS}+ overlapping sessions, "
                "so nothing could be merged (this is not evidence of independence)")
    elif merged:
        note = f"declared + merged at rho>={rho_min:.2f}: " + "; ".join(merged)
    else:
        note = f"declared; {pairs_seen} driver pair(s) measured, none merged at rho>={rho_min:.2f}"
    return out, note


def cap_fraction(gross_cap: float) -> float:
    """The per-driver notional cap, as a fraction of equity."""
    return DRIVER_SHARE_OF_GROSS * float(gross_cap)


def notional_by_driver(by_symbol: dict[str, float], drivers: dict[str, str] | None = None
                       ) -> dict[str, float]:
    """Σ|notional| per driver from a per-symbol notional map.

    Symbols absent from `drivers` are resolved on the spot from the declared
    map, so a position the pass never considered still counts against its
    driver -- the book is what it is, not what this pass looked at.
    """
    drivers = drivers or {}
    out: dict[str, float] = {}
    for sym, usd in by_symbol.items():
        s = str(sym or "").strip().upper()
        d = drivers.get(s) or declared_driver(s)
        out[d] = out.get(d, 0.0) + abs(float(usd or 0.0))
    return out


def returns_from_bars(bars: dict[str, list[dict]]) -> dict[str, list[float]]:
    """Per-symbol log returns from an Alpaca `stock_bars_multi` payload."""
    out: dict[str, list[float]] = {}
    for sym, rows in (bars or {}).items():
        closes = [float(r["c"]) for r in (rows or []) if r.get("c")]
        if len(closes) > MIN_SESSIONS:
            out[str(sym).upper()] = [math.log(closes[i] / closes[i - 1])
                                     for i in range(1, len(closes))
                                     if closes[i] > 0 and closes[i - 1] > 0]
    return out
