"""Central, fail-closed prediction-book authority for the paper tracker fleet.

The old contract required a laptop to run `tracker --refresh` and
`prediction_book --seal --publish` every trading day.  Railway runners then
correctly declined when that artifact was missing.  This service owns only the
missing orchestration step: refresh one tracker snapshot, seal one immutable
book, and serve that exact JSON to every tracker personality.

It does NOT submit orders and has no account mandate.  Consumers independently
verify the book's content hash before installing it.

SECOND ARTEFACT, SAME ARTERY (chunk 13c, 2026-09-13): THE ALLOCATOR RECORD
==========================================================================
The allocator's daily cut used to be computed on a laptop and shipped in the
image, so a budget computed on Tuesday could not reach a loop before the next
deploy -- and the laptop holds no role keys at all
(`docs/DEPLOY_PLAN_2026-09-14.md` 4b).  This service already serves ONE daily
file to every loop over HTTP and is the only process that can be given all five
key pairs without pasting a value anywhere: Railway resolves
`${{aat-loop-hack1.AAT_HACK1_KEY_ID}}` server-side, so the authority's
environment carries the keys and no human or receipt ever sees them.

So after the seal step, and only after the venue's close, the maintainer marks
the five allocated books and writes `state/allocator/<day>.json` beside the
book.  It is served at `/allocator/<day>.json` and `/allocator/latest.json`,
carries a `content_sha256` computed exactly the way a sealed book's is, and
`scripts/allocator_sync.py` verifies it on the loop side before installing.

It STILL submits no orders: the curves come from
`GET /v2/account/portfolio/history` through `scripts/allocator_venue.py`, whose
client exposes reads only, and the allocator itself is pinned by
`tests_smoke_allocator.py` to have no order path.

THIRD ARTEFACT: BOOK F'S MONTHLY ENGINE FILE (chunk 15b, 2026-09-13)
====================================================================
`docs/DEPLOY_PLAN_2026-09-14.md` 3 said, in capitals, "THIS BOOK NEEDS A
REDEPLOY EVERY CALENDAR MONTH": `F_seasonality_<YYYY-MM>.json` reached a loop
only inside the image, so 1 October stopped hack3 unless a human remembered.
A calendar dependency on a person is the failure this service was built to
remove for the prediction book, so the engine file joins it:

  * `GET /engines/F_seasonality_<YYYY-MM>.json` and
    `GET /engines/latest/F_seasonality.json` are served from a WHITELIST with
    the same shape as `/allocator/` -- basename only, matched against a literal
    pattern, so nothing above the engines directory is nameable;
  * the bytes come from `state/engines/` FIRST and `docs/seed/engines/` second.
    The seed copy is the one in the image today (the authority has no volume by
    design, `tests_smoke_allocator_artery` 7), so on a fresh boot the image IS
    the source; `state/engines/` is the path a later research-side push writes
    into, and a verified copy there WINS, which is the correction path `cp -rn`
    never had;
  * every candidate is HASH-VERIFIED before it is served. A file that fails its
    own `content_sha256` is not offered at all and the other location is tried,
    so a corrupted push cannot displace a good seed copy.

`scripts/engine_sync.py` is the consumer, `alpha/brains/seasonality_f.py` calls
it before the order path when the volume lacks the month, and the brain's own
fail-closed checks are unchanged: this artery can only put a file where the
brain will look, never make the brain accept one.
"""
from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, time as dtime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

from scripts import prediction_book

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parent.parent
STATE = Path(os.getenv("AAT_LEDGER_DIR") or (ROOT / "state"))
BOOKS = STATE / "predictions"
ALLOC = STATE / "allocator"

#: Book F's monthly engine files. `ENGINES` is where a later research-side push
#: lands (and is empty on a fresh boot, because this service deliberately has no
#: volume); `SEED_ENGINES` is the copy that ships in the image and is therefore
#: the live source today. A VERIFIED file in `ENGINES` wins, which is the
#: correction path `cp -rn` never had on the loop side.
ENGINES = STATE / "engines"
SEED_ENGINES = ROOT / "docs" / "seed" / "engines"

#: The earliest ET time the allocator record may be computed. The venue closes
#: 16:00 ET and `_in_session` already forbids 09:25-16:05; 16:30 is twenty-five
#: minutes of daylight past the bell so a late print cannot land inside the mark,
#: and it is a LOCAL-TO-ET number -- this machine's other clock is UTC+8 and the
#: two have been confused here before (MEMORY.md: machine UTC+8, scheduler ET).
ALLOCATOR_AFTER_ET = dtime(16, 30)

#: `state/allocator/<day>.json`, and nothing else, is reachable under /allocator/.
_DAY_JSON = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")

#: `F_seasonality_<YYYY-MM>.json`, and nothing else, is reachable under
#: /engines/ -- plus the literal `F_seasonality.json`, which resolves to the
#: newest verified month exactly as `/allocator/latest.json` resolves to the
#: newest record. Same whitelist shape, same reason: a name this cannot admit is
#: a name that cannot escape the directory.
_ENGINE_JSON = re.compile(r"^F_seasonality_(\d{4}-\d{2})\.json$")
_ENGINE_LATEST = "F_seasonality.json"


def _day() -> str:
    return datetime.now(ET).date().isoformat()


def _weekday() -> bool:
    return datetime.now(ET).weekday() < 5


def _in_session(now_t: dtime | None = None) -> bool:
    """Weekday 09:25-16:05 ET: bars are in progress, sealing is forbidden."""
    now_t = now_t or datetime.now(ET).time()
    return _weekday() and dtime(9, 25) <= now_t < dtime(16, 5)


def _in_session_at(now: datetime) -> bool:
    """The same predicate, but on a GIVEN moment rather than on the wall clock.

    `_in_session` reads today's weekday from `datetime.now`, so a caller that
    passes a time from another day gets that day's hour checked against TODAY's
    weekday. That is invisible five days a week and wrong on the other two --
    `tests_smoke_seal_delivery` works around it by stubbing the function, which
    is a workaround, not a predicate. Anything that reasons about a moment uses
    this one; `_in_session` keeps its signature for the callers that mean "now".
    """
    return now.weekday() < 5 and dtime(9, 25) <= now.time() < dtime(16, 5)


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

    # NEVER SEAL FROM AN IN-PROGRESS SESSION (red-team R2, 2026-09-02): the
    # refresh fetches bars with no end bound, so a mid-morning restart would
    # bake the 10:15 print into close/high_60d/realised_vol -- selection
    # changing under the hash. The authority seals from CLOSED markets only;
    # a book-less open-hours restart keeps the runners declining with
    # reasons, which is the designed failure.
    if _in_session():
        print(f"SEAL AUTHORITY {day}: venue session in progress "
              f"({datetime.now(ET):%H:%M} ET); refusing to refresh/seal from "
              "in-progress bars", flush=True)
        return False

    # Attention first: a fresh 13D/13G subject must be in TODAY's refresh
    # universe. A watcher failure must not block the seal -- the union is
    # optional-by-design (tracker warns and continues on a missing watchlist).
    _run([sys.executable, "-m", "scripts.ownership_watch"])
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


# ---------------------------------------------------------------------------
# THE ALLOCATOR RECORD (chunk 13c)
# ---------------------------------------------------------------------------

def allocator_due(now: datetime | None = None) -> tuple[str | None, str]:
    """`(day, why)` -- the trading day whose allocator record is owed RIGHT NOW.

    `None` is not a failure: a weekend, a pre-close weekday and an in-session
    minute are all "no record required", and each says which. The allocator's
    mark is a CLOSE, so this deliberately cannot be satisfied before 16:30 ET --
    a half-computed day would be written under a full day's name and the loops
    would install it as today's budget.
    """
    now = now or datetime.now(ET)
    day = now.date().isoformat()
    if now.weekday() >= 5:
        return None, f"{day}: weekend, no allocator record required"
    if _in_session_at(now):
        return None, (f"{day}: venue session in progress ({now:%H:%M} ET); an "
                      f"allocator mark is a CLOSE and this is not one")
    if now.time() < ALLOCATOR_AFTER_ET:
        return None, (f"{day}: {now:%H:%M} ET is before {ALLOCATOR_AFTER_ET:%H:%M} ET; "
                      f"the close has not settled, so today's record is not owed yet")
    return day, f"{day}: after {ALLOCATOR_AFTER_ET:%H:%M} ET on a weekday"


def allocator_record_path(day: str) -> Path:
    return ALLOC / f"{day}.json"


def latest_allocator_path() -> Path | None:
    if not ALLOC.is_dir():
        return None
    found = sorted(p for p in ALLOC.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"))
    return found[-1] if found else None


def _stamp(rec: dict) -> dict:
    """Add `content_sha256` the way a sealed book carries one.

    Same function, `prediction_book._sha`, over the record with the key removed
    -- so `scripts/allocator_sync.py` can verify an allocator record with the
    identical arithmetic `prediction_book_sync` uses on a book, and a reader who
    has understood one artery has understood both.
    """
    body = {k: v for k, v in rec.items() if k != "content_sha256"}
    return {**body, "content_sha256": prediction_book._sha(body)}


def ensure_allocator(day: str | None = None) -> bool:
    """Mark the five allocated books from the VENUE and write the day's record.

    Returns True when the day's record exists (already or newly), False when it
    is owed and could not be produced. A day that is not owed returns True and
    says why -- "no record required" is a state, not a failure.
    """
    from alpha import allocator as A
    from scripts import allocator as _run_allocator

    if day is None:
        day, why = allocator_due()
        if day is None:
            print(f"SEAL AUTHORITY allocator {why}", flush=True)
            return True
        print(f"SEAL AUTHORITY allocator due -- {why}", flush=True)

    ALLOC.mkdir(parents=True, exist_ok=True)
    existing = allocator_record_path(day)
    if existing.is_file():
        print(f"SEAL AUTHORITY allocator ready day={day} file={existing.name}", flush=True)
        return True

    try:
        anchor = _run_allocator.load_anchor()
    except SystemExit as exc:
        print(f"SEAL AUTHORITY allocator REFUSED: {exc}", flush=True)
        return False

    from scripts import allocator_venue

    fleet = allocator_venue.read_fleet(A.ROLES, anchor=anchor)
    curves, _equities, notes = allocator_venue.curves_and_equities(fleet)
    read = [r for r in A.ROLES if curves.get(r)]
    if not read:
        # EVERY read failed. That is a credentials or venue problem, not an
        # allocation, and writing a record out of five holes would hand every
        # book a budget computed from nothing.
        for n in notes:
            print(f"SEAL AUTHORITY allocator   {n}", flush=True)
        print(f"SEAL AUTHORITY allocator REFUSED day={day}: no role's equity could "
              f"be read; refusing to write a record with five holes in it", flush=True)
        return False

    yesterday, _ = A.latest_record(day=_prev_day(day))
    rec = A.allocate(day, curves=curves, anchor=anchor, yesterday=yesterday)
    rec["notes"] = list(rec.get("notes") or []) + notes + [
        f"computed inside scripts/seal_authority.py on {datetime.now(ET):%Y-%m-%d %H:%M} ET; "
        f"curves RE-DERIVED from the venue's portfolio history, not accumulated on disk "
        f"(this service has no volume)",
        f"roles read from the venue: {read}",
    ]
    rec["anchor_hash"] = anchor.get("contract_hash")
    rec["produced_by"] = "seal_authority"
    if anchor.get("contract_hash") != rec["contract_hash"]:
        rec["notes"].append(
            f"CONTRACT CHANGED SINCE THE ANCHOR: anchor "
            f"{str(anchor.get('contract_hash'))[:16]} vs today "
            f"{rec['contract_hash'][:16]}. Every number before today was produced "
            f"under a different rule.")

    stamped = _stamp(rec)
    tmp = existing.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(stamped, indent=1), encoding="utf-8")
    os.replace(tmp, existing)
    budgets = {r: stamped["per_book"][r]["gross_budget_scale"] for r in A.ROLES}
    print(f"SEAL AUTHORITY ALLOCATED day={day} sha={stamped['content_sha256'][:16]} "
          f"gross={budgets} worst_case_usd={stamped.get('worst_case_usd_fleet')}",
          flush=True)
    for line in (stamped.get("rule_fired") or []):
        print(f"SEAL AUTHORITY allocator RULE FIRED: {line}", flush=True)
    for n in notes:
        print(f"SEAL AUTHORITY allocator   {n}", flush=True)
    return True


def _prev_day(day: str) -> str:
    from datetime import date, timedelta

    y, m, d = (int(x) for x in str(day).split("-"))
    return (date(y, m, d) - timedelta(days=1)).isoformat()


def maintainer(interval: int) -> None:
    last_day: str | None = None
    while True:
        day = _day()
        path = _book_path(day)
        if day != last_day or path is None:
            ensure_today()
            last_day = day if _book_path(day) is not None else None
        # AFTER the seal, never instead of it. A venue read that hangs must not
        # be able to delay the book the whole fleet declines without, so the
        # allocator step is last and its failure is logged rather than raised:
        # a loop with no fresh record KEEPS its last budget (never a silent 1.00)
        # and that is a designed state, not an outage.
        try:
            ensure_allocator()
        except Exception as exc:                                    # noqa: BLE001
            print(f"SEAL AUTHORITY allocator step failed: "
                  f"{type(exc).__name__}: {exc}", flush=True)
        time.sleep(interval)


class QuietHandler(SimpleHTTPRequestHandler):
    """GET/HEAD over two named directories, and nothing else.

    The served root is still `state/predictions` (`os.chdir` in `main`), so the
    2026-09-04 audit's finding holds unchanged: no `do_POST` exists anywhere in
    the class chain, so POST/PUT/DELETE/PATCH are 501 from
    `BaseHTTPRequestHandler.handle_one_request`.

    `/allocator/...` is the one added route and it is a WHITELIST, not a second
    document root: the request path is unquoted, reduced to its basename (which
    drops every directory component, `..` included) and then matched against
    `_DAY_JSON` (a literal YYYY-MM-DD.json) or the literal `latest.json`. Anything else
    resolves to a name that cannot exist and 404s. That is deliberately stricter
    than `translate_path`'s own traversal filter -- the audit noted symlinks as
    the one escape `translate_path` does not close, and a whitelist closes it
    because no name it admits can be one.

    `/engines/...` (chunk 15b) is the second such whitelist and is written the
    same way on purpose: basename only, one literal pattern
    (`F_seasonality_<YYYY-MM>.json`) plus the literal `F_seasonality.json` for
    "latest". It differs from `/allocator/` in exactly one respect -- it may
    resolve into EITHER `state/engines/` or `docs/seed/engines/`, whichever
    holds a copy that passes its own content hash, volume first.
    """

    def log_message(self, fmt: str, *args) -> None:
        print("SEAL AUTHORITY HTTP " + (fmt % args), flush=True)

    def translate_path(self, path: str) -> str:
        raw = unquote(urlsplit(path).path)
        if raw.startswith("/allocator/"):
            return str(ALLOC / _allocator_name(raw))
        if raw.startswith("/engines/"):
            return str(_engine_served_path(raw))
        return super().translate_path(path)


def _allocator_name(raw: str) -> str:
    """The ONE file `/allocator/<...>` may name, or a name that cannot exist.

    `latest.json` is resolved to the newest record's own file name rather than
    written as a second copy: two files claiming to be the same record is how a
    corrected one gets served forever from the stale side of the pair, and
    `docs/DEPLOY_PLAN_2026-09-14.md` 3 already records that failure with
    `cp -rn` on the engine files.
    """
    name = posixpath.basename(posixpath.normpath(raw))
    if name == "latest.json":
        newest = latest_allocator_path()
        return newest.name if newest else "__no_allocator_record__"
    if _DAY_JSON.match(name):
        return name
    return "__refused__"


# ---------------------------------------------------------------------------
# BOOK F'S MONTHLY ENGINE FILE (chunk 15b)
# ---------------------------------------------------------------------------

def _engine_verifies(path: Path) -> bool:
    """True when the file matches its OWN `content_sha256` and names a month.

    The arithmetic is `prediction_book._sha` over the payload with the key
    removed -- the same function the sealed book and the allocator record are
    stamped with, and the same one `alpha/brains/seasonality_f._sha_of` and
    `scripts/engine_sync._canonical_sha` recompute on the consumer side. Four
    copies of one hash is a thing to keep in step and it is pinned by
    `tests_smoke_engine_artery`; four DIFFERENT hashes would be worse.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    claimed = payload.pop("content_sha256", None)
    if not claimed or claimed != prediction_book._sha(payload):
        return False
    m = _ENGINE_JSON.match(path.name)
    return bool(m and payload.get("month") == m.group(1) and payload.get("selected"))


def engine_file(month: str) -> Path | None:
    """The file to serve for `month`: the volume's copy, else the image's, else None.

    ORDER MATTERS AND IS THE WHOLE POINT. `state/engines/` is checked first so a
    corrected export can override a month the image already carries -- the exact
    move `cp -rn` refuses on the loop side, recorded in
    `docs/DEPLOY_PLAN_2026-09-14.md` 3 as a silent failure. A copy that does not
    verify is SKIPPED rather than served, so a half-written push falls back to
    the image instead of taking the book down.
    """
    for base in (ENGINES, SEED_ENGINES):
        p = base / f"F_seasonality_{month}.json"
        if p.is_file() and _engine_verifies(p):
            return p
    return None


def engine_months() -> list[str]:
    """Every month with a verified file anywhere, ascending. Never guesses one."""
    months = set()
    for base in (ENGINES, SEED_ENGINES):
        if not base.is_dir():
            continue
        for p in base.glob("F_seasonality_*.json"):
            m = _ENGINE_JSON.match(p.name)
            if m and _engine_verifies(p):
                months.add(m.group(1))
    return sorted(months)


def _engine_served_path(raw: str) -> Path:
    """The ONE file `/engines/<...>` may name, or a path that cannot exist.

    Basename-only, like `_allocator_name`: `posixpath.normpath` then
    `posixpath.basename` drops every directory component including `..`, so
    `/engines/latest/F_seasonality.json` and `/engines/../../.env` are decided by
    the last segment alone. A refusal resolves INSIDE the engines directory
    under a name nothing can create, so the handler 404s instead of reaching
    `translate_path`'s own (weaker) traversal filter.

    `latest` is resolved to the newest VERIFIED month's real file rather than
    written as a second copy on disk, for the reason `/allocator/latest.json`
    gives: two files claiming to be one artefact is how the stale half gets
    served for ever.
    """
    name = posixpath.basename(posixpath.normpath(unquote(urlsplit(raw).path)))
    if name == _ENGINE_LATEST:
        months = engine_months()
        if not months:
            return ENGINES / "__no_engine_file__"
        name = f"F_seasonality_{months[-1]}.json"
    m = _ENGINE_JSON.match(name)
    if not m:
        return ENGINES / "__refused__"
    path = engine_file(m.group(1))
    # A month that exists but fails its own hash is NOT served from the other
    # side of the pair silently -- `engine_file` already tried both and refused
    # both, and an unverified engine file is exactly the thing this artery is
    # for refusing.
    return path if path is not None else ENGINES / "__refused_unverified__"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=int(os.getenv("PORT", "8080")))
    p.add_argument("--check-seconds", type=int, default=300)
    a = p.parse_args(argv)
    BOOKS.mkdir(parents=True, exist_ok=True)
    ALLOC.mkdir(parents=True, exist_ok=True)
    ENGINES.mkdir(parents=True, exist_ok=True)

    # Serve immediately so consumers get a deterministic 404 while a long
    # whole-market refresh is running, instead of a connection failure that is
    # indistinguishable from a dead authority.
    os.chdir(BOOKS)
    server = ThreadingHTTPServer(("0.0.0.0", a.port), QuietHandler)
    thread = threading.Thread(target=maintainer, args=(max(60, a.check_seconds),), daemon=True)
    thread.start()
    print(f"SEAL AUTHORITY serving {BOOKS} on :{a.port}", flush=True)
    print(f"SEAL AUTHORITY serving {ALLOC} at /allocator/<day>.json and "
          f"/allocator/latest.json on :{a.port}", flush=True)
    _months = engine_months()
    _note = ", ".join(_months) if _months else (
        "NONE -- every /engines/ request will 404 and hack3 declines, "
        "which is the designed failure")
    print(f"SEAL AUTHORITY serving Book F engines at "
          f"/engines/F_seasonality_<YYYY-MM>.json and "
          f"/engines/latest/F_seasonality.json on :{a.port}; verified months: "
          f"{_note} (volume {ENGINES}, image {SEED_ENGINES})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
