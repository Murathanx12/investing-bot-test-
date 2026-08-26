"""Effective N by RISK: a book that looks like five bets can behave like one."""
import math
import random
import sys

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import concentration as C

rng = random.Random(7)


def series(n=120, sd=0.02):
    return [rng.gauss(0, sd) for _ in range(n)]


def with_common(factor, beta, idio_sd=0.01):
    return [beta * f + rng.gauss(0, idio_sd) for f in factor]


print("\n-- independent names: N by risk should equal N by weight")
ind = {f"S{i}": series() for i in range(5)}
c = C.measure({k: 1.0 for k in ind}, ind)
check("5 equal independent names -> N_weight 5", abs(c.n_weight - 5) < 1e-6, f"{c.n_weight:.3f}")
check("...and N_risk is also about 5", abs(c.n_risk - 5) < 0.9, f"{c.n_risk:.3f}")
check("...with near-zero average correlation", abs(c.avg_rho) < 0.15, f"{c.avg_rho:+.3f}")

print("\n-- one shared factor: the weight count stops meaning anything")
f = series(120, 0.02)
same = {f"T{i}": with_common(f, 1.0, 0.003) for i in range(5)}
c2 = C.measure({k: 1.0 for k in same}, same)
check("N_weight is still 5 -- capital IS spread", abs(c2.n_weight - 5) < 1e-6, f"{c2.n_weight:.3f}")
check("but N_RISK collapses toward 1", c2.n_risk < 1.6, f"{c2.n_risk:.3f}")
check("...and the overstatement is reported", c2.overstatement > 3, f"{c2.overstatement:.1f}x")
check("real vol EXCEEDS the independent vol when names move together",
      c2.vol_real > c2.vol_independent, f"{c2.vol_real:.4f} > {c2.vol_independent:.4f}")

print("\n-- the verdict is calibrated against a real blow-up, not a round number")
check("the reference is Situational Awareness's measured 1.43",
      abs(C.SITUATIONAL_AWARENESS_Q2_2026_N_RISK - 1.43) < 1e-9)
st, why = C.verdict(c2)
check("a one-factor book reads CONCENTRATED", st == "CONCENTRATED", why[:60])
check("...and the verdict NAMES the comparison", "Situational Awareness" in why)
st2, _ = C.verdict(c)
check("an independent book reads SPREAD", st2 == "SPREAD", st2)
st3, why3 = C.verdict(None)
check("no measurement is UNKNOWN, and says so is not diversification",
      st3 == "UNKNOWN" and "not evidence" in why3, why3[:50])

print("\n-- an unpriced name is DROPPED and NAMED, never assumed uncorrelated")
c3 = C.measure({"A": 1.0, "B": 1.0, "GHOST": 5.0}, {"A": series(), "B": series()})
check("the unpriced name is excluded", c3.names == 2, str(c3.names))
check("...and reported by name", c3.unpriced == ["GHOST"], str(c3.unpriced))
check("...and appears in the summary line", "GHOST" in c3.summary())
# Silently dropping it would RAISE the diversification reading -- the direction
# that flatters the book -- which is exactly why it is named instead.

print("\n-- weights come from TRUE MAX LOSS, not from marks")


class S:
    def __init__(self, symbol, mlpu, contracts):
        self.symbol, self.max_loss_per_unit, self.contracts = symbol, mlpu, contracts


class B:
    structures = [S("NVDA260828C00200000", 5.0, 10), S("NVDA", 3.0, 10), S("AMD", 2.0, 25)]


w = C.weights_from_book(B())
check("option legs are folded into their UNDERLYING", set(w) == {"NVDA", "AMD"}, str(w))
check("max loss is per-unit times contracts", w["NVDA"] == 80.0 and w["AMD"] == 50.0, str(w))
check("OCC symbols decode to the underlying",
      C.underlying_of("NVDA260828C00200000") == "NVDA" and C.underlying_of("SPY") == "SPY")

print("\n-- marginal contribution: which name costs the most diversification")
# Size and diversification-damage give DIFFERENT orderings, and the difference is
# the whole point: a large uncorrelated position can RAISE effective N while a
# small duplicate of the book's main bet lowers it. Measured live the same day:
# in exp1, removing NVDA -- an 18% position -- would have made the book MORE
# concentrated, because it is the only thing uncorrelated with its index cluster.
f2 = series(120, 0.02)
mixed = {"CLONE_A": with_common(f2, 1.0, 0.002),      # duplicates the main bet
         "CLONE_B": with_common(f2, 1.0, 0.002),
         "CLONE_C": with_common(f2, 1.0, 0.002),
         "DIVERSIFIER": series(120, 0.02)}            # independent of it
w = {"CLONE_A": 1.0, "CLONE_B": 1.0, "CLONE_C": 1.0, "DIVERSIFIER": 4.0}
m = C.marginal(w, mixed)
check("a CLONE is flagged to cut first, not the BIGGEST position",
      m[0][0].startswith("CLONE"), f"flagged {m[0][0]}, biggest is DIVERSIFIER")
check("removing the DIVERSIFIER makes the book WORSE (negative delta)",
      m[-1][0] == "DIVERSIFIER" and m[-1][3] < 0, f"{m[-1][0]} {m[-1][3]:+.2f}")
check("every entry reports share, N-without, and delta", all(len(r) == 4 for r in m))
check("it is sorted worst-first",
      [r[3] for r in m] == sorted([r[3] for r in m], reverse=True))
check("an unmeasurable book returns no ranking",
      C.marginal({"A": 1.0}, {"A": series()}) == [])

print("\n-- degenerate inputs refuse rather than returning a flattering number")
check("one name cannot be measured", C.measure({"A": 1.0}, {"A": series()}) is None)
check("too few sessions cannot be measured",
      C.measure({"A": 1.0, "B": 1.0}, {"A": [0.1, 0.2], "B": [0.1, 0.2]}) is None)
check("zero weights cannot be measured",
      C.measure({"A": 0.0, "B": 0.0}, {"A": series(), "B": series()}) is None)

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("ALL PASS")
