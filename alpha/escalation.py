"""REPEATED_INVARIANT_ESCALATION -- a warning may not print fifty-three times.

WHAT THIS IS FOR
================
`verify_chain` reported the ledger broken on every pass of every loop for two
days. 53+ occurrences. Nobody investigated it, including me, twice. When it was
finally investigated it took twenty minutes and turned out to be six breaks
rather than one, two of them rows physically lost.

The failure was not inattention. It was that the warning had no way to get
louder. A line that says exactly the same thing on the first occurrence and the
fiftieth is indistinguishable from decoration, and a reader who learns to skim
it has learned correctly -- skimming it cost nothing forty-nine times.

So repetition itself becomes evidence:

    1st occurrence          WARN        something happened
    3rd consecutive         ELEVATED    it is not transient
    10th consecutive        FAIL        it is now a standing defect

A clean observation RESETS the count, so a genuinely transient blip decays
instead of accumulating toward a false alarm.

WHAT ESCALATION IS NOT
======================
It never fixes anything and never suppresses anything. FAIL means a surface a
human reads goes red and stays red until someone either resolves the underlying
problem or records a decision about it -- which for the ledger meant declaring an
epoch, not repairing the chain.

The one thing it must never become is a snooze button. There is deliberately no
"acknowledge" verb here: the only way to clear a count is for the underlying
check to start passing.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STORE = Path(__file__).resolve().parent.parent / "state" / "escalation.json"

OK, WARN, ELEVATED, FAIL = "OK", "WARN", "ELEVATED", "FAIL"

#: Consecutive-failure thresholds. ELEVATED at 3 because two in a row is still
#: plausibly one transient event seen twice; FAIL at 10 because the ledger
#: warning reached 53 and ten is comfortably inside the range where a human
#: should already have looked.
ELEVATE_AT = 3
FAIL_AT = 10


@dataclass
class Escalation:
    key: str
    level: str
    consecutive: int
    total: int
    first_seen: str | None
    last_seen: str | None
    detail: str

    @property
    def red(self) -> bool:
        return self.level == FAIL

    def line(self) -> str:
        if self.level == OK:
            return f"{self.key}: OK"
        n = self.consecutive
        tail = {
            WARN: "first occurrences -- may be transient.",
            ELEVATED: f"{n} IN A ROW -- this is not transient and has not been acted on.",
            FAIL: (f"{n} CONSECUTIVE OCCURRENCES. This is a standing defect, not a warning. "
                   "It cannot be cleared by acknowledging it -- either the check starts "
                   "passing, or a decision about it gets recorded."),
        }[self.level]
        return f"{self.key}: [{self.level}] {self.detail[:120]} ({tail})"


def _load() -> dict[str, Any]:
    if not STORE.exists():
        return {}
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(d: dict[str, Any]) -> None:
    try:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STORE.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
        os.replace(tmp, STORE)
    except OSError:
        pass


def level_for(consecutive: int) -> str:
    if consecutive <= 0:
        return OK
    if consecutive >= FAIL_AT:
        return FAIL
    if consecutive >= ELEVATE_AT:
        return ELEVATED
    return WARN


def observe(key: str, ok: bool, detail: str = "", *, persist: bool = True) -> Escalation:
    """Record one observation of a named invariant and return its escalation.

    `ok=True` RESETS the consecutive count. That is what stops a transient
    network blip from marching toward FAIL over a week, and it is why the count
    is *consecutive* rather than cumulative.
    """
    now = datetime.now(timezone.utc).isoformat()
    d = _load()
    rec = d.get(key) or {"consecutive": 0, "total": 0, "first_seen": None,
                         "last_seen": None, "detail": ""}
    if ok:
        rec["consecutive"] = 0
        rec["first_seen"] = None
        rec["detail"] = ""
    else:
        rec["consecutive"] = int(rec.get("consecutive", 0)) + 1
        rec["total"] = int(rec.get("total", 0)) + 1
        rec["first_seen"] = rec.get("first_seen") or now
        rec["detail"] = detail
    rec["last_seen"] = now
    d[key] = rec
    if persist:
        _save(d)
    return Escalation(key=key, level=level_for(rec["consecutive"]),
                      consecutive=rec["consecutive"], total=rec["total"],
                      first_seen=rec["first_seen"], last_seen=rec["last_seen"],
                      detail=rec["detail"])


def status(key: str) -> Escalation | None:
    rec = _load().get(key)
    if not rec:
        return None
    return Escalation(key=key, level=level_for(rec.get("consecutive", 0)),
                      consecutive=rec.get("consecutive", 0), total=rec.get("total", 0),
                      first_seen=rec.get("first_seen"), last_seen=rec.get("last_seen"),
                      detail=rec.get("detail", ""))


def all_status() -> list[Escalation]:
    return [e for e in (status(k) for k in sorted(_load())) if e]


def standing_defects() -> list[Escalation]:
    """Everything at FAIL. These are the things that have been ignored longest."""
    return [e for e in all_status() if e.red]
