"""Smoke: the allocator cuts on risk, gates promotion on evidence, and prints the bill.

Every check here is a way the allocator could look reasonable while being
wrong, and each one is a line in `docs/TRIALS/TRIAL-DRAFT-ALLOCATOR-v0.md`:

  1. the cut fires at -5.01% and does NOT fire at -4.99%. A threshold nobody
     tested on both sides of is a threshold nobody has;
  2. the floor floors, the cooldown counts down, and a floored book is never
     set to zero -- zeroing it would end its series and destroy the exact
     counterfactual both twins depend on;
  3. the 35% ceiling binds and the water-fill still sums to one;
  4. a STALE record keeps yesterday's budget and SAYS SO; a missing record
     REFUSES. Neither ever returns a silent 100%;
  5. both twins are computed on the same clock, under the same kill scales and
     the same ceiling, so the comparison isolates the learning;
  6. the worst case in dollars is computed from `contract.worst_case`, printed
     before anything is written, and moves only with the budget;
  7. the LLM has no path in.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from alpha import allocator as A, contract as _c

fails = 0


def check(name, ok, detail=""):
    global fails
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        fails += 1


def curve(days_equities):
    return [{"day": d, "equity": float(e)} for d, e in days_equities]


ANCHOR = {"anchor_day": "2026-09-11", "contract_hash": A.contract_sha256(),
          "books": {r: {"anchor_equity": 100_000.0, "anchor_day": "2026-09-11"}
                    for r in A.ROLES}}


print("\n-- the frozen contract")
c = A.contract()
check("the ladder is the reported one", c["cut_halve"] == -0.05 and c["cut_floor"] == -0.075)
check("the floor is de minimis, never zero", c["floor_weight"] == 0.02 and c["floor_weight"] > 0)
check("cooldown 20 sessions, ceiling 35%", c["cooldown_sessions"] == 20 and c["ceiling"] == 0.35)
check("hack2 is NOT allocated to (lane D)", "hack2" not in A.ROLES and len(A.ROLES) == 5)
check("the contract hash is stable across calls", A.contract_sha256() == A.contract_sha256())
h0 = A.contract_sha256()
_old = A.CEILING
A.CEILING = 0.34
check("and it MOVES when a frozen number moves", A.contract_sha256() != h0)
A.CEILING = _old
check("...and comes back", A.contract_sha256() == h0)


print("\n-- the cut fires at -5.01% and not at -4.99%")
for dd, want in ((-0.0499, "ACTIVE"), (-0.0500, "HALVED"), (-0.0501, "HALVED"),
                 (-0.0749, "HALVED"), (-0.0750, "FLOOR"), (-0.0751, "FLOOR")):
    step = A.kill_step(dd, state="ACTIVE", cooldown_left=0)
    check(f"drawdown {dd:+.2%} -> {want}", step["state"] == want, step["state"])
check("the halve scale is exactly one half", A.kill_step(-0.06, state="ACTIVE", cooldown_left=0)["scale"] == 0.5)
check("the floor scale is the de-minimis weight",
      A.kill_step(-0.08, state="ACTIVE", cooldown_left=0)["scale"] == A.FLOOR_WEIGHT)
check("a fired rule says what it did, in numbers",
      "-5.0%" in A.kill_step(-0.06, state="ACTIVE", cooldown_left=0)["fired"])

print("\n-- the cooldown counts down and nothing re-arms inside it")
step = A.kill_step(-0.08, state="ACTIVE", cooldown_left=0)
check("floor sets the cooldown", step["cooldown_left"] == A.COOLDOWN_SESSIONS)
back = A.kill_step(+0.20, state="FLOOR", cooldown_left=step["cooldown_left"])
check("a huge gain inside the cooldown does NOT re-arm the book",
      back["state"] == "FLOOR" and back["scale"] == A.FLOOR_WEIGHT, str(back))
check("and the cooldown ticks", back["cooldown_left"] == A.COOLDOWN_SESSIONS - 1)
out = A.kill_step(-0.01, state="FLOOR", cooldown_left=0)
check("after the cooldown a recovered book can leave the floor", out["state"] == "ACTIVE")

print("\n-- a halved book recovers only on a new post-cut high, and a cut re-bases the peak")
rec = A.kill_step(-0.001, state="HALVED", cooldown_left=0)
check("HALVED -> ACTIVE on a new post-cut high", rec["state"] == "ACTIVE" and rec["scale"] == 1.0)
check("and it says so in the log", "restored" in (rec["fired"] or "").lower())
still = A.kill_step(-0.06, state="HALVED", cooldown_left=0)
check("a still-losing halved book is not cut twice", still["state"] == "HALVED" and still["fired"] is None)

print("\n-- an unmeasurable drawdown is CANNOT DETERMINE, not a pass and not a kill")
unk = A.kill_step(None, state="HALVED", cooldown_left=0)
check("no drawdown -> yesterday's state carried, said out loud",
      unk["state"] == "HALVED" and "CANNOT DETERMINE" in unk["why"], str(unk))
d = A.drawdown([], since="2026-09-11")
check("an empty curve refuses rather than reporting 0%", d["drawdown"] is None and "CANNOT DETERMINE" in d["status"])

print("\n-- the peak is measured from `since`, so a cut gives the book a fair recovery")
c5 = curve([("2026-09-11", 100_000), ("2026-09-12", 90_000), ("2026-09-13", 92_000)])
check("from the anchor: -8% off the 100k peak",
      abs(A.drawdown(c5, since="2026-09-11")["drawdown"] + 0.08) < 1e-9)
check("from the cut: +2.2% off the 90k peak, i.e. a new high",
      A.drawdown(c5, since="2026-09-12")["drawdown"] == 0.0,
      str(A.drawdown(c5, since="2026-09-12")))

print("\n-- the ceiling binds and the water-fill still sums to one")
w, bound = A.apply_ceiling({"a": 0.8, "b": 0.1, "c": 0.1})
check("no book above the ceiling", max(w.values()) <= A.CEILING + 1e-9, str(w))
check("weights still sum to 1", abs(sum(w.values()) - 1.0) < 1e-9, str(sum(w.values())))
check("the bound book is named", bound == {"a"}, str(bound))
w2, b2 = A.apply_ceiling({"a": 0.3, "b": 0.4, "c": 0.3})
check("a second book over the line is caught too", max(w2.values()) <= A.CEILING + 1e-9)
w3, b3 = A.apply_ceiling({"a": 0.34, "b": 0.33, "c": 0.33})
check("nothing under the line is touched", b3 == set() and abs(w3["a"] - 0.34) < 1e-9)

print("\n-- date blocks, not daily marks")
check("a block is the book's own declared minimum hold",
      A.block_sessions("hack3") == _c.HORIZON_REMAP["hack3"]["min_normal_hold_sessions"] == 21)
check("an incomplete block is not counted", A.blocks_of([0.01] * 20, 21) == [])
check("two complete blocks out of 43 marks", len(A.blocks_of([0.01] * 43, 21)) == 2)
check("the block mean is the mean", A.blocks_of([0.0, 0.02], 2) == [0.01])

print("\n-- the priors: zero complete blocks is zero evidence about a mean")
p3 = A.prior_for("hack3")
check("hack3 carries Book F's replay prior, 419 blocks",
      p3.status == "MEASURED" and p3.n_effective_blocks == 419)
check("and its centre is the measured monthly excess over 21 sessions",
      abs(p3.mean - 0.004328 / 21.0) < 1e-12, f"{p3.mean}")
check("and its spread is that cell's own standard error", p3.sd < p3.mean, f"{p3.sd}")
p4 = A.prior_for("hack4")
check("hack4's 10 sessions is less than one 42-session block -> centre ZERO",
      p4.mean == 0.0 and p4.sd == A.DAILY_SD and p4.n_effective_blocks == 0.0, str(p4))
check("and the observed number is REPORTED, not deleted",
      "+0.2375%" in p4.status or "0.2375" in p4.status, p4.status)
p5 = A.prior_for("hack5")
check("hack5's 2-session hold DOES clear five blocks, so it keeps its centre",
      p5.n_effective_blocks == 5.0 and p5.mean > 0, str(p5))
try:
    A.prior_for("nosuchbook")
    check("an undeclared book refuses rather than starting from ignorance", False)
except A.AllocatorUnavailable:
    check("an undeclared book refuses rather than starting from ignorance", True)

print("\n-- the Thompson step is Sharpe-shaped, and it says so")
posts = {"measured": {"mean": 0.000206, "sd": 0.000066},
         "unmeasured1": {"mean": 0.0, "sd": 0.015},
         "unmeasured2": {"mean": 0.0, "sd": 0.015},
         "unmeasured3": {"mean": 0.0, "sd": 0.015}}
d1 = A.thompson(posts, seed=20260911)
check("the reward is named on the output", "Sharpe-shaped" in d1["reward"])
check("the ONLY measured book gets the largest share",
      max(d1["weights"], key=d1["weights"].get) == "measured", json.dumps(d1["weights"]))
check("P(best) would have done the opposite, and is reported anyway",
      d1["p_best"]["measured"] < d1["weights"]["measured"],
      f"p_best {d1['p_best']['measured']:.3f} vs weight {d1['weights']['measured']:.3f}")
check("weights sum to one", abs(sum(d1["weights"].values()) - 1.0) < 1e-9)
check("the draw is reproducible from its seed",
      A.thompson(posts, seed=20260911)["weights"] == d1["weights"])
check("and a different day is a different draw",
      A.thompson(posts, seed=20260912)["weights"] != d1["weights"])

print("\n-- the posterior updates on blocks, and says when it has none")
pr = A.Prior(0.0, 0.015, 0.0, "s", "UNINFORMATIVE")
p0 = A.posterior(pr, [], 21)
check("no complete block -> PRIOR ONLY, and the prior is unchanged",
      p0["status"].startswith("PRIOR ONLY") and p0["mean"] == 0.0 and p0["sd"] == 0.015)
p1 = A.posterior(pr, [0.01, 0.01, 0.01], 21)
check("three positive blocks move the mean up and the sd down",
      p1["mean"] > 0 and p1["sd"] < 0.015 and p1["n_effective_date_blocks"] == 3, str(p1))

print("\n-- the twins are built with the allocator, on the same clock")
tw = A.twins(["a", "b", "c", "d"], seed=7)
check("equal weight is 1/N over the survivors", set(tw["equal_weight"].values()) == {0.25})
check("the random twin is a proper Dirichlet draw",
      abs(sum(tw["random_dirichlet"].values()) - 1.0) < 1e-9
      and all(v > 0 for v in tw["random_dirichlet"].values()))
check("the random twin is seeded, so it is reproducible",
      A.twins(["a", "b", "c", "d"], seed=7)["random_dirichlet"] == tw["random_dirichlet"])
check("a floored book leaves the survivor set", A.twins([], seed=7)["equal_weight"] == {})


print("\n-- a whole day: the cut fires, the twins carry the same kill scales, the bill is printed")
curves = {r: curve([("2026-09-11", 100_000), ("2026-09-12", 100_000)]) for r in A.ROLES}
curves["hack6"] = curve([("2026-09-11", 100_000), ("2026-09-12", 94_000)])   # -6%
curves["hack4"] = curve([("2026-09-11", 100_000), ("2026-09-12", 92_000)])   # -8%
rec = A.allocate("2026-09-12", curves=curves, anchor=ANCHOR)
check("hack6 halved at -6%", rec["per_book"]["hack6"]["kill_state_base"] == "HALVED")
check("hack4 floored at -8%", rec["per_book"]["hack4"]["kill_state_base"] == "FLOOR")
check("the floored book keeps a de-minimis weight, never zero",
      rec["per_book"]["hack4"]["allocator_weight"] == A.FLOOR_WEIGHT)
check("and so does its gross budget", rec["per_book"]["hack4"]["gross_budget_scale"] == A.FLOOR_WEIGHT)
check("the halved book's gross is halved", rec["per_book"]["hack6"]["gross_budget_scale"] == 0.5)
check("BOTH twins carry the same kill scales",
      rec["per_book"]["hack4"]["equal_weight_twin_weight"] == A.FLOOR_WEIGHT
      and rec["per_book"]["hack4"]["random_twin_weight"] == A.FLOOR_WEIGHT)
check("the freed capital is CASH, not a gift to the winners",
      any("cash_weight" in n for n in rec["notes"])
      and sum(rec["per_book"][r]["allocator_weight"] for r in A.ROLES) < 1.0,
      str(sum(rec["per_book"][r]["allocator_weight"] for r in A.ROLES)))
check("both kills are in the kill log with their drawdowns", len(rec["kill_log"]) == 2)
check("and in rule_fired, in words", len(rec["rule_fired"]) == 2)
check("the binding constraint is named per book",
      rec["per_book"]["hack4"]["binding_constraint"] == "kill:FLOOR"
      and rec["per_book"]["hack6"]["binding_constraint"] == "kill:HALVED")

print("\n-- the worst case in dollars, per book and fleet, recomputed not quoted")
want = sum(_c.worst_case(r)["worst_case_frac"] * rec["per_book"][r]["gross_budget_scale"]
           * rec["per_book"][r]["current_equity"] for r in A.ROLES)
check("the fleet worst case is the sum of the books'",
      abs(rec["worst_case_usd_fleet"] - want) < 0.02, f"{rec['worst_case_usd_fleet']} vs {want}")
check("a cut book's worst case falls with its budget",
      rec["per_book"]["hack4"]["worst_case_usd"]
      < 0.05 * _c.worst_case("hack4")["worst_case_frac"] * 92_000)
check("the fleet number is also a percentage of fleet equity",
      0 < rec["worst_case_pct_equity_fleet"] < 0.15, str(rec["worst_case_pct_equity_fleet"]))
check("every book names the fraction it used", all(
    rec["per_book"][r]["declared_worst_case_frac"] == _c.worst_case(r)["worst_case_frac"]
    for r in A.ROLES))

print("\n-- promotion on RETURN is gated on evidence; the drawdown rule is not")
check("no book has a complete date block on day two",
      all(rec["per_book"][r]["n_effective_date_blocks"] == 0 for r in A.ROLES))
check("so an ACTIVE book's gross is exactly its kill scale, and the row says why",
      rec["per_book"]["hack1"]["gross_budget_scale"] == 1.0
      and "complete date block" in rec["per_book"]["hack1"]["gross_budget_scale_why"],
      rec["per_book"]["hack1"]["gross_budget_scale_why"])
check("the pool weight is still computed and graded from session one",
      rec["per_book"]["hack1"]["allocator_weight"] > 0)
check("p_best is reported and explicitly not used",
      "thompson_p_best_REPORTED_NOT_USED" in rec["per_book"]["hack1"])

print("\n-- the verdict clock does not read early")
check("the clock says TOO EARLY and names the clause",
      rec["verdict_clock"]["status"] == "TOO EARLY"
      and "FAILED_VARIANT" in rec["verdict_clock"]["clause"])
check("60 sessions is the decision horizon", A.DECISION_SESSIONS == 60)
late = dict(rec["cumulative"]); late["sessions"] = 60
late["vs_equal_weight"], late["vs_random"] = -0.01, +0.01
vc = A._verdict_clock(late)
check("a negative read at 60 sessions is FAILED_VARIANT", vc["status"] == "FAILED_VARIANT")
check("and it names the SECOND test a null owes", "two tests" in vc["second_test_owed"])

print("\n-- the contract hash travels on the receipt")
check("every record carries it", rec["contract_hash"] == A.contract_sha256())
check("and the licence and the trial", rec["licence"] == "PRODUCT_EXPERIMENT"
      and rec["trial"] == "TRIAL-DRAFT-ALLOCATOR-v0")


print("\n-- what the loop reads: FRESH, STALE, or a refusal -- never a silent 100%")
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    old_state, old_seed = A.STATE, A.SEED_STATE
    A.STATE, A.SEED_STATE = root / "allocator", root / "seed"
    try:
        A.STATE.mkdir(parents=True)
        try:
            A.budget_for("hack3", day="2026-09-14")
            check("no record at all -> REFUSAL that names the fix", False)
        except A.AllocatorUnavailable as exc:
            check("no record at all -> REFUSAL that names the fix",
                  "--anchor" in str(exc) and "100%" in str(exc), str(exc)[:140])
        (A.STATE / "2026-09-12.json").write_text(json.dumps(rec), encoding="utf-8")
        b = A.budget_for("hack1", day="2026-09-12")
        check("today's record is FRESH", b["freshness"] == "FRESH" and b["scale"] == 1.0)
        st = A.budget_for("hack6", day="2026-09-16")
        check("an older record is STALE and the book KEEPS that budget",
              st["freshness"] == "STALE" and st["scale"] == 0.5, json.dumps(st))
        check("and the staleness is said, with both days",
              "2026-09-12" in st["note"] and "2026-09-16" in st["note"], st["note"])
        check("a stale allocator never re-arms a cut book", st["scale"] < 1.0)
        try:
            A.budget_for("hack2", day="2026-09-12")
            check("hack2 is refused by name (lane D), never given a default", False)
        except A.AllocatorUnavailable as exc:
            check("hack2 is refused by name (lane D), never given a default",
                  "lane D" in str(exc), str(exc)[:120])
    finally:
        A.STATE, A.SEED_STATE = old_state, old_seed


print("\n-- the fleet reads the budget through loop_args, and hack2 gets no flag")
from alpha import fleet

args3 = fleet.loop_args(fleet.FLEET["hack3"])
check("an allocated role carries --gross-scale", "--gross-scale" in args3, str(args3[:8]))
check("hack2 (lane D) carries none", "--gross-scale" not in fleet.loop_args(fleet.FLEET["hack2"]))
scale, why = fleet.gross_scale_for(fleet.FLEET["hack2"])
check("and says why", scale is None and "lane D" in why, why)
check("the flag comes BEFORE --universe, which must stay last",
      args3.index("--gross-scale") < args3.index("--universe"))

print("\n-- the gross scale binds where every consumer already reads")
from alpha.engine import sizing

_prev = os.environ.pop("AAT_GROSS_SCALE", None)
try:
    base = sizing.gross_cap("basket")
    os.environ["AAT_GROSS_SCALE"] = "0.5"
    check("the budget halves the cap", abs(sizing.gross_cap("basket") - base * 0.5) < 1e-12)
    os.environ["AAT_GROSS_SCALE"] = "4.0"
    check("it can never LEVER: >1 is clamped", sizing.gross_cap("basket") == base)
    os.environ["AAT_GROSS_SCALE"] = "not-a-number"
    check("a malformed value is 1.0, not a disarmed book", sizing.gross_cap("basket") == base)
    os.environ["AAT_GROSS_SCALE"] = "-3"
    check("a negative value floors at zero", sizing.gross_cap("basket") == 0.0)
finally:
    os.environ.pop("AAT_GROSS_SCALE", None)
    if _prev is not None:
        os.environ["AAT_GROSS_SCALE"] = _prev
check("and the unscaled cap is still <= 1.0 (tests_smoke_monday's pin)",
      all(sizing.gross_cap(p) <= 1.0 for p in sizing.PROFILES))

print("\n-- the LLM has no path into the allocator")
for f in ("alpha/allocator.py", "scripts/allocator.py"):
    src = Path(f).read_text(encoding="utf-8")
    body = "\n".join(ln for ln in src.splitlines()
                     if not ln.strip().startswith("#") and "LLM" not in ln)
    check(f"{f}: no model import, no order path",
          not any(t in body for t in ("deepseek", "llm_", "openai", "anthropic",
                                      "alpha.broker", "submit", "/v2/orders")))
check("and the daily receipt says so", any("LLM has no path" in n for n in rec["notes"]))

print(f"\n{'ALL PASS' if not fails else f'{fails} FAIL'}")
sys.exit(1 if fails else 0)
