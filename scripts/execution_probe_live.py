"""COMPETITION_EXECUTION_PROBE_v1 -- the LIVE half. Sends, observes, cancels.

    AAT_ACCOUNT_ROLE=staging python -m scripts.execution_probe_live --yes-i-mean-it

`scripts/execution_probe.py` validates every payload locally and, in --live
mode, prints instructions for a human to send them one at a time. That was
never done (`docs/NEXT_SESSION_2026-08-28_EXECUTE.md`, open item 1), so every
claim about which order shapes Alpaca accepts came from documentation.

This file is the attended sweep, written so that it CANNOT leave a position:

* every payload is priced so that it cannot fill -- a $0.01 debit on a spread
  that costs dollars, a $0.05 bid on a put worth more, an equity LIMIT at a
  price far below the market. A market-day equity order is sent ONLY when the
  venue clock says the market is CLOSED, so it queues and is cancelled before
  the open. If the market is open that shape is skipped and said so;
* every accepted order is cancelled immediately and the cancel is verified by
  re-reading the order;
* the role is refused unless it is one of the rehearsal roles. `competition`
  can never run this;
* the whole result is written to `state/evidence/execution_probe_<role>.json`
  so the next reader has a receipt, not a memory.

The verdict per shape is ACCEPTED / REJECTED(<venue text>) against the
`expect` column, which is the only reason to run it: a probe that records what
happened without a prediction cannot tell "works" from "fails as predicted".
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from alpha import config, timing
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal

REHEARSAL_ROLES = {"dev", "staging", "exp1", "pead"}

# 2026-09-18 monthly, verified to exist on the venue on 28 Aug (OI 59,312 on
# the 700 put). Spot was ~771, so every strike below is OTM.
PUT_700 = "SPY260918P00700000"
PUT_690 = "SPY260918P00690000"
PUT_755 = "SPY260918P00755000"
PUT_716 = "SPY260918P00716000"


def shapes(market_open: bool) -> list[dict]:
    out = [
        {"name": "equity LIMIT day, unfillable price",
         "payload": {"symbol": "SPY", "qty": 1, "side": "buy", "type": "limit",
                     "limit_price": "100.00", "time_in_force": "day"},
         "expect": "accepted"},
        {"name": "equity MARKET-ON-CLOSE (cls)",
         "payload": {"symbol": "SPY", "qty": 1, "side": "buy", "type": "market",
                     "time_in_force": "cls"},
         "expect": "accepted before 15:50 ET, REJECTED after",
         "skip_if_open": True},
        {"name": "equity limit-on-close (loc), unfillable",
         "payload": {"symbol": "SPY", "qty": 1, "side": "buy", "type": "limit",
                     "limit_price": "100.00", "time_in_force": "cls"},
         "expect": "accepted before 15:50 ET"},
        {"name": "single-leg option limit day, unfillable",
         "payload": {"symbol": PUT_700, "qty": 1, "side": "buy", "type": "limit",
                     "limit_price": "0.01", "time_in_force": "day"},
         "expect": "accepted at options level 2+"},
        {"name": "single-leg option with cls  (THE v1 BUG)",
         "payload": {"symbol": PUT_700, "qty": 1, "side": "buy", "type": "limit",
                     "limit_price": "0.01", "time_in_force": "cls"},
         "expect": "REJECTED -- options accept tif=day only"},
        {"name": "multileg DEBIT spread, limit day, unfillable",
         "payload": {"order_class": "mleg", "qty": 1, "type": "limit",
                     "limit_price": "0.01", "time_in_force": "day",
                     "legs": [
                         {"symbol": PUT_700, "side": "buy", "ratio_qty": "1",
                          "position_intent": "buy_to_open"},
                         {"symbol": PUT_690, "side": "sell", "ratio_qty": "1",
                          "position_intent": "sell_to_open"}]},
         "expect": "accepted at options LEVEL 3 ONLY"},
        {"name": "multileg CREDIT spread, limit day, unfillable credit",
         # Alpaca mleg: a NEGATIVE limit is a net credit. Asking for a $30 credit
         # on a $39-wide spread that trades near $8 cannot fill.
         "payload": {"order_class": "mleg", "qty": 1, "type": "limit",
                     "limit_price": "-30.00", "time_in_force": "day",
                     "legs": [
                         {"symbol": PUT_755, "side": "sell", "ratio_qty": "1",
                          "position_intent": "sell_to_open"},
                         {"symbol": PUT_716, "side": "buy", "ratio_qty": "1",
                          "position_intent": "buy_to_open"}]},
         "expect": "accepted at level 3 -- proves the credit-spread payload shape"},
        {"name": "multileg spread as a MARKET order",
         "payload": {"order_class": "mleg", "qty": 1, "type": "market",
                     "time_in_force": "day",
                     "legs": [
                         {"symbol": PUT_700, "side": "buy", "ratio_qty": "1",
                          "position_intent": "buy_to_open"},
                         {"symbol": PUT_690, "side": "sell", "ratio_qty": "1",
                          "position_intent": "sell_to_open"}]},
         "expect": "refused by US before the venue",
         "never_send": True},
        {"name": "multileg limit WITHOUT a limit price",
         "payload": {"order_class": "mleg", "qty": 1, "type": "limit",
                     "time_in_force": "day",
                     "legs": [{"symbol": PUT_700, "side": "buy", "ratio_qty": "1",
                               "position_intent": "buy_to_open"}]},
         "expect": "REJECTED -- 'limit price is required for limit orders'"},
    ]
    if market_open:
        for s in out:
            if s.get("skip_if_open"):
                s["never_send"] = True
                s["expect"] += "  (SKIPPED: market open, a cls market order could fill)"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes-i-mean-it", action="store_true", dest="confirmed")
    args = ap.parse_args()
    config.load_env()
    role = config.role()
    if role not in REHEARSAL_ROLES:
        print(f"REFUSED: role {role!r} is not a rehearsal role {sorted(REHEARSAL_ROLES)}")
        return 2
    if not args.confirmed:
        print("dry: pass --yes-i-mean-it to send. Nothing sent.")
        return 0

    client = AlpacaPaper()
    acct = client.account()
    clock = client.clock()
    is_open = bool(clock.get("is_open"))
    num = acct.get("account_number")
    print(f"LIVE role={role} account={num} level={acct.get('options_approved_level')} "
          f"market_open={is_open} equity={acct.get('equity')}")
    if float(acct.get("equity") or 0) <= 0:
        print("REFUSED: unreadable equity")
        return 2

    results = []
    for shape in shapes(is_open):
        name, payload = shape["name"], shape["payload"]
        local = timing.validate_payload(payload)
        rec = {"name": name, "expect": shape["expect"], "payload": payload,
               "local_refusals": local}
        if shape.get("never_send") or local:
            rec["venue"] = "NOT SENT" + (" (refused locally)" if local else "")
            results.append(rec)
            print(f"-- {name:<52} {rec['venue']}")
            continue
        decision_id = f"probe:{role}:{name}:{datetime.now(timezone.utc).isoformat()}"
        snap = {"probe": True, "clock": clock}
        try:
            resp = client.submit(payload, decision_id=decision_id, quote_snapshot=snap)
            oid = resp.get("id")
            rec["venue"] = f"ACCEPTED status={resp.get('status')} id={oid}"
            print(f"-- {name:<52} ACCEPTED status={resp.get('status')}")
            # cancel and verify
            time.sleep(0.5)
            client.cancel_order(oid)
            time.sleep(0.8)
            after = client._request("GET", f"/v2/orders/{oid}")
            rec["after_cancel"] = after.get("status")
            print(f"     after cancel: {after.get('status')}")
        except BrokerRefusal as exc:
            rec["venue"] = f"REJECTED {str(exc)[:200]}"
            print(f"-- {name:<52} REJECTED\n     {str(exc)[:160]}")
        results.append(rec)

    # nothing may be left behind
    open_orders = client.orders(status="open")
    positions = client.positions()
    for o in open_orders:
        print(f"!! open order left: {o.get('id')} {o.get('symbol')} -- cancelling")
        client.cancel_order(o["id"])
    left = {"open_orders_after_sweep": len(client.orders(status="open")),
            "positions": len(positions)}
    print(f"\nleft behind: {left}")

    out = Path(config.ledger_dir() if hasattr(config, "ledger_dir") else "state") / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"execution_probe_{role}.json"
    path.write_text(json.dumps({"role": role, "account": num, "at_utc": datetime.now(timezone.utc).isoformat(),
                                "market_open": is_open, "options_level": acct.get("options_approved_level"),
                                "results": results, "left": left}, indent=1))
    print(f"receipt: {path}")
    return 0 if left["positions"] == 0 and left["open_orders_after_sweep"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
