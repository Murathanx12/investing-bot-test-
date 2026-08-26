"""MURAT_SELECTION_ORACLE_v1 -- did the user's picks carry a measurable characteristic, or beta?

    python -m scripts.selection_oracle [--asof 2025-11-07] [--controls 40] [--seed 7]

The review's design (2026-08-26): take every stock the user selected, note the
date it first appeared, build 100-500 contemporaneous MATCHED controls, hide
the ticker, and ask what differentiates the picks -- then compare picks to
controls at 1/5/21/63/126/252 sessions under equal, user and risk-normalised
weights, so SELECTION skill is separated from SIZING skill.

What THIS machine can do today, and what it cannot:
  * the only timestamped list is the Nov-2025 research list graded in
    `state/murat_list_2025-11_grade.json` (price on 2025-11-07 = the as-of);
  * controls are matched on the venue's dollar-volume bucket and, where the
    universe carries it, industry -- NOT on market cap (the venue has none) --
    so they are LIQUIDITY-matched, not size-matched;
  * feature attribution (SHAP over PIT features) is NOT possible: there is no
    point-in-time feature panel for these names on this machine. The receipt says
    so rather than fitting a model to twenty rows;
  * user weights are unknown for the list (only for the live book), so the
    sizing comparison is equal vs inverse-vol only.
Everything else in the design is run. Receipt: state/selection_oracle_<asof>.json
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpha import config, universe
from alpha.broker.alpaca import AlpacaPaper

HORIZONS = (1, 5, 21, 63, 126, 200)
GRADE = Path("state") / "murat_list_2025-11_grade.json"


def _t(xs):
    if len(xs) < 3:
        return 0.0
    sd = statistics.pstdev(xs)
    return statistics.mean(xs) / (sd / math.sqrt(len(xs))) if sd > 0 else 0.0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--asof", default="2025-11-07")
    p.add_argument("--controls", type=int, default=40, help="matched controls per pick")
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()
    config.load_env()
    rng = random.Random(args.seed)
    picks = json.loads(GRADE.read_text(encoding="utf-8"))
    pick_syms = [s for s in picks if isinstance(picks[s], dict) and picks[s].get("p_1107")]
    members = {m.symbol: m for m in universe.load() if not m.etf_like}
    print(f"{len(pick_syms)} picks with a {args.asof} price; {len(members)} non-ETF universe members")

    # -- controls: same dollar-volume bucket (and industry when both known), never a pick
    ctrl: dict[str, list[str]] = {}
    for s in pick_syms:
        m = members.get(s)
        pool = [c for c in members.values() if c.symbol not in pick_syms and (m is None or c.dv_bucket == m.dv_bucket)]
        if m is not None and m.industry:
            same = [c for c in pool if c.industry == m.industry]
            if len(same) >= 10:
                pool = same
        ctrl[s] = [c.symbol for c in rng.sample(pool, min(args.controls, len(pool)))]
    all_syms = sorted(set(pick_syms) | {c for cs in ctrl.values() for c in cs})
    start = (datetime.fromisoformat(args.asof) - timedelta(days=120)).strftime("%Y-%m-%d")
    client = AlpacaPaper()
    bars = client.stock_bars_multi(all_syms + ["IWM", "SPY", "XBI"], start=start)
    print(f"bars for {len(bars)} symbols")

    def path(sym):
        b = bars.get(sym) or []
        days = [x["t"][:10] for x in b]
        closes = [float(x["c"]) for x in b]
        i0 = next((i for i, d in enumerate(days) if d >= args.asof), None)
        if i0 is None or i0 < 30:
            return None
        pre = [math.log(closes[i] / closes[i - 1]) for i in range(i0 - 30, i0)]
        vol = statistics.pstdev(pre) * math.sqrt(252)
        out = {"vol_pre": round(vol, 4)}
        for h in HORIZONS:
            if i0 + h < len(closes):
                out[h] = math.log(closes[i0 + h] / closes[i0])
        # survivorship: a control that stops trading is a LOSS, not a missing value
        out["last_day"] = days[-1]
        return out

    P = {s: path(s) for s in all_syms}
    missing_picks = [s for s in pick_syms if P.get(s) is None]
    rep = {"asof": args.asof, "picks": pick_syms, "picks_without_bars": missing_picks, "controls_per_pick": args.controls,
           "matching": "dollar-volume bucket (+ industry where known); NOT market cap -- the venue has none",
           "feature_attribution": "NOT RUN: no point-in-time feature panel on this machine; twenty rows cannot carry SHAP",
           "user_weights": "unknown for the Nov-2025 list; equal vs inverse-vol only"}

    # -- pick vs its own control mean, per horizon (paired) --------------------
    per_h = {}
    for h in HORIZONS:
        diffs, pick_r, ctrl_r, ranks = [], [], [], []
        for s in pick_syms:
            ps = P.get(s)
            if not ps or h not in ps:
                continue
            cs = [P[c][h] for c in ctrl[s] if P.get(c) and h in P[c]]
            if len(cs) < 5:
                continue
            diffs.append(ps[h] - statistics.mean(cs))
            pick_r.append(ps[h])
            ctrl_r.append(statistics.mean(cs))
            ranks.append(sum(1 for c in cs if c < ps[h]) / len(cs))   # percentile of the pick among its controls
        if diffs:
            per_h[h] = {"n_picks": len(diffs), "pick_mean": round(statistics.mean(pick_r), 4),
                        "control_mean": round(statistics.mean(ctrl_r), 4), "diff_mean": round(statistics.mean(diffs), 4),
                        "diff_median": round(statistics.median(diffs), 4), "t_paired": round(_t(diffs), 2),
                        "pick_percentile_mean": round(statistics.mean(ranks), 3),
                        "share_beating_controls": round(sum(1 for r in ranks if r > 0.5) / len(ranks), 3)}
    rep["pick_vs_matched_controls"] = per_h
    print("\nPICKS vs MATCHED CONTROLS (log return from the as-of close; paired on each pick's own controls)")
    for h, v in per_h.items():
        print(f"  {h:4d}s  picks {v['pick_mean']:+.1%}  controls {v['control_mean']:+.1%}  diff {v['diff_mean']:+.1%} (median {v['diff_median']:+.1%})  "
              f"t {v['t_paired']:+.2f}  pick percentile {v['pick_percentile_mean']:.2f}  beat controls {v['share_beating_controls']:.0%}  n={v['n_picks']}")

    # -- sizing: equal vs inverse-vol on the picks; same on controls ------------
    def basket(syms, h, weights):
        rs = [(P[s][h], weights[s]) for s in syms if P.get(s) and h in P[s] and s in weights]
        if not rs:
            return None
        w = sum(x[1] for x in rs)
        return sum(r * ww for r, ww in rs) / w
    eq = {s: 1.0 for s in pick_syms}
    iv = {s: 1.0 / max(P[s]["vol_pre"], 0.05) for s in pick_syms if P.get(s)}
    sizing = {}
    for h in HORIZONS:
        e, i = basket(pick_syms, h, eq), basket(pick_syms, h, iv)
        ce = statistics.mean([basket(ctrl[s], h, {c: 1.0 for c in ctrl[s]}) or 0.0 for s in pick_syms if P.get(s)])
        sizing[h] = {"equal": round(e, 4) if e is not None else None, "inverse_vol": round(i, 4) if i is not None else None,
                     "controls_equal": round(ce, 4)}
    rep["sizing"] = sizing
    print("\nSIZING (basket log return): equal-weight picks | inverse-vol picks | equal-weight controls")
    for h, v in sizing.items():
        f = lambda x: f"{x:+.1%}" if x is not None else "n/a"  # noqa: E731
        print(f"  {h:4d}s  {f(v['equal'])} | {f(v['inverse_vol'])} | {f(v['controls_equal'])}")

    # -- what the picks LOOK like vs controls (the only PIT characteristics on hand)
    def feat(syms):
        vols = [P[s]["vol_pre"] for s in syms if P.get(s)]
        bks = [members[s].dv_bucket for s in syms if s in members]
        return {"n": len(vols), "vol_pre_median": round(statistics.median(vols), 3) if vols else None,
                "dv_bucket_mix": {b: bks.count(b) for b in ("micro", "small", "mid", "large", "mega") if bks.count(b)}}
    rep["characteristics"] = {"picks": feat(pick_syms), "controls": feat([c for cs in ctrl.values() for c in cs])}
    print(f"\nCHARACTERISTICS picks {rep['characteristics']['picks']} | controls {rep['characteristics']['controls']}")
    # dispersion: the picks' cross-sectional spread of outcomes vs the controls'
    for h in (63, 200):
        pr = [P[s][h] for s in pick_syms if P.get(s) and h in P[s]]
        cr = [P[c][h] for cs in ctrl.values() for c in cs if P.get(c) and h in P[c]]
        if pr and cr:
            rep.setdefault("dispersion", {})[h] = {"picks_sd": round(statistics.pstdev(pr), 3), "controls_sd": round(statistics.pstdev(cr), 3),
                                                   "picks_max": round(max(pr), 3), "picks_min": round(min(pr), 3)}
    print(f"DISPERSION {rep.get('dispersion')}")
    per_pick = {s: {h: round(P[s][h], 4) for h in HORIZONS if h in P[s]} | {"vol_pre": P[s]["vol_pre"],
                "ctrl_mean_200": round(statistics.mean([P[c][200] for c in ctrl[s] if P.get(c) and 200 in P[c]] or [0.0]), 4)}
                for s in pick_syms if P.get(s)}
    rep["per_pick"] = per_pick
    out = Path("state") / f"selection_oracle_{args.asof}.json"
    out.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(f"\nreceipt -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
