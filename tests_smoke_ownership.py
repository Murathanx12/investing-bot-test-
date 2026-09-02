"""THE 13D/13G WATCHER: the four ways it could have been silently empty.

On 2026-08-20 a Schedule 13G for ~8.5% of GoPro was filed by Mark Fischbach. The
stock exploded around the 2026-09-01 announcement and AEGIS had nothing to say,
because GPRO cleared neither the universe's $2 price floor nor its $3m/day
execute floor and `alpha/sources/sec.py` watches only 8-K Item 2.02. MISS TYPE:
NOT OBSERVED.

`alpha/sources/edgar_ownership.py` is the repair, and every failure mode it can
have is a QUIET one -- a watcher that matches nothing prints "0 filings today"
and looks exactly like a slow week. So these are the pins:

  1. the daily index really is spelled `SCHEDULE 13G`, and the parser that reads
     it takes both spellings (a `SC 13G`-only filter matches ZERO rows, forever);
  2. a filing whose subject cannot be resolved is RECORDED, not dropped;
  3. the watchlist honours its 45-day window, its 200 cap, and is idempotent by
     accession -- running the watcher twice does not double a symbol; and
  4. `scripts/tracker.py`'s refresh actually READS the watchlist. The artery
     lesson: the seal was correct for two days and nothing called it.

OFFLINE. No socket is opened here; the .idx sample below is a real 2026-08-20
excerpt kept verbatim (column widths included) so a format change fails a test
instead of a night's coverage.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

_fails: list[str] = []
ROOT = Path(__file__).resolve().parent


def check(name: str, ok: bool, note: str = "") -> None:
    # `ok` plus two spaces is what run_tests.py's _OK regex counts.
    print(f"  {'ok ' if ok else 'FAIL'}  {name}" + (f"  ({note})" if note else ""))
    if not ok:
        _fails.append(name)


from alpha.sources import edgar_ownership as own          # noqa: E402
from alpha.sources.http import SourceRefusal              # noqa: E402

# OFFLINE, PINNED. run_tests.py blocks the socket, so a stray fetch here would
# surface as a connection refusal from somewhere deep in urllib -- true, and
# unreadable. Every network door in the module goes through `_get_text`, so
# replacing it names the offending URL instead, and keeps a bare
# `python tests_smoke_ownership.py` offline as well.
_net_calls: list[str] = []


def _no_network(url, **kw):
    _net_calls.append(url)
    raise AssertionError(f"this suite must not touch the network: {url}")


own._get_text = _no_network

# ---------------------------------------------------------------------------
# A verbatim excerpt of https://www.sec.gov/Archives/edgar/daily-index/2026/
# QTR3/form.20260820.idx -- header block, one non-ownership row, the GPRO 13G,
# an amendment, and a two-row filing (the same accession under the filer's CIK
# and the subject's) so the grouping is exercised. Column widths are the real
# ones; do not reflow this block.
# ---------------------------------------------------------------------------
IDX = """Description:           Daily Index of EDGAR Dissemination Feed by Form Type
Last Data Received:    Aug 20, 2026
Comments:              webmaster@sec.gov
Anonymous FTP:         ftp://ftp.sec.gov/edgar/




Form Type   Company Name                                                  CIK
      Date Filed  File Name
---------------------------------------------------------------------------------------------------------------------------------------------
1-A              ECOSPIRE GLOBAL INC.                                          2141083     20260820    edgar/data/2141083/0002141083-26-000001.txt
8-K              GROUP 1 AUTOMOTIVE INC                                        1031203     20260820    edgar/data/1031203/0001031203-26-000044.txt
SCHEDULE 13D     Conifer Management, L.L.C.                                    1773994     20260820    edgar/data/1773994/0000905148-26-003844.txt
SCHEDULE 13D     GROUP 1 AUTOMOTIVE INC                                        1031203     20260820    edgar/data/1031203/0000905148-26-003844.txt
SCHEDULE 13G     Fischbach Mark Edward                                         1630759     20260820    edgar/data/1630759/0001630759-26-000003.txt
SCHEDULE 13G     GoPro, Inc.                                                   1500435     20260820    edgar/data/1500435/0001630759-26-000003.txt
SCHEDULE 13G/A   BlackRock, Inc.                                               1364742     20260820    edgar/data/1364742/0001086364-26-004102.txt
13F-HR           SOME ADVISORS LP                                              9999999     20260820    edgar/data/9999999/0009999999-26-000001.txt
"""

#: The header of the real GPRO 13G, trimmed. The SUBJECT is GoPro; the row that
#: carried this filing in the index named FISCHBACH. That gap is the whole
#: reason a second request per filing is paid for.
HEADER = """<SEC-DOCUMENT>0001630759-26-000003.txt : 20260820
<SEC-HEADER>0001630759-26-000003.hdr.sgml : 20260820
<ACCEPTANCE-DATETIME>20260820151702
ACCESSION NUMBER:\t\t0001630759-26-000003
CONFORMED SUBMISSION TYPE:\tSCHEDULE 13G
FILED AS OF DATE:\t\t20260820

SUBJECT COMPANY:\t

\tCOMPANY DATA:\t
\t\tCOMPANY CONFORMED NAME:\t\t\tGoPro, Inc.
\t\tCENTRAL INDEX KEY:\t\t\t0001500435
\t\tSTANDARD INDUSTRIAL CLASSIFICATION:\tPHOTOGRAPHIC EQUIPMENT & SUPPLIES [3861]

\tFILING VALUES:
\t\tFORM TYPE:\t\tSCHEDULE 13G

FILED BY:\t\t

\tCOMPANY DATA:\t
\t\tCOMPANY CONFORMED NAME:\t\t\tFischbach Mark Edward
\t\tCENTRAL INDEX KEY:\t\t\t0001630759

\tFILING VALUES:
\t\tFORM TYPE:\t\tSCHEDULE 13G
</SEC-HEADER>
"""

print("\n-- 1. the form spelling, and the index the SEC actually publishes")

# THE SILENT ZERO. EDGAR full-text search says `SC 13G`; the daily index says
# `SCHEDULE 13G`. A watcher that knows only one of them reports a quiet, wholly
# plausible empty day every day of its life.
check("`SCHEDULE 13G` is an ownership form", own.is_ownership_form("SCHEDULE 13G"))
check("`SC 13G` is too (the other spelling)", own.is_ownership_form("SC 13G"))
for f in ("SCHEDULE 13D", "SC 13D/A", "SCHEDULE 13G/A", "sc 13d"):
    check(f"`{f}` is an ownership form", own.is_ownership_form(f))
for f in ("8-K", "13F-HR", "SC TO-I", "SC 13E3", "4", ""):
    check(f"`{f or '<empty>'}` is NOT", not own.is_ownership_form(f))
check("an amendment is flagged as one",
      own.normalise_form("SCHEDULE 13G/A") == {"form_family": "13G", "amendment": True,
                                               "form_normalised": "SC 13G/A"})
check("a plain 13D normalises without /A",
      own.normalise_form("SCHEDULE 13D")["form_normalised"] == "SC 13D")

recs = own.parse_form_index(IDX, day="2026-08-20")
by_acc = {r["accession"]: r for r in recs}
check("the sample yields 3 ownership FILINGS from 5 ownership ROWS", len(recs) == 3,
      f"{len(recs)}: {sorted(by_acc)}")
check("the 8-K, the 1-A and the 13F-HR are not ownership filings",
      all("13F" not in r["form"] and r["form"] not in ("8-K", "1-A") for r in recs))
check("the GPRO 13G is in there", "0001630759-26-000003" in by_acc)

gpro = by_acc["0001630759-26-000003"]
check("  its form is recorded as the index spelled it", gpro["form"] == "SCHEDULE 13G")
check("  and normalised to SC 13G", gpro["form_normalised"] == "SC 13G")
check("  filed date is parsed to ISO", gpro["filed_date"] == "2026-08-20")
check("  BOTH index rows are grouped onto the one accession", gpro["index_rows"] == 2,
      str(gpro["index_ciks"]))
check("  and both CIKs are kept -- the filer's AND the subject's",
      sorted(gpro["index_ciks"]) == [1500435, 1630759], str(gpro["index_ciks"]))
check("  the index company alone would have named the FILER, not GoPro",
      "Fischbach Mark Edward" in gpro["index_companies"],
      "which is why the header is fetched at all")

amend = by_acc["0001086364-26-004102"]
check("a 13G/A is recorded as an amendment", amend["amendment"] is True)

# An .idx that parses to nothing is a format change or a truncated download.
# Returning [] for it would read as a quiet day, which is the failure this whole
# module exists to stop.
try:
    own.parse_form_index("Description: junk\nnothing here at all\n")
    check("an unparseable index REFUSES rather than reporting an empty day", False)
except SourceRefusal as exc:
    check("an unparseable index REFUSES rather than reporting an empty day",
          "0 parseable rows" in str(exc))

# A company name carrying a run of spaces must not shift the split.
weird = ("SCHEDULE 13D     ACME   HOLDINGS   CORP                                         "
         "     12345       20260820    edgar/data/12345/0000012345-26-000001.txt\n")
w = own.parse_form_index(IDX + weird)
check("a company name with internal double spaces still parses",
      any(r["index_ciks"] == [12345] for r in w),
      str([r["index_companies"] for r in w]))

print("\n-- 2. the subject, and the row that is never dropped")

sub = own.parse_subject_header(HEADER)
check("the SUBJECT COMPANY block names GoPro", sub["subject_name"] == "GoPro, Inc.")
check("  with its CIK", sub["subject_cik"] == 1500435)
check("  and the FILED BY party is kept separately",
      sub["filer_names"] == ["Fischbach Mark Edward"], str(sub["filer_names"]))

# The dangerous fallback: taking the FIRST company in the header. In a 13G that
# is as often the filer as the subject, and a filer written onto the watchlist
# puts the wrong ticker in front of the tracker.
no_subject = HEADER.replace("SUBJECT COMPANY", "FILED BY").replace("FILED BY:\t\t\n", "")
ns = own.parse_subject_header(no_subject)
check("a header with NO subject block resolves to None, not to the first company",
      ns["subject_cik"] is None and ns["reason"],
      str(ns["reason"]))

TICKERS = {1500435: "GPRO", 1031203: "GPI"}

# `resolve_subject` pays ONE header request per filing. The fetch is stubbed so
# both of its failure branches can be exercised deliberately, offline.
_real_fetch = own.fetch_filing_header
own.fetch_filing_header = lambda cik, acc: HEADER

r_ok = own.resolve_subject(dict(gpro), tickers=TICKERS)
check("a resolvable filing gets its subject ticker", r_ok["subject_ticker"] == "GPRO")
check("  named from the HEADER, not from the index row",
      r_ok["subject_name"] == "GoPro, Inc." and "Fischbach" in str(r_ok["index_companies"]))
check("  the filer is kept separately", r_ok["filer_names"] == ["Fischbach Mark Edward"])
check("  and the resolution path is stated on the row",
      r_ok["subject_resolution"] == "sec_header_subject_company+company_tickers")
check("  a clean resolution carries no unresolved_reason",
      r_ok["unresolved_reason"] is None)
check("  the PIT record carries observed_at and the source url",
      bool(r_ok["observed_at"]) and r_ok["url"].endswith(".txt")
      and r_ok["schema"] == own.SCHEMA)


def _forbidden(cik, acc):
    raise SourceRefusal("GET https://www.sec.gov/... -> HTTP 403")


own.fetch_filing_header = _forbidden
r_403 = own.resolve_subject(dict(gpro), tickers=TICKERS)
check("a 403 on the header still RECORDS the filing",
      r_403["accession"] == gpro["accession"] and r_403["form"] == "SCHEDULE 13G")
check("  subject_ticker is null", r_403["subject_ticker"] is None)
check("  and the reason names the failed step",
      "header unavailable" in (r_403["unresolved_reason"] or ""),
      str(r_403["unresolved_reason"]))

own.fetch_filing_header = lambda cik, acc: HEADER
r_nt = own.resolve_subject(dict(gpro), tickers={})
check("a subject with no LISTED ticker is still recorded, with its CIK",
      r_nt["subject_cik"] == 1500435 and r_nt["subject_name"] == "GoPro, Inc.")
check("  ticker null, reason names company_tickers.json",
      r_nt["subject_ticker"] is None
      and "company_tickers.json" in (r_nt["unresolved_reason"] or ""),
      str(r_nt["unresolved_reason"]))

# The index lists one row per party, so the header's subject CIK must be one of
# them. A mismatch means we read the wrong filing -- worth flagging, not worth
# throwing the row away over.
own.fetch_filing_header = lambda cik, acc: HEADER.replace("0001500435", "0000000042")
r_x = own.resolve_subject(dict(gpro), tickers={42: "XXX"})
check("a subject CIK absent from the index rows is FLAGGED, not discarded",
      r_x.get("subject_cik_in_index") is False and r_x["subject_ticker"] == "XXX")

own.fetch_filing_header = lambda cik, acc: HEADER.replace("SUBJECT COMPANY", "FILER")
r_ns = own.resolve_subject(dict(gpro), tickers=TICKERS)
check("a header with no subject block records the row and says so",
      r_ns["subject_ticker"] is None
      and "subject not named" in (r_ns["unresolved_reason"] or ""),
      str(r_ns["unresolved_reason"]))

own.fetch_filing_header = _real_fetch

print("\n-- 3. the store and the watchlist")


def row(sym, filed, acc, form="SC 13G", filer="Some Holder LP"):
    return {"schema": own.SCHEMA, "accession": acc, "form": form, "form_normalised": form,
            "filed_date": filed, "subject_ticker": sym, "subject_cik": 1,
            "subject_name": sym, "filer_names": [filer], "index_companies": [filer]}


AS_OF = "2026-08-31"
edge = (date.fromisoformat(AS_OF) - timedelta(days=own.WATCHLIST_DAYS)).isoformat()
outside = (date.fromisoformat(AS_OF) - timedelta(days=own.WATCHLIST_DAYS + 1)).isoformat()

wl = own.build_watchlist([
    row("GPRO", "2026-08-20", "a1", form="SC 13G", filer="Fischbach Mark Edward"),
    row("EDGE", edge, "a2"),
    row("OLD", outside, "a3"),
    {"accession": "a4", "filed_date": AS_OF, "subject_ticker": None,
     "unresolved_reason": "CIK 42 is not in company_tickers.json"},
], as_of=AS_OF)

check("a filing inside the window is on the watchlist", "GPRO" in wl["symbols"])
check("the 45-day EDGE is inclusive", "EDGE" in wl["symbols"])
check("one day past the window is NOT", "OLD" not in wl["symbols"], str(wl["symbols"]))
check("an unresolved subject is COUNTED, not silently absent",
      wl["n_filings_unresolved_subject"] == 1)
check("the window is stated on the artefact",
      wl["window_days"] == 45 and wl["window_from"] == edge, str(wl["window_from"]))
gpro_e = [e for e in wl["entries"] if e["symbol"] == "GPRO"][0]
check("the GPRO entry names the filer", gpro_e["filer_name"] == "Fischbach Mark Edward")
check("  its last_form is the 13G", gpro_e["last_form"] == "SC 13G")
check("  and it carries the accession", gpro_e["accessions"] == ["a1"])

# The cap is a COST bound on the tracker's per-name fetches. It must bite from
# the OLD end -- a cap that dropped the newest events would delete exactly the
# rows it exists to surface.
many = [row(f"S{i:03d}", (date.fromisoformat(AS_OF) - timedelta(days=i % 40)).isoformat(),
            f"acc{i}") for i in range(300)]
capped = own.build_watchlist(many, as_of=AS_OF)
check("the cap holds at 200", capped["n_symbols"] == own.WATCHLIST_MAX == 200,
      str(capped["n_symbols"]))
check("  and says how many qualified before it bit",
      capped["n_symbols_before_cap"] == 300)
check("  the NEWEST survive the cap -- it must not delete the fresh events",
      capped["entries"][0]["last_seen"] == AS_OF
      and min(e["last_seen"] for e in capped["entries"])
      > min(r["filed_date"] for r in many),
      "a cap biting from the new end would delete exactly what it exists to surface")

# Two filings on one symbol collapse to one entry with both accessions.
twice = own.build_watchlist([row("DUP", "2026-08-20", "x1", form="SC 13D"),
                             row("DUP", "2026-08-25", "x2", form="SC 13D/A")],
                            as_of=AS_OF)
check("two filings on one name are ONE entry", twice["n_symbols"] == 1)
e = twice["entries"][0]
check("  first_seen is the earlier filing", e["first_seen"] == "2026-08-20")
check("  last_form is the LATER one", e["last_form"] == "SC 13D/A")
check("  and both accessions are kept", e["accessions"] == ["x1", "x2"])

print("\n-- 3b. append-only, idempotent by accession")

with tempfile.TemporaryDirectory() as td:
    os.environ["AAT_LEDGER_DIR"] = td
    day = "2026-08-20"
    check("a missing store reads as no accessions", own.recorded_accessions(day) == set())
    check("a missing watchlist is [], not an error", own.attention_symbols() == [])

    batch = [row("GPRO", day, "0001630759-26-000003"), row("GPI", day, "0000905148-26-003844")]
    w1, s1 = own.append_filings(day, batch)
    check("the first run writes both", (w1, s1) == (2, 0), f"{w1},{s1}")
    w2, s2 = own.append_filings(day, batch)
    check("the SECOND run writes nothing -- idempotent by accession", (w2, s2) == (0, 2),
          f"{w2},{s2}")
    lines = own.day_path(day).read_text(encoding="utf-8").strip().splitlines()
    check("  and the file still has exactly two lines", len(lines) == 2, str(len(lines)))

    w3, s3 = own.append_filings(day, batch + [row("NEW", day, "acc-new")])
    check("a genuinely new accession IS appended", (w3, s3) == (1, 2), f"{w3},{s3}")

    # APPEND-ONLY. A re-resolution never overwrites what an earlier run knew.
    before = own.day_path(day).read_text(encoding="utf-8")
    own.append_filings(day, [dict(batch[0], subject_ticker="WRONG")])
    check("a re-resolution does NOT rewrite the earlier line",
          own.day_path(day).read_text(encoding="utf-8") == before,
          "the jsonl is the point-in-time record of what we knew when")

    recorded = own.read_recorded()
    check("read_recorded returns what was written", len(recorded) == 3, str(len(recorded)))
    check("  including the GPRO row", any(r["subject_ticker"] == "GPRO" for r in recorded))

    own.write_watchlist(own.build_watchlist(recorded, as_of=day))
    check("the watchlist round-trips to disk", own.watchlist_path().exists())
    check("  and attention_symbols() reads GPRO back out",
          "GPRO" in own.attention_symbols(), str(own.attention_symbols()))

    # An UNREADABLE watchlist is a different fact from an absent one and must
    # not be laundered into "no attention names today".
    own.watchlist_path().write_text("{ this is not json", encoding="utf-8")
    try:
        own.attention_symbols()
        check("a CORRUPT watchlist refuses (absence != unreadable)", False)
    except SourceRefusal as exc:
        check("a CORRUPT watchlist refuses (absence != unreadable)", "unreadable" in str(exc))
    own.watchlist_path().write_text(json.dumps({"schema": "x"}), encoding="utf-8")
    try:
        own.attention_symbols()
        check("a watchlist with no `symbols` key refuses", False)
    except SourceRefusal as exc:
        check("a watchlist with no `symbols` key refuses", "symbols" in str(exc))

    # WRITE AS YOU GO. 2026-08-14 carried 1,615 ownership filings -- about 22
    # minutes of header requests. If append_filings drained the generator before
    # writing, a kill at minute 20 would destroy 20 minutes of resolved work,
    # which is the failure analyst_panel already paid for once.
    own.day_path("2026-08-22").unlink(missing_ok=True)

    def _dies_after_two():
        yield row("A", "2026-08-22", "s1")
        yield row("B", "2026-08-22", "s2")
        raise RuntimeError("killed mid-day")

    try:
        own.append_filings("2026-08-22", _dies_after_two())
        check("a mid-day kill keeps the rows already resolved", False, "no raise")
    except RuntimeError:
        kept = own.day_path("2026-08-22").read_text(encoding="utf-8").strip().splitlines()
        check("a mid-day kill keeps the rows already resolved", len(kept) == 2,
              f"{len(kept)} lines survived")

    check("iter_resolved is a generator, not an eager list",
          hasattr(own.iter_resolved([], tickers={}), "__next__"),
          "an eager list gives the writer nothing until the last filing lands")

    check("the store honours AAT_LEDGER_DIR at CALL time, not import time",
          str(own._store()).startswith(td),
          "a module-level constant would freeze the wrong path on Railway")
os.environ.pop("AAT_LEDGER_DIR", None)

print("\n-- 4. the tracker actually reads it (the artery pin)")

src = (ROOT / "scripts" / "tracker.py").read_text(encoding="utf-8")
check("scripts/tracker.py references attention_watchlist", "attention_watchlist" in src,
      "a watchlist nothing reads is the book_limits failure again")
check("  it imports the ownership source", "edgar_ownership" in src)
refresh_body = src.split("def refresh(", 1)[-1].split("\ndef ", 1)[0]
check("  and the REFRESH is where the union happens",
      "_attention_union" in refresh_body,
      "not a helper defined beside a function that never calls it")
check("  the union is applied AFTER --limit",
      refresh_body.index("if limit:") < refresh_body.index("_attention_union"),
      "a fast slice must still observe the attention names")
check("rows are labelled with where the name came from",
      '"universe_source": "screen" if m is not None else "ownership_attention"' in src)
check("  and the label is written on the ROW, in the refresh",
      '"universe_source"' in refresh_body)
check("the derived liquidity carries its provenance",
      '"median_dollar_volume_source"' in src and "refresh_bars_60d" in src,
      "the same column filled two ways with no provenance stops meaning anything")
check("an attention name's membership lookup is None-safe",
      "by_symbol.get(sym)" in src and "by_symbol[sym]" not in refresh_body,
      "a KeyError on the first attention name would kill the whole nightly job")
check("a missing/unreadable watchlist warns and continues",
      "attention watchlist unreadable" in src and "SourceRefusal" in src)

union_body = src.split("def _attention_union(", 1)[-1].split("\ndef ", 1)[0]
check("an untradable-at-the-venue name is not silently claimed tradable",
      "SKIPPING the attention union" in union_body,
      "apply_status reads a falsy `tradable` as DROP")
check("  and an ETF-like subject is excluded, as the screen excludes it",
      "looks_like_etf" in union_body,
      "a 13G against a closed-end fund would otherwise enter by the side door")

watch_src = (ROOT / "scripts" / "ownership_watch.py").read_text(encoding="utf-8")
check("scripts/ownership_watch.py writes the watchlist",
      "write_watchlist" in watch_src and "append_filings" in watch_src)
check("  it sweeps business days behind the named day", "business_days_back" in watch_src)
check("  and it can place nothing -- no broker, no order call",
      "AlpacaPaper" not in watch_src and "submit_order" not in watch_src)

from scripts import ownership_watch as watch                    # noqa: E402

check("business_days_back skips the weekend",
      watch.business_days_back("2026-08-24", 3) == ["2026-08-19", "2026-08-20", "2026-08-21"],
      str(watch.business_days_back("2026-08-24", 3)))
check("  and returns them oldest first",
      watch.business_days_back("2026-08-24", 2) == ["2026-08-20", "2026-08-21"])

with tempfile.TemporaryDirectory() as td:
    os.environ["AAT_LEDGER_DIR"] = td
    sweep = watch.days_to_sweep("2026-08-24", backfill=5)
    check("a FIRST run sweeps the trailing week plus the day", len(sweep) == 6, str(sweep))
    check("  ending on the named day", sweep[-1] == "2026-08-24")
    own.append_filings("2026-08-21", [row("X", "2026-08-21", "a")])
    sweep2 = watch.days_to_sweep("2026-08-24", backfill=5)
    check("a day already on disk is NOT re-fetched",
          "2026-08-21" not in sweep2 and len(sweep2) == 5, str(sweep2))
    check("--backfill 0 asks only for the named day",
          watch.days_to_sweep("2026-08-24", backfill=0) == ["2026-08-24"])
os.environ.pop("AAT_LEDGER_DIR", None)

# ---- the cap ranks TIERS, not recency alone (2026-09-02) --------------------
# Measured at full scale: 1,585 symbols qualified over 45 days vs a 200 cap,
# and the quarterly 13G/A amendment flood (1,615 filings on 2026-08-14) would
# have evicted GPRO's ORIGINAL 13G within days. An original outranks any
# amendment; recency orders only within a tier.
flood = [row(f"AM{i:03d}", "2026-08-30", f"am{i}", form="SC 13G/A") for i in range(30)]
old_original = row("GPRO", "2026-08-01", "orig1", form="SC 13G")
wl = own.build_watchlist(flood + [old_original], as_of=AS_OF, cap=10)
kept_syms = wl["symbols"]
check("an old ORIGINAL 13G survives a cap flooded with fresh 13G/A",
      "GPRO" in kept_syms, f"kept={kept_syms[:4]}...")
check("  and ranks FIRST despite being 29 days older", kept_syms[0] == "GPRO")
d_row = row("ACTV", "2026-08-05", "d1", form="SC 13D")
wl2 = own.build_watchlist(flood + [old_original, d_row], as_of=AS_OF, cap=10)
check("  an original 13D outranks the original 13G",
      wl2["symbols"][:2] == ["ACTV", "GPRO"])

check("NOTHING in this suite touched the network", not _net_calls, str(_net_calls))

print()
if _fails:
    print(f"FAILED: {len(_fails)} -> {_fails}")
    raise SystemExit(1)
print("ALL PASS tests_smoke_ownership")
