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
import time
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
    account_role: str | None = None
    """Which paper account made this decision. Two accounts run champion vs
    challenger against the same sessions; without this field their rows are
    indistinguishable and the comparison is impossible."""

    entry_cost_per_unit: float | None = None
    max_loss_per_unit: float | None = None
    legs: tuple = ()
    """The structure at UNIT scale, recorded on every row including refusals.

    `max_loss_usd` is the position we sized; these three are the thing itself.
    Without them a refused candidate cannot be priced forward later, and a
    refusal nobody can price is a claim of prudence rather than a measurement of
    one -- see `alpha/counterfactual.py`."""


def _path(name: str = "decisions") -> Path:
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    return LEDGER_DIR / f"{name}.jsonl"


def _last_hash(path: Path) -> str:
    if not path.exists():
        return GENESIS
    # Read only the TAIL. Scanning the whole file on every append made the
    # counterfactual ledger quadratic: two loops recording ~5,000 marks each at
    # the same hour held the lock past its timeout (26 Aug 04:00 HK).
    size = path.stat().st_size
    if size == 0:
        return GENESIS
    with path.open("rb") as fh:
        chunk = 1 << 16
        while True:
            start = max(size - chunk, 0)
            fh.seek(start)
            data = fh.read(size - start)
            lines = [l for l in data.split(b"\n") if l.strip()]
            # need the full last line: either we reached the file start, or the
            # chunk holds at least two line breaks so the last line is complete
            if start == 0 or data.count(b"\n") >= 2:
                if not lines:
                    return GENESIS
                return hashlib.sha256(lines[-1] + b"\n").hexdigest()
            chunk *= 4


class _Lock:
    """Exclusive cross-process lock on a ledger: O_EXCL create of a side file,
    retried; a lock older than STALE_S is assumed abandoned by a dead writer.

    Two loops (dev and exp1) appended to the same chain on 25 Aug and it broke
    at line 1203: writer A read the last hash, writer B appended, writer A
    appended with the wrong `_prev`. A hash chain assumes one writer; this
    makes that true instead of assuming it.
    """
    STALE_S = 30.0

    def __init__(self, path: Path):
        self.lock = path.with_suffix(path.suffix + ".lock")

    def __enter__(self):
        deadline = time.monotonic() + 120.0
        while True:
            try:
                fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except (FileExistsError, PermissionError):
                # Windows reports a contested O_EXCL create as EACCES, not EEXIST.
                try:
                    if time.time() - self.lock.stat().st_mtime > self.STALE_S:
                        self.lock.unlink(missing_ok=True)
                        continue
                except OSError:
                    continue
                if time.monotonic() > deadline:
                    raise TimeoutError(f"ledger lock {self.lock} held for >120s")
                time.sleep(0.05)

    def __exit__(self, *exc):
        try:
            self.lock.unlink(missing_ok=True)
        except OSError:
            pass


def record(decision: Decision, *, name: str = "decisions") -> str:
    """Append one row and return its hash. Never modifies an existing line."""
    path = _path(name)
    row = asdict(decision)
    with _Lock(path):
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
    out, bad = [], []
    with path.open(encoding="utf-8") as fh:
        for i, l in enumerate(fh, start=1):
            if not l.strip():
                continue
            try:
                out.append(json.loads(l))
            except ValueError:
                bad.append(i)
    if bad:
        # Lines interleaved by two unlocked writers on 25 Aug. The file is never
        # rewritten (tamper-evidence); the damage is COUNTED and surfaced.
        MALFORMED[name] = bad
    return out


#: name -> line numbers that could not be parsed on the last read_all().
MALFORMED: dict[str, list[int]] = {}


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
            try:
                row = json.loads(raw)
            except ValueError:
                return False, f"chain breaks at line {i}: the line is not JSON (interleaved write)."
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
