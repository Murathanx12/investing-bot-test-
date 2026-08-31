"""Write today's CompanyState rows. Append-only; run it every night.

    python -m scripts.company_state_append              # today, whole tracker universe
    python -m scripts.company_state_append --day 2026-08-31
    python -m scripts.company_state_append --dry-run    # assemble and report, write nothing

Joins what already exists -- the tracker's day file, the news-attention
baseline, the STORED EDGAR filings and the sealed book's rule numbers -- into
one append-only row per company per day. It fetches NOTHING: every input is
already on disk, so this is cheap, offline, and safe to run beside a refresh.

WHY IT JOINS RATHER THAN COLLECTS
=================================
Each of those sources already has its own guards, receipts and refusal
semantics. Re-fetching here would duplicate them and the two copies would drift.
What is missing is not another collector; it is the DAILY VINTAGE that ties them
together, which is the thing no vendor sells and the thing a year of running
turns into a training table.

BACKFILL IS EXPLICIT AND LIMITED
================================
`--day` will assemble a past day from the tracker files already on disk, and
that is legitimate -- those files are themselves dated vintages. It cannot
recover a day the tracker never wrote. Stated so nobody later believes the
history is deeper than it is.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpha import company_state, newsmakers
from alpha import tracker as _tracker

STATE = Path(__file__).resolve().parent.parent / "state"


def _edgar_counts(as_of: str | None = None) -> dict[str, dict]:
    """{symbol: {total, by_form}} from the STORED FILINGS, not from the receipt.

    The first version read `edgar_backfill_<date>.json`. That receipt is named
    per DAY and is REWRITTEN by every run, so seven batches of 500 names each
    overwrote the last and it held 59 records -- while 161,215 filings sat
    correctly in the corpus. CompanyState then recorded EDGAR coverage on 164
    of 3,059 names and looked merely sparse rather than wrong.

    A summary artefact is not the data. Counting from the observations also
    makes this point-in-time: `as_of` bounds `observed_at`, so a past day's
    vintage counts only the filings we could have known about THEN.
    """
    from alpha.sources import corpus

    out: dict[str, dict] = {}
    for r in corpus.read(as_of=as_of):
        if r.get("source_type") != "company_filing":
            continue
        form = str(((r.get("extra") or {}).get("form")) or r.get("body") or "other")
        for sym in (r.get("symbols") or []):
            d = out.setdefault(str(sym).upper(), {"total": 0, "by_form": {}})
            d["total"] += 1
            d["by_form"][form] = d["by_form"].get(form, 0) + 1
    return out


def _attention() -> dict[str, dict]:
    """{symbol: attention row} scored against the name's own trailing baseline."""
    base = newsmakers.load_baseline()
    if not base:
        return {}
    # The most recent day in the baseline is "today's" attention.
    p = newsmakers.BASELINE
    last = None
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                last = json.loads(line)
            except ValueError:
                continue
    if not last:
        return {}
    today = {s: {"symbol": s, "n_articles": n, "n_sources": 0, "sources": [],
                 "headlines": [], "weighted": float(n), "first_at": None}
             for s, n in (last.get("counts") or {}).items()}
    # Exclude the latest day from its own baseline, or every name is compared
    # against a history that already contains today.
    hist = {}
    for line in p.read_text(encoding="utf-8").splitlines()[:-1]:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        for s, n in (row.get("counts") or {}).items():
            hist.setdefault(s.upper(), []).append(float(n))
    return {r["symbol"]: r for r in newsmakers.score(today, hist)}


def _book_numbers(day: str) -> dict[str, dict]:
    """{symbol: rule/brain numbers} from the sealed book, if one exists."""
    for base in (STATE / "predictions",
                 Path(__file__).resolve().parent.parent / "docs" / "seed" / "predictions"):
        cands = sorted(base.glob(f"{day}.json")) + sorted(base.glob(f"{day}.resealed_*.json"))
        if not cands:
            continue
        try:
            b = json.loads(cands[-1].read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        return {str(p.get("symbol", "")).upper(): p for p in (b.get("predictions") or [])}
    return {}


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                           # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=None, help="ET trading day (default: newest tracker day)")
    ap.add_argument("--dry-run", action="store_true", help="assemble and report; write nothing")
    args = ap.parse_args(argv)

    from scripts import tracker as tracker_cli

    day = args.day or tracker_cli.latest_day()
    if not day:
        print("REFUSED: no tracker day on disk -- there is no state to record.")
        return 1
    raw = tracker_cli.load_day(day)
    if not raw:
        print(f"REFUSED: tracker file for {day} is empty.")
        return 1

    rows = _tracker.build_rows(raw)
    prev_day = tracker_cli.latest_day(before=day)
    _tracker.apply_status(rows, prev_by_symbol={r["symbol"]: r for r in tracker_cli.load_day(prev_day)}
                          if prev_day else {})

    # The band 12 months ago, for `band_change_12m`. Absent early in the
    # tracker's life, and recorded as absent rather than as "no change".
    year_ago = (datetime.fromisoformat(day) - timedelta(days=365)).date().isoformat()
    old_day = tracker_cli.latest_day(before=year_ago)
    prior_band: dict[str, int] = {}
    if old_day:
        for r in tracker_cli.load_day(old_day):
            b, _ = company_state.band_of(r.get("median_dollar_volume"))
            if b is not None:
                prior_band[str(r.get("symbol", "")).upper()] = b

    # `as_of` the day being recorded: a vintage must not count filings that
    # arrived after it.
    att, fil, book = _attention(), _edgar_counts(as_of=day), _book_numbers(day)

    out = []
    for r in rows:
        sym = str(r.get("symbol", "")).upper()
        out.append(company_state.build_row(
            day=day, tracker_row=r, prior_band=prior_band.get(sym),
            attention=att.get(sym), filings=fil.get(sym), book_row=book.get(sym)))

    cov = lambda k: sum(1 for r in out if r.get(k) is not None)
    print(f"CompanyState {day}: {len(out):,} rows")
    print(f"  band                 {cov('band'):>6,}   "
          f"band_change_12m {cov('band_change_12m'):>6,}"
          + ("" if old_day else "   (no tracker day ~1y back yet)"))
    print(f"  expected_rt_bps      {cov('expected_round_trip_bps'):>6,}   "
          f"analyst_disagreement {cov('analyst_disagreement'):>6,}")
    print(f"  attention_z          {cov('attention_z'):>6,}   "
          f"news_articles {cov('news_articles'):>6,}")
    print(f"  edgar_filings_6m     {cov('edgar_filings_6m'):>6,}   "
          f"rule numbers  {cov('exp_return'):>6,}")
    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0
    path = company_state.write_day(out, day)
    print(f"\nwrote {path}"
          + ("   (a vintage for this day already existed; written beside it)"
             if ".rerun_" in path.name else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
