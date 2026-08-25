"""One decision pass over a universe. The agent's main entry point.

    python -m scripts.run_pass --expiry 2026-08-28 --dry-run
    python -m scripts.run_pass --expiry 2026-08-28 --profile maximum --live
    python -m scripts.run_pass --role exp1 --profile maximum --live

`--dry-run` is the default and `--live` must be typed. The asymmetry is
deliberate: the failure that costs something is an unintended order, never an
unintended dry run.
"""

from __future__ import annotations

import argparse
import logging
import sys

from alpha import config, ledger, runner
from alpha.brains import vol_gap
from alpha.broker.alpaca import AlpacaPaper

#: Starting universe. Liquid, optionable, and spanning several volatility
#: regimes so the structure enumeration has something to disagree about. The
#: catalyst names from docs/STRATEGY.md are here on purpose.
UNIVERSE = ["SPY", "QQQ", "IWM", "NVDA", "AVGO", "AMD", "TSLA", "META",
            "AAPL", "MSFT", "GOOGL", "AMZN", "NIO", "PANW", "SMH"]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--expiry", required=True, help="YYYY-MM-DD")
    p.add_argument("--role", default=None, help="account role (default: AAT_ACCOUNT_ROLE)")
    p.add_argument("--profile", default=None, choices=sorted(__import__(
        "alpha.engine.sizing", fromlist=["x"]).PROFILES))
    p.add_argument("--horizon", type=float, default=3.0, help="forecast horizon in days")
    p.add_argument("--universe", nargs="*", default=UNIVERSE)
    p.add_argument("--live", action="store_true", help="actually send orders")
    p.add_argument("--field-leader", type=float, default=None,
                   help="estimated podium return, e.g. 0.25 for +25%%")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config.load_env()
    client = AlpacaPaper(role=args.role)

    forecasts = []
    for symbol in args.universe:
        try:
            forecasts.append(vol_gap.forecast(client, symbol, horizon_days=args.horizon))
        except Exception as exc:                                    # noqa: BLE001
            logging.warning("%s: no forecast -- %s", symbol, str(exc)[:120])

    if not forecasts:
        logging.error("no forecasts produced; refusing to run an empty pass")
        return 1

    result = runner.run_pass(
        client, forecasts, expiry=args.expiry, risk_profile=args.profile,
        dry_run=not args.live, field_leader_estimate=args.field_leader,
    )
    ok, msg = ledger.verify_chain()
    logging.info("considered=%d submitted=%d refused=%d errors=%d | ledger: %s",
                 result.considered, result.submitted, result.refused, result.errors, msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
