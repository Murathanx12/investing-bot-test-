"""SCHEDULE 13D / 13G -- who just took a material stake, recorded point-in-time.

WHY THIS FILE EXISTS
====================
On 2026-08-20 Mark Fischbach filed a Schedule 13G for ~8.5% of GoPro. The stock
exploded around the 2026-09-01 announcement. AEGIS never had an opinion on it,
and could not have had one, for two compounding reasons:

  1. `alpha/universe.py` screens at MIN_PRICE $2 and a $3m/day EXECUTE floor, so
     GPRO was not among the 3,059 names the tracker refreshes; and
  2. `alpha/sources/sec.py` watches exactly one thing on EDGAR -- an 8-K
     carrying Item 2.02 -- so no beneficial-ownership filing has ever been read.

MISS TYPE: **NOT OBSERVED**. Not mispriced, not mis-ranked, not refused. We did
not decide against GPRO; we arranged never to have an opinion, which is the
WBUY failure written out again one screen over (`alpha/universe.py`, the
OBSERVATION IS NOT EXECUTION block).

So this module does two things and stops:

  * it RECORDS every 13D/13G/13D-A/13G-A from EDGAR's daily index, point-in-time,
    append-only, one JSON line per filing; and
  * it maintains an ATTENTION WATCHLIST -- the subject tickers of the last
    `WATCHLIST_DAYS` days of those filings -- which `scripts/tracker.py` unions
    into the refresh so a name with a fresh material-holder event is OBSERVED
    whatever its liquidity.

It places nothing, scores nothing and ranks nothing. A 13G is an observation.

THE DAILY INDEX, AND FOUR THINGS ITS FORMAT DOES NOT ADVERTISE
==============================================================
`https://www.sec.gov/Archives/edgar/daily-index/{YYYY}/QTR{q}/form.{YYYYMMDD}.idx`
is a fixed-width text file, and all four of these were MEASURED against the
2026-08-20 file (4,183 rows) rather than assumed:

  1. **The form type is spelled `SCHEDULE 13G`, not `SC 13G`.** A watcher
     filtering on the EDGAR full-text-search spelling matches ZERO rows and
     reports a quiet, entirely plausible "no ownership filings today" every
     single day. `_FORM_RE` accepts both spellings; `is_ownership_form` is the
     only place the decision is made.
  2. **Every filing appears TWICE** -- once under the FILER's CIK and once under
     the SUBJECT's. All 52 ownership accessions on 2026-08-20 appeared exactly
     twice. So the row count is not the filing count, and `parse_form_index`
     groups by accession rather than returning one record per line.
  3. **The index row's company is as often the filer as the subject**, and
     nothing on the row says which. `Fischbach Mark Edward` is the company name
     on the row that carries the GPRO 13G. The subject is resolved from the
     filing's own SGML header (`SUBJECT COMPANY:` block), one extra request per
     filing, and cross-checked against the CIKs the index gave for that
     accession.
  4. **`{acc}-index.json` is a 404.** The folder `index.json` exists but carries
     no subject. `Range:` on the full `.txt` is ignored (HTTP 200, whole body),
     so the header read is capped by reading only the first `HEADER_READ_BYTES`
     off the stream and closing it.

DERIVE OR REFUSE -- AND A ROW IS NEVER DROPPED
==============================================
A filing whose subject cannot be resolved to a ticker is still RECORDED, with
`subject_ticker: null` and `unresolved_reason` saying which step failed. That is
deliberate: most 13D/13G subjects that fail to resolve are perfectly real
companies with no listed common ticker, and a watcher that silently drops what
it cannot name is a watcher whose coverage nobody can ever audit. The counts on
every run report resolved / unresolved separately for the same reason -- a
filing count alone cannot tell "quiet day" from "the header fetches all 403'd".

WHAT A DAY COSTS, MEASURED 2026-09-02
=====================================
One index request plus one header request per filing, paced at ~4/s. The daily
filing count is NOT flat, and the spread decides whether this is a 45-second job
or a 25-minute one:

    2026-08-13   688 filings        2026-08-18    47
    2026-08-14 1,615 filings        2026-08-19    43
    2026-08-17    64 filings        2026-08-20    52   <- the GPRO 13G

13G amendments are due 45 days after a quarter end, so mid-February, mid-May,
mid-August and mid-November carry 20-30x an ordinary day. An ordinary night
costs ~45s; a deadline night costs ~25 minutes. Both are fine unattended and
neither is a reason to weaken the subject resolution: a wrong ticker on the
watchlist is worse than a slow job, and the pairing in point 2 above is NOT
enough to name the subject (in `BARCLAYS PLC -> ProCap Acquisition Corp` both
CIKs carry listed tickers, so "the one with a ticker" picks the filer half the
time).

THE USER AGENT IS NOT OPTIONAL
==============================
SEC fair access requires a declared UA with a contact address; without one every
request is a 403, which reads as absence. Rate limit is theirs (10 req/s); this
module paces at `MIN_REQUEST_INTERVAL_S` (~4/s) because nothing here is urgent.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from alpha.sources.http import SourceRefusal

ROOT = Path(__file__).resolve().parent.parent.parent

#: SEC fair access asks for an identifying UA with a contact address.
UA = "AegisResearch mrthnabdullaev@gmail.com"
HEADERS = {"User-Agent": UA}

DAILY_INDEX = "https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{qtr}/form.{ymd}.idx"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FILING_TXT = "https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/{acc}.txt"

#: SEC allows 10 req/s. Nothing here is urgent, so we take about four.
MIN_REQUEST_INTERVAL_S = 0.25
#: The SGML header sits at the top of the full submission text. 24 KB has held
#: every SUBJECT COMPANY / FILED BY block seen so far with room to spare; if a
#: header is truncated the parse REFUSES rather than guessing at a subject.
HEADER_READ_BYTES = 24_000
#: company_tickers.json changes slowly. Weekly is generous.
TICKER_CACHE_MAX_AGE_S = 7 * 24 * 3600

SCHEMA = "ownership-filing-1"
WATCHLIST_SCHEMA = "ownership-attention-watchlist-1"
#: A 13D/13G is a claim about a position that is still on. 45 days is long
#: enough that a Wednesday filing is still watched a month later and short
#: enough that the list stays a watchlist rather than an archive.
WATCHLIST_DAYS = 45
#: The tracker pays a Finnhub call and a yfinance call per name it refreshes, so
#: this cap is a COST bound, not a belief about how many events matter.
#:
#: MEASURED 2026-09-02, AND IT BINDS HARD: two recorded days (688 + 52 filings)
#: already produced 612 qualifying symbols, and an ordinary day contributes ~40
#: distinct subjects. Over a full 45-day window that is on the order of 1,800
#: symbols, so a 200 cap ordered by recency turns the stated 45-day window into
#: an EFFECTIVE ~5-day one. That is a real narrowing and it is reported on every
#: build (`n_symbols_before_cap`) rather than left for someone to discover.
#: `--cap` widens it for a run; the better fix, when someone wants one, is to
#: rank inside the cap (a 13D is an activist stake, a 13G/A is a passive
#: amendment, and recency treats them identically) -- not to raise this number.
WATCHLIST_MAX = 200

#: `SC 13G`, `SCHEDULE 13G`, `SC 13D/A`, `SCHEDULE 13G/A`, ... The daily index
#: uses the second spelling; EDGAR full-text search and `submissions` JSON use
#: the first. Accepting only one of them is a silent zero.
_FORM_RE = re.compile(r"^(?:SC|SCHEDULE)\s*13\s*([DG])\s*(/A)?$", re.I)

#: One fixed-width index row. Parsed from the RIGHT-hand columns (a digit CIK, an
#: 8-digit date, a space-free path) so a company name containing runs of spaces
#: cannot shift the split -- the non-greedy company group backtracks until the
#: tail matches. Measured: 4,183 of 4,183 rows on 2026-08-20 parse.
_ROW_RE = re.compile(
    r"^(?P<form>\S.*?)\s{2,}(?P<company>\S.*?)\s{2,}"
    r"(?P<cik>\d+)\s+(?P<filed>\d{8})\s+(?P<file>\S+)\s*$")

_last_request_at = 0.0


# ------------------------------------------------------------------ plumbing

def _store() -> Path:
    """`state/research/ownership`, resolved at CALL time.

    Not at import: `AAT_LEDGER_DIR` is set by the Railway service and by tests,
    and a module-level constant would freeze whichever value existed first.
    """
    base = Path(os.getenv("AAT_LEDGER_DIR") or (ROOT / "state"))
    return base / "research" / "ownership"


def day_path(day: str) -> Path:
    return _store() / f"{day}.jsonl"


def watchlist_path() -> Path:
    return _store() / "attention_watchlist.json"


def _throttle() -> None:
    global _last_request_at
    wait = MIN_REQUEST_INTERVAL_S - (time.time() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.time()


def _get_text(url: str, *, max_bytes: int | None = None, timeout: float = 45.0) -> str:
    """GET -> text, throttled, with the SEC user agent. Raises SourceRefusal.

    `max_bytes` reads only that many bytes off the stream and closes it, because
    the SEC ignores a `Range:` header on Archives and answers 200 with the whole
    body -- a 40 MB submission would otherwise be downloaded to read 2 KB of
    header.
    """
    _throttle()
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_bytes) if max_bytes else resp.read()
    except urllib.error.HTTPError as exc:
        raise SourceRefusal(f"GET {url} -> HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceRefusal(f"GET {url} -> {exc}") from exc
    return raw.decode("utf-8", "ignore")


# --------------------------------------------------------------- form types

def is_ownership_form(form: str) -> bool:
    """True for SC/SCHEDULE 13D, 13G and their amendments. The ONLY filter."""
    return bool(_FORM_RE.match((form or "").strip()))


def normalise_form(form: str) -> dict[str, Any] | None:
    """`SCHEDULE 13G/A` -> {family: '13G', amendment: True, normalised: 'SC 13G/A'}."""
    m = _FORM_RE.match((form or "").strip())
    if not m:
        return None
    family = f"13{m.group(1).upper()}"
    amendment = bool(m.group(2))
    return {"form_family": family, "amendment": amendment,
            "form_normalised": f"SC {family}" + ("/A" if amendment else "")}


# ------------------------------------------------------------- daily index

def quarter_of(day: str) -> int:
    d = date.fromisoformat(day)
    return (d.month - 1) // 3 + 1


def daily_index_url(day: str) -> str:
    d = date.fromisoformat(day)
    return DAILY_INDEX.format(year=d.year, qtr=quarter_of(day), ymd=d.strftime("%Y%m%d"))


def parse_form_index(text: str, *, day: str | None = None) -> list[dict[str, Any]]:
    """OFFLINE. The ownership filings in one `form.YYYYMMDD.idx`, one per ACCESSION.

    Grouped by accession, because every filing appears once per party -- see the
    docstring's point 2. The row's company names are kept as `index_companies`
    with no claim about which is the subject; that claim is made only by
    `parse_subject_header`.

    Raises SourceRefusal if the file has no parseable rows at all: an .idx that
    yields nothing is a format change or a truncated download, and returning []
    for it would read as "a day with no filings", which is the failure this
    whole module exists to stop.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    parsed, unparsed = 0, 0
    by_acc: dict[str, dict[str, Any]] = {}
    for ln in lines:
        if ln.startswith(("Description:", "Last Data Received:", "Comments:",
                          "Anonymous FTP:", "Form Type", "---", "      Date Filed",
                          "CIK", "Company Name")):
            continue
        m = _ROW_RE.match(ln)
        if not m:
            unparsed += 1
            continue
        parsed += 1
        form = m.group("form").strip()
        if not is_ownership_form(form):
            continue
        path = m.group("file")
        accession = path.rsplit("/", 1)[-1]
        if accession.endswith(".txt"):
            accession = accession[:-4]
        filed = m.group("filed")
        rec = by_acc.setdefault(accession, {
            "accession": accession,
            "form": form,
            "filed_date": f"{filed[:4]}-{filed[4:6]}-{filed[6:8]}",
            "file_name": path,
            "index_companies": [],
            "index_ciks": [],
        })
        rec["index_companies"].append(m.group("company").strip())
        rec["index_ciks"].append(int(m.group("cik")))
    if parsed == 0:
        raise SourceRefusal(
            f"form.idx has {len(lines)} lines and 0 parseable rows "
            f"({unparsed} unparsed) -- the fixed-width format changed, or the "
            f"download was truncated. REFUSING rather than reporting an empty day.")
    for rec in by_acc.values():
        rec.update(normalise_form(rec["form"]) or {})
        if day:
            rec["index_day"] = day
        rec["index_rows"] = len(rec["index_ciks"])
    return sorted(by_acc.values(), key=lambda r: r["accession"])


def fetch_daily_index(day: str) -> str:
    """The raw .idx text for one day. A weekend/holiday is a 403 or 404 there."""
    return _get_text(daily_index_url(day))


# ------------------------------------------------------- the subject company

_NAME_RE = re.compile(r"COMPANY CONFORMED NAME:\s*(.+)")
_CIK_RE = re.compile(r"CENTRAL INDEX KEY:\s*(\d+)")


def parse_subject_header(text: str) -> dict[str, Any]:
    """OFFLINE. `{subject_cik, subject_name, filer_names}` from an SGML header.

    The header names the parties explicitly:

        SUBJECT COMPANY:
            COMPANY DATA:
                COMPANY CONFORMED NAME:   GoPro, Inc.
                CENTRAL INDEX KEY:        0001500435
        FILED BY:
            COMPANY DATA:
                COMPANY CONFORMED NAME:   Fischbach Mark Edward

    A header with no SUBJECT COMPANY block returns `subject_cik: None` and a
    reason. It does NOT fall back to the first company it can find: the first
    company in a 13G header is frequently the filer, and a filer silently
    recorded as a subject would put the wrong ticker on the watchlist.
    """
    if "SUBJECT COMPANY" not in text:
        reason = ("no SUBJECT COMPANY block in the filing header"
                  + ("" if "</SEC-HEADER>" in text else "; header may be truncated"))
        return {"subject_cik": None, "subject_name": None, "filer_names": [],
                "reason": reason}
    head, _, tail = text.partition("SUBJECT COMPANY")
    # The subject block ends where the next top-level party block begins.
    subject_block = re.split(r"\n(?:FILED BY|FILER|REPORTING-OWNER|ISSUER)\s*:", tail)[0]
    name = _NAME_RE.search(subject_block)
    cik = _CIK_RE.search(subject_block)
    filers = [m.strip() for m in _NAME_RE.findall(
        "".join(re.split(r"\n(?=(?:FILED BY|FILER)\s*:)", tail)[1:]))]
    if not cik:
        return {"subject_cik": None, "subject_name": (name.group(1).strip() if name else None),
                "filer_names": filers,
                "reason": "SUBJECT COMPANY block carries no CENTRAL INDEX KEY"}
    return {"subject_cik": int(cik.group(1)),
            "subject_name": name.group(1).strip() if name else None,
            "filer_names": filers, "reason": None}


def fetch_filing_header(cik: int | str, accession: str) -> str:
    """The first `HEADER_READ_BYTES` of a filing's full submission text."""
    return _get_text(
        FILING_TXT.format(cik=int(cik), nodash=accession.replace("-", ""), acc=accession),
        max_bytes=HEADER_READ_BYTES)


# ------------------------------------------------------------ CIK -> ticker

def _ticker_cache_path() -> Path:
    base = Path(os.getenv("AAT_LEDGER_DIR") or (ROOT / "state"))
    return base / "sec_cache" / "company_tickers.json"


def cik_ticker_map(*, max_age_s: float = TICKER_CACHE_MAX_AGE_S,
                   allow_fetch: bool = True) -> dict[int, str]:
    """`{cik: TICKER}` from SEC company_tickers.json, cached to disk weekly.

    A stale cache is USED and said so rather than refused: a ticker map from
    last Tuesday resolves GPRO exactly as well as today's, and refusing to
    resolve anything because a refresh failed would turn a network hiccup into
    a day of unresolved filings.
    """
    p = _ticker_cache_path()
    fresh = p.exists() and (time.time() - p.stat().st_mtime) < max_age_s
    if not fresh and allow_fetch:
        try:
            raw = _get_text(TICKERS_URL)
            json.loads(raw)  # parse before overwriting a usable cache
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(raw, encoding="utf-8")
        except (SourceRefusal, json.JSONDecodeError) as exc:
            if not p.exists():
                raise SourceRefusal(f"company_tickers.json unavailable and no cache: {exc}") from exc
            print(f"  ownership: company_tickers.json refresh failed ({exc}); "
                  f"using the cache from {datetime.fromtimestamp(p.stat().st_mtime):%Y-%m-%d}")
    if not p.exists():
        raise SourceRefusal(f"no CIK->ticker map at {p} and fetching was not allowed")
    data = json.loads(p.read_text(encoding="utf-8"))
    rows = data.values() if isinstance(data, dict) else data
    out: dict[int, str] = {}
    for v in rows:
        try:
            out.setdefault(int(v["cik_str"]), str(v["ticker"]).upper())
        except (KeyError, TypeError, ValueError):
            continue
    if not out:
        raise SourceRefusal("company_tickers.json parsed to zero CIK->ticker pairs")
    return out


# ------------------------------------------------------------- the day's work

def resolve_subject(rec: dict[str, Any], *, tickers: dict[int, str]) -> dict[str, Any]:
    """Fill subject_cik / subject_name / subject_ticker on ONE index record.

    Never drops. Every failure mode leaves `subject_ticker: None` and writes
    `unresolved_reason`, so a coverage question is answerable from the file.
    """
    out = dict(rec)
    out.update({"schema": SCHEMA, "source": "sec_daily_index_form_idx",
                "url": f"https://www.sec.gov/Archives/{rec['file_name']}",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "subject_cik": None, "subject_name": None, "subject_ticker": None,
                "filer_names": [], "subject_resolution": None, "unresolved_reason": None})
    ciks = rec.get("index_ciks") or []
    try:
        header = fetch_filing_header(ciks[0] if ciks else 0, rec["accession"])
    except (SourceRefusal, IndexError) as exc:
        out["unresolved_reason"] = f"filing header unavailable: {exc}"
        return out
    parsed = parse_subject_header(header)
    out["subject_name"] = parsed["subject_name"]
    out["filer_names"] = parsed["filer_names"]
    if parsed["subject_cik"] is None:
        out["unresolved_reason"] = f"subject not named in the header: {parsed['reason']}"
        return out
    out["subject_cik"] = parsed["subject_cik"]
    out["subject_resolution"] = "sec_header_subject_company"
    # CROSS-CHECK. The index lists one row per party, so the subject CIK the
    # header names must be one of them. A mismatch means the header we read
    # belongs to a different filing than the row -- worth knowing, not worth
    # discarding the row over.
    if ciks and parsed["subject_cik"] not in ciks:
        out["subject_cik_in_index"] = False
    ticker = tickers.get(parsed["subject_cik"])
    if not ticker:
        out["unresolved_reason"] = (
            f"CIK {parsed['subject_cik']} ({parsed['subject_name']}) is not in "
            f"company_tickers.json -- no listed common ticker")
        return out
    out["subject_ticker"] = ticker
    out["subject_resolution"] = "sec_header_subject_company+company_tickers"
    return out


def iter_resolved(records: Iterable[dict[str, Any]], *,
                  tickers: dict[int, str]) -> Iterable[dict[str, Any]]:
    """A GENERATOR, deliberately: one resolved record at a time.

    2026-08-14 carried 1,615 ownership filings (the 45-day 13G amendment
    deadline), which is ~22 minutes of header requests. An eager list would hand
    the caller nothing until all 1,615 had landed, so a kill at minute 20
    destroys 20 minutes of completed work -- the exact failure `analyst_panel`
    paid for and `scripts/tracker.py`'s WRITE AS YOU GO section was written
    about. Yielding lets `append_filings` flush each line as it resolves.
    """
    for r in records:
        yield resolve_subject(r, tickers=tickers)


def ownership_filings(day: str, *, resolve: bool = True,
                      limit: int | None = None) -> list[dict[str, Any]]:
    """Every 13D/13G filed on `day`, subject-resolved. NETWORK, and EAGER.

    A convenience for probes and ad-hoc reads. The recording path uses
    `parse_form_index` + `iter_resolved` so it can write as it goes and so an
    already-recorded accession is skipped BEFORE its header is paid for.
    """
    recs = parse_form_index(fetch_daily_index(day), day=day)
    if limit:
        recs = recs[:limit]
    if not resolve:
        return recs
    return list(iter_resolved(recs, tickers=cik_ticker_map()))


# ------------------------------------------------------------ the append-only store

def recorded_accessions(day: str) -> set[str]:
    """What is already on today's file. The idempotency key is the ACCESSION."""
    p = day_path(day)
    if not p.exists():
        return set()
    out: set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.add(str(json.loads(line)["accession"]))
        except (json.JSONDecodeError, KeyError):
            continue
    return out


def append_filings(day: str, records: Iterable[dict[str, Any]]) -> tuple[int, int]:
    """Append what is new to `state/research/ownership/{day}.jsonl` -> (written, skipped).

    APPEND-ONLY. A record already on the file is never rewritten, even if this
    run resolved a subject the last run could not: the file is the point-in-time
    record of what we knew when, and a re-resolution belongs on a later line
    under a later `observed_at`, never on top of the earlier one.
    """
    seen = recorded_accessions(day)
    p = day_path(day)
    p.parent.mkdir(parents=True, exist_ok=True)
    written, skipped = 0, 0
    with p.open("a", encoding="utf-8") as fh:
        for r in records:
            if str(r.get("accession")) in seen:
                skipped += 1
                continue
            fh.write(json.dumps(r, default=str) + "\n")
            fh.flush()
            seen.add(str(r.get("accession")))
            written += 1
    return written, skipped


def read_recorded(*, since: str | None = None) -> list[dict[str, Any]]:
    """Every recorded filing on or after `since` (by the file's day)."""
    store = _store()
    if not store.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(store.glob("*.jsonl")):
        if since and p.stem < since:
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


# ------------------------------------------------------- the attention watchlist

def build_watchlist(records: Iterable[dict[str, Any]], *, as_of: str,
                    days: int = WATCHLIST_DAYS, cap: int = WATCHLIST_MAX) -> dict[str, Any]:
    """PURE. The subject tickers of the last `days` of filings, newest first, capped.

    `first_seen` is the earliest filing date we hold for the symbol INSIDE the
    window, not the earliest ever -- the window is the claim, so the field must
    be read the same way.
    """
    floor = (date.fromisoformat(as_of) - timedelta(days=days)).isoformat()
    entries: dict[str, dict[str, Any]] = {}
    considered, out_of_window, unresolved = 0, 0, 0
    for r in records:
        considered += 1
        sym = r.get("subject_ticker")
        filed = str(r.get("filed_date") or "")
        if not sym:
            unresolved += 1
            continue
        if not filed or filed < floor or filed > as_of:
            out_of_window += 1
            continue
        e = entries.setdefault(str(sym).upper(), {
            "symbol": str(sym).upper(), "first_seen": filed, "last_seen": filed,
            "last_form": r.get("form_normalised") or r.get("form"),
            "filer_name": (r.get("filer_names") or [None])[0] or (
                r.get("index_companies") or [None])[0],
            "accessions": [],
        })
        e["first_seen"] = min(e["first_seen"], filed)
        if filed >= e["last_seen"]:
            e["last_seen"] = filed
            e["last_form"] = r.get("form_normalised") or r.get("form")
            e["filer_name"] = ((r.get("filer_names") or [None])[0]
                               or (r.get("index_companies") or [None])[0]
                               or e["filer_name"])
        acc = str(r.get("accession") or "")
        if acc and acc not in e["accessions"]:
            e["accessions"].append(acc)
    ordered = sorted(entries.values(), key=lambda e: (e["last_seen"], e["symbol"]), reverse=True)
    kept = ordered[:cap]
    return {
        "schema": WATCHLIST_SCHEMA,
        "as_of": as_of,
        "window_days": days,
        "window_from": floor,
        "cap": cap,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "n_symbols": len(kept),
        # A cap that silently bites is a coverage claim nobody can check.
        "n_symbols_before_cap": len(ordered),
        "n_filings_considered": considered,
        "n_filings_out_of_window": out_of_window,
        "n_filings_unresolved_subject": unresolved,
        "symbols": [e["symbol"] for e in kept],
        "entries": kept,
    }


def write_watchlist(wl: dict[str, Any]) -> Path:
    p = watchlist_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(wl, indent=1, default=str), encoding="utf-8")
    return p


def attention_symbols() -> list[str]:
    """The watchlist's symbols, for `scripts/tracker.py` to union into its refresh.

    A MISSING file returns [] -- the watchlist is new and a day before its first
    run is a day with no attention names, which is true. An UNREADABLE file
    raises: a corrupt watchlist is a different thing from an absent one and must
    not be laundered into "no attention names today".
    """
    p = watchlist_path()
    if not p.exists():
        return []
    try:
        wl = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SourceRefusal(f"attention_watchlist.json at {p} is unreadable: {exc}") from exc
    syms = wl.get("symbols")
    if syms is None:
        raise SourceRefusal(f"attention_watchlist.json at {p} carries no `symbols` key")
    return [str(s).upper() for s in syms if s]


# -------------------------------------------------------------------- probe

def probe() -> tuple[bool, str]:
    """NETWORK. One recent business day's index, parsed but not resolved."""
    d = datetime.now(timezone.utc).date()
    for back in range(1, 8):
        day = (d - timedelta(days=back)).isoformat()
        try:
            recs = parse_form_index(fetch_daily_index(day), day=day)
        except SourceRefusal:
            continue
        return True, f"{day}: {len(recs)} ownership filings in the daily index"
    return False, "no parseable daily index in the last 7 days"
