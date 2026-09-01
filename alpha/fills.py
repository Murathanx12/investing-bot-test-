"""Fill audit -- the first measurement, and the one that decides the $99.

WHAT IS MEASURED, AND WHY EACH NUMBER
=====================================
Every submitted order carries the quote we SAW at decision time (`quote_snapshot`
in the ledger: bid/ask per leg, feed, age). The venue later tells us what we
actually PAID (`filled_avg_price`, per leg). Between those two numbers sits the
entire question of whether a fifteen-minute-delayed option feed is good enough
to trade on:

    decision_ask       what the structure cost at the quotes we decided on
    fill               what the paper venue filled it at
    slippage           fill - decision_ask   (positive = we paid more)
    slippage / edge    the decision rule in docs/HANDOFF.md: buy Algo Trader
                       Plus only if this exceeds ~15% of the expected edge

Then the position is MARKED at the side we could exit at (long legs at the bid)
at increasing elapsed times. Every mark is appended, never overwritten, so the
series 5m / 15m / 60m / EOD accumulates from repeated runs of the audit rather
than from a scheduler we would have to trust.

WHAT THIS CANNOT SAY
====================
One fill is one fill. It distinguishes "the delayed feed is off by dollars" from
"it is off by cents", which is the decision we actually face; it does not
estimate a slippage distribution, and the receipt says `n=1` so nobody reads it
as one.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from alpha import ledger

MULT = 100.0


def mult_of(symbol: str, underlying: str) -> float:
    """100 for an option leg, 1 for shares. A SHARES leg is the one whose
    symbol IS the underlying -- that is how the runner writes it. 28 Aug:
    every share position's fill audit crashed for a session because the
    options quote endpoint was asked for 'NVDA', and share slippage in dollars
    was multiplied by 100."""
    return 1.0 if symbol == underlying else MULT


@dataclass
class FillAudit:
    decision_id: str
    alpaca_order_id: str
    symbol: str
    instrument: str
    status: str
    submitted_at: str
    filled_at: str | None
    qty: int
    decision_ask_per_unit: float | None
    """Sum of executable asks per leg at decision time, in option points.
    None when any leg's decision quote was not recorded -- an unreadable
    decision price is never zero (2026-09-01, the ABAT phantom-slippage fix)."""
    decision_bid_per_unit: float | None
    limit_price: float | None
    fill_per_unit: float | None
    slippage_per_unit: float | None
    slippage_usd: float | None
    mdm_edge: float | None
    expected_edge_usd: float | None
    """`mdm_edge` x max loss committed -- a crude dollar expectation of the edge
    the sizer thought it had, so slippage can be stated as a fraction of it."""
    slippage_over_edge: float | None
    feed: str
    quote_age_s: float
    legs: list[dict[str, Any]] = field(default_factory=list)
    mark: dict[str, Any] | None = None


def audit(client, decision: dict, *, now: datetime | None = None) -> FillAudit:
    """Compare one submitted decision with the venue's account of it."""
    at = now or datetime.now(timezone.utc)
    order = client._request("GET", f"/v2/orders/{decision['alpaca_order_id']}")
    snap = decision.get("quote_snapshot") or {}
    legs_seen = {l["symbol"]: l for l in snap.get("legs", [])}
    struct_legs = [tuple(l) for l in decision.get("legs") or []]
    if not struct_legs:
        # Rows written before leg capture: reconstruct from the order payload.
        order_legs = (decision.get("order") or {}).get("legs") or []
        struct_legs = [(l["symbol"], l["side"], int(l.get("ratio_qty") or 1)) for l in order_legs]
        if not struct_legs and (decision.get("order") or {}).get("symbol"):
            o = decision["order"]
            struct_legs = [(o["symbol"], o["side"], 1)]

    # A GUARD DERIVES ITS INPUT OR REFUSES. The old `if s in legs_seen` filter
    # made a missing decision quote an EMPTY SUM: dec_ask = 0.0, and slippage
    # then equalled the entire fill -- ABAT booked ~$9,900 of phantom slippage
    # on 2026-08-31 because its snapshot was empty. An unreadable decision
    # quote is None, never zero, and the audit says which leg was missing.
    def _leg_ok(s, key):
        return s in legs_seen and legs_seen[s].get(key) is not None
    quotes_complete = all(_leg_ok(s, "ask" if side == "buy" else "bid")
                          and _leg_ok(s, "bid" if side == "buy" else "ask")
                          for s, side, _ in struct_legs) and bool(struct_legs)
    if quotes_complete:
        dec_ask = sum((legs_seen[s]["ask"] if side == "buy" else -legs_seen[s]["bid"]) * r
                      for s, side, r in struct_legs)
        dec_bid = sum((legs_seen[s]["bid"] if side == "buy" else -legs_seen[s]["ask"]) * r
                      for s, side, r in struct_legs)
    else:
        dec_ask = dec_bid = None

    legs_out, fill = [], None
    venue_legs = order.get("legs") or [order]
    filled_all = all(l.get("filled_avg_price") for l in venue_legs)
    if filled_all:
        fill = 0.0
        for l in venue_legs:
            px = float(l["filled_avg_price"])
            side = l.get("side")
            sign = 1 if side == "buy" else -1
            fill += sign * px
            seen = legs_seen.get(l["symbol"], {})
            legs_out.append({"symbol": l["symbol"], "side": side, "fill": px,
                             "decision_bid": seen.get("bid"), "decision_ask": seen.get("ask"),
                             "filled_at": l.get("filled_at")})
    qty = int(float(order.get("qty") or decision.get("order", {}).get("qty") or 0))
    max_loss = float(decision.get("max_loss_usd") or 0.0)
    edge = decision.get("mdm_edge")
    exp_edge = (edge * max_loss) if (edge is not None and max_loss) else None

    slip = (fill - dec_ask) if (fill is not None and dec_ask is not None) else None
    mult = mult_of(struct_legs[0][0], decision["symbol"]) if struct_legs else MULT
    out = FillAudit(
        decision_id=decision["decision_id"], alpaca_order_id=decision["alpaca_order_id"],
        symbol=decision["symbol"], instrument=decision.get("instrument", ""),
        status=order.get("status", "?"), submitted_at=decision.get("ts_utc", ""),
        filled_at=order.get("filled_at"), qty=qty,
        decision_ask_per_unit=round(dec_ask, 4) if dec_ask is not None else None,
        decision_bid_per_unit=round(dec_bid, 4) if dec_bid is not None else None,
        limit_price=float(order["limit_price"]) if order.get("limit_price") else None,
        fill_per_unit=round(fill, 4) if fill is not None else None,
        slippage_per_unit=round(slip, 4) if slip is not None else None,
        slippage_usd=round(slip * mult * qty, 2) if slip is not None else None,
        mdm_edge=edge, expected_edge_usd=round(exp_edge, 2) if exp_edge else None,
        slippage_over_edge=(round(slip * mult * qty / exp_edge, 4)
                            if (slip is not None and exp_edge) else None),
        feed=snap.get("feed", "?"), quote_age_s=float(snap.get("median_quote_age_s") or 0.0),
        legs=legs_out,
    )
    out.mark = mark_now(client, struct_legs, fill_per_unit=fill, qty=qty,
                        filled_at=order.get("filled_at"), now=at, underlying=decision["symbol"])
    return out


def mark_now(client, legs: list[tuple], *, fill_per_unit: float | None, qty: int,
             filled_at: str | None, now: datetime, underlying: str = "") -> dict[str, Any]:
    """Exit value at the crossed side, right now, and elapsed time since fill."""
    symbols = [s for s, _, _ in legs]
    if not symbols:
        return {"note": "no legs"}
    eq = [x for x in symbols if x == underlying]
    opt = [x for x in symbols if x != underlying]
    quotes: dict[str, Any] = {}
    if opt:
        quotes.update(client.option_quotes(opt) or {})
    if eq:
        quotes.update((client.stock_quote(eq) or {}).get("quotes") or {})
    exit_pu, detail = 0.0, []
    for s, side, r in legs:
        q = quotes.get(s) or {}
        bid, ask = float(q.get("bp") or 0.0), float(q.get("ap") or 0.0)
        exit_pu += (bid if side == "buy" else -ask) * r
        detail.append({"symbol": s, "bid": bid, "ask": ask, "t": q.get("t")})
    elapsed_min = None
    if filled_at:
        try:
            f = datetime.fromisoformat(filled_at.replace("Z", "+00:00"))
            elapsed_min = round((now - f).total_seconds() / 60.0, 1)
        except ValueError:
            pass
    pnl = (exit_pu - fill_per_unit) * mult_of(symbols[0], underlying) * qty if fill_per_unit is not None else None
    return {"marked_at": now.isoformat(), "elapsed_min_since_fill": elapsed_min,
            "exit_per_unit_at_bid": round(exit_pu, 4),
            "pnl_usd_if_closed_now": round(pnl, 2) if pnl is not None else None,
            "legs": detail}


def record(a: FillAudit) -> None:
    """Append to its own ledger. Marks accumulate; nothing is rewritten."""
    ledger.record(ledger.Decision(
        decision_id=f"{a.decision_id}:fill",
        ts_utc=datetime.now(timezone.utc).isoformat(),
        symbol=a.symbol, brain="fill_audit", signal_shape=None, instrument=a.instrument,
        thesis=f"fill audit: status={a.status} slippage={a.slippage_per_unit}",
        predicted_move=None, predicted_sd=None, implied_move=None, breakeven_move=None,
        mdm_edge=a.mdm_edge, quote_snapshot={"legs": a.legs, "feed": a.feed,
                                             "quote_age_s": a.quote_age_s},
        action="audited", refusal_reason=None, risk_fraction=0.0,
        max_loss_usd=0.0, order=None, alpaca_order_id=a.alpaca_order_id,
        fill={"per_unit": a.fill_per_unit, "decision_ask": a.decision_ask_per_unit,
              "slippage_per_unit": a.slippage_per_unit, "slippage_usd": a.slippage_usd,
              "slippage_over_edge": a.slippage_over_edge, "filled_at": a.filled_at},
        outcome=a.mark,
    ), name="fills")


def to_json(a: FillAudit) -> str:
    return json.dumps(asdict(a), indent=1, default=str)
