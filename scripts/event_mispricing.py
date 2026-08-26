"""EVENT_MISPRICING_v1 -- predict what the option market gets WRONG, not what the stock does.

    python -m scripts.event_mispricing            # walk-forward on the 117 reconstructed prints
    python -m scripts.event_mispricing --json

`event_move` forecasts the size of the earnings move. The thing we are paid on
is different: was the straddle EXPENSIVE or CHEAP? So the target here is the
straddle's own return (and, as a second target, realised-minus-implied), and
the features are only things knowable at the entry close:

    implied_move           the straddle's own price / spot
    rv20                   trailing 20-day daily realised vol
    implied_over_rv        implied move / rv20 -- "how rich is the print"
    prior_resid            the name's PRIOR prints: mean realised-minus-implied
    prior_straddle         the name's PRIOR prints: mean straddle return
    n_prior                how many prior prints inform the two above
    bellwether_prior       on the name's PRIOR prints: mean |QQQ move| / mean |own move|
    drift5                 |5-day return| into the print
    log_volume             option volume at entry (that day's bar)

Model: ridge on standardised features, WALK-FORWARD -- every prediction for
print i is fitted on prints strictly before it (by entry date), with the first
40 prints as burn-in. No neural network on 112 observations; the paper trail
this repo keeps says exactly why.

The honest baselines are named beside it: the name's own prior mean (which is
what `event_move` already does) and zero.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from alpha import config
from alpha.brains.vol_gap import _daily_bars
from alpha.broker.alpaca import AlpacaPaper

BURN_IN = 40
RIDGE_LAMBDA = 3.0
FEATURES = ["implied_move", "rv20", "implied_over_rv", "prior_resid", "prior_straddle", "n_prior",
            "bellwether_prior", "drift5", "log_volume"]


def _state_dir() -> Path:
    return Path(config.__file__).resolve().parent.parent / "state"


def _closes(bars: list[dict]) -> tuple[list[str], list[float]]:
    return [b["t"][:10] for b in bars], [float(b["c"]) for b in bars]


def _rv(closes: list[float], idx: int, n: int = 20) -> float | None:
    if idx < n + 1:
        return None
    rets = [math.log(closes[j] / closes[j - 1]) for j in range(idx - n + 1, idx + 1)]
    return statistics.pstdev(rets) if len(rets) > 2 else None


def build_rows(events: list[dict], bars: dict[str, tuple[list[str], list[float]]],
               qqq: tuple[list[str], list[float]]) -> list[dict]:
    """One feature row per print, using ONLY information at the entry close."""
    qdays, qcl = qqq
    qidx = {d: i for i, d in enumerate(qdays)}

    def qmove(day: str) -> float | None:
        i = qidx.get(day)
        return abs(qcl[i] / qcl[i - 1] - 1.0) if i else None

    rows = []
    by_symbol: dict[str, list[dict]] = {}
    for e in sorted(events, key=lambda x: x["entry_day"]):
        sym = e["symbol"]
        days, cl = bars[sym]
        idx = {d: i for i, d in enumerate(days)}
        i = idx.get(e["entry_day"])
        if i is None or i < 26:
            continue
        rv20 = _rv(cl, i)
        if not rv20:
            continue
        prior = by_symbol.get(sym, [])
        resid = [p["realised_abs_move"] - p["implied_move"] for p in prior]
        sret = [p["straddle_return"] for p in prior]
        q_prior = [qmove(p["event_day"]) for p in prior]
        own_prior = [p["realised_abs_move"] for p in prior]
        pairs = [(q, o) for q, o in zip(q_prior, own_prior) if q is not None and o > 0]
        bell = (statistics.mean(q for q, _ in pairs) / statistics.mean(o for _, o in pairs)) if pairs else 0.0
        row = {
            "symbol": sym, "entry_day": e["entry_day"], "event_day": e["event_day"],
            "implied_move": e["implied_move"], "rv20": rv20,
            "implied_over_rv": e["implied_move"] / rv20,
            "prior_resid": statistics.mean(resid) if resid else 0.0,
            "prior_straddle": statistics.mean(sret) if sret else 0.0,
            "n_prior": len(prior), "bellwether_prior": bell,
            "drift5": abs(cl[i] / cl[i - 5] - 1.0),
            "log_volume": math.log1p(float(e.get("volume_entry") or 0.0)),
            "y_straddle": e["straddle_return"],
            "y_resid": e["realised_abs_move"] - e["implied_move"],
        }
        rows.append(row)
        by_symbol.setdefault(sym, []).append(e)
    return rows


def ridge_fit(X: np.ndarray, y: np.ndarray, lam: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    mu, sd = X.mean(axis=0), X.std(axis=0) + 1e-12
    Z = (X - mu) / sd
    ym = y.mean()
    A = Z.T @ Z + lam * np.eye(Z.shape[1])
    w = np.linalg.solve(A, Z.T @ (y - ym))
    return w, mu, sd, ym


def walk_forward(rows: list[dict], target: str, lam: float = RIDGE_LAMBDA) -> dict:
    X = np.array([[r[f] for f in FEATURES] for r in rows], dtype=float)
    y = np.array([r[target] for r in rows], dtype=float)
    preds, base_prior, truth, keep = [], [], [], []
    for i in range(BURN_IN, len(rows)):
        w, mu, sd, ym = ridge_fit(X[:i], y[:i], lam)
        preds.append(float(((X[i] - mu) / sd) @ w + ym))
        base_prior.append(rows[i]["prior_straddle"] if target == "y_straddle" else rows[i]["prior_resid"])
        truth.append(float(y[i]))
        keep.append(i)
    p, b, t = np.array(preds), np.array(base_prior), np.array(truth)

    def corr(a, c):
        return float(np.corrcoef(a, c)[0, 1]) if a.std() > 0 and c.std() > 0 else 0.0

    def hit(a, c):
        m = a != 0
        return float(((a[m] > 0) == (c[m] > 0)).mean()) if m.any() else 0.0

    order = np.argsort(p)
    n = len(p)
    terc = [order[: n // 3], order[n // 3: 2 * n // 3], order[2 * n // 3:]]
    tercile_mean = [float(t[ix].mean()) for ix in terc]
    top, bottom = t[terc[2]], t[terc[0]]
    spread = float(top.mean() - bottom.mean())
    pooled_sd = float(np.sqrt((top.var(ddof=1) / len(top)) + (bottom.var(ddof=1) / len(bottom)))) if len(top) > 2 and len(bottom) > 2 else 0.0
    w, _, _, _ = ridge_fit(X, y, lam)
    return {
        "target": target, "n_oos": n, "burn_in": BURN_IN, "lambda": lam,
        "oos_corr_model": round(corr(p, t), 3), "oos_corr_prior_mean": round(corr(b, t), 3),
        "sign_hit_model": round(hit(p, t), 3), "sign_hit_prior_mean": round(hit(b, t), 3),
        "tercile_mean_truth_by_pred": [round(x, 4) for x in tercile_mean],
        "top_minus_bottom": round(spread, 4),
        "top_minus_bottom_t": round(spread / pooled_sd, 2) if pooled_sd > 0 else None,
        "mean_truth": round(float(t.mean()), 4),
        "long_when_pred_positive": {
            "n": int((p > 0).sum()), "mean": round(float(t[p > 0].mean()), 4) if (p > 0).any() else None},
        "avoid_when_pred_negative": {
            "n": int((p <= 0).sum()), "mean_avoided": round(float(t[p <= 0].mean()), 4) if (p <= 0).any() else None},
        "final_fit_coefficients_standardised": {f: round(float(c), 4) for f, c in zip(FEATURES, w)},
        "oos_rows": [{"symbol": rows[i]["symbol"], "event_day": rows[i]["event_day"], "pred": round(float(pp), 4),
                      "truth": round(float(tt), 4)} for i, pp, tt in zip(keep, preds, truth)],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    p.add_argument("--lambda", dest="lam", type=float, default=RIDGE_LAMBDA)
    args = p.parse_args()
    config.load_env()
    src = _state_dir() / "event_straddle_backtest.json"
    events = json.loads(src.read_text(encoding="utf-8"))["events"]
    client = AlpacaPaper()
    bars = {}
    for sym in sorted({e["symbol"] for e in events}):
        bars[sym] = _closes(_daily_bars(client, sym, 800))
    qqq = _closes(_daily_bars(client, "QQQ", 800))
    rows = build_rows(events, bars, qqq)
    print(f"\nEVENT_MISPRICING_v1 -- {len(rows)} prints with features, walk-forward from print {BURN_IN + 1}\n")
    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n_rows": len(rows), "features": FEATURES}
    for target in ("y_straddle", "y_resid"):
        r = walk_forward(rows, target, args.lam)
        out[target] = r
        print(f"target {target:11s}  n_oos {r['n_oos']}  OOS corr model {r['oos_corr_model']:+.3f} vs name-prior "
              f"{r['oos_corr_prior_mean']:+.3f} | sign hit {r['sign_hit_model']:.0%} vs {r['sign_hit_prior_mean']:.0%}")
        print(f"    truth by predicted tercile (low->high): {r['tercile_mean_truth_by_pred']}  "
              f"top-bottom {r['top_minus_bottom']:+.4f} (t {r['top_minus_bottom_t']})  mean {r['mean_truth']:+.4f}")
        print(f"    long when pred>0: n={r['long_when_pred_positive']['n']} mean {r['long_when_pred_positive']['mean']}; "
              f"avoided when pred<=0: n={r['avoid_when_pred_negative']['n']} mean {r['avoid_when_pred_negative']['mean_avoided']}")
        coefs = sorted(r["final_fit_coefficients_standardised"].items(), key=lambda kv: -abs(kv[1]))
        print("    coefficients (standardised, final fit): " + ", ".join(f"{k} {v:+.3f}" for k, v in coefs[:5]))
    # The univariate reading the model is built on: does implied/rv alone sort straddle returns?
    ratio = np.array([r["implied_over_rv"] for r in rows]); ys = np.array([r["y_straddle"] for r in rows])
    order = np.argsort(ratio); n = len(rows)
    uni = [round(float(ys[order[k * n // 3:(k + 1) * n // 3]].mean()), 4) for k in range(3)]
    out["univariate_implied_over_rv_terciles"] = uni
    print(f"\n    univariate: straddle return by implied/rv20 tercile (cheap->rich): {uni}")
    if args.json:
        path = _state_dir() / "event_mispricing.json"
        path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\n  receipt: {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
