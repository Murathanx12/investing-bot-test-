"""T13's guards. The rewrite is only a test if these hold.

Every one of these is a way the fantasy transposition could look like it worked
while measuring something else -- a leaked ticker, a changed number, a rewriter
that supplies its own variation, a ranking that has found the calendar.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alpha import transpose as TP  # noqa: E402


def test_the_map_is_deterministic_and_hashed():
    """A map rebuilt from the same era and seed must be byte-identical, or a
    lost file cannot be recovered and two machines silently disagree about
    which fantasy company was which."""
    a = TP.build_entity_map(["MU", "NVDA", "AARD"], ["Semis", "Semis", "Bio"], era="2025-06")
    b = TP.build_entity_map(["AARD", "NVDA", "MU"], ["Bio", "Semis", "Semis"], era="2025-06")
    assert a["companies"] == b["companies"]
    assert a["sha256"] == b["sha256"]
    c = TP.build_entity_map(["MU", "NVDA", "AARD"], ["Semis", "Semis", "Bio"], era="2026-06")
    assert c["companies"] != a["companies"], "a different era must give a different world"


def test_one_real_company_gets_one_fantasy_name_and_they_do_not_collide():
    """The decider has to be able to follow a company across windows, which it
    can only do if the mapping is stable and injective."""
    syms = [f"S{i}" for i in range(60)]
    m = TP.build_entity_map(syms, ["x"] * 60, era="2025-06")
    names = list(m["companies"].values())
    assert len(set(names)) == len(names), "two real companies got the same fantasy name"


def test_the_year_moves_far_enough_to_be_unrecognisable():
    m = TP.build_entity_map(["MU"], ["Semis"], era="2016-01")
    assert m["year_offset"] >= 20


def test_magnitudes_are_compared_as_a_multiset_both_ways():
    src = "Revenue fell 18% to $4.2bn; the third guidance cut. Rating 4.6 of 5."
    good = "Output fell 18% to $4.2bn; the third supply cut. Standing 4.6 of 5."
    assert TP.magnitudes_preserved(src, good)["ok"]

    dropped = "Output fell to $4.2bn after another cut. Standing 4.6 of 5."
    r = TP.magnitudes_preserved(src, dropped)
    assert not r["ok"] and r["n_dropped"] >= 1

    # An ADDED number is the worse failure: the decider would be reading a fact
    # that never happened.
    added = dropped_plus = good + " Margin 31%."
    r2 = TP.magnitudes_preserved(src, added)
    assert not r2["ok"] and "31%" in r2["added"]
    assert dropped_plus


def test_years_are_not_counted_as_magnitudes():
    """The whole point of the rewrite is to change the year, so counting years
    as magnitudes would fail every good rewrite and pass none."""
    src = "In 2016 revenue fell 18%."
    out = "In 2051 output fell 18%."
    assert TP.magnitudes_preserved(src, out)["ok"]
    assert "2016" not in "".join(TP.numbers_in(src))


def test_a_month_abbreviation_inside_a_word_does_not_eat_a_magnitude():
    """Both bugs the date-stripper shipped with, pinned.

    (1) `[2025-10-27]` matched the number pattern as `-10` and `-27`, so a
        correct rewrite to `[2051-11-17]` read as three magnitudes dropped and
        three invented -- and the windows with the most dated items failed most.
    (2) Fixing that with `(?:Jan|Feb|Mar|...)[a-z]*` made "Mar" match inside
        "Margin", so "Margin 31%" was stripped as a date and a real magnitude
        vanished from one side of the comparison.
    """
    assert TP.numbers_in("[2025-10-27] fell 18%") == ["18%"]
    assert "31%" in TP.numbers_in("Margin 31% on Dec. 13")
    assert TP.numbers_in("Margin 31% on Dec. 13") == ["31%"]
    assert TP.numbers_in("effective 13 December, up 4%") == ["4%"]
    src = "[2025-10-27] guidance cut, margin 31%, effective Dec. 13"
    out = "[2051-11-17] guidance cut, margin 31%, effective Nov. 30"
    assert TP.magnitudes_preserved(src, out)["ok"]


def test_a_leaked_ticker_or_year_fails_the_rewrite():
    src = "MU guided lower in 2016."
    assert not TP.leak_check("Vantor Systems guided lower in 2016.",
                             real_symbols=["MU"], real_years=TP.years_in(src))["clean"]
    assert not TP.leak_check("MU guided lower in 2051.",
                             real_symbols=["MU"], real_years=TP.years_in(src))["clean"]
    assert TP.leak_check("Vantor Systems guided lower in 2051.",
                         real_symbols=["MU"], real_years=TP.years_in(src))["clean"]


def test_ranking_is_code_and_a_missing_number_ranks_last():
    ds = [
        {"key": "A", "p_up_21d": 0.6, "exp_return": 0.05, "downside_5pct": -0.10},
        {"key": "B", "p_up_21d": 0.6, "exp_return": 0.05, "downside_5pct": -0.40},
        {"key": "C", "p_up_21d": 0.9, "exp_return": None, "downside_5pct": -0.01},
    ]
    top = TP.rank(ds, personality="balanced", k=3)
    assert [d["key"] for d in top] == ["A", "B"], "C has no exp_return and must not rank"

    # aggressive does NOT subtract the bad case, and is meant not to.
    agg = TP.rank(ds, personality="aggressive", k=3)
    assert [d["key"] for d in agg] == ["A", "B"]
    assert agg[0]["rank_value"] == 0.6 * 0.05


def test_calibration_is_reported_against_climatology_not_against_zero():
    """A Brier score with nothing beside it is unreadable. The benchmark a
    probability has to beat is always-predict-the-base-rate."""
    ds = [{"key": "A", "p_up_21d": 0.9}, {"key": "B", "p_up_21d": 0.9},
          {"key": "C", "p_up_21d": 0.1}, {"key": "D", "p_up_21d": 0.1}]
    good = TP.calibration(ds, {"A": 0.05, "B": 0.05, "C": -0.05, "D": -0.05})
    assert good["skill_vs_climatology"] > 0

    flipped = TP.calibration(ds, {"A": -0.05, "B": -0.05, "C": 0.05, "D": 0.05})
    assert flipped["skill_vs_climatology"] < 0, "confident and wrong must score worse"
    assert good["base_rate"] == 0.5 and flipped["base_rate"] == 0.5


def test_wealth_compounds_by_date_and_refuses_an_empty_set():
    picks = {"2025-07-01": [{"key": "A"}], "2025-08-01": [{"key": "B"}]}
    w = TP.wealth(picks, {"A": 0.10, "B": 0.10})
    assert abs(w["terminal_wealth"] - 1.21) < 1e-9
    assert w["n_dates"] == 2
    assert TP.wealth({}, {})["verdict"] == "NOT GRADEABLE"


def test_parity_calls_a_rewriter_that_supplies_the_variation_a_leak():
    """If two rewrites of ONE window disagree as much as different windows do,
    the arm is measuring the rewriter and the grid should not be paid for."""
    keys = [f"K{i}" for i in range(10)]
    stable_a = [{"key": k, "p_up_21d": 0.30 + 0.04 * i} for i, k in enumerate(keys)]
    stable_b = [{"key": k, "p_up_21d": 0.30 + 0.04 * i + 0.005} for i, k in enumerate(keys)]
    assert TP.parity(stable_a, stable_b)["verdict"] == "OK"

    noisy_b = [{"key": k, "p_up_21d": 0.30 + 0.04 * ((i + 5) % 10)}
               for i, k in enumerate(keys)]
    assert TP.parity(stable_a, noisy_b)["verdict"] == "REWRITER_LEAK"

    assert TP.parity(stable_a[:2], stable_b[:2])["verdict"] == "NOT GRADEABLE"


def test_the_shuffled_null_keeps_the_outcomes_and_moves_only_who_gets_them():
    ds = [{"key": k} for k in ("A", "B", "C", "D", "E", "F")]
    out = {"A": 0.1, "B": -0.2, "C": 0.3, "D": -0.4, "E": 0.5, "F": -0.6}
    null = TP.shuffled_null(ds, out)
    assert sorted(null.values()) == sorted(out.values()), "an outcome was invented or lost"
    assert null != out, "nothing was shuffled"


def test_the_decider_schema_has_no_abstain():
    """'I don't know' is retired. A refusal field would let the model decline
    exactly the hard names the exercise exists to test."""
    assert "abstain" not in TP.DECIDER_KEYS
    assert "refuse" not in " ".join(TP.DECIDER_KEYS)
    assert "p_up_21d" in TP.DECIDER_KEYS and "confidence" in TP.DECIDER_KEYS


def test_the_decide_prompt_asks_for_probabilities_and_forbids_refusal():
    from scripts import era_replay as ER
    s = ER.DECIDE_SYSTEM.lower()
    assert "probability" in s
    assert "abstain" in s or "refus" in s
    assert "0.5" in s, "the prompt must say HOW to express uncertainty, not just ban refusal"


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
