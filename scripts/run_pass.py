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

from alpha import brains, config, genesis, ledger, runner
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
    p.add_argument("--horizon", type=float, default=None,
                   help="forecast horizon in TRADING SESSIONS. Default: derived from --expiry. "
                        "This was hardcoded to 3.0 until 27 Aug, so every brain was asked for "
                        "three sessions of movement however long the option actually had -- and "
                        "on the last day before expiry that overstated the width by sqrt(3).")
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

    # -- THE JUDGED ACCOUNT MAY NOT BE TRADED WITHOUT A GENESIS RECORD -------
    # `scripts/preflight` prints this too, but preflight is something a person
    # chooses to run. This is on the path every order actually takes, and it is
    # the difference between a limit and a proposal. Non-judged roles are
    # unaffected: the whole point of the record is that only ONE account is
    # being judged.
    if config.role() == genesis.JUDGED_ROLE and args.live:
        ok_gen, gen_lines = genesis.verify(client, role=genesis.JUDGED_ROLE)
        if not ok_gen:
            logging.error("REFUSED -- the judged account cannot be traded:")
            for line in gen_lines:
                logging.error("  %s", line)
            return 2

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
    horizon = args.horizon
    if horizon is None:
        from datetime import datetime, timezone
        from alpha.engine.structures import _days as _sessions_to

        class _Now:                       # _days only reads .fetched_at
            fetched_at = datetime.now(timezone.utc)
        horizon = _sessions_to(_Now(), args.expiry)
        logging.info("horizon derived from expiry %s: %.2f trading sessions", args.expiry, horizon)
    if horizon <= 0:
        logging.error("horizon resolved to %.2f sessions; refusing to forecast a zero-length window", horizon)
        return 2
    forecasts, declined = brains.forecast_all(
        client, args.universe, horizon, brains=names, expiries=[args.expiry])
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
                 "dry_run=%d shadow=%d errors=%d | ledger: %s", len(names), len(forecasts),
                 len(declined), result.considered, result.submitted, result.refused,
                 result.dry_run, result.shadow, result.errors, msg)
    # WHY it refused, which is the only part that says what to work on next. A
    # pass that refused everything on `risk` and one that refused everything on
    # `evidence` print the same headline and call for opposite work.
    logging.info("refusals by class: %s", result.decomposition())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
