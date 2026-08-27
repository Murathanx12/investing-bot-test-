"""LIVE_SPREAD_CONSTRUCTOR_v1 runner -- price the core from the ACTUAL chain.

    AAT_ACCOUNT_ROLE=dev python -m scripts.live_spread_book
    AAT_ACCOUNT_ROLE=dev python -m scripts.live_spread_book --symbols SPY --floor 0.10

Reads the real option chain and enumerates every vertical it can support,
crossing the spread against us on BOTH legs. Prints; places nothing.

WHY A SEPARATE RUNNER FROM `competition_book`
=============================================
`competition_book` decides HOW MUCH risk each candidate deserves, from measured
distributions. This decides WHETHER a placeable structure exists AT ALL right
now, from live quotes. The two failures are different and the second is the one
that bites at 15:52 ET: an allocation is worthless if no structure clears the
spread when the order goes in.

THE FLOOR IS AN ARGUMENT, NOT A CONSTANT
========================================
`--floor` is the minimum credit as a fraction of width. Passing nothing means NO
measured floor has been established, and the output says so instead of quietly
ranking by credit and looking like evidence. The measured value comes from
`scripts/optionmetrics_core_replay` (Aegis repo), which found a median credit
ratio near 10% of width for a 25-delta, 5%-wide SPY put spread over 2005-2020.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from alpha import config, playbook, spreads, timing
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal
from alpha.data import chain as chain_mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="SPY,QQQ,IWM")
    ap.add_argument("--floor", type=float, default=None,
                    help="minimum credit / width, from MEASURED evidence. "
                         "Omitted means no floor is established.")
    ap.add_argument("--equity", type=float, default=100_000.0)
    ap.add_argument("--right", default="P", choices=["P", "C"])
    ap.add_argument("--delta", type=float, default=0.25,
                    help="short-leg delta the REPLAY measured; the live pick "
                         "matches this rather than maximising credit")
    ap.add_argument("--width-frac", type=float, default=0.05)
    args = ap.parse_args()
    config.load_env()

    client = AlpacaPaper()
    lo = (date.today() + timedelta(days=playbook.MIN_DTE)).isoformat()
    hi = (date.today() + timedelta(days=playbook.MAX_DTE)).isoformat()

    print(f"LIVE SPREAD BOOK   expiries {lo} .. {hi}   right={args.right}")
    print("execution assumption: sell the SHORT leg at the BID, buy the LONG "
          "leg at the OFFER.")
    print("=" * 92)

    names = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    per_name = playbook.name_budget(args.equity, len(names) or 1)

    for sym in names:
        print(f"\n{sym}")
        try:
            snap = chain_mod.fetch(client, sym, expiry_from=lo, expiry_to=hi)
        except (BrokerRefusal, chain_mod.ChainRefusal) as exc:
            print(f"  REFUSED: {type(exc).__name__}: {exc}")
            print("  A chain we cannot read is not a chain we may trade.")
            continue

        print(f"  spot ${snap.spot:,.2f}  {len(snap.contracts)} contracts  "
              f"feed={snap.feed}  median quote age "
              f"{snap.median_quote_age_seconds:.0f}s  "
              f"market_open={snap.market_open}")

        search = spreads.enumerate_verticals(
            snap, right=args.right, min_dte=playbook.MIN_DTE,
            max_dte=playbook.MAX_DTE)
        print(f"  search: {search.summary()}")
        for note in search.notes:
            print(f"    note: {note}")

        # MATCH the replayed geometry rather than maximise the credit ratio.
        # Ranking by credit/width picks the narrowest at-the-money spread, which
        # is close to a coin flip and is NOT the structure the 30-year replay
        # measured -- so its distribution would not describe the trade.
        best, refusals = spreads.matching_spread(
            search, spot=snap.spot, target_delta=args.delta,
            target_width_frac=args.width_frac)
        for r in refusals:
            print(f"  {r}")
        if best is None:
            print("  -> CASH for this underlying.")
            continue
        if args.floor is not None and best.credit_ratio < args.floor:
            print(f"  CREDIT TOO THIN: {best.credit_ratio:.1%} of width against "
                  f"a measured floor of {args.floor:.1%}. -> CASH.")
            continue
        if args.floor is None:
            print("  NO MEASURED CREDIT FLOOR supplied: the structure below is "
                  "the right SHAPE but nothing here says it is well priced.")

        n = playbook.size_leg(per_name, best.max_loss_per_contract)
        print(f"  BEST  {best.describe()}")
        print(f"        short {best.short_symbol}   long {best.long_symbol}")
        oi = (f"min OI {best.min_open_interest}" if best.oi_known
              else "OI UNAVAILABLE (gate did not run)")
        print(f"        worst leg spread {best.worst_leg_spread:.1%}   {oi}   "
              f"quote age {best.quote_age_seconds:.0f}s")
        print(f"        credit {best.credit_ratio:.1%} of width crossed, "
              f"{best.mid_credit / best.width:.1%} at the mids   "
              f"short delta {best.short_delta:+.2f}")
        print(f"        breakeven ${best.breakeven:.2f} "
              f"({best.breakeven / snap.spot - 1:+.2%} from spot)")
        if n <= 0:
            print(f"        SIZE 0: one contract risks "
                  f"${best.max_loss_per_contract:,.0f} against a "
                  f"${per_name:,.0f} per-name budget.")
            continue
        print(f"        SIZE {n} contracts, ${n * best.max_loss_per_contract:,.0f} "
              f"of defined loss")

        # The limit price the order would actually carry. An earlier version
        # passed `best.width` as the ask, which made the "limit" the midpoint
        # between the credit and the spread width -- a number with no meaning
        # that printed as $0.72 on a $0.43 credit. The real two-sided range is
        # the crossed credit (worst) to the mid credit (best).
        px = timing.marketable_limit(max(best.credit, 0.01),
                                     max(best.mid_credit, best.credit + 0.01),
                                     "sell", aggression=0.5)
        t = timing.entry_timing("option", signal_frozen_et=None)
        print(f"        ORDER  multileg LIMIT net credit ~${px:.2f}, "
              f"tif={t.time_in_force} (options accept no other)")

    print("\nNOTHING WAS SENT.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
