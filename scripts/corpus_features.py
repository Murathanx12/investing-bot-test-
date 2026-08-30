"""Build the NEWS->NUMBERS panel from the corpus, and ask whether any of it led a return.

    python -m scripts.corpus_features                       # build, default symbols
    python -m scripts.corpus_features --symbols NTLA SLDP --since 2025-09-01
    python -m scripts.corpus_features --ic                  # rank IC vs forward returns
    python -m scripts.corpus_features --no-embed            # TF-IDF novelty, no NVIDIA call

WHAT IT WRITES
==============
    state/corpus/features/<SYMBOL>.jsonl     one row per TRADING day (bar date)
    state/corpus/features/bars_<SYMBOL>.json Alpaca daily bars, cached per symbol
    state/corpus/features/embed_<model>.npz  title vectors, keyed by title hash
    state/corpus/features/ic_<date>.json     the IC table and its receipt

POINT IN TIME
=============
`alpha.sources.features.daily_features` filters on `observed_at <= day 23:59Z`
itself; this script passes it everything and never pre-filters by date, so
there is exactly one place the bound lives. Forward returns are the ONLY thing
here that reads past `day`, and they are computed in `--ic` from bars alone:
entry at the OPEN of session t+1, exit at the CLOSE of session t+h (h = 5 or
21 sessions after t). "SPY-relative" subtracts SPY's return over the identical
sessions. A signal that needs the close of t cannot trade the close of t
(Alpaca rejects `cls` after 15:50 ET), so t+1 open is the honest entry.

BARS END YESTERDAY
==================
The free SIP plan refuses `end` inside the last 15 minutes ("subscription does
not permit querying recent SIP data"), so the cache ends at the previous
calendar day and the last feature row is yesterday's. That is a fact about the
data plan, printed rather than papered over with the IEX feed (whose volume
is 2-4% of consolidated -- see `stock_bars_multi`).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from alpha import config
from alpha import exits as _exits
from alpha.sources import corpus, features
from scripts.news_backfill import MURAT_NAMES

ROOT = Path(__file__).resolve().parent.parent
OUT = corpus.CORPUS / "features"
BENCH = "SPY"
HORIZONS = (5, 21)
HISTORY_DAYS = 200          # corpus/bars history loaded BEFORE --since, for baselines and 60-bar context


def default_symbols() -> list[str]:
    return sorted(set(MURAT_NAMES) | {"SPY", "QQQ", "IWM"})


def corpus_symbols(min_rows: int = 20) -> list[str]:
    """Every symbol the corpus actually has news for, plus the benchmarks.

    WHY THIS EXISTS (2026-08-30). The panel was built on 23 symbols while the
    corpus carried news for 156, and the gap decided what could be asked:

      * T6 (Murat's rule cells) had 1,226 symbol-days passing target-ratio AND
        drawdown -- across seventeen names, which is not a cross-section.
      * T3 (sector lead/laggard) needs THREE names in one declared driver in the
        same week. On 23 symbols the only groups that big were `murat_book`
        (a bag of picks, not a mechanism), `UNCLASSIFIED` (by definition not a
        driver) and `index_beta` (the market). Every real theme had ONE name, so
        the question could not be asked at all.

    `min_rows` keeps out names with a handful of stray headlines, whose
    `coverage_baseline_90d` would be noise and whose attention_z would then be
    an artefact of the denominator.
    """
    counts = corpus.symbols_covered(kinds=["news"])
    syms = {s.upper() for s, n in counts.items() if n >= min_rows}
    return sorted(syms | {"SPY", "QQQ", "IWM"})


# ----------------------------------------------------------------------- bars


def bars_path(sym: str) -> Path:
    return OUT / f"bars_{sym}.json"


def load_bars(symbols: list[str], *, start: str, end: str, refresh: bool) -> tuple[dict[str, list[dict]], list[str]]:
    """Daily bars per symbol, one venue call per symbol, cached. (bars, notes)."""
    out: dict[str, list[dict]] = {}
    notes: list[str] = []
    need = []
    for s in symbols:
        p = bars_path(s)
        if p.exists() and not refresh:
            blob = json.loads(p.read_text(encoding="utf-8"))
            if blob.get("start", "9999") <= start and blob.get("end", "") >= end:
                out[s] = blob["bars"]
                continue
        need.append(s)
    if need:
        if config.test_mode():
            notes.append(f"AAT_TEST_MODE: {len(need)} symbols have no cached bars and will not be fetched")
            return out, notes
        from alpha.broker.alpaca import AlpacaPaper
        client = AlpacaPaper()
        OUT.mkdir(parents=True, exist_ok=True)
        for s in need:
            t0 = time.time()
            got = client.stock_bars_multi([s], start=start, end=end).get(s) or []
            bars_path(s).write_text(json.dumps({"symbol": s, "start": start, "end": end,
                                                "feed": "sip", "adjustment": "all",
                                                "fetched_utc": corpus.utcnow(), "bars": got}),
                                    encoding="utf-8")
            out[s] = got
            notes.append(f"bars {s}: {len(got)} rows in {time.time() - t0:.1f}s")
    return out, notes


# ---------------------------------------------------------------- analyst panel


def load_panel() -> list[tuple[str, dict[str, dict]]]:
    """[(file_date, {symbol: latest rec_period})], oldest first."""
    root = ROOT / "state" / "research" / "analyst_panel"
    out = []
    for p in sorted(root.glob("*.jsonl")) if root.exists() else []:
        by: dict[str, dict] = {}
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            periods = row.get("rec_periods") or []
            if periods:
                by[str(row.get("symbol") or "").upper()] = periods[0]
        out.append((p.stem, by))
    return out


def panel_rec(panel: list[tuple[str, dict]], sym: str, day: str) -> dict | None:
    rec = None
    for fdate, by in panel:
        if fdate <= day and sym in by:
            rec = by[sym]
    return rec


# ------------------------------------------------------------------ embeddings


def embed_cache_path(model: str) -> Path:
    safe = model.replace("/", "__")
    return OUT / f"embed_{safe}.npz"


def load_embed_cache(model: str) -> dict[str, np.ndarray]:
    p = embed_cache_path(model)
    if not p.exists():
        return {}
    z = np.load(p)
    return {k: v for k, v in zip(z["keys"].tolist(), z["vecs"])}


def save_embed_cache(model: str, cache: dict[str, np.ndarray]) -> None:
    if not cache:
        return
    OUT.mkdir(parents=True, exist_ok=True)
    keys = list(cache)
    np.savez_compressed(embed_cache_path(model), keys=np.array(keys),
                        vecs=np.stack([cache[k] for k in keys]).astype(np.float16))


def choose_embedder(no_embed: bool) -> tuple[features.Embedder, str]:
    if no_embed or config.test_mode():
        return features.Embedder.tfidf(), "tfidf (requested or test mode)"
    try:
        emb = features.Embedder.nvidia()
    except RuntimeError as exc:
        return features.Embedder.tfidf(), f"tfidf (nvidia unavailable: {exc})"
    if emb.probe():
        return emb, f"nvidia {emb.model}"
    return features.Embedder.tfidf(), f"tfidf (nvidia {emb.model} did not answer the probe)"


# ---------------------------------------------------------------------- build


def build(symbols: list[str], *, since: str, until: str, no_embed: bool, refresh_bars: bool) -> dict:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    hist_start = (date.fromisoformat(since) - timedelta(days=HISTORY_DAYS)).isoformat()
    bars, notes = load_bars(symbols, start=hist_start, end=until, refresh=refresh_bars)
    for n in notes:
        print("  " + n)

    rows = corpus.read(since=hist_start, symbols=symbols)
    by_sym: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        for s in r.get("symbols") or []:
            if s.upper() in symbols:
                by_sym[s.upper()].append(r)
    print(f"  corpus: {len(rows)} rows since {hist_start} across {len(by_sym)} of {len(symbols)} symbols")

    panel = load_panel()
    embedder, embed_note = choose_embedder(no_embed)
    print(f"  novelty vectors: {embed_note}")
    cache = load_embed_cache(embedder.model) if embedder.backend == "nvidia" else None

    n_rows = 0
    per_symbol: dict[str, int] = {}
    for sym in symbols:
        srows = by_sym.get(sym, [])
        past_news = [r for r in srows if r.get("tense") != "future"]
        te = time.time()
        idx = features.NoveltyIndex(past_news, embedder, cache=cache) if past_news else None
        if idx is not None and embedder.backend == "nvidia":
            save_embed_cache(embedder.model, cache)       # survive a crash mid-run
        sbars = bars.get(sym) or []
        days = [str(b["t"])[:10] for b in sbars if since <= str(b["t"])[:10] <= until]
        out_p = OUT / f"{sym}.jsonl"
        with out_p.open("w", encoding="utf-8") as fh:
            for day in days:
                row = features.daily_features(sym, day, srows, srows, bars=sbars,
                                              rating_rec=panel_rec(panel, sym, day), novelty=idx)
                row["novelty_backend"] = embedder.backend if idx is not None else None
                fh.write(features.dumps(row) + "\n")
        per_symbol[sym] = len(days)
        n_rows += len(days)
        print(f"  {sym:6} {len(days):4} days  {len(past_news):5} news rows  "
              f"{len(idx.titles) if idx else 0:5} titles  {time.time() - te:5.1f}s")
    receipt = {"built_utc": corpus.utcnow(), "symbols": symbols, "since": since, "until": until,
               "n_symbol_days": n_rows, "per_symbol": per_symbol, "novelty": embed_note,
               "embed_calls": embedder.calls, "embed_titles": embedder.n_embedded,
               "close_source": "alpaca_daily_bar_close_sip_adj_all",
               "runtime_s": round(time.time() - t0, 1)}
    (OUT / "build_receipt.json").write_text(json.dumps(receipt, indent=1), encoding="utf-8")
    print(f"  built {n_rows} symbol-days in {receipt['runtime_s']}s")
    return receipt


# ------------------------------------------------------------------------- IC


def forward_returns(bars: list[dict], h: int) -> dict[str, float]:
    """{day: open[t+1] -> close[t+h]}. Null where the future is not in the file."""
    out = {}
    for i in range(len(bars) - h):
        o = bars[i + 1].get("o")
        c = bars[i + h].get("c")
        if o and c and float(o) > 0:
            out[str(bars[i]["t"])[:10]] = float(c) / float(o) - 1.0
    return out


def ic_table(symbols: list[str], *, since: str) -> dict:
    t0 = time.time()
    bars = {}
    for s in symbols + [BENCH]:
        p = bars_path(s)
        if p.exists():
            bars[s] = json.loads(p.read_text(encoding="utf-8"))["bars"]
    if BENCH not in bars:
        raise SystemExit(f"no cached bars for {BENCH}; build first")
    bench_fwd = {h: forward_returns(bars[BENCH], h) for h in HORIZONS}

    panel: list[dict] = []          # one dict per (symbol, day) with features + targets
    for s in symbols:
        p = OUT / f"{s}.jsonl"
        if not p.exists() or s not in bars:
            continue
        fwd = {h: forward_returns(bars[s], h) for h in HORIZONS}
        for line in p.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            day = row["day"]
            if day < since:
                continue
            feats = features.numeric_fields(row)
            targets = {}
            for h in HORIZONS:
                r = fwd[h].get(day)
                b = bench_fwd[h].get(day)
                if r is not None:
                    targets[f"fwd_{h}d"] = r
                    if b is not None:
                        targets[f"fwd_{h}d_rel"] = r - b
            if targets:
                panel.append({"symbol": s, "day": day, "month": day[:7], "f": feats, "t": targets})

    names = sorted({k for r in panel for k in r["f"]})
    table = []
    for name in names:
        rec = {"feature": name}
        for tgt in ("fwd_5d", "fwd_5d_rel", "fwd_21d", "fwd_21d_rel"):
            xs, ys, bl = [], [], []
            for r in panel:
                if name in r["f"] and tgt in r["t"]:
                    xs.append(r["f"][name])
                    ys.append(r["t"][tgt])
                    bl.append(r["month"])
            rec[tgt] = features.rank_ic(xs, ys, bl)
        table.append(rec)
    table.sort(key=lambda r: -abs(r["fwd_21d"]["ic"] or 0.0))

    def fmt(c):
        if c["ic"] is None:
            return "     --              "
        lo = c["ci_lo"]
        hi = c["ci_hi"]
        band = f"[{lo:+.3f},{hi:+.3f}]" if lo is not None else "[   --  ,   --  ]"
        return f"{c['ic']:+.3f} {band}"

    print("\n  RANK IC (Spearman) vs forward return, entry t+1 OPEN, exit t+h CLOSE; 90% CI = month-block bootstrap")
    print(f"  {'feature':24} {'n':>6}  {'IC_5d raw':21} {'IC_5d vs SPY':21} {'IC_21d raw':21} {'IC_21d vs SPY':21}")
    for r in table:
        print(f"  {r['feature']:24} {r['fwd_21d']['n']:6}  {fmt(r['fwd_5d'])} {fmt(r['fwd_5d_rel'])} "
              f"{fmt(r['fwd_21d'])} {fmt(r['fwd_21d_rel'])}")
    receipt = {"computed_utc": corpus.utcnow(), "symbols": symbols, "since": since,
               "n_symbol_days": len(panel), "n_months": len({r["month"] for r in panel}),
               "entry": "open of session t+1", "exit": "close of session t+h", "benchmark": BENCH,
               "bootstrap": "500 resamples of calendar months with replacement, 5th/95th pct",
               "table": table, "runtime_s": round(time.time() - t0, 1)}
    out_p = OUT / f"ic_{date.today().isoformat()}.json"
    out_p.write_text(json.dumps(receipt, indent=1), encoding="utf-8")
    print(f"\n  {len(panel)} symbol-days, {receipt['n_months']} months -> {out_p}")
    return receipt


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--universe", choices=("default", "corpus"), default="default",
                    help="'corpus' = every symbol with >= 20 news rows, so the panel covers "
                         "what the sensors cover (23 -> ~156). T3 cannot be asked below that.")
    ap.add_argument("--since", default="2025-09-01")
    # THE DAY BEFORE THE LAST ET SESSION, not the day before the machine's date.
    # `date.today()` is local, and this machine runs UTC+8, so from 08:00 SGT the
    # local date is already tomorrow in ET and `today - 1` asks SIP for a session
    # that has not closed -- HTTP 403, "subscription does not permit querying
    # recent SIP data", which reads like a plan problem and is a clock problem.
    # Third instance of the two-clocks trap in this repo; `exits.session_day` is
    # the one definition (see its docstring).
    ap.add_argument("--until",
                    default=(date.fromisoformat(_exits.session_day()) - timedelta(days=1)).isoformat(),
                    help="last bar date; default the session before the current ET trading day "
                         "(the free SIP plan refuses data inside the last 15 minutes)")
    ap.add_argument("--ic", action="store_true", help="compute the rank-IC table from the built files")
    ap.add_argument("--no-build", action="store_true", help="with --ic: skip the build")
    ap.add_argument("--no-embed", action="store_true", help="TF-IDF novelty; never call NVIDIA")
    ap.add_argument("--refresh-bars", action="store_true")
    ap.add_argument("--role", default=None, help="account role for the data client (sets AAT_ACCOUNT_ROLE if unset)")
    args = ap.parse_args(argv)

    config.load_env()
    if args.role and not os.getenv("AAT_ACCOUNT_ROLE"):
        os.environ["AAT_ACCOUNT_ROLE"] = args.role
    if args.symbols:
        symbols = sorted({s.upper() for s in args.symbols})
    elif args.universe == "corpus":
        symbols = corpus_symbols()
    else:
        symbols = default_symbols()
    print(f"corpus_features: {len(symbols)} symbols, {args.since} -> {args.until}")
    if not args.no_build:
        build(symbols, since=args.since, until=args.until, no_embed=args.no_embed,
              refresh_bars=args.refresh_bars)
    if args.ic:
        ic_table(symbols, since=args.since)
    return 0


if __name__ == "__main__":
    sys.exit(main())
