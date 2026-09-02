"""GO TO ZERO: the attended backstop when nothing else is trustworthy.

    python -m scripts.flatten --role hack3                 # DRY RUN (always safe)
    AAT_ALLOW_FLATTEN=1 python -m scripts.flatten --role hack3 --i-mean-it
    AAT_ALLOW_FLATTEN=1 python -m scripts.flatten --all --i-mean-it

WHY (Murat, 2026-09-02): "even if everything is down there should be a backup.
with decisions that matter most it should sell everything or reject everything
so we stay at 0." The reject half already exists everywhere (the books fail
closed). This is the sell half: cancel every open order, close every position,
per role or fleet-wide, with two independent arming steps so it can never fire
from a stray shell history line.

Notes that matter when you actually need this:
- Market CLOSED: close_position is rejected by the venue; the dry run still
  shows the book, and the resting protective stops remain armed broker-side.
- This uses the BROKER's close endpoint (market orders), so it works even when
  every AEGIS service, seal, and ledger is broken -- only .env is needed.
- Paper accounts only: AlpacaPaper refuses live endpoints by construction.
"""

from __future__ import annotations

import argparse
import os
import sys

ROLES = ("hack1", "hack2", "hack3", "hack4", "hack5", "hack6")


def flatten_role(role: str, *, armed: bool) -> int:
    from alpha.broker.alpaca import AlpacaPaper
    b = AlpacaPaper(role)
    orders = b.orders()
    positions = b.positions()
    print(f"== {role}: {len(orders)} open orders, {len(positions)} positions "
          f"{'-- FLATTENING' if armed else '-- DRY RUN'}")
    errors = 0
    for o in orders:
        oid, sym = o.get("id"), o.get("symbol")
        print(f"  cancel {sym} {o.get('side')} {o.get('qty')} ({o.get('order_type') or o.get('type')})")
        if armed:
            try:
                b.cancel_order(oid)
            except Exception as exc:  # noqa: BLE001
                errors += 1
                print(f"    FAILED: {exc}")
    for p in positions:
        sym = p.get("symbol")
        print(f"  close  {sym} qty {p.get('qty')} mkt_value {p.get('market_value')}")
        if armed:
            try:
                b.close_position(sym)
            except Exception as exc:  # noqa: BLE001
                errors += 1
                print(f"    FAILED: {exc}")
    if armed and errors:
        print(f"  {errors} actions FAILED -- the book is NOT flat; re-run or use the broker UI")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--role", choices=ROLES)
    g.add_argument("--all", action="store_true")
    ap.add_argument("--i-mean-it", action="store_true",
                    help="second arming step; without it this is a dry run")
    a = ap.parse_args()

    armed = a.i_mean_it and os.getenv("AAT_ALLOW_FLATTEN") == "1"
    if a.i_mean_it and not armed:
        print("REFUSED: --i-mean-it given but AAT_ALLOW_FLATTEN=1 is not set. "
              "Both arming steps are required, deliberately.")
        return 2

    from alpha import config
    config.load_env()
    roles = ROLES if a.all else (a.role,)
    total_errors = 0
    for role in roles:
        try:
            total_errors += flatten_role(role, armed=armed)
        except Exception as exc:  # noqa: BLE001
            total_errors += 1
            print(f"== {role}: UNREACHABLE: {exc}")
    if not armed:
        print("\nDRY RUN ONLY. To execute: AAT_ALLOW_FLATTEN=1 ... --i-mean-it")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
