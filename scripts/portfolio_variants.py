"""PORTFOLIO VARIANTS -- the eight books Murat named, built as SHADOW books.

    python -m scripts.portfolio_variants                 # today's tracker day
    python -m scripts.portfolio_variants --day 2026-09-02
    python -m scripts.portfolio_variants --json          # receipt to stdout

WHAT THIS IS, AND WHAT IT IS EMPHATICALLY NOT
=============================================
Eight alternative constructions over the SAME day, the SAME universe and the
SAME v2 band-prior numbers as the sealed book, written to
`state/variant_books/<day>/`. They are FILES. Nothing in this repo reads
`state/variant_books/`; no brain, no runner, no scheduler. This script imports
no broker module, submits nothing, and cannot -- `tests_smoke_leverage_lab.py`
pins that property the way `tests_smoke_ownership` pins the watcher's.

WHY A TOURNAMENT OF CONSTRUCTIONS RATHER THAN A NEW SIGNAL
==========================================================
The bottleneck rule says a new MECHANISM arrives as its own book. These are not
new mechanisms: every one of them scores names with `alpha/murat_rule.py`'s
`evaluate` + `score` under BAND_PRIOR v2, exactly as the seal does. What varies
is PORTFOLIO TREATMENT -- k, per-name notional, sector cap, which admissible
band, which column decides the order. That is the same axis the ten arena books
already differ on, and the honest thing to say about it up front is that a
tournament of constructions over one alpha source cannot manufacture alpha; it
can only show how much of the book's outcome was the construction.

THE CONTROL IS THE POINT
========================
`BALANCED` is hack3's live Personality, unmodified, and it MUST reproduce the
day's sealed `portfolios["hack3"]` holding for holding. It does (2026-09-02:
IVA TNXP IMRX LENZ ASPI DAKT INVA CRUS VST NPKI). If it ever stops matching,
this file is measuring something other than what trades, and the run REFUSES
rather than printing seven variants beside a control that is not one.

THE HOUSE RULES ARE CALLED, NOT COPIED
======================================
Eligibility is `alpha.tracker._eligibility_checks` -- the single expression of
past-winner exclusion, the downside cap, the catalyst clause, the coverage
band, the liquidity floor, the long-book coherence floor and the rankability
test. Ranking is `alpha.tracker.rank_value` for the four house columns; the two
columns Murat's variants need that the house does not have (`exp_return` and
`low_vol`) are computed here and SAY SO on the book. Re-implementing the
filters would let this file's idea of admissible drift away from the seal's,
which is the entire failure mode `_eligibility_checks` was factored out to end.

ONE MEASURED CAVEAT ON EVERY BOOK, INCLUDING THE CONTROL
========================================================
Alpaca PAPER fills ignore NBBO size. So every book here carries a CAPACITY
block: position dollars as a fraction of the name's own median daily dollar
volume, at the declared equity, flagged above 2%. A 2% participation rate is
not a fill, it is a day of work, and a paper engine will report it as a fill at
the touch. Read the capacity flags before reading the returns.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alpha import murat_rule as MR                      # noqa: E402
from alpha import tracker as T                          # noqa: E402

OUT = Path(os.getenv("AAT_VARIANT_DIR") or (ROOT / "state" / "variant_books"))

#: Declared equity for every dollar figure printed here. The books are shadow
#: books, so there is no account to read; the genesis file is the honest source
#: for what a real one started with and `--equity` overrides it.
DEFAULT_EQUITY = 100_000.0

#: Above this fraction of a name's median daily dollar volume, a paper fill is
#: fiction. 2% is not a law; it is the level at which the difference between a
#: paper fill and a real one stops being a rounding error.
CAPACITY_FLAG = 0.02

#: The band the v2 prior measured at +16.55%/yr (t 2.20, n=5,888 name-months) --
#: the "lost winners" cell that the +400% toxicity bar throws away with the
#: toxic one. AGGRESSIVE is the book that holds ONLY this cell.
AGGRESSIVE_BAND = (3.0, 5.0)

#: `market_cap_usd` IS NOT ALWAYS IN USD (measured here, 2026-09-02).
#:
#: Sorting the 3,056-name tracker by that column returns SKHY, TLK, EC, CIB,
#: TSM, KB, SHG, MUFG, TM, YPF -- an ADR list, not a leadership list. SKHY's
#: value is 1,223,036,300 BILLION, which is SK Hynix's market cap in KRW; TLK's
#: is in IDR, MUFG's in JPY, YPF's in ARS. The column name asserts a currency
#: the vendor did not deliver, and a ranking that mixes KRW with USD is not a
#: ranking of size.
#:
#: A guard DERIVES its input or REFUSES, and here it takes TWO readings because
#: one is not enough. Both are computed from columns the tracker carries.
#:
#:  1. IMPLIED SHARE COUNT = market_cap / close. Currency-consistent, and the
#:     largest genuine count in this 3,056-name file is NVDA at 2.37e10. 3e10
#:     is that number with 1.27x headroom. Catches the 30x+ currencies (KRW,
#:     JPY, IDR, COP, ARS): 51 rows on 2026-09-02.
#:  2. DAYS TO TRADE THE COMPANY = market_cap / median_dollar_volume, both of
#:     which would be in the same currency if the cap were honest. Every
#:     verified US mega-cap in this file sits between 104 (TSLA) and 669 (GOOG)
#:     days; the survivors of check 1 that are still mis-denominated sit at
#:     2,185 (PBR, BRL) to 145,400 (CHT, TWD). 1,000 is GOOG's reading with
#:     1.5x headroom.
#:
#: Check 2 is a DETECTOR, not a proof, and its known cost is stated rather than
#: hidden: VALE reads 971 days and is kept though its cap is in BRL, and any
#: genuinely US-denominated but very thinly traded large cap would be refused.
#: Both diagnostics are printed on every SP_TOPN holding so a reader can audit
#: the ten names rather than trust the two thresholds.
IMPLIED_SHARES_MAX = 3e10
DAYS_TO_TRADE_MAX = 1000.0

#: Clause (b)'s threshold, reused as a TILT rather than a gate.
#: TRIAL-AGREE-CELL-TILT-1, pre-registered in the Aegis module (f3762ab) and in
#: NO seal. This book is the shadow arm of that trial and nothing else.
ANALYST_TILT_MIN = MR.RATING_MIN


# --------------------------------------------------------------------------
# The two rankings the house does not have
# --------------------------------------------------------------------------

def _rank(row: dict, how: str) -> float:
    """`alpha.tracker.rank_value` for the house columns; two more here.

    Missing inputs return -inf, never 0.0 -- the house convention, and the
    reason for it: a zero would let an UNMEASURED name outrank a measured one
    whose number is genuinely negative, which is how an absence gets promoted
    into a position.
    """
    neg = float("-inf")
    if how == "exp_return":
        # UNDER v2 THIS COLUMN IS NEARLY CONSTANT AND THAT IS NOT A BUG. The
        # band prior publishes one exp_return per ratio band, so a book that
        # ranks on it is really choosing a BAND and then breaking ties. The
        # tie-break is declared (`risk_adjusted_ratio`), not alphabetical:
        # an arbitrary tie-break wearing a sort is exactly how hack6 came out
        # as twelve biotechs on 2026-08-30.
        er = row.get("exp_return")
        return neg if er is None else float(er)
    if how == "low_vol":
        # SAFEST ranks on the name's own realised vol, lowest first. No
        # separate `max_downside` cap is declared for that book: downside_5pct
        # is a monotone transform of this very number, so a cap on top of the
        # ranking would be the same rule applied twice and would read as two
        # pieces of evidence.
        v = row.get("realised_vol_20d")
        return neg if v is None else -float(v)
    if how == "market_cap":
        mc, _why = usd_market_cap(row)
        return neg if mc is None else float(mc)
    return T.rank_value(row, how)


def usd_market_cap(row: dict) -> tuple[float | None, str]:
    """(market cap in USD, or None and the reason it could not be read).

    See IMPLIED_SHARES_MAX. This refuses; it does not convert. Converting would
    need an FX rate this repo does not carry, and guessing one to keep a row in
    a leadership ranking is exactly the shape of error the column already made.
    """
    mc = row.get("market_cap_usd")
    close = row.get("close")
    dv = row.get("median_dollar_volume")
    if mc is None:
        return None, "market cap unreadable"
    if not close:
        return None, "close unreadable, so the currency check cannot run"
    shares = float(mc) / float(close)
    if shares > IMPLIED_SHARES_MAX:
        return None, (f"market cap REFUSED: {float(mc):.3g} / close {float(close):g} implies "
                      f"{shares:.3g} shares, above the {IMPLIED_SHARES_MAX:.0g} bound -- the "
                      "vendor value is in a local currency, not USD")
    if not dv:
        return None, "median dollar volume unreadable, so the turnover check cannot run"
    days = float(mc) / float(dv)
    if days > DAYS_TO_TRADE_MAX:
        return None, (f"market cap REFUSED: {days:,.0f} days of its own median dollar volume "
                      f"to trade the company, above the {DAYS_TO_TRADE_MAX:,.0f} bound -- the "
                      "cap and the dollar volume are not in the same currency")
    return float(mc), "ok"


def market_cap_diagnostics(row: dict) -> dict:
    """Both currency readings for one row, so the ten names can be audited."""
    mc, why = usd_market_cap(row)
    close, dv = row.get("close"), row.get("median_dollar_volume")
    raw = row.get("market_cap_usd")
    return {
        "market_cap_reported": raw,
        "implied_shares": (round(float(raw) / float(close), 1) if raw and close else None),
        "days_to_trade_at_median_dollar_volume": (round(float(raw) / float(dv), 1)
                                                  if raw and dv else None),
        "accepted_as_usd": mc is not None,
        "verdict": why,
    }


def _tie_break(row: dict, how: str) -> float:
    """Declared secondary sort for the columns that tie. -inf sorts last."""
    if how in ("exp_return", "market_cap"):
        return T.rank_value(row, "risk_adjusted_ratio")
    return 0.0


# --------------------------------------------------------------------------
# The variant contract
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Variant:
    name: str
    intent: str                       # Murat's words for what this book is
    k: int
    notional: float                   # per name, fraction of equity
    rank: str
    #: A Personality carrying every constraint the house already expresses, so
    #: `_eligibility_checks` is the one place those rules live.
    personality: Any
    #: Extra admission applied to the POOL before the house checks run. Used for
    #: the two variants whose admissible set is not a Personality field.
    pool_filter: Callable[[dict], bool] | None = None
    pool_filter_note: str = ""
    #: SP_TOPN is a SENSOR, not a capital candidate: it holds the ten largest
    #: names whether or not the long-book coherence floor likes them, because
    #: filtering the sensor changes the thing being sensed.
    apply_house_eligibility: bool = True
    max_sector_share: float | None = None
    shadow_only_note: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def target_gross(self) -> float:
        return round(self.k * self.notional, 4)


def _p(book: str, name: str, **kw) -> Any:
    """A Personality with clause (f) DECLARED -- the dataclass refuses a default."""
    kw.setdefault("exclude_past_winners", False)
    return T.Personality(book, name, **kw)


def variants() -> tuple[Variant, ...]:
    """The eight books, frozen here so a diff shows a change of construction."""
    hack3 = next(p for p in T.PERSONALITIES if p.book == "hack3")
    return (
        Variant(
            name="BALANCED",
            intent="THE CONTROL. hack3's live personality, unmodified. Must equal "
                   "the day's sealed portfolios['hack3'] or this run refuses.",
            k=hack3.k, notional=hack3.max_notional, rank=hack3.rank,
            personality=hack3, max_sector_share=hack3.max_sector_share,
            tags=("control",)),
        Variant(
            name="ROI_MAX",
            intent="Top-k by expected return, concentrated. k=5.",
            k=5, notional=0.10, rank="exp_return",
            personality=_p("ROI_MAX", "profit_max", k=5, max_notional=0.10,
                           rank="risk_adjusted_ratio", min_dollar_volume=1_000_000.0),
            max_sector_share=None,
            tags=("concentrated",)),
        Variant(
            name="SECTOR_BALANCED",
            intent="At most two names per sector, k=12. hack3's rules otherwise.",
            k=12, notional=0.08, rank="risk_adjusted_ratio",
            personality=_p("SECTOR_BALANCED", "balanced", k=12, max_notional=0.08,
                           rank="risk_adjusted_ratio", exclude_past_winners=True,
                           min_dollar_volume=1_000_000.0, max_sector_share=0.16,
                           max_downside=0.30),
            max_sector_share=0.16,
            tags=("diversified",)),
        Variant(
            name="AGGRESSIVE",
            intent="ONLY the 3..5 target-ratio band -- the +16.55%/yr 'lost winners' "
                   "cell -- ranked by hack4's upside x consensus. k=8.",
            k=8, notional=0.10, rank="upside_x_consensus",
            personality=_p("AGGRESSIVE", "profit_max", k=8, max_notional=0.10,
                           rank="upside_x_consensus", min_dollar_volume=1_000_000.0,
                           max_sector_share=0.30),
            pool_filter=lambda r: _in_band(r, *AGGRESSIVE_BAND),
            pool_filter_note=(f"target_ratio in [{AGGRESSIVE_BAND[0]:g}, {AGGRESSIVE_BAND[1]:g}) "
                              "-- EXP-RETURN-XS-1's +16.55%/yr cell (t 2.20, n=5,888 "
                              "name-months). Every other band is excluded, including the "
                              "+2.41%/yr cell most of the market sits in."),
            max_sector_share=0.30,
            tags=("band_3_5",)),
        Variant(
            name="SAFEST",
            intent="Lowest realised vol among the positive-expected admissible names, "
                   "k=15, gross 60%.",
            k=15, notional=0.04, rank="low_vol",
            personality=_p("SAFEST", "preservation", k=15, max_notional=0.04,
                           rank="risk_adjusted_ratio", min_dollar_volume=5_000_000.0,
                           max_sector_share=0.12),
            max_sector_share=0.12,
            tags=("low_gross",)),
        Variant(
            name="CAPPED",
            intent="BALANCED with a 25% sector cap and an 8% name cap. k=10.",
            k=10, notional=0.08, rank="risk_adjusted_ratio",
            personality=_p("CAPPED", "balanced", k=10, max_notional=0.08,
                           rank="risk_adjusted_ratio", exclude_past_winners=True,
                           min_dollar_volume=1_000_000.0, max_sector_share=0.25,
                           max_downside=0.30),
            max_sector_share=0.25,
            tags=("capped",)),
        Variant(
            name="ANALYST_TILT",
            intent="Admissible AND consensus rating >= 4.1. The pre-registered "
                   "TRIAL-AGREE-CELL-TILT-1 tilt, as a SHADOW arm only.",
            k=10, notional=0.083, rank="risk_adjusted_ratio",
            personality=_p("ANALYST_TILT", "balanced", k=10, max_notional=0.083,
                           rank="risk_adjusted_ratio", exclude_past_winners=True,
                           min_dollar_volume=1_000_000.0, max_sector_share=0.30,
                           max_downside=0.30),
            pool_filter=lambda r: (r.get("consensus") is not None
                                   and float(r["consensus"]) >= ANALYST_TILT_MIN),
            pool_filter_note=(f"consensus >= {ANALYST_TILT_MIN} (clause (b) as a TILT, not a "
                              "gate). TRIAL-AGREE-CELL-TILT-1 is pre-registered and is in NO "
                              "seal; this book exists to accrue its forward evidence."),
            max_sector_share=0.30,
            shadow_only_note=("TRIAL-AGREE-CELL-TILT-1 SHADOW ARM. Pre-registered, not sealed, "
                              "not routed to any account. Grading it is the whole purpose; "
                              "trading it before the trial's earliest decision date would "
                              "spend the pre-registration."),
            tags=("shadow", "preregistered")),
        Variant(
            name="SP_TOPN",
            intent="The ten largest names in the tracker universe by market cap. A "
                   "leadership-regime SENSOR, never a rule.",
            k=10, notional=0.10, rank="market_cap",
            personality=_p("SP_TOPN", "sensor", k=10, max_notional=0.10, rank="upside"),
            apply_house_eligibility=False,
            max_sector_share=None,
            shadow_only_note=(
                "REGIME-CONDITIONAL SENSOR, NOT A CAPITAL CANDIDATE. Receipt "
                "topn_concentration.json (aegis-finance, 1993-2024, 383 months): the "
                "verdict is MIXED on the full sample and REGIME-CONDITIONAL in every era "
                "-- TOP1 loses even over 1993-2024 and 2000-2012 reverses everything. It "
                "also runs WITHOUT the long-book coherence floor and without the "
                "liquidity floor, deliberately: filtering a sensor changes what it "
                "senses. Read it as 'what is leadership doing', never as a book."),
            tags=("sensor", "regime_conditional")),
    )


def _in_band(row: dict, lo: float, hi: float) -> bool:
    up = row.get("upside")
    if up is None:
        return False
    ratio = 1.0 + float(up)
    return lo <= ratio < hi


# --------------------------------------------------------------------------
# Scoring the day, exactly as the seal does
# --------------------------------------------------------------------------

def scored_candidates(day: str | None = None) -> tuple[list[dict], dict, str]:
    """(tracker candidate rows carrying v2 numbers, provenance, day).

    `scripts.prediction_book.tracker_rows` reshapes the tracker file into the
    rows the RULE reads and returns the tracker rows the PERSONALITIES read
    alongside; `alpha.murat_rule.evaluate` + `score` put the v2 band-prior
    numbers on both. This is the seal's own path, called rather than copied --
    and it reproduces 2026-09-02's hack3 book exactly, which is checked below.
    """
    from scripts import prediction_book as pb

    rows, prov, cands = pb.tracker_rows(day)
    prior = pb.rule_prior()
    by_symbol = {r["symbol"]: r for r in rows}
    for c in cands:
        r = by_symbol.get(c["symbol"])
        if r is None:
            continue
        verdict = MR.evaluate(r)
        s = MR.score(r, verdict, prior)
        for k in ("exp_return", "downside_5pct", "confidence", "p_up_21d",
                  "upside_band", "exp_return_basis"):
            c[k] = s.get(k)
        c["claims"] = verdict["fires"]
        c["rule_variant"] = verdict["rule_variant"]
        c["numbers_source"] = "rule"
    return cands, prov, prov["tracker_day"]


def all_tracker_rows(day: str) -> list[dict]:
    """Every tracker row for the day, candidate or not -- SP_TOPN's universe."""
    from scripts import tracker as tracker_cli
    return T.build_rows(tracker_cli.load_day(day))


# --------------------------------------------------------------------------
# Building one variant
# --------------------------------------------------------------------------

def build_variant(pool: list[dict], v: Variant) -> dict:
    """Select and weight one variant book. House filters, declared ranking.

    Every name excluded is COUNTED by reason, first-fired, exactly as
    `alpha.tracker.build_portfolio` counts them -- a book that reports only
    what it holds cannot be debugged.
    """
    excluded: dict[str, int] = {}
    examples: dict[str, str] = {}

    def drop(reason: str, detail: str = "") -> None:
        excluded[reason] = excluded.get(reason, 0) + 1
        if detail and reason not in examples:
            examples[reason] = detail

    considered = list(pool)
    if v.pool_filter is not None:
        kept = []
        for r in considered:
            if v.pool_filter(r):
                kept.append(r)
            else:
                drop("outside this variant's declared admissible set", v.pool_filter_note)
        considered = kept

    if v.apply_house_eligibility:
        checks = T._eligibility_checks(v.personality)
    else:
        checks = []

    eligible: list[dict] = []
    for r in considered:
        failures = [f for f in (c(r) for c in checks) if f is not None]
        if failures:
            reason, detail = failures[0]
            drop(reason, detail)
            continue
        if _rank(r, v.rank) == float("-inf"):
            if v.rank == "market_cap":
                _mc, why = usd_market_cap(r)
                drop("market cap unreadable or not denominated in USD",
                     f"{r['symbol']}: {why}")
            else:
                drop(f"no {v.rank} value", r["symbol"])
            continue
        eligible.append(r)

    distinct = len({round(_rank(r, v.rank), 9) for r in eligible})
    eligible.sort(key=lambda r: (-_rank(r, v.rank), -_tie_break(r, v.rank), r["symbol"]))

    picked: list[dict] = []
    sector_notional: dict[str, float] = {}
    seen_caps: set[float] = set()
    for r in eligible:
        if len(picked) >= v.k:
            break
        if v.rank == "market_cap":
            # DUAL SHARE CLASSES ARE ONE COMPANY. GOOG and GOOGL carry the same
            # market cap, and a top-10 that spends two of its ten slots on one
            # issuer is a nine-name book pretending to be ten -- the same error
            # as counting tickers instead of bets. The receipt this arm is
            # labelled against aggregates by permco; identical reported cap is
            # the derivable stand-in for that here.
            cap = float(r.get("market_cap_usd") or 0.0)
            if cap in seen_caps:
                drop("dual share class of a company already held",
                     f"{r['symbol']}: same reported market cap as an earlier pick")
                continue
            seen_caps.add(cap)
        sec = r.get("sector") or "_UNKNOWN"
        if v.max_sector_share is not None:
            if sector_notional.get(sec, 0.0) + v.notional > v.max_sector_share + 1e-9:
                drop("sector at its cap", f"{sec} at {v.max_sector_share:.0%}")
                continue
        sector_notional[sec] = sector_notional.get(sec, 0.0) + v.notional
        picked.append({
            "symbol": r["symbol"],
            "notional": v.notional,
            "sector": sec,
            "rank_value": round(_rank(r, v.rank), 6),
            "reason": _reason(r, v),
            "exp_return": r.get("exp_return"),
            "downside_5pct": r.get("downside_5pct"),
            "confidence": r.get("confidence"),
            "upside": r.get("upside"),
            "consensus": r.get("consensus"),
            "upside_band": r.get("upside_band"),
            "coverage_bucket": r.get("coverage_bucket"),
            "realised_vol_20d": r.get("realised_vol_20d"),
            "median_dollar_volume": r.get("median_dollar_volume"),
            "market_cap_usd": r.get("market_cap_usd"),
            "past_winner": r.get("past_winner"),
            "claims": r.get("claims"),
            "numbers_source": r.get("numbers_source") or "rule",
            **({"market_cap_check": market_cap_diagnostics(r)}
               if v.rank == "market_cap" else {}),
        })

    return {
        "variant": v.name,
        "intent": v.intent,
        "ranking": v.rank,
        "ranking_is_house_column": v.rank not in ("exp_return", "low_vol", "market_cap"),
        "rank_distinct_values": distinct,
        "ranking_is_degenerate": bool(eligible and distinct < 2),
        "tie_break": ("risk_adjusted_ratio, then symbol -- DECLARED, because under v2 this "
                      "column is near-constant within a band"
                      if v.rank in ("exp_return", "market_cap") else "symbol"),
        "k_target": v.k,
        "n_selected": len(picked),
        "max_notional_each": v.notional,
        "target_gross": v.target_gross,
        "derived_gross": round(sum(h["notional"] for h in picked), 4),
        "constraints": {
            "exclude_past_winners": v.personality.exclude_past_winners,
            "requires_catalyst": v.personality.requires_catalyst,
            "min_coverage_bucket": v.personality.min_coverage_bucket,
            "max_coverage_bucket": v.personality.max_coverage_bucket,
            "min_dollar_volume": v.personality.min_dollar_volume,
            "max_sector_share": v.max_sector_share,
            "max_downside": v.personality.max_downside,
            "house_eligibility_applied": v.apply_house_eligibility,
            "pool_filter": v.pool_filter_note or None,
        },
        "holdings": picked,
        "candidate_pool": len(pool),
        "after_pool_filter": len(considered),
        "eligible": len(eligible),
        "excluded_by_reason": dict(sorted(excluded.items(), key=lambda kv: -kv[1])),
        "excluded_examples": examples,
        "sector_notional": {k: round(x, 4) for k, x in sorted(sector_notional.items())},
        "shadow_only_note": v.shadow_only_note or None,
        "tags": list(v.tags),
    }


def _reason(row: dict, v: Variant) -> str:
    """One line per holding saying why THIS book holds THIS name."""
    bits = [f"{v.rank}={_rank(row, v.rank):+.6g}"]
    if row.get("upside") is not None:
        bits.append(f"target/close={1.0 + float(row['upside']):.2f}")
    if row.get("upside_band"):
        bits.append(f"band {row['upside_band']}")
    if row.get("consensus") is not None:
        bits.append(f"consensus {row['consensus']:.2f}")
    if row.get("downside_5pct") is not None:
        bits.append(f"modelled 5% downside {row['downside_5pct']:+.1%}")
    if row.get("claims") is not None:
        bits.append("rule CLAIMS" if row["claims"] else "rule declines (held on construction)")
    return "; ".join(bits)


# --------------------------------------------------------------------------
# Capacity -- the paper-fill caveat, per holding
# --------------------------------------------------------------------------

def capacity(book: dict, *, equity: float, gross_multiplier: float = 1.0) -> dict:
    """Position dollars as a fraction of each name's median daily dollar volume.

    ALPACA PAPER FILLS IGNORE NBBO SIZE. A paper engine fills 300% of a
    micro-cap's daily volume at the touch and reports it as a fill; a real one
    would move the print or not fill at all. So any levered result computed
    from paper fills is OPTIMISTIC by an amount this block bounds and does not
    correct, and the flag list is the part of the receipt to read first.
    """
    rows, flagged = [], []
    for h in book["holdings"]:
        dv = h.get("median_dollar_volume")
        dollars = equity * float(h["notional"]) * gross_multiplier
        frac = (dollars / float(dv)) if dv else None
        row = {"symbol": h["symbol"], "position_usd": round(dollars, 2),
               "median_dollar_volume": dv,
               "pct_of_median_dollar_volume": (round(frac, 6) if frac is not None else None),
               "flag": bool(frac is not None and frac > CAPACITY_FLAG),
               "unreadable": dv is None}
        rows.append(row)
        if row["flag"] or row["unreadable"]:
            flagged.append(h["symbol"])
    worst = max((r["pct_of_median_dollar_volume"] or 0.0) for r in rows) if rows else 0.0
    return {
        "equity_usd": equity,
        "gross_multiplier": gross_multiplier,
        "flag_threshold": CAPACITY_FLAG,
        "n_flagged": len(flagged),
        "flagged": flagged,
        "worst_pct_of_median_dollar_volume": round(worst, 6),
        "per_holding": rows,
        "caveat": ("Alpaca PAPER fills ignore NBBO size, so any result computed from paper "
                   f"fills is optimistic. A name above {CAPACITY_FLAG:.0%} of its own median "
                   "daily dollar volume is a day of work, not a fill. An unreadable dollar "
                   "volume is FLAGGED, never passed through as zero participation."),
    }


# --------------------------------------------------------------------------
# Worst case -- printed before any average, every time
# --------------------------------------------------------------------------

def worst_case_line(book: dict, *, stop_fraction: float = 0.08,
                    gross_cap: float = 1.0, gross_multiplier: float = 1.0) -> dict:
    """`n x notional x stop`, and the all-gap case at the book's OWN downside.

    House rule earned on 2026-08-28 and re-earned on 08-29: twelve names at 25%
    is 300% gross, and a 3% stop on 300% gross is -9%; widening the stop on
    uncapped gross made the same book -24%. So the bound is computed from the
    binding constraint and names which one binds, and the STOP case is printed
    beside the GAP case because a stop does not hold through a gap.
    """
    n = book["n_selected"]
    notional = book["max_notional_each"]
    wc = T.worst_case(n=n, notional_each=notional * gross_multiplier,
                      stop_fraction=stop_fraction, gross_cap=gross_cap * gross_multiplier)
    downs = [abs(float(h["downside_5pct"])) for h in book["holdings"]
             if h.get("downside_5pct") is not None]
    mean_down = (sum(downs) / len(downs)) if downs else None
    gap_loss = (-wc["gross"] * mean_down) if mean_down is not None else None
    return {
        **wc,
        "gross_multiplier": gross_multiplier,
        "all_gap_case": {
            "mean_modelled_downside_5pct": (round(mean_down, 5) if mean_down is not None else None),
            "n_holdings_with_a_downside": len(downs),
            "loss_fraction": (round(gap_loss, 5) if gap_loss is not None else None),
            "loss_pct": (f"{gap_loss:.2%}" if gap_loss is not None else "UNDETERMINABLE"),
            "basis": ("gross x the mean of the holdings' own modelled downside_5pct (the 5% "
                      "normal quantile at each name's realised vol). A stop does not survive "
                      "a gap, so this is the number the stop case does NOT bound."),
        },
    }


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

def _sealed_book(day: str) -> dict | None:
    p = ROOT / "state" / "predictions" / f"{day}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


def build_all(day: str | None = None, *, equity: float = DEFAULT_EQUITY) -> dict:
    cands, prov, day = scored_candidates(day)
    every_row = all_tracker_rows(day)
    sealed = _sealed_book(day)

    books: dict[str, dict] = {}
    for v in variants():
        pool = every_row if v.name == "SP_TOPN" else cands
        b = build_variant(pool, v)
        b["capacity"] = capacity(b, equity=equity)
        b["worst_case"] = worst_case_line(b)
        b["day"] = day
        b["shadow"] = True
        b["authority"] = (
            "SHADOW BOOK. This file is read by `scripts/variant_grade.py` and by nothing "
            "else. No brain, no runner and no scheduler in this repo opens "
            "state/variant_books/; the builder imports no broker module and can place "
            "no order. Routing any of these to an account is a separate, attended, "
            "explicitly named decision.")
        books[v.name] = b

    control = books["BALANCED"]
    control_check = _check_control(control, sealed)

    refused = [r["symbol"] for r in every_row if usd_market_cap(r)[0] is None
               and r.get("market_cap_usd") is not None]
    currency_defect = {
        "finding": ("`market_cap_usd` on the tracker row is NOT always in USD -- foreign "
                    "listings carry the local-currency cap (SKHY in KRW, TLK in IDR, MUFG "
                    "in JPY, YPF in ARS). Sorting the column returns an ADR list, not a "
                    "size list."),
        "detected_by": (f"TWO derived readings: implied share count = market_cap / close above "
                        f"{IMPLIED_SHARES_MAX:.0g} (US listings top out at NVDA's 2.4e10), and "
                        f"days-to-trade = market_cap / median_dollar_volume above "
                        f"{DAYS_TO_TRADE_MAX:,.0f} (verified US mega-caps run 104-669). The "
                        "second is a detector, not a proof: VALE at 971 days survives it."),
        "rows_refused": len(refused),
        "rows_total": len(every_row),
        "example_symbols": refused[:12],
        "handled": ("REFUSED, not converted. This script needs no FX rate to know the number "
                    "is unreadable, and it will not guess one to keep a row in a ranking. "
                    "RECORDED, not repaired: `alpha/tracker.py` is untouched by this session."),
    }

    return {
        "schema": "variant-books-1",
        "day": day,
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "equity_usd": equity,
        "licence": "PRODUCT_EXPERIMENT",
        "universe_source": prov,
        "band_prior": {"receipt": MR.BAND_PRIOR["receipt"],
                       "window": MR.BAND_PRIOR["window"],
                       "source": MR.BAND_PRIOR["source"]},
        "control_check": control_check,
        "data_defect_market_cap_currency": currency_defect,
        "books": books,
    }


def _check_control(control: dict, sealed: dict | None) -> dict:
    """BALANCED must be the sealed hack3 book. Anything else is a measurement
    of something that does not trade."""
    if sealed is None:
        return {"status": "CANNOT DETERMINE", "reason": "no sealed book on disk for this day"}
    port = (sealed.get("portfolios") or {}).get("hack3")
    if not port:
        return {"status": "CANNOT DETERMINE",
                "reason": "sealed book carries no portfolios['hack3'] block (schema-2 seal)"}
    mine = [h["symbol"] for h in control["holdings"]]
    theirs = [h["symbol"] for h in port["holdings"]]
    same_w = all(abs(float(a["notional"]) - float(b["notional"])) < 1e-9
                 for a, b in zip(control["holdings"], port["holdings"]))
    return {
        "status": "MATCH" if (mine == theirs and same_w) else "DIFFERS",
        "sealed_sha256": sealed.get("content_sha256"),
        "sealed_hack3": theirs,
        "control": mine,
        "weights_match": bool(same_w),
        "why_it_matters": ("BALANCED is hack3's live Personality called unmodified. If it "
                           "stops matching the seal, every other book here is being compared "
                           "against a control that is not the live book."),
    }


def write_all(payload: dict) -> Path:
    day = payload["day"]
    d = OUT / day
    d.mkdir(parents=True, exist_ok=True)
    for name, book in payload["books"].items():
        (d / f"{name}.json").write_text(
            json.dumps(book, indent=1, ensure_ascii=False), encoding="utf-8")
    receipt = {k: v for k, v in payload.items() if k != "books"}
    receipt["summary"] = {
        name: {"n": b["n_selected"], "gross": b["derived_gross"],
               "worst_case_pct": b["worst_case"]["worst_case_pct"],
               "all_gap_pct": b["worst_case"]["all_gap_case"]["loss_pct"],
               "capacity_flags": b["capacity"]["n_flagged"],
               "holdings": [h["symbol"] for h in b["holdings"]]}
        for name, b in payload["books"].items()}
    (d / "receipt.json").write_text(
        json.dumps(receipt, indent=1, ensure_ascii=False), encoding="utf-8")
    return d


def _print(payload: dict) -> None:
    ctl = payload["control_check"]
    print(f"\nVARIANT BOOKS  day {payload['day']}  equity ${payload['equity_usd']:,.0f}  "
          f"SHADOW ONLY (no orders, no account)")
    print(f"CONTROL vs SEALED hack3: {ctl['status']}"
          + (f"  sha {str(ctl.get('sealed_sha256'))[:10]}" if ctl.get("sealed_sha256") else ""))
    if ctl["status"] == "DIFFERS":
        print(f"  sealed  {ctl['sealed_hack3']}")
        print(f"  control {ctl['control']}")
    d = payload["data_defect_market_cap_currency"]
    print(f"DATA DEFECT (recorded, not repaired): market_cap_usd is not USD on "
          f"{d['rows_refused']}/{d['rows_total']} tracker rows -- {d['example_symbols'][:6]}")

    control_syms = {h["symbol"] for h in payload["books"]["BALANCED"]["holdings"]}
    print("\nWORST CASE FIRST (n x notional x stop, then the all-gap case at the "
          "book's own modelled downside):")
    for name, b in payload["books"].items():
        wc = b["worst_case"]
        print(f"  {name:<16} n={b['n_selected']:<3} x {b['max_notional_each']:.1%} "
              f"= gross {wc['gross']:.0%} (binding {wc['binding']}), "
              f"stop {wc['stop_fraction']:.0%} -> {wc['worst_case_pct']:>8}   "
              f"all-gap -> {wc['all_gap_case']['loss_pct']:>8}")

    print("\nBOOKS")
    for name, b in payload["books"].items():
        syms = [h["symbol"] for h in b["holdings"]]
        overlap = len(control_syms & set(syms))
        deg = "  RANKING DEGENERATE" if b["ranking_is_degenerate"] else ""
        print(f"\n  {name}  ({b['ranking']}, k {b['n_selected']}/{b['k_target']}, "
              f"gross {b['derived_gross']:.0%}, overlap with control {overlap}/{len(syms)}){deg}")
        print(f"    {b['intent']}")
        print(f"    pool {b['candidate_pool']} -> filtered {b['after_pool_filter']} -> "
              f"eligible {b['eligible']} -> selected {b['n_selected']}")
        print(f"    {' '.join(syms) if syms else '(empty)'}")
        if b["excluded_by_reason"]:
            top = list(b["excluded_by_reason"].items())[:4]
            print("    excluded: " + ", ".join(f"{k} {v}" for k, v in top))
        cap = b["capacity"]
        if cap["n_flagged"]:
            print(f"    CAPACITY FLAGS ({cap['n_flagged']}, >{cap['flag_threshold']:.0%} of "
                  f"median daily $ volume): {' '.join(cap['flagged'])}  "
                  f"worst {cap['worst_pct_of_median_dollar_volume']:.2%}")
        else:
            print(f"    capacity: no name above {cap['flag_threshold']:.0%} of its median "
                  f"daily $ volume (worst {cap['worst_pct_of_median_dollar_volume']:.2%})")
        if b["shadow_only_note"]:
            print(f"    NOTE: {b['shadow_only_note']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--day", help="tracker day (default: the newest on disk)")
    ap.add_argument("--equity", type=float, default=DEFAULT_EQUITY)
    ap.add_argument("--json", action="store_true", help="print the receipt to stdout")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args(argv)

    payload = build_all(args.day, equity=args.equity)
    if args.json:
        print(json.dumps({k: v for k, v in payload.items() if k != "universe_source"},
                         indent=1, ensure_ascii=False))
        return 0
    _print(payload)
    if not args.no_write:
        d = write_all(payload)
        print(f"\nwrote {len(payload['books'])} shadow books + receipt.json -> {d}")
    if payload["control_check"]["status"] == "DIFFERS":
        print("\nREFUSED: the control does not reproduce the sealed hack3 book. Every "
              "comparison above is against a control that is not the live book.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
