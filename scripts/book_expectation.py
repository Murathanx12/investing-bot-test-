"""What does the proposed competition book actually pay over five sessions?

    python -m scripts.book_expectation --equity 100000

Runs the EXACT composition `scripts/competition_book` proposes -- 70% of risk in
index short put spreads, 30% in a k=20 momentum share basket -- over every
five-session window of the last year, and reports the distribution.

A point estimate would be the same mistake the ranker makes. Five sessions is
ONE draw from this distribution, so the median and the left tail are the numbers
that describe what actually happens, and they are printed beside the mean rather
than under it.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

import numpy as np

from alpha import config, lab, optlab, playbook
from scripts.competition_book import CORE, EARNINGS_IN_WINDOW, WORST_5D
from scripts.wealth_lab import UNIVERSE

CORE_IV = 0.20      # index 30-day IV, the level SPY/QQQ actually trade at
SAT_IV = 0.35


def windows(panel: lab.Panel, sel, start_i: int, horizon: int) -> np.ndarray:
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--equity", type=float, default=100_000.0)
    ap.add_argument("--horizon", type=int, default=5)
    args = ap.parse_args()
    config.load_env()

    panel = lab.build_panel(UNIVERSE, start=(date.today() - timedelta(days=1100)).isoformat())
    start_i = panel.n_dates - 252 - args.horizon - 1
    core_risk, sat_risk = playbook.core_satellite(args.equity)
    core_risk = min(core_risk, playbook.name_budget(args.equity, len(CORE)) * len(CORE))

    # --- core: index returns -> short put spread P&L, per dollar of margin ----
    def core_basket(p, i):
        w = np.zeros(p.n_symbols)
        for s in CORE:
            if s in p.symbols:
                w[p.symbols.index(s)] = 1.0 / len(CORE)
        return w

    core_r = windows(panel, core_basket, start_i, args.horizon)
    core_res = {r.name: r for r in optlab.evaluate(core_r, sigma=CORE_IV,
                                                   holding_days=args.horizon, dte=30)}
    sps = [v for k, v in core_res.items() if k.startswith("short put spread 100/90")][0]

    # --- satellite: the k=20 momentum basket, held as shares -----------------
    sat_sel = lab.cross_sectional(252, 21, playbook.MIN_BREADTH_K)
    sat_r = windows(panel, sat_sel, start_i, args.horizon)
    sat_notional = sat_risk / WORST_5D

    print(f"BOOK EXPECTATION over {args.horizon} sessions, ${args.equity:,.0f} equity")
    print("=" * 78)
    print(f"  core      ${core_risk:>9,.0f} margin in index short put spreads "
          f"(IV {CORE_IV:.0%})")
    print(f"  satellite ${sat_notional:>9,.0f} notional in a k={playbook.MIN_BREADTH_K} "
          f"momentum share basket")
    print(f"  {len(core_r)} historical five-session windows (last year)\n")

    print(f"  {'leg':<28} {'mean':>9} {'median':>9} {'hit':>6} {'worst':>9}")
    print("  " + "-" * 64)
    print(f"  {'core (short put spreads)':<28} {sps.mean_pnl * core_risk:>+9,.0f} "
          f"{sps.median_pnl * core_risk:>+9,.0f} {sps.hit:>6.1%} "
          f"{sps.worst * core_risk:>+9,.0f}")
    print(f"  {'satellite (shares)':<28} {np.mean(sat_r) * sat_notional:>+9,.0f} "
          f"{np.median(sat_r) * sat_notional:>+9,.0f} {np.mean(sat_r > 0):>6.1%} "
          f"{np.min(sat_r) * sat_notional:>+9,.0f}")

    # Combine PAIRWISE on the same windows -- adding two independently computed
    # medians would assume the legs are independent, and they share the market.
    n = min(len(core_r), len(sat_r))
    S0 = 100.0
    T0, T1 = 30 / 365.0, (30 - args.horizon) / 365.0
    S1 = S0 * (1.0 + core_r[:n])
    credit = float(optlab.bs(S0, 100.0, T0, CORE_IV, call=False)
                   - optlab.bs(S0, 90.0, T0, CORE_IV, call=False))
    margin = (100.0 - 90.0) - credit
    exitv = (np.asarray(optlab.bs(S1, 100.0, T1, CORE_IV, call=False), dtype=float)
             - np.asarray(optlab.bs(S1, 90.0, T1, CORE_IV, call=False), dtype=float))
    fee = abs(credit) * 0.02 + np.abs(exitv) * 0.02
    core_leg = (credit - exitv - fee) / margin

    combined = core_leg * core_risk + sat_r[:n] * sat_notional
    print("  " + "-" * 64)
    print(f"  {'COMBINED (same windows)':<28} {np.mean(combined):>+9,.0f} "
          f"{np.median(combined):>+9,.0f} {np.mean(combined > 0):>6.1%} "
          f"{np.min(combined):>+9,.0f}")
    pct = np.percentile(combined, [5, 25, 50, 75, 95])
    print(f"\n  five-session P&L percentiles:")
    for lbl, v in zip(("5th", "25th", "50th", "75th", "95th"), pct):
        print(f"    {lbl:>5}  {v:>+10,.0f}  ({v / args.equity:+.2%})")
    print(f"\n  The 5th percentile is the number to plan around: a bad week costs")
    print(f"  ${abs(pct[0]):,.0f}. The book that lost $37,337 had no such figure,")
    print(f"  because nothing in it had a defined loss before the order went out.")

    core_only = core_leg * core_risk
    print(f"\n  DISCOUNT THE SATELLITE. Its distribution is measured on")
    print(f"  `wealth_lab.UNIVERSE` -- 216 tickers liquid TODAY -- which is")
    print(f"  survivorship bias a point-in-time screen does not have. The same")
    print(f"  momentum family replayed on CRSP 1993-2024 at this horizon returned")
    print(f"  0.47x terminal wealth at k=20. Treat the satellite median as an")
    print(f"  UPPER BOUND, and the core-only line as the defensible one:")
    print(f"    core only   mean {np.mean(core_only):+,.0f}   "
          f"median {np.median(core_only):+,.0f}   "
          f"5th pct {np.percentile(core_only, 5):+,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
