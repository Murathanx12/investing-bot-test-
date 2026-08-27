"""Which ROLE resolves to which ACCOUNT, read from the venue. Read-only.

    python -m scripts.accounts

WHY THIS EXISTS
===============
On 2026-08-27 a reviewer read the Alpaca dashboard, saw an account labelled
"hackathon" sitting at -13%, and concluded the judged account was already
poisoned. The label is a UI nickname; the ROLE is an env-var prefix in this repo;
the identity is the `account_number` the venue returns. Those three are not the
same object and only the third one is authoritative.

So this prints the mapping instead of letting anyone infer it. Nothing here
trades, sizes or writes -- it issues GETs and prints.

The output is also the input to `alpha/genesis.py`: an account number that has
already been traded is a legacy account forever, and the only way to know which
numbers those are is to ask.
"""

from __future__ import annotations

import argparse
import os

from alpha import config
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--role", action="append", help="limit to these roles (default: all known)")
    args = p.parse_args()
    config.load_env()

    roles = args.role or config.known_roles()
    if not roles:
        print("no roles have credentials in this environment")
        return 1

    print(f"{'role':<12} {'account':<14} {'equity':>12} {'pos':>4} {'ord':>5}  status")
    print("-" * 78)
    rows = []
    for role in roles:
        # `config.credentials` REFUSES when --role and AAT_ACCOUNT_ROLE disagree,
        # because a disagreement means orders go to one account and ledger rows
        # are stamped with another's name. This script writes no rows and sends
        # no orders, so it keeps the two in agreement rather than bypassing the
        # check -- the guard stays honest and this loop still works.
        os.environ["AAT_ACCOUNT_ROLE"] = role
        client = AlpacaPaper(role=role)
        try:
            acct = client.account()
            positions = client.positions()
            try:
                orders = client.orders(status="all", limit=500)
            except BrokerRefusal:
                orders = client.orders(status="open")
            number = str(acct.get("account_number") or "?")
            equity = float(acct.get("equity") or 0.0)
            status = str(acct.get("status") or "?")
            traded = len(orders) > 0 or len(positions) > 0
            rows.append((role, number, equity, len(positions), len(orders), traded))
            print(f"{role:<12} {number:<14} {equity:>12,.2f} {len(positions):>4} "
                  f"{len(orders):>5}  {status}"
                  + ("   <- HAS TRADED: legacy forever" if traded else "   clean"))
        except Exception as exc:                                        # noqa: BLE001
            print(f"{role:<12} {'--':<14} {'':>12} {'':>4} {'':>5}  "
                  f"UNREADABLE {type(exc).__name__}: {str(exc)[:60]}")

    traded = [r for r in rows if r[5]]
    if traded:
        print("\nACCOUNTS THAT HAVE TRADED -- these can never hold the `competition` role:")
        for role, number, equity, npos, nord, _ in traded:
            print(f"  {number}   (role {role}, ${equity:,.0f}, {npos} positions, {nord} orders)")
        print("\nAdd any number missing from alpha/genesis.DENIED_ACCOUNTS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
