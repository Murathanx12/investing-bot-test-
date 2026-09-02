"""SCENARIO LAB -- invented companies, declared expectations, the REAL stack.

    python -m scripts.scenario_lab                  # L1 only, offline, deterministic
    python -m scripts.scenario_lab --llm            # L1 + L2 (one DeepSeek call)
    python -m scripts.scenario_lab --llm --n 10     # how many scenarios to ask for
    python -m scripts.scenario_lab --llm --dry      # print the prompt, spend nothing

WHY THIS EXISTS
===============
Every test in this repo asserts a property of a function. None of them asks the
question Murat asked on 2026-09-02: *what does the whole decision stack DO to a
company nobody has ever seen?* A green suite proves the pieces behave; it does
not prove that a name with a stale target across a reverse split, or one analyst,
or a $1.50 close, gets the disposition the documentation promises.

So: synthetic companies, in the REAL tracker row schema, pushed through the REAL
path -- `tracker.build_rows` -> `apply_status` -> `murat_rule.evaluate/score`
(band overlay included) -> `tracker.build_portfolio` for all three
personalities. Nothing is mocked except the panel base rate, which is FROZEN
below and says so.

THE EXPECTATION IS DECLARED BEFORE THE RUN
==========================================
Each scenario carries `expected` -- written from the documented rules, not from
a first run. That ordering is the whole method. An expectation written after
seeing the output is a transcription of the engine, and a test that transcribes
the engine cannot disagree with it.

A MISMATCH IS THE PRODUCT, NOT THE FAILURE
==========================================
When the engine and the expectation disagree, one of them is wrong and we do not
yet know which. The lab RECORDS the disagreement with both sides and refuses to
resolve it by editing the engine, which is the one repair that would destroy the
evidence. `known_disagreement` on a scenario marks one that has been adjudicated
in writing; it still prints, loudly, on every run.

WHY THE PRIOR IS FROZEN
=======================
`prediction_book.rule_prior()` measures the base rate off panel bars, which
means a network fetch and a number that moves when the panel moves. A lab whose
expectations shift under it is not measuring the rule. `FROZEN_PRIOR` below is a
declared, in-lab constant with the shape `murat_rule.score` reads, chosen so
that a FIRING rule scores above the coin and a non-firing one below it -- which
is the sign structure the live panel has had since it was first measured. The
numbers are the lab's, not the market's, and no result here is evidence about
the market.

WHAT IT MAY NOT DO
==================
It places nothing, sizes nothing, seals nothing, and writes to exactly one
directory: `state/scenario_lab/`. It never writes a tracker day file, never
touches `state/predictions/`, and never calls the venue. L1 makes no network
call at all; L2 makes exactly one, to DeepSeek, through the spend gate.

THE LLM GENERATES; IT NEVER JUDGES
==================================
L2 asks DeepSeek to INVENT scenarios and to state what it expects. The engine
then rules on them. The model is never shown the engine's answer and is never
asked to grade anything -- including its own output. Where model and engine
disagree, the engine's ruling is recorded beside the model's expectation and
neither is declared correct: that pair is a research lead.

AND NO NUMBER GOES INTO THE PROMPT
==================================
House lesson, measured 2026-08-30: "move p_up by at most +/-0.10" made 11 of 13
answers come back at exactly 0.100. A bound the model can see is an anchor. The
L2 prompt therefore describes the books in words -- balanced, profit-seeking,
preservation -- and names no threshold, no ratio, no cap and no floor. It asks
for scenarios, never for calibrations.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alpha import config, murat_rule
from alpha import tracker as _tracker

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "state" / "scenario_lab"
RUNS = OUT / "runs.jsonl"
SUMMARY = OUT / "latest_summary.json"

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"

#: The lab's own base rate. NOT a measurement -- see the module docstring.
#: `n_blocks` is at `CONFIDENCE_FULL_BLOCKS` so `confidence` is decided by how
#: many clauses were READABLE, which is the term a scenario can actually vary.
FROZEN_PRIOR: dict[str, Any] = {
    "p_up_uncond": {"p_up": 0.45, "n": 4000, "n_blocks": 12, "mean_rel": -0.004},
    "p_up_rule": {"p_up": 0.55, "n": 900, "n_blocks": 12, "mean_rel": 0.006},
    "clauses_measured": ["a_target_ratio", "e_drawdown"],
    "clauses_not_measured": ["b_rating", "d_catalyst"],
    "in_sample": True,
    "lab_note": ("FROZEN BY THE SCENARIO LAB. A declared constant with the shape "
                 "`murat_rule.score` reads, so a scenario's disposition cannot move "
                 "because the panel moved. It is not evidence about any market."),
}

#: A healthy, entirely unremarkable company. Every scenario is this row with the
#: one thing it is testing changed, so a disposition difference has exactly one
#: cause. Fields and their spellings are copied from a real row in
#: `state/tracker/2026-09-02.jsonl`.
BASE_ROW: dict[str, Any] = {
    "symbol": "ZZTEST0",
    "day": "2026-09-02",
    "observed_at": "2026-09-02T04:38:33.767695+00:00",
    "close": 20.00,
    "high_60d": 28.00,                 # drawdown -28.6%, clear of the -15% clause
    "ret_12m": 0.10,
    "sessions": 315,
    "rec_counts": {"strongBuy": 8, "buy": 4, "hold": 0, "sell": 0, "strongSell": 0},
    "rec_period": "2026-09-01",
    "rec_status": "ok",
    "mean_target": 40.00,              # ratio 2.00 -> the +50..200% band
    "target_high": 55.0,
    "target_low": 28.0,
    "n_analysts_yf": 12,               # coverage bucket 11-25, CALIBRATED scale
    "target_status": "ok",
    "target_source": "scenario_lab:synthetic",
    "sector": "Industrials",
    "market_cap_usd": 2_000_000_000.0,
    "days_to_catalyst": 10,
    "days_to_catalyst_units": "calendar_days",
    "dv_bucket": "mid",
    "exchange": "NASDAQ",
    "median_dollar_volume": 20_000_000.0,
    "tradable": True,
    "shortable": True,
    "realised_vol_20d": 0.40,          # downside_5pct -19.0%: inside every cap
}

BOOKS = tuple(p.book for p in _tracker.PERSONALITIES)


# --------------------------------------------------------------------------
# The stack, run once per scenario
# --------------------------------------------------------------------------

def _band_label(band: dict | None) -> str:
    """Which of the band prior's FIVE answers this row got.

    `band_overlay` documents four silences and one opinion, and the difference
    between the silences is the whole point of it -- "no opinion" and
    "historically bad" are not the same statement about a company. Collapsing
    them into `applies: False` is exactly the collapse the prior was written to
    prevent, so the lab reads the basis string and names which one fired.
    """
    if band is None:
        return "NO_OPINION"
    if band.get("applies"):
        return "APPLIED"
    basis = band.get("basis") or ""
    if "close unreadable" in basis:
        return "WITHHELD_CLOSE"
    if "UNINFORMATIVE" in basis:
        return "UNINFORMATIVE_SUB2"
    if "coverage unreadable" in basis:
        return "WITHHELD_COVERAGE"
    if "NOT MEASURED" in basis:
        return "NOT_MEASURED_COVERAGE"
    return "UNLABELLED"


def _sign(x: float | None) -> str:
    if x is None:
        return "none"
    return "+" if x > 0 else ("-" if x < 0 else "0")


def _rule_row(t: dict) -> dict:
    """The tracker row reshaped into what the rule reads.

    Copied field-for-field from `prediction_book.tracker_rows`, including the
    `close` line that was added on 2026-09-01 when a pre-seal replay found the
    band prior could not verify its own sub-$2 condition without it. If those
    two ever diverge, the lab is testing a path that does not ship -- so the
    mapping is written once, here, in the same order and with the same comment.
    """
    up = t.get("upside")
    return {
        "symbol": t["symbol"],
        "realised_vol_20d": t.get("realised_vol_20d"),
        "drawdown_from_60d_high": t.get("drawdown_60d"),
        "days_to_next_catalyst": t.get("days_to_catalyst"),
        # target_ratio is target/price; the tracker stores it as target/price - 1.
        "target_ratio": (1.0 + up) if up is not None else None,
        "close": t.get("close"),
        "rating_counts_mean": t.get("consensus"),
        "coverage": t.get("coverage"),
        "coverage_bucket": t.get("coverage_bucket"),
        "past_winner": t.get("past_winner"),
        "sector": t.get("sector"),
        "ret_12m": t.get("ret_12m"),
    }


def _first_failure(row: dict, p: _tracker.Personality) -> str | None:
    """The eligibility rule this row fails FIRST, using the builder's own checks.

    `_eligibility_checks` is the single expression of every rule -- the same
    objects `build_portfolio` filters with. Re-deriving the reasons from a
    second copy is how an explanation drifts away from the filter it describes,
    which is the failure that whole function was restructured to prevent.
    """
    for check in _tracker._eligibility_checks(p):
        got = check(row)
        if got is not None:
            reason, detail = got
            return f"{reason}" + (f" [{detail}]" if detail else "")
    return None


def run_rows(raw: list[dict]) -> dict:
    """Push raw tracker rows through the whole decision stack. No side effects."""
    trows = _tracker.build_rows([dict(r) for r in raw])
    status_hist = _tracker.apply_status(trows)

    scored: dict[str, dict] = {}
    bands: dict[str, str] = {}
    fires: dict[str, bool] = {}
    for t in trows:
        rr = _rule_row(t)
        verdict = murat_rule.evaluate(rr)
        s = murat_rule.score(rr, verdict, FROZEN_PRIOR)
        scored[t["symbol"]] = s
        bands[t["symbol"]] = _band_label(murat_rule.band_overlay(rr))
        fires[t["symbol"]] = bool(verdict["fires"])
        # Exactly what `_build_from_tracker` carries back before it builds the
        # books. Without this every ratio ranking sees None and ranks -inf,
        # which is an empty book that took the same code path as a full one.
        for k in ("exp_return", "downside_5pct", "confidence", "p_up_21d"):
            t[k] = s.get(k)
        t["numbers_source"] = "rule"

    pool = _tracker.candidates(trows)
    pool_syms = {r["symbol"] for r in pool}

    books: dict[str, dict] = {}
    for p in _tracker.PERSONALITIES:
        built = _tracker.build_portfolio(trows, p)
        held = {h["symbol"] for h in built["holdings"]}
        per_symbol = {}
        for t in trows:
            sym = t["symbol"]
            if sym in held:
                per_symbol[sym] = {"disposition": "ADMITTED", "reason": None}
            elif sym not in pool_syms:
                per_symbol[sym] = {"disposition": "EXCLUDED",
                                   "reason": f"not a candidate (status {t.get('status')})"}
            else:
                fail = _first_failure(t, p)
                per_symbol[sym] = {
                    "disposition": "EXCLUDED",
                    "reason": fail or "eligible but not selected (rank, k, or sector cap)"}
        books[p.book] = {"n_selected": built["n_selected"],
                         "eligible": built["eligible"],
                         "candidate_pool": built["candidate_pool"],
                         "rank_distinct_values": built["rank_distinct_values"],
                         "per_symbol": per_symbol}

    return {"tracker_rows": trows, "status_histogram": status_hist,
            "scored": scored, "bands": bands, "fires": fires, "books": books}


def rule_row_disposition(rr: dict) -> dict:
    """A scenario that bypasses the tracker and hands the RULE a row directly.

    The tracker is not the only producer of a rule row: `prediction_book.build()`
    assembles one from the corpus panel, with its own field list. A scenario kind
    that speaks to the rule directly is the only way to test a row shape the
    tracker cannot make -- which is exactly where the interesting divergence
    between the two producers turned out to live.
    """
    verdict = murat_rule.evaluate(rr)
    s = murat_rule.score(rr, verdict, FROZEN_PRIOR)
    return {
        "band": _band_label(murat_rule.band_overlay(rr)),
        "rule_fires": bool(verdict["fires"]),
        "exp_return_sign": _sign(s.get("exp_return")),
        "exp_return": s.get("exp_return"),
        "exp_return_basis": s.get("exp_return_basis"),
        "target_ratio": rr.get("target_ratio"),
    }


def corpus_row_keys() -> set[str]:
    """The field list `prediction_book.build()` puts on a corpus-path rule row.

    Read out of the SOURCE with `ast`, not copied here, because a copy is a
    second thing to keep in sync and the whole finding below is what happens
    when two producers of the same row drift apart. If the shape it expects is
    gone it REFUSES -- a parity check that silently finds nothing would report
    parity, which is the opposite of what it saw.
    """
    import ast

    src = (ROOT / "scripts" / "prediction_book.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "build"), None)
    if fn is None:
        raise LabRefusal("scripts/prediction_book.py has no `build` -- the parity check "
                         "cannot find the corpus row producer and refuses to report parity.")
    found: list[set[str]] = []
    for node in ast.walk(fn):
        # `rows.append({...})` SPECIFICALLY. A first cut matched any `.append`
        # with a "symbol" key and picked up `predictions.append` as well, then
        # refused because it had found two. Refusing was right; the fix is to
        # name the list, not to relax the count.
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "append"
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "rows"
                and node.args and isinstance(node.args[0], ast.Dict)):
            keys = {k.value for k in node.args[0].keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if "symbol" in keys:
                found.append(keys)
    if len(found) != 1:
        raise LabRefusal(f"expected exactly one `rows.append({{...}})` inside "
                         f"`prediction_book.build`, found {len(found)}. The producer moved; "
                         f"the parity check refuses rather than guessing.")
    return found[0]


def tracker_row_keys() -> set[str]:
    """The field list the TRACKER path puts on a rule row -- from the lab's own copy.

    `_rule_row` is a byte-for-byte transcription of `prediction_book.tracker_rows`,
    so this is the tracker producer's shape as the lab reproduces it.
    """
    return set(_rule_row({"symbol": "ZZ", "upside": 1.0}))


def producer_parity() -> dict:
    """Do the two rule-row producers agree on the fields the band prior reads?"""
    corpus, tracker = corpus_row_keys(), tracker_row_keys()
    needed = {"close", "coverage"}
    return {
        "corpus_row_keys": sorted(corpus),
        "band_inputs_missing_from_corpus_row": sorted(needed - corpus),
        "band_inputs_missing_from_tracker_row": sorted(needed - tracker),
    }


def disposition(sc: dict) -> dict:
    """The ACTUAL disposition of one scenario, in the vocabulary `expected` uses."""
    if sc.get("kind") == "rule_row":
        return rule_row_disposition(sc["rule_row"])
    if sc.get("kind") == "producer_parity":
        return producer_parity()
    out = run_rows(sc["rows"])
    head = sc["rows"][0]["symbol"]
    t = next(r for r in out["tracker_rows"] if r["symbol"] == head)
    s = out["scored"][head]
    return {
        "status": t.get("status"),
        "band": out["bands"][head],
        "rule_fires": out["fires"][head],
        "exp_return_sign": _sign(s.get("exp_return")),
        "exp_return": s.get("exp_return"),
        "downside_5pct": s.get("downside_5pct"),
        "upside": t.get("upside"),
        "target_ratio": None if t.get("upside") is None else round(1.0 + t["upside"], 6),
        "coverage_bucket": t.get("coverage_bucket"),
        "books": {b: out["books"][b]["per_symbol"][head]["disposition"] for b in BOOKS},
        "book_reasons": {b: out["books"][b]["per_symbol"][head]["reason"] for b in BOOKS},
        "n_selected": {b: out["books"][b]["n_selected"] for b in BOOKS},
        "status_histogram": out["status_histogram"],
    }


def compare(expected: dict, actual: dict) -> list[str]:
    """Every declared key that did not come true. Keys not declared are not judged.

    `book_reasons` is compared as a SUBSTRING because the engine's reason strings
    carry per-name detail (a dollar figure, a ticker). Pinning them exactly would
    make the lab fail on a formatting change and pass on a logic change, which is
    the wrong sensitivity in both directions.
    """
    bad: list[str] = []
    for key, want in expected.items():
        if key == "book_reasons":
            for book, frag in (want or {}).items():
                got = actual["book_reasons"].get(book) or ""
                if frag.lower() not in got.lower():
                    bad.append(f"{book} reason: want ~{frag!r}, got {got!r}")
            continue
        if key in ("books", "n_selected"):
            for book, wv in (want or {}).items():
                gv = actual.get(key, {}).get(book)
                if gv != wv:
                    bad.append(f"{key}.{book}: want {wv!r}, got {gv!r}")
            continue
        got = actual.get(key)
        if got != want:
            bad.append(f"{key}: want {want!r}, got {got!r}")
    return bad


def _row(**over: Any) -> dict:
    r = dict(BASE_ROW)
    r.update(over)
    return r


# --------------------------------------------------------------------------
# L1 -- the hand-written canon
# --------------------------------------------------------------------------
#
# ONE-NAME UNIVERSES, AND WHAT THAT CHANGES. Each scenario is built alone, so
# `mark_past_winners` has a one-value cross-section and `_decile_cut` correctly
# returns None -- the decile leg cannot be evaluated on a sample of one. The
# ABSOLUTE leg (`ret_12m >= +100%`) still runs, and that is the leg the canon
# uses to make a past winner. The isolation is deliberate: a shared universe
# would make every scenario's status depend on every other scenario's return.

CANON: list[dict] = [
    {
        "id": "L1-01-admissible-mid-band",
        "why": "the ordinary case: a hygienic +100% target must be admitted by all three books",
        "rows": [_row(symbol="ZZTEST1")],
        "expected": {
            "status": "STRONG_BUY", "band": "APPLIED", "rule_fires": True,
            "exp_return_sign": "+",
            "books": {"hack3": "ADMITTED", "hack4": "ADMITTED", "hack6": "ADMITTED"},
        },
    },
    {
        "id": "L1-02-lost-winners-band",
        "why": ("the +200..400% band was RE-ADMITTED on 2026-09-01 at +16.55%/yr t2.20. "
                "If it silently stops being admissible the seal loses its best cell."),
        "rows": [_row(symbol="ZZTEST2", mean_target=70.00)],       # ratio 3.5
        "expected": {
            "status": "STRONG_BUY", "band": "APPLIED", "rule_fires": True,
            "exp_return_sign": "+",
            "books": {"hack3": "ADMITTED", "hack4": "ADMITTED", "hack6": "ADMITTED"},
        },
    },
    {
        "id": "L1-03-toxic-band",
        "why": ("ratio >= 5 measured -37.77%/yr t-7.75. It must be barred from candidacy "
                "AND carry a negative expectation -- two independent refusals, not one."),
        "rows": [_row(symbol="ZZTEST3", mean_target=120.00)],      # ratio 6.0
        "expected": {
            "status": "WATCH", "band": "APPLIED", "exp_return_sign": "-",
            "books": {"hack3": "EXCLUDED", "hack4": "EXCLUDED", "hack6": "EXCLUDED"},
            "book_reasons": {"hack3": "not a candidate"},
        },
    },
    {
        "id": "L1-04-boundary-ratio-1.50",
        "why": "clause (a) is `>=`, so exactly 1.50 must FIRE, not fall a hair short",
        "rows": [_row(symbol="ZZTEST4", mean_target=30.00)],       # ratio exactly 1.5
        "expected": {
            "status": "STRONG_BUY", "band": "APPLIED", "rule_fires": True,
            "target_ratio": 1.5, "exp_return_sign": "+",
            "books": {"hack3": "ADMITTED", "hack4": "ADMITTED", "hack6": "ADMITTED"},
        },
    },
    {
        "id": "L1-05-boundary-ratio-5.00-is-upside-4.00",
        "why": ("THE UNITS CHECK. `UPSIDE_IMPLAUSIBLE_AT = 4.00` is a RETURN and the toxic "
                "band's 5.0 is a RATIO. They are the same line, and if either constant is "
                "ever edited alone a corridor opens that one rule bars and the other blesses."),
        "rows": [_row(symbol="ZZTEST5", mean_target=100.00)],      # upside 4.00 == ratio 5.00
        "expected": {
            "status": "WATCH", "band": "APPLIED", "exp_return_sign": "-",
            "upside": 4.0, "target_ratio": 5.0,
            "books": {"hack3": "EXCLUDED", "hack4": "EXCLUDED", "hack6": "EXCLUDED"},
        },
    },
    {
        "id": "L1-06-sub-two-dollar-silence",
        "why": ("S30b: the sub-$2 cell measured t 0.39. The band must say NOTHING -- not "
                "'historically bad'. Silence and a negative verdict are different claims."),
        "rows": [_row(symbol="ZZTEST6", close=1.50, high_60d=2.10, mean_target=3.75,
                      median_dollar_volume=8_000_000.0)],
        "expected": {
            "status": "STRONG_BUY", "band": "UNINFORMATIVE_SUB2", "rule_fires": True,
            "exp_return_sign": "+",
            "books": {"hack3": "ADMITTED", "hack4": "ADMITTED", "hack6": "ADMITTED"},
        },
    },
    {
        "id": "L1-07-one-analyst-not-measured",
        "why": ("every EXP-RETURN-XS-1 cell conditions on >= 2 analysts, so a 1-analyst name "
                "is OUTSIDE the receipt. And hack6, the preservation book, must refuse it on "
                "coverage -- the 1.80x scale error let exactly this name in once already."),
        "rows": [_row(symbol="ZZTEST7", n_analysts_yf=1)],
        "expected": {
            "status": "STRONG_BUY", "band": "NOT_MEASURED_COVERAGE", "rule_fires": True,
            "coverage_bucket": "1-3", "exp_return_sign": "+",
            "books": {"hack3": "ADMITTED", "hack4": "ADMITTED", "hack6": "EXCLUDED"},
            "book_reasons": {"hack6": "coverage below 4-10"},
        },
    },
    {
        "id": "L1-08-missing-close-withheld",
        "why": ("`band_overlay` documents 'close unreadable -> WITHHELD' as one of its four "
                "silences. This asks whether that branch is reachable from the path that "
                "actually ships."),
        "rows": [_row(symbol="ZZTEST8", close=None)],
        "expected": {
            "status": "WATCH", "band": "WITHHELD_CLOSE",
            "books": {"hack3": "EXCLUDED", "hack4": "EXCLUDED", "hack6": "EXCLUDED"},
        },
        # ADJUDICATED 2026-09-02, first run. The declared expectation was WRONG
        # and the engine right, and the expectation is left standing rather than
        # rewritten: an expectation edited to match the output is a transcription
        # of the engine, and this record is the evidence that it was not one.
        #
        # On the TRACKER path `target_ratio` is derived FROM the close
        # (`(1.0 + upside)`, and `upside()` returns None on a missing price), so
        # an unreadable close makes the RATIO unreadable one step earlier and
        # `band_overlay` returns None -- NO_OPINION -- before the close branch is
        # ever reached. WITHHELD_CLOSE cannot fire on this path at all.
        #
        # Which raised the question that L1-17 and L1-18 answer: WHICH path can
        # fire it, and what does that path look like in production?
        "verdict": "EXPECTATION_WAS_WRONG",
        "known_disagreement": (
            "the lab's expectation was wrong, not the engine: on the tracker path the ratio "
            "is derived from the close, so a missing close makes the ratio unreadable FIRST "
            "and the band returns NO_OPINION. WITHHELD_CLOSE is unreachable here. Kept "
            "standing as the record that the expectation was declared before the run. "
            "See L1-17/L1-18 for where it IS reachable."),
    },
    {
        "id": "L1-09-negative-exp-coherence-floor",
        "why": ("S33's finding, as a fixture: a name the TRACKER calls STRONG_BUY that every "
                "book refuses on the long-book coherence floor. The gate is not the alpha."),
        # Coverage 1 puts it outside the band prior, so the panel's unconditional
        # cell decides; the shallow drawdown fails clause (e), so the rule does
        # not fire and that cell is below the coin.
        "rows": [_row(symbol="ZZTEST9", n_analysts_yf=1, close=27.50, high_60d=28.00,
                      mean_target=44.00)],
        "expected": {
            "status": "STRONG_BUY", "band": "NOT_MEASURED_COVERAGE", "rule_fires": False,
            "exp_return_sign": "-",
            "books": {"hack3": "EXCLUDED", "hack4": "EXCLUDED", "hack6": "EXCLUDED"},
            "book_reasons": {"hack4": "exp_return not positive"},
        },
    },
    {
        "id": "L1-10-downside-above-the-caps",
        "why": ("a stop is decoration if the 5% quantile gaps through it. hack3 caps at 30%, "
                "hack6 at 20%, hack4 at NOTHING -- so one row must split the three books."),
        "rows": [_row(symbol="ZZTESTA", realised_vol_20d=1.20)],   # |downside| ~57%
        "expected": {
            "status": "STRONG_BUY", "band": "APPLIED", "exp_return_sign": "+",
            "books": {"hack3": "EXCLUDED", "hack4": "ADMITTED", "hack6": "EXCLUDED"},
            "book_reasons": {"hack3": "downside above the 30% cap",
                             "hack6": "downside above the 20% cap"},
        },
    },
    {
        "id": "L1-11-illiquid-below-hack6-floor",
        "why": ("hack6's $5m/day floor is the one that actually binds; hack3/hack4's $1m is "
                "inert today. An inert floor must read as inert, never as a screen."),
        "rows": [_row(symbol="ZZTESTB", median_dollar_volume=2_000_000.0)],
        "expected": {
            "books": {"hack3": "ADMITTED", "hack4": "ADMITTED", "hack6": "EXCLUDED"},
            "book_reasons": {"hack6": "liquidity floor"},
        },
    },
    {
        "id": "L1-12-dollar-volume-unreadable",
        "why": ("a guard DERIVES its input or REFUSES. An unreadable dollar volume is not a "
                "liquid name, and `or 0` here would admit exactly what the floor excludes."),
        "rows": [_row(symbol="ZZTESTC", median_dollar_volume=None)],
        "expected": {
            "books": {"hack3": "EXCLUDED", "hack4": "EXCLUDED", "hack6": "EXCLUDED"},
            "book_reasons": {"hack3": "dollar volume unreadable",
                             "hack6": "dollar volume unreadable"},
        },
    },
    {
        "id": "L1-13-no-readable-catalyst",
        "why": ("hack4 alone requires a dated catalyst. Absent one the status must fall from "
                "STRONG_BUY to BUY -- blocked, not failed -- and only hack4 must lose the name."),
        "rows": [_row(symbol="ZZTESTD", days_to_catalyst=None)],
        "expected": {
            "status": "BUY",
            "books": {"hack3": "ADMITTED", "hack4": "EXCLUDED", "hack6": "ADMITTED"},
            "book_reasons": {"hack4": "no readable catalyst"},
        },
    },
    {
        "id": "L1-14-past-winner-live-ab",
        "why": ("clause (f) is a LIVE A/B, not a setting: ON for hack3, OFF for hack4/hack6. "
                "One row must be refused by one book and held by two, or the experiment has "
                "quietly ended."),
        "rows": [_row(symbol="ZZTESTE", ret_12m=3.00)],            # +300% -> absolute leg
        "expected": {
            "books": {"hack3": "EXCLUDED", "hack4": "ADMITTED", "hack6": "ADMITTED"},
            "book_reasons": {"hack3": "past winner"},
        },
    },
    {
        "id": "L1-15-reverse-split-stale-target",
        "why": ("the +400% band's MEDIAN upside is 44x -- arithmetic, not opinion: an old "
                "target read against a post-reverse-split price. It must never be a candidate."),
        "rows": [_row(symbol="ZZTESTF", close=2.00, mean_target=90.00, high_60d=3.00,
                      median_dollar_volume=8_000_000.0)],          # ratio 45
        "expected": {
            "status": "WATCH", "band": "APPLIED", "exp_return_sign": "-",
            "books": {"hack3": "EXCLUDED", "hack4": "EXCLUDED", "hack6": "EXCLUDED"},
        },
    },
    {
        "id": "L1-16-sector-cap-binds",
        "why": ("20 of 21 names falling together on 28 Aug was ONE bet wearing 20 tickers. "
                "Five identical names in one sector must fill hack4 to its cap of 2, not to k=5."),
        "rows": [_row(symbol=f"ZZTESTG{i}", ret_12m=None,
                      # a hair of dispersion so the ranking is not degenerate
                      mean_target=40.00 + i * 0.5) for i in range(5)],
        "expected": {"n_selected": {"hack4": 2}},
    },
    {
        "id": "L1-17-corpus-shape-withholds-the-band",
        "kind": "rule_row",
        "why": ("WHERE WITHHELD_CLOSE ACTUALLY FIRES. `prediction_book.build()` -- the CORPUS "
                "arm, and the CLI default -- assembles a rule row with `target_ratio` but "
                "without `close`. That is precisely the shape the band prior must refuse."),
        # The corpus producer's exact field list, with a ratio deep in the toxic
        # band. On the tracker path this row would score -37.77%/yr and be
        # thrown out; here the band declines to look.
        "rule_row": {"symbol": "ZZTESTH", "realised_vol_20d": 0.40,
                     "drawdown_from_60d_high": -0.2857, "days_to_next_catalyst": 10,
                     "target_ratio": 6.0, "rating_counts_mean": 4.67},
        "expected": {"band": "WITHHELD_CLOSE", "rule_fires": True, "exp_return_sign": "+"},
    },
    {
        "id": "L1-18-producer-parity",
        "kind": "producer_parity",
        "why": ("THE FINDING L1-08 UNCOVERED. Two functions build a rule row -- "
                "`tracker_rows()` and `build()` -- and the band prior reads `close` and "
                "`coverage` off it. Both producers must carry both, or the prior is silently "
                "OFF for one arm of a live A/B."),
        "expected": {"band_inputs_missing_from_corpus_row": [],
                     "band_inputs_missing_from_tracker_row": []},
        "verdict": "ENGINE_DISAGREES",
        "known_disagreement": (
            "LIVE ASYMMETRY, recorded not repaired. `tracker_rows()` gained `close` on "
            "2026-09-01 after a pre-seal replay found the band prior could not verify its own "
            "sub-$2 condition; the fix landed on ONE of the two producers. "
            "`prediction_book.build()` -- the corpus arm, and `--universe`'s DEFAULT -- still "
            "ships neither `close` nor `coverage`, so BAND-CONDITIONAL PRIOR v2 is WITHHELD on "
            "every corpus name while it applies on every tracker name. The two arms are "
            "therefore not running the same scorer. Not fixed here: this lab does not edit the "
            "engine, and which arm is correct is a decision about the experiment, not a "
            "typo. Owner: the next seal review."),
    },
    {
        "id": "L1-19-target-below-price-still-scores-positive",
        "why": ("PROMOTED FROM L2 on 2026-09-02 -- deepseek invented it, the engine ruled on "
                "it, and it is now permanent coverage. The band prior's lowest cell is "
                "`(0.0, 1.5)`, so a consensus target at a TWENTIETH of the last close lands in "
                "the same bucket as an ordinary name and is handed the same POSITIVE "
                "+2.41%/yr constant. Nothing keeps that name out of a long book except the "
                "STATUS rule -- the expectation itself does not object. The gate, not the "
                "alpha, again: if the status bar ever moved, this would arrive already "
                "blessed. Pinned as an OBSERVATION of today's behaviour, not as approval."),
        "rows": [_row(symbol="ZZTESTI", mean_target=1.00)],        # ratio 0.05
        "expected": {
            "status": "SELL", "band": "APPLIED", "rule_fires": False,
            "exp_return_sign": "+",
            "books": {"hack3": "EXCLUDED", "hack4": "EXCLUDED", "hack6": "EXCLUDED"},
            "book_reasons": {"hack3": "not a candidate", "hack4": "not a candidate",
                             "hack6": "not a candidate"},
        },
    },
]


# --------------------------------------------------------------------------
# L2 -- the LLM invents the adversary
# --------------------------------------------------------------------------

_LANG = ("Answer in English only. Reply with STRICT JSON and nothing else, in the form "
         '{"scenarios": [ ... ]} -- no prose before or after it.')

#: NO NUMBER APPEARS HERE ON PURPOSE. See the module docstring: a bound in the
#: prompt is an anchor, and the anchored answer looks like agreement. The books
#: are described by their MANDATE, which is what a scenario writer needs, and
#: never by their thresholds, which is what would let the model reverse-engineer
#: the engine instead of attacking it.
L2_PROMPT = """You are inventing ADVERSARIAL TEST SCENARIOS for a US-equity screening engine. Each scenario is one fictional company. Your job is to invent companies whose correct handling is genuinely hard or ambiguous, so that a disagreement between you and the engine points at something real.

The engine reads a daily row per company with these fields:

  symbol                 ticker (invent one; it must start with "ZZ")
  close                  last close in USD, or null if unreadable
  high_60d               highest price in the last 60 sessions, or null
  ret_12m                trailing 12-month total return as a DECIMAL fraction, or null
  rec_counts             {{"strongBuy": int, "buy": int, "hold": int, "sell": int, "strongSell": int}}
  mean_target            mean analyst price target in USD, or null
  n_analysts_yf          number of analysts covering the name, or null
  sector                 sector name as a string
  market_cap_usd         market capitalisation in USD
  days_to_catalyst       calendar days to the next dated company event, or null
  median_dollar_volume   median daily traded value in USD, or null
  realised_vol_20d       annualised realised volatility over 20 sessions, as a decimal
  tradable               true or false

Downstream, three portfolios select from whatever the screen admits:

  hack3  BALANCED       -- wants reward per unit of risk, and declines companies whose
                          last twelve months already look like the win
  hack4  PROFIT-SEEKING -- wants the largest expected move, insists on a dated near-term
                          company event, and accepts a rough ride to get it
  hack6  PRESERVATION   -- wants a well-covered, liquid company with a contained bad case

Invent {n} scenarios. Hunt the edge cases a careful engineer would miss:
  - units confusion between a target RATIO and a target RETURN, in either direction
  - a price target left stale across a stock split or a reverse split
  - the boundary of analyst coverage, in both directions
  - companies that barely trade, or whose traded value is unreadable
  - targets that are absurd, self-contradictory, or inconsistent with the rating
  - fields that are missing rather than wrong, and fields that are wrong rather than missing
  - anything where "no opinion" and "a bad opinion" would be easy to confuse

Do NOT propose thresholds, cutoffs, or calibrations, and do not guess the engine's constants. Invent COMPANIES.

For each scenario return an object:
{{"scenario_id": "<short slug>",
  "row": {{ ...the fields above... }},
  "expected_status": "<one of STRONG_BUY, BUY, HOLD, SELL, DROP, WATCH>",
  "expected_books": {{"hack3": "<ADMITTED or EXCLUDED>", "hack4": "...", "hack6": "..."}},
  "rationale": "<one line, under 30 words, saying what this scenario is attacking>"}}

{lang}"""


class LabRefusal(RuntimeError):
    """The lab declines to proceed, and says why."""


def l2_prompt(n: int) -> str:
    return L2_PROMPT.format(n=n, lang=_LANG)


def ask_llm(n: int, *, timeout: float = 180.0) -> tuple[str, dict]:
    """One DeepSeek call. Returns (raw text, usage). Refuses rather than mocking."""
    from alpha.spend import llm_post

    key = os.getenv("AAT_DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise LabRefusal("AAT_DEEPSEEK_API_KEY is not set -- L2 refuses rather than "
                         "inventing scenarios locally and calling them the model's.")
    body = {"model": MODEL, "temperature": 1.0, "max_tokens": 4096,
            "messages": [{"role": "user", "content": l2_prompt(n)}]}
    why = ("decides whether the scenario canon covers the edge cases a fresh adversary "
           "finds, and each disagreement between the model's expectation and the engine's "
           "ruling is ranked as a research lead for the next seal")
    data, _dt = llm_post(DEEPSEEK_URL, body, headers={"Authorization": f"Bearer {key}"},
                         why=why, caller="scenario_lab", timeout=timeout)
    text = data["choices"][0]["message"]["content"]
    return text, (data.get("usage") or {})


_ROW_KEYS = set(BASE_ROW)
_NUMERIC = ("close", "high_60d", "ret_12m", "mean_target", "n_analysts_yf",
            "market_cap_usd", "days_to_catalyst", "median_dollar_volume",
            "realised_vol_20d", "target_high", "target_low")


def parse_llm_scenarios(text: str) -> tuple[list[dict], list[dict]]:
    """(usable scenarios, refusals). A malformed scenario is RECORDED, never dropped.

    Silence about a scenario that could not be read is indistinguishable from a
    scenario that was never proposed, and the count is what tells us whether the
    generator is producing usable adversaries or noise.
    """
    refused: list[dict] = []
    obj = None
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        obj = json.loads(m.group(0) if m else (text or ""))
    except (ValueError, AttributeError) as exc:
        return [], [{"scenario_id": "<whole reply>", "refusal": f"reply is not JSON: {exc}",
                     "raw": (text or "")[:400]}]

    raw_list = obj.get("scenarios") if isinstance(obj, dict) else obj
    if not isinstance(raw_list, list):
        return [], [{"scenario_id": "<whole reply>",
                     "refusal": "no `scenarios` list in the reply",
                     "raw": str(obj)[:400]}]

    out: list[dict] = []
    for i, item in enumerate(raw_list):
        sid = str((item or {}).get("scenario_id") or f"unnamed-{i}")[:60] if isinstance(item, dict) else f"unnamed-{i}"
        if not isinstance(item, dict) or not isinstance(item.get("row"), dict):
            refused.append({"scenario_id": sid, "refusal": "no `row` object",
                            "raw": str(item)[:300]})
            continue
        src = item["row"]
        # START FROM THE BASE ROW, not from {}. A scenario that omits a field is
        # testing the field it DID set; scoring it against a row of nulls would
        # make every LLM scenario a missing-data test and nothing else. Fields
        # the model set to null stay null -- an explicit null is a scenario.
        row = dict(BASE_ROW)
        unknown = [k for k in src if k not in _ROW_KEYS]
        for k, v in src.items():
            if k in _ROW_KEYS:
                row[k] = v
        bad: list[str] = []
        for k in _NUMERIC:
            v = row.get(k)
            if v is None or isinstance(v, (int, float)) and not isinstance(v, bool):
                continue
            try:
                row[k] = float(v)
            except (TypeError, ValueError):
                bad.append(f"{k}={v!r}")
        if not isinstance(row.get("rec_counts"), dict) and row.get("rec_counts") is not None:
            bad.append(f"rec_counts={row.get('rec_counts')!r}")
        if bad:
            refused.append({"scenario_id": sid,
                            "refusal": "unreadable field(s): " + ", ".join(bad)[:200],
                            "raw": str(src)[:300]})
            continue
        # The symbol is REPLACED, never trusted. A scenario carrying a real
        # ticker would read, in a log, exactly like a decision about that
        # company -- and this lab must never produce a row that could.
        row["symbol"] = f"ZZLLM{i:02d}"
        row["day"] = BASE_ROW["day"]
        row["target_source"] = "scenario_lab:llm"

        exp: dict[str, Any] = {}
        st = item.get("expected_status")
        if isinstance(st, str) and st.upper() in _tracker.STATUSES:
            exp["status"] = st.upper()
        eb = item.get("expected_books")
        if isinstance(eb, dict):
            books = {b: str(eb[b]).upper() for b in BOOKS
                     if isinstance(eb.get(b), str) and str(eb[b]).upper() in ("ADMITTED", "EXCLUDED")}
            if books:
                exp["books"] = books
        if not exp:
            refused.append({"scenario_id": sid,
                            "refusal": "no readable expectation (status or books)",
                            "raw": str(item)[:300]})
            continue
        out.append({
            "id": f"L2-{i:02d}-{re.sub(r'[^a-z0-9-]+', '-', sid.lower())[:40]}",
            "why": str(item.get("rationale") or "")[:240],
            "llm_symbol": str(src.get("symbol") or "")[:16],
            "unknown_fields": unknown,
            "rows": [row],
            "expected": exp,
        })
    return out, refused


# --------------------------------------------------------------------------
# L3 -- the log
# --------------------------------------------------------------------------

def evaluate_scenarios(scenarios: list[dict], layer: str, source: str) -> list[dict]:
    """Run each scenario and compare against its DECLARED expectation."""
    results: list[dict] = []
    for sc in scenarios:
        try:
            actual = disposition(sc)
            mismatches = compare(sc["expected"], actual)
            err = None
        except Exception as exc:                                   # noqa: BLE001
            # An engine EXCEPTION on a synthetic row is itself a finding: the
            # stack met an input it could not classify. It is recorded as one
            # rather than crashing the lab, which would lose every later row.
            actual, mismatches, err = None, ["engine raised"], f"{type(exc).__name__}: {exc}"
        results.append({
            "scenario_id": sc["id"],
            "layer": layer,
            "source": source,
            "rationale": sc.get("why", ""),
            "expected": sc["expected"],
            "actual": actual,
            "match": not mismatches,
            "mismatches": mismatches,
            "engine_error": err,
            "known_disagreement": sc.get("known_disagreement"),
            "verdict": sc.get("verdict"),
            "llm_symbol": sc.get("llm_symbol"),
        })
    return results


class _NullFile:
    """A file that accepts writes and keeps none, so `--no-log` shares ONE code
    path with the logging one. Two paths would let the logged and unlogged runs
    drift, and the unlogged run is the one nobody reads the output of twice."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def write(self, _s: str) -> None:
        return None


def log_run(results: list[dict], refusals: list[dict], *, run_id: str,
            layers: list[str], usage: dict | None = None, write: bool = True) -> dict:
    """Append one line per scenario, then overwrite the summary receipt.

    `write=False` builds the same summary and touches no file, so an offline
    canon check cannot destroy the receipt of a paid run.
    """
    ts = datetime.now(timezone.utc).isoformat()
    if write:
        OUT.mkdir(parents=True, exist_ok=True)
    with (RUNS.open("a", encoding="utf-8") if write else _NullFile()) as fh:
        for r in results:
            fh.write(json.dumps({
                "run_id": run_id, "ts": ts, "layer": r["layer"],
                "scenario_id": r["scenario_id"], "source": r["source"],
                "expected": r["expected"], "actual": r["actual"],
                "match": r["match"], "mismatches": r["mismatches"],
                "engine_error": r["engine_error"],
                "known_disagreement": r["known_disagreement"],
                "verdict": r.get("verdict"),
                "rationale": r["rationale"],
            }) + "\n")
        for ref in refusals:
            fh.write(json.dumps({
                "run_id": run_id, "ts": ts, "layer": "L2", "source": "deepseek",
                "scenario_id": ref["scenario_id"], "expected": None, "actual": None,
                "match": None, "mismatches": ["refused to parse"],
                "engine_error": None, "known_disagreement": None,
                "rationale": ref["refusal"], "raw": ref.get("raw"),
            }) + "\n")

    by_layer: dict[str, dict] = {}
    for r in results:
        d = by_layer.setdefault(r["layer"], {"n": 0, "match": 0, "mismatch": 0,
                                             "known_disagreement": 0, "engine_error": 0})
        d["n"] += 1
        d["match"] += 1 if r["match"] else 0
        d["mismatch"] += 0 if r["match"] else 1
        d["known_disagreement"] += 1 if (not r["match"] and r["known_disagreement"]) else 0
        d["engine_error"] += 1 if r["engine_error"] else 0
    if refusals:
        by_layer.setdefault("L2", {"n": 0, "match": 0, "mismatch": 0,
                                   "known_disagreement": 0, "engine_error": 0})
        by_layer["L2"]["refused_to_parse"] = len(refusals)

    summary = {
        "schema": "scenario-lab-1",
        "run_id": run_id, "ts": ts, "layers": layers,
        "frozen_prior": FROZEN_PRIOR,
        "counts_by_layer": by_layer,
        "llm_usage": usage or {},
        "mismatches": [
            {"scenario_id": r["scenario_id"], "layer": r["layer"], "source": r["source"],
             "rationale": r["rationale"], "detail": r["mismatches"],
             "expected": r["expected"], "actual": r["actual"],
             "known_disagreement": r["known_disagreement"],
             "verdict": r.get("verdict"), "engine_error": r["engine_error"]}
            for r in results if not r["match"]],
        "refused_to_parse": refusals,
        "note": ("A mismatch is a RESEARCH LEAD, not a defect report. Where an LLM-invented "
                 "expectation and the engine disagree, neither side is graded here -- the "
                 "pair is recorded so a human can decide which one is wrong. The engine is "
                 "never edited to make a scenario pass."),
    }
    if write:
        SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


# --------------------------------------------------------------------------

def _wrap(text: str, width: int = 84) -> list[str]:
    import textwrap
    return textwrap.wrap(text, width) or [""]


def _print_results(results: list[dict]) -> tuple[int, int, int]:
    """(hard failures, adjudicated disagreements, research leads).

    ONLY THE L1 CANON CAN FAIL A RUN. Its expectations are the documented rules,
    written down by a human before the engine was asked, so a mismatch there is
    either a defect or a misreading of the documentation -- and both are worth an
    exit code.

    An L2 disagreement is neither. The model wrote its expectation from a prose
    description of three mandates; the engine applied eleven years of measured
    thresholds. That the two differ is the OUTPUT of that layer, not a fault in
    it, and a lab that exits 1 whenever an LLM guesses differently is a lab
    nobody runs twice. L2 disagreements are counted as LEADS and printed whole.
    """
    hard, soft, leads = 0, 0, 0
    for r in results:
        if r["match"]:
            print(f"  ok       {r['scenario_id']}")
            continue
        if r["known_disagreement"]:
            soft += 1
            head = ("EXPECTATION WAS WRONG -- recorded as a finding"
                    if r.get("verdict") == "EXPECTATION_WAS_WRONG"
                    else "ENGINE DISAGREES -- recorded as a finding")
            print(f"  {head}: {r['scenario_id']}")
            for line in _wrap(r["known_disagreement"]):
                print(f"           {line}")
        elif r["layer"] == "L1":
            hard += 1
            print(f"  MISMATCH {r['scenario_id']}")
        else:
            leads += 1
            print(f"  LEAD     {r['scenario_id']}   model expected / engine ruled")
            if r.get("rationale"):
                print(f"           the model was attacking: {r['rationale'][:96]}")
        for m in r["mismatches"]:
            print(f"           - {m}")
        if r["engine_error"]:
            print(f"           ! {r['engine_error']}")
    return hard, soft, leads


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--llm", action="store_true", help="also run L2 (one DeepSeek call)")
    ap.add_argument("--llm-only", action="store_true", help="skip the L1 canon")
    ap.add_argument("--n", type=int, default=10, help="scenarios to ask the model for")
    ap.add_argument("--dry", action="store_true", help="print the L2 prompt, spend nothing")
    #: `latest_summary.json` is overwritten by whatever ran last, so a quick
    #: offline L1 sanity pass silently DELETED the receipt of the paid L2 run
    #: that produced it -- twice, on the day this was written. The append-only
    #: log kept every line, which is exactly why it is append-only; the receipt
    #: did not. This flag is the cheap fix: check the canon without spending a
    #: call to restore a receipt.
    ap.add_argument("--no-log", action="store_true",
                    help="run and print, but do not append to runs.jsonl or overwrite "
                         "latest_summary.json (for offline canon checks)")
    args = ap.parse_args(argv)
    config.load_env()

    if args.dry:
        print(l2_prompt(args.n))
        return 0

    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
    results: list[dict] = []
    refusals: list[dict] = []
    usage: dict = {}
    layers: list[str] = []

    if not args.llm_only:
        print(f"\nL1 -- hand-written canon ({len(CANON)} scenarios, offline, deterministic)")
        results += evaluate_scenarios(CANON, "L1", "hand")
        layers.append("L1")

    if args.llm or args.llm_only:
        print(f"\nL2 -- asking {MODEL} for {args.n} adversarial scenarios")
        try:
            text, usage = ask_llm(args.n)
        except Exception as exc:                                   # noqa: BLE001
            print(f"  REFUSED: {type(exc).__name__}: {str(exc)[:200]}")
            return 2
        got, refusals = parse_llm_scenarios(text)
        print(f"  parsed {len(got)} usable, {len(refusals)} refused to parse")
        for sc in got:
            print(f"    {sc['id']:44} {sc['why'][:70]}")
        results += evaluate_scenarios(got, "L2", "deepseek")
        layers.append("L2")

    print("")
    hard, soft, leads = _print_results(results)
    summary = log_run(results, refusals, run_id=run_id, layers=layers, usage=usage,
                      write=not args.no_log)

    print(f"\nrun {run_id}")
    for layer, d in sorted(summary["counts_by_layer"].items()):
        print(f"  {layer}: {d}")
    if args.no_log:
        print("  NOT LOGGED (--no-log): runs.jsonl and latest_summary.json untouched")
    else:
        print(f"  log     {RUNS}")
        print(f"  receipt {SUMMARY}")
    if soft:
        print(f"  {soft} adjudicated disagreement(s) -- kept, not repaired")
    if leads:
        print(f"  {leads} model/engine disagreement(s) -- THE PRODUCT of L2, listed in "
              f"latest_summary.json under `mismatches`. Each is a lead, not a defect.")
    if hard:
        print(f"\n{hard} UNADJUDICATED CANON MISMATCH(ES). Read them; do not edit the "
              f"engine to silence them.")
        return 1
    print("\nSCENARIO LAB OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
