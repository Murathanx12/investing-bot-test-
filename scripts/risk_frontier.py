"""TOURNAMENT_RISK_FRONTIER_v1 -- what defined-loss budget maximises P(target) under a floor?

    AAT_ACCOUNT_ROLE=staging python -m scripts.risk_frontier --target 0.02 --floor -0.05

WHAT IT SIMULATES, AND WITH WHAT
================================
Five sessions, $100k. Two sleeves:
  * BETA CORE  -- shares in SPY, sampled by BOOTSTRAP from real five-session
                  windows of the last ~1,160 sessions (Alpaca daily bars);
  * OPTION SLEEVE -- SPY call debit spreads at a defined-loss budget b, whose
                  return on premium is drawn from the OptionMetrics replay
                  moments (state/evidence/core_replay.json: n=884, mean +3.3%,
                  sd 47.6%, p05 -72%, hit 51%) -- modelled as a two-part
                  mixture (a total-loss mass and a lognormal-ish winner tail)
                  fitted to those moments, because per-block returns are not in
                  the receipt. THIS IS PARAMETRIC ON MEASURED MOMENTS, stated so.
The sleeves are drawn with the same market path (a spread's outcome is driven
by the same SPY move as the shares), so the left tail is not independent.

For each budget b in {0, 5, 10, ..., 40}% and each core weight, report
P(terminal >= target), P(terminal <= floor), median, p05. The frontier is the
budget that maximises P(target) subject to P(floor) <= a stated ceiling.
`tournament.mode_for` decides WHEN to attack; this says HOW MUCH is rational
when it does. Places nothing.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

import numpy as np

from alpha import config
from alpha.broker.alpaca import AlpacaPaper

STATE = Path(os.getenv("AAT_LEDGER_DIR") or "state")


def five_session_returns(client, symbol: str = "SPY", start: str = "2022-01-01") -> np.ndarray:
    data = client._request("GET", f"/v2/stocks/{symbol}/bars", base=config.data_url(),
                           params={"timeframe": "1Day", "start": start, "limit": 10000, "feed": config.stock_feed(),
                                   "adjustment": "all"})
    closes = np.array([float(b["c"]) for b in (data or {}).get("bars") or []])
    return closes[5:] / closes[:-5] - 1.0


def spread_return_given_move(move: np.ndarray, rng: np.random.Generator, *, mean=0.0334, sd=0.4757, p05=-0.7217,
                             hit=0.5147, worst=-0.969) -> np.ndarray:
    """A call debit spread's return on premium, conditioned on the SPY move.

    A ~30 DTE ATM/OTM call spread is a leveraged, capped bet on the move: below
    the long strike it tends to the total-loss floor, above the short strike to
    the capped max gain. Map the standardised move through a logistic so that
    the UNCONDITIONAL moments reproduce the receipt's hit rate and mean, then
    add residual noise scaled so the unconditional sd matches. The dependence on
    the same path is the point; the exact shape is a stated approximation.
    """
    z = (move - np.median(move)) / (np.std(move) + 1e-12)
    # hit-rate calibration: P(win) ~ hit at z=0 offset
    k = 1.8
    prob_up = 1.0 / (1.0 + np.exp(-k * (z + math.log(hit / (1 - hit)) / k)))
    win_size = 1.2          # capped max gain on premium
    base = np.where(rng.random(len(move)) < prob_up, win_size, worst)
    # residual noise to fill the middle of the distribution
    noise = rng.normal(0.0, 0.35, len(move))
    r = np.clip(base + noise, worst, 2.5)
    # rescale to the receipt's mean and sd
    r = (r - r.mean()) / (r.std() + 1e-12) * sd + mean
    return np.clip(r, -1.0, 3.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=float, default=0.02)
    ap.add_argument("--floor", type=float, default=-0.05)
    ap.add_argument("--floor-ceiling", type=float, default=0.05, help="max acceptable P(terminal <= floor)")
    ap.add_argument("--core", type=float, default=0.60, help="share of equity in the beta core")
    ap.add_argument("--paths", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    config.load_env()
    client = AlpacaPaper()
    rng = np.random.default_rng(args.seed)
    spy5 = five_session_returns(client)
    print(f"SPY five-session windows: n={len(spy5)}  mean {spy5.mean():+.3%}  sd {spy5.std():.3%}  p05 {np.percentile(spy5, 5):+.2%}")

    rows = []
    idx = rng.integers(0, len(spy5), args.paths)
    move = spy5[idx]
    spread = spread_return_given_move(move, rng)
    print(f"spread sleeve (parametric on receipt moments): mean {spread.mean():+.3%} sd {spread.std():.3%} hit {(spread > 0).mean():.0%} p05 {np.percentile(spread, 5):+.2%}")
    print(f"\n{'budget':>7}{'core':>6}{'P(>=tgt)':>10}{'P(<=floor)':>11}{'median':>9}{'p05':>9}{'p95':>9}{'mean':>9}")
    best = None
    for b in [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40]:
        for core in sorted({0.0, args.core, 1.0}):
            term = core * move + b * spread
            p_t = float((term >= args.target).mean()); p_f = float((term <= args.floor).mean())
            row = {"budget": b, "core": core, "p_target": p_t, "p_floor": p_f, "median": float(np.median(term)),
                   "p05": float(np.percentile(term, 5)), "p95": float(np.percentile(term, 95)), "mean": float(term.mean())}
            rows.append(row)
            print(f"{b:>7.0%}{core:>6.0%}{p_t:>10.1%}{p_f:>11.1%}{row['median']:>+9.2%}{row['p05']:>+9.2%}{row['p95']:>+9.2%}{row['mean']:>+9.2%}")
            if p_f <= args.floor_ceiling and (best is None or p_t > best["p_target"]):
                best = row
    print(f"\nFRONTIER for target {args.target:+.0%}, floor {args.floor:+.0%} (P(floor) <= {args.floor_ceiling:.0%}): "
          + (f"budget {best['budget']:.0%}, core {best['core']:.0%}, P(target) {best['p_target']:.1%}, P(floor) {best['p_floor']:.1%}" if best else "no row satisfies the floor"))
    print("The option sleeve is PARAMETRIC on the receipt's moments; the core is a bootstrap of real windows. "
          "Read the ORDERING across budgets, not the third decimal.")
    out = STATE / "risk_frontier.json"
    out.write_text(json.dumps({"target": args.target, "floor": args.floor, "rows": rows, "best": best,
                               "spy_windows": int(len(spy5)), "note": "option sleeve parametric on core_replay moments"}, indent=1), encoding="utf-8")
    print(f"receipt: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
