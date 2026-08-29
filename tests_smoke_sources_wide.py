"""Smoke checks for the WIDE sensors: EDGAR filings, IR feeds, fleet-universe news.
No keys, no network -- both transports are replaced with fakes that RECORD.

Run: python run_tests.py -k sources_wide

What these pin, in order of what a regression would cost:

1. **the two timestamps** -- an EDGAR row's `observed_at` is the acceptance
   second, and the 22:00 ET fallback is AFTER the day's cutoff, never at
   midnight; `effective_at` is the filing date;
2. **the bounded-result branch** -- when `recent` does not reach the window
   start, the older pages are fetched; when it does, they are NOT;
3. **the throttle** -- eight calls per second means the seventh call waits;
4. **the form filter** -- 3/5/144/DEF 14A are counted and NOT stored;
5. **no invented timestamps** -- an RSS entry without a date is dropped and
   the drop is counted;
6. **the UA on every request** -- asserted on the fake transport, for both
   collectors, including robots.txt;
7. **a dead host is abandoned** after two failures instead of absorbing the
   whole path list.
"""
from __future__ import annotations

import os
import tempfile
import urllib.error
from datetime import date, timedelta

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


_TMP = tempfile.mkdtemp(prefix="aat_wide_test_")
os.environ["AAT_STATE_DIR"] = _TMP

from alpha.sources import corpus                                        # noqa: E402
from scripts import edgar_backfill as eb                               # noqa: E402
from scripts import ir_backfill as ir                                  # noqa: E402
from scripts import news_backfill as nb                                # noqa: E402

TODAY = date.today()
D = lambda n: (TODAY - timedelta(days=n)).isoformat()                  # noqa: E731

# ------------------------------------------------------------------ EDGAR
print("\n-- EDGAR: fixture -> observations with the right two timestamps")
calls: list[tuple[str, dict]] = []

RECENT = {
    "form": ["8-K", "4", "SC 13D/A", "424B5", "10-Q", "3", "DEF 14A", "SC TO-T", "S-1/A", "144"],
    "filingDate": [D(10), D(20), D(30), D(40), D(50), D(60), D(70), D(80), D(90), D(100)],
    "acceptanceDateTime": [f"{D(10)}T21:05:33.000Z", "", f"{D(30)}T16:31:00.000Z", "", f"{D(50)}T20:00:00.000Z",
                           "", "", "", "", ""],
    "items": ["2.02,9.01", "", "", "", "", "", "", "", "", ""],
    "accessionNumber": [f"0001-{i:02d}-000001" for i in range(10)],
    "primaryDocument": [f"doc{i}.htm" for i in range(10)],
    "primaryDocDescription": ["8-K", "FORM 4", "13D/A", "424B5", "10-Q", "3", "PROXY", "SC TO-T", "S-1/A", "144"],
    "reportDate": [""] * 10,
}
OLD_PAGE = {
    "form": ["8-K"], "filingDate": [D(200)], "acceptanceDateTime": [f"{D(200)}T12:00:00.000Z"],
    "items": ["8.01"], "accessionNumber": ["0001-99-000001"], "primaryDocument": ["old.htm"],
    "primaryDocDescription": ["8-K"], "reportDate": [""],
}
SUBMISSIONS = {"cik": 1234, "name": "TEST CO", "filings": {
    "recent": RECENT,
    "files": [{"name": "CIK0000001234-submissions-001.json", "filingFrom": D(400), "filingTo": D(150)},
              {"name": "CIK0000001234-submissions-002.json", "filingFrom": D(900), "filingTo": D(401)}]}}
TICKERS = {"0": {"cik_str": 1234, "ticker": "TST", "title": "Test Co"}}
FIXTURES = {"company_tickers.json": TICKERS, "CIK0000001234.json": SUBMISSIONS,
            "CIK0000001234-submissions-001.json": OLD_PAGE,
            "CIK0000001234-submissions-002.json": {"form": ["8-K"], "filingDate": [D(800)], "acceptanceDateTime": [""],
                                                   "items": [""], "accessionNumber": ["x"], "primaryDocument": ["y"],
                                                   "primaryDocDescription": [""], "reportDate": [""]}}


def fake_http(url, headers, timeout=30.0):
    import json as _j
    calls.append((url, dict(headers)))
    name = url.rsplit("/", 1)[-1]
    if name not in FIXTURES:
        raise urllib.error.HTTPError(url, 404, "nf", {}, None)
    return _j.dumps(FIXTURES[name]).encode()


eb._http_get = fake_http
ticks: list[float] = [0.0]
slept: list[float] = []
thr = eb.Throttle(8.0, clock=lambda: ticks[0], sleep=lambda s: (slept.append(s), ticks.__setitem__(0, ticks[0] + s)))

tmap = eb.ticker_map(thr, refresh=True)
check("ticker map resolves TST -> zero-padded CIK", tmap.get("TST", ("",))[0] == "0000001234", str(tmap))

since_short = D(100)               # recent reaches exactly D(100) -> covers the window, NO paging
filings, rec = eb.filings_since("0000001234", since_short, thr, refresh=True)
check("recent block covers a 100-day window: no page-back", rec["paged_back"] is False and rec["pages_fetched"] == 0, str(rec))
check("all 10 recent filings inside the window", rec["n_in_window"] == 10)

obs = [o for o in (eb.to_observation("TST", "0000001234", "Test Co", f) for f in filings) if o]
by_form = {o.extra["form"]: o for o in obs}
check("form filter stores 8-K,4,13D/A,424B5,10-Q,SC TO-T,S-1/A and drops 3, DEF 14A, 144",
      set(by_form) == {"8-K", "4", "SC 13D/A", "424B5", "10-Q", "SC TO-T", "S-1/A"}, str(sorted(by_form)))
k = by_form["8-K"]
check("observed_at = acceptanceDateTime (UTC)", k.observed_at == f"{D(10)}T21:05:33+00:00", k.observed_at)
check("effective_at = filingDate", k.effective_at == D(10))
check("title is '<form> <items> [accession]'", k.title == "8-K 2.02,9.01 [0001-00-000001]", k.title)
two = [eb.to_observation("TST", "0000001234", "Test Co",
                         {"form": "4", "filingDate": D(20), "accessionNumber": f"0009-00-00000{i}", "primaryDocument": "f.xml"})
       for i in (1, 2)]
check("two same-day Form 4s are two rows, not one (uid differs)", two[0].uid != two[1].uid)
sixk = eb.to_observation("TSM", "0000001046179", "TSMC", {"form": "6-K", "filingDate": D(5), "accessionNumber": "a-b-c", "primaryDocument": "x.htm"})
check("6-K (foreign private issuer) is stored as a filing", sixk is not None and sixk.kind == "filing")
check("primary document URL built", k.url.endswith("/000100000001/doc0.htm") and "/edgar/data/1234/" in k.url, k.url)
check("source/source_type/verified", (k.source, k.source_type, k.source_verified) == ("sec_edgar", "company_filing", True))
f4 = by_form["4"]
et_hour = f4.observed_at
check("no acceptance -> 22:00 ET fallback, expressed in UTC (02:00 or 03:00 next day)",
      f4.observed_at.endswith("+00:00") and f4.observed_at[11:13] in ("02", "03") and f4.observed_at[:10] > D(20), et_hour)
check("kinds: 8-K filing, 424B corporate, SC TO corporate",
      (k.kind, by_form["424B5"].kind, by_form["SC TO-T"].kind) == ("filing", "corporate", "corporate"))

print("\n-- EDGAR: the bounded-result branch fires when `recent` is younger than the window")
n_before = len(calls)
filings, rec = eb.filings_since("0000001234", D(365), thr, refresh=True)
check("paged back", rec["paged_back"] is True, str(rec))
check("fetched ONLY the page whose filingTo reaches the window (1 of 2)", rec["pages_fetched"] == 1, str(rec))
check("older filing recovered into the window", any(f["filingDate"] == D(200) for f in filings))
check("filing older than the window excluded", not any(f["filingDate"] == D(800) for f in filings))
fetched = [u for u, _ in calls[n_before:]]
check("page 002 (filingTo older than window) not requested", not any(u.endswith("-002.json") for u in fetched), str(fetched))

print("\n-- EDGAR: every request carries the required UA")
check("UA on every EDGAR request", calls and all(h.get("User-Agent") == eb.USER_AGENT for _, h in calls),
      f"{len(calls)} calls")
check("UA names a contact address", "mrthnabdullaev@gmail.com" in eb.USER_AGENT)

print("\n-- EDGAR: the throttle spaces calls at <= 8/s")
ticks[0] = 0.0
slept.clear()
t = eb.Throttle(8.0, clock=lambda: ticks[0], sleep=lambda s: (slept.append(s), ticks.__setitem__(0, ticks[0] + s)))
for _ in range(9):
    t.wait()
check("9 back-to-back calls sleep 8 times", len(slept) == 8, str(slept))
check("each gap is 1/8 s", all(abs(s - 0.125) < 1e-9 for s in slept))
check("9 calls span >= 1 s of clock", ticks[0] >= 1.0 - 1e-9, str(ticks[0]))
ticks[0] = 10.0
t.wait()
check("a call after a long gap does not sleep", len(slept) == 8)

print("\n-- EDGAR: refusal is named, not swallowed")
rec = eb.backfill_symbol("NOPE", "0000009999", "No Co", D(365), thr, refresh=True, dry_run=True)
check("404 lands in the symbol's refusals", rec["refusals"] and "HTTP 404" in rec["refusals"][0], str(rec["refusals"]))

print("\n-- EDGAR: end-to-end store + dedupe")
rec = eb.backfill_symbol("TST", "0000001234", "Test Co", D(120), thr, refresh=True)
check("stored 7, form census lists 'other'", rec["stored"] == 7 and rec["by_form"].get("other") == 3, str(rec["by_form"]))
rec2 = eb.backfill_symbol("TST", "0000001234", "Test Co", D(120), thr, refresh=True)
check("re-run stores nothing", rec2["stored"] == 0 and rec2["known"] == 7)
rows = corpus.read(kinds=("filing", "corporate"), symbols=("TST",))
check("corpus holds the filings under sec_edgar", len(rows) == 7 and all(r["source"] == "sec_edgar" for r in rows))
check("as_of before every acceptance hides every row", not corpus.read(kinds=("filing",), symbols=("TST",), as_of=D(60)))
check("as_of after the 13D acceptance shows the 13D and hides the 8-K",
      {r["extra"]["form"] for r in corpus.read(kinds=("filing",), symbols=("TST",), as_of=D(25))} == {"SC 13D/A", "10-Q"})

# --------------------------------------------------------------------- IR
print("\n-- IR: RSS fixture -> observations; entry without a date dropped and counted")
RSS = f"""<?xml version="1.0"?><rss version="2.0"><channel><title>Test IR</title>
<item><title>Test Co reports Q2</title><link>https://ir.test.com/a</link>
<description>Revenue up</description><pubDate>Tue, 05 Aug 2025 12:30:00 GMT</pubDate></item>
<item><title>Undated release</title><link>https://ir.test.com/b</link><description>x</description></item>
<item><title>Atom-style date</title><link>https://ir.test.com/c</link><pubDate>2025-09-01T08:00:00-04:00</pubDate></item>
</channel></rss>"""
entries = ir.parse_feed(RSS.encode())
check("three entries parsed", len(entries) == 3)
obs, dropped = ir.to_observations("TST", "ir.test.com", entries)
check("undated entry dropped and counted", dropped == 1 and len(obs) == 2, f"{dropped} dropped")
check("RFC822 date -> UTC", obs[0].observed_at == "2025-08-05T12:30:00+00:00", obs[0].observed_at)
check("ISO date with offset -> UTC", obs[1].observed_at == "2025-09-01T12:00:00+00:00", obs[1].observed_at)
check("source company_ir:<host>, verified, issuer group",
      (obs[0].source, obs[0].source_type, obs[0].source_verified, obs[0].independence_group)
      == ("company_ir:ir.test.com", "company_ir", True, "issuer:TST"))
ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>x</title>
<entry><title>Atom entry</title><link href="https://x/1"/><summary>s</summary><published>2025-07-01T10:00:00Z</published></entry></feed>"""
a = ir.parse_feed(ATOM.encode())
check("Atom entries parsed with href link", len(a) == 1 and a[0]["link"] == "https://x/1" and a[0]["published"] == "2025-07-01T10:00:00+00:00", str(a))
try:
    ir.parse_feed(b"<html><body>not a feed</body></html>")
    check("HTML refused as a feed", False)
except ir.FeedRefusal:
    check("HTML refused as a feed", True)

print("\n-- IR: discovery -- UA on every request incl. robots, dead host after two failures, first feed wins")
ir_calls: list[tuple[str, dict]] = []


def fake_ir_http(url, headers, timeout=15.0):
    ir_calls.append((url, dict(headers)))
    host = url.split("/")[2]
    if url.endswith("/robots.txt"):
        return 200, b"User-agent: *\nDisallow: /private\n"
    if host == "ir.test.com":
        raise urllib.error.URLError("dns")           # every path fails -> host dies after 2
    if host == "investors.test.com" and url.endswith("/rss/pressrelease.aspx"):
        return 200, RSS.encode()
    raise urllib.error.HTTPError(url, 404, "nf", {}, None)


ir._http_get = fake_ir_http
tk = [0.0]
pacer = ir.Pacer(1.0, clock=lambda: tk[0], sleep=lambda s: tk.__setitem__(0, tk[0] + s))
fetcher = ir.Fetcher(pacer)
rec = ir.discover("TST", "test.com", fetcher)
check("feed found on the second host", rec["found"] and rec["feed"] == "https://investors.test.com/rss/pressrelease.aspx", str(rec["feed"]))
ir_hits = [u for u, _ in ir_calls if u.split("/")[2] == "ir.test.com" and not u.endswith("robots.txt")]
check("ir.test.com abandoned after exactly 2 failures", len(ir_hits) == 2, str(ir_hits))
check("skipped host recorded on the receipt", "ir.test.com" in rec["skipped_hosts"])
check("stopped at the first feed (no www. attempts)", not any(u.split("/")[2] == "www.test.com" for u, _ in ir_calls))
check("UA on every IR request including robots.txt", all(h.get("User-Agent") == ir.USER_AGENT for _, h in ir_calls), f"{len(ir_calls)} calls")
check("robots.txt fetched once per host", sum(1 for u, _ in ir_calls if u.endswith("robots.txt")) == 2)
check("pacer spaced every call by >= 1s", pacer.n_calls == len(ir_calls) and tk[0] >= len(ir_calls) - 1, f"{pacer.n_calls} calls, clock {tk[0]}")
rp_fetch = fetcher
try:
    rp_fetch.get("https://investors.test.com/private/x.xml")
    check("robots Disallow honoured", False)
except ir.FeedRefusal as exc:
    check("robots Disallow honoured", "robots" in str(exc), str(exc))

# ----------------------------------------------------------- news_backfill
print("\n-- news_backfill: --universe fleet is the wide set; coverage names thin symbols")
import argparse                                                        # noqa: E402
import json                                                            # noqa: E402
# The state dir is the scratch one, so the window universe is whatever THIS
# test writes -- the real file is 98 names and lives in the real state dir.
(corpus.STATE / "window_universe.json").write_text(json.dumps({"universe": ["zzwin", "PANW"]}), encoding="utf-8")
ns = argparse.Namespace(symbols=None, murat=False, universe="fleet")
u = nb._universe(ns)
check("fleet universe includes MURAT_NAMES and the indices", set(nb.MURAT_NAMES) <= set(u) and {"SPY", "QQQ", "IWM"} <= set(u), f"{len(u)} names")
check("fleet universe includes the window universe, upper-cased", {"ZZWIN", "PANW"} <= set(u))
check("fleet universe includes the theme basket", len(u) >= len(nb.MURAT_NAMES) + 3 + 2 + 30, str(len(u)))
check("wide_universe is deduped and sorted", u == sorted(set(u)))
check("THIN floor is 3", nb.THIN_ITEMS == 3)
check("news_backfill.wide_universe is what edgar_backfill imports", eb.wide_universe is nb.wide_universe)

print()
if fails:
    print(f"FAILED {len(fails)}: {fails}")
    raise SystemExit(1)
print("ALL OK")
