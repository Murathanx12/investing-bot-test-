"""Does a RELEVANCE-FILTERED event count carry what a raw count did not?

THE QUESTION, AND WHY IT IS NOT THE ONE ALREADY ANSWERED
========================================================
On 2026-08-30 the raw event counts were withdrawn: `ev_insider_20d` +0.023
[-0.004,+0.046] on 152 names, 0 of 29 features clearing zero. That is a GLOBAL
negative about ONE ENCODING -- a count of every headline the wire attached to a
ticker.

An LLM read a 250-row random sample of that corpus the same day and found the
encoding is mostly noise: 82.8% of rows have the right subject, but only
**18.4% are a new dated fact ABOUT that company**. 78.4% are recaps, listicles,
'stocks moving' aggregates and opinion. So the withdrawn feature was counting
roughly five stale items for every real event.

Two different things follow, and this file tests both:

  1. FILTER. `ev_real_20d` counts only (role=subject AND is_new_fact). It is a
     different feature, not a cleaned version of the old one.
  2. SIGN. Tetlock, *All the News That's Fit to Reprint* (RFS 2011): stale news
     moves prices LESS, and the day-of return on stale news REVERSES over the
     following week. So `stale_share_20d` is a signed hypothesis with a
     literature prior and a HORIZON -- one week, which is why 5d is tested
     first and given equal standing with 21d.

PRE-REGISTRATION (written before the first result was read; see PREREG below)
=============================================================================
Declared in code so that it cannot be edited after the fact without showing in
the diff. `--verify-prereg` re-prints it.

PIT
===
Entry is the OPEN of session t+1, so an item with `effective_at <= t` is public
before the trade regardless of the hour it crossed the wire. Labels come from
`news_relevance`, which sees only the item's own text -- never a price, never an
outcome -- so joining a label made today to a 2025 date introduces no lookahead.
Conditioning terciles are computed CROSS-SECTIONALLY PER DAY, never over the
full sample: a full-sample quantile is a lookahead dressed as a control.

NOTHING HERE PLACES AN ORDER.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from alpha.sources import corpus, features  # noqa: E402
from scripts.corpus_features import BENCH, bars_path, forward_returns  # noqa: E402

REL = corpus.CORPUS / "relevance"
FEAT = corpus.CORPUS / "features"

PREREG = {
    "trial_id": "T12-RELEVANCE-FILTERED-EVENT-COUNTS",
    "registered": "2026-08-30",
    "licence": "PRODUCT_EXPERIMENT",
    "question": "Does counting only new dated company facts (LLM-labelled) carry cross-sectional "
                "information that counting every tagged headline did not?",
    "features": [
        "ev_real_20d      count of (subject AND new fact) items, trailing 20 sessions",
        "ev_real_5d       the same over 5 sessions",
        "ev_all_20d       CONTROL: every tagged item, trailing 20 sessions (the withdrawn encoding)",
        "stale_share_20d  1 - ev_real_20d/ev_all_20d; Tetlock's staleness, signed NEGATIVE by prior",
        "ev_real_hard_20d subject AND new fact AND event_type in {earnings, guidance, m_and_a, "
        "clinical, regulatory, contract, insider}  (drops analyst_rating/product/macro/none)",
    ],
    "targets": ["fwd_5d_rel", "fwd_21d_rel"],
    "horizon_prior": "5d is the PRIMARY horizon for stale_share (Tetlock RFS 2011 reversal is one "
                     "week); 21d is reported for comparability with the withdrawn run.",
    "conditioning": "terciles of realised_vol_20d and of coverage_baseline_90d, computed "
                    "cross-sectionally PER DAY (never full-sample)",
    "null": "the same IC after shuffling the feature within each day (cross-sectional shuffle), "
            "which destroys the cross-section while keeping every marginal",
    "multiplicity": "BH-FDR at q=0.10 across every (feature x target x cell) reported",
    "pass": "a cell whose 90% block-bootstrap CI excludes zero AND survives BH-FDR AND whose sign "
            "matches the pre-declared prior where one exists",
    "not_a_pass": "a raw IC that clears zero in one cell of eighteen with no FDR survival",
}

#: The types that describe a dated corporate development. `analyst_rating` is
#: excluded from the HARD variant on purpose -- it is a third party's opinion
#: about the company, not an act by the company -- and `product`/`macro`/`none`
#: because the first is mostly marketing and the last two are not company facts.
HARD_TYPES = {"earnings", "guidance", "m_and_a", "clinical", "regulatory", "contract", "insider"}

HORIZONS = (5, 21)
WINDOWS = {"20d": 20, "5d": 5}


def bh_fdr(pvals: list[float], q: float = 0.10) -> list[bool]:
    """Benjamini-Hochberg. True where the hypothesis survives at level q.

    CANON §63: a SCREEN controls the false discovery rate; an EXPORT controls
    the family-wise rate with Holm. This is a screen.
    """
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    keep = [False] * m
    kmax = -1
    for rank, i in enumerate(order, 1):
        if pvals[i] <= q * rank / m:
            kmax = rank
    for rank, i in enumerate(order, 1):
        if rank <= kmax:
            keep[i] = True
    return keep


def boot_p(ic: float | None, lo: float | None, hi: float | None) -> float:
    """A two-sided p implied by the bootstrap CI, via a normal approximation.

    The CI is a 90% block bootstrap, so (hi-lo) spans 2 x 1.645 sigma. This is
    an approximation and it is stated as one: it exists to ORDER hypotheses for
    BH-FDR, not to be quoted as a p-value.
    """
    if ic is None or lo is None or hi is None or hi <= lo:
        return 1.0
    sigma = (hi - lo) / (2 * 1.6449)
    if sigma <= 0:
        return 1.0
    from math import erfc, sqrt
    return float(erfc(abs(ic) / (sigma * sqrt(2))))


def load_labels() -> dict[str, list[dict]]:
    """{symbol: [label, ...]} with an effective date on each."""
    by_sym: dict[str, list[dict]] = defaultdict(list)
    if not REL.exists():
        raise SystemExit(f"no labels in {REL}; run `python -m scripts.news_relevance` first")
    for p in sorted(REL.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            d = str(r.get("effective_at") or "")[:10]
            if d:
                by_sym[r["symbol"]].append({"day": d, "role": r["role"],
                                            "new": bool(r["is_new_fact"]), "type": r["event_type"]})
    for v in by_sym.values():
        v.sort(key=lambda x: x["day"])
    return by_sym


def counts_for(labels: list[dict], sessions: list[str]) -> dict[str, dict[str, float]]:
    """Trailing-window counts on each SESSION day (not calendar day).

    The window is `n` trading sessions ending at t inclusive. Using sessions,
    not calendar days, keeps a long weekend from shrinking the window.
    """
    idx = {d: i for i, d in enumerate(sessions)}
    # Bucket every label onto the first session >= its effective date.
    per_session: dict[int, list[dict]] = defaultdict(list)
    for lab in labels:
        i = idx.get(lab["day"])
        if i is None:
            j = next((k for k, d in enumerate(sessions) if d >= lab["day"]), None)
            if j is None:
                continue
            i = j
        per_session[i].append(lab)
    out: dict[str, dict[str, float]] = {}
    for i, day in enumerate(sessions):
        rec: dict[str, float] = {}
        for tag, n in WINDOWS.items():
            lo = max(0, i - n + 1)
            win = [x for k in range(lo, i + 1) for x in per_session.get(k, ())]
            real = [x for x in win if x["role"] == "subject" and x["new"]]
            rec[f"ev_all_{tag}"] = float(len(win))
            rec[f"ev_real_{tag}"] = float(len(real))
            if tag == "20d":
                rec["ev_real_hard_20d"] = float(sum(1 for x in real if x["type"] in HARD_TYPES))
                rec["stale_share_20d"] = (1.0 - len(real) / len(win)) if win else float("nan")
        out[day] = rec
    return out


def load_cond(sym: str) -> dict[str, dict[str, float]]:
    """{day: {realised_vol_20d, coverage_baseline_90d}} from the built panel."""
    p = FEAT / f"{sym}.jsonl"
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        out[r["day"]] = {k: r.get(k) for k in ("realised_vol_20d", "coverage_baseline_90d")}
    return out


def tercile_by_day(rows: list[dict], key: str) -> None:
    """Stamp each row with a per-day tercile of `key`. PIT: the cut uses only
    that day's cross-section, never the full sample."""
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        v = r["cond"].get(key)
        if v is not None and np.isfinite(v):
            by_day[r["day"]].append(r)
    for day, group in by_day.items():
        vals = np.array([g["cond"][key] for g in group], dtype=float)
        if len(vals) < 9:                       # a tercile of 8 names is not a tercile
            continue
        q1, q2 = np.quantile(vals, [1 / 3, 2 / 3])
        for g in group:
            v = g["cond"][key]
            g[f"tc_{key}"] = "low" if v <= q1 else ("high" if v > q2 else "mid")


def build_panel(symbols: list[str] | None) -> list[dict]:
    labels = load_labels()
    syms = sorted(symbols or labels.keys())
    bench = bars_path(BENCH)
    if not bench.exists():
        raise SystemExit(f"no cached bars for {BENCH}")
    bbars = json.loads(bench.read_text(encoding="utf-8"))["bars"]
    bench_fwd = {h: forward_returns(bbars, h) for h in HORIZONS}

    panel: list[dict] = []
    for s in syms:
        p = bars_path(s)
        if not p.exists() or s not in labels:
            continue
        bars = json.loads(p.read_text(encoding="utf-8"))["bars"]
        sessions = [str(b["t"])[:10] for b in bars]
        fwd = {h: forward_returns(bars, h) for h in HORIZONS}
        cnt = counts_for(labels[s], sessions)
        cond = load_cond(s)
        for day in sessions:
            f = cnt.get(day) or {}
            if not f or f.get("ev_all_20d", 0) <= 0:
                continue                        # no news at all: not a row about news
            t = {}
            for h in HORIZONS:
                r, b = fwd[h].get(day), bench_fwd[h].get(day)
                if r is not None and b is not None:
                    t[f"fwd_{h}d_rel"] = r - b
            if not t:
                continue
            panel.append({"symbol": s, "day": day, "month": day[:7],
                          "f": f, "t": t, "cond": cond.get(day) or {}})
    for k in ("realised_vol_20d", "coverage_baseline_90d"):
        tercile_by_day(panel, k)
    return panel


def ic_cell(rows: list[dict], feat: str, tgt: str, *, shuffle_null: bool = False,
            seed: int = 7) -> dict:
    xs, ys, bl = [], [], []
    if shuffle_null:
        rng = np.random.default_rng(seed)
        by_day: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            by_day[r["day"]].append(r)
        rows = []
        for day, g in by_day.items():
            vals = [r["f"].get(feat) for r in g]
            perm = rng.permutation(len(g))
            for i, r in enumerate(g):
                rows.append({**r, "f": {**r["f"], feat: vals[perm[i]]}})
    for r in rows:
        v, y = r["f"].get(feat), r["t"].get(tgt)
        if v is None or y is None or not np.isfinite(v):
            continue
        xs.append(v)
        ys.append(y)
        bl.append(r["month"])
    if len(xs) < 30:
        return {"ic": None, "n": len(xs), "n_blocks": len(set(bl)), "ci_lo": None, "ci_hi": None}
    return features.rank_ic(xs, ys, bl)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--q", type=float, default=0.10, help="BH-FDR level")
    ap.add_argument("--verify-prereg", action="store_true")
    a = ap.parse_args(argv)

    print("\n  PRE-REGISTRATION " + PREREG["trial_id"] + f"  ({PREREG['registered']}, {PREREG['licence']})")
    for k in ("question", "horizon_prior", "conditioning", "null", "multiplicity", "pass"):
        print(f"    {k:14s} {PREREG[k]}")
    print("    features")
    for f in PREREG["features"]:
        print(f"                   {f}")
    if a.verify_prereg:
        return 0

    panel = build_panel(a.symbols)
    if not panel:
        raise SystemExit("empty panel -- are labels and bars both present?")
    syms = {r["symbol"] for r in panel}
    print(f"\n  panel: {len(panel):,} symbol-days, {len(syms)} symbols, "
          f"{len({r['month'] for r in panel})} months, {min(r['day'] for r in panel)} -> "
          f"{max(r['day'] for r in panel)}")

    feats = ["ev_real_20d", "ev_real_5d", "ev_real_hard_20d", "stale_share_20d", "ev_all_20d"]
    tgts = ["fwd_5d_rel", "fwd_21d_rel"]
    cells: list[dict] = []

    print("\n  == GLOBAL (all 152) ==")
    print(f"  {'feature':18} {'target':12} {'n':>6} {'blk':>4}  {'IC [90% CI]':26} {'shuffled null':>14}")
    for f in feats:
        for t in tgts:
            c = ic_cell(panel, f, t)
            nul = ic_cell(panel, f, t, shuffle_null=True)
            cells.append({"cell": "global", "feature": f, "target": t, **c,
                          "null_ic": nul["ic"]})
            band = (f"{c['ic']:+.3f} [{c['ci_lo']:+.3f},{c['ci_hi']:+.3f}]"
                    if c["ic"] is not None and c["ci_lo"] is not None else "   --")
            print(f"  {f:18} {t:12} {c['n']:6,} {c['n_blocks']:4}  {band:26} "
                  f"{(f'{nul['ic']:+.3f}' if nul['ic'] is not None else '  --'):>14}")

    for key, short in (("realised_vol_20d", "vol"), ("coverage_baseline_90d", "cov")):
        print(f"\n  == CONDITIONAL on {key} tercile (per-day cross-section) ==")
        print(f"  {'feature':18} {'target':12} {'cell':10} {'n':>6} {'blk':>4}  {'IC [90% CI]':26}")
        for f in feats:
            for t in tgts:
                for tc in ("low", "mid", "high"):
                    rows = [r for r in panel if r.get(f"tc_{key}") == tc]
                    c = ic_cell(rows, f, t)
                    if c["ic"] is None:
                        continue
                    cells.append({"cell": f"{short}:{tc}", "feature": f, "target": t, **c})
                    band = (f"{c['ic']:+.3f} [{c['ci_lo']:+.3f},{c['ci_hi']:+.3f}]"
                            if c["ci_lo"] is not None else "   --")
                    print(f"  {f:18} {t:12} {short + ':' + tc:10} {c['n']:6,} {c['n_blocks']:4}  {band:26}")

    ps = [boot_p(c["ic"], c["ci_lo"], c["ci_hi"]) for c in cells]
    keep = bh_fdr(ps, a.q)
    for c, p, k in zip(cells, ps, keep):
        c["p_approx"], c["bh_survives"] = round(p, 4), bool(k)
    winners = [c for c in cells if c["bh_survives"]]

    print(f"\n  == BH-FDR at q={a.q:.2f} across {len(cells)} cells ==")
    if not winners:
        print("  NOTHING SURVIVES. The relevance filter does not rescue the event count.")
        print("  That is a second negative on the ENCODING, and it is a real answer:")
        print("  the counts were not weak because they were dirty.")
    else:
        for c in sorted(winners, key=lambda x: x["p_approx"]):
            print(f"  SURVIVES  {c['feature']:18} {c['target']:12} {c['cell']:10} "
                  f"IC {c['ic']:+.3f} [{c['ci_lo']:+.3f},{c['ci_hi']:+.3f}]  n={c['n']:,}  "
                  f"p~{c['p_approx']:.4f}")

    out = corpus.CORPUS / f"relevance_ic_{date.today().isoformat()}.json"
    out.write_text(json.dumps({"prereg": PREREG, "computed_utc": corpus.utcnow(),
                               "n_symbol_days": len(panel), "n_symbols": len(syms),
                               "q": a.q, "cells": cells}, indent=1), encoding="utf-8")
    print(f"\n  receipt -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
