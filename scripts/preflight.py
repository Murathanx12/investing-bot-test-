"""PRE-FLIGHT -- what the account looks like before the first competition order.

    python -m scripts.preflight                  # this account, full report
    python -m scripts.preflight --require-clean  # exit 1 unless the book is EMPTY

WHY THIS EXISTS
===============
The rehearsal book reached **72.9% of equity in true max loss** while every
individual structure was defined-risk and every admission check passed. Nothing
was violated; the checks simply never asked the question this asks.

The competition account starts from zero positions and has to prove each one
against a state it can see. This prints that state, and `--require-clean`
refuses to certify an account that has already been traded into.

WHAT IT REPORTS, AND WHY EACH LINE IS HERE
==========================================
equity / free capital       the denominator every other number divides by
true max loss               what the book loses if every structure goes wrong
premium-paid view           what it loses if you only count debits -- the
                            FLATTERING view, printed beside the honest one so
                            the gap is visible rather than selectable
effective N by RISK         how many bets this actually is (alpha/concentration)
largest thesis cluster      the concentration that killed a $20bn fund in July
open + in-flight orders     a resting order is exposure that no position shows
daily loss latch            whether today is already latched
loop liveness               a book nobody is managing is not a managed book

Nothing here trades or sizes. It reads and it refuses.
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timedelta, timezone

from alpha import (book as book_mod, book_limits, concentration, config, daybreak,
                   genesis, liveness)
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal


def _returns(client: AlpacaPaper, syms: list[str], days: int = 60) -> dict[str, list[float]]:
    if not syms:
        return {}
    start = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    try:
        bars = client.stock_bars_multi(sorted(syms), start=start, timeframe="1Day")
    except BrokerRefusal:
        return {}
    out = {}
    for sym, rows in bars.items():
        c = [float(r["c"]) for r in rows if r.get("c")]
        if len(c) > 5:
            out[sym] = [math.log(c[i] / c[i - 1]) for i in range(1, len(c)) if c[i - 1] > 0]
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--require-clean", action="store_true",
                   help="exit 1 unless the account holds no positions and no open orders")
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()

    acct = client.account()
    equity = float(acct.get("equity") or 0.0)
    cash = float(acct.get("cash") or 0.0)
    buying_power = float(acct.get("buying_power") or 0.0)
    positions = client.positions()
    try:
        open_orders = client.orders(status="open")
    except BrokerRefusal:
        open_orders = []

    print(f"PRE-FLIGHT  account {acct.get('account_number')}  role={config.account_role()}"
          if hasattr(config, "account_role") else
          f"PRE-FLIGHT  account {acct.get('account_number')}")
    print(f"  equity            ${equity:,.0f}")
    print(f"  cash              ${cash:,.0f}")
    print(f"  buying power      ${buying_power:,.0f}")
    print(f"  positions         {len(positions)}")
    print(f"  open orders       {len(open_orders)}"
          + ("   <- resting orders are exposure no position shows" if open_orders else ""))

    b = book_mod.read(client)
    tml = getattr(b, "max_loss_usd", 0.0) or 0.0
    ppd = getattr(b, "premium_paid_usd", 0.0) or 0.0
    print(f"\n  TRUE max loss     ${tml:,.0f}  = {100*tml/equity if equity else 0:.1f}% of equity")
    print(f"  premium-paid view ${ppd:,.0f}  = {100*ppd/equity if equity else 0:.1f}%"
          "   (the flattering view, printed so the gap is visible)")
    print(f"  book unbounded    {getattr(b, 'unbounded', None)}")
    print(f"  structures        {len(getattr(b, 'structures', []))}"
          f"   residual legs {len(getattr(b, 'residuals', []) or [])}")

    weights = concentration.weights_from_book(b)
    if weights:
        c = concentration.measure(weights, _returns(client, list(weights)))
        state, why = concentration.verdict(c)
        print(f"\n  CONCENTRATION     [{state}]")
        print(f"    {why}")
        top, tw = max(weights.items(), key=lambda kv: kv[1]), sum(weights.values())
        print(f"    largest single thesis: {top[0]} at {100*top[1]/tw:.1f}% of book max loss")
    else:
        print("\n  CONCENTRATION     no structures -- nothing to measure (a clean book)")

    # THE PROPOSED LIMITS, SHOWN AND NOT ENFORCED. Nothing refuses on these;
    # printing them is how the 28 Aug decision gets made from numbers rather
    # than from a paragraph. See docs/PROPOSAL_2026-08-26_COMPETITION_ADMISSION.md
    breaches = book_limits.evaluate(
        equity=equity, true_max_loss=tml, free_capital=cash,
        thesis_weights=weights or None,
        n_risk=(c.n_risk if weights and c else None))
    print("\n  PROPOSED LIMITS (not enforced -- nothing refuses on these)")
    if not breaches:
        print("    within every declared book limit")
    for br in breaches:          # not `b` -- that is the book, still in scope
        print(f"    [{br.limit}] {br.detail}")

    try:
        day = daybreak.read(client)
        print(f"\n  DAILY LATCH       {'LATCHED' if day.latched else 'not tripped'}")
        print(f"    {day.reason[:150]}")
    except Exception as exc:                                   # noqa: BLE001
        print(f"\n  DAILY LATCH       UNREADABLE ({type(exc).__name__}) -- treat as latched")

    ok_live, lines = liveness.report()
    print(f"\n  LOOP LIVENESS     {'ok' if ok_live else 'NOT HEALTHY'}")
    for line in lines[:4]:
        print(f"    {line[:150]}")

    # -- THE JUDGED ACCOUNT'S IDENTITY (alpha/genesis.py) --------------------
    # Every other check on this page is about the BOOK. This one is about WHICH
    # ACCOUNT the book is in, and it is the only check whose failure cannot be
    # fixed by trading differently. It REFUSES rather than reporting: a
    # denylisted number under the judged role means orders would land in the
    # -15.1% dev book, and every role-keyed guard in this repo would still pass.
    number = str(acct.get("account_number") or "")
    role_now = config.role()
    denied = genesis.DENIED_ACCOUNTS.get(number)
    if role_now == genesis.JUDGED_ROLE:
        print(f"\n  JUDGED ACCOUNT    {number}")
        if denied:
            print(f"    REFUSED -- DENYLISTED: {denied}")
            return 1
        ok_gen, gen_lines = genesis.verify(client, role=role_now)
        print(f"    genesis {'OK' if ok_gen else 'REFUSED'}")
        for line in gen_lines:
            print(f"    {line}")
        if not ok_gen:
            return 1
    elif denied:
        print(f"\n  ACCOUNT           {number} is denylisted for the judged role")
        print(f"    {denied}")
        print(f"    (current role is {role_now!r}, so this is a note, not a refusal)")

    if args.require_clean:
        dirty = []
        if positions:
            dirty.append(f"{len(positions)} open position(s)")
        if open_orders:
            dirty.append(f"{len(open_orders)} open order(s)")
        print()
        if dirty:
            print("REFUSED: this account is NOT clean -- " + ", ".join(dirty) + ".")
            print("  The competition account inherits no rehearsal book. A book assembled under")
            print("  the old admission rules has not proved itself under the new ones, and the")
            print("  rehearsal book reached 72.9% of equity in true max loss with every")
            print("  individual check passing.")
            return 1
        print("CLEAN: no positions, no open orders. The account is ready to prove each")
        print("  position against a state it can see.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
