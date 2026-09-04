"""Smoke: the ENTRY pass refuses past the liquidation deadline, and a manage-only
mandate reaches the command line.

Run: python run_tests.py -k entry_deadline      (never the file directly)

THE INCIDENT (2026-09-04, hack1 and hack2)
==========================================
`exits.deadline_liquidation_due` made the EXIT pass liquidate on sight past
10:45 ET on judging day. Nothing said the same to the ENTRY pass, so the loop
kept entering on its 30-minute cadence and the next exit pass closed what had
just been opened: hack2 sold 74 PANW at 11:03:39 ET and bought it back at
11:03:44 ET. A ONE-SIDED GUARD CATCHES HALF THE ERROR.

These checks pin the two halves that were missing, and pin them the way that
would have FAILED before the fix rather than the way that merely passes after
it: the entry gate reads the SAME predicate and the SAME constant as the exit
gate (not a second copy of 10:45), the refusal is a typed LEDGER ROW rather than
a silent skip, and a mandate that declares manage_only emits the flag.
"""
from __future__ import annotations

import importlib.util
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

fails = 0


def check(name, ok, detail=""):
    global fails
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        fails += 1


ledger_tmp = Path(tempfile.mkdtemp())
os.environ["AAT_LEDGER_DIR"] = str(ledger_tmp)

from alpha import config, exits, fleet, ledger, refusal_classes  # noqa: E402

ledger.LEDGER_DIR = ledger_tmp

ROOT = Path(__file__).parent
RUN_PASS = ROOT / "scripts" / "run_pass.py"
SRC = RUN_PASS.read_text(encoding="utf-8")

print("\n-- the entry pass has a deadline gate at all")
check("run_pass calls exits.deadline_liquidation_due",
      "exits.deadline_liquidation_due(" in SRC)
check("--allow-entry-past-deadline is a declared, opt-IN override",
      '"--allow-entry-past-deadline"' in SRC
      and "not args.allow_entry_past_deadline" in SRC)
check("the gate returns a distinct non-zero code (not 0, not the expiry gate's 2)",
      re.search(r"_record_deadline_refusal\(reason\)\s*\n\s*return 3", SRC) is not None)

print("\n-- ONE predicate, ONE constant: the two passes cannot drift apart")
# The whole defect was two passes with different opinions about the same minute.
# A second hardcoded 10:45 inside run_pass would pass a naive test and quietly
# re-open the same class of bug the day someone changed LIQUIDATE_BY_ET.
check("run_pass hardcodes no second liquidation time",
      "time(10, 45)" not in SRC and "10:45" not in SRC,
      "a literal deadline in run_pass would drift from exits.LIQUIDATE_BY_ET")
check("run_pass reads the deadline constant from exits",
      "exits.LIQUIDATE_BY_ET" in SRC)
check("run_pass reads the deadline DATE from config.COMPETITION, as manage.py does",
      'config.COMPETITION["deadline_utc"]' in SRC)

print("\n-- the gate fires on the right side of the minute")
deadline = config.COMPETITION["deadline_utc"]
judging_et = (datetime.fromisoformat(deadline.replace("Z", "+00:00")) + exits.ET_OFFSET).date()


def at_et(h, m, day=None):
    """A UTC instant that is h:m ET on the judging day (or another day)."""
    d = day or judging_et
    return datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc) - exits.ET_OFFSET


check("10:44 ET on judging day: entries still allowed",
      exits.deadline_liquidation_due(deadline, now=at_et(10, 44)) is False)
check("10:45 ET on judging day: entry authority gone (inclusive)",
      exits.deadline_liquidation_due(deadline, now=at_et(10, 45)) is True)
check("11:03 ET on judging day -- the minute hack2 churned -- is refused",
      exits.deadline_liquidation_due(deadline, now=at_et(11, 3)) is True)
check("15:30 ET on judging day is still refused (it never re-arms)",
      exits.deadline_liquidation_due(deadline, now=at_et(15, 30)) is True)
check("11:03 ET the DAY BEFORE is allowed (the gate is a deadline, not a curfew)",
      exits.deadline_liquidation_due(
          deadline, now=at_et(11, 3, judging_et - timedelta(days=1))) is False)

print("\n-- the refusal is TYPED, and is not the silent catch-all bucket")
reason = (f"{refusal_classes.PAST_LIQUIDATION_DEADLINE}: past "
          f"{exits.LIQUIDATE_BY_ET.strftime('%H:%M')} ET on judging day ({deadline}).")
refusal_classes.UNMAPPED.clear()
state = refusal_classes.terminal_state(reason, action="refused")
check("the class is PAST_LIQUIDATION_DEADLINE",
      refusal_classes.classify(reason) == "PAST_LIQUIDATION_DEADLINE",
      refusal_classes.classify(reason))
check("its terminal state is a member of the closed enum",
      state in refusal_classes.TERMINAL_STATES, state)
check("it is NOT OTHER_TYPED (an untyped gate dissolves in every report)",
      state != refusal_classes.OTHER_TYPED, state)
check("nothing landed in UNMAPPED", not refusal_classes.UNMAPPED,
      str(dict(refusal_classes.UNMAPPED)))

print("\n-- the refusal REACHES the ledger (a skip nobody can count is a silence)")
spec = importlib.util.spec_from_file_location("_rp_under_test", RUN_PASS)
rp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rp)
rp.ledger.LEDGER_DIR = ledger_tmp
before = len(ledger.read_all())
rp._record_deadline_refusal(reason)
rows = ledger.read_all()
check("exactly one row was appended", len(rows) == before + 1, f"{before} -> {len(rows)}")
row = rows[-1] if rows else {}
check("the row is a refusal", row.get("action") == "refused", str(row.get("action")))
check("the row carries the full sentence", reason[:40] in (row.get("refusal_reason") or ""))
check("the row carries the typed terminal_state",
      row.get("terminal_state") == state, str(row.get("terminal_state")))
check("the row is PASS-scoped, not attributed to an invented symbol",
      row.get("symbol") == "-" and row.get("brain") == "deadline_gate",
      f"{row.get('symbol')}/{row.get('brain')}")
check("the row risks nothing",
      (row.get("max_loss_usd") or 0) == 0 and not row.get("order"))
ok_chain, chain_msg = ledger.verify_chain()
check("the hash chain is still intact after the write", ok_chain, chain_msg)

print("\n-- recording must NEVER be the reason a refusal becomes a crash")
_real = rp.ledger.record


def _boom(*_a, **_k):
    raise RuntimeError("disk full")


try:
    rp.ledger.record = _boom
    rp._record_deadline_refusal(reason)
    check("a failing ledger write does not raise out of the gate", True)
except Exception as exc:                                            # noqa: BLE001
    check("a failing ledger write does not raise out of the gate", False, repr(exc))
finally:
    rp.ledger.record = _real

print("\n-- a manage-only MANDATE reaches the command line (prose is not a guard)")
check("Mandate carries a manage_only field, defaulting to False",
      fleet.Mandate.__dataclass_fields__["manage_only"].default is False)
check("hack1 -- the SAFE anchor whose caveat said 'exits only' -- declares it",
      fleet.FLEET["hack1"].manage_only is True)
for r, m in fleet.FLEET.items():
    args = fleet.loop_args(m)
    env = fleet.env_for(m)
    if m.manage_only:
        check(f"{r}: loop_args emits --manage-only", "--manage-only" in args, str(args[:6]))
        check(f"{r}: it survives into AAT_LOOP_ARGS", "--manage-only" in env["AAT_LOOP_ARGS"])
        # nargs="*" must not swallow the flag: --universe stays LAST.
        if "--universe" in args:
            check(f"{r}: --manage-only precedes --universe",
                  args.index("--manage-only") < args.index("--universe"))
    else:
        check(f"{r}: no --manage-only where none was declared",
              "--manage-only" not in args and "--manage-only" not in env["AAT_LOOP_ARGS"])
check("declared manage_only roles == roles emitting the flag",
      {r for r, m in fleet.FLEET.items() if m.manage_only}
      == {r for r, m in fleet.FLEET.items() if "--manage-only" in fleet.loop_args(m)})
check("the flag agent_loop actually parses is spelled the same way",
      '"--manage-only"' in (ROOT / "scripts" / "agent_loop.py").read_text(encoding="utf-8"))

print(f"\n{'FAILED' if fails else 'ok'}  tests_smoke_entry_deadline: {fails} failure(s)")
