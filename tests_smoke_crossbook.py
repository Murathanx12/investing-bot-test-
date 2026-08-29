"""ONE BET, ONE INSTRUMENT -- the convex book vs what the fleet already holds.

Run: python tests_smoke_crossbook.py  (also executed by tests_smoke.py)

28 Aug: hack3 bought twelve theme names in shares and hack5 bought five 5-DTE
calls on the SAME names. Reported as two independent selectors; lost -8.9% and
-8.6% on one afternoon. These pin the refusal, the READ-ONLY handle (this is
the only place a process holds another account's keys), and -- the part that
matters most -- that an UNREADABLE peer prints differently from a flat one.
"""
from __future__ import annotations

import os

os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import config, crossbook, fleet


class FakePeer:
    def __init__(self, rows):
        self._rows = rows
        self.calls = 0

    def positions(self):
        self.calls += 1
        return self._rows


def opener(mapping):
    def _open(role):
        rows = mapping.get(role)
        return None if rows is None else crossbook.PeerBook(role, FakePeer(rows))
    return _open


print("\n-- who counts as a peer")
peers = crossbook.peer_roles("hack5")
check("the convex book's peers are the share-expressing books",
      "hack3" in peers and "hack1" in peers, str(peers))
check("a book is never its own peer", "hack5" not in peers, str(peers))
check("and the convex book is nobody's share peer",
      all(fleet.FLEET[r].profile != "convex" for r in peers), str(peers))

print("\n-- the refusal, when the peers can actually be read")
held, notes = crossbook.held_by_peers("hack5", opener=opener({
    "hack1": [{"symbol": "SPY"}],
    "hack2": [],
    "hack3": [{"symbol": "QS"}, {"symbol": "SMR"}],
    "hack4": [{"symbol": "NVDA260904C00200000"}],
    "hack6": [{"symbol": "QS"}],
}))
check("share and option positions both resolve to the UNDERLYING",
      held == {"SPY", "QS", "SMR", "NVDA"}, str(sorted(held)))
check("a name the basket book holds is refused on the convex book",
      crossbook.overlap_refusal("QS", held, notes) is not None)
check("the refusal names the date and the arithmetic, not just 'no'",
      "28 Aug" in crossbook.overlap_refusal("QS", held, notes)
      and "8.9%" in crossbook.overlap_refusal("QS", held, notes))
check("a name nobody holds is not refused", crossbook.overlap_refusal("IONQ", held, notes) is None)
check("an empty book is read and reported as read, not as unreadable",
      any(n.startswith("read:hack2") for n in notes), str(notes))
check("the status says how many books were actually seen",
      crossbook.status(held, notes).startswith("read 5 peer book(s)"),
      crossbook.status(held, notes))

print("\n-- an UNREADABLE peer is a STATE, and it must not print like a flat one")
held2, notes2 = crossbook.held_by_peers("hack5", opener=opener({}))   # no keys for anyone
check("no keys -> nothing held", held2 == set())
check("...but every blind peer is NAMED",
      all(n.startswith("UNREADABLE:") for n in notes2) and len(notes2) == len(peers), str(notes2))
check("the status is CANNOT DETERMINE, not 'clear'",
      crossbook.status(held2, notes2).startswith("CANNOT DETERMINE"),
      crossbook.status(held2, notes2)[:60])
check("and it says WHY, and where to get the number",
      "only its own key pair" in crossbook.status(held2, notes2)
      and "--overlap" in crossbook.status(held2, notes2))
check("CANNOT DETERMINE does not refuse -- a gate that can never go green is broken",
      crossbook.overlap_refusal("QS", held2, notes2) is None)

partial = dict.fromkeys(peers, None)
partial["hack3"] = [{"symbol": "QS"}]
held3, notes3 = crossbook.held_by_peers("hack5", opener=opener({k: v for k, v in partial.items() if v is not None}))
check("one readable peer among blind ones still refuses on what it saw",
      crossbook.overlap_refusal("QS", held3, notes3) is not None)
check("and the status says it was BLIND to the rest",
      "BLIND to 4" in crossbook.status(held3, notes3), crossbook.status(held3, notes3))


class Boom:
    def positions(self):
        raise TimeoutError("venue timed out")


held4, notes4 = crossbook.held_by_peers("hack5", opener=lambda r: crossbook.PeerBook(r, Boom()))
check("a peer that ERRORS is named with its error, never counted as flat",
      all(n.startswith("ERROR:") and "TimeoutError" in n for n in notes4), str(notes4[:1]))
check("and an errored read leaves nothing to refuse on",
      held4 == set() and crossbook.status(held4, notes4).startswith("CANNOT DETERMINE"))

print("\n-- the peer handle can READ and can do nothing else")
pb = crossbook.PeerBook("hack3", FakePeer([{"symbol": "QS"}]))
surface = [a for a in dir(pb) if not a.startswith("_")]
check("its whole public surface is `positions` and `role`",
      sorted(surface) == ["positions", "role"], str(sorted(surface)))
for verb in ("submit_order", "submit_protective_stop", "cancel_order", "close_position",
             "close_all_positions", "_request"):
    check(f"it cannot {verb}", not hasattr(pb, verb))
check("it is __slots__-ed, so an ordering method cannot be attached to it later",
      not hasattr(pb, "__dict__"))

print("\n-- the read-only credential door refuses the same things the order door does")
try:
    config.peer_credentials("not a role!!")
    check("a bad role name is refused", False)
except config.CredentialRefusal as exc:
    check("a bad role name is refused", "not a role" in str(exc), str(exc)[:60])
try:
    config.peer_credentials("hack3" if not os.getenv("AAT_HACK3_KEY_ID") else "nokeysrole")
    check("a role with no key pair is refused, and the refusal explains Railway", False)
except config.CredentialRefusal as exc:
    check("a role with no key pair is refused, and the refusal explains Railway",
          "CANNOT DETERMINE" in str(exc) and "only its own keys" in str(exc), str(exc)[:80])

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
