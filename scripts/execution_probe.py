"""COMPETITION_EXECUTION_PROBE_v1 -- prove the payloads BEFORE the judged account.

    python -m scripts.execution_probe                      # dry run, default
    AAT_ACCOUNT_ROLE=dev python -m scripts.execution_probe --live --yes-i-mean-it

WHY
===
`docs/FINDING_2026-08-28_THE_BOOK_COULD_NOT_HAVE_BEEN_PLACED.md`: v1 of the book
instructed "enter MARKET-ON-CLOSE" for a core made of multileg options, which
Alpaca rejects outright. That was caught by reading the venue's documentation.
Documentation is not a fill.

This enumerates every order shape the book intends to use and checks each one.
The DRY RUN half is free and complete: `alpha.timing.validate_payload` knows the
venue's TIF rules, so anything it rejects would have been rejected by Alpaca. A
live rehearsal only has to test what genuinely needs a broker round trip --
whether the account is APPROVED for the structure, and whether a multileg
payload is accepted as written.

NOTHING IS PLACED WITHOUT TWO EXPLICIT FLAGS
============================================
`--live` alone is not enough. Placing orders is a capital action even on paper:
it moves a book that other measurements read, and the whole reason this file
exists is that an unexercised assumption cost a design. So the second flag is
required and is deliberately awkward to type.

WHAT A LIVE RUN MUST NOT USE
============================
Never the judged competition account. `alpha/genesis.py` keeps a denylist keyed
on the venue's own `account_number`; a rehearsal belongs on `dev` or a scratch
book, and the probe refuses any role it was not explicitly given.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, time, timedelta

from alpha import config, playbook, timing

#: Every shape the book can emit. `expect` is what SHOULD happen -- a probe that
#: only records what it observed cannot distinguish "works" from "fails the way
#: we predicted", and the second is the more useful result.
SHAPES = [
    {"name": "equity market day",
     "payload": {"symbol": "SPY", "qty": 1, "side": "buy", "type": "market",
                 "time_in_force": "day"},
     "expect": "accepted"},
    {"name": "equity MARKET-ON-CLOSE (cls)",
     "payload": {"symbol": "SPY", "qty": 1, "side": "buy", "type": "market",
                 "time_in_force": "cls"},
     "expect": "accepted before 15:50 ET, REJECTED after"},
    {"name": "equity limit-on-close (loc)",
     "payload": {"symbol": "SPY", "qty": 1, "side": "buy", "type": "limit",
                 "limit_price": "1.00", "time_in_force": "cls"},
     "expect": "accepted before 15:50 ET"},
    {"name": "single-leg option limit day",
     "payload": {"symbol": "SPY260918P00700000", "qty": 1, "side": "buy",
                 "type": "limit", "limit_price": "0.05",
                 "time_in_force": "day"},
     "expect": "accepted at options level 2+"},
    {"name": "single-leg option with cls  (THE v1 BUG)",
     "payload": {"symbol": "SPY260918P00700000", "qty": 1, "side": "buy",
                 "type": "limit", "limit_price": "0.05",
                 "time_in_force": "cls"},
     "expect": "REJECTED -- options accept tif=day only"},
    {"name": "multileg credit spread, limit day",
     "payload": {"order_class": "mleg", "qty": 1, "type": "limit",
                 "limit_price": "1.00", "time_in_force": "day",
                 "legs": [
                     {"symbol": "SPY260918P00755000", "side": "sell",
                      "ratio_qty": "1", "position_intent": "sell_to_open"},
                     {"symbol": "SPY260918P00716000", "side": "buy",
                      "ratio_qty": "1", "position_intent": "buy_to_open"}]},
     "expect": "accepted at options LEVEL 3 ONLY -- level 2 cannot place spreads"},
    {"name": "multileg spread as a MARKET order",
     "payload": {"order_class": "mleg", "qty": 1, "type": "market",
                 "time_in_force": "day",
                 "legs": [
                     {"symbol": "SPY260918P00755000", "side": "sell",
                      "ratio_qty": "1", "position_intent": "sell_to_open"},
                     {"symbol": "SPY260918P00716000", "side": "buy",
                      "ratio_qty": "1", "position_intent": "buy_to_open"}]},
     "expect": "refused by US -- an unbounded fill on a wide spread quote"},
    {"name": "multileg limit WITHOUT a limit price",
     "payload": {"order_class": "mleg", "qty": 1, "type": "limit",
                 "time_in_force": "day",
                 "legs": [
                     {"symbol": "SPY260918P00755000", "side": "sell",
                      "ratio_qty": "1", "position_intent": "sell_to_open"}]},
     "expect": "REJECTED -- 'limit price is required for limit orders'"},
]


def dry_run() -> tuple[int, int]:
    print("DRY RUN -- payload validation only. No venue contact.\n")
    ok = bad = 0
    for shape in SHAPES:
        problems = timing.validate_payload(shape["payload"])
        verdict = "REFUSED HERE" if problems else "passes local validation"
        flag = "  " if not problems else "!!"
        print(f"{flag} {shape['name']:<42} {verdict}")
        print(f"     expect at venue: {shape['expect']}")
        for m in problems:
            print(f"     -> {m}")
        ok, bad = (ok + 1, bad) if not problems else (ok, bad + 1)
    return ok, bad


def live_run(role: str) -> int:
    from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal

    client = AlpacaPaper()
    acct = client.account()
    num = acct.get("account_number")
    lvl = acct.get("options_approved_level")
    print(f"\nLIVE against role={role} account={num} "
          f"options_approved_level={lvl}")

    struct, why = playbook.structure_for_level(
        int(lvl) if lvl is not None else None)
    print(f"  structure permitted: {struct}  ({why})")
    if struct != "short_put_spread":
        print("  NOTE: this account cannot place the book's core structure.")

    print("\n  A live rehearsal is NOT implemented as an automatic order sweep.")
    print("  Each shape must be sent, observed and CANCELLED by a human who is")
    print("  watching the book, because a probe that places eight orders and")
    print("  loses track of one has created a position nobody decided to hold.")
    print("  Use the payloads above with `client.submit(...)` one at a time.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--yes-i-mean-it", action="store_true",
                    dest="confirmed",
                    help="required alongside --live; deliberately awkward")
    args = ap.parse_args()
    config.load_env()

    print("COMPETITION EXECUTION PROBE v1")
    print("=" * 78)
    ok, bad = dry_run()
    print(f"\n{ok} shapes pass local validation, {bad} refused before the venue.")

    # The two shapes we EXPECT to be refused locally are the v1 bug and the
    # market-order-on-a-spread. A run where nothing is refused means the
    # validator stopped working, which is worth failing over.
    if bad == 0:
        print("\nFAIL: no shape was refused. `timing.validate_payload` is "
              "supposed to catch the tif=cls option order and the multileg "
              "market order. A validator that passes everything is not a "
              "validator.")
        return 1

    if not args.live:
        print("\nDry run only. Add --live --yes-i-mean-it to contact the venue.")
        print("The venue half answers exactly two things the docs cannot: is "
              "this account APPROVED for spreads, and is the mleg payload "
              "accepted as written.")
        return 0
    if not args.confirmed:
        print("\nREFUSING: --live requires --yes-i-mean-it. Placing orders "
              "moves a book that other measurements read.")
        return 1

    import os
    role = os.getenv("AAT_ACCOUNT_ROLE", "")
    if not role:
        print("\nREFUSING: set AAT_ACCOUNT_ROLE explicitly. A rehearsal must "
              "never default onto whichever account happens to be configured.")
        return 1
    return live_run(role)


if __name__ == "__main__":
    raise SystemExit(main())
