"""Synchronise the central immutable prediction book into a runner volume.

This is the missing delivery artery between the pre-market seal authority and
tracker_portfolio.  It never computes, ranks, reseals, or alters a book.  It
only downloads the already-sealed artifact, verifies its date and content hash,
and atomically installs it under AAT_LEDGER_DIR/predictions where the existing
brain already looks first.

Run beside agent_loop on tracker accounts.  Without
AAT_PREDICTION_BOOK_BASE_URL it is a no-op so non-tracker books are unaffected.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from alpha import exits


def _canonical_sha(payload: dict) -> str:
    body = dict(payload)
    claimed = body.pop("content_sha256", None)
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    actual = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    if not claimed or claimed != actual:
        raise ValueError(f"content hash mismatch: claimed={claimed!r} actual={actual}")
    return actual


def _target(day: str) -> Path:
    root = Path(os.getenv("AAT_LEDGER_DIR") or "state") / "predictions"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{day}.json"


def _valid_local(path: Path, day: str) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("day") != day:
            return False
        _canonical_sha(payload)
        return True
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def sync_once(day: str | None = None) -> bool:
    base = (os.getenv("AAT_PREDICTION_BOOK_BASE_URL") or "").strip().rstrip("/")
    if not base:
        return True
    day = day or exits.session_day()
    dst = _target(day)
    if _valid_local(dst, day):
        return True

    url = f"{base}/{day}.json"
    try:
        with urllib.request.urlopen(url, timeout=12) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
    except (OSError, urllib.error.URLError) as exc:
        print(f"SEAL SYNC waiting day={day} url={url}: {exc}", flush=True)
        return False
    if len(raw) > 8 * 1024 * 1024:
        print(f"SEAL SYNC refused oversized artifact day={day}", flush=True)
        return False
    try:
        payload = json.loads(raw.decode("utf-8"))
        if payload.get("day") != day:
            raise ValueError(f"artifact day {payload.get('day')!r} != requested {day}")
        sha = _canonical_sha(payload)
        if not payload.get("portfolios"):
            raise ValueError("artifact has no portfolios block")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"SEAL SYNC refused invalid artifact day={day}: {exc}", flush=True)
        return False

    tmp = dst.with_suffix(".json.tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, dst)
    print(f"SEAL SYNC installed day={day} sha={sha[:16]} path={dst}", flush=True)
    return True


def main() -> int:
    base = (os.getenv("AAT_PREDICTION_BOOK_BASE_URL") or "").strip()
    if not base:
        print("SEAL SYNC disabled: AAT_PREDICTION_BOOK_BASE_URL unset", flush=True)
        return 0
    interval = max(30, int(os.getenv("AAT_PREDICTION_BOOK_SYNC_SECONDS", "120")))
    last_day: str | None = None
    while True:
        day = exits.session_day()
        ok = sync_once(day)
        if ok and day != last_day:
            print(f"SEAL SYNC ready for {day}", flush=True)
            last_day = day
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
