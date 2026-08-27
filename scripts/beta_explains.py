"""Is the leaderboard a signal ranking, or a beta ranking wearing one's clothes?

If terminal wealth over the sample is explained by AVERAGE MARKET EXPOSURE, then
every row is the same trade at a different size, the ordering carries no
information about selection, and the only real decision is how much beta to hold
and what it costs to hold it.

That question decides what the competition book should be, so it gets a test
rather than an assertion.
"""
from __future__ import annotations

import numpy as np

from alpha import config, lab
from scripts.wealth_lab import UNIVERSE, battery

HORIZON = 5


def main() -> int:
    config.load_env()
    from datetime import date, timedelta
    panel = lab.build_panel(UNIVERSE, start=(date.today() - timedelta(days=1100)).isoformat())
    start_i = panel.n_dates - 252 - HORIZON - 1
    spy = panel.symbols.index("SPY")

    # THE REGRESSOR IS REALISED BETA, NOT DOLLAR WEIGHT.
    # A first version of this script regressed on the sum of the weight vector,
    # which is 1.00 for TQQQ and 1.00 for SPY -- a near-constant explains
    # nothing, and the R^2 of 0.036 it produced was a property of the test.
    # Beta is measured from the strategy's own return series against the
    # market's over the SAME holding windows.
    mkt = lab.run(panel, lab.hold("SPY"), horizon=HORIZON, name="mkt", start_i=start_i)

    def window_returns(sel):
        out = []
        for i in range(start_i, panel.n_dates - HORIZON - 1):
            w = sel(panel, i)
            if w is None:
                out.append(0.0); continue
            w = np.nan_to_num(w, nan=0.0, posinf=0.0, neginf=0.0)
            entry, exit_ = panel.open_[i + 1], panel.open_[i + 1 + HORIZON]
            ok = np.isfinite(entry) & np.isfinite(exit_) & (entry > 0) & (w != 0)
            leg = np.zeros_like(w)
            if ok.any():
                leg[ok] = exit_[ok] / entry[ok] - 1.0
            out.append(float(np.sum(w * leg)))
        return np.asarray(out)

    m = window_returns(lab.hold("SPY"))
    rows = []
    for name, sel, _why in battery(HORIZON):
        r = lab.run(panel, sel, horizon=HORIZON, name=name, start_i=start_i)
        s_ret = window_returns(sel)
        n = min(len(s_ret), len(m))
        cov = float(np.cov(s_ret[:n], m[:n])[0, 1])
        beta = cov / float(np.var(m[:n])) if np.var(m[:n]) > 0 else 0.0
        rows.append((name, beta, r.wealth, r.mean, r.t))

    mkt_w = None
    for name, e, wealth, mean, t in rows:
        if name == "BUY AND HOLD SPY":
            mkt_w = wealth
    x = np.array([r[1] for r in rows])
    y = np.array([r[2] for r in rows])
    A = np.vstack([x, np.ones_like(x)]).T
    slope, intercept = np.linalg.lstsq(A, y, rcond=None)[0]
    pred = A @ np.array([slope, intercept])
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    print("DOES AVERAGE GROSS EXPOSURE EXPLAIN TERMINAL WEALTH?  (1 year, hold 5)")
    print(f"{'strategy':<34} {'beta to SPY':>12} {'wealth':>8} {'residual':>9}")
    print("-" * 68)
    for (name, e, wealth, mean, t), pr in sorted(zip(rows, pred), key=lambda z: -z[0][2]):
        print(f"{name:<34} {e:>12.2f} {wealth:>8.3f}x {wealth - pr:>+9.3f}")
    print("-" * 68)
    print(f"  wealth ~= {intercept:.3f} + {slope:.3f} * beta     R^2 = {r2:.3f}")
    print()
    if r2 > 0.5:
        print("  VERDICT: the leaderboard is mostly a BETA ranking. Selection is not")
        print("  what separates these books; SIZE is. The decision that matters for a")
        print("  five-session P&L is how much exposure to carry and what it costs --")
        print("  not which of twenty-two signals to believe.")
    else:
        print("  VERDICT: exposure does NOT explain the ordering; selection is doing work.")
    top = sorted(zip(rows, pred), key=lambda z: -(z[0][2] - z[1]))[:3]
    print("\n  Largest POSITIVE residuals -- the only rows that earned more than their")
    print("  BETA alone would predict:")
    for (name, e, wealth, mean, t), pr in top:
        print(f"    {name:<32} {wealth:.3f}x vs {pr:.3f}x predicted  ({wealth - pr:+.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
