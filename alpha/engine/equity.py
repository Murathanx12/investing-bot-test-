"""SHARES as a structure -- the honest instrument for a 1%-of-spot edge.

WHY THIS FILE EXISTS
====================
The one mechanism in this project with a positive t (source PEAD: +1.13% over
three sessions, t 2.72, n=108 -- `alpha/brains/post_event_drift.py`) dies of
OPTION costs, not of doubt: at a 1%-of-spot round trip the mean is +0.13% and
the t is 0.32. A long option on a 0.7% centre pays half its spread for a jump
the tercile split says is not in the signal. Session 6 asked whether the
underlying itself is the honest expression; this file is the answer. In NVDA
shares the round trip is a few basis points, so the instrument keeps ~+1.08 of
the +1.13.

IT GOES THROUGH THE SAME GATE, NOT AROUND IT
============================================
A share position is a `sizing.Structure` like any other and is enumerated
BESIDE the option structures, gated by the same MDM test, ranked by the same
EV/max-loss and sized by the same risk envelope. A `direction` brain is still
integrated at the CHAIN's width (`runner.effective_sd`), so the shares win the
ranking only when the SHIFT the brain claims moves enough mass past a
break-even of one bid-ask to beat every option that must first pay its
premium. Measured on 26 Aug: a +0.72% centre against a post-print chain width
of ~3% clears the 5pp floor (~+7.6pp) in shares and does NOT clear it in any
option at the same width -- which is exactly the finding this file exists to
express. Against the PRE-print width of 5.4% it clears nothing, in shares
either; that refusal stands.

THE WORST CASE IS DECLARED, AND IT IS A STOP PLUS A GAP
=======================================================
Every structure this agent trades must state a positive bounded `max_loss`.
Shares have none by construction, so this one is DECLARED: the exit stop
(`STOP_FRACTION`) plus an allowance for the stop being gapped through
(`GAP_ALLOWANCE`), charged as the unit's max loss at entry and in the book.
A stop cannot bound a gap; the allowance says so in the number rather than in
a comment. The size the sizer approves is then converted into shares AT THAT
MAX LOSS -- 5% of spot per share -- and additionally capped at
`MAX_NOTIONAL_FRACTION` of equity per name, because a 7% risk budget over a 5%
per-share worst case would otherwise buy 140% of the account.

SHORTS
======
The DOWN side of the drift is the stronger half (hit 72%, t 2.37), so a short
share structure is enumerated when the venue says the name is shortable and
easy to borrow. Otherwise it is simply not built, and the reason is logged.
"""

from __future__ import annotations

import logging
import math

from alpha.engine.sizing import Structure

logger = logging.getLogger(__name__)

#: Exit stop on the position as a fraction of entry spot. `exits.py` enforces it.
STOP_FRACTION = 0.03
#: A stop cannot bound a gap. Charged on top of the stop as the declared worst case.
GAP_ALLOWANCE = 0.02
#: Declared max loss per share as a fraction of spot.
MAX_LOSS_FRACTION = STOP_FRACTION + GAP_ALLOWANCE
#: Take-profit for a drift position: about twice the measured three-day centre.
#: The mechanism's mean is ~1%; +2.5% inside the window is noise realised, and
#: the tercile split says an over-extended move stops continuing.
PROFIT_TARGET = 0.025
#: Hard cap on share notional per name, as a fraction of equity.
MAX_NOTIONAL_FRACTION = 0.25

KINDS = frozenset({"long_shares", "short_shares"})


def is_equity_symbol(symbol: str) -> bool:
    """Equities are not OCC contracts: shorter than 15 chars or no 8-digit strike."""
    return not (len(symbol) >= 15 and symbol[-8:].isdigit())


def shares(symbol: str, *, spot: float, bid: float, ask: float, direction: str,
           implied_move: float, horizon_days: float, days_to_expiry: float,
           shortable: bool = True, quote: dict | None = None) -> Structure | None:
    """One share of `symbol` as a bounded structure, or None if it cannot be built.

    `implied_move` is the chain's expected absolute move to `days_to_expiry`;
    it is rescaled by sqrt(horizon/dte) so the width a direction brain is
    integrated at is the width over the LIFE of this position, not of some
    option's. `direction` is "up" (buy) or "down" (sell short).
    """
    if direction not in ("up", "down"):
        raise ValueError(f"shares: direction must be up/down, got {direction!r}")
    if spot <= 0 or bid <= 0 or ask <= 0 or ask < bid:
        return None
    if direction == "down" and not shortable:
        logger.info("%s: short shares not built -- venue says not shortable/easy-to-borrow", symbol)
        return None
    mid = 0.5 * (bid + ask)
    spread = ask - bid
    spread_pct = spread / mid if mid > 0 else 0.0
    # Break-even is one round trip: buy the ask, sell the bid (or the mirror).
    breakeven = (spread / spot) if direction == "up" else -(spread / spot)
    horizon = max(0.5, float(horizon_days or 1.0))
    dte = max(0.5, float(days_to_expiry or horizon))
    width = float(implied_move or 0.0) * math.sqrt(horizon / dte)
    entry_cost = ask if direction == "up" else -bid
    max_loss = spot * MAX_LOSS_FRACTION
    return Structure(
        symbol=symbol,
        kind="long_shares" if direction == "up" else "short_shares",
        direction=direction,
        entry_cost=entry_cost,
        max_loss=max_loss,
        max_gain=None,
        breakeven_move=breakeven,
        implied_move=width,
        quote_spread_pct=spread_pct,
        days_to_expiry=horizon,
        legs=((symbol, "buy" if direction == "up" else "sell", 1),),
        staleness_penalty=0.0,
        quote=quote,
    )


def units_cap(spot: float, equity: float) -> int:
    """Most shares of a name the notional cap allows."""
    if spot <= 0 or equity <= 0:
        return 0
    return int((MAX_NOTIONAL_FRACTION * equity) // spot)


def stop_hit(unrealized_plpc: float) -> bool:
    return unrealized_plpc <= -STOP_FRACTION


def target_hit(unrealized_plpc: float) -> bool:
    return unrealized_plpc >= PROFIT_TARGET
