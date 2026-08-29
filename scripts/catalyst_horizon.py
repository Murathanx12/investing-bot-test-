"""CATALYST_HORIZON -- the DIARY the engine never had: every dated event, 1 to 6 months out.

    python -m scripts.catalyst_horizon --days 180                 # everything
    python -m scripts.catalyst_horizon --days 180 --murat         # + trial readouts for his names
    python -m scripts.catalyst_horizon --show 40                  # read what is stored

WHY (roadmap 2026-08-29 §3, §5)
===============================
Murat's selection rule requires **"a NAMED catalyst inside 12 months"** -- a
Phase 3 readout, a PDUFA date, a launch, a legal decision. The engine held no
forward-dated events at all beyond a two-day earnings peek, so the one
condition his rule leans on hardest was the one condition it could not
evaluate. A screen that cannot see the catalyst is a screen on price and
rating alone, which is how a rule that produced +300% names also produced
-35% names.

FOUR SOURCES, EACH WITH ITS DATE VERIFIED OR ITS ROW MARKED UNVERIFIED
======================================================================
- **Finnhub `/calendar/earnings`** -- report dates with `bmo`/`amc`. A
  confirmed date is `source_verified: True`; an ESTIMATED one is not, and the
  difference decides whether an option expiry can be chosen at all.
- **FRED `/releases/dates`** -- scheduled macro. The publisher's own calendar,
  so these are verified by construction.
- **ClinicalTrials.gov v2** -- `primaryCompletionDateStruct`, whose `type` is
  ACTUAL or ESTIMATED. An ESTIMATED completion is a *hint*, never a date to
  buy an expiry against, and the row says so.
- **the corpus itself** -- anything a backfilled headline already dated.

THE 1500-ROW CAP THAT DELETES THE NEAR TERM (measured 2026-08-29)
=================================================================
Asking Finnhub for 2026-08-30 -> 2027-02-28 in one call returns exactly 1500
rows spanning **2027-02-08 to 2027-02-26**. The cap is silent and it returns
the TAIL, so a single wide call drops the next five months -- the only part
that is tradeable -- while looking like a full result.

So `earnings_window()` pages in short windows and then CHECKS that what came
back actually spans what was asked. A window that returns at the cap is
SPLIT, not accepted. This is the same failure as filtering an options pull on
`delta`: a bound that looks like a limit and behaves like a deletion of the
informative end.

WHAT IT IS NOT
==============
Shadow, like everything upstream of a decision. It writes rows into
`alpha.sources.corpus` with `tense="future"` and a receipt at
`state/corpus/horizon_<day>.json`. It places nothing, sizes nothing, and its
rows are marked `future` precisely so a backtest cannot mistake a diary entry
for something that happened.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone

from alpha import config, fleet
from alpha.sources import corpus, finnhub
from alpha.sources.http import SourceRefusal, get_json

from scripts.news_backfill import MURAT_NAMES

#: TWO endpoints, one letter apart, and they answer different questions.
#: `/releases/dates` (plural) is EVERY release's dates and IGNORES release_id;
#: `/release/dates` (singular) is ONE release's. Passing release_id to the
#: plural one returned 11,000 rows that looked like a rich calendar and were
#: the whole firehose again -- the dedupe absorbed most of it, which is
#: exactly what made it hard to see. Named separately so the mistake is
#: visible at the call site.
FRED_ALL_RELEASE_DATES = "https://api.stlouisfed.org/fred/releases/dates"
FRED_ONE_RELEASE_DATES = "https://api.stlouisfed.org/fred/release/dates"
CTGOV = "https://clinicaltrials.gov/api/v2/studies"

#: Finnhub returns at most this many calendar rows and gives no warning.
#: A window that hits it is TRUNCATED, not complete.
FINNHUB_ROW_CAP = 1500

#: Which FRED releases move a whole book. Matched on the release NAME the API
#: itself returns rather than on hardcoded ids, so a renamed or renumbered
#: release degrades to "not matched" instead of to a wrong row.
MACRO_PATTERNS = re.compile(
    r"(employment situation|consumer price index|producer price index|"
    r"fomc|federal open market|gross domestic product|personal income and outlays|"
    r"retail sales|advance monthly sales|job openings|jolts|"
    r"industrial production|housing starts|consumer sentiment|"
    r"unemployment insurance weekly)", re.I)

#: The same names carry regional and derived cuts that no book trades. 'Gross
#: Domestic Product by County' matches the pattern above and is not an event.
#:
#: `FOMC Press Release` is excluded for a subtler reason, and the cadence check
#: below is what found it: FRED release 101 carries **363 dates a year**. It is
#: not the eight-meetings-a-year event calendar -- it is the DAILY fed funds
#: target series, whose nominal publisher is the FOMC press release. Every one
#: of those rows is a true FRED release date and a useless catalyst, and
#: keeping them would put a macro event on every day of the diary, which reads
#: as "there is always an event" and is worse than holding no calendar at all.
#: `State Unemployment Insurance Weekly Claims Report` is the same Thursday
#: print as the national one, cut by state -- 17 duplicate rows in a 180-day
#: window, on the same dates. A calendar that lists one event twice makes a
#: reader who is counting events wrong.
MACRO_EXCLUDE = re.compile(r"(by state|by county|by industry|debt to|research |monthly state|"
                           r"selected real|fomc press release|^state unemployment)", re.I)

#: WHAT THIS CALENDAR KNOWS IT DOES NOT HAVE. Written onto every receipt,
#: because a missing source that nobody records becomes a missing source that
#: nobody remembers -- and the reader of a clean-looking calendar will assume
#: the absence of an FOMC row means no meeting.
KNOWN_GAPS = [
    "FOMC MEETING DATES: not available from FRED (release 101 is the daily fed-funds "
    "series, 363 dates/yr, excluded). Real meeting calendar is federalreserve.gov HTML. "
    "Treat FOMC dates as UNKNOWN here, never as absent.",
    "FDA PDUFA DATES: no free API. ClinicalTrials.gov primary-completion is a proxy for "
    "a READOUT, not for an approval decision.",
    "GUIDANCE / INVESTOR DAYS / LOCK-UP EXPIRIES: not collected.",
]


def _horizon(days: int) -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    return today.isoformat(), (today + timedelta(days=days)).isoformat()


def earnings_window(start: str, end: str, *, step_days: int = 14) -> tuple[list[dict], list[str]]:
    """Paged earnings calendar with a TRUNCATION CHECK on every window."""
    rows: list[dict] = []
    notes: list[str] = []
    cur = date.fromisoformat(start)
    stop = date.fromisoformat(end)
    while cur < stop:
        nxt = min(cur + timedelta(days=step_days), stop)
        try:
            got = finnhub.earnings_calendar(start=cur.isoformat(), end=nxt.isoformat())
        except SourceRefusal as exc:
            notes.append(f"finnhub calendar {cur}..{nxt}: {str(exc)[:80]}")
            cur = nxt
            continue
        if len(got) >= FINNHUB_ROW_CAP and step_days > 1:
            # TRUNCATED. Split rather than accept -- accepting would drop the
            # near end of this window and nothing would say so.
            notes.append(f"cap hit {cur}..{nxt} ({len(got)} rows) -> split")
            sub, sub_notes = earnings_window(cur.isoformat(), nxt.isoformat(),
                                             step_days=max(1, step_days // 2))
            rows += sub
            notes += sub_notes
        else:
            span = (min((r.get("date", "") for r in got), default=""),
                    max((r.get("date", "") for r in got), default=""))
            # Only a gap wide enough to hide a TRADING day is a truncation
            # signal. A window starting on a Saturday whose first row is Monday
            # is a calendar, not a defect -- and a note that fires every run
            # teaches the reader to skim the notes that matter.
            if got and (date.fromisoformat(span[0]) - cur).days > 3:
                notes.append(f"window {cur}..{nxt} returned {span[0]}..{span[1]} -- near end may be missing")
            rows += got
        cur = nxt
        time.sleep(1.1)
    return rows, notes


def macro_releases(start: str, end: str) -> tuple[list[dict], list[str]]:
    """Scheduled macro, asked RELEASE BY RELEASE rather than as one wide sweep.

    The first design paged `/fred/releases/dates` over the whole window: 3,376
    rows in six months, of which ~60 matter, and page 2 timed out on three
    consecutive attempts -- so the calendar came back holding 1,000 of 3,376
    rows and would have printed like a complete one.

    Asking for the whole firehose and discarding 98% of it was the mistake.
    `/fred/releases` is ONE call that names all 331 releases; the ~12 that move
    a book are selected from it by name, and each is then asked for its own
    dates -- four rows for Employment Situation over six months. Small calls
    that cannot time out, and the selection is DERIVED from what the API says
    exists rather than from hardcoded ids that a renumbering would silently
    break.
    """
    key = os.getenv("AAT_FRED_API_KEY", "").strip()
    if not key:
        return [], ["AAT_FRED_API_KEY is not set"]
    notes: list[str] = []
    try:
        d, _ = get_json("https://api.stlouisfed.org/fred/releases",
                        {"api_key": key, "file_type": "json", "limit": 1000}, timeout=45.0)
    except SourceRefusal as exc:
        return [], [f"fred releases list: {str(exc)[:80]}"]
    wanted = [r for r in ((d or {}).get("releases") or [])
              if MACRO_PATTERNS.search(str(r.get("name", "")))
              and not MACRO_EXCLUDE.search(str(r.get("name", "")))]
    out: list[dict] = []
    for rel in wanted:
        rid, name = rel.get("id"), str(rel.get("name", ""))
        got = None
        for attempt in range(3):
            try:
                got, _ = get_json(FRED_ONE_RELEASE_DATES, {"api_key": key, "file_type": "json", "release_id": rid,
                                         "realtime_start": start, "realtime_end": end,
                                         "include_release_dates_with_no_data": "true",
                                         "sort_order": "asc"}, timeout=45.0)
                break
            except SourceRefusal as exc:
                if attempt == 2:
                    notes.append(f"fred release {rid} ({name}): {str(exc)[:60]}")
                time.sleep(1.5 * (attempt + 1))
        if not got:
            continue
        dates = [r.get("date") for r in (got.get("release_dates") or []) if r.get("date")]

        # CADENCE CHECK -- `include_release_dates_with_no_data=true` is REQUIRED
        # for a forward calendar (with it false every future window returns 0),
        # but for some releases FRED pads the answer with every calendar day:
        # measured 2026-08-29, release 101 'FOMC Press Release' returned 125
        # dates over 180 days, while Employment Situation returned 4 and CPI 4.
        # A committee that meets eight times a year cannot have 125 dates, and
        # a padded row would put a macro catalyst on every day of the diary --
        # which reads as "there is always an event" and is worse than no
        # calendar at all.
        #
        # The bound is MEASURED, not asserted: the same release is asked what it
        # actually did over the trailing window, and a forward count far above
        # its own history is padding. A hardcoded "FOMC is monthly" would break
        # the day FRED renumbers or a new release behaves the same way.
        hist_n = None
        try:
            past_start = (date.fromisoformat(start) - timedelta(days=365)).isoformat()
            hist, _ = get_json(FRED_ONE_RELEASE_DATES,
                               {"api_key": key, "file_type": "json", "release_id": rid,
                                "realtime_start": past_start, "realtime_end": start,
                                "include_release_dates_with_no_data": "false",
                                "sort_order": "asc"}, timeout=45.0)
            hist_n = len(hist.get("release_dates") or [])
        except SourceRefusal:
            pass
        window_yr = (date.fromisoformat(end) - date.fromisoformat(start)).days / 365.0
        if hist_n:
            expected = max(1.0, hist_n * window_yr)
            if len(dates) > 3 * expected:
                notes.append(f"fred {name!r}: {len(dates)} forward dates vs {hist_n}/yr observed "
                             f"(~{expected:.0f} expected) -- PADDED, dropped")
                time.sleep(0.4)
                continue
        elif len(dates) > 60 * window_yr:
            notes.append(f"fred {name!r}: {len(dates)} forward dates and no history to check "
                         "against -- more than weekly, dropped as padded")
            time.sleep(0.4)
            continue

        for d0 in dates:
            out.append({"release_id": rid, "release_name": name, "date": d0,
                        "observed_cadence_per_year": hist_n})
        time.sleep(0.4)
    if len(out) == 0 and wanted:
        # Matching 12 releases and finding no dates is a REFUSAL, not a quiet
        # calendar; six months always contains an NFP.
        notes.append(f"fred: {len(wanted)} releases matched but ZERO dates returned -- treat macro as MISSING")
    return out, notes


def trial_milestones(sponsor: str, start: str, end: str, *, limit: int = 20) -> tuple[list[dict], list[str]]:
    """Primary completion dates in the window for one sponsor."""
    try:
        d, _ = get_json(CTGOV, {
            "query.term": f"AREA[PrimaryCompletionDate]RANGE[{start},{end}]",
            "query.spons": sponsor, "pageSize": limit, "format": "json",
            "filter.overallStatus": "RECRUITING|ACTIVE_NOT_RECRUITING|ENROLLING_BY_INVITATION"})
    except SourceRefusal as exc:
        return [], [f"ctgov {sponsor}: {str(exc)[:80]}"]
    return (d or {}).get("studies") or [], []


def sponsor_for(symbol: str) -> str | None:
    """Company name from Finnhub's profile -- DERIVED, not a hand-written table,
    so a wrong mapping shows up as no trials rather than as another firm's."""
    try:
        prof = finnhub.profile(symbol)
    except SourceRefusal:
        return None
    name = (prof or {}).get("name") or ""
    # 'Solid Power Inc' -> 'Solid Power'; the registry suffix hurts the match.
    return re.sub(r"\b(inc|corp|corporation|ltd|plc|holdings|group|co|sa|nv|ag)\b\.?,?\s*$",
                  "", name, flags=re.I).strip() or None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180, help="horizon in days (default 180 = 6 months)")
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--murat", action="store_true")
    ap.add_argument("--no-earnings", action="store_true")
    ap.add_argument("--no-macro", action="store_true")
    ap.add_argument("--no-trials", action="store_true")
    ap.add_argument("--show", type=int, default=0, help="print the stored horizon and exit")
    ap.add_argument("--all", action="store_true",
                    help="with --show: every name in the store, not just the watched set")
    args = ap.parse_args()
    config.load_env()

    start, end = _horizon(args.days)

    if args.show:
        # DEFAULT TO THE WATCHED SET. The store holds 8,500+ forward rows, of
        # which the overwhelming majority are earnings for names nobody here
        # trades: an unfiltered view spends 24 lines on tickers like JMM and
        # QQQX before the first row that matters. A diary nobody can read is a
        # diary nobody reads, so `--all` is opt-in.
        watch_show = {s.upper() for s in (args.symbols or [])} or set(MURAT_NAMES)
        if not args.all:
            try:
                watch_show |= set(fleet.theme_symbols())
            except Exception:                                           # noqa: BLE001
                pass
        rows = corpus.read(since=start, until=end, tense="future",
                           symbols=None if args.all else sorted(watch_show))
        if not args.all:
            # Macro carries no symbol, so a symbol filter would drop NFP and CPI
            # -- the two rows most likely to decide whether to hold anything at all.
            rows = sorted(rows + corpus.read(since=start, until=end, tense="future",
                                             kinds=["macro"]),
                          key=lambda r: str(r["effective_at"]))
        scope = "ALL names" if args.all else f"{len(watch_show)} watched names + macro"
        print(f"forward catalysts, {scope}\n")
        print(f"{'date':<12}{'kind':<10}{'ver':<5}{'symbols':<12}title")
        for r in rows[:args.show]:
            print(f"{str(r['effective_at'])[:10]:<12}{r['kind']:<10}"
                  f"{'yes' if r.get('source_verified') else 'no':<5}"
                  f"{','.join(r.get('symbols') or [])[:11]:<12}{r['title'][:66]}")
        total_all = len(corpus.read(since=start, until=end, tense="future"))
        print(f"\n{len(rows)} rows shown of {total_all} future rows in {start}..{end}")
        print("`ver` = the ISSUER confirmed the date. An UNCONFIRMED date must never "
              "choose an option expiry.")
        for g in KNOWN_GAPS:
            print(f"  GAP: {g}")
        return 0

    watch = {s.upper() for s in (args.symbols or [])}
    if args.murat or not watch:
        watch |= set(MURAT_NAMES)
    try:
        watch |= set(fleet.theme_symbols())
    except Exception:                                                   # noqa: BLE001
        pass

    now = corpus.utcnow()
    obs: list[corpus.Observation] = []
    notes: list[str] = []
    print(f"horizon {start} -> {end} ({args.days} days), {len(watch)} watched names")

    if not args.no_earnings:
        rows, n = earnings_window(start, end)
        notes += n
        seen_span = (min((r.get("date", "") for r in rows), default="-"),
                     max((r.get("date", "") for r in rows), default="-"))
        for r in rows:
            sym, when = str(r.get("symbol", "")).upper(), str(r.get("date", ""))
            if not sym or not when:
                continue
            hour = r.get("hour") or ""
            obs.append(corpus.Observation(
                kind="earnings", tense="future",
                title=f"{sym} Q{r.get('quarter')} {r.get('year')} earnings"
                      + (f" ({hour})" if hour else ""),
                body=f"EPS estimate {r.get('epsEstimate')}, revenue estimate {r.get('revenueEstimate')}",
                source="finnhub:calendar/earnings", source_type="sell_side",
                observed_at=now, effective_at=when, symbols=(sym,),
                independence_group="finnhub:earnings_calendar",
                source_verified=bool(hour),      # bmo/amc means the issuer confirmed a slot
                extra={"hour": hour, "quarter": r.get("quarter"), "year": r.get("year"),
                       "eps_estimate": r.get("epsEstimate"), "rev_estimate": r.get("revenueEstimate")}))
        print(f"  earnings: {len(rows)} rows, span {seen_span[0]}..{seen_span[1]}, "
              f"{sum(1 for o in obs if o.source_verified)} with a confirmed slot")

    if not args.no_macro:
        rel, n = macro_releases(start, end)
        notes += n
        for r in rel:
            obs.append(corpus.Observation(
                kind="macro", tense="future", title=str(r.get("release_name", "")),
                source="fred:releases/dates", source_type="government",
                observed_at=now, effective_at=str(r.get("date", "")),
                independence_group="gov:fred", source_verified=True,
                extra={"release_id": r.get("release_id")}))
        print(f"  macro: {len(rel)} market-moving releases")

    if not args.no_trials:
        bio = sorted(watch)
        hits = 0
        for j, sym in enumerate(bio):
            if j:
                time.sleep(1.1)
            spons = sponsor_for(sym)
            if not spons:
                continue
            studies, n = trial_milestones(spons, start, end)
            notes += n
            for st in studies:
                proto = st.get("protocolSection") or {}
                ident = proto.get("identificationModule") or {}
                status = proto.get("statusModule") or {}
                pcd = (status.get("primaryCompletionDateStruct") or {})
                when, dtype = str(pcd.get("date", "")), str(pcd.get("type", ""))
                if not when:
                    continue
                # 'YYYY-MM' means the sponsor gave a month, not a day.
                eff = when if len(when) == 10 else f"{when}-15"
                # Is the issuer the LEAD sponsor, or a collaborator on someone
                # else's trial? Both are real catalysts -- Kyverna's drug read
                # out by Penn still moves KYTX -- so the row is KEPT and the
                # relationship is recorded. Dropping the collaborator rows
                # would delete exactly the academic-run readouts that small
                # biotech leans on, and delete them invisibly.
                org = str((ident.get("organization") or {}).get("fullName", ""))
                lead = spons.split()[0].lower() in org.lower()
                hits += 1
                obs.append(corpus.Observation(
                    kind="clinical", tense="future",
                    title=f"{sym} primary completion: {ident.get('briefTitle', '')[:120]}",
                    body=f"{status.get('overallStatus', '')}; primary completion {when} ({dtype})",
                    url=f"https://clinicaltrials.gov/study/{ident.get('nctId', '')}",
                    source="clinicaltrials.gov", source_type="government",
                    observed_at=now, effective_at=eff, symbols=(sym,),
                    independence_group=f"issuer:{sym}",
                    # ESTIMATED is a HINT. An expiry must never be chosen against it.
                    source_verified=(dtype.upper() == "ACTUAL" and len(when) == 10),
                    extra={"nct_id": ident.get("nctId"), "date_type": dtype,
                           "date_granularity": "day" if len(when) == 10 else "month",
                           "sponsor": org, "sponsor_role": "lead" if lead else "collaborator",
                           "status": status.get("overallStatus")}))
        print(f"  clinical: {hits} dated milestones across {len(bio)} names")

    new, dup = corpus.append_many(obs)
    watched = [o for o in obs if set(o.symbols) & watch]
    print(f"\nstored {new} new future rows ({dup} already known); {len(watched)} touch a watched name")

    out = corpus.CORPUS / f"horizon_{date.today().isoformat()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "generated_utc": now, "start": start, "end": end, "days": args.days,
        "n_rows": len(obs), "n_new": new, "n_watched": len(watched),
        "by_kind": {k: sum(1 for o in obs if o.kind == k) for k in {o.kind for o in obs}},
        "n_verified": sum(1 for o in obs if o.source_verified),
        "watched": sorted(watch), "notes": notes, "known_gaps": KNOWN_GAPS,
        "next_30d_watched": [
            {"date": o.effective_at, "kind": o.kind, "symbols": list(o.symbols),
             "title": o.title, "verified": o.source_verified}
            for o in sorted(watched, key=lambda o: o.effective_at)
            if o.effective_at <= (date.today() + timedelta(days=30)).isoformat()],
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"receipt: {out}")
    if notes:
        print(f"notes ({len(notes)}): " + "; ".join(notes[:5]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
