"""One decision pass over a universe. The agent's main entry point.

    python -m scripts.run_pass --expiry 2026-08-28 --dry-run
    python -m scripts.run_pass --expiry 2026-08-28 --brains vol_gap,event_move --live
    python -m scripts.run_pass --role exp1 --profile maximum --live

`--dry-run` is the default and `--live` must be typed. The asymmetry is
deliberate: the failure that costs something is an unintended order, never an
unintended dry run.

Brains listed in `--shadow` forecast and enumerate but never execute.
"""

from __future__ import annotations

import argparse
import logging
import sys

from alpha import brains, config, ledger, runner
from alpha.broker.alpaca import AlpacaPaper

#: Starting universe. Liquid, optionable, spanning several volatility regimes.
UNIVERSE = ["SPY", "QQQ", "IWM", "NVDA", "AVGO", "AMD", "TSLA", "META",
            "AAPL", "MSFT", "GOOGL", "AMZN", "NIO", "PANW", "SMH"]

DEFAULT_BRAINS = "vol_gap,event_move,options_attention,narrative_dispersion,relay,post_event_drift"
#: Brains that WIDEN sigma by construction win the MDM comparison by construction
#: on long premium -- the sizer rewards disagreement, and a wider claim is a bigger
#: disagreement. They earn execution by beating the others in the counterfactual
#: ledger first, not by being loudest.
#:
#: `post_event_drift` is deliberately NOT on this list, and the reason the list
#: exists is the reason: it does the OPPOSITE of widening sigma. It quotes a
#: centre of +0.72% against a spread floored at the dispersion the backtest
#: measured, and it FALLS BACK to the later, smaller arrival number when it
#: cannot tell how late it is. A brain that cannot inflate its own edge does not
#: need the veto this list applies -- the MDM gate and the EV/max-loss ranker are
#: the gates it must pass, and on a 1%-of-spot edge the spread will refuse most
#: structures without help. It is `PRODUCT_EXPERIMENT` on paper accounts; the
#: evidence is in state/source_pead_decompose.json and _horizon.json.
DEFAULT_SHADOW = "options_attention,narrative_dispersion,relay"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--expiry", required=True, help="YYYY-MM-DD")
    p.add_argument("--role", default=None, help="account role (default: AAT_ACCOUNT_ROLE)")
    p.add_argument("--profile", default=None, choices=sorted(__import__(
        "alpha.engine.sizing", fromlist=["x"]).PROFILES))
    p.add_argument("--horizon", type=float, default=3.0, help="forecast horizon in days")
    p.add_argument("--universe", nargs="*", default=UNIVERSE)
    p.add_argument("--brains", default=DEFAULT_BRAINS, help="comma list of brains to run")
    p.add_argument("--shadow", default=DEFAULT_SHADOW,
                   help="comma list of brains that may not execute (pass '' to let all execute)")
    p.add_argument("--live", action="store_true", help="actually send orders")
    p.add_argument("--candidates", action="store_true",
                   help="add today's whole-market candidates (state/candidates/<date>.json) to the universe")
    p.add_argument("--field-leader", type=float, default=None,
                   help="estimated podium return, e.g. 0.25 for +25%%")
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

    universe_syms = list(args.universe)
    if args.candidates:
        import json
        from pathlib import Path

        files = sorted((Path("state") / "candidates").glob("*.json"))
        if files:
            data = json.loads(files[-1].read_text(encoding="utf-8"))
            extra = [c["symbol"] for c in data.get("candidates", []) if c["symbol"] not in universe_syms]
            universe_syms += extra
            logging.info("candidates from %s: +%d symbols (%s)", files[-1].name, len(extra), ",".join(extra[:12]))
        else:
            logging.warning("--candidates given but no state/candidates/*.json exists; universe unchanged")
    args.universe = universe_syms
    names = [b.strip() for b in args.brains.split(",") if b.strip()]
    unknown = [b for b in names if b not in brains.BRAINS]
    if unknown:
        logging.error("unknown brains %s; have %s", unknown, sorted(brains.BRAINS))
        return 2
    forecasts, declined = brains.forecast_all(
        client, args.universe, args.horizon, brains=names, expiries=[args.expiry])
    for d in declined:
        logging.info("declined %-20s %-6s %s", d["brain"], d["symbol"], d["why"])
    if not forecasts:
        logging.error("no forecasts produced; refusing to run an empty pass")
        return 1

    result = runner.run_pass(
        client, forecasts, expiry=args.expiry, risk_profile=args.profile,
        dry_run=not args.live, field_leader_estimate=args.field_leader,
        shadow_brains=tuple(b.strip() for b in args.shadow.split(",") if b.strip()),
    )
    ok, msg = ledger.verify_chain()
    logging.info("brains=%d forecasts=%d declined=%d | considered=%d submitted=%d refused=%d "
                 "shadow=%d errors=%d | ledger: %s", len(names), len(forecasts), len(declined),
                 result.considered, result.submitted, result.refused, result.shadow,
                 result.errors, msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
