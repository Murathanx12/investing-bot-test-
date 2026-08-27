"""PASSIVE_BETA_v2 -- the benchmark's state, read from the venue.

WHY v1 NEEDED A v2
==================
`PASSIVE_BETA_v1` named its convention "next regular-session open, market order"
and implemented it as `type=market, time_in_force=opg`. That is the correct
translation of the sentence. It also does not necessarily produce a position:
an OPG order is eligible **only for the opening auction**, and Alpaca cancels
any OPG order that is unfilled once the open has passed.

On 2026-08-27 the `market` account (`PA3I7VTCC0BM`) read:

    equity $100,000.00    positions 0    orders 1

which is the signature exactly: an order exists, no position does, and equity
has not moved off its seed. Meanwhile the seed script had printed `SUBMITTED`
and written a ledger row saying the arm was live, so every downstream reader --
`preflight`, the scoreboard, the handoff -- reported an ACTIVE benchmark that
did not exist. Nine days of "our arms versus the market" had no market in it.

**The defect is not the OPG order. It is that SUBMITTED was allowed to mean
SEEDED.** A submitted order is a request; a filled order is a fact. Everything
in this repo that says "the benchmark is active" now has to get that from a
position, and the state below is derived from the venue on every read rather
than latched into a file.

THE STATES
==========
    UNSEEDED           no order, no position. Nothing has been attempted.
    ORDER_SENT         an order exists and is still working. NOT active.
    EXPIRED_UNFILLED   the order reached a terminal state without filling. This
                       is a FAILURE that needs a person, and it is deliberately
                       not the same state as UNSEEDED -- "we tried and it did
                       not work" and "we never tried" call for different acts.
    ACTIVE             a position exists with positive quantity. The only state
                       in which a benchmark number may be quoted.
    OVERSEEDED         more than one position, or a position on a symbol the
                       contract does not name. A buy-and-hold arm that got
                       topped up is not a buy-and-hold record.

There is no state for "an order filled but we have not looked yet". A fill that
has not produced a position is not a fill this module will report.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Order statuses Alpaca uses for an order that will never fill now.
TERMINAL_UNFILLED = frozenset({"canceled", "cancelled", "expired", "rejected", "done_for_day",
                               "suspended", "stopped", "replaced"})

#: Statuses that mean the order is still capable of filling.
WORKING = frozenset({"new", "accepted", "pending_new", "accepted_for_bidding", "held",
                     "partially_filled", "calculated", "pending_replace"})

UNSEEDED = "UNSEEDED"
ORDER_SENT = "ORDER_SENT"
EXPIRED_UNFILLED = "EXPIRED_UNFILLED"
ACTIVE = "ACTIVE"
OVERSEEDED = "OVERSEEDED"


@dataclass(frozen=True)
class BenchmarkState:
    state: str
    symbol: str
    qty: float
    filled_qty: float
    orders_seen: int
    detail: str

    @property
    def is_active(self) -> bool:
        return self.state == ACTIVE

    def line(self) -> str:
        return f"[{self.state}] {self.detail}"


def read(client, *, symbol: str = "SPY") -> BenchmarkState:
    """The benchmark's state, from positions and orders. Read-only.

    `status="all"` on purpose: an expired OPG order is invisible under
    `status="open"`, so the failure that produced `EXPIRED_UNFILLED` would read
    as `UNSEEDED` -- "we never tried" -- and someone would helpfully try again
    with the same convention.
    """
    sym = symbol.upper()
    positions = [p for p in client.positions() if str(p.get("symbol", "")).upper() == sym]
    others = [p for p in client.positions() if str(p.get("symbol", "")).upper() != sym]
    try:
        orders = [o for o in client.orders(status="all", limit=500)
                  if str(o.get("symbol", "")).upper() == sym]
    except Exception:                                                  # noqa: BLE001
        orders = []

    filled_qty = sum(float(o.get("filled_qty") or 0.0) for o in orders)
    held = sum(float(p.get("qty") or 0.0) for p in positions)

    if others:
        return BenchmarkState(
            OVERSEEDED, sym, held, filled_qty, len(orders),
            f"the benchmark account holds {len(others)} position(s) outside {sym}: "
            f"{', '.join(sorted(str(p.get('symbol')) for p in others))}. A buy-and-hold arm "
            "that acquired anything else is no longer the bar the other arms are measured "
            "against.")
    if len(positions) > 1:
        return BenchmarkState(OVERSEEDED, sym, held, filled_qty, len(orders),
                              f"{len(positions)} separate {sym} positions.")
    if held > 0:
        return BenchmarkState(ACTIVE, sym, held, filled_qty, len(orders),
                              f"{held:g} {sym} held. The benchmark exists and may be quoted.")

    working = [o for o in orders if str(o.get("status", "")).lower() in WORKING]
    if working:
        return BenchmarkState(
            ORDER_SENT, sym, 0.0, filled_qty, len(orders),
            f"{len(working)} {sym} order(s) still working, no position yet. SUBMITTED is not "
            "SEEDED -- do not quote a benchmark from this state.")
    if orders:
        statuses = sorted({str(o.get("status", "?")).lower() for o in orders})
        return BenchmarkState(
            EXPIRED_UNFILLED, sym, 0.0, filled_qty, len(orders),
            f"{len(orders)} {sym} order(s), none working, nothing held. Statuses: "
            f"{', '.join(statuses)}. An OPG order is eligible only for the opening auction and "
            "is cancelled if it does not fill there. The arm needs re-seeding under a "
            "convention that produces a fill, and it is NOT the same as never having tried.")
    return BenchmarkState(UNSEEDED, sym, 0.0, 0.0, 0,
                          f"no {sym} orders and no position. Nothing has been attempted.")
