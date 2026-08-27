"""Given a book's MEASURED five-session returns, which option structure wins?

    python -m scripts.structure_lab
    python -m scripts.structure_lab --iv 0.45 --dte 21

Ranks by MEDIAN, not mean. A five-session competition is one draw; the mean is
what you get from many, and the ranker that optimised it chose a 33%-hit-rate
call over a 56%-hit-rate share position.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import numpy as np

from alpha import config, lab, optlab
from scripts.wealth_lab import SECTORS, UNIVERSE

BOOKS = {
    "sector rotate 1m top1": lambda: lab.rotate(SECTORS, 21),
    "mega-cap mom 6m k=5": lambda: lab.cross_sectional(126, 0, 5),
    "BUY AND HOLD QQQ": lambda: lab.hold("QQQ"),
}


def window_returns(panel: lab.Panel, sel, start_i: int, horizon: int) -> np.ndarray:
    out = []
    for i in range(start_i, panel.n_dates - horizon - 1):
        w = sel(panel, i)
        if w is None:
            continue
        w = np.nan_to_num(w, nan=0.0, posinf=0.0, neginf=0.0)
        entry, exit_ = panel.open_[i + 1], panel.open_[i + 1 + horizon]
        ok = np.isfinite(entry) & np.isfinite(exit_) & (entry > 0) & (w != 0)
        if not ok.any():
            continue
        leg = np.zeros_like(w)
        leg[ok] = exit_[ok] / entry[ok] - 1.0
        out.append(float(np.sum(w * leg)))
    return np.asarray(out)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--iv", type=float, default=0.35, help="implied vol, annualised")
    p.add_argument("--dte", type=int, default=30)
    p.add_argument("--horizon", type=int, default=5)
    p.add_argument("--demean", action="store_true",
                   help="THE NULL: strip the drift, keep the shape. Every option "
                        "structure levers whatever edge is in the input, so a "
                        "structure ranking computed on a drift that has not "
                        "cleared its noise floor is a ranking of an assumption.")
    args = p.parse_args()
    config.load_env()

    panel = lab.build_panel(UNIVERSE, start=(date.today() - timedelta(days=1100)).isoformat())
    start_i = panel.n_dates - 252 - args.horizon - 1

    for label, mk in BOOKS.items():
        rets = window_returns(panel, mk(), start_i, args.horizon)
        if args.demean:
            rets = rets - float(np.mean(rets))
        rv = float(np.std(rets)) * np.sqrt(252.0 / args.horizon)
        print("=" * 92)
        if args.demean:
            print("*** NULL: drift removed. Fat tails, vol and skew are the real ones. ***")
        print(f"BOOK: {label}   {len(rets)} five-session draws, "
              f"realised vol {rv:.1%}, priced at IV {args.iv:.0%}, {args.dte}d expiry")
        if rv > args.iv:
            print(f"  NOTE: realised {rv:.1%} EXCEEDS the {args.iv:.0%} IV assumed here, so long")
            print("  premium is flattered. Re-run with --iv above the realised number.")
        print(f"{'structure':<30} {'mean':>8} {'median':>8} {'hit':>6} {'worst':>8} {'best':>8}")
        print("-" * 92)
        res = optlab.evaluate(rets, sigma=args.iv, holding_days=args.horizon, dte=args.dte)
        for r in sorted(res, key=lambda r: -r.median_pnl):
            print(r.line())
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
