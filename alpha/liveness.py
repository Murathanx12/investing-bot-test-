"""LOOP_LIVENESS_v1 -- a stopped loop must not read like a quiet market.

THE FAILURE THIS EXISTS FOR
===========================
On 26 Aug a DNS blip killed both paper loops mid-session. Nothing announced it.
The log simply stopped, and a stopped log is byte-for-byte indistinguishable
from a market where nothing happened to be worth trading. Session 9 hit the same
death and never traced the cause; it went unnoticed for days both times.

The transport now converts `URLError/TimeoutError/OSError` into `BrokerRefusal`
and the supervisor wraps each cycle with backoff. Both are necessary. Neither
tells anyone the loop is gone, because a dead process cannot report its own
death. **Silence has to become a positive statement, made by something else.**

WHY THERE IS NO WATCHDOG DAEMON
===============================
The obvious design is a second process that checks the first. On this machine
that is another Python process that can die of the same DNS blip, in which case
the watchdog's silence means nothing either -- the original bug reproduced one
level up, now with a false sense of coverage.

So liveness here is **PULL-BASED FROM A SURFACE ALREADY BEING READ**. The loop
writes a receipt at every completed cycle; `scripts.dashboard` and
`scripts.liveness` read it, and both are things a human already opens. Nothing
runs in the background to make this work, so nothing in the background can fail
silently and take the guarantee with it.

THE PID PROBE, AND WHY IT IS NOT `os.kill`
==========================================
Measured on this machine, 2026-08-26, against a process killed and reaped one
second earlier:

    os.kill(pid, 0)   known-alive -> ALIVE     known-dead -> **ALIVE**
    tasklist          known-alive -> ALIVE     known-dead -> DEAD

`os.kill(pid, 0)` reports a DEAD process as alive on Windows. That is the
dangerous direction: a watchdog built on it certifies a dead loop as healthy,
which is precisely the failure being fixed. Git Bash `kill -0` is worse still --
it cannot see native Windows PIDs at all and reports every live process as dead.

So the probe is `tasklist` on Windows and `os.kill` only on POSIX, where it is
genuinely a probe. When neither is available the answer is **None -- CANNOT
DETERMINE** -- and the status is UNKNOWN rather than a guess in either
direction. A guard derives its inputs or refuses.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BEAT_DIR = Path(__file__).resolve().parent.parent / "state" / "liveness"

#: A cycle is not late until longer than the longest job it may be running.
#: `scripts.run_pass` is allowed 1500s by `agent_loop.TIMEOUTS_S`, so anything
#: under that is a loop working, not a loop hung. 35 minutes leaves margin for
#: the kill path and the next cycle to start.
STALE_AFTER_S = 2100.0

HEALTHY, DEGRADED, STALE, DEAD, UNKNOWN = "HEALTHY", "DEGRADED", "STALE", "DEAD", "UNKNOWN"

#: A loop that was started BEFORE the heartbeat existed cannot emit one, and
#: will not until the next restart. Reporting that as UNKNOWN-and-therefore-red
#: would create exactly the defect this project keeps paying for: a red line no
#: action available today can clear, printed on every dashboard render, training
#: its reader to skim red lines.
#:
#: The process table still answers the question that matters. Finding ZERO
#: `agent_loop` processes is what proved both loops dead on 26 Aug; finding as
#: many as we expect is the same evidence pointing the other way. What it cannot
#: do is attribute a process to an ACCOUNT ROLE -- the role lives in the
#: environment, not the command line -- so this state is never called HEALTHY.
#: It is called what it is, and it disappears at the next restart.
PRE_HEARTBEAT = "PRE-BEAT"

#: sentinel: "call the real process table", distinct from an injected None
#: (which means "the process table could not be read").
_USE_REAL_SCAN = object()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def pid_alive(pid: int) -> bool | None:
    """True / False / None, where None means CANNOT DETERMINE.

    Never `os.kill` on Windows: it reports dead processes as alive (measured),
    and for signals other than 0 CPython routes it to TerminateProcess -- a
    liveness probe that can kill what it is probing.
    """
    if pid <= 0:
        return False
    if platform.system() == "Windows":
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"],
                                 capture_output=True, text=True, timeout=20).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        # tasklist prints an INFO line when nothing matches, and the row itself
        # when something does. Matching on the pid as a token avoids counting
        # the pid echoed back inside the filter text.
        return any(str(int(pid)) in line.split() for line in out.splitlines())
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True          # exists, owned by someone else
    except OSError:
        return None


@dataclass
class Beat:
    role: str
    pid: int
    cycle: int = 0
    started_utc: str | None = None
    completed_utc: str | None = None
    last_broker_ok_utc: str | None = None
    last_error: str | None = None
    consecutive_errors: int = 0
    backoff_until_utc: str | None = None
    commit: str | None = None
    expiry: str | None = None
    live: bool = False
    argv: list[str] = field(default_factory=list)
    failing_steps: dict[str, int] = field(default_factory=dict)
    """Sub-steps exiting non-zero, and for how many cycles in a row.

    A loop can cycle perfectly while the step that places orders refuses on
    every pass -- a bad --expiry, an unverified genesis, a missing window
    universe. The heartbeat said HEALTHY throughout, because from the loop's
    point of view nothing was wrong: `_run` returns an exit code and every
    caller discards it. A refusing pass reads exactly like a quiet market, which
    is the same shape as the dead loops on 26 Aug."""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _path(role: str) -> Path:
    return BEAT_DIR / f"{role or 'unset'}.json"


def write(beat: Beat) -> None:
    """Atomic, so a reader never sees a half-written receipt."""
    p = _path(beat.role)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(beat.as_dict(), indent=1), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        # A loop must never die because it could not write its own heartbeat.
        pass


def read(role: str) -> Beat | None:
    p = _path(role)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    known = {f for f in Beat.__dataclass_fields__}
    return Beat(**{k: v for k, v in d.items() if k in known})


def _age_s(stamp: str | None, now: datetime) -> float | None:
    if not stamp:
        return None
    try:
        return (now - datetime.fromisoformat(stamp)).total_seconds()
    except ValueError:
        return None


def status(role: str, *, now: datetime | None = None,
           stale_after_s: float = STALE_AFTER_S) -> tuple[str, str]:
    """Classify one loop. Returns (state, a sentence saying why)."""
    now = now or _now()
    beat = read(role)
    if beat is None:
        return UNKNOWN, (f"no heartbeat receipt for role {role!r}. Either the loop has never run "
                         f"since liveness was added, or it died before its first cycle. "
                         f"CANNOT DETERMINE -- this is not evidence of health.")

    alive = pid_alive(beat.pid)
    age = _age_s(beat.completed_utc, now)
    started_age = _age_s(beat.started_utc, now)

    if alive is False:
        return DEAD, (f"pid {beat.pid} is NOT running. Last completed cycle "
                      f"{beat.cycle} was {_fmt(age)} ago"
                      + (f"; last error: {beat.last_error[:120]}" if beat.last_error else "")
                      + ". The loop is gone and the log stopping did not say so.")
    if alive is None:
        return UNKNOWN, (f"cannot determine whether pid {beat.pid} is running on this platform. "
                         f"Last completed cycle {beat.cycle}, {_fmt(age)} ago. Refusing to "
                         f"report health from an undetermined probe.")

    if age is None:
        return STALE, (f"pid {beat.pid} is running but has never completed a cycle "
                       f"(started {_fmt(started_age)} ago).")
    if age > stale_after_s:
        return STALE, (f"pid {beat.pid} is running but its last completed cycle was "
                       f"{_fmt(age)} ago, past the {_fmt(stale_after_s)} ceiling. A live "
                       f"process that is not cycling is not a working loop.")

    backoff = _age_s(beat.backoff_until_utc, now)
    if beat.consecutive_errors > 0 or (backoff is not None and backoff < 0):
        return DEGRADED, (f"pid {beat.pid} is cycling ({_fmt(age)} since cycle {beat.cycle}) but "
                          f"carries {beat.consecutive_errors} consecutive error(s)"
                          + (f", backing off for {_fmt(-backoff)}" if backoff is not None and backoff < 0 else "")
                          + (f"; last: {beat.last_error[:120]}" if beat.last_error else "") + ".")
    if beat.failing_steps:
        worst = ", ".join(f"{m} x{n}" for m, n in sorted(
            beat.failing_steps.items(), key=lambda kv: -kv[1]))
        return DEGRADED, (f"pid {beat.pid} is cycling ({_fmt(age)} since cycle {beat.cycle}) "
                          f"but a sub-step keeps exiting non-zero: {worst}. The loop is fine "
                          "and the work is not happening -- run the step by hand and read "
                          "the refusal.")
    return HEALTHY, (f"pid {beat.pid} completed cycle {beat.cycle} {_fmt(age)} ago"
                     + (f", expiry {beat.expiry}" if beat.expiry else "")
                     + (", LIVE" if beat.live else ", dry") + ".")


def _fmt(sec: float | None) -> str:
    if sec is None:
        return "never"
    sec = abs(sec)
    if sec < 90:
        return f"{sec:.0f}s"
    if sec < 5400:
        return f"{sec/60:.0f}m"
    return f"{sec/3600:.1f}h"


def roles() -> list[str]:
    if not BEAT_DIR.exists():
        return []
    return sorted(p.stem for p in BEAT_DIR.glob("*.json"))


def report(expected: tuple[str, ...] = ("dev", "exp1"), *,
           now: datetime | None = None,
           scan: "tuple[int, list[str]] | None | object" = _USE_REAL_SCAN,
           ) -> tuple[bool, list[str]]:
    """(all_healthy, lines). Roles that were EXPECTED and have no receipt are
    reported, because a missing role is the loudest case and the one a listing
    of present files would silently omit."""
    now = now or _now()
    lines, ok = [], True
    for role in sorted(set(expected) | set(roles())):
        st, why = status(role, now=now)
        if st != HEALTHY:
            ok = False
        lines.append(f"{role:6s} {st:8s} {why}")
    if not lines:
        return False, ["no loops and no expectations -- nothing was checked, "
                       "which is not the same as nothing being wrong."]

    # The independent check, always printed. A heartbeat can only speak for
    # loops started after it existed; the process table speaks for all of them,
    # and counting command lines is what caught the 26 Aug death.
    # The scan is injectable so this function is testable. Reading the real
    # process table inside a test makes the verdict depend on whatever happens
    # to be running on the machine -- the ambient-environment defect that made
    # two other tests in this suite pass for the wrong reason.
    scanned = scan_processes() if scan is _USE_REAL_SCAN else scan
    if scanned is None:
        lines.append("scan   UNKNOWN  the process table could not be read; the heartbeat above "
                     "is the only evidence, and it cannot see pre-heartbeat loops.")
        return False, lines

    n, cmds = scanned
    lines.append(f"scan   {'OK  ' if n else 'NONE'}     {n} agent_loop process(es) in the OS "
                 f"process table (roles not resolvable from a command line).")
    for c in cmds:
        lines.append(f"         {c[:150]}")
    if n == 0:
        # Zero processes is decisive whatever the receipts say, and it is the
        # observation that actually caught the 26 Aug death.
        return False, lines

    # EVERY expected role unreceipted, but the processes are there: these are
    # loops predating the heartbeat. Say so precisely instead of crying wolf.
    unreceipted = [r for r in expected if read(r) is None]
    if unreceipted and len(unreceipted) == len(expected) and n >= len(expected):
        rewritten = []
        for line in lines:
            role = line.split()[0] if line.split() else ""
            if role in unreceipted:
                rewritten.append(
                    f"{role:6s} {PRE_HEARTBEAT:8s} started before the heartbeat existed, so it "
                    f"cannot emit one until the next restart. Not confirmed alive BY ROLE.")
            else:
                rewritten.append(line)
        rewritten.append(
            f"note   {n} loop process(es) are running, which is the evidence that proved both "
            f"loops DEAD on 26 Aug, read in the other direction. What it cannot do is attribute a "
            f"process to an account role. Liveness becomes authoritative at the next restart.")
        return True, rewritten
    return ok, lines

def scan_processes(needle: str = "agent_loop") -> tuple[int, list[str]] | None:
    """How many loop processes exist, read from the OS process table.

    The heartbeat is the primary signal, but it only exists for loops STARTED
    after it was added, and a loop that dies before its first beat leaves no
    receipt at all. This is the independent check -- and it is the one that
    actually caught the 26 Aug death, when counting `agent_loop` command lines
    found ZERO while the log looked merely quiet.

    Returns (count, command lines) or None if the process table is unreadable.
    Roles are NOT resolvable this way: the account role lives in the
    environment, not the command line, so this answers "how many loops" and
    never "which account". Reported as such rather than guessed.
    """
    if platform.system() == "Windows":
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
               "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
               "Select-Object -ExpandProperty CommandLine"]
    else:
        cmd = ["ps", "-eo", "args"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    hits = [l.strip() for l in out.splitlines() if needle in l and "scripts.liveness" not in l]
    return len(hits), hits

