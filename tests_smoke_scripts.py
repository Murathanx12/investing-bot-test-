"""Pure logic inside the session-13 scripts: dates, OCC parsing, regression."""
import math
import random
import sys
from datetime import date

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from scripts import contagion, reunderwrite

print("\n-- OCC symbols: an expiry misread silently mis-ages every position")
check("a call decodes", reunderwrite.expiry_of("NVDA260828C00200000") == date(2026, 8, 28))
check("a put decodes", reunderwrite.expiry_of("SPY260115P00450000") == date(2026, 1, 15))
check("a share symbol has no expiry", reunderwrite.expiry_of("NVDA") is None)
check("junk has no expiry", reunderwrite.expiry_of("NOT-AN-OCC") is None)
check("an impossible date is refused, not wrapped",
      reunderwrite.expiry_of("NVDA269932C00200000") is None)
# 2-digit years: OCC has no century, so 26 must mean 2026 and not 1926.
check("the 2-digit year resolves to this century",
      reunderwrite.expiry_of("AAPL300101C00100000") == date(2030, 1, 1))

print("\n-- event nodes")
check("a dated node parses", reunderwrite.event_date_of("print:2026-08-27") == date(2026, 8, 27))
check("an undated node is None", reunderwrite.event_date_of("theme:ai") is None)
check("no node is None", reunderwrite.event_date_of(None) is None)

print("\n-- the two-regressor OLS the contagion decomposition rests on")
rng = random.Random(3)
n = 250
x1 = [rng.gauss(0, 0.02) for _ in range(n)]
x2 = [rng.gauss(0, 0.02) for _ in range(n)]
y = [1.3 * a + (-0.7) * b + rng.gauss(0, 0.001) for a, b in zip(x1, x2)]
a, b, sd = contagion._ols2(y, x1, x2)
check("recovers a known positive loading", abs(a - 1.3) < 0.05, f"{a:.3f}")
check("recovers a known NEGATIVE loading", abs(b + 0.7) < 0.05, f"{b:.3f}")
check("residual sd is small when the model is right", sd < 0.005, f"{sd:.5f}")

# A degenerate regressor pair must not produce a confident beta. Two identical
# regressors are perfectly collinear and the split between them is arbitrary --
# returning any number there would be a beta invented by floating-point dust.
a2, b2, sd2 = contagion._ols2(y, x1, list(x1))
check("perfectly collinear regressors return zeros, not an arbitrary split",
      (a2, b2) == (0.0, 0.0), f"{a2:.3f},{b2:.3f}")
check("too few observations refuse", contagion._ols2(y[:5], x1[:5], x2[:5]) == (0.0, 0.0, 0.0))

print("\n-- the mechanical index weight is a BAND, not a point estimate")
lo, hi = contagion.NVDA_SPX_WEIGHT_BAND
check("the point estimate sits inside its own band",
      lo <= contagion.NVDA_SPX_WEIGHT <= hi, f"{lo}..{hi}")
# The band must CONTAIN the empirically fitted loading, not merely be near it.
# The first version of this test allowed +0.006 of slack so a 0.084 fit could
# pass a 0.080 ceiling -- which is a test edited to fit the number rather than a
# band edited to fit the evidence. The band was widened instead.
check("the band CONTAINS the empirically fitted SPY loading, with no slack",
      lo <= contagion.NVDA_SPX_WEIGHT_FITTED <= hi,
      f"fitted {contagion.NVDA_SPX_WEIGHT_FITTED} in {lo}..{hi}")
check("the fitted loading is ABOVE the reported weight, as a beta should be",
      contagion.NVDA_SPX_WEIGHT_FITTED > contagion.NVDA_SPX_WEIGHT,
      "a regression beta absorbs mechanical weight PLUS unexplained correlation")

print("\n-- SMH is a regressor and must never be scored as a node")
check("SMH is excluded from the node list", "SMH" not in contagion.NODES)
check("NVDA is excluded from the node list", "NVDA" not in contagion.NODES)
check("SMH is an index/regressor", "SMH" in contagion.INDEXES)

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("ALL PASS")
