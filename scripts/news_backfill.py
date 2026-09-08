"""NEWS_BACKFILL -- give the engine a MEMORY: past news per name, RESUMABLY.

    python -m scripts.news_backfill --stats
    python -m scripts.news_backfill --start 2025-01-01 --end 2026-09-08 --universe fleet --no-finnhub
    python -m scripts.news_backfill --start 2015-01-01 --end 2026-09-08 --universe tradable --no-finnhub
    python -m scripts.news_backfill --start 2026-07-01 --end 2026-09-08 --symbols SLDP KYTX AARD
    python -m scripts.news_backfill --start ... --end ... --resume-status   # where did it get to?

WHY (measured, 2026-08-29)
==========================
The Featherless digest read 394 headlines over 156 names and gave **none of
Murat's twenty names a bet**, because the only news source in the pipe was
Alpaca/Benzinga over a 48-hour window, and Benzinga had not written about
SLDP, KYTX or AARD that week. The engine could not have known that AARD is on
a clinical hold with unblinded data due in Q3 -- the fact is nine months old
and the window was two days.

WHY IT WAS REWRITTEN (measured, 2026-09-07 03:18)
=================================================
A 134-month run DIED with the Alpaca leg 112 months in (83.6%) and the Finnhub
leg not started. There was no cursor, no log file and no PID file, so:

  * nothing could be resumed -- the work was gone, not paused;
  * nothing could say why it stopped, or when;
  * the only receipt was written at the END, so a run that never ends produces
    no evidence at all. "27% through" was quoted in a document afterwards with
    no derivation behind it, because there was nothing to derive it from.

So this script now runs through `scripts.pull_journal`: a per-month cursor, a
log on disk, a pid file, and **a coverage receipt per month**. Re-running the
same command RESUMES; the corpus dedupes on `uid`, so a resumed month costs a
few duplicate fetches and never a duplicate row.

And the window is now `--start` / `--end` as explicit ISO dates. The old
`--months N` counted back from *today*, which means the same command names a
different window every day it is run: two "identical" runs are not comparable,
a cursor cannot be keyed on the job, and a coverage table has no fixed
denominator. A relative window is a bug in a reproducibility system.

THREE SOURCES, AND WHY THE SECOND ONE IS THE POINT
==================================================
- **Alpaca/Benzinga** (`/v1beta1/news`) -- deep and fast for names a US wire
  covers, paged month by month, **20 symbols per call**, so a whole-market
  universe costs `ceil(N/20)` calls per month rather than N.
- **Finnhub `company-news`** -- PER SYMBOL, and it covers the small biotech and
  small-cap names Benzinga ignores. **This is the fix for the coverage gap**:
  it is asked per name rather than per wire, so a name with no wire coverage
  still gets its own history instead of silently getting none. It is also
  ~1.1 s/call and therefore the leg that dominates the wall clock.
- **SEC EDGAR** -- 8-K/10-Q press releases (`scripts.edgar_backfill`). The
  issuer speaking directly, so `independence_group` is the issuer and a wire
  restating it is not a second witness.

RATE LIMITS ARE MEASURED, NOT ASSUMED
=====================================
Finnhub free tier is 60 calls/minute, so the loop pauses 1.1 s between calls
and retries a 429 with backoff -- a dropped window is INDISTINGUISHABLE from
"this company had no news that month", which is exactly the false silence the
corpus was built to end. Alpaca news allows 50/page with `next_page_token` and
is paged until exhausted or `--max-pages`.

WHAT THIS DOES NOT DO
=====================
It stores what was PUBLISHED. It does not decide what any of it meant, does
not rank, does not size and places nothing. `observed_at` is the publication
timestamp, so every row is safe to condition on at any later date -- and
unsafe to condition on before it, which `corpus.read(as_of=...)` enforces.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timezone

from alpha import config, fleet
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal
from alpha.sources import corpus, finnhub
from alpha.sources.http import SourceRefusal
from scripts import pull_journal, tradable_universe

#: Murat's own list (roadmap §3, reconstructed from four PDFs). These are the
#: names the 48-hour pipe structurally cannot see, so they are the acceptance
#: test for this script: after a run, every one of them must have rows.
MURAT_NAMES = ["SLDP", "DKNG", "HUBS", "BHVN", "AMSC", "KYTX", "PRCH", "NTLA",
               "ABSI", "QUBT", "AARD", "SOC", "TSM", "MU", "MRVL", "AMD",
               "SRRK", "OLMA", "SLNO", "BEAM"]

FINNHUB_PAUSE_S = 1.1          # 60/min free tier, with headroom
ALPACA_PAGE_LIMIT = 50
ALPACA_BATCH = 20              # symbols per /v1beta1/news call

#: Below this many items over the whole backfill a name is reported as THIN.
#: Three is the floor at which a digest can tell "quiet" from "unseen".
THIN_ITEMS = 3


def window_universe_symbols() -> list[str]:
    """The names `scripts.window_universe --json` wrote. Empty if it never ran --
    stated as empty, not silently absent, so the caller can print it."""
    p = corpus.STATE / "window_universe.json"
    if not p.exists():
        return []
    try:
        return [str(s).upper() for s in json.loads(p.read_text(encoding="utf-8")).get("universe", [])]
    except (json.JSONDecodeError, OSError):
        return []


def wide_universe() -> list[str]:
    """MURAT_NAMES + the theme basket + the window universe + the three indices,
    deduped -- the ~160 names the fleet can actually trade. Shared by every
    collector so "the universe" is one function and not four lists."""
    syms: set[str] = set(MURAT_NAMES) | {"SPY", "QQQ", "IWM"}
    try:
        syms.update(s.upper() for s in fleet.theme_symbols())
    except Exception:                                                   # noqa: BLE001
        pass
    syms.update(window_universe_symbols())
    return sorted(syms)


def _universe(args: argparse.Namespace) -> list[str]:
    """The names to pull. `tradable` REFUSES rather than falling back: a
    whole-market claim built on a silent 156-name fallback is the failure this
    lane exists to end."""
    syms: set[str] = set()
    if getattr(args, "symbols", None):
        syms.update(s.upper() for s in args.symbols)
    if getattr(args, "murat", False) or getattr(args, "universe", None) == "murat":
        syms.update(MURAT_NAMES)
    if getattr(args, "universe", None) == "fleet":
        syms.update(wide_universe())
    if getattr(args, "universe", None) == "tradable":
        syms.update(tradable_universe.load())        # raises UniverseRefusal
        syms.update(MURAT_NAMES)                     # the acceptance names, always
    if not syms:
        syms.update({"SPY", "QQQ", "IWM"})
        try:
            syms.update(fleet.theme_symbols())
        except Exception:                                               # noqa: BLE001
            pass
        syms.update(MURAT_NAMES)
    return sorted(syms)


# --------------------------------------------------------------------- fetchers

def alpaca_batch(client, batch: list[str], start: str, end: str,
                 *, max_pages: int = 40) -> tuple[list[corpus.Observation], list[str], int]:
    """Every Benzinga item for ONE batch of <=20 symbols in [start, end), paged.

    Returns (observations, refusals, pages_read). One batch is the resumable
    UNIT inside a month: the cursor records how many of them are behind us, so
    a kill costs one batch of API work rather than a month of it.
    """
    obs: list[corpus.Observation] = []
    refusals: list[str] = []
    token, pages = None, 0
    while pages < max_pages:
        params = {"symbols": ",".join(batch), "limit": ALPACA_PAGE_LIMIT, "sort": "desc",
                  "start": f"{start}T00:00:00Z", "end": f"{end}T00:00:00Z"}
        if token:
            params["page_token"] = token
        try:
            d = client._request("GET", "/v1beta1/news", base=config.data_url(), params=params)
        except BrokerRefusal as exc:
            refusals.append(f"alpaca {batch[0]}..{batch[-1]} {start}: {str(exc)[:120]}")
            break
        items = (d or {}).get("news") or []
        wanted = {s.upper() for s in batch}
        for n in items:
            at = n.get("created_at") or n.get("updated_at")
            if not at:
                # An item with no timestamp is not an observation. Inventing
                # one at the start of the month is a PIT leak in the
                # direction that flatters every number (2026-08-29 review).
                refusals.append(f"alpaca {batch[0]}..{batch[-1]} {start}: item without timestamp dropped")
                continue
            syms = tuple(s.upper() for s in (n.get("symbols") or []) if s.upper() in wanted)
            if not syms:
                continue
            try:
                obs.append(corpus.Observation(
                    kind="news", tense="past", title=(n.get("headline") or "").strip(),
                    body=(n.get("summary") or "")[:600], url=n.get("url") or "",
                    source=f"alpaca:{n.get('source') or 'benzinga'}", source_type="wire_service",
                    observed_at=at, effective_at=at[:10], symbols=syms,
                    independence_group=f"wire:{n.get('source') or 'benzinga'}",
                    extra={"author": n.get("author"), "id": n.get("id")}))
            except corpus.CorpusRefusal:
                continue
        token = (d or {}).get("next_page_token")
        pages += 1
        if not token or not items:
            break
    if pages >= max_pages and token:
        # A truncated batch must SAY it was truncated. Silently stopping at
        # page 40 reads downstream as "that is all the news there was".
        refusals.append(f"alpaca {batch[0]}..{batch[-1]} {start}: TRUNCATED at max_pages={max_pages}")
    return obs, refusals, pages


def alpaca_history(client, symbols: list[str], start: str, end: str,
                   *, max_pages: int = 40) -> tuple[list[corpus.Observation], list[str]]:
    """Every Benzinga item for these symbols in [start, end). Kept for callers
    that want the whole month in one call and do not need a cursor."""
    obs: list[corpus.Observation] = []
    refusals: list[str] = []
    for i in range(0, len(symbols), ALPACA_BATCH):
        o, r, _ = alpaca_batch(client, symbols[i:i + ALPACA_BATCH], start, end, max_pages=max_pages)
        obs += o
        refusals += r
    return obs, refusals


def finnhub_history(symbol: str, start: str, end: str) -> tuple[list[corpus.Observation], list[str]]:
    """Per-NAME coverage. The point of this source is the names wires skip.

    A 429 HERE IS THE BUG THIS WHOLE MODULE EXISTS TO FIX, one level down.
    Measured on the first 12-month run: 31 windows were rate-limited, and they
    landed on SRRK (10 months), HUBS (8), KYTX (8) and PRCH (5) -- exactly the
    small names whose counts are thin, where a missing month is a large share
    of the whole record. A dropped window is INDISTINGUISHABLE from "this
    company had no news that month", which is precisely the false silence the
    corpus was built to end.

    So a 429 is retried with backoff rather than recorded as an absence, and
    the caller reports which months actually came back.
    """
    rows = None
    for attempt in range(4):
        try:
            rows = finnhub.company_news(symbol, start=start, end=end)
            break
        except SourceRefusal as exc:
            if "429" not in str(exc) or attempt == 3:
                return [], [f"finnhub {symbol} {start}: {str(exc)[:90]}"]
            time.sleep(2.0 * (2 ** attempt))       # 2s, 4s, 8s
    if rows is None:
        return [], [f"finnhub {symbol} {start}: rate limited after 4 tries"]
    obs = []
    for n in rows:
        ts = n.get("datetime")
        if not ts:
            continue
        at = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat(timespec="seconds")
        try:
            obs.append(corpus.Observation(
                kind="news", tense="past", title=(n.get("headline") or "").strip(),
                body=(n.get("summary") or "")[:600], url=n.get("url") or "",
                source=f"finnhub:{n.get('source') or 'unknown'}", source_type="media",
                observed_at=at, effective_at=at[:10], symbols=(symbol.upper(),),
                independence_group=f"wire:{n.get('source') or 'unknown'}",
                extra={"category": n.get("category"), "id": n.get("id")}))
        except corpus.CorpusRefusal:
            continue
    return obs, []


# ------------------------------------------------------------------- receipting

def _month_receipt(*, symbols: int, units: int, items: int, new: int, dup: int,
                   seen: dict[str, int], refusals: list[str], first: str | None,
                   last: str | None, pages: int, elapsed: float,
                   resumed_at: int) -> dict:
    """One month of one leg, in the shape the E3 coverage gate reads.

    `symbols_with_any` over `symbols_requested` is the coverage fraction; the
    HTTP errors sit beside it, so a month that is 'done' and a month that is
    'done and full' can never be read as the same sentence.
    """
    return {
        "symbols_requested": symbols,
        "units": units,                       # batches (alpaca) or symbols (finnhub)
        "resumed_at_unit": resumed_at,
        "items_fetched": items,
        "rows_stored_new": new,
        "rows_duplicate": dup,
        "distinct_symbols": len(seen),
        "symbols_with_any": len(seen),
        "coverage_fraction": round(len(seen) / symbols, 4) if symbols else 0.0,
        "first_observed_at": first,
        "last_observed_at": last,
        "pages_read": pages,
        "http_errors": pull_journal.tally({}, refusals),
        "n_refusals": len(refusals),
        "refusal_sample": refusals[:5],
        "elapsed_s": round(elapsed, 1),
        "seen": seen,
    }


def _bounds(obs) -> tuple[str | None, str | None]:
    ts = sorted(o.observed_at for o in obs if o.observed_at)
    return (ts[0], ts[-1]) if ts else (None, None)


# -------------------------------------------------------------------- the legs

def run_alpaca_leg(jr: pull_journal.PullJournal, syms: list[str], months: list[tuple[str, str]],
                   *, role: str, max_pages: int) -> None:
    # `/v1beta1/news` is the MARKET DATA host. It reads; it cannot place an
    # order, and the row it returns is identical whichever account asks. So a
    # role is needed here only to pick a key pair. It is named on the receipt
    # anyway, because "which credentials fetched this" is provenance.
    client = AlpacaPaper(role=role)
    jr.log(f"alpaca leg: {len(syms)} names, {len(months)} months, "
           f"{(len(syms) + ALPACA_BATCH - 1) // ALPACA_BATCH} batches/month, role={role!r} "
           "(data endpoint, places nothing)")
    for mi, (m0, m1) in enumerate(months, 1):
        key = m0[:7]
        if jr.is_done("alpaca", key):
            continue
        # The LAST month of a window is a PARTIAL month: `iter_months` yields
        # whole calendar months, so without this clamp a pull asked to stop at
        # 2026-09-01 fetches through 2026-10-01 and its receipt describes a
        # window nobody asked for.
        m_end = min(m1, jr.cursor["meta"]["end"])
        t0 = time.time()
        start_unit = jr.resume_index("alpaca", key)
        if start_unit:
            jr.log(f"alpaca {key}: RESUMING at batch {start_unit}")
        seen: dict[str, int] = {}
        items = new = dup = pages = 0
        refusals: list[str] = []
        first = last = None
        batches = [syms[i:i + ALPACA_BATCH] for i in range(0, len(syms), ALPACA_BATCH)]
        for bi in range(start_unit, len(batches)):
            obs, refs, pg = alpaca_batch(client, batches[bi], m0, m_end, max_pages=max_pages)
            pages += pg
            refusals += refs
            items += len(obs)
            for o in obs:
                for s_ in o.symbols:
                    seen[s_] = seen.get(s_, 0) + 1
            lo, hi = _bounds(obs)
            first = lo if first is None or (lo and lo < first) else first
            last = hi if last is None or (hi and hi > last) else last
            n, d = corpus.append_many(obs)
            new += n
            dup += d
            jr.checkpoint("alpaca", key, bi + 1)
        r = _month_receipt(symbols=len(syms), units=len(batches), items=items, new=new,
                           dup=dup, seen=seen, refusals=refusals, first=first, last=last,
                           pages=pages, elapsed=time.time() - t0, resumed_at=start_unit)
        r["window"] = [m0, m_end]
        jr.complete_month("alpaca", key, r)
        jr.log(f"alpaca {key} [{mi}/{len(months)}]: {items:>6} items (+{new} new, {dup} known) "
               f"{len(seen)}/{len(syms)} names  errors={r['http_errors'] or '{}'}  "
               f"{r['elapsed_s']}s")


def run_finnhub_leg(jr: pull_journal.PullJournal, syms: list[str],
                    months: list[tuple[str, str]]) -> None:
    """MONTH-MAJOR, not symbol-major.

    The old loop was `for symbol: for month:`, so a kill halfway through lost
    every month of every symbol not yet reached AND produced no per-month
    receipt for anybody. Month-major means the cursor unit is (month, symbol
    index) and the receipt for a finished month is complete for every name.
    """
    jr.log(f"finnhub leg: {len(syms)} names x {len(months)} months, "
           f"~{FINNHUB_PAUSE_S}s/call => ~{len(syms) * len(months) * FINNHUB_PAUSE_S / 3600:.1f}h")
    for mi, (m0, m1) in enumerate(months, 1):
        key = m0[:7]
        if jr.is_done("finnhub", key):
            continue
        m_end = min(m1, jr.cursor["meta"]["end"])      # see the alpaca leg
        t0 = time.time()
        start_unit = jr.resume_index("finnhub", key)
        if start_unit:
            jr.log(f"finnhub {key}: RESUMING at symbol {start_unit} ({syms[start_unit]})")
        seen: dict[str, int] = {}
        items = new = dup = 0
        refusals: list[str] = []
        first = last = None
        for si in range(start_unit, len(syms)):
            sym = syms[si]
            obs, refs = finnhub_history(sym, m0, m_end)
            refusals += refs
            items += len(obs)
            for o in obs:
                seen[sym] = seen.get(sym, 0) + 1
            lo, hi = _bounds(obs)
            first = lo if first is None or (lo and lo < first) else first
            last = hi if last is None or (hi and hi > last) else last
            n, d = corpus.append_many(obs)
            new += n
            dup += d
            if si % 10 == 9 or si == len(syms) - 1:
                jr.checkpoint("finnhub", key, si + 1)
            time.sleep(FINNHUB_PAUSE_S)
        r = _month_receipt(symbols=len(syms), units=len(syms), items=items, new=new,
                           dup=dup, seen=seen, refusals=refusals, first=first, last=last,
                           pages=0, elapsed=time.time() - t0, resumed_at=start_unit)
        r["window"] = [m0, m_end]
        jr.complete_month("finnhub", key, r)
        jr.log(f"finnhub {key} [{mi}/{len(months)}]: {items:>6} items (+{new} new, {dup} known) "
               f"{len(seen)}/{len(syms)} names  errors={r['http_errors'] or '{}'}  "
               f"{r['elapsed_s']}s")


# ------------------------------------------------------------------------ main

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=None, help="ISO date, inclusive (REQUIRED for a pull)")
    ap.add_argument("--end", default=None, help="ISO date, exclusive (REQUIRED for a pull)")
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--murat", action="store_true", help="Murat's twenty names")
    ap.add_argument("--universe", choices=("default", "murat", "fleet", "tradable"),
                    default="default",
                    help="fleet = ~160 names; tradable = the CRSP-common proxy "
                         "(scripts.tradable_universe), thousands of names")
    ap.add_argument("--no-alpaca", action="store_true")
    ap.add_argument("--no-finnhub", action="store_true")
    ap.add_argument("--max-pages", type=int, default=40)
    ap.add_argument("--role", default=None,
                    help="account whose keys read the NEWS endpoint (default: env, else hack1)")
    ap.add_argument("--run-id", default=None, help="override the derived cursor id")
    ap.add_argument("--redo-degraded", type=int, nargs="?", const=1, default=None,
                    metavar="MIN_REFUSALS",
                    help="before resuming, un-mark every DONE month whose receipt shows "
                         "at least MIN_REFUSALS refusals (default 1), so a network "
                         "outage that was survived rather than fatal gets re-pulled. "
                         "The old receipt is kept as .superseded-N.json")
    ap.add_argument("--list-degraded", action="store_true",
                    help="print the DONE months whose receipts carry refusals, and exit")
    ap.add_argument("--stats", action="store_true", help="print corpus stats and exit")
    ap.add_argument("--corpus-coverage", action="store_true",
                    help="coverage-by-year of the WHOLE corpus against the tradable "
                         "universe, written to a receipt; this is what the E3 gate reads")
    ap.add_argument("--resume-status", action="store_true",
                    help="print this job's cursor and per-month receipts, and exit")
    ap.add_argument("--no-rebuild-index", action="store_true",
                    help="skip the end-of-run uid index rebuild (only safe when no "
                         "other collector ran against this corpus)")
    ap.add_argument("--months", type=int, default=None,
                    help=argparse.SUPPRESS)     # retired; see the refusal below
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    config.load_env()

    if args.stats:
        print(json.dumps(corpus.stats(), indent=1))
        return 0

    if args.corpus_coverage:
        try:
            uni = tradable_universe.load()
        except tradable_universe.UniverseRefusal as exc:
            print(f"(no tradable universe: {exc})")
            uni = []
        rep = corpus_coverage_by_year(uni)
        out = corpus.CORPUS / f"corpus_coverage_by_year_{date.today().isoformat()}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rep, indent=1), encoding="utf-8")
        print(f"{'year':<6}{'rows':>10}{'mo':>4}{'symbols':>9}{'in-univ':>9}{'univ%':>8}")
        for y, r in rep["years"].items():
            uf = "n/a" if r["universe_fraction"] is None else f"{r['universe_fraction'] * 100:.1f}%"
            print(f"{y:<6}{r['rows']:>10}{r['months_with_rows']:>4}"
                  f"{r['distinct_symbols']:>9}{r['universe_symbols_with_any']:>9}{uf:>8}")
        print(f"universe = {rep['universe_size']} names; receipt: {out}")
        return 0

    if args.months is not None:
        print("REFUSED: --months counted back from TODAY, so the same command named a "
              "different window every day it ran and no two runs were comparable.\n"
              "Pass explicit dates instead, e.g. --start 2025-01-01 --end 2026-09-08.")
        return 2

    if not args.start or not args.end:
        print("REFUSED: --start and --end are required (ISO dates). A relative window "
              "cannot be resumed, cached or compared.")
        return 2
    try:
        s_d, e_d = date.fromisoformat(args.start), date.fromisoformat(args.end)
    except ValueError as exc:
        print(f"REFUSED: {exc}")
        return 2
    if e_d <= s_d:
        print(f"REFUSED: --end {args.end} is not after --start {args.start}")
        return 2

    try:
        syms = _universe(args)
    except tradable_universe.UniverseRefusal as exc:
        print(f"REFUSED: {exc}")
        return 2

    legs = [n for n, off in (("alpaca", args.no_alpaca), ("finnhub", args.no_finnhub)) if not off]
    uni_tag = args.universe if not args.symbols else f"{args.universe}+syms"
    rid = args.run_id or pull_journal.run_id_for(
        "news", start=args.start, end=args.end, universe=uni_tag,
        extra=",".join(syms) if args.symbols else "")
    # `iter_months` yields whole calendar months and stops on `end`'s OWN month,
    # so an --end of 2026-09-01 would add a 2026-09 month whose clamped window is
    # zero-length. Fetching it would spend 610 calls and then write a receipt
    # reading "0 items, 0 symbols" for a month nobody asked about -- a coverage
    # hole invented by an off-by-one.
    months = [(m0, m1) for m0, m1 in corpus.iter_months(args.start, args.end) if m0 < args.end]
    month_keys = [m0[:7] for m0, _ in months]

    if args.list_degraded:
        jr = pull_journal.PullJournal(rid, meta={"start": args.start, "end": args.end})
        any_ = False
        for lg in ("alpaca", "finnhub"):
            for m, n in jr.degraded_months(lg):
                print(f"{lg} {m}: {n} refusals -- DONE but NOT full")
                any_ = True
        if not any_:
            print("no degraded months: every completed month's receipt is refusal-free")
        return 0

    if args.resume_status:
        jr = pull_journal.PullJournal(rid, meta={"start": args.start, "end": args.end})
        print(json.dumps({"run_id": rid, "dir": str(jr.dir),
                          "months_total": len(months),
                          "done": {lg: len(jr.done_months(lg)) for lg in ("alpaca", "finnhub")},
                          "partial": jr.cursor.get("partial"),
                          "totals": jr.cursor.get("totals"),
                          "status": jr.cursor.get("status", "INTERRUPTED_OR_RUNNING")}, indent=1))
        return 0

    meta = {"start": args.start, "end": args.end, "universe": uni_tag,
            "n_symbols": len(syms), "legs": legs, "months": len(months),
            "max_pages": args.max_pages}
    try:
        jr = pull_journal.PullJournal(rid, meta=meta).open(list(sys.argv))
    except pull_journal.JournalRefusal as exc:
        print(f"REFUSED: {exc}")
        return 3

    if args.redo_degraded is not None:
        for lg in legs:
            for m, n in jr.degraded_months(lg, args.redo_degraded):
                jr.reopen_month(lg, m)
                jr.log(f"REDO {lg} {m}: receipt carried {n} refusals; re-opened "
                       "(old receipt kept as .superseded-N.json)")

    jr.log(f"backfill {len(syms)} names, {args.start} -> {args.end} "
           f"({len(months)} months), legs={legs}")
    jr.log(f"log={jr.log_path}")
    jr.log(f"cursor={jr.cursor_path}  pid={jr.pid_path}  receipts={jr.months_dir}")

    news_role = (args.role or os.getenv("AAT_ACCOUNT_ROLE", "").strip() or "hack1").lower()
    try:
        if "alpaca" in legs:
            run_alpaca_leg(jr, syms, months, role=news_role, max_pages=args.max_pages)
        if "finnhub" in legs:
            run_finnhub_leg(jr, syms, months)
    except KeyboardInterrupt:
        jr.log("INTERRUPTED by KeyboardInterrupt -- cursor holds the last completed unit")
        jr.close("interrupted")
        return 130
    except Exception as exc:                                            # noqa: BLE001
        # A crash must leave a readable trail. The old run left none, which is
        # why nobody could say what killed it at 03:18.
        jr.log(f"CRASHED: {type(exc).__name__}: {exc}")
        jr.close("crashed")
        raise

    if not args.no_rebuild_index:
        n_uid = rebuild_index_streaming()
        jr.log(f"uid index rebuilt from the shards: {n_uid} uids")
    else:
        corpus.flush_index()
    st = corpus.stats()
    cov = corpus.symbols_covered()
    missing = [s for s in syms if cov.get(s, 0) == 0]
    receipts = jr.month_receipts()
    seen_all: dict[str, int] = {}
    for r in receipts:
        for k, v in (r.get("seen") or {}).items():
            seen_all[k] = seen_all.get(k, 0) + int(v)
    thin = [s for s in syms if seen_all.get(s, 0) < THIN_ITEMS]

    summary = {
        "months_requested": len(months),
        "months_done": {lg: len(jr.done_months(lg)) for lg in legs},
        "n_symbols": len(syms),
        "symbols_with_any_this_run": len(seen_all),
        "thin": len(thin),
        "no_coverage_in_corpus": len(missing),
        "corpus_observations": st["n_observations"],
        "corpus_symbols": st["n_symbols"],
        "corpus_span": st["effective_span"],
        "coverage_by_year": coverage_by_year(receipts, month_keys),
    }
    jr.log("SUMMARY " + json.dumps(summary["months_done"]) +
           f"  corpus {st['n_observations']} obs / {st['n_symbols']} symbols, span {st['effective_span']}")
    if missing:
        # THE COVERAGE GAP, NAMED. A name with zero rows after a backfill is a
        # name the engine is structurally blind to, and saying so is the finding.
        jr.log(f"NO COVERAGE IN CORPUS ({len(missing)}): " + " ".join(missing[:40]) +
               (" ..." if len(missing) > 40 else ""))
    jr.log(f"THIN (< {THIN_ITEMS} items this run): {len(thin)}/{len(syms)}")
    all_done = all(len(jr.done_months(lg)) == len(months) for lg in legs)
    jr.close("complete" if all_done else "partial", summary)
    print(json.dumps(summary, indent=1))
    return 0


def corpus_coverage_by_year(universe: list[str] | None = None) -> dict:
    """What the CORPUS holds, per year, against a named universe.

    The E3 gate is ">= 90% coverage per year", and that phrase has two readings
    that differ by an order of magnitude:

      `month_fraction`   -- months of the year with any row at all. This is a
                            PIPELINE health number: it catches a pull that died
                            mid-year, which is the failure of 2026-09-07.
      `universe_fraction`-- names in the universe with at least one row that
                            year. This is a DATA number, and it is the one a
                            book actually needs, because a name with no news
                            cannot be ranked by news.

    Both are reported. A gate quoted without saying which one it means is a
    gate that will be met by whichever reading happens to pass.
    """
    uni = {s.upper() for s in (universe or [])}
    per_year: dict[str, dict] = {}
    if not corpus.OBS_DIR.exists():
        return {"years": {}, "universe_size": len(uni)}
    for shard in sorted(corpus.OBS_DIR.glob("*.jsonl")):
        month = shard.stem
        year = month[:4]
        y = per_year.setdefault(year, {"rows": 0, "months": set(), "symbols": set()})
        n = 0
        with shard.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("kind") != "news":
                    continue
                n += 1
                for s_ in r.get("symbols") or []:
                    y["symbols"].add(str(s_).upper())
        if n:
            y["rows"] += n
            y["months"].add(month)
    out = {}
    for year in sorted(per_year):
        y = per_year[year]
        in_uni = (y["symbols"] & uni) if uni else set()
        out[year] = {
            "rows": y["rows"],
            "months_with_rows": len(y["months"]),
            "month_fraction": round(len(y["months"]) / 12, 4),
            "distinct_symbols": len(y["symbols"]),
            "universe_symbols_with_any": len(in_uni),
            "universe_fraction": round(len(in_uni) / len(uni), 4) if uni else None,
        }
    return {"years": out, "universe_size": len(uni), "at": pull_journal.utcnow()}


def rebuild_index_streaming() -> int:
    """Re-derive `uid_index.json` from the shards WITHOUT loading them into RAM.

    `corpus.rebuild_index()` calls `corpus.read()`, which materialises every row
    -- 437k dicts over 264 MB of JSONL on 2026-09-07, on a box with 3.6 GB free
    while other agents' jobs are running. Streaming the uid out of each line
    costs a few seconds and a few MB.

    WHY IT IS RUN AT ALL: `corpus._INDEX` is per-process and `flush_index()`
    writes the whole set, so two collectors running at once end last-writer-wins
    and the loser's uids vanish from the index while its ROWS stay on disk --
    the next run then re-appends them. The shards are the truth; this rederives
    the index from them, so whichever collector finishes LAST leaves a correct
    index behind. Documented in `alpha/sources/corpus.rebuild_index`.
    """
    uids: set[str] = set()
    for shard in sorted(corpus.OBS_DIR.glob("*.jsonl")) if corpus.OBS_DIR.exists() else []:
        with shard.open(encoding="utf-8") as fh:
            for line in fh:
                i = line.find('"uid": "')
                if i >= 0:
                    j = line.find('"', i + 8)
                    if j > 0:
                        uids.add(line[i + 8:j])
                        continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("uid"):
                    uids.add(r["uid"])
    corpus.CORPUS.mkdir(parents=True, exist_ok=True)
    (corpus.CORPUS / "uid_index.json").write_text(json.dumps(sorted(uids)), encoding="utf-8")
    corpus._INDEX = uids                     # this process keeps the repaired set
    return len(uids)


def coverage_by_year(receipts: list[dict], month_keys: list[str]) -> dict[str, dict]:
    """Per YEAR: months with a receipt, items, and distinct symbols.

    This is what the E3 gate (>= 90% coverage per year) reads. It is computed
    from the per-month receipts on disk, so it survives the death of the
    process that produced them -- which is the entire point.
    """
    want: dict[str, int] = {}
    for m in month_keys:
        want[m[:4]] = want.get(m[:4], 0) + 1
    got: dict[str, dict] = {}
    for r in receipts:
        y = str(r.get("month", ""))[:4]
        g = got.setdefault(y, {"months_with_receipt": set(), "items": 0, "symbols": set()})
        g["months_with_receipt"].add(r.get("month"))
        g["items"] += int(r.get("items_fetched", 0))
        g["symbols"].update((r.get("seen") or {}).keys())
    out = {}
    for y, n_months in sorted(want.items()):
        g = got.get(y, {"months_with_receipt": set(), "items": 0, "symbols": set()})
        out[y] = {"months_requested": n_months,
                  "months_with_receipt": len(g["months_with_receipt"]),
                  "month_fraction": round(len(g["months_with_receipt"]) / n_months, 4),
                  "items": g["items"], "distinct_symbols": len(g["symbols"])}
    return out


if __name__ == "__main__":
    raise SystemExit(main())
