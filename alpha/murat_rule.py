"""MURAT_RULE_V1 -- the second generator, and the first one allowed to CLAIM.

WHY A SECOND GENERATOR RATHER THAN A LOOSER GATE
================================================
The sealed pre-open book looked at 151 names on 30 Aug and claimed **nothing**.
That was not bad luck and not a bug: `prediction_book.CLAIMING` is DERIVED from
whether any measured signal's 95% CI excludes zero, and on the 152-symbol panel
none does. A book whose only generator is `event_counts_v1` can therefore never
claim, however many names it reads.

The wrong fix is to widen the CI test until something passes -- that converts a
measurement into a wish. The right fix is to add a DIFFERENT generator with its
own contract, its own inputs and its own grade, and let the two sit side by side
so Friday's autopsy can compare a rule that claims against a panel that does
not. This is `CLAUDE.md`'s bottleneck rule ("a new mechanism arrives as its own
PRODUCT_EXPERIMENT, never as a weight in the composite") applied to a book
instead of to an arena.

THE RULE IS MURAT'S, STATED BEFORE ANY OF IT WAS MEASURED
=========================================================
Four clauses, frozen here before the first seal:

    (a) consensus 90-day median broker target / last close  >= 1.50
    (b) consensus analyst rating                            >= 4.1     (see below)
    (d) a dated forward catalyst within 21 SESSIONS
    (e) drawdown from the 60-session high                   <= -15%

(c) -- "sector fit" -- is deliberately absent. It is a judgement, not a reading,
and a clause nobody can evaluate identically twice does not belong in a frozen
contract.

(b) IS CONDITIONAL, AND THE ROW SAYS SO
=======================================
Finnhub's `recommendation` endpoint returns the CURRENT consensus and no
history. On a live pre-open book that is a legitimate same-day reading. On the
2025-26 panel it is not: stamping today's rating onto a 2025 date is exactly the
lookahead the panel exists to prevent, which is why T6 reported (b) as
UNAVAILABLE on 21 of 37,601 symbol-days rather than pretending to test it.

So (b) is applied ONLY when a same-day reading exists, and every row carries
`rule_variant`: `a_b_d_e` when the rating was readable, `a_d_e` when it was not.
A grade that cannot tell those apart cannot say which clause was wrong.

NO ROW ABSTAINS
===============
Murat's instruction of 2026-08-30: *"the engine just says I don't know and this
is why. It should say I am x confident this might happen with this risk and this
profit."* So every name scored by this generator returns `p_up_21d`,
`exp_return`, `downside_5pct` and `confidence` -- never a refusal. Uncertainty
is expressed as `p_up` near 0.5 at low confidence.

That is a licence to publish a number, NOT a licence to invent one. Every number
here carries a `*_basis` field naming what it was computed from:

  * `p_up_21d`      a base rate MEASURED on the panel (see `prior_from_panel`),
                    conditional on the clauses that were testable there.
  * `exp_return`    `(2*p_up - 1) x claimed_abs_move` -- so p_up = 0.5 gives
                    exactly zero, and no edge can enter through the magnitude.
  * `claimed_abs_move` the name's OWN realised vol scaled to 21 sessions, capped
                    at 15%. A scale, not a forecast.
  * `downside_5pct` the 5% normal quantile at that same vol. Also a scale.
  * `confidence`    how many clauses were readable x how much date-block
                    evidence stands behind the base rate.

THE BASE RATE IS IN-SAMPLE AND IS LABELLED IN-SAMPLE
====================================================
`prior_from_panel` measures the rule's historical hit rate on the same panel the
book ranks over. That is a BASE RATE, not an edge claim, and it is not evidence
that the rule works -- the forward grade and the calibration table are. It is
here because a published probability with a measured basis is checkable, and a
published probability without one is a guess wearing a decimal point.

NOTHING HERE SIZES OR ORDERS ANYTHING. It returns rows.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Sequence

#: (a) Consensus target must be at least this multiple of the last close.
TARGET_RATIO_MIN = 1.50

#: (b) Consensus rating on Finnhub's 1-5 scale, applied only when readable.
RATING_MIN = 4.1

#: (d) 21 SESSIONS, expressed in calendar days because `days_to_next_catalyst`
#: is a calendar difference (`features.daily_features` subtracts two dates).
#: 21 sessions x 7/5 = 29.4, so 30 is the honest conversion. Naming the unit
#: here is the whole point: reading a calendar-day feature as sessions would
#: silently tighten the clause by nine days.
CATALYST_MAX_SESSIONS = 21
CATALYST_MAX_CALENDAR_DAYS = 30

#: (e) At least this far below the 60-session high.
DRAWDOWN_MAX = -0.15

#: The claimed move is capped here however volatile the name is. A 60% realised
#: vol does not entitle the book to claim 60%.
CLAIM_ABS_MOVE_CAP = 0.15

HORIZON_SESSIONS = 21
TRADING_DAYS_PER_YEAR = 252.0

#: 5% one-sided normal quantile, for `downside_5pct`.
Z05 = 1.6449

#: Below this many date blocks behind the measured base rate, confidence is
#: scaled down rather than the number being withheld. CANON §58: n_effective
#: counts DATE BLOCKS.
CONFIDENCE_FULL_BLOCKS = 12

#: BAND-CONDITIONAL PRIOR (2026-09-01). The two-cell prior hands every name in
#: a cell the SAME expected return -- a constant is barely a forecast, and it
#: collapses exactly the structure the eleven-year panel measured: the upside
#: BAND decides the sign. Numbers verbatim from receipt UPSIDE-BAND-DECON-1
#: (aegis-finance `backend/data/optimus/tracker_backtest/
#: upside_band_decontamination.json`, IBES+CRSP 2013-2024, 143 months,
#: paired-vs-market; finance commit cb3b13a):
#:
#:   target_ratio >= 5   (+400%+ upside)   -25.91%/yr excess, t -4.43, n=54,310
#:   3 <= target_ratio<5 (+200..400%)      +20.70%/yr excess, t +2.95, n=10,419
#:   close < $2          UNINFORMATIVE     (t 0.39 in-cell) -> NO band opinion
#:
#: The monthly number (annualised/12) IS the 21-session exp_return for names
#: the band covers; every other name keeps the panel's two-cell prior. This is
#: the S30b verdict operationalised: the believable extreme target is the
#: toxic one, the band below it is where the lost winners live, and below $2
#: the history says nothing rather than "bad". These are HISTORICAL BASE
#: RATES for calibration under PRODUCT_EXPERIMENT, not a claim of alpha.
BAND_PRIOR = {
    "receipt": "UPSIDE-BAND-DECON-1",
    "source": "aegis-finance backend/data/optimus/tracker_backtest/upside_band_decontamination.json",
    "window": "2013-2024 IBES+CRSP, 143 months, paired vs market",
    "min_price": 2.0,
    "bands": (
        # (ratio_lo, ratio_hi, monthly_mean_excess, annualised, t_stat, name_months)
        (5.0, None, -0.25910 / 12.0, -0.2591, -4.431, 54310),
        (3.0, 5.0, +0.20700 / 12.0, +0.2070, +2.948, 10419),
    ),
}


def band_overlay(row: dict) -> dict | None:
    """The band prior's opinion on one row, or None where it has none.

    None is three different silences, and the caller may not care which but
    the basis string does: ratio outside every measured band; ratio unreadable;
    price under $2 where the eleven-year cell is statistically UNINFORMATIVE
    (t 0.39) -- "no opinion", never "historically bad".
    """
    tr = row.get("target_ratio")
    close = row.get("close")
    if tr is None:
        return None
    for lo, hi, monthly, ann, t, n in BAND_PRIOR["bands"]:
        if tr >= lo and (hi is None or tr < hi):
            if close is None:
                # A guard DERIVES its input or REFUSES: without the price the
                # $2 condition cannot be verified, so the band has no opinion.
                return {"band": f"ratio>={lo:g}", "applies": False,
                        "basis": ("band prior WITHHELD: close unreadable, so the sub-$2 "
                                  "condition cannot be verified -- panel prior kept")}
            if float(close) < BAND_PRIOR["min_price"]:
                return {"band": f"ratio>={lo:g}", "applies": False,
                        "basis": (f"band prior UNINFORMATIVE under ${BAND_PRIOR['min_price']:g} "
                                  "(S30b: sub-$2 cell t 0.39) -- no opinion, panel prior kept")}
            return {"band": f"ratio {lo:g}..{hi if hi is not None else 'inf'}",
                    "applies": True, "exp_return_monthly": monthly,
                    "basis": (f"{BAND_PRIOR['receipt']}: {ann:+.1%}/yr excess "
                              f"(t {t:+.2f}, n={n:,} name-months, {BAND_PRIOR['window']}) "
                              f"/ 12 for the 21-session horizon")}
    return None

#: The frozen contract. Hashed into every sealed book that uses this generator,
#: so a later edit to any threshold is visible in the diff AND in the seal.
CONTRACT: dict[str, Any] = {
    "generator": "murat_rule_v1",
    "registered": "2026-08-30",
    "licence": "PRODUCT_EXPERIMENT",
    "author": "Murat, stated 2026-08-29; frozen before the first seal",
    "direction": "up",
    "horizon_sessions": HORIZON_SESSIONS,
    "clauses": {
        "a_target_ratio": f"consensus 90d median broker target / last close >= {TARGET_RATIO_MIN}",
        "b_rating": f"consensus rating >= {RATING_MIN}, APPLIED ONLY when a same-day reading exists",
        "d_catalyst": f"a dated forward catalyst within {CATALYST_MAX_SESSIONS} sessions "
                      f"({CATALYST_MAX_CALENDAR_DAYS} calendar days)",
        "e_drawdown": f"drawdown from the 60-session high <= {DRAWDOWN_MAX:.0%}",
    },
    "clause_c_omitted": "'sector fit' is a judgement, not a reading; a clause that cannot be "
                        "evaluated identically twice does not belong in a frozen contract",
    "claim_size": f"claimed_abs_move = min(realised_vol_20d x sqrt(21/252), {CLAIM_ABS_MOVE_CAP})",
    "no_abstain": "every scored name returns p_up_21d, exp_return, downside_5pct and confidence; "
                  "uncertainty is p_up near 0.5 at low confidence, never a refusal",
    "falsifier": "a claiming row fails if the name's SPY-relative return from the next open to "
                 "the close 21 sessions later is <= 0",
    "authority": "ZERO SIZE in the book itself. Routing to a paper book is a separate, "
                 "explicitly named decision.",
}


# ------------------------------------------------------------------ the clauses


def evaluate(row: dict) -> dict:
    """Evaluate the four clauses on one feature row.

    Returns the clause verdicts, which inputs were readable, and whether the
    rule fires. A clause whose input is missing is `None` -- NOT False. The
    distinction decides `rule_variant`, and collapsing it would let an absent
    reading masquerade as a failed test.
    """
    tr = row.get("target_ratio")
    rating = row.get("rating_counts_mean")
    cat = row.get("days_to_next_catalyst")
    dd = row.get("drawdown_from_60d_high")

    a = None if tr is None else bool(tr >= TARGET_RATIO_MIN)
    b = None if rating is None else bool(rating >= RATING_MIN)
    d = None if cat is None else bool(cat <= CATALYST_MAX_CALENDAR_DAYS)
    e = None if dd is None else bool(dd <= DRAWDOWN_MAX)

    # (b) is skipped when unreadable; every other clause must be READ and TRUE.
    required = {"a": a, "d": d, "e": e}
    fires = all(v is True for v in required.values()) and (b is not False)
    readable = sum(1 for v in (a, b, d, e) if v is not None)

    return {
        "fires": bool(fires),
        "rule_variant": "a_b_d_e" if b is not None else "a_d_e",
        "clauses": {"a_target_ratio": a, "b_rating": b, "d_catalyst": d, "e_drawdown": e},
        "inputs": {"target_ratio": tr, "rating_counts_mean": rating,
                   "days_to_next_catalyst": cat, "drawdown_from_60d_high": dd},
        "n_clauses_readable": readable,
        "failed_clauses": [k for k, v in
                           (("a_target_ratio", a), ("b_rating", b),
                            ("d_catalyst", d), ("e_drawdown", e)) if v is False],
        "unreadable_clauses": [k for k, v in
                               (("a_target_ratio", a), ("b_rating", b),
                                ("d_catalyst", d), ("e_drawdown", e)) if v is None],
    }


# ----------------------------------------------------------------- the base rate


def prior_from_panel(rows: dict[str, Sequence[dict]],
                     forward: dict[str, dict[str, float]]) -> dict:
    """MEASURED base rates for the rule, on the panel.

    `rows`    {symbol: [feature row, ...]} with `day`, `target_ratio`,
              `drawdown_from_60d_high`.
    `forward` {symbol: {day: SPY-relative 21-session forward return}}.

    Two numbers come back, and the difference between them is the only thing
    worth looking at:

      `p_up_uncond`  P(21-session SPY-relative return > 0) over the whole panel
      `p_up_rule`    the same, restricted to rows where the rule's TESTABLE
                     clauses hold

    WHICH CLAUSES ARE TESTABLE HERE IS NOT THE SAME SET THE LIVE BOOK APPLIES.
    On the panel, (b) is never readable (no rating history) and (d) is almost
    never readable (the forward-catalyst calendar was empty until 2026-08-30).
    So `p_up_rule` is the base rate of **(a) AND (e)** -- a strictly WEAKER
    condition than the live rule. It is reported with `clauses_measured` naming
    exactly which ones it stands on, because a base rate quoted for the wrong
    condition is worse than no base rate: it is a wrong number with a receipt.

    `n_blocks` counts distinct year-months. A base rate resting on three months
    is three observations of a market, not 3,000 observations of a rule.
    """
    all_y: list[float] = []
    all_b: list[str] = []
    rule_y: list[float] = []
    rule_b: list[str] = []
    n_with_target = 0

    for sym, rs in rows.items():
        fwd = forward.get(sym) or {}
        for r in rs:
            day = str(r.get("day") or "")[:10]
            y = fwd.get(day)
            if y is None:
                continue
            all_y.append(y)
            all_b.append(day[:7])
            tr, dd = r.get("target_ratio"), r.get("drawdown_from_60d_high")
            if tr is not None:
                n_with_target += 1
            if tr is None or dd is None:
                continue
            if tr >= TARGET_RATIO_MIN and dd <= DRAWDOWN_MAX:
                rule_y.append(y)
                rule_b.append(day[:7])

    def _rate(ys: list[float], bs: list[str]) -> dict:
        if not ys:
            return {"p_up": None, "n": 0, "n_blocks": 0, "mean_rel": None}
        return {"p_up": round(sum(1 for v in ys if v > 0) / len(ys), 4),
                "n": len(ys), "n_blocks": len(set(bs)),
                "mean_rel": round(sum(ys) / len(ys), 5)}

    uncond = _rate(all_y, all_b)
    rule = _rate(rule_y, rule_b)
    return {
        "p_up_uncond": uncond,
        "p_up_rule": rule,
        "clauses_measured": ["a_target_ratio", "e_drawdown"],
        "clauses_not_measured": ["b_rating", "d_catalyst"],
        "why_not_measured": ("(b) has no rating history on the panel -- stamping today's "
                             "consensus on a 2025 date is the lookahead the panel exists to "
                             "prevent. (d) had an EMPTY forward-catalyst calendar until "
                             "2026-08-30, so `days_to_next_catalyst` is null on essentially "
                             "every panel row. The live rule is therefore STRICTER than the "
                             "condition this base rate was measured under."),
        "in_sample": True,
        "in_sample_note": ("measured on the same panel the book ranks over. This is a BASE "
                           "RATE for calibration, not evidence that the rule works; the "
                           "forward grade and the reliability table are."),
        "n_rows_with_target_ratio": n_with_target,
        "month_blocks_uncond": uncond["n_blocks"],
    }


# ------------------------------------------------------------------- the scoring


def score(row: dict, verdict: dict, prior: dict) -> dict:
    """Numbers for ONE name. Never abstains; every number names its basis."""
    vol = row.get("realised_vol_20d")
    mag = (float(vol) * math.sqrt(HORIZON_SESSIONS / TRADING_DAYS_PER_YEAR)) if vol else None
    claimed = min(mag, CLAIM_ABS_MOVE_CAP) if mag is not None else None

    cell = prior["p_up_rule"] if verdict["fires"] else prior["p_up_uncond"]
    p_up = cell.get("p_up")
    basis = ("panel base rate for (a AND e), the clauses measurable on the panel"
             if verdict["fires"] else "panel unconditional base rate")
    if p_up is None:
        # The panel could not produce a rate at all. 0.5 is the only defensible
        # number, and it is labelled as the absence it is rather than dressed up.
        p_up, basis = 0.5, "NO MEASURABLE BASE RATE on the panel; 0.5 is ignorance, not a forecast"

    exp_return = (2.0 * p_up - 1.0) * claimed if claimed is not None else None
    exp_basis = "(2*p_up - 1) x claimed_abs_move; p_up = 0.5 gives exactly zero"
    band = band_overlay(row)
    if band is not None and band.get("applies"):
        # The band's eleven-year mean excess replaces the two-cell scale hack
        # for the names it covers: the toxic +400%+ band goes NEGATIVE (and the
        # long-book coherence floor then excludes it), the +200..400% band goes
        # positive and is finally admissible on evidence rather than lost.
        exp_return = band["exp_return_monthly"]
        exp_basis = band["basis"]
    elif band is not None:
        exp_basis = f"{exp_basis}; {band['basis']}"
    downside = -Z05 * mag if mag is not None else None

    blocks = cell.get("n_blocks") or 0
    conf = (verdict["n_clauses_readable"] / 4.0) * min(1.0, blocks / CONFIDENCE_FULL_BLOCKS)
    conf = max(0.05, min(0.95, conf))

    return {
        "p_up_21d": round(p_up, 4),
        "p_up_basis": basis,
        "p_up_n": cell.get("n"),
        "p_up_n_blocks": blocks,
        "claimed_abs_move": round(claimed, 4) if claimed is not None else None,
        "claimed_abs_move_basis": (f"the name's own realised_vol_20d scaled by "
                                   f"sqrt({HORIZON_SESSIONS}/252), capped at "
                                   f"{CLAIM_ABS_MOVE_CAP:.0%}. A scale, not a forecast."),
        "exp_return": round(exp_return, 5) if exp_return is not None else None,
        "exp_return_basis": exp_basis,
        "upside_band": (band or {}).get("band"),
        "downside_5pct": round(downside, 5) if downside is not None else None,
        "downside_basis": f"-{Z05} x the same vol scale (5% normal quantile). Not a stop.",
        "confidence": round(conf, 3),
        "confidence_basis": (f"(clauses readable / 4) x min(1, date blocks / "
                             f"{CONFIDENCE_FULL_BLOCKS}) behind the base rate"),
    }


def rank_key(scored: dict, *, lam: float = 1.0) -> float:
    """`exp_return - lam*|downside_5pct|`. Code ranks; no prose ranks.

    lam = 1.0 balanced, 0.25 aggressive (the vision addendum's two settings).
    A row missing either number sorts last rather than sorting as zero -- an
    unmeasured name must not outrank a measured one that scored badly.
    """
    er, dn = scored.get("exp_return"), scored.get("downside_5pct")
    if er is None or dn is None:
        return float("-inf")
    return er - lam * abs(dn)


def reliability_table(graded: Sequence[dict], *, bins: int = 5) -> list[dict]:
    """Deciles (default quintiles) of `p_up` against the realised hit rate.

    This is the table that catches confident-and-wrong, which a hit rate alone
    cannot: a generator that says 0.9 and is right 55% of the time and one that
    says 0.55 and is right 55% of the time have the SAME hit rate and are not
    the same generator.
    """
    rows = [g for g in graded if g.get("p_up_21d") is not None and g.get("hit") is not None]
    if not rows:
        return []
    out = []
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        cell = [g for g in rows if (lo <= g["p_up_21d"] < hi) or (i == bins - 1 and g["p_up_21d"] == 1.0)]
        if not cell:
            continue
        hits = [1.0 if g["hit"] else 0.0 for g in cell]
        out.append({
            "p_up_bin": f"[{lo:.2f},{hi:.2f})",
            "n": len(cell),
            "mean_p_up": round(sum(g["p_up_21d"] for g in cell) / len(cell), 4),
            "realised_hit_rate": round(sum(hits) / len(hits), 4),
            "gap": round(sum(hits) / len(hits) - sum(g["p_up_21d"] for g in cell) / len(cell), 4),
        })
    return out


def brier(graded: Sequence[dict]) -> dict:
    """Brier score against the 0.5 reference. Lower is better; 0.25 is a coin."""
    rows = [g for g in graded if g.get("p_up_21d") is not None and g.get("hit") is not None]
    if not rows:
        return {"brier": None, "n": 0, "reference_coin": 0.25, "beats_coin": None}
    bs = sum((g["p_up_21d"] - (1.0 if g["hit"] else 0.0)) ** 2 for g in rows) / len(rows)
    return {"brier": round(bs, 5), "n": len(rows), "reference_coin": 0.25,
            "beats_coin": bool(bs < 0.25),
            "note": "a Brier below 0.25 beats always saying 0.5; on fewer than 20 graded "
                    "rows it is a receipt, not a result"}


def variant_histogram(rows: Sequence[dict]) -> dict[str, int]:
    """How many rows ran with the rating clause and how many without."""
    return dict(Counter(r.get("rule_variant", "?") for r in rows))
