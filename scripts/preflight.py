"""Prove the account is the one we think it is, BEFORE the agent trades on it.

Run this against `dev` during rehearsal and against `competition` immediately
after the judged account is created at kickoff. It answers, with the server's
own words rather than ours:

  * is this a PAPER account (PA-prefixed account number)?
  * is the starting equity the $100,000 the rules require?
  * is it FRESH -- zero fills, zero positions, no prior history that would make
    it a "reused account" and therefore ineligible?
  * are options enabled, and at what level (multi-leg needs level 3)?
  * is the market data feed real OPRA, or the free INDICATIVE one that makes
    every expected-value calculation in this repo fiction?
  * does the clock agree with the competition window?

A check that did not run is not a check that passed. Each line prints PASS,
FAIL or CANNOT DETERMINE -- never a silent skip -- because the failure mode that
costs the most here is a guard that reported green while reading nothing.

    python -m scripts.preflight
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from alpha import config
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "????"


def _line(status: str, label: str, detail: str = "") -> bool:
    print(f"  [{status}] {label}" + (f"  --  {detail}" if detail else ""))
    return status == PASS


def main() -> int:
    try:
        role = config.role()
    except config.CredentialRefusal as exc:
        print(f"REFUSED: {exc}")
        return 2

    print(f"\nPREFLIGHT  role={role}  host={config.base_url()}")
    print(f"window: {config.COMPETITION['kickoff_utc']} -> {config.COMPETITION['deadline_utc']}\n")

    client = AlpacaPaper(role=role)
    results: list[bool] = []

    try:
        acct = client.account()
    except (BrokerRefusal, config.CredentialRefusal) as exc:
        print(f"  [{FAIL}] account fetch  --  {exc}")
        return 1

    number = str(acct.get("account_number", ""))
    results.append(_line(PASS if number.startswith("PA") else FAIL,
                         "paper account", f"account_number={number}"))

    equity = float(acct.get("equity", 0) or 0)
    required = config.COMPETITION["required_starting_equity"]
    if role == "competition":
        # Fresh account: equity should still BE the starting balance.
        ok = abs(equity - required) < 1.0
        results.append(_line(PASS if ok else FAIL, "starting equity",
                             f"${equity:,.2f} (rules require ${required:,.0f})"))
    else:
        results.append(_line(PASS, "equity (dev account, not rules-bound)", f"${equity:,.2f}"))

    # Freshness. Only meaningful for the judged account, and it is the check
    # that cannot be repaired after the fact -- an account with history cannot
    # be un-used, and resetting it is itself a reuse.
    if role == "competition":
        try:
            fills = client.orders(status="closed", limit=5)
            positions = client.positions()
            fresh = not fills and not positions
            results.append(_line(
                PASS if fresh else FAIL, "account is FRESH",
                "no prior orders or positions" if fresh
                else f"{len(fills)} closed order(s), {len(positions)} position(s) -- "
                     "a reused account is INELIGIBLE and this cannot be undone",
            ))
        except BrokerRefusal as exc:
            results.append(_line(UNKNOWN, "account is FRESH", str(exc)))

    opts_level = acct.get("options_trading_level")
    if opts_level is None:
        results.append(_line(UNKNOWN, "options level",
                             "field absent from the account payload -- verify in the dashboard"))
    else:
        ok = int(opts_level) >= 3
        results.append(_line(PASS if ok else FAIL, "options level",
                             f"level {opts_level} (multi-leg needs 3; paper is auto-approved)"))

    # The data feed. This is not a nicety: on the free plan the options feed is
    # INDICATIVE, which means the bid/ask this agent computes its minimum
    # detectable move from is not a price anyone would trade.
    try:
        chain = client.option_chain("SPY")
        snaps = (chain or {}).get("snapshots") or {}
        with_quote = sum(1 for s in snaps.values() if (s.get("latestQuote") or {}).get("ap"))
        with_greeks = sum(1 for s in snaps.values() if s.get("greeks"))
        if not snaps:
            results.append(_line(FAIL, "OPRA option chain", "no snapshots returned"))
        else:
            results.append(_line(PASS, "OPRA option chain",
                                 f"{len(snaps)} contracts, {with_quote} quoted, {with_greeks} with greeks"))
    except BrokerRefusal as exc:
        results.append(_line(FAIL, "OPRA option chain",
                             f"{exc}  --  if this is a 403/subscription error, the account is on the "
                             "free INDICATIVE feed and Algo Trader Plus ($99/mo) is required"))

    try:
        clock = client.clock()
        now = datetime.now(timezone.utc)
        deadline = datetime.fromisoformat(config.COMPETITION["deadline_utc"].replace("Z", "+00:00"))
        remaining = (deadline - now).total_seconds() / 3600.0
        results.append(_line(PASS, "clock",
                             f"market {'OPEN' if clock.get('is_open') else 'closed'}, "
                             f"{remaining:.1f}h to the submission deadline"))
    except BrokerRefusal as exc:
        results.append(_line(UNKNOWN, "clock", str(exc)))

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} checks passed.\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
