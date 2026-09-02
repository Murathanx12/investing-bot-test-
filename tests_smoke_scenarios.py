"""SCENARIO LAB -- the hand-written canon, run offline, against the real stack.

Run: python tests_smoke_scenarios.py   (also executed by run_tests.py)

WHAT THIS SUITE IS FOR, AND WHY IT IS NOT LIKE THE OTHERS
========================================================
Every other suite here asserts a property of a function. This one asserts a
DISPOSITION: nineteen invented companies go in at the top of the decision stack
-- `tracker.build_rows` -> `apply_status` -> `murat_rule.evaluate/score` with the
band overlay -> `tracker.build_portfolio` for hack3, hack4 and hack6 -- and what
comes out is compared against an expectation written BEFORE the run, from the
documented rules.

That ordering is the method. An expectation written after seeing the output is a
transcription of the engine, and a transcription cannot disagree with it.

OFFLINE, ALWAYS. L1 touches no network: the panel base rate is frozen inside
`scripts/scenario_lab.FROZEN_PRIOR`, the rows are synthetic, and nothing here
reads a tracker day file or a sealed book. L2 -- the DeepSeek-generated
adversarial layer -- is NEVER run from this suite; only its PARSER is, on fixed
strings, because a generator that needs the network cannot be a unit test.

WHEN THE ENGINE AND THE EXPECTATION DISAGREE
============================================
The engine is not edited to make a scenario pass. One scenario currently
disagrees and it is adjudicated in writing in the lab; this suite prints it
loudly on every run and stays green, because a permanent red line beside
seventeen real checks teaches the reader to skim red lines. What it will NOT
tolerate is a disagreement that nobody has written down: an unadjudicated
mismatch fails.

  L1-08  EXPECTATION WAS WRONG. On the tracker path `target_ratio` is derived
         from `close`, so a missing close makes the RATIO unreadable first and
         the band answers NO_OPINION -- WITHHELD_CLOSE is unreachable there.
  L1-18  WAS "ENGINE DISAGREES", REPAIRED 2026-09-02. The two producers of a
         rule row did not agree on the fields the band prior reads:
         `prediction_book.build()` (the corpus arm, and the CLI default) shipped
         neither `close` nor `coverage`, so BAND-CONDITIONAL PRIOR v2 was
         WITHHELD on every corpus name while it applied on every tracker name --
         two arms of a live A/B, not running the same scorer. Both producers now
         build through ONE `rule_row`, which REFUSES a caller that leaves a
         canonical field unstated. The corpus arm carries `close` from the same
         bars that priced its ratio, and an EXPLICIT `coverage=None` because its
         only analyst count is on a scale 1.80x the one the prior was measured
         on. v2 still withholds there -- now as stated data-absence rather than
         as a key nobody wrote. The pin below asserts the repair.

It also writes nothing. `evaluate_scenarios` is pure; only the lab's `main()`
appends to `state/scenario_lab/`, and one check below proves this suite left
that file exactly as it found it.
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import murat_rule as mr            # noqa: E402
from alpha import tracker as tr               # noqa: E402
from scripts import prediction_book as pb     # noqa: E402
from scripts import scenario_lab as lab       # noqa: E402


print("\n-- the lab itself: a scenario that declares nothing cannot be wrong")
check("every canon scenario declares an expectation BEFORE the run",
      all(s.get("expected") for s in lab.CANON), f"{len(lab.CANON)} scenarios")
check("every canon scenario says what it is attacking",
      all(len(s.get("why") or "") > 40 for s in lab.CANON))
check("canon ids are unique", len({s["id"] for s in lab.CANON}) == len(lab.CANON))
_syms = [r["symbol"] for s in lab.CANON for r in s.get("rows", [])]
_syms += [s["rule_row"]["symbol"] for s in lab.CANON if s.get("kind") == "rule_row"]
check("no canon scenario names a real ticker (every symbol is ZZ-prefixed)",
      _syms and all(x.startswith("ZZ") for x in _syms), f"{len(_syms)} symbols")
# The canon's sign structure rests on this and nothing else. If the frozen prior
# ever stopped straddling the coin, "the rule fired" and "the rule did not fire"
# would produce the same sign and half these scenarios would silently stop
# testing what they name.
check("the frozen prior straddles the coin (firing above, not firing below)",
      lab.FROZEN_PRIOR["p_up_rule"]["p_up"] > 0.5 > lab.FROZEN_PRIOR["p_up_uncond"]["p_up"])
check("the frozen prior is labelled as the lab's own, not as a measurement",
      "FROZEN BY THE SCENARIO LAB" in lab.FROZEN_PRIOR["lab_note"])

print("\n-- the reshape is the SHIPPING reshape, not a lab convenience")
# `_rule_row` WAS a transcription of `prediction_book.tracker_rows`, kept in sync
# by hand. On 2026-09-02 it became a call to the shipping builder itself, so
# "the lab exercises a path that does not ship" is no longer possible by
# construction -- which is stronger than the check that used to pin it, and the
# check is therefore about the shipping shape rather than about the copy.
_ship = {"symbol", "realised_vol_20d", "drawdown_from_60d_high", "days_to_next_catalyst",
         "target_ratio", "close", "rating_counts_mean", "coverage", "coverage_bucket",
         "past_winner", "sector", "ret_12m"}
check("the lab's tracker->rule reshape carries the shipping field list",
      _ship <= lab.tracker_row_keys(), str(sorted(_ship - lab.tracker_row_keys())))
check("the band prior's own inputs are on it", {"close", "coverage"} <= lab.tracker_row_keys())
check("and it IS the shipping builder, not a copy of it",
      lab.tracker_row_keys() == set(pb.rule_row_from_tracker({"symbol": "ZZ", "upside": 1.0})))

print("\n-- nineteen invented companies through the real decision stack")
_before = lab.RUNS.stat().st_size if lab.RUNS.exists() else None
results = lab.evaluate_scenarios(lab.CANON, "L1", "hand")
_after = lab.RUNS.stat().st_size if lab.RUNS.exists() else None
check("the canon ran", len(results) == len(lab.CANON), f"{len(results)} results")

adjudicated: list[dict] = []
for r in results:
    if r["match"]:
        check(r["scenario_id"], True)
        continue
    if r["known_disagreement"]:
        adjudicated.append(r)
        continue
    check(r["scenario_id"], False, "; ".join(r["mismatches"])[:200])

print("\n-- disagreements that are RECORDED rather than repaired")
for r in adjudicated:
    head = ("EXPECTATION WAS WRONG" if r.get("verdict") == "EXPECTATION_WAS_WRONG"
            else "ENGINE DISAGREES")
    print(f"  {head} -- recorded as a finding: {r['scenario_id']}")
    for m in r["mismatches"]:
        print(f"      {m}")
    print(f"      {r['known_disagreement'][:300]}")
check("every adjudicated disagreement carries a written verdict",
      all(x.get("verdict") in ("ENGINE_DISAGREES", "EXPECTATION_WAS_WRONG")
          for x in adjudicated), f"{len(adjudicated)} adjudicated")
check("no engine EXCEPTION on any synthetic row",
      not [r for r in results if r["engine_error"]],
      str([r["engine_error"] for r in results if r["engine_error"]])[:200])
check("running the canon writes NOTHING (only the lab's main() logs)",
      _before == _after, f"{_before} -> {_after}")

print("\n-- L1-18: the producer split, REPAIRED 2026-09-02, and pinned repaired")
# THIS PIN WAS WRITTEN TO FAIL WHEN THE SPLIT WAS REPAIRED SILENTLY, and that is
# what it did. It is rewritten rather than deleted, because the reason it flipped
# is a DECISION and the decision belongs beside the assertion:
#
#   a close and an analyst count are fundamentally observable for any US-listed
#   name, so a producer that omits them is a SCHEMA gap and never a data gap.
#
# `close` on the corpus arm now comes from `features.last_close` on the SAME bars
# and day that priced its `target_ratio`. `coverage` is an EXPLICIT None: the
# corpus arm's only available analyst count is Finnhub's panel total, a median
# 1.80x the yfinance/IBES scale `BAND_PRIOR["min_coverage"]` was measured on, and
# reading one against the other is the error that had hack6 admitting
# 1-2-analyst names while believing it required four. So v2 still WITHHOLDS on
# corpus names -- now for a stated reason, on a field that is present.
_parity = lab.producer_parity()
check("REPAIRED: both producers carry the band prior's inputs",
      _parity["band_inputs_missing_from_corpus_row"] == []
      and _parity["band_inputs_missing_from_tracker_row"] == [],
      str(_parity["band_inputs_missing_from_corpus_row"]))
check("REPAIRED: both producers state every canonical field",
      _parity["canonical_fields_missing_from_corpus_row"] == []
      and _parity["canonical_fields_missing_from_tracker_row"] == [],
      str(_parity["canonical_fields_missing_from_corpus_row"]))
check("and both go through ONE builder, so the split cannot silently reopen",
      _parity["corpus_producer_uses_canonical_builder"]
      and _parity["tracker_producer_uses_canonical_builder"])
# The mechanism, not the outcome: a producer that forgets a canonical field gets
# a loud refusal rather than a row the band prior quietly withholds on.
try:
    pb.rule_row(symbol="ZZ", target_ratio=2.0, close=20.0)
    _refused = ""
except ValueError as _exc:
    _refused = str(_exc)
check("rule_row REFUSES a producer that leaves a canonical field unstated",
      "REFUSES" in _refused and "coverage" in _refused, _refused[:120])
check("an explicit coverage=None is ACCEPTED -- a null is a statement",
      pb.rule_row(**{k: None for k in pb.RULE_ROW_FIELDS})["coverage"] is None)
# The corpus arm's honest silence, end to end: present field, no opinion.
_corpus_row = pb.rule_row_from_features(
    "ZZQ", {"target_ratio": 6.0, "realised_vol_20d": 0.40}, close=20.0)
check("a corpus row now carries its close, so the $2 condition is verifiable",
      _corpus_row["close"] == 20.0)
check("and its coverage is a STATED None, which v2 maps to WITHHELD_COVERAGE",
      "coverage" in _corpus_row and _corpus_row["coverage"] is None
      and lab._band_label(mr.band_overlay(_corpus_row)) == "WITHHELD_COVERAGE",
      lab._band_label(mr.band_overlay(_corpus_row)))

print("\n-- WITHHELD_CLOSE is still the contract for a row with no readable price")
check("FINDING: a row with no readable close WITHHOLDS the band even in the toxic cell",
      lab.rule_row_disposition({"symbol": "ZZP", "target_ratio": 6.0,
                                "realised_vol_20d": 0.40})["band"] == "WITHHELD_CLOSE")
check("and the same row WITH a close gets the toxic band's negative number",
      lab.rule_row_disposition({"symbol": "ZZP", "target_ratio": 6.0, "close": 20.0,
                                "coverage": 12, "realised_vol_20d": 0.40}
                               )["exp_return_sign"] == "-")

print("\n-- the boundary constants are ONE line, in two units")
# L1-05 asserts this behaviourally; this asserts it arithmetically, because the
# two constants live in different files and a future edit to either alone opens
# a corridor that one rule bars and the other blesses.
check("UPSIDE_IMPLAUSIBLE_AT (a RETURN) is the toxic band's edge (a RATIO) minus one",
      abs((tr.UPSIDE_IMPLAUSIBLE_AT + 1.0) - mr.BAND_PRIOR["bands"][0][0]) < 1e-12,
      f"{tr.UPSIDE_IMPLAUSIBLE_AT} vs {mr.BAND_PRIOR['bands'][0][0]}")

print("\n-- L2's prompt: a bound the model can see is an anchor")
prompt = lab.l2_prompt(10)
check("the prompt asks for English", "English only" in prompt)
check("the prompt asks for strict JSON", "STRICT JSON" in prompt)
check("the prompt asks for scenarios, explicitly NOT for calibrations",
      "Do NOT propose thresholds" in prompt and "Invent COMPANIES" in prompt)
# Every decimal threshold the engine actually uses. Bare integers are not
# checkable here -- "hack3", "high_60d" and "ret_12m" all contain digits -- so
# this pins the decimal forms, which is where the anchoring risk lives.
_thresholds = sorted({
    mr.TARGET_RATIO_MIN, mr.RATING_MIN, mr.DRAWDOWN_MAX, mr.CLAIM_ABS_MOVE_CAP,
    tr.UPSIDE_IMPLAUSIBLE_AT, tr.MIN_PRICE_USD, tr.STRONG_BUY_UPSIDE, tr.STRONG_BUY_CONSENSUS,
    tr.BUY_UPSIDE, tr.BUY_CONSENSUS, tr.HOLD_UPSIDE, tr.SELL_UPSIDE, tr.SELL_CONSENSUS,
    mr.BAND_PRIOR["min_price"], *[b[0] for b in mr.BAND_PRIOR["bands"]],
    *[p.max_notional for p in tr.PERSONALITIES],
    *[p.max_downside for p in tr.PERSONALITIES if p.max_downside is not None],
    *[p.max_sector_share for p in tr.PERSONALITIES if p.max_sector_share is not None],
})
_leaked = [v for v in _thresholds if str(float(v)) in prompt]
check("no engine threshold reaches the prompt in decimal form", not _leaked, str(_leaked))
_leaked_floor = [f for f in (1_000_000.0, 5_000_000.0)
                 if any(s in prompt for s in (f"{f:,.0f}", f"{int(f)}", f"${int(f / 1e6)}m"))]
check("no liquidity floor reaches the prompt", not _leaked_floor, str(_leaked_floor))
check("no personality's k reaches the prompt",
      not [p for p in tr.PERSONALITIES
           if f"{p.book}" in prompt and f"top {p.k}" in prompt.lower()])

print("\n-- L2's parser: a malformed scenario is RECORDED, never dropped in silence")
ok, refused = lab.parse_llm_scenarios("this is not json at all")
check("a non-JSON reply is one recorded refusal, not an empty success",
      not ok and len(refused) == 1 and "not JSON" in refused[0]["refusal"])
ok, refused = lab.parse_llm_scenarios('{"answer": 42}')
check("JSON without a `scenarios` list is a recorded refusal",
      not ok and len(refused) == 1 and "scenarios" in refused[0]["refusal"])
_mixed = json.dumps({"scenarios": [
    {"scenario_id": "good", "row": {"symbol": "ZZGOOD", "close": 12.0, "mean_target": 30.0},
     "expected_status": "STRONG_BUY",
     "expected_books": {"hack3": "ADMITTED", "hack4": "ADMITTED", "hack6": "EXCLUDED"},
     "rationale": "an ordinary admissible name"},
    {"scenario_id": "no-row", "expected_status": "WATCH"},
    {"scenario_id": "junk-number", "row": {"symbol": "ZZBAD", "close": "twelve dollars"},
     "expected_status": "WATCH"},
    {"scenario_id": "no-expectation", "row": {"symbol": "ZZNOEXP", "close": 5.0}},
]})
ok, refused = lab.parse_llm_scenarios(_mixed)
check("the readable scenario survives", len(ok) == 1 and ok[0]["id"].startswith("L2-00-good"))
check("the three unreadable ones are RECORDED, not dropped", len(refused) == 3,
      str([r["scenario_id"] for r in refused]))
check("a missing row is named as such",
      any("no `row`" in r["refusal"] for r in refused))
check("an unreadable number is named with its field",
      any("close=" in r["refusal"] for r in refused))
check("a scenario with no readable expectation is refused, not judged against nothing",
      any("no readable expectation" in r["refusal"] for r in refused))
check("an LLM symbol is REPLACED, so no lab row can ever read as a real company",
      ok[0]["rows"][0]["symbol"].startswith("ZZLLM")
      and ok[0]["llm_symbol"] == "ZZGOOD")
# An omitted field must inherit the healthy base row. Scoring omissions against a
# row of nulls would turn every LLM scenario into the same missing-data test.
check("omitted fields inherit the base row; only what the model set is varied",
      ok[0]["rows"][0]["sector"] == lab.BASE_ROW["sector"]
      and ok[0]["rows"][0]["close"] == 12.0)
check("an LLM expectation is read into the same vocabulary the canon uses",
      ok[0]["expected"]["status"] == "STRONG_BUY"
      and ok[0]["expected"]["books"]["hack6"] == "EXCLUDED")
# The model is a GENERATOR. If a future edit ever asked it to grade, this fails.
_src = (lab.ROOT / "scripts" / "scenario_lab.py").read_text(encoding="utf-8")
check("the lab never sends the engine's ruling back to the model",
      "actual" not in lab.L2_PROMPT and "engine said" not in _src.lower())

print("\n-- an LLM-shaped scenario runs through the same stack as the canon")
_got = lab.evaluate_scenarios(ok, "L2", "deepseek")
check("an LLM scenario is evaluated, not merely parsed",
      len(_got) == 1 and _got[0]["actual"] is not None and _got[0]["layer"] == "L2")
check("its disposition speaks the canon's vocabulary",
      set(_got[0]["actual"]["books"]) == set(lab.BOOKS)
      and _got[0]["actual"]["status"] in tr.STATUSES)

print(f"\n{'ALL PASS tests_smoke_scenarios' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
raise SystemExit(1 if fails else 0)
