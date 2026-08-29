"""EDGAR_BACKFILL -- the ISSUER speaking to the REGULATOR, one row per filing.

    python -m scripts.edgar_backfill --murat                  # Murat's twenty names
    python -m scripts.edgar_backfill                          # the ~160-name fleet universe
    python -m scripts.edgar_backfill --symbols SLDP KYTX --months 12
    python -m scripts.edgar_backfill --dry-run                # count, store nothing

WHY THIS SOURCE
===============
The corpus held news for 21 symbols on 2026-08-29 because every collector in
it asked a WIRE what it had written. A wire writes about NVDA 390 times for
every AARD headline. The SEC does not have that bias: a company that files a
Form 4, an 8-K or a 13D files it whether or not Benzinga cares, and the
filing carries the two timestamps the corpus is built on --

- `filingDate`         -> `effective_at`  (the day the fact was filed)
- `acceptanceDateTime` -> `observed_at`   (the second EDGAR accepted it; that
                                            is the moment it became knowable)

-- so it is the one source in the pipe whose point-in-time discipline the
issuer itself guarantees. `source_type` is `company_filing`, the top of the
independence ladder in `registry.py`; a wire restating an 8-K is not a second
witness and the digest can now see that.

THE BOUNDED-RESULT TRAP, HERE
=============================
`data.sec.gov/submissions/CIK##########.json` returns a `recent` block that is
CAPPED (~1,000 filings). For a quiet biotech that block spans years; for a
company whose insiders file Form 4 every week it spans MONTHS, and a collector
that read `recent` alone would report twelve months of coverage on a name
where it held four -- the same shape as the Finnhub 1500-row cap and the
digest chunk (`docs/CORPUS_2026-08-29_MEMORY_AND_DIARY.md` §2: "never accept a
bounded answer as a complete one"). So the earliest date in `recent` is
CHECKED against the window, and when it is younger the older pages in
`filings.files[]` are fetched until the window is covered. The receipt says,
per symbol, how many pages it took.

RATE LIMIT AND IDENTITY
=======================
The SEC's published rule is 10 requests/second with a descriptive User-Agent
naming a contact; requests without one are refused with 403. `Throttle` paces
every call at `MAX_RPS` = 8, measured on a monotonic clock, and the UA is set on
every request by the single transport function -- there is no second path an
un-headed request could leave by.

NO LLM, NO INTERPRETATION
=========================
This stores WHAT WAS FILED. It does not read the filing, does not decide what an
8-K item 2.02 meant, and places nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from alpha.sources import corpus
from scripts.news_backfill import MURAT_NAMES, wide_universe

USER_AGENT = "AegisFinance research contact mrthnabdullaev@gmail.com"
MAX_RPS = 8.0                                   # SEC rule is 10/s; 8 leaves headroom
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
CACHE = corpus.STATE / "sec_cache" / "edgar"     # state/sec_cache is gitignored
TICKER_TTL_S = 24 * 3600
SUBMISSIONS_TTL_S = 6 * 3600                    # filings land daily; a day-old index is stale

#: The forms we keep, matched on the form's PREFIX so amendments ("8-K/A",
#: "SC 13D/A") and the 424B family ("424B3", "424B5") are included. Anything
#: else (3, 5, 144, DEF 14A, ...) is counted under `other` and not stored.
FORM_PREFIXES: tuple[tuple[str, str], ...] = (
    ("8-K", "filing"),
    ("4", "filing"),            # exact-match guarded below: "4" and "4/A" only
    ("SC 13D", "filing"),
    ("SC 13G", "filing"),
    ("S-1", "corporate"),       # registration -- an offering is coming
    ("424B", "corporate"),      # prospectus -- the offering is PRICED
    ("SC TO", "corporate"),     # tender offer
    ("10-Q", "filing"),
    ("10-K", "filing"),
    ("6-K", "filing"),          # foreign private issuers (TSM, NIO, JKS...) file 6-K, not 8-K
    ("20-F", "filing"),         # ...and 20-F, not 10-K. Without these an ADR is blind.
)

#: Tickers the SEC's own map lacks, with the CIK found by hand. VERIFIED AT
#: FETCH TIME: the submissions JSON's `name` must contain the expected word or
#: the override is refused -- a wrong CIK would file another company's 8-Ks
#: under this symbol and nothing downstream could tell.
CIK_OVERRIDES: dict[str, tuple[str, str]] = {
    "SLNO": ("0001484565", "SOLENO"),
}

ET = ZoneInfo("America/New_York")


class EdgarRefusal(RuntimeError):
    """The SEC did not answer, or answered with something we will not store."""


# ------------------------------------------------------------------ transport
class Throttle:
    """At most `rps` calls per second on a MONOTONIC clock.

    `clock` and `sleep` are injectable so the pacing can be tested without
    spending wall time; the default is real time.
    """

    def __init__(self, rps: float = MAX_RPS, *, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.min_gap = 1.0 / float(rps)
        self._clock, self._sleep = clock, sleep
        self._last: float | None = None
        self.n_calls = 0
        self.slept_s = 0.0

    def wait(self) -> None:
        now = self._clock()
        if self._last is not None:
            gap = self.min_gap - (now - self._last)
            if gap > 0:
                self._sleep(gap)
                self.slept_s += gap
                now = self._clock()
        self._last = now
        self.n_calls += 1


def _http_get(url: str, headers: dict[str, str], timeout: float = 30.0) -> bytes:
    """The ONE transport. Tests replace this attribute and assert on `headers`."""
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_json(url: str, throttle: Throttle) -> Any:
    throttle.wait()
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
    try:
        raw = _http_get(url, headers)
    except urllib.error.HTTPError as exc:
        raise EdgarRefusal(f"HTTP {exc.code} {url}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise EdgarRefusal(f"{type(exc).__name__} {url}: {str(exc)[:80]}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EdgarRefusal(f"non-JSON {url}") from exc


def _cached_json(path: Path, url: str, throttle: Throttle, ttl_s: float,
                 *, refresh: bool = False) -> Any:
    if not refresh and path.exists() and (time.time() - path.stat().st_mtime) < ttl_s:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    d = fetch_json(url, throttle)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(d), encoding="utf-8")
    return d


# ------------------------------------------------------------- ticker -> CIK
def ticker_map(throttle: Throttle, *, refresh: bool = False) -> dict[str, tuple[str, str]]:
    """{TICKER: (cik10, company title)} from the SEC's own list."""
    d = _cached_json(CACHE / "company_tickers.json", TICKERS_URL, throttle, TICKER_TTL_S,
                     refresh=refresh)
    out: dict[str, tuple[str, str]] = {}
    rows = d.values() if isinstance(d, dict) else d
    for r in rows:
        t = str(r.get("ticker") or "").upper().strip()
        if t:
            out[t] = (f"{int(r['cik_str']):010d}", str(r.get("title") or ""))
    return out


# -------------------------------------------------------------- the filings
def _columns(block: dict[str, Any]) -> list[dict[str, Any]]:
    """EDGAR ships filings as parallel COLUMNS (`form: [...]`, `filingDate: [...]`);
    one dict per filing is what everything downstream wants."""
    keys = [k for k, v in block.items() if isinstance(v, list)]
    n = len(block.get("filingDate") or [])
    return [{k: (block[k][i] if i < len(block[k]) else None) for k in keys} for i in range(n)]


def filings_since(cik10: str, since: str, throttle: Throttle, *,
                  refresh: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Every filing with filingDate >= `since`, paging back past `recent` when
    the recent block does not reach that far. Returns (filings, receipt)."""
    sub = _cached_json(CACHE / f"CIK{cik10}.json", SUBMISSIONS_URL.format(name=f"CIK{cik10}.json"),
                       throttle, SUBMISSIONS_TTL_S, refresh=refresh)
    filings_block = (sub or {}).get("filings") or {}
    recent = _columns(filings_block.get("recent") or {})
    dates = [str(f.get("filingDate") or "") for f in recent if f.get("filingDate")]
    earliest = min(dates) if dates else None
    receipt = {"n_recent": len(recent), "recent_earliest": earliest, "pages_fetched": 0,
               "pages_available": len(filings_block.get("files") or []), "paged_back": False}
    rows = list(recent)
    # THE BOUNDED-RESULT CHECK. If the recent block's earliest filing is YOUNGER
    # than the window start, the block was capped inside our window and the
    # older pages hold the rest. A collector that skipped this would report a
    # full year on exactly the names that file the most.
    if earliest is not None and earliest > since:
        receipt["paged_back"] = True
        for page in filings_block.get("files") or []:
            # `filingTo` is the newest date on that page; a page whose newest
            # filing is older than the window cannot contribute.
            if str(page.get("filingTo") or "") < since:
                continue
            name = page.get("name")
            if not name:
                continue
            old = _cached_json(CACHE / name, SUBMISSIONS_URL.format(name=name), throttle,
                               SUBMISSIONS_TTL_S, refresh=refresh)
            rows += _columns(old if isinstance(old, dict) else {})
            receipt["pages_fetched"] += 1
    out = [f for f in rows if str(f.get("filingDate") or "") >= since]
    receipt["n_in_window"] = len(out)
    return out, receipt


def classify_form(form: str) -> tuple[str | None, str]:
    """(kind or None, canonical family). None means: counted, not stored."""
    f = (form or "").strip().upper()
    if f in ("4", "4/A"):
        return "filing", "4"
    for prefix, kind in FORM_PREFIXES:
        if prefix == "4":
            continue
        if f == prefix or f.startswith(prefix + "/") or (prefix in ("424B", "SC TO") and f.startswith(prefix)):
            return kind, prefix
    return None, "other"


def observed_at_for(filing: dict[str, Any]) -> str:
    """acceptanceDateTime when EDGAR gives it; else 22:00 ET on the filing date.

    22:00 ET is AFTER the EDGAR daily cutoff (22:00 ET), so a fallback row is
    never observable before the venue could have seen it -- the conservative
    direction. A fallback at 00:00 would let a same-day filing be "known" at
    the open.
    """
    acc = str(filing.get("acceptanceDateTime") or "").strip()
    if acc:
        try:
            dt = datetime.fromisoformat(acc.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
        except ValueError:
            pass
    d = str(filing.get("filingDate") or "")[:10]
    y, m, dd = int(d[:4]), int(d[5:7]), int(d[8:10])
    return datetime(y, m, dd, 22, 0, tzinfo=ET).astimezone(timezone.utc).isoformat(timespec="seconds")


def to_observation(symbol: str, cik10: str, company: str,
                   filing: dict[str, Any]) -> corpus.Observation | None:
    kind, family = classify_form(str(filing.get("form") or ""))
    if kind is None:
        return None
    form = str(filing.get("form") or "").strip()
    items = str(filing.get("items") or "").strip()
    acc = str(filing.get("accessionNumber") or "")
    # THE TITLE CARRIES THE ACCESSION NUMBER. The corpus uid is a hash of
    # (source, kind, symbols, title, date), and a Form 4's title is otherwise
    # just "4" -- so on the first live run 145 of TSM's 174 insider filings
    # were "already known" because several insiders file the same day. The
    # accession number is the filing's identity at the SEC; nothing else in the
    # index is guaranteed to differ between two same-day filings.
    title = (f"{form} {items}".strip() if items else form) + (f" [{acc}]" if acc else "")
    doc = str(filing.get("primaryDocument") or "")
    url = ARCHIVE_URL.format(cik=int(cik10), acc=acc.replace("-", ""), doc=doc) if acc and doc else ""
    return corpus.Observation(
        kind=kind, tense="past", title=title,
        body=str(filing.get("primaryDocDescription") or "")[:300],
        url=url, source="sec_edgar", source_type="company_filing",
        observed_at=observed_at_for(filing), effective_at=str(filing.get("filingDate"))[:10],
        symbols=(symbol.upper(),), independence_group=f"issuer:{symbol.upper()}",
        source_verified=True,                   # the issuer filed it with the regulator
        extra={"form": form, "family": family, "items": items, "accession": acc,
               "cik": cik10, "company": company,
               "acceptance": filing.get("acceptanceDateTime"),
               "report_date": filing.get("reportDate")})


def backfill_symbol(symbol: str, cik10: str, company: str, since: str, throttle: Throttle,
                    *, refresh: bool = False, dry_run: bool = False) -> dict[str, Any]:
    rec: dict[str, Any] = {"symbol": symbol, "cik": cik10, "company": company,
                           "by_form": {}, "stored": 0, "known": 0, "refusals": []}
    try:
        filings, page_receipt = filings_since(cik10, since, throttle, refresh=refresh)
    except EdgarRefusal as exc:
        rec["refusals"].append(str(exc))
        return rec
    rec.update(page_receipt)
    obs: list[corpus.Observation] = []
    for f in filings:
        o = to_observation(symbol, cik10, company, f)
        fam = classify_form(str(f.get("form") or ""))[1]
        rec["by_form"][fam] = rec["by_form"].get(fam, 0) + 1
        if o is not None:
            obs.append(o)
    if not dry_run:
        rec["stored"], rec["known"] = corpus.append_many(obs)
    else:
        rec["would_store"] = len(obs)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--murat", action="store_true", help="Murat's twenty names only")
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--refresh", action="store_true", help="ignore the on-disk cache")
    ap.add_argument("--dry-run", action="store_true", help="fetch and count; store nothing")
    args = ap.parse_args()

    if args.symbols:
        syms = sorted({s.upper() for s in args.symbols})
    elif args.murat:
        syms = sorted(MURAT_NAMES)
    else:
        syms = wide_universe()
    since = (datetime.now(timezone.utc).date() - timedelta(days=int(30.5 * args.months))).isoformat()

    throttle = Throttle(MAX_RPS)
    t0 = time.time()
    print(f"EDGAR backfill {len(syms)} names, filings since {since}, <= {MAX_RPS:.0f} req/s, "
          f"UA {USER_AGENT!r}")
    try:
        tmap = ticker_map(throttle, refresh=args.refresh)
    except EdgarRefusal as exc:
        print(f"REFUSED: ticker map -- {exc}")
        return 1
    print(f"  ticker map: {len(tmap)} tickers")

    records: list[dict[str, Any]] = []
    no_cik: list[str] = []
    for s in syms:
        if s in tmap:
            cik10, company = tmap[s]
        elif s in CIK_OVERRIDES:
            cik10, expect = CIK_OVERRIDES[s]
            try:
                sub = _cached_json(CACHE / f"CIK{cik10}.json", SUBMISSIONS_URL.format(name=f"CIK{cik10}.json"),
                                   throttle, SUBMISSIONS_TTL_S, refresh=args.refresh)
            except EdgarRefusal as exc:
                records.append({"symbol": s, "cik": cik10, "company": "", "by_form": {}, "stored": 0,
                                "known": 0, "refusals": [str(exc)]})
                continue
            company = str((sub or {}).get("name") or "")
            if expect not in company.upper():
                records.append({"symbol": s, "cik": cik10, "company": company, "by_form": {}, "stored": 0,
                                "known": 0, "refusals": [f"override CIK {cik10} is {company!r}, not {expect}"]})
                continue
        else:
            no_cik.append(s)
            continue
        rec = backfill_symbol(s, cik10, company, since, throttle,
                              refresh=args.refresh, dry_run=args.dry_run)
        records.append(rec)
        forms = " ".join(f"{k}={v}" for k, v in sorted(rec["by_form"].items()))
        paged = f"  PAGED {rec.get('pages_fetched', 0)} back" if rec.get("paged_back") else ""
        ref = f"  REFUSED {rec['refusals'][0][:60]}" if rec["refusals"] else ""
        n = rec.get("would_store", rec["stored"])
        print(f"  {s:<6} +{n:>4} new {rec['known']:>4} known  [{forms}]{paged}{ref}")

    corpus.flush_index()
    elapsed = time.time() - t0
    total_new = sum(r.get("would_store", r["stored"]) for r in records)
    refused = [r for r in records if r["refusals"]]
    print(f"\nstored {total_new} new filings across {len(records)} names in {elapsed:.0f}s "
          f"({throttle.n_calls} requests, {throttle.slept_s:.1f}s throttled)")
    if no_cik:
        # ETFs (SPY/QQQ/IWM) and foreign ADRs without a US ticker entry land here.
        # Named, not silently dropped: "no filings" and "not in the map" differ.
        print(f"NO CIK ({len(no_cik)}): {' '.join(no_cik)}")
    if refused:
        print(f"REFUSALS ({len(refused)}): " + "; ".join(f"{r['symbol']} {r['refusals'][0][:70]}" for r in refused))
    paged = [r["symbol"] for r in records if r.get("paged_back")]
    if paged:
        print(f"paged past `recent` ({len(paged)}): {' '.join(paged)}")

    receipt = corpus.CORPUS / f"edgar_backfill_{datetime.now(timezone.utc).date().isoformat()}.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({"at": corpus.utcnow(), "since": since, "n_symbols": len(syms),
                                   "dry_run": args.dry_run, "elapsed_s": round(elapsed, 1),
                                   "requests": throttle.n_calls, "no_cik": no_cik,
                                   "records": records}, indent=1), encoding="utf-8")
    print(f"receipt: {receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
