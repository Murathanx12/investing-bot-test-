"""SANITY_SENTINELS_v1 -- the 96.4% pathology, generalised and given an action.

The fraction was computable the whole time. Every one of those 6,070 decisions
wrote `predicted_sd` and `implied_move` to the ledger; nothing read them
together, and the books spent -$22,017 on long straddles first.

Measured on the whole ledger when this was written: relay 99.0%,
narrative_dispersion 96.1%, options_attention 95.4%, vol_gap 93.1% -- four of
five brains, not just the one that had been quarantined by hand. `event_move`,
the only brain that never executed, is the only one that reads balanced.
"""
from __future__ import annotations

import math
from pathlib import Path

from alpha import sentinels

fails: list[str] = []
ran = 0


def check(name: str, cond: bool, why: str = "") -> None:
    global ran
    ran += 1
    if cond:
        print(f"  ok   {name}")
    else:
        fails.append(name)
        print(f"  FAIL {name}  {why}")


print("sanity sentinels")

CHAIN_IM = 0.08                      # E|move|
CHAIN_SIGMA = CHAIN_IM * math.sqrt(math.pi / 2.0)


def rows(brain, n, sd):
    return [{"brain": brain, "predicted_sd": sd, "implied_move": CHAIN_IM} for _ in range(n)]


# --- THE CONVERSION, which is the whole point ------------------------------
# The chain quotes E|move|, not a sigma. sigma = E|move| * sqrt(pi/2). Writing
# `predicted_sd / implied_move` overstates the brain by 25% on every row, and
# that is literally one of the three original bugs.
check("chain_sigma applies sqrt(pi/2)",
      abs(sentinels.chain_sigma(CHAIN_IM) - CHAIN_SIGMA) < 1e-12)
check("  so a brain whose sd EQUALS the chain's E|move| reads BELOW the chain",
      sentinels.ratios(rows("b", 1, CHAIN_IM))["b"][0] < 1.0,
      "without the conversion this would read exactly 1.0 and drift over the line")
check("a brain at exactly the chain's sigma reads 1.0",
      abs(sentinels.ratios(rows("b", 1, CHAIN_SIGMA))["b"][0] - 1.0) < 1e-12)

# --- the verdicts -----------------------------------------------------------
wide = sentinels.judge("wide", [1.5] * 200)
check("a brain above the chain on 100% of 200 decisions is BROKEN",
      wide.state == sentinels.BROKEN, wide.line())
check("  and may NOT open", not wide.may_open)
check("  and the detail names the 96.4% pathology and the ruler",
      "96.4%" in wide.detail and "ruler that reads long" in wide.detail)
check("  and says exits and marking continue",
      "exits and marking continue" in wide.detail,
      "quarantining exits turns a measurement problem into a trapped book")

narrow = sentinels.judge("narrow", [0.5] * 200)
check("the MIRROR image -- always cheap-selling -- is BROKEN too",
      narrow.state == sentinels.BROKEN and "EXPENSIVE" in narrow.detail, narrow.line())
check("  and it names selling premium as the failure mode",
      "sells premium instead of buying it" in narrow.detail)

balanced = sentinels.judge("bal", [1.2] * 100 + [0.8] * 100)
check("a brain that disagrees BOTH ways is OK", balanced.state == sentinels.OK,
      balanced.line())
check("  and may open", balanced.may_open)

edge = sentinels.judge("edge", [1.5] * 89 + [0.5] * 11)
check("89% one-sided is NOT broken -- the trigger is above 90%",
      edge.state == sentinels.OK, edge.line())
check("91% one-sided IS broken",
      sentinels.judge("e2", [1.5] * 91 + [0.5] * 9).state == sentinels.BROKEN)
check("the trigger sits BELOW the observed pathology, not on it",
      sentinels.ONE_SIDED_MAX < 0.964,
      "0.90 vs the measured 0.964 -- a trigger sitting on the observation catches nothing")

# --- thin samples -----------------------------------------------------------
thin = sentinels.judge("thin", [1.5] * 6)
check("six one-sided decisions is CANNOT_DETERMINE, not BROKEN",
      thin.state == sentinels.CANNOT_DETERMINE, thin.line())
check("  and it says 'we could not look' is not 'it is fine'",
      "must not print the same" in thin.detail)
check("  and CANNOT_DETERMINE may still open",
      thin.may_open,
      "the sentinel catches a measured pathology; it does not block every new brain")
check("the floor is 50", sentinels.MIN_DECISIONS == 50)

# --- rows that cannot be judged are dropped, not defaulted ------------------
mixed = [{"brain": "x", "predicted_sd": 0.1, "implied_move": 0.08},
         {"brain": "x", "predicted_sd": None, "implied_move": 0.08},
         {"brain": "x", "predicted_sd": 0.1, "implied_move": None},
         {"brain": "x", "predicted_sd": 0.1, "implied_move": 0.0},
         {"brain": None, "predicted_sd": 0.1, "implied_move": 0.08}]
check("only rows carrying BOTH a forecast and a quote are counted",
      len(sentinels.ratios(mixed)["x"]) == 1,
      "a missing implied move is not a zero-width chain")

check("broken() returns the names, for the runner to shadow",
      sentinels.broken(rows("bad", 100, 0.3) + rows("good", 100, CHAIN_SIGMA * 1.1)
                       + rows("good", 100, CHAIN_SIGMA * 0.9)) == {"bad"})

# --- and it must be WIRED ---------------------------------------------------
src = Path("scripts/run_pass.py").read_text(encoding="utf-8")
check("run_pass consults the sentinels", "sentinels.broken(" in src)
check("  and SHADOWS the brain rather than killing it",
      "shadow_list.append(b)" in src,
      "it still forecasts, enumerates and gets graded in the counterfactual")
i_s, i_r = src.find("sentinels.broken("), src.find("runner.run_pass(")
check("  before the pass runs", -1 < i_s < i_r, f"{i_s} vs {i_r}")
check("a sentinel that cannot run says so instead of passing silently",
      "proceeding WITHOUT them and" in src,
      "an exception here must not read as a clean bill of health")
check("there is an explicit escape hatch", "--no-sentinels" in src)

print(f"\n{ran} checks")
print("ALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
