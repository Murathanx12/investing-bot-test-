"""OWNERSHIP WATCH -- record every 13D/13G, and keep the attention watchlist.

    python -m scripts.ownership_watch                    # today ET (+ a first-run sweep)
    python -m scripts.ownership_watch --day 2026-08-20   # one named day
    python -m scripts.ownership_watch --backfill 10      # the last 10 business days
    python -m scripts.ownership_watch --rebuild-only     # no network; watchlist only

WHAT IT WRITES
==============
    state/research/ownership/{day}.jsonl          append-only, one line per filing
    state/research/ownership/attention_watchlist.json   the last 45 days' subjects

The jsonl is the POINT-IN-TIME record: what EDGAR published that day and what we
could resolve about it AT THAT MOMENT. Nothing rewrites a line. The watchlist is
derived and disposable -- delete it and the next run rebuilds it identically
from the jsonl, which is the property that makes it safe for `scripts/tracker.py`
to read at the top of a refresh.

WHY IT SWEEPS BACKWARDS
=======================
EDGAR has no Saturday index, and this job has no guarantee of running. A watcher
that only ever asks about TODAY loses a Friday 13G to any weekend it is not
started, and loses it SILENTLY -- there would be no file, no gap, nothing to
notice. So a day with no file yet inside the trailing window is fetched, and the
run says which days it filled in. Days already on disk are not re-fetched.

WHAT IT DOES NOT DO
===================
It places nothing and scores nothing. Reaching the nightly loop is a separate,
attended step; this is a CLI and a file.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from alpha.sources import edgar_ownership as own
from alpha.sources.http import SourceRefusal

ET = ZoneInfo("America/New_York")
#: The trailing window a run will fill in if a day has no file. Five business
#: days covers a long weekend plus a laptop that was shut.
FIRST_RUN_BUSINESS_DAYS = 5


def _today_et() -> str:
    return datetime.now(ET).date().isoformat()


def business_days_back(day: str, n: int) -> list[str]:
    """The `n` business days strictly BEFORE `day`, oldest first.

    Weekday-only. US market holidays are NOT excluded: EDGAR simply has no index
    on them, the fetch refuses with a 403/404, and the run reports it as a day
    with no index rather than pretending to a filing count.
    """
    out: list[str] = []
    d = date.fromisoformat(day)
    while len(out) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            out.append(d.isoformat())
    return list(reversed(out))


def days_to_sweep(day: str, *, backfill: int) -> list[str]:
    """`day`, plus any of the trailing business days that has no file yet."""
    days = [d for d in business_days_back(day, backfill)
            if not own.day_path(d).exists()]
    return days + [day]


def watch_day(day: str) -> dict:
    """Fetch, resolve and append one day. Returns counts; never raises on a 403.

    Written STREAMING, and idempotent BEFORE the network: an accession already
    on the file is dropped from the work list before its header is fetched, so
    re-running a finished 1,615-filing day costs one index request rather than
    twenty minutes of requests whose answers are then thrown away.
    """
    try:
        recs = own.parse_form_index(own.fetch_daily_index(day), day=day)
        tickers = own.cik_ticker_map()
    except SourceRefusal as exc:
        # A weekend, a holiday, or a day EDGAR has not published yet. Said out
        # loud and counted as NO INDEX, which is a different fact from zero
        # filings and must never be recorded as one.
        print(f"  {day}: no index ({exc})")
        return {"day": day, "index": False, "filings": 0, "new": 0, "resolved": 0}

    seen = own.recorded_accessions(day)
    todo = [r for r in recs if r["accession"] not in seen]
    print(f"  {day}: {len(recs)} filings in the index | {len(seen)} already recorded | "
          f"{len(todo)} to resolve", flush=True)

    seen_tickers: set[str] = set()
    counts = {"resolved": 0}

    def _resolving():
        for i, rec in enumerate(own.iter_resolved(todo, tickers=tickers), 1):
            if rec.get("subject_ticker"):
                counts["resolved"] += 1
                seen_tickers.add(rec["subject_ticker"])
            if i % 200 == 0 or i == len(todo):
                print(f"      [{i}/{len(todo)}] {counts['resolved']} resolved, "
                      f"{len(seen_tickers)} distinct tickers", flush=True)
            yield rec

    written, skipped = own.append_filings(day, _resolving())
    unresolved = written - counts["resolved"]
    print(f"  {day}: {written} newly recorded, {skipped} skipped | "
          f"{counts['resolved']} resolved to a ticker, {unresolved} not | "
          f"{len(seen_tickers)} distinct subjects", flush=True)
    if seen_tickers:
        head = ", ".join(sorted(seen_tickers)[:20])
        print(f"      subjects: {head}{' ...' if len(seen_tickers) > 20 else ''}")
    return {"day": day, "index": True, "filings": len(recs), "new": written,
            "resolved": counts["resolved"]}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--day", help="YYYY-MM-DD (default: today ET)")
    p.add_argument("--backfill", type=int, default=None,
                   help=f"business days to sweep behind --day "
                        f"(default: {FIRST_RUN_BUSINESS_DAYS} where a day has no file)")
    p.add_argument("--rebuild-only", action="store_true",
                   help="rebuild the watchlist from what is already recorded; no network")
    p.add_argument("--cap", type=int, default=own.WATCHLIST_MAX,
                   help=f"max symbols on the watchlist (default {own.WATCHLIST_MAX}). "
                        f"Measured: an ordinary day adds ~40 subjects, so the default "
                        f"makes the 45-day window an effective ~5-day one")
    args = p.parse_args(argv)

    day = args.day or _today_et()
    try:
        date.fromisoformat(day)
    except ValueError:
        print(f"REFUSED: --day {day!r} is not YYYY-MM-DD")
        return 2

    print(f"ownership watch | day {day} | store {own._store()}")

    totals = {"filings": 0, "new": 0, "resolved": 0, "days_with_index": 0}
    if not args.rebuild_only:
        backfill = FIRST_RUN_BUSINESS_DAYS if args.backfill is None else args.backfill
        sweep = days_to_sweep(day, backfill=backfill)
        if len(sweep) > 1:
            print(f"sweeping {len(sweep)} days (a day already on disk is not re-fetched): "
                  f"{', '.join(sweep)}")
        for d in sweep:
            r = watch_day(d)
            totals["filings"] += r["filings"]
            totals["new"] += r["new"]
            totals["resolved"] += r["resolved"]
            totals["days_with_index"] += 1 if r["index"] else 0

    # ---- the watchlist, always rebuilt from the whole recorded window --------
    floor = (date.fromisoformat(day) - timedelta(days=own.WATCHLIST_DAYS)).isoformat()
    wl = own.build_watchlist(own.read_recorded(since=floor), as_of=day, cap=args.cap)
    path = own.write_watchlist(wl)

    print()
    print(f"FILINGS   {totals['filings']} across {totals['days_with_index']} day(s) with an "
          f"index | {totals['new']} newly recorded | {totals['resolved']} subject-resolved")
    print(f"WATCHLIST {wl['n_symbols']} symbols over {wl['window_days']} days "
          f"(from {wl['window_from']}) -> {path}")
    if wl["n_symbols_before_cap"] > wl["n_symbols"]:
        print(f"          CAPPED: {wl['n_symbols_before_cap']} symbols qualified, "
              f"newest {wl['cap']} kept")
    if wl["n_filings_unresolved_subject"]:
        print(f"          {wl['n_filings_unresolved_subject']} recorded filings in the window "
              f"carry no subject ticker (kept on file, named in `unresolved_reason`)")
    print(f"          {', '.join(wl['symbols'][:25])}"
          f"{' ...' if len(wl['symbols']) > 25 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
