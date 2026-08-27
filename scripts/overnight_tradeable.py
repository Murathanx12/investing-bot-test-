"""Is the overnight tilt tradeable ON ONE LIQUID ETF, at that ETF's real costs?

    python -m scripts.overnight_tradeable

WHY THIS IS A DIFFERENT QUESTION FROM THE LAST ONE
==================================================
`FINDING_2026-08-28_ALL_OF_IT_HAPPENS_OVERNIGHT.md` measured the split on an
equal-weight basket of 200 names and killed the standalone version on costs: a
daily round trip over 200 names dies above ~1.5bps.

But that cost is a property of THE BASKET, not of the effect. SPY's quoted
spread is about a cent on ~$770 -- **0.13bp**, two orders of magnitude cheaper
than the basket's implied cost. So the honest follow-up is: run the same trade
on ONE ETF, at ONE ETF's spread.

And the comparison that matters is NOT overnight-only versus buy-and-hold.
Overnight-only earns less in total (it is flat all day) while carrying much less
risk, so comparing them raw rewards whoever took more risk. The right question
is **at MATCHED VOLATILITY**: lever the overnight leg until its risk equals
buy-and-hold's, and ask which ends with more money.
"""

from __future__ import annotations

import argparse
import math
from datetime import date, timedelta

import numpy as np

from alpha import config, lab
from scripts.wealth_lab import UNIVERSE

# One-way cost in bps for a single liquid ETF: half-spread plus a little impact.
# SPY quotes ~$0.01 on ~$770 = 0.13bp; 0.5bp one way is deliberately pessimistic.
ETF_ONE_WAY_BPS = 0.5


def summarise(name: str, r: np.ndarray, *, lev: float = 1.0) -> dict:
    r = r[np.isfinite(r)] * lev
    w = float(np.prod(1.0 + r))
    yrs = r.size / 252.0
    return {
        "name": name, "wealth": w, "n": r.size,
        "cagr": (w ** (1.0 / yrs) - 1.0) if w > 0 else -1.0,
        "vol": float(np.std(r)) * math.sqrt(252.0),
        "sharpe": (float(np.mean(r)) / float(np.std(r)) * math.sqrt(252.0)
                   if np.std(r) > 0 else 0.0),
        "worst": float(np.min(r)),
    }


def row(d: dict) -> str:
    return (f"  {d['name']:<34} {d['wealth']:>9.3f}x {d['cagr']:>+8.2%} "
            f"{d['vol']:>7.1%} {d['sharpe']:>+6.2f} {d['worst']:>+8.2%}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="SPY,QQQ,IWM,SMH")
    ap.add_argument("--bps", type=float, default=ETF_ONE_WAY_BPS)
    args = ap.parse_args()
    config.load_env()

    panel = lab.build_panel(UNIVERSE, start=(date.today() - timedelta(days=1100)).isoformat())
    print(f"Alpaca SIP  {panel.dates[0]} .. {panel.dates[-1]}  "
          f"({panel.n_dates} sessions)")
    print(f"one-way cost {args.bps:.2f}bp -> overnight-only pays "
          f"{2 * args.bps:.2f}bp per session, buy-and-hold pays it twice EVER\n")

    for sym in args.symbols.split(","):
        if sym not in panel.symbols:
            continue
        j = panel.symbols.index(sym)
        c, o = panel.close[:, j], panel.open_[:, j]
        m = np.isfinite(c[:-1]) & np.isfinite(o[1:]) & np.isfinite(c[1:]) & (c[:-1] > 0)
        hold = (c[1:] / c[:-1] - 1.0)[m]
        on = (o[1:] / c[:-1] - 1.0)[m] - 2.0 * args.bps / 10_000.0
        intra = (c[1:] / o[1:] - 1.0)[m] - 2.0 * args.bps / 10_000.0

        h = summarise("buy and hold", hold)
        n1 = summarise("overnight only (net)", on)
        i1 = summarise("intraday only (net)", intra)
        # Lever the overnight leg to the SAME realised vol as buy-and-hold.
        lev = h["vol"] / n1["vol"] if n1["vol"] > 0 else 1.0
        nl = summarise(f"overnight levered {lev:.2f}x", on, lev=lev)

        print(f"{sym}")
        print(f"  {'book':<34} {'wealth':>9} {'CAGR':>8} {'vol':>7} "
              f"{'Sharpe':>6} {'worst':>8}")
        print("  " + "-" * 76)
        for d in (h, n1, i1, nl):
            print(row(d))
        verdict = ("BEATS buy-and-hold at matched risk"
                   if nl["wealth"] > h["wealth"] else "does NOT beat buy-and-hold")
        print(f"  -> at matched volatility the overnight leg {verdict}.\n")

    print("Leverage here is a MODELLING device, not a recommendation: it is how a")
    print("lower-risk book is compared fairly with a higher-risk one. Financing")
    print("cost is NOT charged, so the levered rows are an upper bound -- and at")
    print("~5%/yr on the borrowed half that is not a rounding error.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
