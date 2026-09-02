"""Central, fail-closed prediction-book authority for the paper tracker fleet.

The old contract required a laptop to run `tracker --refresh` and
`prediction_book --seal --publish` every trading day.  Railway runners then
correctly declined when that artifact was missing.  This service owns only the
missing orchestration step: refresh one tracker snapshot, seal one immutable
book, and serve that exact JSON to every tracker personality.

It does NOT submit orders and has no account mandate.  Consumers independently
verify the book's content hash before installing it.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import prediction_book

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parent.parent
STATE = Path(os.getenv("AAT_LEDGER_DIR") or (ROOT / "state"))
BOOKS = STATE / "predictions"


def _day() -> str:
    return datetime.now(ET).date().isoformat()


def _weekday() -> bool:
    return datetime.now(ET).weekday() < 5


def _book_path(day: str) -> Path | None:
    cands = sorted(BOOKS.glob(f"{day}.json")) + sorted(BOOKS.glob(f"{day}.resealed_*.json"))
    return cands[-1] if cands else None


def _verify(path: Path, day: str) -> tuple[bool, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        claimed = payload.pop("content_sha256", None)
        actual = prediction_book._sha(payload)
        if payload.get("day") != day:
            return False, f"day mismatch {payload.get('day')!r} != {day}"
        if not claimed or claimed != actual:
            return False, f"hash mismatch claimed={claimed!r} actual={actual}"
        if not payload.get("portfolios"):
            return False, "no portfolios block"
        return True, actual
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return False, str(exc)


def _run(cmd: list[str]) -> bool:
    print("SEAL AUTHORITY run: " + " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=ROOT, check=False)
    if proc.returncode:
        print(f"SEAL AUTHORITY command failed rc={proc.returncode}: {' '.join(cmd)}", flush=True)
        return False
    return True


def ensure_today() -> bool:
    day = _day()
    if not _weekday():
        print(f"SEAL AUTHORITY {day}: weekend, no trading seal required", flush=True)
        return True
    existing = _book_path(day)
    if existing:
        ok, note = _verify(existing, day)
        if ok:
            # The consumers ask for /<day>.json.  A later attended reseal remains
            # separately named for auditability; we intentionally do not alias it
            # over the original here because no retroactive reseals is the default.
            print(f"SEAL AUTHORITY ready day={day} sha={note[:16]} file={existing.name}", flush=True)
            return True
        print(f"SEAL AUTHORITY refused invalid existing book {existing}: {note}", flush=True)
        return False

    if not _run([sys.executable, "-m", "scripts.tracker", "--refresh", "--day", day]):
        return False
    # refresh does NOT derive realised_vol_20d; without this step hack3/hack6
    # seal EMPTY (S30, 2026-08-31). The order is refresh -> backfill -> seal.
    if not _run([sys.executable, "-m", "scripts.tracker", "--backfill-prices", "--day", day]):
        return False
    if not _run([sys.executable, "-m", "scripts.prediction_book", "--seal", "--universe", "tracker", "--day", day]):
        return False
    path = _book_path(day)
    if path is None:
        print(f"SEAL AUTHORITY failed: seal command returned success but no book exists for {day}", flush=True)
        return False
    ok, note = _verify(path, day)
    if not ok:
        print(f"SEAL AUTHORITY refused generated book {path}: {note}", flush=True)
        return False
    print(f"SEAL AUTHORITY SEALED day={day} sha={note[:16]} file={path.name}", flush=True)
    return True


def maintainer(interval: int) -> None:
    last_day: str | None = None
    while True:
        day = _day()
        path = _book_path(day)
        if day != last_day or path is None:
            ensure_today()
            last_day = day if _book_path(day) is not None else None
        time.sleep(interval)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print("SEAL AUTHORITY HTTP " + (fmt % args), flush=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=int(os.getenv("PORT", "8080")))
    p.add_argument("--check-seconds", type=int, default=300)
    a = p.parse_args(argv)
    BOOKS.mkdir(parents=True, exist_ok=True)

    # Serve immediately so consumers get a deterministic 404 while a long
    # whole-market refresh is running, instead of a connection failure that is
    # indistinguishable from a dead authority.
    os.chdir(BOOKS)
    server = ThreadingHTTPServer(("0.0.0.0", a.port), QuietHandler)
    thread = threading.Thread(target=maintainer, args=(max(60, a.check_seconds),), daemon=True)
    thread.start()
    print(f"SEAL AUTHORITY serving {BOOKS} on :{a.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
