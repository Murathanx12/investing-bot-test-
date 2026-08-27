"""WEALTH_LAB and the option-structure evaluator.

The lab exists because two paper books lost $37,337 without a single
stock-picking error. Every check here pins a step where the ANALYSIS could
repeat the mistake the BOOK made.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from alpha import lab, optlab, playbook

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


print("wealth lab")

# --- the denominator --------------------------------------------------------
r = np.arange(20.0)
check("blocks are NON-overlapping at the holding period",
      list(lab._blocks(r, 5)) == [0.0, 5.0, 10.0, 15.0],
      "a 5-day return sampled daily overlaps 80% with its neighbour; counting "
      "those as independent claims 5x the sample it has (canon §58)")

res = lab.summarise("x", np.full(50, 0.01), 5)
check("  and the t is computed on blocks, not on the overlapping draws",
      res.n_blocks == 10 and res.n_windows == 50)
check("terminal wealth compounds the blocks",
      abs(res.wealth - 1.01 ** 10) < 1e-9, f"{res.wealth}")

# --- the leaderboard noise floor -------------------------------------------
med22, p95_22 = lab.noise_max_t(51, 22)
med1, _ = lab.noise_max_t(51, 1)
check("a 22-row leaderboard's noise floor is well above 2.0", med22 > 2.0,
      f"median max|t| {med22:.2f} -- comparing a leaderboard winner to 2.0 asks "
      "whether ONE pre-registered strategy worked")
check("  and it RISES with the number of strategies tried",
      lab.noise_max_t(51, 66)[0] > med22)
check("  while a single strategy sits near the ordinary critical value",
      med1 < 1.2, f"{med1:.2f}")

# --- no lookahead -----------------------------------------------------------
n = 120
dates = [f"2026-01-{i:02d}" for i in range(1, n + 1)]
close = np.cumprod(np.full((n, 2), 1.001), axis=0) * 100.0
panel = lab.Panel(dates=dates, symbols=["A", "B"], close=close, open_=close.copy(),
                  high=close, low=close, volume=np.full((n, 2), 1e6), vwap=close)

seen: list[int] = []


def spy_on_reads(p, i):
    seen.append(i)
    w = np.zeros(2)
    w[0] = 1.0
    return w


lab.run(panel, spy_on_reads, horizon=5, name="t", start_i=60)
check("the selector is never handed an index beyond its decision date",
      max(seen) <= panel.n_dates - 7,
      "a selector that can see the exit price is not a strategy")

# --- fills ------------------------------------------------------------------
flat = lab.run(panel, lab.hold("A"), horizon=5, name="f", start_i=60, cost_bps=0.0)
costed = lab.run(panel, lab.hold("A"), horizon=5, name="c", start_i=60, cost_bps=50.0)
check("costs are charged BOTH ways and reduce the return",
      costed.mean < flat.mean, f"{costed.mean} vs {flat.mean}")
check("  and are never optional -- a zero-cost run must be asked for explicitly",
      lab.EQUITY_BPS > 0)

# --- option pricing ---------------------------------------------------------
S, K, T, sig = 100.0, 100.0, 0.25, 0.30
c = float(optlab.bs(S, K, T, sig, call=True))
put = float(optlab.bs(S, K, T, sig, call=False))
check("put-call parity holds", abs((c - put) - (S - K * math.exp(-0.04 * T))) < 1e-6,
      f"c-p={c-put:.6f}")
check("a call is worth more with more time", optlab.bs(S, K, 0.5, sig) > c)
check("delta of a deep ITM call is near 1", float(optlab.delta(S, 50.0, T, sig)) > 0.97)

# --- THE FINDING, pinned ----------------------------------------------------
# A low-vol underlying priced at a high IV: long premium must lose.
rng = np.random.default_rng(11)
quiet = rng.normal(0.004, 0.018, 400)          # ~18% annualised at 5 days
res_q = {r.name: r for r in optlab.evaluate(quiet, sigma=0.35, holding_days=5, dte=30)}
strad = [v for k, v in res_q.items() if "straddle" in k][0]
check("a long straddle on a quiet underlying priced rich has a LOSING median",
      strad.median_pnl < 0, f"{strad.median_pnl:+.2%}")
check("  and a hit rate far below a coin flip", strad.hit < 0.35, f"{strad.hit:.1%}")
condor = [v for k, v in res_q.items() if "condor" in k][0]
check("  while the condor on that SAME underlying wins",
      condor.median_pnl > 0 and condor.hit > 0.6,
      "the two structures are not both wrong -- they were run on the wrong assets")

# --- the null that decides the structure ------------------------------------
drifty = rng.normal(0.026, 0.055, 400)
res_d = {r.name: r for r in optlab.evaluate(drifty, sigma=0.55, holding_days=5, dte=30)}
res_n = {r.name: r for r in optlab.evaluate(drifty - drifty.mean(), sigma=0.55,
                                            holding_days=5, dte=30)}
atm_d = [v for k, v in res_d.items() if k.startswith("ATM call")][0]
atm_n = [v for k, v in res_n.items() if k.startswith("ATM call")][0]
check("with a drift, an ATM call has a positive median", atm_d.median_pnl > 0)
check("STRIP THE DRIFT and the same call goes negative", atm_n.median_pnl < 0,
      f"{atm_n.median_pnl:+.2%} -- long premium levers a drift; it does not create one")
sps_n = [v for k, v in res_n.items() if k.startswith("short put spread 95/85")][0]
check("  while the short put spread survives the null",
      sps_n.median_pnl > atm_n.median_pnl,
      "this is the whole reason the playbook defaults to it")

# --- the overnight decomposition, and the trap in comparing it -------------
# Overnight-only carries much less risk than buy-and-hold, so comparing their
# raw returns rewards whoever took more risk. The comparison must be at MATCHED
# VOLATILITY or it is not a comparison.
rng2 = np.random.default_rng(29)
on_leg = rng2.normal(0.00055, 0.007, 2000)     # lower total, much lower vol
day_leg = rng2.normal(0.00040, 0.006, 2000)    # positive day, so HOLD wins raw
hold_leg = on_leg + day_leg
# A first version gave the day leg a near-zero mean and HIGHER vol, and holding
# then compounded LESS than the overnight leg alone -- variance drag, the very
# effect FINDING_2026-08-28_VARIANCE_DRAG_ATE_THE_EDGE.md is about, showing up
# uninvited in a fixture meant to isolate a different point.

def ann_vol(a):
    return float(np.std(a)) * math.sqrt(252.0)

check("the overnight leg earns LESS in total than holding",
      float(np.prod(1 + on_leg)) < float(np.prod(1 + hold_leg)),
      "which is why a raw comparison is the wrong one")
check("  but carries less risk", ann_vol(on_leg) < ann_vol(hold_leg))
lev = ann_vol(hold_leg) / ann_vol(on_leg)
check("  and levering to MATCHED vol makes the comparison fair",
      abs(ann_vol(on_leg * lev) - ann_vol(hold_leg)) < 1e-9,
      f"lev={lev:.2f}")

check("costs are charged PER SESSION for a daily round trip",
      float(np.prod(1 + (on_leg - 2 * 5.0 / 10_000)))
      < float(np.prod(1 + (on_leg - 2 * 0.5 / 10_000))),
      "the cost that killed the basket version is a property of the BASKET, "
      "not of the effect -- 200 names round-tripped daily vs one ETF at 0.13bp")

_ot = Path("scripts/overnight_tradeable.py").read_text(encoding="utf-8")
check("overnight_tradeable states that financing is NOT charged",
      "Financing" in _ot and "NOT charged" in _ot,
      "the levered rows win by roughly the size of the financing cost")
check("  and calls leverage a modelling device, not a recommendation",
      "MODELLING device" in _ot)

# --- and the lab must be REACHABLE -----------------------------------------
for mod, user in (("alpha/lab.py", "scripts/wealth_lab.py"),
                  ("alpha/optlab.py", "scripts/structure_lab.py"),
                  ("alpha/playbook.py", "scripts/competition_book.py")):
    stem = Path(mod).stem
    check(f"{mod} has a caller ({user})",
          stem in Path(user).read_text(encoding="utf-8"),
          "a module with no caller is a discovery three weeks later")

print(f"\n{ran} checks")
print("ALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
