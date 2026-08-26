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

THE NUMBER THE BOOK IS CHARGED IS A STRESS-LOSS CHARGE, NOT A WORST CASE
=======================================================================
Every option structure this agent trades states a CONTRACTUAL maximum loss.
Shares have none: a long share can go to zero and a short share has no ceiling
at all. So what `Structure.max_loss` carries for shares is a **stress-loss
charge** -- the exit stop (`STOP_FRACTION`) plus a GAP allowance for the stop
being gapped through -- and it is named as such on every row
(`quote["risk_semantics"]`), beside the THEORETICAL maximum loss (the notional
for a long; UNBOUNDED for a short). Corrected 2026-08-26 after review: calling
5% a "worst case" would have let the book arithmetic believe something false.

The gap allowance is MEASURED, not assumed (`gap_allowance`): the 95th
percentile of the name's own |overnight gap| over the trailing year, floored at
`GAP_FLOOR`; and when a scheduled event sits inside the position's horizon the
allowance is at least the chain's implied move for that event, because a generic
2% gap into an earnings print is exactly the wrong number. The size the sizer
approves is converted into shares AT THE CHARGE and additionally capped at
`MAX_NOTIONAL_FRACTION` of equity per name, because a 7% risk budget over a 5%
per-share charge would otherwise buy 140% of the account.

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
#: Floor on the gap allowance when the name's own history says less.
GAP_FLOOR = 0.02
#: Default gap allowance when no bars are available to measure one.
GAP_ALLOWANCE = GAP_FLOOR
#: Default stress-loss charge per share as a fraction of spot (stop + floor gap).
#: The LIVE charge is `stress_charge(...)`; this constant is the fallback and the
#: number the book uses for an unexplained long share residual.
MAX_LOSS_FRACTION = STOP_FRACTION + GAP_FLOOR
GAP_PERCENTILE = 0.95
GAP_LOOKBACK = 250


def gap_allowance(bars: list[dict] | None, *, implied_move: float = 0.0,
                  event_pending: bool = False) -> tuple[float, str]:
    """Gap allowance as a fraction of spot, and how it was derived.

    `bars` are daily bars with open `o` and close `c`; the overnight gap is
    open_t / close_{t-1} - 1. Percentile of |gap| over the trailing window,
    floored at GAP_FLOOR. With an event inside the horizon the allowance is at
    least the chain's implied move -- a print IS the gap."""
    gaps: list[float] = []
    if bars:
        closes = [float(b.get("c") or 0.0) for b in bars]
        opens = [float(b.get("o") or 0.0) for b in bars]
        for i in range(1, len(bars)):
            if closes[i - 1] > 0 and opens[i] > 0:
                gaps.append(abs(opens[i] / closes[i - 1] - 1.0))
    gaps = gaps[-GAP_LOOKBACK:]
    if gaps:
        s = sorted(gaps)
        k = min(len(s) - 1, max(0, int(round(GAP_PERCENTILE * (len(s) - 1)))))
        measured = s[k]
        how = f"p{int(GAP_PERCENTILE * 100)} |overnight gap| over {len(s)} sessions = {measured:.2%}"
    else:
        measured = 0.0
        how = "no bars; floor"
    gap = max(GAP_FLOOR, measured)
    if event_pending and implied_move > gap:
        gap = implied_move
        how += f"; event pending -> raised to the chain's implied move {implied_move:.2%}"
    elif gap == GAP_FLOOR and measured < GAP_FLOOR:
        how += f"; floored at {GAP_FLOOR:.0%}"
    return gap, how


def stress_charge(bars: list[dict] | None, *, implied_move: float = 0.0,
                  event_pending: bool = False) -> tuple[float, str]:
    """Stress-loss charge per share as a fraction of spot = stop + gap allowance."""
    gap, how = gap_allowance(bars, implied_move=implied_move, event_pending=event_pending)
    return STOP_FRACTION + gap, f"stop {STOP_FRACTION:.0%} + gap {gap:.2%} ({how})"
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
           shortable: bool = True, quote: dict | None = None,
           charge_fraction: float | None = None, charge_note: str = "") -> Structure | None:
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
    # The chain's width is over ITS life. If our horizon is LONGER, scale it up
    # by sqrt(time). If our horizon is shorter it is NOT scaled down: the width
    # to a post-print expiry is mostly the print, a jump, and sqrt(t) on a jump
    # is a fiction that shrank a 5.1% pre-print width to 4.5% and let shares
    # clear the floor on 26 Aug at 00:50 ET, two hours after the doctrine said
    # they must not. Under-stating the market's width is the unsafe error.
    width = float(implied_move or 0.0) * max(1.0, math.sqrt(horizon / dte))
    entry_cost = ask if direction == "up" else -bid
    charge = charge_fraction if charge_fraction is not None else MAX_LOSS_FRACTION
    if charge <= 0:
        raise ValueError(f"shares: stress charge must be positive, got {charge}")
    max_loss = spot * charge
    semantics = {
        "max_loss_is": "STRESS_LOSS_CHARGE, not a contractual worst case",
        "stress_loss_charge_frac": round(charge, 5),
        "stress_loss_charge_note": charge_note or f"default stop {STOP_FRACTION:.0%} + gap floor {GAP_FLOOR:.0%}",
        "theoretical_max_loss": ("notional (the share can go to zero)" if direction == "up"
                                 else "UNBOUNDED (short share, no ceiling)"),
        "theoretical_max_loss_per_unit": (round(ask, 4) if direction == "up" else None),
    }
    quote = {**(quote or {}), "risk_semantics": semantics}
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
