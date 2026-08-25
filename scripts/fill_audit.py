"""Audit every submitted order against the quote we decided on, and mark it.

    AAT_ACCOUNT_ROLE=dev python -m scripts.fill_audit
    python -m scripts.fill_audit --role dev --record     # append to state/fills.jsonl

Run repeatedly after a fill: each run appends one more mark, so the 5m / 15m /
60m / end-of-day series builds up from the record rather than from a timer.
"""

from __future__ import annotations

import argparse
import logging
import sys

from alpha import config, fills, ledger
from alpha.broker.alpaca import AlpacaPaper


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--role", default=None)
    p.add_argument("--record", action="store_true", help="append the audit to state/fills.jsonl")
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING)
    config.load_env()
    client = AlpacaPaper(role=args.role)

    submitted = [r for r in ledger.read_all() if r.get("action") == "submitted"
                 and r.get("alpaca_order_id")]
    if not submitted:
        print("no submitted orders in the ledger -- nothing to audit (an absence, not a pass)")
        return 0
    for row in submitted:
        a = fills.audit(client, row)
        print(fills.to_json(a))
        if args.record:
            fills.record(a)
    if args.record:
        ok, msg = ledger.verify_chain("fills")
        print("fills ledger:", msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
