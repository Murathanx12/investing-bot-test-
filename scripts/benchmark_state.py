"""What state the passive-beta benchmark is actually in. Read-only.

    AAT_ACCOUNT_ROLE=market python -m scripts.benchmark_state

Exits 0 only when the state is ACTIVE -- i.e. a position exists. Every other
state exits 1, including ORDER_SENT, because a working order is not a benchmark.
"""

from __future__ import annotations

import argparse

from alpha import benchmark, config
from alpha.broker.alpaca import AlpacaPaper


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="SPY")
    p.add_argument("--role", default=None)
    args = p.parse_args()
    config.load_env()

    client = AlpacaPaper(role=args.role)
    st = benchmark.read(client, symbol=args.symbol)
    acct = client.account()
    print(f"PASSIVE BETA  account {acct.get('account_number')}  equity "
          f"${float(acct.get('equity') or 0):,.2f}")
    print(f"  {st.line()}")
    print(f"  qty held {st.qty:g}   filled across orders {st.filled_qty:g}   "
          f"orders seen {st.orders_seen}")
    if not st.is_active:
        print("\n  NO BENCHMARK NUMBER MAY BE QUOTED FROM THIS STATE.")
    return 0 if st.is_active else 1


if __name__ == "__main__":
    raise SystemExit(main())
