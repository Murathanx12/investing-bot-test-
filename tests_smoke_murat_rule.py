"""MURAT_RULE_V1 -- the clause logic, the no-abstain contract, and the two clocks.

Run: python tests_smoke_murat_rule.py  (also executed by tests_smoke.py)

What these pin, and why each one was worth a test:

  * AN UNREADABLE CLAUSE IS NOT A FAILED CLAUSE. If a missing analyst rating
    collapsed to False, a name nobody covers would be indistinguishable from a
    name analysts dislike, and `rule_variant` -- the only thing that lets a
    grade say WHICH clause was wrong -- would be meaningless.
  * p_up = 0.5 GIVES EXACTLY ZERO EXPECTED RETURN. `exp_return` is algebraic,
    not assigned, so no edge can enter through the magnitude term while nobody
    is looking at the probability.
  * NO ROW ABSTAINS. Murat's 2026-08-30 instruction: every name returns
    numbers, and uncertainty is p_up near 0.5 at low confidence.
  * TWO CLOCKS, TWO BOUNDS. `days_to_next_catalyst` was None for every name in
    the book because the price context is cut at the last CLOSED session while
    the catalyst calendar is pulled TODAY -- one shared bound deleted every
    forward row. The default must stay `day` (a backtest that saw today's
    calendar in a 2025 row would be lookahead), so the fix is a bound a caller
    asks for by name.
"""
from __future__ import annotations

import os

# NOTE: this suite deliberately does not set the venue-block environment
# variable. `run_tests.py` owns it, and `tests_smoke_test_isolation` fails if any
# other suite so much as names it -- a blunt substring check, and correctly so:
# the block works by that variable reaching child processes, and a suite that set
# it locally would still pass on a day the runner had stopped setting it. Nothing
# here makes a network call anyway; the rule, the scoring and `daily_features`
# are all pure over their arguments.
os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import murat_rule as mr  # noqa: E402
from alpha.sources import features  # noqa: E402

FIRES = {"target_ratio": 1.8, "rating_counts_mean": 4.3,
         "days_to_next_catalyst": 10, "drawdown_from_60d_high": -0.30,
         "realised_vol_20d": 0.50}

print("\n-- the four clauses")
v = mr.evaluate(FIRES)
check("all four true -> fires", v["fires"] and v["rule_variant"] == "a_b_d_e", str(v["clauses"]))

for field, bad, clause in (("target_ratio", 1.49, "a_target_ratio"),
                           ("rating_counts_mean", 4.09, "b_rating"),
                           ("days_to_next_catalyst", 31, "d_catalyst"),
                           ("drawdown_from_60d_high", -0.149, "e_drawdown")):
    v = mr.evaluate({**FIRES, field: bad})
    check(f"{clause} just below its threshold blocks the claim",
          not v["fires"] and clause in v["failed_clauses"], f"{field}={bad}")

print("\n-- an UNREADABLE clause is not a FAILED clause")
v = mr.evaluate({**FIRES, "rating_counts_mean": None})
check("missing rating still fires, as variant a_d_e",
      v["fires"] and v["rule_variant"] == "a_d_e", str(v["rule_variant"]))
check("missing rating is 'unreadable', never 'failed'",
      "b_rating" in v["unreadable_clauses"] and "b_rating" not in v["failed_clauses"])
check("clause verdict is None, not False", v["clauses"]["b_rating"] is None)
v = mr.evaluate({**FIRES, "days_to_next_catalyst": None})
check("a REQUIRED clause that cannot be read blocks the claim",
      not v["fires"] and "d_catalyst" in v["unreadable_clauses"])

print("\n-- the calendar-day / session conversion is explicit")
check("21 sessions is carried as 30 calendar days",
      mr.CATALYST_MAX_SESSIONS == 21 and mr.CATALYST_MAX_CALENDAR_DAYS == 30)
check("a catalyst at exactly 30 calendar days still counts",
      mr.evaluate({**FIRES, "days_to_next_catalyst": 30})["fires"])

print("\n-- no row abstains, and every number names its basis")
prior = {"p_up_uncond": {"p_up": 0.46, "n": 34180, "n_blocks": 11},
         "p_up_rule": {"p_up": 0.55, "n": 3894, "n_blocks": 11}}
s = mr.score(FIRES, mr.evaluate(FIRES), prior)
for k in ("p_up_21d", "exp_return", "downside_5pct", "confidence"):
    check(f"{k} is present and numeric", isinstance(s.get(k), (int, float)), str(s.get(k)))
for k in ("p_up_basis", "exp_return_basis", "downside_basis", "confidence_basis",
          "claimed_abs_move_basis"):
    check(f"{k} explains where the number came from", bool(s.get(k)))
check("a firing row uses the RULE base rate", s["p_up_21d"] == 0.55, str(s["p_up_21d"]))
s_no = mr.score(FIRES, mr.evaluate({**FIRES, "target_ratio": 1.0}), prior)
check("a non-firing row uses the UNCONDITIONAL base rate", s_no["p_up_21d"] == 0.46)
check("a non-firing row still publishes every number",
      all(s_no.get(k) is not None for k in ("p_up_21d", "exp_return", "downside_5pct")))

print("\n-- exp_return is algebraic: p_up = 0.5 means exactly zero")
flat = mr.score(FIRES, mr.evaluate(FIRES),
                {"p_up_uncond": {"p_up": 0.5, "n": 1, "n_blocks": 11},
                 "p_up_rule": {"p_up": 0.5, "n": 1, "n_blocks": 11}})
check("p_up 0.5 -> exp_return 0.0", flat["exp_return"] == 0.0, str(flat["exp_return"]))
check("but the claimed move is still published", flat["claimed_abs_move"] is not None)

print("\n-- the claimed move is capped however volatile the name is")
wild = mr.score({**FIRES, "realised_vol_20d": 4.0}, mr.evaluate(FIRES), prior)
check("a 400% vol name still claims at most the cap",
      wild["claimed_abs_move"] == mr.CLAIM_ABS_MOVE_CAP, str(wild["claimed_abs_move"]))

print("\n-- an absent base rate is labelled ignorance, not forecast")
none_prior = {"p_up_uncond": {"p_up": None, "n": 0, "n_blocks": 0},
              "p_up_rule": {"p_up": None, "n": 0, "n_blocks": 0}}
sn = mr.score(FIRES, mr.evaluate(FIRES), none_prior)
check("p_up falls back to 0.5", sn["p_up_21d"] == 0.5)
check("and says so", "NO MEASURABLE BASE RATE" in sn["p_up_basis"])

print("\n-- confidence scales with readable clauses AND date blocks")
thin = mr.score(FIRES, mr.evaluate(FIRES),
                {"p_up_uncond": {"p_up": 0.46, "n": 10, "n_blocks": 1},
                 "p_up_rule": {"p_up": 0.55, "n": 10, "n_blocks": 1}})
check("one date block behind the rate -> low confidence",
      thin["confidence"] < s["confidence"], f"{thin['confidence']} < {s['confidence']}")
partial = mr.score(FIRES, mr.evaluate({**FIRES, "rating_counts_mean": None}), prior)
check("a clause we could not read -> lower confidence",
      partial["confidence"] < s["confidence"], f"{partial['confidence']} < {s['confidence']}")

print("\n-- the rank expression is code, and an unmeasured row cannot outrank a measured one")
good = {"exp_return": 0.02, "downside_5pct": -0.10}
bad = {"exp_return": -0.05, "downside_5pct": -0.10}
missing = {"exp_return": None, "downside_5pct": None}
check("exp_return - lam*|downside|", abs(mr.rank_key(good) - (0.02 - 0.10)) < 1e-12)
check("lam scales the risk term", mr.rank_key(good, lam=0.25) > mr.rank_key(good, lam=1.0))
check("a measured loser still outranks an unmeasured name",
      mr.rank_key(bad) > mr.rank_key(missing))

print("\n-- the base rate reports which clauses it actually stands on")
rows = {"AAA": [{"day": "2025-03-03", "target_ratio": 2.0, "drawdown_from_60d_high": -0.30},
                {"day": "2025-04-03", "target_ratio": 1.0, "drawdown_from_60d_high": -0.30}],
        "BBB": [{"day": "2025-05-05", "target_ratio": 2.0, "drawdown_from_60d_high": -0.30}]}
fwd = {"AAA": {"2025-03-03": 0.10, "2025-04-03": -0.10}, "BBB": {"2025-05-05": -0.05}}
pr = mr.prior_from_panel(rows, fwd)
check("unconditional counts every row with a forward return", pr["p_up_uncond"]["n"] == 3)
check("the rule cell counts only rows where (a) and (e) hold", pr["p_up_rule"]["n"] == 2)
check("rule p_up is measured, not assumed", pr["p_up_rule"]["p_up"] == 0.5)
check("it names the clauses it could NOT measure",
      pr["clauses_not_measured"] == ["b_rating", "d_catalyst"])
check("and flags itself in-sample", pr["in_sample"] is True)
check("n_blocks counts DATE BLOCKS, not rows", pr["p_up_uncond"]["n_blocks"] == 3)

print("\n-- calibration: a hit rate alone cannot catch confident-and-wrong")
conf_wrong = [{"p_up_21d": 0.9, "hit": h} for h in [True] * 11 + [False] * 9]
meek_right = [{"p_up_21d": 0.55, "hit": h} for h in [True] * 11 + [False] * 9]
b1, b2 = mr.brier(conf_wrong), mr.brier(meek_right)
check("same 55% hit rate, different Brier", b1["brier"] != b2["brier"], f"{b1['brier']} vs {b2['brier']}")
check("the confident-and-wrong one scores WORSE", b1["brier"] > b2["brier"])
check("a coin reference is carried", b1["reference_coin"] == 0.25)
tbl = mr.reliability_table(conf_wrong)
check("the reliability table shows the gap", tbl and abs(tbl[0]["gap"] - (0.55 - 0.9)) < 1e-9,
      str(tbl[0] if tbl else None))
check("empty input gives an empty table, not a crash", mr.reliability_table([]) == [])
check("brier on nothing refuses rather than returning 0", mr.brier([])["brier"] is None)

print("\n-- TWO CLOCKS: a forward row needs its own knowledge bound")
rows_pit = [
    {"observed_at": "2026-08-20T12:00:00Z", "tense": "past", "kind": "news",
     "title": "old news", "symbols": ["ZZZ"]},
    # pulled TODAY, dated in the future -- this is the catalyst diary
    {"observed_at": "2026-08-30T09:00:00Z", "tense": "future", "kind": "earnings",
     "title": "ZZZ earnings", "symbols": ["ZZZ"], "effective_at": "2026-09-21"},
]
bars = [{"t": f"2026-08-{d:02d}T00:00:00Z", "o": 10.0, "h": 10.5, "l": 9.5, "c": 10.0, "v": 1000}
        for d in range(1, 29)]
f_default = features.daily_features("ZZZ", "2026-08-28", rows_pit, bars=bars)
check("DEFAULT bound hides a calendar pulled after the last closed bar",
      f_default.get("days_to_next_catalyst") is None, str(f_default.get("days_to_next_catalyst")))
f_seal = features.daily_features("ZZZ", "2026-08-28", rows_pit, bars=bars,
                                 future_known_by="2026-08-30T09:15:00Z")
check("the seal-instant bound makes clause (d) readable",
      f_seal.get("days_to_next_catalyst") == 24, str(f_seal.get("days_to_next_catalyst")))
f_early = features.daily_features("ZZZ", "2026-08-28", rows_pit, bars=bars,
                                  future_known_by="2026-08-30T08:00:00Z")
check("a row observed AFTER the seal instant is still excluded",
      f_early.get("days_to_next_catalyst") is None)
check("the wider bound does not leak into BACKWARD counts",
      f_seal.get("n_items_20d") == f_default.get("n_items_20d"),
      f"{f_seal.get('n_items_20d')} vs {f_default.get('n_items_20d')}")

print("\n-- knowable_by accepts a day or an instant, and they differ")
day_rows = [{"observed_at": "2026-08-30T18:00:00Z"}]
check("a whole-day bound admits an 18:00 row",
      len(features.knowable_by(day_rows, "2026-08-30")) == 1)
check("a 09:15 instant bound does not",
      len(features.knowable_by(day_rows, "2026-08-30T09:15:00Z")) == 0)

print("\n-- the contract is frozen and self-describing")
for k in ("generator", "licence", "clauses", "falsifier", "no_abstain", "claim_size"):
    check(f"contract carries {k}", bool(mr.CONTRACT.get(k)))
check("the licence is PRODUCT_EXPERIMENT", mr.CONTRACT["licence"] == "PRODUCT_EXPERIMENT")
check("clause (c) is recorded as deliberately omitted", bool(mr.CONTRACT.get("clause_c_omitted")))
check("the contract has no 'abstain' anywhere",
      "abstain" not in repr(mr.CONTRACT).lower().replace("no_abstain", "").replace(
          "never a refusal", ""))

print("\n-- the BRAIN trades the seal, and declines loudly when there is none")
import json  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

from alpha.brains import murat_rule as brain  # noqa: E402

_tmp = Path(tempfile.mkdtemp())
_orig_books, _orig_seed = brain.BOOKS, brain.SEED_BOOKS
brain.BOOKS = _tmp / "empty"
brain.SEED_BOOKS = _tmp / "seed"
brain.SEED_BOOKS.mkdir(parents=True)

DAY = "2026-08-31"
try:
    brain.forecast(None, "MU", 5.0, day=DAY)
    check("no sealed book -> declines", False, "it produced a forecast")
except brain.RuleDeclined as exc:
    check("no sealed book -> declines rather than re-deriving",
          "no sealed book" in str(exc) and "re-deriving" in str(exc))

BOOK = {
    "day": DAY, "content_sha256": "deadbeef" * 8, "universe_considered": 2,
    "predictions": [
        {"symbol": "MU", "generator": "murat_rule_v1", "claims": True,
         "rule_variant": "a_b_d_e", "p_up_21d": 0.55, "exp_return": 0.011,
         "claimed_abs_move": 0.11, "downside_5pct": -0.18, "confidence": 0.9,
         "p_up_n": 3894, "p_up_n_blocks": 11, "p_up_basis": "panel base rate",
         "clauses": {}, "clause_inputs": {"target_ratio": 1.8,
                                          "days_to_next_catalyst": 10,
                                          "drawdown_from_60d_high": -0.3}},
        {"symbol": "ZZZ", "generator": "murat_rule_v1", "claims": False,
         "rule_variant": "a_d_e", "failed_clauses": ["e_drawdown"],
         "unreadable_clauses": ["b_rating"], "p_up_21d": 0.46,
         "exp_return": -0.004, "claimed_abs_move": 0.09, "downside_5pct": -0.15,
         "confidence": 0.4, "clauses": {}, "clause_inputs": {}},
    ],
}
(brain.SEED_BOOKS / f"{DAY}.json").write_text(json.dumps(BOOK), encoding="utf-8")

f = brain.forecast(None, "MU", 21 * 7 / 5, day=DAY)
check("reads the SEED dir when the ledger volume has nothing", f.symbol == "MU")
check("claim is DIRECTION, never distribution", f.claim == "direction", f.claim)
check("centre is the book's exp_return at full horizon", abs(f.centre - 0.011) < 1e-9, str(f.centre))
check("sd is the claimed move, not a vol guess", abs(f.sd - 0.11) < 1e-9, str(f.sd))
check("conviction is the book's confidence", abs(f.conviction - 0.9) < 1e-9)
check("the sealed hash travels onto the forecast",
      f.evidence["book_sha256"] == BOOK["content_sha256"])
check("the in-sample caveat travels with it", "IN-SAMPLE" in f.evidence["caveat"].upper())

half = brain.forecast(None, "MU", 21 * 7 / 5 / 2, day=DAY)
check("a shorter horizon SCALES the centre down, linearly",
      abs(half.centre - 0.011 * 0.5) < 1e-6, str(half.centre))
check("and the spread by sqrt, not linearly",
      abs(half.sd - 0.11 * (0.5 ** 0.5)) < 1e-6, str(half.sd))
check("so a 21-session centre is never reused at 5 sessions", half.centre < f.centre)

try:
    brain.forecast(None, "ZZZ", 5.0, day=DAY)
    check("a non-claiming name declines", False, "it produced a forecast")
except brain.RuleDeclined as exc:
    check("a non-claiming name declines WITH the blocking clause",
          "e_drawdown" in str(exc) and "b_rating" in str(exc), str(exc)[:90])

try:
    brain.forecast(None, "NOTINBOOK", 5.0, day=DAY)
    check("a name absent from the book declines", False, "it produced a forecast")
except brain.RuleDeclined as exc:
    check("a name absent from the book declines", "not in the sealed book" in str(exc))

bad = dict(BOOK)
bad["predictions"] = [{**BOOK["predictions"][0], "exp_return": None}]
(brain.SEED_BOOKS / f"{DAY}.json").write_text(json.dumps(bad), encoding="utf-8")
try:
    brain.forecast(None, "MU", 5.0, day=DAY)
    check("a claim with no numbers is refused", False, "it invented them")
except brain.RuleDeclined as exc:
    check("a claim carrying no numbers is refused, not filled in",
          "inventing" in str(exc), str(exc)[:80])

brain.BOOKS, brain.SEED_BOOKS = _orig_books, _orig_seed

print("\n-- the band prior: eleven years decide the SIGN, and $2 is a silence")
b_toxic = mr.score({**FIRES, "target_ratio": 6.0, "close": 10.0}, mr.evaluate({**FIRES, "target_ratio": 6.0}), prior)
check("+400%+ band at a readable price goes NEGATIVE (the S30b toxic cell)",
      b_toxic["exp_return"] is not None and b_toxic["exp_return"] < 0, str(b_toxic["exp_return"]))
check("and the basis names the receipt", "UPSIDE-BAND-DECON-1" in b_toxic["exp_return_basis"])
check("and the band travels on the row", b_toxic.get("upside_band") == "ratio 5..inf", str(b_toxic.get("upside_band")))
b_good = mr.score({**FIRES, "target_ratio": 4.0, "close": 10.0}, mr.evaluate({**FIRES, "target_ratio": 4.0}), prior)
check("+200..400% band goes POSITIVE at the measured monthly excess",
      abs(b_good["exp_return"] - 0.2070 / 12.0) < 1e-9, str(b_good["exp_return"]))
b_cheap = mr.score({**FIRES, "target_ratio": 4.0, "close": 1.50}, mr.evaluate({**FIRES, "target_ratio": 4.0}), prior)
check("under $2 the band prior says NOTHING (panel prior kept, basis says why)",
      "UNINFORMATIVE" in b_cheap["exp_return_basis"]
      and abs(b_cheap["exp_return"] - (2 * 0.55 - 1) * b_cheap["claimed_abs_move"]) < 1e-9,
      b_cheap["exp_return_basis"][:80])
b_none = mr.score({**FIRES, "close": 10.0}, mr.evaluate(FIRES), prior)
check("ratio 1.8 is outside every band: two-cell formula untouched",
      "claimed_abs_move" in b_none["exp_return_basis"] and b_none.get("upside_band") is None)


print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
raise SystemExit(1 if fails else 0)
