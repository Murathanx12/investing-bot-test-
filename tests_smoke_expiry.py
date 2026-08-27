"""NEVER HOLD THROUGH AN EXPIRY -- the rule with no test, on the day it matters.

`alpha/exits.CLOSE_BEFORE_EXPIRY_ET` exists, is correct, and on 2026-08-27 was
covered by no test in the suite. It matters tomorrow: the dev book holds a SHORT
NVDA 225 call expiring 2026-08-28, and an ITM short call left open through the
close is auto-exercised at $0.01 -- converting a 19-lot premium position into a
1,900-share stock short overnight, with no decision taken by anybody.

The deadline rule above it is tested here too, because their ORDER is
load-bearing: the deadline must outrank a position that still has time on it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from alpha import exits

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


print("expiry and deadline exits")

DEADLINE = "2026-09-04T15:00:00Z"


def at_et(y, m, d, hh, mm):
    """A UTC instant that is `hh:mm` in ET, using the module's own offset."""
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc) - exits.ET_OFFSET


def pos(symbol, qty=-19.0, cost=1000.0, plpc=0.0):
    return {"symbol": symbol, "qty": str(qty), "cost_basis": str(cost),
            "unrealized_plpc": str(plpc)}


SHORT_CALL = pos("NVDA260828C00225000")          # the real dev position
LONG_CALL = pos("NVDA260828C00232500", qty=34.0)

# --- the expiry session -----------------------------------------------------
v = exits.evaluate(SHORT_CALL, deadline_utc=DEADLINE, now=at_et(2026, 8, 28, 15, 31))
check("a short call on its expiry session, past 15:30 ET, is CLOSED", v.close, v.reason)
check("  immediately", v.urgency == "immediate")
check("  and the reason names the auto-exercise, not just the clock",
      "auto-exercise" in v.reason and "stock" in v.reason)

v = exits.evaluate(SHORT_CALL, deadline_utc=DEADLINE, now=at_et(2026, 8, 28, 15, 29))
check("one minute BEFORE the cut it is not forced", not v.close, v.reason)

v = exits.evaluate(LONG_CALL, deadline_utc=DEADLINE, now=at_et(2026, 8, 28, 15, 31))
check("a LONG call is closed on the expiry session too", v.close,
      "an ITM long auto-exercises into stock the account may not be able to hold")

v = exits.evaluate(SHORT_CALL, deadline_utc=DEADLINE, now=at_et(2026, 8, 27, 15, 31))
check("the DAY BEFORE expiry, 15:31 ET does not force it", not v.close, v.reason)

v = exits.evaluate(SHORT_CALL, deadline_utc=DEADLINE, now=at_et(2026, 8, 31, 10, 0))
check("an ALREADY-EXPIRED contract is flattened as residue", v.close, v.reason)
check("  immediately, and called residue",
      v.urgency == "immediate" and "residue" in v.reason)

# --- the deadline outranks it ----------------------------------------------
# A position with a week of life left, on judging morning, past 10:45.
FAR = pos("NVDA260918C00225000")
v = exits.evaluate(FAR, deadline_utc=DEADLINE, now=at_et(2026, 9, 4, 10, 46))
check("past 10:45 ET on judging day, a position with time left is CLOSED",
      v.close and v.urgency == "immediate", v.reason)
check("  and the reason is the DEADLINE, not the expiry",
      "deadline liquidation" in v.reason)
check("  naming why a wide option's mark is not a price anyone would pay",
      "not a price anyone would pay" in v.reason)

v = exits.evaluate(FAR, deadline_utc=DEADLINE, now=at_et(2026, 9, 4, 10, 44))
check("at 10:44 it is not yet forced", not v.close, v.reason)

v = exits.evaluate(FAR, deadline_utc=DEADLINE, now=at_et(2026, 9, 3, 15, 59))
check("the day before judging, nothing is forced", not v.close, v.reason)

check("the liquidation cut leaves margin before the 11:00 judging",
      exits.LIQUIDATE_BY_ET.hour == 10 and exits.LIQUIDATE_BY_ET.minute == 45,
      "an order sent at 10:59 into a wide option spread is a hope, not an exit")
check("the expiry cut is before the close, not at it",
      exits.CLOSE_BEFORE_EXPIRY_ET.hour == 15
      and exits.CLOSE_BEFORE_EXPIRY_ET.minute == 30)

# --- and the rules must be in the right ORDER -------------------------------
# On judging day a contract expiring THAT day hits both rules. The deadline must
# win, because it fires 4h45m earlier and waiting for the expiry rule would leave
# the position open through the cut.
SAME_DAY = pos("SPY260904C00770000")
v = exits.evaluate(SAME_DAY, deadline_utc=DEADLINE, now=at_et(2026, 9, 4, 10, 46))
check("on judging day the DEADLINE fires before the expiry rule would",
      v.close and "deadline liquidation" in v.reason,
      "the expiry rule waits until 15:30, four hours after judging")

print(f"\n{ran} checks")
print("ALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
