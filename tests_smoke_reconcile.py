"""Intent-before-POST, and the reconciliation it makes possible.

The property under test is not "runner writes two rows". It is that after a
crash between the POST and the ledger write, the order at the venue is still
FINDABLE -- which needs the client_order_id to be derivable from something that
was already on disk before the POST went out.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from alpha import runner
from alpha.broker.alpaca import client_order_id

fails: list[str] = []
ran = 0
ROOT = Path(__file__).parent


def check(name: str, cond: bool, why: str = "") -> None:
    global ran
    ran += 1
    if cond:
        print(f"  ok   {name}")
    else:
        fails.append(name)
        print(f"  FAIL {name}  {why}")


print("intent before POST")

src = inspect.getsource(runner)
i_intent = src.find('action="intent"')
i_submit = src.find("client.submit(order")
check("runner writes an intent row", i_intent != -1)
check("and writes it BEFORE the POST", -1 < i_intent < i_submit,
      f"intent at {i_intent}, submit at {i_submit}")
check("the submitted row is still written after", src.find('action="submitted"') > i_submit)

# --- the id is DERIVED, which is what makes recovery possible --------------
a, b = client_order_id("dec-123"), client_order_id("dec-123")
check("client_order_id is deterministic", a == b, f"{a} vs {b}")
check("different decisions get different ids", client_order_id("dec-124") != a)
check("and it is the documented shape", a.startswith("aat-") and len(a) == 36, f"{a} len {len(a)}")

# --- an intent row must not look like a refusal ----------------------------
rec = inspect.getsource(runner._record)
check("an intent row carries no refusal_reason",
      '("submitted", "intent")' in rec,
      "intent rows would be counted as declines in the refusal census")

# --- and must be invisible to everything that reads the book ---------------
# The whole safety argument for adding a row type mid-flight is that every
# consumer filters on explicit action values. If one ever stops doing that, this
# is where it should be noticed.
import alpha.book as book
import alpha.counterfactual as cf
import alpha.exits as exits
import alpha.fills as fills
import alpha.recovery as recovery

for mod in (book, exits, recovery, fills):
    s = inspect.getsource(mod)
    uses_action = 'action"' in s or "action'" in s
    filters_explicitly = '== "submitted"' in s or '!= "submitted"' in s or 'in ("submitted' in s
    check(f"{mod.__name__.split('.')[-1]} filters on an explicit action",
          (not uses_action) or filters_explicitly,
          "reads action without naming the values it accepts -- an intent row could leak in")

s = inspect.getsource(cf)
check("counterfactual filters on explicit actions",
      'action == "submitted"' in s and 'action in ("submitted"' in s)

# --- the reconciler reports rather than repairs ---------------------------
rc = (ROOT / "scripts" / "reconcile.py").read_text(encoding="utf-8")
check("reconcile never writes to the ledger",
      "ledger.record" not in rc and "ledger.append" not in rc,
      "silently appending to a hash chain is the tampering the chain exists to expose")
check("reconcile distinguishes 'could not ask' from 'not there'", "UNKNOWN" in rc and "unanswered" in rc)
check("reconcile exits non-zero on an unanswered question",
      "return 1 if (found or unknown) else 0" in rc)
check("an empty result is stated, not implied", "NO UNSETTLED INTENTS" in rc)
check("and it says pre-protocol rows are out of scope", "predate the intent-before-POST" in rc)

# --- the venue-side scan, and the two mistakes its first run made ----------
check("there is a venue-side scan at all", "--from-venue" in rc and "_from_venue" in rc,
      "the intent scan cannot see books written before intent rows existed")
check("it matches against ALL ledger rows, not the role-filtered ones",
      "every = ledger.read_all()" in rc and "for r in every" in rc,
      "role-filtering the known-set reported 16 orders as lost when every one was on file; "
      "their rows carry account_role=None")
check("it separates our lost rows from broker-named exits",
      "LOST-ROW" in rc and "broker_named" in rc and "DELETE /v2/positions" in rc,
      "calling a normal close 'foreign' reads as an intrusion")
check("only a lost row exits non-zero", "return 1 if lost else 0" in rc,
      "exiting non-zero on every exit trains the reader to ignore the command")
check("a page-sized result is called truncated", "TRUNCATED" in rc)

print("\n16 checks")
print("ALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
