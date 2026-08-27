"""WINDOW_UNIVERSE_v1 -- the universe is a consequence of the calendar.

On 27 Aug a dry pass over the hardcoded UNIVERSE produced ZERO forecasts. Every
line was `NotApplicable`; every mega-cap was 19-25 sessions past a late-July
print against a drift window of +1..+3. The agent was pointed at the one slice
of the market guaranteed to have no events during the contest.

A book that refuses everything scores zero, and P&L is criterion #1. These
checks pin the arithmetic that stops it -- especially the amc/bmo distinction,
which decides which session the drift is counted from.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

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


print("window universe -- events that reach inside the contest")

from scripts.window_universe import (DRIFT_SESSIONS, effective_print_date,   # noqa: E402
                                     sessions_between)

# --- amc vs bmo decides the session the market first reacts in --------------
# Thu 2026-08-27 amc -> the reaction is Fri 28 Aug, day one of the contest.
check("an amc print reacts the NEXT session",
      effective_print_date(date(2026, 8, 27), "amc") == date(2026, 8, 28))
check("a bmo print reacts the SAME session",
      effective_print_date(date(2026, 8, 27), "bmo") == date(2026, 8, 27))
check("a BLANK hour is treated as amc",
      effective_print_date(date(2026, 8, 27), "") == date(2026, 8, 28),
      "delaying the window is the conservative error; opening it early would act "
      "on information before it is public")
check("an amc print on FRIDAY reacts on Monday",
      effective_print_date(date(2026, 8, 28), "amc") == date(2026, 8, 31),
      "a calendar-day + 1 would land on Saturday and count a session that does not exist")
check("a bmo print on Friday reacts on Friday",
      effective_print_date(date(2026, 8, 28), "bmo") == date(2026, 8, 28))

# --- session counting skips weekends ---------------------------------------
check("Fri -> Mon is ONE session", sessions_between(date(2026, 8, 28), date(2026, 8, 31)) == 1,
      str(sessions_between(date(2026, 8, 28), date(2026, 8, 31))))
check("Fri 28 Aug -> Fri 4 Sep is FIVE sessions",
      sessions_between(date(2026, 8, 28), date(2026, 9, 4)) == 5,
      "the contest is 5.0 equity sessions; if this says 7 it is counting calendar days")
check("a date with itself is zero", sessions_between(date(2026, 9, 1), date(2026, 9, 1)) == 0)
check("backwards is zero, never negative",
      sessions_between(date(2026, 9, 4), date(2026, 8, 28)) == 0)

check("the drift window matches the brain's measurement", DRIFT_SESSIONS == (1, 3),
      "post_event_drift measures +1..+3; a mismatch here silently widens the universe")

# --- the plan must classify the deadline, not ignore it ---------------------
src = Path("scripts/window_universe.py").read_text(encoding="utf-8")
for status in ("FULL_WINDOW", "TRUNCATED_BY_DEADLINE", "TOO_LATE", "BEFORE_KICKOFF"):
    check(f"the plan can report {status}", status in src)
check("a print past the deadline is LISTED, not dropped",
      "listed and marked `TOO_LATE` rather than dropped" in src,
      "'there were no events' and 'there were events we could not reach' are different "
      "sentences and call for different work")
check("the revenue floor is labelled a PROXY for chain liquidity",
      "LIQUIDITY" in src and "poor stand-in" in src,
      "revenue is not liquidity and the code must not pretend otherwise")
check("holidays are stated rather than assumed",
      "Labor Day is 7 Sep 2026" in src and "AFTER the contest" in src)

# --- and it must be reachable from the pass ---------------------------------
rp = Path("scripts/run_pass.py").read_text(encoding="utf-8")
check("run_pass can load the window universe", "--window-universe" in rp)
check("it reads the receipt rather than re-deriving it",
      "window_universe.json" in rp,
      "a second derivation is a second thing that can disagree")
check("it REFUSES when the receipt is missing",
      "run\\n" not in rp and "needs state/window_universe.json" in rp,
      "silently falling back to the empty mega-cap universe is the original bug")
check("the reason is recorded where the next reader will hit it",
      "report in the last\n        # week of JULY" in rp or "week of JULY" in rp)

print(f"\n{ran} checks")
print("ALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
