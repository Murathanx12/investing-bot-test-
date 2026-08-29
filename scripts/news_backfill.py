"""NEWS_BACKFILL -- give the engine a MEMORY: up to a year of past news per name.

    python -m scripts.news_backfill --months 12                 # the tradeable universe
    python -m scripts.news_backfill --months 12 --murat         # Murat's twenty names
    python -m scripts.news_backfill --months 6 --symbols SLDP KYTX AARD
    python -m scripts.news_backfill --months 12 --universe fleet --no-finnhub
                                     # the ~160-name fleet universe, Alpaca batch only
    python -m scripts.news_backfill --stats                     # what the corpus holds

WHY (measured, 2026-08-29)
==========================
The Featherless digest read 394 headlines over 156 names and gave **none of
Murat's twenty names a bet**, because the only news source in the pipe was
Alpaca/Benzinga over a 48-hour window, and Benzinga had not written about
SLDP, KYTX or AARD that week. The engine could not have known that AARD is on
a clinical hold with unblinded data due in Q3 -- the fact is nine months old
and the window was two days.

This script fills `alpha.sources.corpus` backwards. It is FETCH ONLY: no LLM
call happens here (that is `scripts.corpus_digest`), because a collector that
also interprets is a collector whose bug every consumer inherits.

THREE SOURCES, AND WHY THE SECOND ONE IS THE POINT
==================================================
- **Alpaca/Benzinga** (`/v1beta1/news`) -- deep and fast for names a US wire
  covers, paged month by month. This is what we already had.
- **Finnhub `company-news`** -- one year, PER SYMBOL, and it covers the small
  biotech and small-cap names Benzinga ignores. **This is the fix for the
  coverage gap**: it is asked per name rather than per wire, so a name with no
  wire coverage still gets its own history instead of silently getting none.
- **SEC EDGAR** -- 8-K/10-Q press releases. The issuer speaking directly, so
  `independence_group` is the issuer and a wire restating it is not a second
  witness.

RATE LIMITS ARE MEASURED, NOT ASSUMED
=====================================
Finnhub free tier is 60 calls/minute; one call per symbol-month would be 240
calls for 20 names over a year, so the loop is per symbol-YEAR where the API
allows a range, with a pause. Alpaca news allows 50/page with a `next_page_token`
and is paged until exhausted or `--max-pages`.

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
import time
from datetime import datetime, timedelta, timezone

from alpha import config, fleet
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal
from alpha.sources import corpus, finnhub
from alpha.sources.http import SourceRefusal

#: Murat's own list (roadmap §3, reconstructed from four PDFs). These are the
#: names the 48-hour pipe structurally cannot see, so they are the acceptance
#: test for this script: after a run, every one of them must have rows.
MURAT_NAMES = ["SLDP", "DKNG", "HUBS", "BHVN", "AMSC", "KYTX", "PRCH", "NTLA",
               "ABSI", "QUBT", "AARD", "SOC", "TSM", "MU", "MRVL", "AMD",
               "SRRK", "OLMA", "SLNO", "BEAM"]

FINNHUB_PAUSE_S = 1.1          # 60/min free tier, with headroom
ALPACA_PAGE_LIMIT = 50

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
    syms: set[str] = set()
    if args.symbols:
        syms.update(s.upper() for s in args.symbols)
    if args.murat or getattr(args, "universe", None) == "murat":
        syms.update(MURAT_NAMES)
    if getattr(args, "universe", None) == "fleet":
        syms.update(wide_universe())
    if not syms:
        syms.update({"SPY", "QQQ", "IWM"})
        try:
            syms.update(fleet.theme_symbols())
        except Exception:                                               # noqa: BLE001
            pass
        syms.update(MURAT_NAMES)
    return sorted(syms)


def alpaca_history(client, symbols: list[str], start: str, end: str,
                   *, max_pages: int = 40) -> tuple[list[corpus.Observation], list[str]]:
    """Every Benzinga item for these symbols in [start, end), paged."""
    obs: list[corpus.Observation] = []
    refusals: list[str] = []
    for i in range(0, len(symbols), 20):
        batch = symbols[i:i + 20]
        token, pages = None, 0
        while pages < max_pages:
            params = {"symbols": ",".join(batch), "limit": ALPACA_PAGE_LIMIT, "sort": "desc",
                      "start": f"{start}T00:00:00Z", "end": f"{end}T00:00:00Z"}
            if token:
                params["page_token"] = token
            try:
                d = client._request("GET", "/v1beta1/news", base=config.data_url(), params=params)
            except BrokerRefusal as exc:
                refusals.append(f"alpaca {batch[0]}..{batch[-1]} {start}: {str(exc)[:90]}")
                break
            items = (d or {}).get("news") or []
            for n in items:
                at = n.get("created_at") or n.get("updated_at")
                if not at:
                    # An item with no timestamp is not an observation. Inventing
                    # one at the start of the month is a PIT leak in the
                    # direction that flatters every number (2026-08-29 review).
                    refusals.append(f"alpaca {batch[0]}..{batch[-1]} {start}: item without timestamp dropped")
                    continue
                syms = tuple(s.upper() for s in (n.get("symbols") or []) if s.upper() in set(batch))
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=12, help="how far back (default 12)")
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--murat", action="store_true", help="Murat's twenty names")
    ap.add_argument("--universe", choices=("default", "murat", "fleet"), default="default",
                    help="fleet = MURAT_NAMES + theme basket + window universe (~160 names)")
    ap.add_argument("--no-alpaca", action="store_true")
    ap.add_argument("--no-finnhub", action="store_true")
    ap.add_argument("--max-pages", type=int, default=40)
    ap.add_argument("--role", default=None,
                    help="account whose keys read the NEWS endpoint (default: env, else hack1)")
    ap.add_argument("--stats", action="store_true", help="print corpus stats and exit")
    args = ap.parse_args()
    config.load_env()

    if args.stats:
        print(json.dumps(corpus.stats(), indent=1))
        return 0

    today = datetime.now(timezone.utc).date()
    start = (today - timedelta(days=31 * args.months)).replace(day=1).isoformat()
    end = (today + timedelta(days=1)).isoformat()
    syms = _universe(args)
    print(f"backfill {len(syms)} names, {start} -> {end} ({args.months} months)")

    stored, dup, refusals = 0, 0, []
    #: items SEEN per symbol per month (before dedupe) -- the coverage table.
    seen: dict[str, dict[str, int]] = {s: {} for s in syms}

    if not args.no_alpaca:
        # `/v1beta1/news` is the MARKET DATA host. It reads; it cannot place an
        # order, and the row it returns is identical whichever account asks. So
        # a role is needed here only to pick a key pair, and defaulting it does
        # not risk the thing `config.role()` refuses to risk (an unset variable
        # silently selecting the JUDGED account for an ORDER). It is named on
        # the receipt anyway, because "which credentials fetched this" is
        # provenance and provenance is the point of the corpus.
        news_role = (args.role or os.getenv("AAT_ACCOUNT_ROLE", "").strip() or "hack1").lower()
        client = AlpacaPaper(role=news_role)
        print(f"  (news read with role {news_role!r} -- data endpoint, places nothing)")
        for m0, m1 in corpus.iter_months(start, end):
            obs, refs = alpaca_history(client, syms, m0, min(m1, end), max_pages=args.max_pages)
            for o in obs:
                for s_ in o.symbols:
                    seen.setdefault(s_, {})[m0[:7]] = seen.setdefault(s_, {}).get(m0[:7], 0) + 1
            n, d = corpus.append_many(obs)
            stored += n
            dup += d
            refusals += refs
            print(f"  alpaca {m0[:7]}: {len(obs):>5} items  (+{n} new, {d} known)")

    if not args.no_finnhub:
        for j, sym in enumerate(syms):
            if j:
                time.sleep(FINNHUB_PAUSE_S)
            got, refs, months_ok = [], [], 0
            # Finnhub caps a company-news range; ask month by month so a
            # silent truncation cannot masquerade as "this name had no news".
            # The pause is 1.1s BETWEEN MONTHS as well as between symbols: the
            # first run paused 0.25s here, which is ~4 calls/second against a
            # 60/minute limit, and it rate-limited 31 windows.
            all_months = list(corpus.iter_months(start, end))
            for m0, m1 in all_months:
                o, r = finnhub_history(sym, m0, min(m1, end))
                got += o
                refs += r
                if not r:
                    months_ok += 1
                time.sleep(FINNHUB_PAUSE_S)
            for o in got:
                seen.setdefault(sym, {})[o.effective_at[:7]] = seen.setdefault(sym, {}).get(o.effective_at[:7], 0) + 1
            n, d = corpus.append_many(got)
            stored += n
            dup += d
            refusals += refs
            # MONTHS COVERED, not just items found. "0 items over 12/12 months"
            # is a quiet company; "0 items over 4/12 months" is a hole in the
            # record, and the two must never print the same way.
            gap = "" if months_ok == len(all_months) else f"  MONTHS {months_ok}/{len(all_months)}"
            print(f"  finnhub {sym:<6}: {len(got):>5} items  (+{n} new, {d} known)"
                  + gap + (f"  REFUSALS {len(refs)}" if refs else ""))

    corpus.flush_index()
    st = corpus.stats()
    cov = corpus.symbols_covered()
    missing = [s for s in syms if cov.get(s, 0) == 0]
    print(f"\nstored {stored} new, {dup} already known")
    print(f"corpus: {st['n_observations']} observations, {st['n_symbols']} symbols, span {st['effective_span']}")
    if missing:
        # THE COVERAGE GAP, NAMED. A name with zero rows after a year-long
        # backfill is a name the engine is structurally blind to, and saying so
        # is the finding -- an empty result that prints nothing reads as success.
        print(f"NO COVERAGE ({len(missing)}): {' '.join(missing)}")
    if refusals:
        print(f"refusals ({len(refusals)}): " + "; ".join(refusals[:6]))

    if args.universe == "fleet" or len(syms) > 40:
        # COVERAGE PER SYMBOL AS ITEMS/MONTH. A wide batch backfill returns one
        # number per page and nothing per name; the names that got NOTHING are
        # the finding, and a total that averages NVDA's thousands over them
        # hides it. Every name prints, thin ones are listed by name.
        months = [m0[:7] for m0, _ in corpus.iter_months(start, end)]
        n_months = max(1, len(months))
        thin: list[str] = []
        print(f"\ncoverage this run (items seen / month, {n_months} months):")
        for s_ in syms:
            per = seen.get(s_, {})
            total = sum(per.values())
            covered = sum(1 for m in months if per.get(m, 0) > 0)
            if total < THIN_ITEMS:
                thin.append(s_)
            print(f"  {s_:<6} {total:>6} items  {total / n_months:>6.1f}/mo  months with any {covered:>2}/{n_months}")
        print(f"\nTHIN (< {THIN_ITEMS} items this run, {len(thin)}/{len(syms)}): "
              + (" ".join(thin) if thin else "none"))
        receipt = corpus.CORPUS / f"news_backfill_coverage_{today.isoformat()}.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps({"at": corpus.utcnow(), "start": start, "end": end,
                                       "universe": args.universe, "n_symbols": len(syms),
                                       "alpaca": not args.no_alpaca, "finnhub": not args.no_finnhub,
                                       "seen": seen, "thin": thin, "refusals": refusals},
                                      indent=1), encoding="utf-8")
        print(f"receipt: {receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
