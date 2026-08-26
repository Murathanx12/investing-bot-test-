"""RESEARCH_ALPHA_BUDGET: generation is free, promotion is rationed."""
import math
import os
import random
import statistics as st
import sys
import tempfile
from pathlib import Path

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import alpha_budget as ab

ab.LEDGER = Path(tempfile.mkdtemp()) / "alpha_budget.jsonl"

print("\n-- expected max |t|: the number that prices 'our best cell hit 2.0'")

random.seed(11)
for n in (1, 2, 8, 50):
    sims = [max(abs(random.gauss(0, 1)) for _ in range(n)) for _ in range(60_000)]
    mc, exact = st.mean(sims), ab.expected_max_abs_t(n)
    check(f"n={n} matches Monte-Carlo", abs(mc - exact) < 0.02, f"MC {mc:.3f} vs {exact:.3f}")

check("it RISES with the number of cells tested",
      ab.expected_max_abs_t(2) < ab.expected_max_abs_t(8) < ab.expected_max_abs_t(50))
# The Gumbel approximation understates this, which is the dangerous direction:
# it makes the noise bar look lower and a reported t look more remarkable.
gumbel = math.sqrt(2 * math.log(16)) - (
    (math.log(math.log(16)) + math.log(4 * math.pi)) / (2 * math.sqrt(2 * math.log(16))))
check("and it EXCEEDS the Gumbel approximation that was tried first",
      ab.expected_max_abs_t(8) > gumbel, f"exact {ab.expected_max_abs_t(8):.3f} > {gumbel:.3f}")

print("\n-- charging a family for every cell LOOKED AT")

v = ab.record_batch("famA", "eight cells, best t 1.99", best_t=1.99, n_tests=8)
check("t 1.99 over 8 cells is NOT promotable", not v.promoted, v.reason[:56])
check("the adjusted p prices the eight looks", 0.25 < v.p_value < 0.40, f"p_adj={v.p_value:.4f}")
check("a failed test COSTS wealth", v.wealth_after < v.wealth_before,
      f"{v.wealth_before:.4f} -> {v.wealth_after:.4f}")

v1 = ab.record_batch("famB", "one clean pre-registered test", best_t=4.2, n_tests=1)
check("the SAME t on ONE preregistered cell is promotable", v1.promoted, v1.reason[:56])
v2 = ab.record_batch("famC", "same t, sliced 40 ways", best_t=4.2, n_tests=40)
check("...and slicing 40 ways can take the same t below the bar",
      v2.p_value > v1.p_value, f"{v1.p_value:.5f} -> {v2.p_value:.5f}")
check("a discovery PAYS a dividend back", v1.wealth_after > v1.wealth_before - 0.05,
      f"{v1.wealth_before:.4f} -> {v1.wealth_after:.4f}")

print("\n-- the budget actually runs out")

for i in range(12):
    ab.record_batch("famD", f"variant {i}", best_t=1.2, n_tests=6)
w = ab.wealth("famD")
last = ab.record_batch("famD", "variant 13", best_t=9.0, n_tests=1)
check("a family that keeps failing goes broke", w / 2.0 < ab.MIN_ALPHA, f"wealth={w:.5f}")
check("and is then REFUSED even with a huge t -- generation continues, promotion stops",
      not last.promoted and "OUT OF BUDGET" in last.reason, last.reason[:52])

print("\n-- families are independent, and every test is recorded either way")

check("a broke family does not affect a healthy one", ab.wealth("famB") > 0)
s = ab.summary()
check("the summary reports cells charged, not experiments run",
      s["famA"]["cells_charged"] == 8 and s["famA"]["experiments"] == 1, str(s["famA"]))
check("famD is marked exhausted", s["famD"]["exhausted"])
check("refused tests are still LEDGERED (a corpse with a p-value is worth more)",
      len(ab.history("famD")) == 13, str(len(ab.history("famD"))))

print("\n-- splitting one experiment into many cannot buy fresh budget")
before = ab.wealth("famA")
for i in range(4):
    ab.record_batch("famA", f"cell {i} reported alone", best_t=1.99, n_tests=1)
check("charging the same family four more times still drains it",
      ab.wealth("famA") < before, f"{before:.4f} -> {ab.wealth('famA'):.4f}")

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("ALL PASS")
