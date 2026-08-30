"""The logic brain's guards -- the ones that make it an adjuster, not a picker.

Every test here is about something the PROMPT asks for and the CODE enforces.
That distinction is the whole design: a prompt is a request to a model that is
free to decline, and three of these guards exist because a model did.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alpha import logic_brain as LB  # noqa: E402

RULE = {"p_up_21d": 0.50, "exp_return": 0.01, "downside_5pct": -0.20, "confidence": 0.4}
FACTS = [{"fact_id": "F1", "uid": "u1", "effective_at": "2026-08-29",
          "event_type": "earnings", "expectation": "beat", "source": "benzinga"}]


def test_no_named_fact_means_no_move():
    """The rule the whole design rests on. A model always has an opinion; an
    opinion with no named cause cannot be graded, improved or refused."""
    ans = {"p_up_21d": 0.72, "exp_return": 0.09, "downside_5pct": -0.05,
           "confidence": 0.9, "fact_id": LB.NO_FACT, "reason": "feels strong"}
    out, notes = LB.bound(ans, RULE, FACTS)
    assert out["p_up_21d"] == RULE["p_up_21d"]
    assert out["adjustment"] == 0.0
    assert any("without naming a fact" in n for n in notes)


def test_a_fact_that_was_never_supplied_is_not_a_fact():
    """Checked against what was SUPPLIED, in code. Asked in the prompt only,
    this is the single easiest instruction in the file for a model to ignore."""
    ans = {"p_up_21d": 0.60, "exp_return": 0.02, "downside_5pct": -0.20,
           "confidence": 0.5, "fact_id": "F9", "reason": "the merger"}
    out, notes = LB.bound(ans, RULE, FACTS)
    assert out["fact_id"] == LB.NO_FACT
    assert out["p_up_21d"] == RULE["p_up_21d"]
    assert any("not supplied" in n for n in notes)


def test_the_adjustment_is_clipped_and_the_clip_is_counted():
    ans = {"p_up_21d": 0.95, "exp_return": 0.01, "downside_5pct": -0.20,
           "confidence": 0.5, "fact_id": "F1", "reason": "huge beat"}
    out, notes = LB.bound(ans, RULE, FACTS)
    assert abs(out["adjustment"] - LB.MAX_ADJUSTMENT) < 1e-9
    assert out["clipped"] is True
    assert any("clipped" in n for n in notes)


def test_the_cap_is_never_shown_to_the_model():
    """MEASURED 2026-08-30, and it inverted the result.

    With `at most +/-0.10` in the prompt, ELEVEN of thirteen adjustments came
    back at exactly 0.100 -- the model returned the bound, i.e. a sign wearing a
    magnitude's clothes. With the same cap enforced in code and absent from the
    prompt, the same 16 names produced 4 adjustments averaging 0.024. A bound
    the model can see is an anchor; a bound only the code applies is a bound.
    """
    prompt = LB.build_user_prompt({"symbol": "X"}, RULE, FACTS)
    assert "0.10" not in prompt
    assert str(LB.MAX_ADJUSTMENT) not in prompt
    assert "clipped" not in prompt.lower()


def test_the_downside_may_never_shrink():
    """The bad case is what the position size is built on, and a model that
    talks itself into a smaller one has done the thing this project has been
    burned by most often."""
    ans = {"p_up_21d": 0.55, "exp_return": 0.01, "downside_5pct": -0.02,
           "confidence": 0.5, "fact_id": "F1", "reason": "beat"}
    out, notes = LB.bound(ans, RULE, FACTS)
    assert out["downside_5pct"] == RULE["downside_5pct"]
    assert any("shrink the downside" in n for n in notes)


def test_exp_return_is_bounded_against_the_names_own_bad_case():
    """A fixed percentage cap means one thing for a utility and another for a
    clinical-stage biotech, so the bound is relative to the name's downside."""
    ans = {"p_up_21d": 0.52, "exp_return": 0.90, "downside_5pct": -0.20,
           "confidence": 0.5, "fact_id": "F1", "reason": "beat"}
    out, notes = LB.bound(ans, RULE, FACTS)
    cap = abs(RULE["downside_5pct"]) * LB.MAX_EXP_RETURN_SHIFT_VS_DOWNSIDE
    assert abs(out["exp_return"] - (RULE["exp_return"] + cap)) < 1e-9
    assert any("exp_return moved" in n for n in notes)


def test_a_numeric_string_is_parsed_and_junk_is_not():
    """'0.55' has exactly one reading, so parsing it is not repairing it. On the
    first live run three rows read 'p_up unreadable' and reverted to the rule
    because the model answered with strings."""
    ans = {"p_up_21d": "0.55", "exp_return": "0.02", "downside_5pct": "-0.20",
           "confidence": "0.6", "fact_id": "F1", "reason": "beat"}
    out, _ = LB.bound(ans, RULE, FACTS)
    assert abs(out["p_up_21d"] - 0.55) < 1e-9

    junk = dict(ans, p_up_21d="quite likely")
    out2, notes2 = LB.bound(junk, RULE, FACTS)
    assert out2["p_up_21d"] == RULE["p_up_21d"]
    assert any("unreadable" in n for n in notes2)


def test_a_missing_rule_number_is_not_an_invitation_to_invent_one():
    ans = {"p_up_21d": 0.70, "exp_return": 0.02, "downside_5pct": -0.20,
           "confidence": 0.5, "fact_id": "F1", "reason": "beat"}
    out, notes = LB.bound(ans, dict(RULE, p_up_21d=None), FACTS)
    assert out["p_up_21d"] is None
    assert out["adjustment"] == 0.0
    assert any("unreadable" in n for n in notes)


def test_facts_are_filtered_to_subject_and_new_and_bounded_both_ways():
    labels = [
        {"symbol": "X", "role": "subject", "is_new_fact": True,
         "effective_at": "2026-08-29", "uid": "keep"},
        {"symbol": "X", "role": "mentioned", "is_new_fact": True,
         "effective_at": "2026-08-29", "uid": "listicle"},
        {"symbol": "X", "role": "subject", "is_new_fact": False,
         "effective_at": "2026-08-29", "uid": "recap"},
        {"symbol": "X", "role": "subject", "is_new_fact": True,
         "effective_at": "2026-07-01", "uid": "too_old"},
        {"symbol": "X", "role": "subject", "is_new_fact": True,
         "effective_at": "2026-09-05", "uid": "the_future"},
        {"symbol": "Y", "role": "subject", "is_new_fact": True,
         "effective_at": "2026-08-29", "uid": "other_company"},
    ]
    got = LB.facts_for(labels, "X", as_of="2026-08-30", lookback_days=10)
    assert [f["uid"] for f in got] == ["keep"]
    assert got[0]["fact_id"] == "F1"


def test_the_grade_compares_the_brain_to_the_rule_not_to_zero():
    """'Better than WHAT'. And only on the names it actually moved: on the rest
    the two forecasts are identical by construction, and including them would
    pull any real difference towards zero."""
    rows = [
        {"symbol": "UP", "fact_id": "F1", "adjustment": 0.05,
         "p_up_21d": 0.55, "rule_p_up_21d": 0.50},
        {"symbol": "DOWN", "fact_id": "F1", "adjustment": -0.05,
         "p_up_21d": 0.45, "rule_p_up_21d": 0.50},
        {"symbol": "UNTOUCHED", "fact_id": LB.NO_FACT, "adjustment": 0.0,
         "p_up_21d": 0.50, "rule_p_up_21d": 0.50},
    ]
    g = LB.grade(rows, {"UP": 0.03, "DOWN": -0.04, "UNTOUCHED": 0.10})
    assert g["n"] == 2, "the untouched name must not be graded"
    assert g["verdict"] == "BRAIN BETTER"
    assert g["adjustment_direction_right"] == 1.0
    assert g["brier_brain"] < g["brier_rule"]


def test_a_grade_with_nothing_resolved_refuses_rather_than_returning_a_tie():
    g = LB.grade([{"symbol": "A", "fact_id": LB.NO_FACT, "adjustment": 0.0,
                   "p_up_21d": 0.5, "rule_p_up_21d": 0.5}], {})
    assert g["verdict"] == "NOT GRADEABLE"


def test_run_summary_shows_the_two_numbers_that_discredit_a_run():
    """A brain that adjusts nothing is paying to say nothing; a brain that sits
    at the cap is being held back by it. Both are findings, not nuisances."""
    rows = [{"fact_id": "F1", "adjustment": LB.MAX_ADJUSTMENT, "clipped": True},
            {"fact_id": "F1", "adjustment": 0.02, "clipped": False},
            {"fact_id": LB.NO_FACT, "adjustment": 0.0, "clipped": False}]
    s = LB.run_summary(rows)
    assert s["n_adjusted"] == 2 and s["n_unchanged_no_fact"] == 1
    assert s["n_clipped"] == 1
    assert s["at_the_cap"] == 1
    assert s["share_adjusted_up"] == 1.0


def _run_all() -> int:
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    fails = []
    for name, fn in fns:
        try:
            fn()
        except Exception as e:                                          # noqa: BLE001
            fails.append(name)
            print(f"  FAIL {name}: {type(e).__name__}: {e}")
        else:
            print(f"  ok   {name}")
    print(f"\n{len(fails)} failures" + (f": {', '.join(fails)}" if fails else ""))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
