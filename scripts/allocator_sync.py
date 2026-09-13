"""Synchronise the central allocator record into a runner volume.

The mirror of `scripts/prediction_book_sync.py`, one artefact over: it never
computes a weight, never re-runs the allocator and never invents a budget. It
downloads the record the seal authority already wrote, verifies its content
hash and its day, installs it atomically under `AAT_LEDGER_DIR/allocator/` --
where `alpha.allocator.budget_for` already looks first -- and hands the pass the
role's `gross` through the existing `--gross-scale` path.

WHERE THE BASE URL COMES FROM
=============================
`base_url()` resolves in three steps and the last one is silence:

  1. `AAT_ALLOCATOR_BASE_URL`, when a deploy or an operator set it explicitly;
  2. else `AAT_PREDICTION_BOOK_BASE_URL` -- the SAME service, the same host,
     already live on the tracker books since 2026-09-02
     (`http://seal-authority.railway.internal:8080`). Two variables naming one
     authority is two things to keep in step, and the artery that already works
     is the one to reuse;
  3. else nothing at all, and this file is an exact no-op.

So a loop needs no new variable to start reading the cut, and
`alpha.fleet.COMMON_ENV` sets (1) anyway on the next deploy so that the books
which never carried the seal variable (hack1, hack5) are not quietly the two
the allocator cannot reach.

THE CADENCE, WHICH IS THE ONLY SUBTLE PART
==========================================
The authority writes day D's record AFTER 16:30 ET on day D. So through the
whole of day D+1's session the newest record on earth is **D**, and that is the
NORMAL state, not a stale one. A freshness rule written against `today` would
call every single trading session stale, print a warning every two minutes, and
teach the reader to skim the line that matters (`CLAUDE.md`: a gate that cannot
go green is a broken gate).

So freshness is measured against `expected_day()` -- *the day whose close has
most recently passed* -- and there are exactly four outcomes, each named:

  * `CURRENT` -- the record is for the last closed session. Its budget is used.
  * `STALE`   -- the record is older. The book KEEPS that budget and says how
                 old it is, and the budget is additionally floored at whatever
                 the deploy-time `--gross-scale` flag said: a stale allocator
                 may never RAISE a book, only keep or reduce it.
  * `AHEAD`   -- the record names a day whose close has not happened. It is
                 REFUSED, not installed: a budget computed from an unfinished
                 day is a mark on a half session.
  * `NO RECORD` -- nothing on the volume, nothing in the image seed. The
                 deploy-time flag stands, loudly. Never a silent 1.00.

`expected_day()` walks back over weekends but knows nothing about holidays, so
on the day after a market holiday the newest record is one weekday older than
this expects and the row reads STALE. That direction is deliberate: STALE keeps
the budget and cannot raise it, so a holiday costs a log line, while the
opposite error -- treating a genuinely stale record as current -- would silently
re-arm a book the allocator had cut.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime, time as dtime, timedelta, timezone

from alpha import exits

#: Matches `scripts/seal_authority.ALLOCATOR_AFTER_ET`. Before this time on a
#: weekday, today's close has not been marked and the day whose close has most
#: recently passed is the previous session.
CLOSE_MARKED_AFTER_ET = dtime(16, 30)

#: An allocator record is a few kilobytes of JSON. The book cap is 8 MiB; this
#: one is smaller on purpose, because the only thing a megabyte-sized allocator
#: record can be is not an allocator record.
MAX_BYTES = 1024 * 1024


def _canonical_sha(payload: dict) -> str:
    """Byte-identical to `prediction_book_sync._canonical_sha`, deliberately.

    Two arteries that verify with two different hashes are two things to get
    right; the seal authority stamps both artefacts with `prediction_book._sha`,
    and this is the same arithmetic on the consumer side.
    """
    body = dict(payload)
    claimed = body.pop("content_sha256", None)
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    actual = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    if not claimed or claimed != actual:
        raise ValueError(f"content hash mismatch: claimed={claimed!r} actual={actual}")
    return actual


def base_url() -> str:
    """The seal authority's HTTP root, or `""` for "this loop does not sync"."""
    for name in ("AAT_ALLOCATOR_BASE_URL", "AAT_PREDICTION_BOOK_BASE_URL"):
        value = (os.getenv(name) or "").strip().rstrip("/")
        if value:
            return value
    return ""


def _root():
    from pathlib import Path

    root = Path(os.getenv("AAT_LEDGER_DIR") or "state") / "allocator"
    root.mkdir(parents=True, exist_ok=True)
    return root


def expected_day(now: datetime | None = None) -> str:
    """The trading day whose close has most recently passed, in ET.

    Derived, never hardcoded: `alpha.exits.session_day` is the repo's one ET
    date and this walks back from it rather than deriving a second ET offset
    (`session_day`'s own docstring: one definition, next to the offset it
    depends on).
    """
    today = date.fromisoformat(exits.session_day(now))
    et_now = (now or datetime.now(timezone.utc)) + exits.ET_OFFSET
    closed_today = today.weekday() < 5 and et_now.time() >= CLOSE_MARKED_AFTER_ET
    d = today if closed_today else today - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def _validate(payload: dict, *, want_day: str) -> tuple[str, str]:
    """`(sha, freshness)` or raise. Never returns a record it would not install."""
    sha = _canonical_sha(payload)
    day = str(payload.get("day") or "")
    if not day:
        raise ValueError("the record names no day")
    if not payload.get("per_book"):
        raise ValueError("the record has no per_book block")
    for role, row in (payload["per_book"] or {}).items():
        if row.get("gross_budget_scale") is None:
            raise ValueError(f"{role} carries no gross_budget_scale")
        scale = float(row["gross_budget_scale"])
        if not (0.0 <= scale <= 1.0):
            raise ValueError(
                f"{role}'s gross_budget_scale is {scale}, outside [0,1]. The "
                f"allocator may only ever REDUCE a book's own declared gross; a "
                f"record that hands one leverage is refused at the door, not "
                f"clamped quietly downstream")
    if day > want_day:
        raise ValueError(
            f"the record is dated {day} and the most recently CLOSED session is "
            f"{want_day}. A budget computed from a day that has not finished is a "
            f"mark on half a session; refusing rather than installing it")
    return sha, ("CURRENT" if day == want_day else "STALE")


def sync_once(day: str | None = None) -> bool:
    """Fetch, verify and install `/allocator/latest.json`. True when installed or
    already present. Never raises, never writes an unverified byte."""
    base = base_url()
    if not base:
        return True
    want = day or expected_day()
    dst = _root() / f"{want}.json"
    if dst.is_file():
        try:
            local = json.loads(dst.read_text(encoding="utf-8"))
            _canonical_sha(local)
            if str(local.get("day")) == want:
                return True
        except (OSError, ValueError, json.JSONDecodeError):
            pass        # a corrupt local copy is re-fetched, not trusted

    url = f"{base}/allocator/latest.json"
    try:
        with urllib.request.urlopen(url, timeout=12) as response:
            raw = response.read(MAX_BYTES + 1)
    except (OSError, urllib.error.URLError) as exc:
        print(f"ALLOCATOR SYNC waiting day={want} url={url}: {exc}", flush=True)
        return False
    if len(raw) > MAX_BYTES:
        print(f"ALLOCATOR SYNC refused oversized artifact day={want}", flush=True)
        return False
    try:
        payload = json.loads(raw.decode("utf-8"))
        sha, freshness = _validate(payload, want_day=want)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"ALLOCATOR SYNC refused invalid artifact day={want}: {exc}", flush=True)
        return False

    got = str(payload["day"])
    target = _root() / f"{got}.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, target)
    print(f"ALLOCATOR SYNC installed day={got} sha={sha[:16]} {freshness} "
          f"(most recent close {want}) path={target}", flush=True)
    if freshness == "STALE":
        print(f"ALLOCATOR SYNC STALE: the authority's newest record is {got}, not "
              f"{want}. This book KEEPS that budget; a stale allocator never "
              f"re-arms a book back to full size.", flush=True)
    return True


def effective_gross_scale(role: str, *, deployed: float | None = None,
                          day: str | None = None) -> tuple[float | None, str]:
    """`(scale, why)` -- the gross budget this pass actually runs at.

    `deployed` is the `--gross-scale` the DEPLOY baked into `AAT_LOOP_ARGS`;
    it is the last budget a human shipped and it is the floor when the live
    record cannot be believed.

      * not an allocated role      -> `(deployed, why)`; hack2 went to lane D.
      * CURRENT record             -> the record's own scale. A restore is
                                      allowed to raise the book here, because
                                      that IS the promotion path and a record
                                      for the last closed session is the whole
                                      point of this artery.
      * STALE record               -> `min(record, deployed)`. Keep or reduce,
                                      never raise.
      * no record anywhere         -> `(deployed, why)`, said loudly.

    Never returns a silent 1.00 and never returns None for an allocated role
    that has a record.
    """
    from alpha import allocator as A

    r = (role or "").strip().lower()
    if r not in A.ROLES:
        return deployed, (f"{r!r} is not an allocated role; the allocator emits no "
                          f"budget for it and the deployed flag stands")
    want = day or expected_day()
    try:
        b = A.budget_for(r, day=want)
    except A.AllocatorUnavailable as exc:
        return deployed, (f"NO ALLOCATOR RECORD: {exc} -- the deployed "
                          f"--gross-scale {deployed} stands unchanged")
    scale = float(b["scale"])
    if b["record_day"] == want:
        return scale, (f"CURRENT: allocator record {b['record_day']} says "
                       f"{scale:.6f} ({b.get('kill_state')}, "
                       f"{b.get('binding_constraint')})")
    if deployed is None:
        return scale, (f"STALE: the newest allocator record is {b['record_day']}, "
                       f"not {want}; keeping its {scale:.6f}. No deployed flag to "
                       f"floor it against.")
    kept = min(scale, float(deployed))
    return kept, (f"STALE: the newest allocator record is {b['record_day']}, not "
                  f"{want}; keeping min(record {scale:.6f}, deployed "
                  f"{float(deployed):.6f}) = {kept:.6f}. A stale allocator may "
                  f"keep or reduce a book, never raise it.")


def main() -> int:
    base = base_url()
    if not base:
        print("ALLOCATOR SYNC disabled: neither AAT_ALLOCATOR_BASE_URL nor "
              "AAT_PREDICTION_BOOK_BASE_URL is set", flush=True)
        return 0
    interval = max(60, int(os.getenv("AAT_ALLOCATOR_SYNC_SECONDS", "300")))
    last: str | None = None
    while True:
        want = expected_day()
        ok = sync_once(want)
        if ok and want != last:
            print(f"ALLOCATOR SYNC ready for {want}", flush=True)
            last = want
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
