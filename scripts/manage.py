"""Exit pass: evaluate every open position and close what earned it.

    python -m scripts.manage                 # dry run
    python -m scripts.manage --live
    python -m scripts.manage --role exp1 --live

Run this far more often than the entry pass. Entries are opportunities and can
wait for the next cycle; the deadline liquidation and the expiry rule cannot.
"""

from __future__ import annotations

import argparse
import logging
import sys

from alpha import config, exits, ledger
from alpha.broker.alpaca import AlpacaPaper


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--role", default=None)
    p.add_argument("--live", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config.load_env()
    # THE FLAG IS AUTHORITATIVE, AND IT IS MADE SO HERE RATHER THAN IN
    # `config.credentials`, so the mutation is visible at the entry point.
    # Every ledger stamp, book match and recovery score reads AAT_ACCOUNT_ROLE
    # from the environment; a `--role` that never reaches it writes rows under
    # the wrong name. `config.credentials` REFUSES if the two disagree, so this
    # only ever fills in a blank. (Audit defect 6.)
    if args.role:
        import os
        os.environ["AAT_ACCOUNT_ROLE"] = args.role.strip().lower()
    client = AlpacaPaper(role=args.role)

    et = exits.now_et()
    logging.info("exit pass at %s ET  (liquidate-by %s on judging day)",
                 et.strftime("%Y-%m-%d %H:%M"), exits.LIQUIDATE_BY_ET.strftime("%H:%M"))

    summary = exits.manage(
        client, deadline_utc=config.deadline_utc(), dry_run=not args.live
    )
    ok, msg = ledger.verify_chain()
    logging.info("checked=%d closed=%d held=%d errors=%d | ledger: %s",
                 summary["checked"], summary["closed"], summary["held"],
                 summary["errors"], msg)
    return 0 if ok and not summary["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
