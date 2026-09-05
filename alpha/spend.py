"""A paid call must name the decision it can change, or it does not happen.

WHY THIS EXISTS
===============
Night session 11 ran four experiments, closed two decisions and opened two more,
for **$0.00** -- every test was bars plus arithmetic. That was reported as an
achievement. It should be the default, and the way to make it the default is to
require the justification at the call site rather than to admire the total
afterwards.

The rule, from the continuation brief: **every paid LLM call carries a
`WHY_THIS_CALL_CAN_CHANGE_A_DECISION` field. If the field cannot be filled, the
call is refused.** Not logged, not warned about -- refused. A call that cannot
name a decision it might change is, by construction, a call whose answer nobody
will act on, and the money is the smallest part of what it costs: it also
produces a plausible paragraph that then gets treated as evidence.

WHAT COUNTS, AND WHAT THE GATE ACTUALLY CATCHES
===============================================
The gate cannot judge whether a justification is TRUE. It catches the three
failures that are mechanically detectable and that account for most of them:

- **absent** -- nobody thought about it;
- **too short to be a reason** -- "research", "analysis", "context";
- **naming no decision** -- prose that describes the SUBJECT rather than what
  would be done differently. So the text must contain a decision verb.

That is a low bar on purpose. A gate strict enough to judge reasoning would be
wrong often enough that people would route around it, and a gate routed around
is worse than none. This one costs a sentence and refuses the reflex.

IT IS ALSO THE SPEND LEDGER
===========================
Every permitted call appends to `state/llm_spend.jsonl` with its justification,
token usage and measured latency. The provider's own balance remains the
economic truth -- our telemetry has been wrong before -- but a per-call ledger
answers the question the balance cannot: *what was the money asked to decide?*
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alpha.sources.http import SourceRefusal, post_json

LEDGER = Path(__file__).resolve().parent.parent / "state" / "llm_spend.jsonl"


def ledger_path() -> Path:
    """Where the spend ledger is written and read, resolved AT CALL TIME.

    IN PRODUCTION THIS IS UNCHANGED, deliberately: `state/llm_spend.jsonl`, the
    same absolute path it has always been. Moving a budget gate's input is how
    `spent_usd()` once read absence as $0.00 and re-authorised $30 that had
    already been spent (feedback: "a docs move disarmed a budget gate"), so this
    function does NOT follow `AAT_LEDGER_DIR` the way the decisions ledger does.

    UNDER `AAT_TEST_MODE` it is redirected to `AAT_LEDGER_DIR`. Measured
    2026-09-05: two ordinary `python run_tests.py` runs appended rows with
    `caller: "tests.smoke"` to the REAL spend ledger -- fictional usage inside
    the file that decides whether a real LLM call is affordable. The venue guard
    lives at the socket for the same reason this lives here: only the process's
    own environment can stop a child, and a suite that plants a fake row is
    indistinguishable afterwards from a call that happened.
    """
    import os

    if os.getenv("AAT_TEST_MODE", "").strip().lower() in ("1", "true", "yes"):
        base = os.getenv("AAT_LEDGER_DIR")
        if base:
            return Path(base) / "llm_spend.jsonl"
    return LEDGER

#: A justification shorter than this is a label, not a reason.
MIN_CHARS = 30

#: The text must say what would be DONE differently. Not a whitelist of good
#: reasons -- a check that a decision is referred to at all.
_DECISION_WORDS = re.compile(
    r"\b(decide|decides|decision|choose|chooses|whether|refuse|refuses|promote|"
    r"promotes|reject|rejects|size|sizes|enter|enters|exit|exits|trade|trades|"
    r"grade|grades|rank|ranks|select|selects|build|builds|kill|kills|close|"
    r"closes|open|opens|resolve|resolves|prioritis|prioritiz|abstain|skip)\w*",
    re.I)


class SpendRefusal(SourceRefusal):
    """Raised instead of spending. Subclasses `SourceRefusal` deliberately, so
    every existing caller's error handling already covers it -- a new exception
    type would have turned a refusal into a crash in four places."""


def justify(why: str, *, caller: str = "") -> str:
    """Validate a justification, or refuse. Returns the cleaned text."""
    text = (why or "").strip()
    where = f" ({caller})" if caller else ""
    if not text:
        raise SpendRefusal(
            f"REFUSED{where}: no WHY_THIS_CALL_CAN_CHANGE_A_DECISION. A paid call "
            "must name the decision it could change. If it cannot, the answer is "
            "one nobody will act on.")
    if len(text) < MIN_CHARS:
        raise SpendRefusal(
            f"REFUSED{where}: {text!r} is {len(text)} chars -- a label, not a reason. "
            f"Name the decision and what a different answer would change "
            f"(>= {MIN_CHARS} chars).")
    if not _DECISION_WORDS.search(text):
        raise SpendRefusal(
            f"REFUSED{where}: {text!r} describes the subject but names no DECISION. "
            "Say what would be done differently -- what gets built, refused, sized, "
            "graded, ranked or skipped depending on the answer.")
    return text


def record(caller: str, why: str, *, usage: dict[str, Any] | None = None,
           seconds: float | None = None, model: str = "", note: str = "") -> None:
    """Append one permitted call to the spend ledger."""
    row = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "caller": caller, "model": model,
        "why_this_call_can_change_a_decision": why,
        "usage": usage or {}, "seconds": round(seconds, 2) if seconds else None,
        "note": note,
    }
    try:
        _led = ledger_path()
        _led.parent.mkdir(parents=True, exist_ok=True)
        with _led.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass  # a ledger that cannot be written must not cancel work already paid for


def llm_post(url: str, body: Any, *, why: str, caller: str,
             headers: dict | None = None, timeout: float = 90.0) -> tuple[Any, float]:
    """`post_json` with the justification gate in front and the ledger behind.

    The gate runs BEFORE the request, so a refused call costs nothing.
    """
    why = justify(why, caller=caller)
    data, dt = post_json(url, body, headers=headers, timeout=timeout)
    record(caller, why, usage=(data or {}).get("usage"), seconds=dt,
           model=str((body or {}).get("model", "")))
    return data, dt


def summary(limit: int | None = None) -> dict[str, Any]:
    """What the money was asked to decide, by caller."""
    _led = ledger_path()
    if not _led.exists():
        return {"calls": 0, "by_caller": {}, "note": "no paid calls recorded"}
    rows = [json.loads(line) for line in
            _led.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = rows[-limit:] if limit else rows
    by: dict[str, dict[str, Any]] = {}
    for r in rows:
        b = by.setdefault(r["caller"], {"calls": 0, "prompt_tokens": 0,
                                        "completion_tokens": 0, "reasons": []})
        b["calls"] += 1
        u = r.get("usage") or {}
        b["prompt_tokens"] += int(u.get("prompt_tokens") or 0)
        b["completion_tokens"] += int(u.get("completion_tokens") or 0)
        if r["why_this_call_can_change_a_decision"] not in b["reasons"]:
            b["reasons"].append(r["why_this_call_can_change_a_decision"])
    return {"calls": len(rows), "by_caller": by,
            "note": "token counts are OUR telemetry; the provider's balance is the "
                    "economic truth and has disagreed before"}
