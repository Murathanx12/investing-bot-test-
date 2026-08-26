"""How many bets is the book actually making?

    python -m scripts.concentration              # this account, weighted by TRUE MAX LOSS
    python -m scripts.concentration --days 60    # longer correlation window

Reports, never refuses. Whether effective-N-by-risk becomes an admission gate is
an attended decision; this is the measurement that would inform it.

Calibration: Situational Awareness LP's Q2 2026 13F -- $20.2bn, 24 issuers --
measured 5.34 by weight and 1.43 BY RISK. On its worst July session 20 of 21
priced names fell together. A book that looks like five bets and behaves like
1.4 is one position wearing twenty-one tickers.
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timedelta, timezone

from alpha import book as book_mod, concentration, config
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=60, help="calendar days of returns")
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()

    b = book_mod.read(client)
    weights = concentration.weights_from_book(b)
    if not weights:
        print("no structures with a positive max loss -- nothing to measure.")
        return 0

    start = (datetime.now(timezone.utc) - timedelta(days=args.days)).date().isoformat()
    try:
        bars = client.stock_bars_multi(sorted(weights), start=start, timeframe="1Day")
    except BrokerRefusal as exc:
        print(f"REFUSED: market data unavailable ({exc}). No reading is better than a wrong one.")
        return 1

    returns: dict[str, list[float]] = {}
    for sym, rows in bars.items():
        closes = [float(r["c"]) for r in rows if r.get("c")]
        if len(closes) > 5:
            returns[sym] = [math.log(closes[i] / closes[i - 1])
                            for i in range(1, len(closes)) if closes[i - 1] > 0]

    c = concentration.measure(weights, returns)
    state, why = concentration.verdict(c)

    total = sum(weights.values())
    print(f"BOOK CONCENTRATION  [{state}]")
    print(f"  {why}\n")
    if c:
        print(f"  sessions used        {c.sessions}")
        print(f"  daily vol (real)     {100*c.vol_real:.2f}%")
        print(f"  ...if independent    {100*c.vol_independent:.2f}%")
        print(f"  reference: Situational Awareness Q2 2026 = "
              f"{concentration.SITUATIONAL_AWARENESS_Q2_2026_N_RISK:.2f} by risk\n")
    print(f"  {'underlying':12s} {'max loss $':>12s} {'share':>7s}")
    for sym, v in sorted(weights.items(), key=lambda kv: -kv[1]):
        flag = "" if sym in returns else "   (UNPRICED - excluded, not assumed uncorrelated)"
        print(f"  {sym:12s} {v:>12,.0f} {100*v/total:>6.1f}%{flag}")

    marg = concentration.marginal(weights, returns)
    if marg:
        print("\n  MARGINAL CONTRIBUTION TO CONCENTRATION")
        print(f"  which name costs the most diversification -- NOT the same ordering as size")
        print(f"  {'underlying':12s} {'share':>7s} {'N_risk without':>15s} {'delta':>8s}")
        for sym, share, n_wo, delta in marg:
            mark = "  <- cut this first" if delta == marg[0][3] and delta > 0.01 else ""
            print(f"  {sym:12s} {100*share:>6.1f}% {n_wo:>15.2f} {delta:>+8.2f}{mark}")
        big_share = max(marg, key=lambda r: r[1])[0]
        worst = marg[0][0]
        if worst != big_share:
            print(f"\n  NOTE: the largest position is {big_share}, but removing {worst} would")
            print(f"  diversify the book more. Cutting by SIZE would cut the wrong name.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
