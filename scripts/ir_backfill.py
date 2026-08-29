"""IR_BACKFILL -- the company's OWN press releases, from its investor-relations feed.

    python -m scripts.ir_backfill                     # Murat's twenty, discover + store
    python -m scripts.ir_backfill --symbols SLDP KYTX
    python -m scripts.ir_backfill --discover-only     # write feeds.json, store nothing

WHY
===
A wire decides what to restate; the issuer's IR page carries everything the
issuer said, dated by the issuer. For a small biotech that is the difference
between four headlines a quarter and every clinical update, and the row is
`source_type="company_ir"` -- second rung of the independence ladder, above
any outlet that repeats it.

FEED DISCOVERY IS A GUESS, AND THE RECEIPT SAYS SO
==================================================
There is no directory of IR feeds. Most IR sites are built by three vendors
(Q4, Notified/GlobeNewswire, Nasdaq IR Insight) that expose RSS at a handful
of conventional paths, so discovery tries those paths on the conventional IR
hosts (`ir.`, `investors.`, `investor.`, `www.`) and STOPS AT THE FIRST FEED
THAT PARSES. GlobeNewswire organisation feeds need an id that cannot be
guessed and are not tried. Every attempt -- found or not -- is written to
`state/corpus/feeds.json` per symbol, so "no IR feed for AARD" is a recorded
fact with the URLs that were tried, not a silent absence.

MANNERS
=======
One request per second per process, a UA that names a contact, `robots.txt`
consulted once per host, and a host is abandoned after two failures (a dead
host would otherwise absorb the whole path list at one second each).

NO INVENTED TIMESTAMPS
======================
An entry without a publication date is DROPPED AND COUNTED. Stamping it "now"
would make a year-old release observable today, which is the leak the corpus
exists to prevent; stamping it with the feed's build date is the same leak with
a better alibi.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable

from alpha.sources import corpus
from scripts.news_backfill import MURAT_NAMES

USER_AGENT = "AegisFinance research contact mrthnabdullaev@gmail.com"
MIN_GAP_S = 1.0                     # one request per second
MAX_FAILURES_PER_HOST = 2
TIMEOUT_S = 15.0

#: Corporate web domains for Murat's twenty. A domain here is a STARTING POINT
#: for discovery, not a feed; discovery still has to find one.
DOMAINS: dict[str, str] = {
    "SLDP": "solidpowerbattery.com", "DKNG": "draftkings.com", "HUBS": "hubspot.com",
    "BHVN": "biohaven.com", "AMSC": "amsc.com", "KYTX": "kyvernatx.com",
    "PRCH": "porchgroup.com", "NTLA": "intelliatx.com", "ABSI": "absci.com",
    "QUBT": "quantumcomputinginc.com", "AARD": "aardvarktherapeutics.com",
    "SOC": "sableoffshore.com", "TSM": "tsmc.com", "MU": "micron.com",
    "MRVL": "marvell.com", "AMD": "amd.com", "SRRK": "scholarrock.com",
    "OLMA": "olema.com", "SLNO": "soleno.life", "BEAM": "beamtx.com",
}

HOST_PREFIXES = ("ir", "investors", "investor", "www")
#: Conventional feed paths, most common vendor first.
FEED_PATHS = (
    "/rss/news-releases.xml",           # Q4
    "/rss/pressrelease.aspx",           # Notified / GlobeNewswire-hosted IR
    "/news-releases/rss",
    "/news/rss",
    "/press-releases/rss",
    "/rss.xml",
    "/feed",
)


class FeedRefusal(RuntimeError):
    pass


class Pacer:
    """One call per `gap` seconds on a monotonic clock; injectable for tests."""

    def __init__(self, gap: float = MIN_GAP_S, *, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.gap, self._clock, self._sleep = gap, clock, sleep
        self._last: float | None = None
        self.n_calls = 0

    def wait(self) -> None:
        now = self._clock()
        if self._last is not None and now - self._last < self.gap:
            self._sleep(self.gap - (now - self._last))
            now = self._clock()
        self._last = now
        self.n_calls += 1


def _http_get(url: str, headers: dict[str, str], timeout: float = TIMEOUT_S) -> tuple[int, bytes]:
    """The ONE transport: (status, body). Tests replace this and assert on headers."""
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


class Fetcher:
    """Paced GET with per-host failure budget and robots.txt consulted once per host."""

    def __init__(self, pacer: Pacer | None = None) -> None:
        self.pacer = pacer or Pacer()
        self.failures: dict[str, int] = {}
        self.robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.log: list[str] = []

    def host_dead(self, host: str) -> bool:
        return self.failures.get(host, 0) >= MAX_FAILURES_PER_HOST

    def _allowed(self, url: str) -> bool:
        host = url.split("/")[2]
        if host not in self.robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                self.pacer.wait()
                status, body = _http_get(f"https://{host}/robots.txt",
                                         {"User-Agent": USER_AGENT, "Accept": "text/plain"})
                rp.parse(body.decode("utf-8", errors="replace").splitlines()) if status == 200 else rp.parse([])
            except Exception:                                           # noqa: BLE001
                rp = None                       # no robots reachable -> nothing forbidden
            self.robots[host] = rp
        rp = self.robots[host]
        return True if rp is None else rp.can_fetch(USER_AGENT, url)

    def get(self, url: str) -> bytes:
        host = url.split("/")[2]
        if self.host_dead(host):
            raise FeedRefusal(f"{host}: skipped after {MAX_FAILURES_PER_HOST} failures")
        if not self._allowed(url):
            raise FeedRefusal(f"{url}: disallowed by robots.txt")
        self.pacer.wait()
        try:
            status, body = _http_get(url, {"User-Agent": USER_AGENT,
                                           "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.5"})
        except urllib.error.HTTPError as exc:
            self.failures[host] = self.failures.get(host, 0) + 1
            raise FeedRefusal(f"HTTP {exc.code} {url}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self.failures[host] = self.failures.get(host, 0) + 1
            raise FeedRefusal(f"{type(exc).__name__} {url}: {str(exc)[:60]}") from exc
        if status != 200:
            self.failures[host] = self.failures.get(host, 0) + 1
            raise FeedRefusal(f"HTTP {status} {url}")
        return body


# ----------------------------------------------------------------- parsing
def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def parse_date(s: str) -> str | None:
    """RFC 822 (RSS) or ISO 8601 (Atom) -> ISO UTC seconds; None if unparseable."""
    s = (s or "").strip()
    if not s:
        return None
    for parser in (parsedate_to_datetime, lambda x: datetime.fromisoformat(x.replace("Z", "+00:00"))):
        try:
            dt = parser(s)
        except (ValueError, TypeError, IndexError):
            continue
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    return None


def parse_feed(raw: bytes) -> list[dict[str, Any]]:
    """RSS 2.0 `item`s or Atom `entry`s -> [{title, link, summary, published}]. Raises on non-feed."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise FeedRefusal(f"not XML: {exc}") from exc
    out: list[dict[str, Any]] = []
    for node in root.iter():
        tag = _strip_ns(node.tag)
        if tag not in ("item", "entry"):
            continue
        fields: dict[str, str] = {}
        link = ""
        for child in node:
            ct = _strip_ns(child.tag)
            if ct == "link":
                link = child.get("href") or _text(child) or link
            elif ct in ("title", "description", "summary", "content", "pubDate", "published", "updated", "date"):
                fields[ct] = _text(child)
        published = (fields.get("pubDate") or fields.get("published") or fields.get("date")
                     or fields.get("updated") or "")
        out.append({"title": fields.get("title", ""), "link": link,
                    "summary": fields.get("description") or fields.get("summary") or fields.get("content") or "",
                    "published_raw": published, "published": parse_date(published)})
    if not out and _strip_ns(root.tag) not in ("rss", "feed", "RDF"):
        raise FeedRefusal(f"XML but not a feed (root <{_strip_ns(root.tag)}>)")
    return out


def to_observations(symbol: str, host: str, entries: list[dict[str, Any]]) -> tuple[list[corpus.Observation], int]:
    """(observations, n_dropped_without_date)."""
    obs, dropped = [], 0
    for e in entries:
        at = e.get("published")
        if not at:
            dropped += 1
            continue
        try:
            obs.append(corpus.Observation(
                kind="news", tense="past", title=e.get("title", "").strip(),
                body=(e.get("summary") or "")[:600], url=e.get("link") or "",
                source=f"company_ir:{host}", source_type="company_ir",
                observed_at=at, effective_at=at[:10], symbols=(symbol.upper(),),
                independence_group=f"issuer:{symbol.upper()}", source_verified=True,
                extra={"published_raw": e.get("published_raw")}))
        except corpus.CorpusRefusal:
            dropped += 1
    return obs, dropped


# --------------------------------------------------------------- discovery
def candidate_urls(domain: str) -> list[str]:
    return [f"https://{pre}.{domain}{path}" for pre in HOST_PREFIXES for path in FEED_PATHS]


def discover(symbol: str, domain: str, fetcher: Fetcher) -> dict[str, Any]:
    """First URL that parses as a feed with >= 1 entry wins. Everything tried is recorded."""
    rec: dict[str, Any] = {"symbol": symbol, "domain": domain, "found": False, "feed": None,
                           "tried": [], "entries": 0, "skipped_hosts": []}
    for url in candidate_urls(domain):
        host = url.split("/")[2]
        if fetcher.host_dead(host):
            if host not in rec["skipped_hosts"]:
                rec["skipped_hosts"].append(host)
            continue
        try:
            body = fetcher.get(url)
            entries = parse_feed(body)
        except FeedRefusal as exc:
            rec["tried"].append({"url": url, "result": str(exc)[:90]})
            continue
        if not entries:
            rec["tried"].append({"url": url, "result": "feed with 0 entries"})
            continue
        rec.update({"found": True, "feed": url, "entries": len(entries), "_entries": entries})
        rec["tried"].append({"url": url, "result": f"FEED {len(entries)} entries"})
        break
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--domain", action="append", default=[], metavar="SYM=domain",
                    help="override/add a corporate domain")
    ap.add_argument("--discover-only", action="store_true")
    args = ap.parse_args()

    domains = dict(DOMAINS)
    for kv in args.domain:
        k, _, v = kv.partition("=")
        domains[k.upper()] = v.strip()
    syms = sorted({s.upper() for s in args.symbols}) if args.symbols else sorted(MURAT_NAMES)

    fetcher = Fetcher()
    t0 = time.time()
    feeds: dict[str, Any] = {}
    total_new = total_known = total_dropped = 0
    print(f"IR feed discovery for {len(syms)} names, 1 req/s, UA {USER_AGENT!r}")
    for s in syms:
        dom = domains.get(s)
        if not dom:
            feeds[s] = {"symbol": s, "domain": None, "found": False, "feed": None, "tried": [],
                        "result": "no domain configured"}
            print(f"  {s:<6} NO DOMAIN configured")
            continue
        rec = discover(s, dom, fetcher)
        entries = rec.pop("_entries", [])
        if rec["found"] and not args.discover_only:
            host = rec["feed"].split("/")[2]
            obs, dropped = to_observations(s, host, entries)
            new, known = corpus.append_many(obs)
            rec.update({"stored": new, "known": known, "dropped_no_date": dropped})
            total_new += new
            total_known += known
            total_dropped += dropped
            span = [o.effective_at for o in obs]
            rec["span"] = [min(span), max(span)] if span else None
        feeds[s] = rec
        if rec["found"]:
            print(f"  {s:<6} FOUND {rec['feed']}  {rec['entries']} entries"
                  + (f"  +{rec['stored']} new {rec['known']} known, {rec['dropped_no_date']} no-date dropped"
                     if "stored" in rec else "")
                  + (f"  span {rec['span'][0]}..{rec['span'][1]}" if rec.get("span") else ""))
        else:
            print(f"  {s:<6} not found  ({len(rec['tried'])} tried, "
                  f"{len(rec['skipped_hosts'])} hosts skipped after failures)")

    corpus.flush_index()
    receipt = corpus.CORPUS / "feeds.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({"at": corpus.utcnow(), "elapsed_s": round(time.time() - t0, 1),
                                   "requests": fetcher.pacer.n_calls, "feeds": feeds}, indent=1),
                       encoding="utf-8")
    found = [s for s, r in feeds.items() if r.get("found")]
    print(f"\nfeeds found {len(found)}/{len(syms)}: {' '.join(found) or 'none'}")
    print(f"not found: {' '.join(s for s in syms if s not in found) or 'none'}")
    print(f"stored {total_new} new, {total_known} known, {total_dropped} entries dropped for no date; "
          f"{fetcher.pacer.n_calls} requests in {time.time() - t0:.0f}s")
    print(f"receipt: {receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
