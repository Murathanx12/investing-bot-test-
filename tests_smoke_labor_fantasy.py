"""B2's guards. A monotonicity share is only a fact about a model if the exam,
the grading arithmetic and the spend gate are all above suspicion.

Every check here runs with a STUBBED decider and costs $0.00. What is pinned:

  * the pairs differ by EXACTLY ONE fact — everything before "This week," is
    byte-identical between the two legs, so a move in the forecast cannot be a
    move in the description;
  * the grading is a DIRECTION, not a magnitude, and a backwards forecast fails
    every leg;
  * the canary fires only above its tolerance;
  * the leg order is shuffled, so a model that always answers higher on the
    first brief scores 50%, not 100%;
  * the prompt carries NO numeric bound (S28: a bound in the prompt is an
    anchor — 11 of 13 answers came back at exactly the bound);
  * the paid path goes through `alpha.spend.justify`, and this exam's
    justification actually passes that gate.

Run:  python run_tests.py -k labor_fantasy      (never any other way)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alpha import spend as SPEND                                # noqa: E402
from scripts import labor_b2_fantasy_exams as B2                # noqa: E402

FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL {name}" + (f" -- {detail}" if detail else ""))


def test_the_two_legs_differ_by_exactly_one_fact():
    items, _ = B2.build_exam(n_pairs=12, n_canaries=4)
    ok, bad = True, ""
    for it in items:
        g, b = it["brief_good"], it["brief_bad"]
        marker = " This week, "
        if marker not in g or marker not in b:
            ok, bad = False, f"{it['pair_id']}: no marker"
            break
        if g.split(marker)[0] != b.split(marker)[0]:
            ok, bad = False, f"{it['pair_id']}: the SETUP differs, not just the fact"
            break
        if g == b:
            ok, bad = False, f"{it['pair_id']}: the two legs are identical"
            break
    check("the two legs share every word before the flipped fact", ok, bad)


def test_the_exam_is_deterministic_and_the_entity_map_is_sealed():
    a, ma = B2.build_exam(8, 2)
    b, mb = B2.build_exam(8, 2)
    check("the exam rebuilds byte-identically from the same seed", a == b)
    check("the entity map is hashed", bool(ma["entity_map_sha256"]) and
          ma["entity_map_sha256"] == mb["entity_map_sha256"])
    names = {i["company"] for i in a}
    check("no two fictional companies share a name", len(names) == len(a))


def test_the_leg_order_is_shuffled():
    items, _ = B2.build_exam(40, 8)
    first = sum(1 for i in items if i["good_first"])
    check("the GOOD leg is not always asked first", 5 < first < len(items) - 5,
          f"good_first on {first} of {len(items)}")


def test_monotonicity_is_a_direction_not_a_magnitude():
    item = {"pair_id": "P", "family": "fda", "is_canary": False}
    g = B2.grade_pair(item,
                      {"p_up_21d": 0.51, "exp_return": 0.002, "downside_5pct": -0.19},
                      {"p_up_21d": 0.50, "exp_return": 0.001, "downside_5pct": -0.20})
    check("a one-point move in the right direction counts",
          g["p_up_moves_correctly"] is True and abs(g["d_p_up"] - 0.01) < 1e-9)


def test_a_backwards_forecast_fails_every_leg():
    item = {"pair_id": "P", "family": "fda", "is_canary": False}
    g = B2.grade_pair(item,
                      {"p_up_21d": 0.20, "exp_return": -0.05, "downside_5pct": -0.40},
                      {"p_up_21d": 0.80, "exp_return": 0.06, "downside_5pct": -0.10})
    check("a backwards forecast fails p_up, exp_return and downside",
          g["p_up_moves_correctly"] is False
          and g["exp_return_moves_correctly"] is False
          and g["downside_moves_correctly"] is False
          and g["all_three_agree"] is False)


def test_the_canary_fires_only_above_its_tolerance():
    item = {"pair_id": "C", "family": "canary_irrelevant", "is_canary": True}
    small = B2.grade_pair(item, {"p_up_21d": 0.52}, {"p_up_21d": 0.50})
    big = B2.grade_pair(item, {"p_up_21d": 0.62}, {"p_up_21d": 0.50})
    check("a canary within tolerance does not fire", small["canary_moved"] is False)
    check("a canary above tolerance fires", big["canary_moved"] is True)


def test_a_missing_number_is_None_and_never_a_zero():
    """A refused or malformed field must not silently grade as 'did not move'."""
    item = {"pair_id": "P", "family": "fda", "is_canary": False}
    g = B2.grade_pair(item, {"p_up_21d": None}, {"p_up_21d": 0.5})
    check("an absent p_up grades None, not False",
          g["d_p_up"] is None and g["p_up_moves_correctly"] is None)
    s = B2.summarise([g])
    check("a pair with no comparable number is EXCLUDED from the share",
          s["pairs_graded"] == 0 and s["monotonicity_share_p_up"] is None)


def test_the_summary_arithmetic_is_what_it_says():
    item = {"pair_id": "P", "family": "fda", "is_canary": False}
    rows = [B2.grade_pair(item, {"p_up_21d": p}, {"p_up_21d": 0.50})
            for p in (0.60, 0.70, 0.40, 0.45)]
    s = B2.summarise(rows)
    check("2 of 4 correct reads 0.5", s["monotonicity_share_p_up"] == 0.5,
          str(s["monotonicity_share_p_up"]))
    check("mean |d p_up| over (0.10, 0.20, 0.10, 0.05) is 0.1125",
          abs(s["mean_abs_move_p_up"] - 0.1125) < 1e-9,
          str(s["mean_abs_move_p_up"]))
    check("the mean SIGNED move is reported separately and is 0.0375",
          abs(s["mean_signed_move_p_up"] - 0.0375) < 1e-9,
          str(s["mean_signed_move_p_up"]))


def test_the_prompt_carries_no_numeric_bound():
    """S28: a bound the model can see is an anchor. Units are not bounds."""
    import re
    hits = re.findall(r"\d", B2._SYSTEM)
    # "21" appears twice (the horizon) and "5" once (the 5th percentile); those
    # name WHAT is being estimated, not how large the answer may be.
    banned = ("at most", "no more than", "between 0", "range", "maximum",
              "minimum", "cap ", "limit")
    check("the system prompt states no limit on the size of the answer",
          not any(w in B2._SYSTEM.lower() for w in banned),
          B2._SYSTEM[:120])
    check("the only digits in the prompt are the horizon and the percentile",
          set(hits) <= {"2", "1", "5"}, "".join(hits))


def test_the_justification_passes_the_spend_gate():
    """The gate is real and this exam's reason clears it -- checked here rather
    than discovered at the first paid call."""
    try:
        SPEND.justify(B2.WHY_THIS_CALL_CAN_CHANGE_A_DECISION, caller="labor_b2")
        ok = True
    except SPEND.SpendRefusal as e:                             # noqa: BLE001
        ok, detail = False, str(e)[:120]
    check("WHY_THIS_CALL_CAN_CHANGE_A_DECISION clears alpha.spend.justify", ok,
          "" if ok else detail)
    refused = False
    try:
        SPEND.justify("research", caller="labor_b2")
    except SPEND.SpendRefusal:
        refused = True
    check("a label instead of a reason is still refused", refused)


def test_the_dry_run_spends_nothing_and_still_grades():
    rec = B2.run(n_pairs=3, n_canaries=1, cap_usd=5.0, dry_run=True)
    check("the dry run makes no paid call", rec["spend"]["usd_from_tokens"] == 0.0)
    check("the dry run still grades every pair",
          rec["summary"]["pairs_graded"] == 3, str(rec["summary"]))
    check("the stub, which reads one word, scores 1.0 -- so the arithmetic is "
          "not what a low share would mean",
          rec["summary"]["monotonicity_share_p_up"] == 1.0)


def main() -> int:
    print("tests_smoke_labor_fantasy")
    for fn in (test_the_two_legs_differ_by_exactly_one_fact,
               test_the_exam_is_deterministic_and_the_entity_map_is_sealed,
               test_the_leg_order_is_shuffled,
               test_monotonicity_is_a_direction_not_a_magnitude,
               test_a_backwards_forecast_fails_every_leg,
               test_the_canary_fires_only_above_its_tolerance,
               test_a_missing_number_is_None_and_never_a_zero,
               test_the_summary_arithmetic_is_what_it_says,
               test_the_prompt_carries_no_numeric_bound,
               test_the_justification_passes_the_spend_gate,
               test_the_dry_run_spends_nothing_and_still_grades):
        fn()
    if FAILED:
        print(f"\nFAILED: {FAILED}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
