"""PULL_JOURNAL -- the on-disk memory of a long network pull, so a kill costs one unit.

WHY THIS EXISTS (measured, 2026-09-07 03:18)
============================================
`scripts.news_backfill` ran overnight against a 134-month window and DIED at
03:18 with the Alpaca leg 112 months in. There was:

  * no cursor  -> nothing to resume from, so the 112 months of API work were
                  repeated-or-abandoned rather than continued;
  * no log     -> the only record was a terminal scrollback that was gone, so
                  nobody could say WHY it stopped or even WHEN;
  * no PID file-> nobody could kill it deliberately, and nobody could tell
                  whether a second run would collide with a first;
  * one receipt at the END -> a run that never reaches the end produces no
                  evidence at all, which is how "83.6% done" got quoted in a
                  document with no derivation behind it.

Four artefacts, four fixes, and they are the whole of this module:

    state/pulls/<run_id>/cursor.json          what is DONE, what is PARTIAL
    state/pulls/<run_id>/run.log              every line, timestamped, on disk
    state/pulls/<run_id>/run.pid              who owns this run right now
    state/pulls/<run_id>/months/<M>.<leg>.json  a receipt PER MONTH

A run_id is derived from the job (source, window, universe), so a resume is
`run the same command again` -- there is no id to remember and no flag to
forget. Re-running is SAFE because the corpus dedupes on `uid`: a month that
was half-stored costs a few duplicate fetches, never a duplicate row.

WHAT A CURSOR IS NOT
====================
It is not a claim that the data is good. It records what was ATTEMPTED and
what came back, including the HTTP errors by status, so "this month is done"
and "this month is done and full" stay different sentences. The per-month
receipt carries the counts; the E3 coverage gate reads THOSE, not the cursor.

CONCURRENCY
===========
One process owns a run at a time. `open()` REFUSES if the pid file names a
process that is still alive -- it does not kill it (killing by anything but a
PID you wrote down yourself is how three agents' work died on 2026-09-06), and
it does not silently proceed, because two writers into `corpus.uid_index.json`
end in last-writer-wins and a re-admitted year of duplicates.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
STATE = Path(os.getenv("AAT_STATE_DIR", str(ROOT / "state")))
PULLS = STATE / "pulls"

SCHEMA = "pull_journal/1"

#: `HTTP 429`, `HTTP 403`... out of a BrokerRefusal / SourceRefusal message.
_HTTP_CODE = re.compile(r"HTTP\s+(\d{3})")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def error_class(msg: str) -> str:
    """The bucket an error counts into: an HTTP status, or the transport."""
    m = _HTTP_CODE.search(msg or "")
    if m:
        return m.group(1)
    if "transport failure" in (msg or ""):
        return "transport"
    if "timed out" in (msg or "").lower():
        return "timeout"
    return "other"


def tally(counts: dict[str, int], messages: Iterable[str]) -> dict[str, int]:
    for m in messages:
        k = error_class(str(m))
        counts[k] = counts.get(k, 0) + 1
    return counts


def pid_alive(pid: int) -> bool:
    """True if a process with this pid exists. Never signals it.

    `os.kill(pid, 0)` is the POSIX idiom and is NOT safe on Windows, where
    CPython implements os.kill for a non-CTRL signal as TerminateProcess --
    a liveness probe that kills the thing it is probing. This repo runs on
    Windows, so the win32 branch opens a handle and closes it instead.
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":
        SYNCHRONIZE = 0x00100000
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        # STILL_ACTIVE == 259. A handle can outlive the process, so a dead
        # process with an open handle must not read as alive.
        return bool(ok) and code.value == 259
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def run_id_for(job: str, *, start: str, end: str, universe: str, extra: str = "") -> str:
    """A STABLE id for one job, so `resume` is `run the same command again`.

    The window and the universe are in the id because a different window is a
    different job: resuming a 2015-2026 pull into a 2025-2026 cursor would
    report months as done that were never asked for.
    """
    tag = f"{job}_{start}_{end}_{universe}"
    if extra:
        tag += "_" + hashlib.sha256(extra.encode()).hexdigest()[:8]
    return re.sub(r"[^A-Za-z0-9_.-]", "-", tag)


class JournalRefusal(RuntimeError):
    """The run will not start, and the reason is stated."""


class PullJournal:
    """Cursor + log + pid + per-month receipts for one resumable pull."""

    def __init__(self, run_id: str, *, root: Path | None = None,
                 meta: dict[str, Any] | None = None) -> None:
        self.run_id = run_id
        self.dir = (root or PULLS) / run_id
        self.months_dir = self.dir / "months"
        self.cursor_path = self.dir / "cursor.json"
        self.log_path = self.dir / "run.log"
        self.pid_path = self.dir / "run.pid"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.months_dir.mkdir(parents=True, exist_ok=True)
        self.cursor = self._load_cursor(meta or {})
        self._log_fh = None
        self._resumed_from: dict[str, Any] = {}

    # ------------------------------------------------------------------ cursor
    def _load_cursor(self, meta: dict[str, Any]) -> dict[str, Any]:
        if self.cursor_path.exists():
            try:
                cur = json.loads(self.cursor_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                # A corrupt cursor is NOT "start from zero". Starting from zero
                # silently is exactly the failure this module exists to end.
                raise JournalRefusal(
                    f"{self.cursor_path} is unreadable ({exc}). Move it aside "
                    "deliberately if you intend to restart from month 0.") from exc
            if cur.get("meta", {}).get("start") and meta.get("start") and \
                    cur["meta"]["start"] != meta["start"]:
                raise JournalRefusal(
                    f"cursor {self.run_id} was opened for {cur['meta']['start']}"
                    f"..{cur['meta'].get('end')}, not {meta['start']}..{meta.get('end')}")
            cur.setdefault("done", {})
            cur.setdefault("partial", {})
            cur.setdefault("totals", {})
            cur["meta"] = {**cur.get("meta", {}), **meta}
            cur["resumed"] = int(cur.get("resumed", 0)) + 1
            return cur
        return {"schema": SCHEMA, "run_id": self.run_id, "created_at": utcnow(),
                "updated_at": utcnow(), "meta": meta, "done": {}, "partial": {},
                "totals": {"items": 0, "stored": 0, "duplicate": 0, "http_errors": {}},
                "resumed": 0}

    def save(self) -> None:
        self.cursor["updated_at"] = utcnow()
        tmp = self.cursor_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.cursor, indent=1), encoding="utf-8")
        tmp.replace(self.cursor_path)   # atomic-ish: a kill mid-write cannot
                                        # leave a truncated cursor behind

    # ---------------------------------------------------------------- lifecycle
    def open(self, argv: list[str]) -> "PullJournal":
        if self.pid_path.exists():
            try:
                prev = json.loads(self.pid_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                prev = {}
            pid = int(prev.get("pid") or 0)
            if pid and pid != os.getpid() and pid_alive(pid):
                raise JournalRefusal(
                    f"run {self.run_id} is already owned by pid {pid} "
                    f"(started {prev.get('started_at')}). Kill THAT pid if you "
                    "mean to take over -- never by image name.")
            # A stale pid file is the normal aftermath of a kill. Say so; a
            # resume that prints nothing about the crash reads as a fresh run.
            self.log(f"stale pid file from pid {pid or '?'} "
                     f"(started {prev.get('started_at')}) -- previous run did not exit cleanly")
        self.pid_path.write_text(json.dumps(
            {"pid": os.getpid(), "started_at": utcnow(), "run_id": self.run_id,
             "argv": argv, "log": str(self.log_path), "cursor": str(self.cursor_path)},
            indent=1), encoding="utf-8")
        self._resumed_from = {leg: list(ms) for leg, ms in self.cursor.get("done", {}).items()}
        n_done = sum(len(v) for v in self._resumed_from.values())
        self.log(f"OPEN pid={os.getpid()} run={self.run_id} resumed={self.cursor.get('resumed', 0)} "
                 f"months already done={n_done} partial={self.cursor.get('partial') or 'none'}")
        self.save()
        return self

    def close(self, status: str, summary: dict[str, Any] | None = None) -> None:
        self.cursor["status"] = status
        self.cursor["closed_at"] = utcnow()
        if summary:
            self.cursor["summary"] = summary
        self.save()
        self.log(f"CLOSE status={status}")
        if self._log_fh:
            self._log_fh.close()
            self._log_fh = None
        # The pid file is removed only on a CLEAN exit, so its presence is
        # itself the evidence that a run was killed.
        if status == "complete":
            self.pid_path.unlink(missing_ok=True)

    # --------------------------------------------------------------------- log
    def log(self, line: str) -> None:
        stamped = f"{utcnow()} {line}"
        print(stamped, flush=True)
        if self._log_fh is None:
            self._log_fh = self.log_path.open("a", encoding="utf-8")
        self._log_fh.write(stamped + "\n")
        self._log_fh.flush()
        os.fsync(self._log_fh.fileno())      # a killed process must still have
                                             # written the line that explains it

    # ------------------------------------------------------------------ units
    def done_months(self, leg: str) -> list[str]:
        return list(self.cursor.setdefault("done", {}).setdefault(leg, []))

    def is_done(self, leg: str, month: str) -> bool:
        return month in self.cursor.setdefault("done", {}).setdefault(leg, [])

    def resume_index(self, leg: str, month: str) -> int:
        """Where inside this month the last run stopped (0 if it never started)."""
        p = self.cursor.setdefault("partial", {}).get(leg) or {}
        return int(p.get("index", 0)) if p.get("month") == month else 0

    def checkpoint(self, leg: str, month: str, index: int) -> None:
        self.cursor.setdefault("partial", {})[leg] = {"month": month, "index": index,
                                                      "at": utcnow()}
        self.save()

    def complete_month(self, leg: str, month: str, receipt: dict[str, Any]) -> Path:
        receipt = {"schema": "month_receipt/1", "leg": leg, "month": month,
                   "run_id": self.run_id, "at": utcnow(), **receipt}
        path = self.months_dir / f"{month}.{leg}.json"
        path.write_text(json.dumps(receipt, indent=1), encoding="utf-8")
        done = self.cursor.setdefault("done", {}).setdefault(leg, [])
        if month not in done:
            done.append(month)
            done.sort()
        self.cursor.setdefault("partial", {}).pop(leg, None)
        t = self.cursor.setdefault("totals", {})
        t["items"] = t.get("items", 0) + int(receipt.get("items_fetched", 0))
        t["stored"] = t.get("stored", 0) + int(receipt.get("rows_stored_new", 0))
        t["duplicate"] = t.get("duplicate", 0) + int(receipt.get("rows_duplicate", 0))
        errs = t.setdefault("http_errors", {})
        for k, v in (receipt.get("http_errors") or {}).items():
            errs[k] = errs.get(k, 0) + int(v)
        self.save()
        return path

    def degraded_months(self, leg: str, min_refusals: int = 1) -> list[tuple[str, int]]:
        """Months marked DONE whose receipt shows the network let us down.

        MEASURED 2026-09-07 11:45 -> 2026-09-08 04:48: this box lost DNS for
        ~17 hours mid-run. Neither job died -- they logged
        `getaddrinfo failed` and carried on -- but `2025-03` finished with 124
        transport refusals and `2026-01` with 125, and both were then marked
        DONE. "Done" and "done and full" are different sentences and the
        receipt keeps them apart; this is the function that acts on the
        difference, so a degraded month can be re-pulled deliberately instead
        of being discovered months later as a hole in a coverage table.
        """
        out = []
        for r in self.month_receipts(leg):
            n = int(r.get("n_refusals", 0))
            if n >= min_refusals and self.is_done(leg, r.get("month", "")):
                out.append((r["month"], n))
        return sorted(out)

    def reopen_month(self, leg: str, month: str) -> None:
        """Un-mark a month so the next run pulls it again. The old receipt is
        kept beside the new one as `<month>.<leg>.superseded-<n>.json`, because
        a receipt that is overwritten is a receipt that cannot be compared."""
        done = self.cursor.setdefault("done", {}).setdefault(leg, [])
        if month in done:
            done.remove(month)
        src = self.months_dir / f"{month}.{leg}.json"
        if src.exists():
            n = len(list(self.months_dir.glob(f"{month}.{leg}.superseded-*.json")))
            src.replace(self.months_dir / f"{month}.{leg}.superseded-{n}.json")
        self.cursor.setdefault("partial", {}).pop(leg, None)
        self.save()

    def month_receipts(self, leg: str | None = None) -> list[dict[str, Any]]:
        out = []
        for p in sorted(self.months_dir.glob("*.json")):
            try:
                r = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if leg and r.get("leg") != leg:
                continue
            if ".superseded-" in p.name:
                continue          # kept for comparison, never counted twice
            out.append(r)
        return out

    # ------------------------------------------------------------------ report
    def progress(self, leg: str, months: list[str]) -> str:
        done = [m for m in months if self.is_done(leg, m)]
        return f"{leg}: month {len(done)} of {len(months)}"


def find_runs(root: Path | None = None) -> list[dict[str, Any]]:
    """Every run on disk with its status -- so `what is running` is answerable
    from the filesystem and not from a scrollback that no longer exists."""
    base = root or PULLS
    out = []
    if not base.exists():
        return out
    for d in sorted(base.iterdir()):
        cur = d / "cursor.json"
        if not cur.exists():
            continue
        try:
            c = json.loads(cur.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            out.append({"run_id": d.name, "status": "UNREADABLE_CURSOR"})
            continue
        pid, alive = None, False
        if (d / "run.pid").exists():
            try:
                pid = int(json.loads((d / "run.pid").read_text(encoding="utf-8")).get("pid") or 0)
                alive = pid_alive(pid)
            except (json.JSONDecodeError, OSError, ValueError):
                pid = None
        out.append({"run_id": d.name, "dir": str(d), "pid": pid, "alive": alive,
                    "status": c.get("status") or ("RUNNING" if alive else "INTERRUPTED"),
                    "updated_at": c.get("updated_at"),
                    "done": {k: len(v) for k, v in (c.get("done") or {}).items()},
                    "partial": c.get("partial"), "totals": c.get("totals"),
                    "meta": c.get("meta")})
    return out


def main() -> int:
    """`python -m scripts.pull_journal` -- what pulls exist and which are alive."""
    runs = find_runs()
    if not runs:
        print(f"no runs under {PULLS}")
        return 0
    for r in runs:
        print(f"{r['run_id']:<52} {r['status']:<14} pid={r.get('pid')} "
              f"alive={r.get('alive')} done={r.get('done')} updated={r.get('updated_at')}")
        if r.get("partial"):
            print(f"    partial: {r['partial']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
