"""Synchronise Book F's frozen MONTHLY ENGINE FILE into a runner volume.

The third artefact over the artery `scripts/prediction_book_sync.py` opened and
`scripts/allocator_sync.py` widened, and it exists to delete one sentence from
`docs/DEPLOY_PLAN_2026-09-14.md` 3:

    "THIS BOOK NEEDS A REDEPLOY EVERY CALENDAR MONTH."

That was true while the only delivery path for `F_seasonality_<YYYY-MM>.json`
was `COPY docs/seed/ /app/seed/` plus a container-start `cp -rn`. A file that
ships in the image can only arrive when a new image does, so 1 October would
have stopped hack3 unless a human remembered to redeploy -- a calendar
dependency on a person, which is exactly the failure mode the seal authority was
built to remove for the prediction book.

WHAT THIS FILE DOES, AND WHAT IT REFUSES TO DO
==============================================
It downloads `GET /engines/F_seasonality_<month>.json` from the seal authority,
verifies the payload against its OWN `content_sha256` with the same arithmetic
the exporter used, checks that the month inside the hashed content is the month
asked for, and installs it atomically at
`AAT_LEDGER_DIR/engines/F_seasonality_<month>.json` -- the first place
`alpha.brains.seasonality_f._engine_path` looks.

It computes no ranking, re-ranks nothing, and NEVER relaxes a refusal. The
brain re-verifies the installed bytes in the ORDER path exactly as before: this
module can only ever put a file where the brain will find it, and a file the
brain would have declined is still declined after this module installs it.

WHERE THE BASE URL COMES FROM
=============================
Three steps, and the last one is silence -- the shape `allocator_sync.base_url`
already uses, with one more fallback because this artefact arrived third:

  1. `AAT_ENGINE_BASE_URL`, when a deploy or an operator set it explicitly;
  2. else `AAT_ALLOCATOR_BASE_URL`, else `AAT_PREDICTION_BOOK_BASE_URL` -- the
     SAME service on the same host. Three variables naming one authority is
     three things to keep in step; `alpha.fleet.COMMON_ENV` sets (1) on the next
     deploy so the fleet is uniform anyway;
  3. else nothing at all, and this file is an exact no-op. A loop with no
     authority keeps the image's seeded engine file and the old contract, which
     is the state every book is in before that deploy lands.

THE CADENCE, AND WHY "STALE" IS NOT A WORD HERE
===============================================
The allocator's record is DAILY, so `allocator_sync` has to distinguish four
freshness states. An engine file is MONTHLY and the brain already refuses any
month but the current one, so there are only two states worth naming:

  * the month asked for is installed  -> nothing to do (and nothing fetched);
  * it is not                         -> fetch it, or say why it could not be.

A file for the WRONG month is never installed under the right month's name:
`_validate` reads the month out of the hashed content, not out of the URL, so an
authority serving September under October's name is refused rather than
renamed. That is the `AHEAD` refusal of the allocator artery in the only form
this artefact can express it.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from alpha import exits

#: The engine name `alpha.brains.seasonality_f` admits. Written here too, and
#: checked here too, so a payload that names another selector never reaches the
#: volume at all -- the brain's identical check is the one that matters, this
#: one just keeps a wrong file off the disk.
ENGINE = "seasonality_11_20_v0"

#: A month's ranking is ~115 KB of JSON (the two seeded files, 2026-09-13). The
#: cap is four megabytes because the only thing a four-megabyte engine file can
#: be is not an engine file; the book cap is 8 MiB and the allocator's 1 MiB,
#: and each is sized to its own artefact rather than copied.
MAX_BYTES = 4 * 1024 * 1024

#: How long a failed fetch is remembered, so a 30-symbol cycle makes ONE
#: request at most rather than thirty. Zero disables the memo (tests).
RETRY_AFTER_S = 300.0

_last_attempt: dict[str, float] = {}


def base_url() -> str:
    """The seal authority's HTTP root, or `""` for "this loop does not sync"."""
    for name in ("AAT_ENGINE_BASE_URL", "AAT_ALLOCATOR_BASE_URL",
                 "AAT_PREDICTION_BOOK_BASE_URL"):
        value = (os.getenv(name) or "").strip().rstrip("/")
        if value:
            return value
    return ""


def _root() -> Path:
    """`AAT_LEDGER_DIR/engines`, resolved at CALL time.

    `seasonality_f.ENGINES` resolves the same directory at IMPORT time, which is
    correct for a long-lived loop and wrong for a test that sets the variable
    afterwards. Resolving here keeps the two agreeing in a process that changed
    its mind, and the loop never does.
    """
    root = Path(os.getenv("AAT_LEDGER_DIR") or "state") / "engines"
    root.mkdir(parents=True, exist_ok=True)
    return root


def month_wanted(day: str | None = None, now: datetime | None = None) -> str:
    """The calendar month Book F trades, from the ET TRADING day.

    `alpha.exits.session_day` is the repo's one ET date, and
    `seasonality_f.month_for` slices the same string. Derived, never a literal:
    a hardcoded month in a delivery path is a fixture that expires (session
    protocol 5).
    """
    return (day or exits.session_day(now))[:7]


def _canonical_sha(payload: dict) -> str:
    """Byte-identical to `seasonality_f._sha_of` and to the exporter's stamp."""
    body = dict(payload)
    claimed = body.pop("content_sha256", None)
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    actual = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    if not claimed or claimed != actual:
        raise ValueError(f"content hash mismatch: claimed={claimed!r} actual={actual}")
    return actual


def _validate(payload: dict, *, want_month: str) -> str:
    """The sha, or raise. Never returns a payload this would not install."""
    sha = _canonical_sha(payload)
    month = str(payload.get("month") or "")
    if not month:
        raise ValueError("the engine file names no month inside its hashed content")
    if month != want_month:
        raise ValueError(
            f"the engine file declares month {month!r} inside its own hashed "
            f"content, not {want_month!r}. A ranking is not renamed on the way to "
            f"a volume -- refusing rather than installing another month's names "
            f"under this month's file name")
    if payload.get("engine") != ENGINE:
        raise ValueError(
            f"the engine file declares engine {payload.get('engine')!r}, not "
            f"{ENGINE!r}; this artery delivers Book F's ranking and nothing else")
    if not payload.get("selected"):
        raise ValueError(
            "the engine file selected no names; an empty selection is the "
            "export's own coverage refusal and is not installed as a book")
    return sha


def installed(month: str | None = None) -> Path | None:
    """The verified local copy for `month`, or None. Reads no network."""
    m = month or month_wanted()
    path = _root() / f"F_seasonality_{m}.json"
    if not path.is_file():
        return None
    try:
        _validate(json.loads(path.read_text(encoding="utf-8")), want_month=m)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return path


def sync_once(month: str | None = None, *, url: str | None = None) -> bool:
    """Fetch, verify and install this month's engine file.

    True when the month is present on the volume afterwards (already or newly),
    False when it is not. Never raises and never writes an unverified byte.
    """
    base = base_url()
    m = month or month_wanted()
    if not base:
        return installed(m) is not None
    if installed(m) is not None:
        return True

    endpoint = url or f"{base}/engines/F_seasonality_{m}.json"
    try:
        with urllib.request.urlopen(endpoint, timeout=12) as response:
            raw = response.read(MAX_BYTES + 1)
    except (OSError, urllib.error.URLError) as exc:
        print(f"ENGINE SYNC waiting month={m} url={endpoint}: {exc}", flush=True)
        return False
    if len(raw) > MAX_BYTES:
        print(f"ENGINE SYNC refused oversized artifact month={m}", flush=True)
        return False
    try:
        payload = json.loads(raw.decode("utf-8"))
        sha = _validate(payload, want_month=m)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"ENGINE SYNC refused invalid artifact month={m}: {exc}", flush=True)
        return False

    target = _root() / f"F_seasonality_{m}.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, target)
    print(f"ENGINE SYNC installed month={m} sha={sha[:16]} "
          f"names={len(payload['selected'])} path={target}", flush=True)
    return True


def ensure_month(month: str | None = None) -> bool:
    """`sync_once` with a per-month back-off, for callers inside a hot path.

    `seasonality_f.engine()` runs once per SYMBOL per cycle. Without this memo a
    month the authority cannot serve would cost thirty timeouts a cycle, and a
    delivery artery that slows the order path down is worse than the redeploy it
    replaced. One attempt per `RETRY_AFTER_S`; a SUCCESS needs no memo because
    `installed()` short-circuits it.
    """
    m = month or month_wanted()
    now = time.monotonic()
    last = _last_attempt.get(m)
    if last is not None and RETRY_AFTER_S > 0 and (now - last) < RETRY_AFTER_S:
        return installed(m) is not None
    _last_attempt[m] = now
    try:
        return sync_once(m)
    except Exception as exc:                                        # noqa: BLE001
        # A delivery failure must never be able to raise into an order path.
        print(f"ENGINE SYNC failed month={m}: {type(exc).__name__}: {exc}", flush=True)
        return False


def main() -> int:
    base = base_url()
    if not base:
        print("ENGINE SYNC disabled: none of AAT_ENGINE_BASE_URL, "
              "AAT_ALLOCATOR_BASE_URL, AAT_PREDICTION_BOOK_BASE_URL is set", flush=True)
        return 0
    interval = max(60, int(os.getenv("AAT_ENGINE_SYNC_SECONDS", "900")))
    last: str | None = None
    while True:
        want = month_wanted()
        ok = sync_once(want)
        if ok and want != last:
            print(f"ENGINE SYNC ready for {want}", flush=True)
            last = want
        if not ok:
            print(f"ENGINE SYNC no engine file for {want} yet -- Book F declines "
                  f"until one is served; the loop is NOT stopped", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
