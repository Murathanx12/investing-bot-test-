"""REPEATED_INVARIANT_ESCALATION: a warning may not print fifty-three times."""
import sys
import tempfile
from pathlib import Path

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import escalation as E

E.STORE = Path(tempfile.mkdtemp()) / "escalation.json"

print("\n-- repetition is evidence: the same failure gets LOUDER")
levels = []
for i in range(1, 12):
    levels.append(E.observe("ledger_chain", False, "chain breaks at line 1203").level)
check("1st occurrence WARNs", levels[0] == E.WARN, levels[0])
check("2nd is still WARN -- two in a row may be one transient seen twice",
      levels[1] == E.WARN, levels[1])
check("3rd ELEVATES", levels[2] == E.ELEVATED, levels[2])
check("10th FAILS", levels[9] == E.FAIL, levels[9])
check("and it stays FAILED", levels[10] == E.FAIL, levels[10])

e = E.status("ledger_chain")
check("the count is carried, not just the level", e.consecutive == 11, str(e.consecutive))
check("FAIL is red", e.red)
check("the line says it cannot be acknowledged away",
      "cannot be cleared by acknowledging" in e.line(), e.line()[-70:])

print("\n-- the real case: 53 occurrences would have gone red at 10")
# The ledger chain warning printed 53+ times over two days and nobody looked.
# Under this rule it becomes a standing defect on the tenth pass, which on a
# five-minute exit cadence is under an hour.
check("53 consecutive is FAIL, not a 53rd identical warning",
      E.level_for(53) == E.FAIL, E.level_for(53))
check("standing_defects surfaces it", [x.key for x in E.standing_defects()] == ["ledger_chain"])

print("\n-- a clean observation RESETS, so a transient blip decays")
E.observe("ledger_chain", True)
e2 = E.status("ledger_chain")
check("one pass clears the consecutive count", e2.consecutive == 0, str(e2.consecutive))
check("...and the level returns to OK", e2.level == E.OK, e2.level)
check("but the TOTAL is remembered", e2.total == 11, str(e2.total))
check("nothing is standing any more", E.standing_defects() == [])

print("\n-- keys are independent")
E.observe("loop_liveness", False, "dev DEAD")
check("a second invariant escalates on its own clock",
      E.status("loop_liveness").consecutive == 1 and E.status("ledger_chain").consecutive == 0)

print("\n-- there is deliberately NO acknowledge verb")
check("escalation exposes no snooze/ack/silence function",
      not any(hasattr(E, n) for n in ("acknowledge", "ack", "snooze", "silence", "mute")),
      "a snooze button is how a warning becomes wallpaper with extra steps")

print("\n-- the CLI must survive the failure it exists to report")
# scripts.liveness printed esc.line() in the unhealthy branch while `esc` was
# never assigned: the wiring patch asserted mid-script and wrote nothing, and I
# reported it as done anyway. The healthy path never touches the name, so the
# NameError was LATENT and would have fired the first time a loop actually
# died -- a guard that crashes at the exact moment of the failure it watches for.
import importlib
import sys as _sys
_cli = importlib.import_module("scripts.liveness")
from alpha import liveness as _A
_orig, _argv = _A.report, _sys.argv
try:
    _A.report = lambda *a, **k: (False, ["dev    DEAD     pid 999 is NOT running."])
    _sys.argv = ["liveness"]
    rc = _cli.main()
    check("the CLI REPORTS a dead loop instead of crashing", rc == 1, f"rc={rc}")
except NameError as exc:
    check("the CLI REPORTS a dead loop instead of crashing", False, f"NameError: {exc}")
finally:
    _A.report, _sys.argv = _orig, _argv
check("...and it actually records the invariant",
      E.status("loop_liveness") is not None,
      "an escalation nobody observes is a ladder nobody climbs")

print("\n-- an unreadable store degrades to 'no history', never to OK-by-accident")
E.STORE.write_text("{ not json", encoding="utf-8")
check("a corrupt store reads as absent", E.status("ledger_chain") is None)
check("...and the next failure still WARNs rather than crashing",
      E.observe("ledger_chain", False, "x").level == E.WARN)

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("ALL PASS")
