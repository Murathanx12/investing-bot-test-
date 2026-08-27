"""What the surviving rules hold RIGHT NOW, and how concentrated that is.

    python -m scripts.today_book

A backtest that never prints its current holdings is a claim nobody can act on
or check. This prints the book each rule would open at the next open, plus the
EFFECTIVE NUMBER OF BETS -- because a five-name book whose names all fall
together is one bet, and that is how $20bn of somebody else's money went to zero.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from alpha import config, lab
from scripts.wealth_lab import SECTORS, UNIVERSE

RULES = [
    ("sector rotate 1m  top1", lambda: lab.rotate(SECTORS, 21)),
    ("sector rotate 3m  top3", lambda: lab.rotate(SECTORS, 63, k=3)),
    ("sector rotate 12m top1", lambda: lab.rotate(SECTORS, 252)),
    ("mega-cap mom 6m  k=5", lambda: lab.cross_sectional(126, 0, 5)),
    ("mega-cap mom 3m  k=5", lambda: lab.cross_sectional(63, 0, 5)),
    ("momentum 12-1  k=10", lambda: lab.cross_sectional(252, 21, 10)),
]


def effective_bets(p: lab.Panel, idx: list[int], i: int, lookback: int = 60) -> float:
    """1 / sum(w_i w_j rho_ij) for an equal-weight book -- the number of
    INDEPENDENT bets, not the number of tickers."""
    if len(idx) < 2:
        return float(len(idx))
    win = p.close[max(0, i - lookback):i + 1][:, idx]
    r = win[1:] / win[:-1] - 1.0
    r = r[np.isfinite(r).all(axis=1)]
    if r.shape[0] < 10:
        return float("nan")
    c = np.corrcoef(r, rowvar=False)
    w = np.full(len(idx), 1.0 / len(idx))
    denom = float(w @ c @ w)
    return 1.0 / denom if denom > 0 else float("nan")


def main() -> int:
    config.load_env()
    panel = lab.build_panel(UNIVERSE, start=(date.today() - timedelta(days=1100)).isoformat())
    i = panel.n_dates - 1
    print(f"decision close: {panel.dates[i]}   (fills at the NEXT open)\n")
    for name, mk in RULES:
        w = mk()(panel, i)
        idx = [j for j in range(panel.n_symbols) if w[j] != 0]
        syms = [panel.symbols[j] for j in idx]
        n_eff = effective_bets(panel, idx, i)
        r21 = lab._trailing_return(panel, i, 21)
        detail = "  ".join(f"{panel.symbols[j]} ({r21[j]:+.1%} 1m)" for j in idx)
        print(f"{name:<24} {len(syms)} name(s), effective bets {n_eff:.2f}")
        print(f"    {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
