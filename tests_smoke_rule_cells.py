"""T6 (Murat's rule cells) and T3 (sector lead vs laggard) -- the arithmetic.

Run: python tests_smoke_rule_cells.py  (also executed by tests_smoke.py)

These pin the three things that decide whether the tables mean anything:

  * the BLOCK count, because a 21-session forward return computed daily overlaps
    20 of its 21 days with the next one and a t on the daily count is a number
    about the calendar;
  * TERMINAL WEALTH as an equal-weight portfolio of the cell, because a mean of
    +0.147% per window with a terminal wealth of 0.1x is the measured shape of
    variance drag on CRSP, and a cell ranked on its mean recommends the book
    that loses;
  * the MDE, so a point estimate smaller than what the sample could detect
    reads `below its own MDE` and not as a finding.
"""
from __future__ import annotations

import os

os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from scripts import rule_cells as rcs

print("\n-- forward returns enter at the NEXT OPEN, never today's close")
bars = [{"t": f"2026-01-{d:02d}T00:00:00Z", "o": 100.0 + d, "c": 101.0 + d} for d in range(1, 12)]
f = rcs.forward(bars, 3)
# day 1 -> open of day 2 (102) to close of day 4 (105)
check("entry is the open AFTER the signal day",
      abs(f["2026-01-01"] - (105.0 / 102.0 - 1)) < 1e-12, str(f.get("2026-01-01")))
check("a day without a full horizon ahead is absent, not zero",
      "2026-01-10" not in f and "2026-01-11" not in f, str(sorted(f)[-1]))

print("\n-- blocks: overlapping windows are not independent observations")
days_daily = [f"2026-0{1 + (i // 28)}-{1 + (i % 28):02d}" for i in range(84)]
check("84 consecutive days over a 21-session horizon are ~3 blocks, not 84",
      2 <= rcs._blocks(days_daily, 21) <= 4, str(rcs._blocks(days_daily, 21)))
check("one day is one block", rcs._blocks(["2026-01-05"], 21) == 1)
check("no days is no blocks", rcs._blocks([], 21) == 0)
check("the same day repeated (many symbols) is still ONE block",
      rcs._blocks(["2026-01-05"] * 40, 21) == 1, str(rcs._blocks(["2026-01-05"] * 40, 21)))

print("\n-- terminal wealth is the CELL as an equal-weight portfolio")
# Two symbols on the same block-start day: +10% and -10%. The portfolio is flat,
# and a construction that picked one name would report 1.10 or 0.90.
vals = [0.10, -0.10]
days = ["2026-01-05", "2026-01-05"]
c = rcs._cell(vals, days, 21)
check("two names on one day compound as their MEAN, not as either one",
      abs(c["terminal_wealth_non_overlapping"] - 1.0) < 1e-9,
      str(c["terminal_wealth_non_overlapping"]))
check("...and that day is one block", c["n_blocks"] == 1, str(c["n_blocks"]))
# Two separated blocks at +10% each compound to 1.21.
c2 = rcs._cell([0.10, 0.10], ["2026-01-05", "2026-03-05"], 21)
check("two separated blocks compound", abs(c2["terminal_wealth_non_overlapping"] - 1.21) < 1e-9,
      str(c2["terminal_wealth_non_overlapping"]))
check("and count as two blocks", c2["n_blocks"] == 2, str(c2["n_blocks"]))
# Overlapping days inside one block must not compound twice.
c3 = rcs._cell([0.10] * 5, [f"2026-01-{d:02d}" for d in (5, 6, 7, 8, 9)], 21)
check("five consecutive days inside one block compound ONCE",
      abs(c3["terminal_wealth_non_overlapping"] - 1.10) < 1e-9,
      str(c3["terminal_wealth_non_overlapping"]))

print("\n-- the mean and the wealth can disagree, and the wealth is the one that pays")
swing = rcs._cell([0.50, -0.40] * 6, [f"2026-{m:02d}-05" for m in range(1, 13)], 21)
check("a +5% mean with a big swing still loses money compounded",
      swing["mean"] > 0 and swing["terminal_wealth_non_overlapping"] < 1.0,
      f"mean {swing['mean']:+.2%}, wealth {swing['terminal_wealth_non_overlapping']:.3f}")

print("\n-- the MDE, and refusing to read an effect smaller than it")
c4 = rcs._cell([0.001] * 40, [f"2026-{m:02d}-05" for m in range(1, 13)] * 4, 21)
check("a tiny effect with no dispersion is not automatically 'below MDE'",
      c4["mde_at_80pct_power"] == 0.0 or c4["mde_at_80pct_power"] is None,
      str(c4["mde_at_80pct_power"]))
noisy = rcs._cell([0.30, -0.28] * 6, [f"2026-{m:02d}-05" for m in range(1, 13)], 21)
check("a noisy cell reports an MDE above its own mean and says so",
      noisy["mde_at_80pct_power"] > abs(noisy["mean"]) and noisy["verdict"] == "below its own MDE",
      f"mean {noisy['mean']:+.2%} vs MDE {noisy['mde_at_80pct_power']:.2%}")
thin = rcs._cell([0.05, 0.06], ["2026-01-05", "2026-01-06"], 21)
check("under three blocks the verdict is 'too few blocks to read'",
      thin["verdict"] == "too few blocks to read", thin["verdict"])
check("an empty cell is empty, never a zero effect",
      rcs._cell([], [], 21)["verdict"] == "empty")

print("\n-- the bars and the rule's own thresholds are Murat's, and stated")
check("upside bar is 1.5", rcs.UPSIDE_BAR == 1.5)
check("drawdown bar is -20%", rcs.DRAWDOWN_BAR == -0.20)
check("rating bar is 4.1 (declared even though it cannot be tested yet)",
      rcs.RATING_BAR == 4.1)
check("T3 needs at least three names in one driver",
      rcs.T3_MIN_NAMES >= 3, str(rcs.T3_MIN_NAMES))
check("the T3 shock is on attention_z, which is normalised by the name's OWN baseline "
      "-- a 390:1 coverage ratio must not decide it", rcs.T3_SHOCK_Z > 0)

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
