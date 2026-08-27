"""Freeze or verify the judged account's birth state. See `alpha/genesis.py`.

    AAT_ACCOUNT_ROLE=competition python -m scripts.genesis --freeze \
        --rules docs/RULES_SNAPSHOT_2026-08-28.md
    AAT_ACCOUNT_ROLE=competition python -m scripts.genesis

`--freeze` is a ONE-TIME act and refuses to overwrite an existing record. It
sends no orders; it reads the account and writes one local JSON file.
"""

from __future__ import annotations

import argparse
import sys

from alpha import config, genesis
from alpha.broker.alpaca import AlpacaPaper


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true", help="record the birth state (one time)")
    p.add_argument("--rules", default="docs/RULES_SNAPSHOT_2026-08-25.md",
                   help="the rules snapshot this account is frozen against")
    p.add_argument("--role", default=None, help="default: AAT_ACCOUNT_ROLE")
    p.add_argument("--force", action="store_true",
                   help="overwrite an existing genesis record (see the refusal text first)")
    args = p.parse_args()
    config.load_env()

    role = args.role or config.role()
    client = AlpacaPaper(role=role)

    if args.freeze:
        try:
            g = genesis.freeze(client, role=role, rules_snapshot=args.rules,
                               force_write=args.force)
        except genesis.GenesisRefusal as exc:
            print(f"GENESIS REFUSED\n  {exc}", file=sys.stderr)
            return 1
        print(f"GENESIS FROZEN for role {g.role!r}")
        print(f"  account   {g.account_number}")
        print(f"  equity    ${g.starting_equity:,.2f}")
        print(f"  at        {g.frozen_at_utc}")
        print(f"  rules     {g.rules_snapshot_path}  sha {g.rules_snapshot_sha256[:16]}")
        print(f"  code      {g.code_commit}")
        print(f"  sha256    {g.digest()}")
        print(f"  written   {genesis.path(role)}")
        return 0

    ok, lines = genesis.verify(client, role=role)
    print(f"GENESIS {'OK' if ok else 'REFUSED'}  role={role}")
    for line in lines:
        print(f"  {line}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
