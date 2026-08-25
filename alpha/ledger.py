"""The append-only record of every decision, including the ones we did not take.

WHY THE REJECTED CANDIDATES ARE THE POINT
=========================================
A trading log that contains only executed orders can answer "how did we do?"
and nothing else. It cannot answer the question that makes this week worth
anything to the research project afterwards:

    given what was knowable at t, what action, what ALTERNATIVE, what
    happened, why, and what should change?

The parent project's fourth standing rule is *study losers as hard as winners*,
and its informative unit is a winner beside a MATCHED loser -- never a gallery
of survivors. A rejected candidate that later moved 12% is the most valuable row
in this file, and it only exists if the refusal was written down at the moment
it was made, with the reason and the quote that justified it.

So every candidate is recorded whether it traded or not, and the refusal reason
is a first-class field rather than an absence.

WHY JSONL AND WHY APPEND-ONLY
=============================
The competition record has to be tamper-evident: a P&L number is a claim, and a
claim that could have been edited after the outcome was known is worth nothing
to the judges and less to us. Lines are appended, never rewritten; each carries
the hash of the previous line, so a single altered row breaks the chain and
`verify_chain()` says exactly where.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER_DIR = Path(os.getenv("AAT_LEDGER_DIR", Path(__file__).resolve().parent.parent / "state"))

#: The genesis link. A chain that started from an empty string would validate
#: against a file someone truncated to zero rows.
GENESIS = "aegis-alpha-terminal/v1"


@dataclass
class Decision:
    """One candidate considered at one moment. Traded or refused."""

    decision_id: str
    ts_utc: str
    symbol: str
    brain: str
    """Which mechanism proposed this -- event, tail_momentum, dispersion,
    global_relay, crypto. Named so attribution afterwards is a groupby and not
    an archaeology project."""
    signal_shape: str | None
    instrument: str
    thesis: str
    predicted_move: float | None
    predicted_sd: float | None
    implied_move: float | None
    breakeven_move: float | None
    mdm_edge: float | None
    quote_snapshot: dict[str, Any]
    """Bid, ask, sizes and timestamp of what we actually saw. Never a mid."""
    action: str                       # "submitted" | "refused" | "closed"
    refusal_reason: str | None
    risk_fraction: float
    max_loss_usd: float
    order: dict[str, Any] | None
    alpaca_order_id: str | None = None
    fill: dict[str, Any] | None = None
    outcome: dict[str, Any] | None = None
    llm: dict[str, Any] | None = None
    """Model, tokens and cost for any LLM reasoning behind this row. Spend that
    is not attributed to a decision is spend nobody can evaluate."""
    tournament_state: dict[str, Any] = field(default_factory=dict)


def _path(name: str = "decisions") -> Path:
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    return LEDGER_DIR / f"{name}.jsonl"


def _last_hash(path: Path) -> str:
    if not path.exists():
        return GENESIS
    last = None
    with path.open("rb") as fh:
        for line in fh:
            if line.strip():
                last = line
    if last is None:
        return GENESIS
    return hashlib.sha256(last).hexdigest()


def record(decision: Decision, *, name: str = "decisions") -> str:
    """Append one row and return its hash. Never modifies an existing line."""
    path = _path(name)
    row = asdict(decision)
    row["_prev"] = _last_hash(path)
    row["_written_utc"] = datetime.now(timezone.utc).isoformat()
    line = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return hashlib.sha256((line + "\n").encode()).hexdigest()


def read_all(name: str = "decisions") -> list[dict[str, Any]]:
    path = _path(name)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def verify_chain(name: str = "decisions") -> tuple[bool, str]:
    """Walk the hash chain. Returns (ok, message naming the first broken row)."""
    path = _path(name)
    if not path.exists():
        return True, "no ledger yet"
    prev = GENESIS
    with path.open("rb") as fh:
        for i, raw in enumerate(fh, start=1):
            if not raw.strip():
                continue
            row = json.loads(raw)
            if row.get("_prev") != prev:
                return False, (
                    f"chain breaks at line {i} (decision_id="
                    f"{row.get('decision_id')!r}): recorded _prev "
                    f"{row.get('_prev')!r} != computed {prev!r}."
                )
            prev = hashlib.sha256(raw).hexdigest()
    return True, f"chain intact, head={prev[:16]}"


def new_decision_id(symbol: str, brain: str, ts: datetime | None = None) -> str:
    """Stable within a decision, distinct across them.

    Deliberately derived from (symbol, brain, minute) rather than a random uuid:
    two runs of the same loop in the same minute over the same candidate are the
    SAME decision, and should collide at the broker rather than open the
    position twice. Restart-safety comes from this line.
    """
    stamp = (ts or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M")
    return f"{stamp}:{brain}:{symbol}"
