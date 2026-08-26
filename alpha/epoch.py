"""Ledger EPOCHS -- how a hash chain survives damage without being rewritten.

THE PROBLEM
===========
On 25 Aug 2026, between 15:39:55 and 15:40:31 UTC, two agent loops (`dev` and
`exp1`) appended to one chain with no lock. Six rows broke, two of them
physically spliced mid-JSON. `alpha.ledger._Lock` was added afterwards and is
the correct fix, but it cannot undo the damage: 79.6% of the file sits
downstream of the first break and can never verify back to genesis.

That left `verify_chain` printing the same red line on every pass -- 53+ times
over two days, unread. A permanent red beside real checks teaches the reader to
skim red lines, which is worse than no check at all. CLAUDE.md already names
this: A GATE THAT CANNOT GO GREEN IS A BROKEN GATE.

WHY NOT REPAIR IT
=================
Because repairing a tamper-evident chain is indistinguishable from the tampering
it exists to detect. Rewriting `_prev` on line 1203 would make the file verify
and would destroy the only evidence that anything happened. The damage is a
FACT about this ledger and it stays in the file.

WHAT AN EPOCH IS INSTEAD
========================
An epoch declares: "integrity cannot be established across this boundary, here
is exactly where and why, and here is the chain resuming from the far side."

    epoch 1: lines 1..1202      verifies to genesis
    BOUNDARY: 6 breaks, CONCURRENT_WRITE, cause known and fixed
    epoch 2: lines 1204..EOF    verifies within itself

The boundary record is itself hashed, so an epoch cannot be quietly widened to
swallow a NEW break. That is the property that matters: a break inside a
declared epoch is still red, and only the enumerated historical breaks are
accepted. This does not launder the damage -- it dates it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

ANCHOR = Path(__file__).resolve().parent.parent / "state" / "ledger_epochs.json"


@dataclass(frozen=True)
class Break:
    line: int
    kind: str            # CONCURRENT_WRITE | SERIALIZATION_CHANGE | DATA_CORRUPTION | SOFTWARE_DEFECT | UNKNOWN
    decision_id: str | None
    detail: str


def manifest_hash(name: str, breaks: list[Break]) -> str:
    """Hash of the accepted-break manifest. Widening an epoch changes this."""
    body = json.dumps({"ledger": name,
                       "breaks": [asdict(b) for b in sorted(breaks, key=lambda b: b.line)]},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def load() -> dict[str, Any]:
    if not ANCHOR.exists():
        return {}
    try:
        return json.loads(ANCHOR.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def accepted_breaks(name: str = "decisions") -> dict[int, Break]:
    """Historical breaks this ledger is allowed to carry, keyed by line."""
    rec = load().get(name)
    if not rec:
        return {}
    out: dict[int, Break] = {}
    for b in rec.get("breaks", []):
        out[int(b["line"])] = Break(int(b["line"]), b["kind"], b.get("decision_id"), b["detail"])
    # An anchor whose manifest hash does not match its own contents has been
    # edited by hand. Refuse it rather than honour it -- the whole point is that
    # the accepted list cannot grow silently.
    if rec.get("manifest_hash") != manifest_hash(name, list(out.values())):
        raise ValueError(
            f"EPOCH ANCHOR TAMPERED: {ANCHOR} lists breaks for {name!r} whose manifest hash "
            f"does not match its contents. An epoch may be declared once, from evidence; it "
            f"may not be widened afterwards to absorb a new break.")
    return out
