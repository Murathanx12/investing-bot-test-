"""Protective stops that live AT THE VENUE, not in our polling loop.

WHY THIS FILE EXISTS
====================
`alpha/engine/equity.py` charges every share position a stress-loss of
`STOP_FRACTION + gap` and calls the 3% part a stop. It was not a stop. It was a
CHARGE. The only thing that ever sold a losing position was `exits.manage`,
which runs when `scripts.agent_loop` gets to it -- every 5 minutes at best, and
never between 16:00 and the next session's first pass. A long filled at 15:58 ET
on a Friday had nothing standing behind it until Monday 09:35.

The night audit (`docs/night/2026-08-26_EXECUTION_AUDIT.md`, defect 1) ranked
this first of seven: our surface has none of the rival repos' bracket-child TIF
bugs because we have no bracket children -- and no stop either. That is the
mirror image of the same failure and it is worse, because a TIF bug is visible
in an order list and an absent order is visible nowhere.

THE THREE RULES, EACH OF WHICH HAS A WAY TO KILL YOU
----------------------------------------------------
1. **A stop is placed only for a position that exists**, sized to the qty the
   venue actually reports. Sizing to the order's `qty` rather than the fill's
   would over-sell a partial fill, and an over-sold long is a short.
2. **A stop is CANCELLED BEFORE the position under it is closed.** This is the
   rule that matters most. `close_position` is a market DELETE; if a resting
   sell-stop survives the close it has nothing left to sell, and the next time
   it triggers it OPENS A SHORT in an account whose book model says the symbol
   is flat. That is how a protective order becomes an unbounded one.
3. **Orphans are swept every pass.** Rule 2 covers the exit we perform; rule 3
   covers the exit we did not -- a manual close, a venue-side liquidation, a
   position that expired out from under its stop.

WHY NOT A BRACKET / OTO ORDER
-----------------------------
Because the entry is a DAY limit that frequently does not fill, and a bracket
ties the child's lifetime to a parent whose TIF we would then have to reason
about. Four of the nine rival repos in the digest are broken in exactly that
seam. A separate, independently-identified GTC order has no parent to inherit
anything from, and `ensure()` is idempotent by reading the venue rather than by
remembering what it did.

IDENTIFICATION
--------------
Ours are the open orders whose `client_order_id` starts with `aat-stop-`. We
never cancel an order we did not place: a human order resting on the same symbol
is left alone, and if it makes the stop redundant that is the human's call.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal

logger = logging.getLogger(__name__)

#: Every protective stop we place carries this `client_order_id` prefix. It is
#: the ONLY thing that distinguishes our orders from a human's, so it is checked
#: before any cancel.
STOP_PREFIX = "aat-stop-"

#: Terminal-ish states an order can be in and still be listed. `status=open`
#: should not return these, but the guard is cheap and a cancelled order we
#: treat as live would suppress a real stop.
_LIVE_STATES = frozenset({"new", "accepted", "held", "pending_new", "accepted_for_bidding",
                          "partially_filled", "replaced", "calculated", "stopped",
                          "pending_replace", "suspended"})


def stop_client_order_id(symbol: str, qty: int, stop_price: float) -> str:
    """Deterministic in the inputs, so a re-place after a size change is a NEW id.

    Idempotency does not rest on this -- it rests on reading the venue's open
    orders in `ensure()`. This exists so that two identical intents cannot
    double-place inside one pass, and so the id is greppable in an audit.
    """
    digest = hashlib.sha256(f"{symbol}|{qty}|{stop_price:.2f}".encode()).hexdigest()[:24]
    return f"{STOP_PREFIX}{digest}"


def is_ours(order: dict[str, Any]) -> bool:
    return str(order.get("client_order_id") or "").startswith(STOP_PREFIX)


def _live(order: dict[str, Any]) -> bool:
    status = str(order.get("status") or "").lower()
    return status in _LIVE_STATES or status == ""


def stopped_today(client: AlpacaPaper, *, now: datetime | None = None) -> set[str]:
    """Symbols whose PROTECTIVE STOP filled during today's session (ET).

    28 Aug: nine basket names stopped at 10:01-10:12 ET; the 10:30 entry pass
    would have re-bought every one of them (still 'near high' by the brain's
    rule) and re-stopped them at 11:00. `held_underlyings` is blind to a
    position that no longer exists, so this reads the venue's CLOSED orders.
    """
    now = now or datetime.now(timezone.utc)
    day_start_et = (now - timedelta(hours=4)).strftime("%Y-%m-%dT00:00:00-04:00")
    out: set[str] = set()
    for order in client._request("GET", "/v2/orders", params={"status": "closed", "after": day_start_et, "limit": 500}) or []:
        if is_ours(order) and order.get("status") == "filled":
            out.add(str(order.get("symbol") or ""))
    return {s for s in out if s}


def open_stops(client: AlpacaPaper) -> dict[str, list[dict[str, Any]]]:
    """Our live protective stops at the venue, by symbol."""
    out: dict[str, list[dict[str, Any]]] = {}
    for order in client.orders(status="open"):
        if not is_ours(order) or not _live(order):
            continue
        sym = str(order.get("symbol") or "")
        if sym:
            out.setdefault(sym, []).append(order)
    return out


def stop_price_for(position: dict[str, Any], stop_fraction: float) -> tuple[float, str]:
    """Stop price and the side that closes this position.

    Read from the venue's `avg_entry_price`, never from our ledger: a partial
    fill and a re-fill at a different price both land here correctly, and the
    venue is the thing the P&L is computed against.
    """
    entry = abs(float(position.get("avg_entry_price") or 0.0))
    qty = float(position.get("qty") or 0.0)
    if entry <= 0.0 or qty == 0.0:
        return 0.0, ""
    if qty > 0:  # long -> a SELL stop underneath
        return round(entry * (1.0 - stop_fraction), 2), "sell"
    return round(entry * (1.0 + stop_fraction), 2), "buy"


def build_stop(position: dict[str, Any], stop_fraction: float) -> dict[str, Any] | None:
    """The order payload, or None when this position cannot carry one."""
    symbol = str(position.get("symbol") or "")
    if (position.get("asset_class") or "") != "us_equity" or not symbol:
        return None  # options are closed by `exits`, not stopped; see module docstring
    qty = abs(int(float(position.get("qty") or 0.0)))
    if qty < 1:
        return None
    price, side = stop_price_for(position, stop_fraction)
    if price <= 0.0 or not side:
        return None
    return {
        "symbol": symbol, "qty": str(qty), "side": side,
        "type": "stop", "stop_price": f"{price:.2f}",
        "time_in_force": "gtc",
        "client_order_id": stop_client_order_id(symbol, qty, price),
    }


def cancel_for(client: AlpacaPaper, symbol: str, *, dry_run: bool = False) -> int:
    """Cancel OUR stops on `symbol`. Call this BEFORE closing the position.

    Returns the number cancelled. A failure to cancel is raised, not swallowed:
    closing a position while its stop rests is the one sequence this module
    exists to prevent, so the caller must be able to decide not to close.
    """
    stops = open_stops(client).get(symbol, [])
    if dry_run:
        return len(stops)
    n = 0
    for order in stops:
        oid = str(order.get("id") or "")
        if not oid:
            continue
        client.cancel_order(oid)
        n += 1
        logger.info("cancelled protective stop %s on %s before closing", oid, symbol)
    return n


def sweep_orphans(client: AlpacaPaper, positions: list[dict[str, Any]] | None = None,
                  *, dry_run: bool = False) -> list[str]:
    """Cancel stops whose position is gone. An orphan sell-stop OPENS a short."""
    positions = positions if positions is not None else client.positions()
    held = {str(p.get("symbol") or ""): abs(float(p.get("qty") or 0.0)) for p in positions}
    killed: list[str] = []
    for symbol, orders in open_stops(client).items():
        if held.get(symbol, 0.0) > 0.0:
            continue
        for order in orders:
            oid = str(order.get("id") or "")
            if not oid:
                continue
            if not dry_run:
                client.cancel_order(oid)
            killed.append(f"{symbol}:{oid}")
            logger.warning("ORPHAN protective stop on %s with no position -- cancelled (%s)",
                           symbol, oid)
    return killed


def ensure(client: AlpacaPaper, positions: list[dict[str, Any]] | None = None,
           *, stop_fraction: float | None = None, dry_run: bool = False,
           exclude_qty: dict[str, int] | None = None) -> dict[str, Any]:
    """Every share position ends this call with a live stop at the venue, or a
    recorded reason why it does not.

    Idempotent: it reads the venue's open orders rather than remembering. Safe
    to call from every `manage` pass and after every restart.
    """
    if stop_fraction is None:
        from alpha.engine import equity as _equity
        stop_fraction = _equity.stop_fraction()

    positions = positions if positions is not None else client.positions()
    existing = open_stops(client)
    summary: dict[str, Any] = {"placed": [], "kept": [], "resized": [], "refused": [],
                               "orphans": sweep_orphans(client, positions, dry_run=dry_run)}

    exclude_qty = exclude_qty or {}
    for position in positions:
        # A pair's HEDGE shares carry no stop of their own: a stop that fires on
        # the hedge alone leaves an unhedged short, which is the one state the
        # pair exists to avoid. They leave with their short leg (`alpha.exits`).
        # Only the part of the position that is NOT a live hedge is stopped.
        sym0 = str(position.get("symbol") or "")
        if sym0 in exclude_qty and exclude_qty[sym0] > 0:
            free = int(float(position.get("qty") or 0.0)) - int(exclude_qty[sym0])
            if free < 1:
                summary["refused"].append(f"{sym0}: hedge leg of a live pair, no stop of its own")
                continue
            position = {**position, "qty": str(free)}
        order = build_stop(position, stop_fraction)
        if order is None:
            continue
        symbol = order["symbol"]
        want_qty = int(order["qty"])
        live = existing.get(symbol, [])
        covered = sum(int(float(o.get("qty") or 0.0)) for o in live)
        if covered >= want_qty and live:
            summary["kept"].append(f"{symbol} x{covered}")
            continue
        if live:
            # A partial fill that later completed: the resting stop covers less
            # than the position. Cancel and re-place at the full size rather
            # than stacking, so the venue holds exactly one stop per symbol.
            for o in live:
                oid = str(o.get("id") or "")
                if oid and not dry_run:
                    client.cancel_order(oid)
            summary["resized"].append(f"{symbol} {covered}->{want_qty}")

        if dry_run:
            summary["placed"].append(f"DRY {symbol} {order['side']} x{want_qty} @ {order['stop_price']}")
            continue
        try:
            placed = client.submit_protective_stop(order)
            summary["placed"].append(f"{symbol} {order['side']} x{want_qty} @ {order['stop_price']}")
            _record(symbol, order, placed.get("id") if isinstance(placed, dict) else None, None)
            logger.info("protective stop placed %s %s x%d @ %s", symbol, order["side"],
                        want_qty, order["stop_price"])
        except BrokerRefusal as exc:
            # The usual cause is a stop already through the market -- the venue
            # refuses a sell-stop at or above the last trade. That position is
            # ALREADY past its stop, so `exits.evaluate` closes it on this same
            # pass; the refusal is recorded, not retried into a loop.
            summary["refused"].append(f"{symbol}: {exc}")
            _record(symbol, order, None, str(exc))
            logger.warning("protective stop REFUSED on %s: %s", symbol, str(exc)[:200])
    return summary


def _record(symbol: str, order: dict[str, Any], order_id: str | None, error: str | None) -> None:
    """Append-only audit of every protective stop. Separate from the decision
    ledger, whose rows are hash-chained decisions and must not gain a second
    meaning."""
    from alpha import ledger
    from pathlib import Path

    path = Path(ledger.LEDGER_DIR) / "protective_stops.jsonl"
    row = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol, "side": order.get("side"), "qty": order.get("qty"),
        "stop_price": order.get("stop_price"),
        "client_order_id": order.get("client_order_id"),
        "alpaca_order_id": order_id, "error": error,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError as exc:  # an audit that cannot be written must not stop a stop
        logger.warning("could not append protective stop audit: %s", exc)
