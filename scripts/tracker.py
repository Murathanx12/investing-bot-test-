"""TRACKER refresh -- rebuild the whole-market watchlist, once a day, and keep it.

    python -m scripts.tracker --refresh                 # the nightly job
    python -m scripts.tracker --refresh --limit 300     # a fast slice
    python -m scripts.tracker --show                    # today's candidate list
    python -m scripts.tracker --sectors                 # top 10 per sector
    python -m scripts.tracker --portfolios              # the three personalities
    python -m scripts.tracker --transitions             # what changed today
    python -m scripts.tracker --publish                 # -> docs/seed/tracker/

WHAT IT FETCHES, AND WHAT EACH COSTS
====================================
    Alpaca  /v2/assets              the tradable universe          1 call
    Alpaca  bars, 200 symbols/call  close, 60d high, 12m return    ~16 calls
    Finnhub /stock/recommendation   analyst counts, ANY name       1 per symbol, 60/min
    Finnhub /stock/profile2         sector + market cap            1 per symbol, CACHED
    yfinance analyst_price_targets  mean/high/low target           1 per symbol, ~0.45s
    corpus  tense == "future"       next dated catalyst            1 read, no network

Sector and market cap are CACHED permanently (`state/tracker/profiles.json`)
because a sector does not change and paying 3,000 calls a night for it would
double the job for nothing. Everything else is re-read daily.

WRITE AS YOU GO
===============
The first version of `analyst_panel` buffered every row and wrote once at the
end, so killing a 40-minute job at minute 38 destroyed 225 completed captures --
which is exactly what happened on its first run. This writes each row the
moment it is complete, and `--refresh` resumes by skipping symbols already in
today's file. A long capture that writes once has no partial credit.

A 429 READS AS ABSENCE
======================
A rate-limited name is not a name without analysts. Every fetch retries with
backoff, and the run reports **coverage by symbol count** -- how many symbols
were asked, answered, refused and errored -- not just how many rows came out.
A row count alone cannot distinguish "3,000 names, 200 covered" from "3,000
names, 2,800 rate-limited".
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from alpha import config, tracker, universe
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal

ROOT = Path(__file__).resolve().parent.parent
STORE = Path(os.getenv("AAT_LEDGER_DIR") or (ROOT / "state")) / "tracker"
SEED = ROOT / "docs" / "seed" / "tracker"
PROFILES = STORE / "profiles.json"
TRANSITIONS = STORE / "transitions.jsonl"
FINNHUB = "https://finnhub.io/api/v1"

#: MEASURED 2026-08-26 in `analyst_panel`: 30 back-to-back profile2 calls with
#: no sleep returned 30x HTTP 200 in 39.7s, so network latency alone paces this
#: at ~45 calls/min, already under the free tier's 60. 0.4s keeps a margin.
FINNHUB_SLEEP_S = 0.4
#: yfinance is unofficial and unrate-limited until it is not. Measured ~0.45s
#: per name warm; a small sleep on top is cheap insurance against a ban that
#: would cost the whole dataset.
YF_SLEEP_S = 0.15


# --------------------------------------------------------------------------- io

def _day() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def path_for(day: str) -> Path:
    return STORE / f"{day}.jsonl"


def load_day(day: str) -> list[dict]:
    p = path_for(day)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue                      # a torn last line from a kill
    return out


def latest_day(before: str | None = None) -> str | None:
    days = sorted(p.stem for p in STORE.glob("*.jsonl") if p.stem != "transitions")
    days = [d for d in days if before is None or d < before]
    return days[-1] if days else None


def load_profiles() -> dict:
    if PROFILES.exists():
        try:
            return json.loads(PROFILES.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_profiles(profiles: dict) -> None:
    STORE.mkdir(parents=True, exist_ok=True)
    PROFILES.write_text(json.dumps(profiles, indent=0, sort_keys=True), encoding="utf-8")


def seed_profiles_from_panel(profiles: dict) -> int:
    """Harvest sector + market cap already paid for by `analyst_panel`.

    1,641 rows of it are sitting in `state/research/analyst_panel/*.jsonl` with
    `industry` and `market_cap_usd` on every one. Re-fetching those from
    Finnhub would be paying twice for a value that does not change.
    """
    panel_dir = ROOT / "state" / "research" / "analyst_panel"
    added = 0
    for f in sorted(panel_dir.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            sym, ind = r.get("symbol"), r.get("industry")
            if sym and ind and sym not in profiles:
                profiles[sym] = {"sector": ind, "market_cap_usd": r.get("market_cap_usd"),
                                 "source": "analyst_panel", "captured": f.stem}
                added += 1
    return added


# --------------------------------------------------------------------- fetching

def _finnhub(path: str, key: str, **kw) -> tuple[object, str]:
    """(payload, status). Status is one of ok / forbidden / ratelimited / error:*."""
    kw["token"] = key
    url = f"{FINNHUB}/{path}?" + urllib.parse.urlencode(kw)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=25) as r:
                return json.load(r), "ok"
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(3 + 3 * attempt)     # back off, do NOT drop the name
                continue
            if e.code == 403:
                return None, "forbidden"
            return None, f"error:HTTP {e.code}"
        except Exception as e:                                          # noqa: BLE001
            return None, f"error:{type(e).__name__}"
    return None, "ratelimited"


def fetch_targets(symbol: str) -> tuple[dict | None, str]:
    """yfinance consensus target. (payload, status).

    NOTE ON VINTAGE: this value carries no date. It is admissible only because
    we stamp `observed_at` at capture and use it strictly afterwards. See the
    module docstring of `alpha/tracker.py` -- it is a forward panel, never a
    backtest source.
    """
    try:
        import yfinance as yf
        pt = yf.Ticker(symbol).analyst_price_targets
    except Exception as e:                                              # noqa: BLE001
        return None, f"error:{type(e).__name__}"
    if not isinstance(pt, dict) or not pt.get("mean"):
        return None, "empty"
    return pt, "ok"


def catalyst_map(as_of: str) -> dict[str, int]:
    """symbol -> calendar days to its next dated catalyst.

    TWO CLOCKS, ONE READ. The backward corpus is bounded at the last closed
    session because a headline published after a decision cannot enter it. A
    FORWARD-dated row asks a different question -- not "had it happened?" but
    "did we know the date?" -- so it is bounded at NOW. Sharing one bound is
    what left `days_to_next_catalyst` empty for every name in the 30 Aug book
    while MU's 21 September earnings date sat in the corpus.

    Units are CALENDAR DAYS, matching `features.daily_features`. The name says
    so and `tracker.CATALYST_MAX_CALENDAR_DAYS` is the bar it is compared to.
    """
    from alpha.sources import corpus
    today = datetime.fromisoformat(as_of).date()
    out: dict[str, int] = {}
    for r in corpus.read(tense="future", as_of=as_of):
        eff = str(r.get("effective_at") or "")[:10]
        if not eff:
            continue
        try:
            d = (datetime.fromisoformat(eff).date() - today).days
        except ValueError:
            continue
        if d < 0:
            continue                          # already happened; not a catalyst
        for s in (r.get("symbols") or []):
            s = str(s).upper()
            if s and (s not in out or d < out[s]):
                out[s] = d
    return out


def stopped_symbols() -> set[str]:
    """Names a live book stopped out of. Feeds the SELL clause.

    Reads the ledger if it is there and returns an empty set if it is not --
    an absent ledger means "no stops recorded", which is different from "no
    stops happened" only in a way that cannot make this rule fire wrongly.
    """
    out: set[str] = set()
    led = Path(os.getenv("AAT_LEDGER_DIR") or (ROOT / "state")) / "ledger.jsonl"
    if not led.exists():
        return out
    try:
        for line in led.read_text(encoding="utf-8").splitlines()[-5000:]:
            if "stop" not in line.lower():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "stop" in str(r.get("reason", "")).lower() and r.get("symbol"):
                out.add(str(r["symbol"]).upper())
    except OSError:
        pass
    return out


# ------------------------------------------------------------------- the refresh

def refresh(*, limit: int | None, skip_targets: bool, day: str | None = None) -> int:
    config.load_env()
    key = os.getenv("AAT_FINNHUB_API_KEY", "").strip()
    if not key:
        print("REFUSED: AAT_FINNHUB_API_KEY is not set. A tracker day that is "
              "missing is recoverable; one built on invented numbers is not.")
        return 1

    day = day or _day()
    STORE.mkdir(parents=True, exist_ok=True)

    members = [m for m in universe.load() if not m.etf_like]
    if not members:
        print("REFUSED: no universe snapshot. Build the universe first.")
        return 1
    # Widest first: if the run is cut short, the names most likely to be
    # tradable are already captured. Ordering is by liquidity, NOT by fame --
    # nothing here scores a name for being large.
    members.sort(key=lambda m: -m.median_dollar_volume)
    if limit:
        members = members[:limit]
    symbols = [m.symbol for m in members]
    by_symbol = {m.symbol: m for m in members}

    done = {r["symbol"] for r in load_day(day)}
    todo = [s for s in symbols if s not in done]
    print(f"universe {len(symbols)} non-ETF names | already captured today {len(done)} "
          f"| to fetch {len(todo)}")

    profiles = load_profiles()
    seeded = seed_profiles_from_panel(profiles)
    if seeded:
        save_profiles(profiles)
        print(f"sector cache seeded with {seeded} names already paid for by analyst_panel "
              f"(cache now {len(profiles)})")

    print("fetching bars in bulk ...")
    client = AlpacaPaper()
    bars: dict[str, list[dict]] = {}
    for i in range(0, len(symbols), 200):
        try:
            bars.update(client.stock_bars_multi(symbols[i:i + 200], start="2025-06-01",
                                                timeframe="1Day"))
        except BrokerRefusal as exc:
            print(f"  bar batch {i}: {exc}")
    print(f"  bars for {len(bars)} of {len(symbols)} symbols")

    now = datetime.now(timezone.utc).isoformat()
    cats = catalyst_map(now)
    print(f"catalyst calendar: {len(cats)} symbols carry a future dated row")

    counters = {"asked": 0, "rec_ok": 0, "rec_forbidden": 0, "rec_ratelimited": 0,
                "rec_error": 0, "target_ok": 0, "target_empty": 0, "target_error": 0,
                "profile_fetched": 0, "no_bars": 0}

    fh = path_for(day).open("a", encoding="utf-8")
    try:
        for i, sym in enumerate(todo, 1):
            counters["asked"] += 1
            m = by_symbol[sym]
            px = tracker.price_stats(bars.get(sym) or [])
            if not px.get("close"):
                counters["no_bars"] += 1

            rec, status = _finnhub("stock/recommendation", key, symbol=sym)
            time.sleep(FINNHUB_SLEEP_S)
            counters[{"ok": "rec_ok", "forbidden": "rec_forbidden",
                      "ratelimited": "rec_ratelimited"}.get(status, "rec_error")] += 1
            periods = sorted(rec or [], key=lambda r: r.get("period", ""), reverse=True)
            counts = periods[0] if periods else None

            if sym not in profiles:
                prof, pstat = _finnhub("stock/profile2", key, symbol=sym)
                time.sleep(FINNHUB_SLEEP_S)
                if pstat == "ok" and isinstance(prof, dict):
                    cap = prof.get("marketCapitalization")
                    profiles[sym] = {"sector": prof.get("finnhubIndustry"),
                                     "market_cap_usd": float(cap) * 1e6 if cap else None,
                                     "source": "finnhub", "captured": day}
                    counters["profile_fetched"] += 1

            targets, tstat = (None, "skipped")
            if not skip_targets:
                targets, tstat = fetch_targets(sym)
                time.sleep(YF_SLEEP_S)
                counters[{"ok": "target_ok", "empty": "target_empty"}
                         .get(tstat, "target_error")] += 1

            row = {
                "symbol": sym, "day": day, "observed_at": now,
                "close": px.get("close"), "high_60d": px.get("high_60d"),
                "ret_12m": px.get("ret_12m"), "sessions": px.get("sessions"),
                "rec_counts": ({k: counts.get(k) for k in
                                ("strongBuy", "buy", "hold", "sell", "strongSell")}
                               if counts else None),
                "rec_period": (counts or {}).get("period"),
                "rec_status": status,
                "mean_target": (targets or {}).get("mean"),
                "target_high": (targets or {}).get("high"),
                "target_low": (targets or {}).get("low"),
                "target_status": tstat,
                "target_source": "yfinance:analyst_price_targets",
                "sector": (profiles.get(sym) or {}).get("sector"),
                "market_cap_usd": (profiles.get(sym) or {}).get("market_cap_usd"),
                "days_to_catalyst": cats.get(sym),
                "days_to_catalyst_units": "calendar_days",
                "dv_bucket": m.dv_bucket, "exchange": m.exchange,
                "median_dollar_volume": m.median_dollar_volume,
                "tradable": True, "shortable": m.shortable,
            }
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            if i % 50 == 0 or i == len(todo):
                save_profiles(profiles)
                print(f"  [{i}/{len(todo)}] {sym:6s} rec={status:6s} "
                      f"tgt={tstat:8s} cov={sum((counts or {}).get(k) or 0 for k in ('strongBuy','buy','hold','sell','strongSell'))}",
                      flush=True)
    finally:
        fh.close()
        save_profiles(profiles)

    print("\nCOVERAGE BY SYMBOL COUNT (a row count cannot tell absence from a 429):")
    for k, v in counters.items():
        print(f"  {k:20s} {v}")
    return grade_and_write(day)


def grade_and_write(day: str) -> int:
    """Derive every computed column, label, log transitions, write latest.json."""
    raw = load_day(day)
    if not raw:
        print("no rows for today")
        return 1
    rows = tracker.build_rows(raw)

    prev_day = latest_day(before=day)
    prev = {r["symbol"]: r for r in load_day(prev_day)} if prev_day else {}
    hist = tracker.apply_status(rows, prev_by_symbol=prev, stopped_symbols=stopped_symbols())
    trans = tracker.transitions(rows, prev, day=day)

    pw = tracker.mark_past_winners(rows)      # already run inside build_rows; re-read summary
    summary = tracker.summary(rows, day=day, hist=hist, pw=pw)
    summary["previous_day"] = prev_day
    summary["n_transitions"] = len(trans)

    STORE.mkdir(parents=True, exist_ok=True)
    (STORE / "latest.json").write_text(json.dumps({
        "summary": summary,
        "candidates": tracker.candidates(rows),
    }, indent=1, default=str), encoding="utf-8")
    if trans:
        with TRANSITIONS.open("a", encoding="utf-8") as f:
            for t in trans:
                f.write(json.dumps(t, default=str) + "\n")

    print(f"\n{len(rows)} rows | statuses {hist} | {summary['n_candidates']} candidates "
          f"| {len(trans)} transitions vs {prev_day or 'nothing'}")
    print(f"past winners flagged: {summary['n_past_winners']} "
          f"({pw['judged_against_sector']} vs own sector, {pw['judged_against_market']} vs market, "
          f"{pw['not_judged_no_history']} no 12m history)")
    return 0


def backfill_prices(day: str | None = None) -> int:
    """Recompute every PRICE column on a day's rows from one bulk bar fetch.

    A row's price columns are derived, not observed: given the bars, `close`,
    `high_60d`, `ret_12m` and `realised_vol_20d` are all recoverable. So when
    the derivation gains a column -- as it did when the book's scorer turned
    out to need `realised_vol_20d` to produce a magnitude at all -- the fix is
    to re-derive, not to re-fetch 3,000 analyst rows that have not changed.

    Only the price columns are touched. Analyst counts and targets are
    OBSERVATIONS with a capture stamp and are never recomputed: rewriting one
    would silently change what we recorded having known, which is the one thing
    an append-only panel exists to prevent.
    """
    config.load_env()
    day = day or latest_day() or _day()
    rows = load_day(day)
    if not rows:
        print(f"no tracker rows for {day}")
        return 1
    syms = [r["symbol"] for r in rows]
    client = AlpacaPaper()
    bars: dict[str, list[dict]] = {}
    for i in range(0, len(syms), 200):
        try:
            bars.update(client.stock_bars_multi(syms[i:i + 200], start="2025-06-01",
                                                timeframe="1Day"))
        except BrokerRefusal as exc:
            print(f"  bar batch {i}: {exc}")
    # CONCURRENCY. The nightly refresh APPENDS to this same file for over an
    # hour. This function rewrites it wholesale, so any row appended between the
    # read above and the replace below would be silently destroyed -- and a
    # capture that is gone is not recoverable, which is the whole reason the
    # refresh writes as it goes. So the line count is re-read immediately before
    # the swap and the swap is ABANDONED if the file grew. Refusing costs one
    # re-run; the alternative costs rows nobody knows are missing.
    n_before = sum(1 for _ in path_for(day).open(encoding="utf-8"))
    patched = 0
    tmp = path_for(day).with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in rows:
            px = tracker.price_stats(bars.get(r["symbol"]) or [])
            if px.get("close"):
                before = r.get("realised_vol_20d")
                r.update({k: px.get(k) for k in
                          ("close", "high_60d", "ret_12m", "realised_vol_20d", "sessions")})
                if before is None and r.get("realised_vol_20d") is not None:
                    patched += 1
            f.write(json.dumps(r) + "\n")
    n_after = sum(1 for _ in path_for(day).open(encoding="utf-8"))
    if n_after != n_before:
        tmp.unlink(missing_ok=True)
        print(f"REFUSED: {path_for(day).name} grew from {n_before} to {n_after} lines while this "
              "ran -- a refresh is appending to it. Rewriting now would delete the rows it "
              "added. Nothing was changed; re-run once the refresh has finished.")
        return 1
    try:
        tmp.replace(path_for(day))
    except PermissionError:
        # Windows refuses to replace a file another process holds open. That is
        # the same protection the line-count check above gives, enforced by the
        # OS a moment later -- report it as the refusal it is, not as a crash.
        tmp.unlink(missing_ok=True)
        print(f"REFUSED: {path_for(day).name} is held open by another process (the refresh is "
              "still appending). Nothing was changed; re-run once it has finished.")
        return 1
    print(f"re-derived price columns on {len(rows)} rows; {patched} gained realised_vol_20d")
    return grade_and_write(day)


# ------------------------------------------------------------------------ views

def _fmt(v, pct=False, nd=2):
    if v is None:
        return "  --  "
    return f"{v:+.1%}" if pct else f"{v:.{nd}f}"


def show(day: str | None = None, n: int = 40) -> int:
    day = day or latest_day() or _day()
    rows = tracker.build_rows(load_day(day))
    if not rows:
        print(f"no tracker rows for {day}")
        return 1
    prev_day = latest_day(before=day)
    prev = {r["symbol"]: r for r in load_day(prev_day)} if prev_day else {}
    hist = tracker.apply_status(rows, prev_by_symbol=prev)
    cands = tracker.candidates(rows)
    print(f"TRACKER {day} -- {len(rows)} names, {len(cands)} candidates")
    print(f"statuses: {hist}\n")
    print(f"{'symbol':8s}{'status':11s}{'upside':>9s}{'cons':>6s}{'cov':>5s}"
          f"{'bucket':>8s}{'ret12m':>9s}{'dd60':>8s}{'cat':>5s}  sector")
    for r in cands[:n]:
        print(f"{r['symbol']:8s}{r.get('status',''):11s}{_fmt(r.get('upside'),1):>9s}"
              f"{_fmt(r.get('consensus')):>6s}{str(r.get('coverage') or ''):>5s}"
              f"{str(r.get('coverage_bucket') or '--'):>8s}{_fmt(r.get('ret_12m'),1):>9s}"
              f"{_fmt(r.get('drawdown_60d'),1):>8s}"
              f"{str(r.get('days_to_catalyst') if r.get('days_to_catalyst') is not None else '--'):>5s}"
              f"  {r.get('sector') or '--'}")
    print("\nclaims by coverage bucket (Murat's thin-coverage hypothesis, as a question):")
    for b, d in tracker.coverage_split(rows, "status").items():
        cand = sum(d.get(s, 0) for s in tracker.CANDIDATE_STATUSES)
        tot = sum(d.values())
        print(f"  {b:6s} {cand:4d} candidates of {tot:5d} names ({100*cand/max(1,tot):4.1f}%)")
    return 0


def sectors(day: str | None = None, n: int = 10) -> int:
    day = day or latest_day() or _day()
    rows = tracker.build_rows(load_day(day))
    if not rows:
        print(f"no tracker rows for {day}")
        return 1
    prev_day = latest_day(before=day)
    tracker.apply_status(rows, prev_by_symbol={r["symbol"]: r for r in load_day(prev_day)}
                         if prev_day else {})
    top = tracker.sector_top(rows, n=n)
    print(f"TRACKER {day} -- top {n} candidates per sector, by upside\n")
    for sec, names in top.items():
        print(f"{sec} ({len(names)})")
        for r in names:
            print(f"   {r['symbol']:8s}{_fmt(r.get('upside'),1):>9s} upside  "
                  f"cons {_fmt(r.get('consensus'))}  cov {r.get('coverage')} "
                  f"({r.get('coverage_bucket')})  {r.get('status')}")
    return 0


def merge_book_numbers(rows: list[dict], day: str) -> tuple[int, str]:
    """Join the sealed book's per-name numbers onto the tracker rows.

    THE CHAIN. The tracker says WHICH names are candidates; the sealed book says
    what each one is worth (`p_up`, `exp_return`, `downside_5pct`,
    `confidence`). Two of the three personalities rank on the book's numbers, so
    without this join they correctly select nothing -- which is what "no
    risk_adjusted value" meant, and is the right refusal rather than a zero.

    Reads the SEAL, never re-derives. Same reason `alpha/brains/murat_rule.py`
    does: what trades has to be what was written down before the open, and a
    recompute at 16:00 can drift from a 09:15 book invisibly.
    """
    from alpha.brains import murat_rule as _brain

    # `_book_for` returns the LOADED book (newest for the day, reseals included),
    # not a path.
    book = _brain._book_for(day)
    if not book:
        return 0, (f"no sealed book for {day}. Seal one over the tracker first:\n"
                   "  python -m scripts.prediction_book --seal --universe tracker")
    # A book carries ONE ROW PER SYMBOL PER GENERATOR, and only the rule
    # generator produces `exp_return` / `downside_5pct` / `confidence`. Taking
    # the first row per symbol takes `event_counts_v1`, which carries none of
    # them -- so the join "succeeds" for every name and delivers nothing, and
    # the portfolios then correctly report "no risk_adjusted value" for a pool
    # that was in fact fully joined. Prefer the row that has the numbers.
    NUMBERS = ("p_up_21d", "exp_return", "downside_5pct", "confidence")
    by_sym: dict[str, dict] = {}
    for p in book.get("predictions", []):
        sym = p.get("symbol")
        if not sym:
            continue
        if sym not in by_sym or any(p.get(k) is not None for k in NUMBERS):
            by_sym[sym] = p
    n = 0
    for r in rows:
        p = by_sym.get(r["symbol"])
        if not p:
            continue
        for k in NUMBERS:
            if p.get(k) is not None:
                r[k] = p[k]
        n += 1
    return n, (f"joined {n} names from the sealed book for {book.get('day')} "
               f"(sha {book.get('content_sha256','')[:12]}, "
               f"generators {book.get('generators')})")


def portfolios(day: str | None = None) -> int:
    """The three personalities, each with its worst case printed."""
    day = day or latest_day() or _day()
    rows = tracker.build_rows(load_day(day))
    if not rows:
        print(f"no tracker rows for {day}")
        return 1
    prev_day = latest_day(before=day)
    tracker.apply_status(rows, prev_by_symbol={r["symbol"]: r for r in load_day(prev_day)}
                         if prev_day else {})
    _n, note = merge_book_numbers(rows, day)
    print(f"  book: {note}\n")
    print(f"TRACKER {day} -- three personalities over one candidate list\n")
    for p in tracker.PERSONALITIES:
        port = tracker.build_portfolio(rows, p)
        gross_cap, stop, profile = _limits_for(p.book)
        wc = tracker.worst_case(n=port["n_selected"], notional_each=p.max_notional,
                                stop_fraction=stop, gross_cap=gross_cap)
        print(f"{p.book}  {p.name.upper():13s} rank={p.rank}  profile={profile}")
        print(f"  pool {port['candidate_pool']} -> eligible {port['eligible']} -> "
              f"selected {port['n_selected']}/{p.k}")
        for h in port["holdings"]:
            print(f"    {h['symbol']:8s} {h['notional']:.1%}  {h['sector'] or '--'}"
                  f"   rank {h['rank_value']:+.4f}")
        if port["excluded_by_reason"]:
            print(f"  excluded: {port['excluded_by_reason']}")
        print(f"  WORST CASE {wc['worst_case_pct']}  "
              f"(gross {wc['gross']:.0%} of a {wc['gross_cap']:.0%} cap, binding on "
              f"{wc['binding']}, stop {wc['stop_fraction']:.0%})\n")
    return 0


def _limits_for(book: str) -> tuple[float, float, str]:
    """(gross cap, stop fraction, profile) DERIVED from the live code.

    Every leg is read from the module that ENFORCES it -- the risk profile from
    `fleet.MANDATES`, the cap from `engine.sizing.gross_cap`, the stop from
    `engine.equity.stop_fraction`. Nothing here is typed by hand.

    That matters more than it looks. hack4 runs the `maximum` profile, whose
    gross cap is 1.50x, not the 1.00x every other book uses; a worst case that
    assumed "basket" for all three would understate hack4's bound by half and
    still print a confident percentage. And a number retyped beside the code
    that enforces it goes stale silently -- `monday_gate_check` reported 0/9
    for weeks because it could not read its own input and so returned a
    constant. A guard derives its inputs or refuses.
    """
    from alpha import fleet
    from alpha.engine import equity as _equity
    from alpha.engine import sizing as _sizing

    registry = getattr(fleet, "FLEET", None) or getattr(fleet, "MANDATES", {})
    mandate = registry.get(book)
    if mandate is None or not getattr(mandate, "profile", None):
        raise SystemExit(f"REFUSED: no risk profile readable for {book} in fleet.FLEET. "
                         "A worst case must be derived, not asserted.")
    profile = mandate.profile
    return float(_sizing.gross_cap(profile)), float(_equity.stop_fraction(profile)), profile


def show_transitions(day: str | None = None) -> int:
    day = day or latest_day() or _day()
    if not TRANSITIONS.exists():
        print("no transitions logged yet")
        return 0
    rows = [json.loads(line) for line in
            TRANSITIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
    todays = [r for r in rows if r.get("day") == day]
    print(f"TRANSITIONS {day} -- {len(todays)} of {len(rows)} logged in total\n")
    for r in todays[:80]:
        print(f"  {r['symbol']:8s} {str(r.get('from')):10s} -> {str(r.get('to')):10s}  "
              f"upside {_fmt(r.get('upside'),1)}  cons {_fmt(r.get('consensus'))}  "
              f"{'; '.join(r.get('reasons') or r.get('blocked_by') or [])[:80]}")
    return 0


def publish(day: str | None = None) -> int:
    """Copy the candidate list to `docs/seed/tracker/` so the container can read it.

    `AAT_LEDGER_DIR=/app/state` is a mounted VOLUME on Railway and a volume
    SHADOWS whatever the image holds at that path -- so a tracker written on
    the laptop and committed under `state/` is invisible to the running loop.
    `docs/seed/` is not shadowed. Same reason, same fix as
    `prediction_book --publish`.
    """
    day = day or latest_day() or _day()
    rows = tracker.build_rows(load_day(day))
    if not rows:
        print(f"no tracker rows for {day}")
        return 1
    prev_day = latest_day(before=day)
    hist = tracker.apply_status(rows, prev_by_symbol={r["symbol"]: r for r in load_day(prev_day)}
                                if prev_day else {})
    SEED.mkdir(parents=True, exist_ok=True)
    out = SEED / f"{day}.json"
    out.write_text(json.dumps({
        "schema": tracker.SCHEMA, "day": day,
        "published_utc": datetime.now(timezone.utc).isoformat(),
        "status_histogram": hist,
        "candidates": tracker.candidates(rows),
    }, indent=1, default=str), encoding="utf-8")
    print(f"published {sum(hist.get(s,0) for s in tracker.CANDIDATE_STATUSES)} candidates -> {out}")
    print("commit docs/seed/tracker and push for the loop to see it.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--refresh", action="store_true", help="fetch and rebuild today's rows")
    p.add_argument("--regrade", action="store_true", help="re-derive labels from today's fetched rows")
    p.add_argument("--backfill-prices", action="store_true",
                   help="re-derive price columns (incl. realised_vol_20d) from one bulk bar fetch")
    p.add_argument("--show", action="store_true")
    p.add_argument("--sectors", action="store_true")
    p.add_argument("--portfolios", action="store_true")
    p.add_argument("--transitions", action="store_true")
    p.add_argument("--publish", action="store_true")
    p.add_argument("--limit", type=int, default=None, help="cap the symbol count")
    p.add_argument("--day", default=None)
    p.add_argument("--n", type=int, default=40)
    p.add_argument("--skip-targets", action="store_true",
                   help="skip yfinance (Finnhub only -- upside will be unreadable)")
    a = p.parse_args(argv)

    if a.refresh:
        return refresh(limit=a.limit, skip_targets=a.skip_targets, day=a.day)
    if a.backfill_prices:
        return backfill_prices(a.day)
    if a.regrade:
        return grade_and_write(a.day or _day())
    if a.sectors:
        return sectors(a.day, a.n)
    if a.portfolios:
        return portfolios(a.day)
    if a.transitions:
        return show_transitions(a.day)
    if a.publish:
        return publish(a.day)
    return show(a.day, a.n)


if __name__ == "__main__":
    sys.exit(main())
