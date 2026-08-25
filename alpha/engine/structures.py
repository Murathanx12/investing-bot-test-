"""Turn a live chain into the handful of structures we could actually trade.

WHAT THIS MODULE REFUSES TO DO
==============================
It does not pick a strategy. It ENUMERATES every structure the chain supports at
a given expiry, prices each one at the side we would actually cross, and hands
the whole list to the sizer -- which then picks by comparing our forecast to the
market's implied distribution.

That ordering is the point. Most agents decide "buy a call" and then look for a
strike. This one prices a long call, a debit spread, a straddle, a defined-risk
credit spread and an iron condor from the same snapshot, and lets the
disagreement with the option market decide which shape of bet is on offer. If
our forecast is a big move, the straddle wins the comparison on its own; if it
is "less movement than the chain implies", the condor does. Nothing is
hardcoded, so nothing has to be argued for in the write-up beyond the mechanism.

PRICED AT THE SIDE WE CROSS, ALWAYS
===================================
Every long leg is costed at `executable_ask` and every short leg at
`executable_bid` -- the quoted price plus the staleness penalty that
`alpha/data/chain.py` charges for carrying a delayed quote forward. Mid-price
arithmetic would make every structure look 3-8% cheaper than it is, which on a
book of short-dated options is most of the edge.

NO UNDEFINED RISK
=================
Every structure returned has a `max_loss` that is bounded and computed. There is
no naked short here, and there is no branch that could produce one: the short
legs only ever appear inside a spread whose long wing caps the loss, and
`sizing.Structure` refuses `max_loss <= 0` at construction.
"""

from __future__ import annotations

from alpha.data.chain import ChainSnapshot, Contract
from alpha.engine.sizing import Structure

#: Contract multiplier for US equity options.
MULT = 100.0

#: Long options are chosen by DELTA rather than by strike distance, so the same
#: code produces a comparable bet across a $760 index and a $35 stock. ~0.35 is
#: the usual sweet spot for a directional debit trade: enough gamma to pay for a
#: real move, not so much premium that the break-even is unreachable.
TARGET_DIRECTIONAL_DELTA = 0.35

#: Short legs of credit structures. 0.20 delta is roughly the 1-sigma edge of
#: the distribution the chain is pricing.
TARGET_SHORT_DELTA = 0.20


def _nearest_delta(pool: list[Contract], target: float) -> Contract | None:
    scored = [c for c in pool if c.delta is not None]
    return min(scored, key=lambda c: abs(abs(c.delta) - target)) if scored else None


def _by(chain: ChainSnapshot, expiry: str, right: str) -> list[Contract]:
    return sorted(
        (c for c in chain.liquid() if c.expiry == expiry and c.right == right),
        key=lambda c: c.strike,
    )


def _days(chain: ChainSnapshot, expiry: str) -> float:
    from datetime import datetime, timezone

    exp = datetime.strptime(expiry, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return max((exp - chain.fetched_at).total_seconds() / 86400.0, 0.01)


def _spread_pct(legs: list[tuple[Contract, int]]) -> float:
    """Round-trip cost of the whole structure as a fraction of its own mid.

    Summed across legs, because a four-leg condor crosses four spreads and a
    per-leg average would understate the cost by a factor of four.
    """
    gross = sum(abs(qty) * (c.ask - c.bid) for c, qty in legs)
    mid = sum(abs(qty) * c.mid for c, qty in legs)
    return gross / mid if mid > 0 else 1.0


def _penalty(legs: list[tuple[Contract, int]]) -> float:
    return sum(abs(qty) * c.staleness_penalty for c, qty in legs) * MULT


def long_option(chain: ChainSnapshot, expiry: str, right: str) -> Structure | None:
    """Plain long call or put. Maximum convexity, maximum decay."""
    pool = _by(chain, expiry, right)
    c = _nearest_delta(pool, TARGET_DIRECTIONAL_DELTA)
    if not c or c.adjusted_mid is None:
        return None
    debit = c.executable_ask
    if debit <= 0:
        return None
    breakeven_price = c.strike + debit if right == "C" else c.strike - debit
    move = (breakeven_price - chain.spot) / chain.spot
    return Structure(
        symbol=c.symbol,
        kind="long_call" if right == "C" else "long_put",
        direction="up" if right == "C" else "down",
        entry_cost=debit * MULT,
        max_loss=debit * MULT,
        max_gain=None,                    # unbounded on the upside
        breakeven_move=move,
        implied_move=chain.implied_move(expiry) or 0.0,
        quote_spread_pct=_spread_pct([(c, 1)]),
        days_to_expiry=_days(chain, expiry),
        legs=((c.symbol, "buy", 1),),
        staleness_penalty=_penalty([(c, 1)]),
    )


def debit_spread(chain: ChainSnapshot, expiry: str, right: str) -> Structure | None:
    """Directional, defined risk, cheaper break-even than the outright.

    Sells the further-out wing to fund the near one. Gives up the unbounded
    tail, which is the correct trade when our forecast has a CENTRE rather than
    a fat tail -- and the sizer will prefer the outright when it does not.
    """
    pool = _by(chain, expiry, right)
    near = _nearest_delta(pool, TARGET_DIRECTIONAL_DELTA)
    if not near:
        return None
    further = [c for c in pool if (c.strike > near.strike if right == "C" else c.strike < near.strike)]
    far = _nearest_delta(further, TARGET_SHORT_DELTA)
    if not far:
        return None

    debit = near.executable_ask - far.executable_bid
    width = abs(far.strike - near.strike)
    if debit <= 0 or debit >= width:
        # A non-positive debit is a free lunch that the quote is lying about; a
        # debit at or above the width is a structure that cannot profit.
        return None

    breakeven_price = near.strike + debit if right == "C" else near.strike - debit
    return Structure(
        symbol=f"{near.symbol}/{far.symbol}",
        kind="bull_call_spread" if right == "C" else "bear_put_spread",
        direction="up" if right == "C" else "down",
        entry_cost=debit * MULT,
        max_loss=debit * MULT,
        max_gain=(width - debit) * MULT,
        breakeven_move=(breakeven_price - chain.spot) / chain.spot,
        implied_move=chain.implied_move(expiry) or 0.0,
        quote_spread_pct=_spread_pct([(near, 1), (far, -1)]),
        days_to_expiry=_days(chain, expiry),
        legs=((near.symbol, "buy", 1), (far.symbol, "sell", 1)),
        staleness_penalty=_penalty([(near, 1), (far, -1)]),
    )


def straddle(chain: ChainSnapshot, expiry: str) -> Structure | None:
    """Long the move, indifferent to direction.

    This is the structure `rev_dispersion` earns. High analyst disagreement is
    a forecast of realised dispersion, and dispersion is exactly what a straddle
    owns -- the signal and the instrument are the same statement.
    """
    call, put = chain.atm(expiry, "C"), chain.atm(expiry, "P")
    if not call or not put:
        return None
    debit = call.executable_ask + put.executable_ask
    if debit <= 0:
        return None
    return Structure(
        symbol=f"{call.symbol}+{put.symbol}",
        kind="long_straddle",
        direction="both",
        entry_cost=debit * MULT,
        max_loss=debit * MULT,
        max_gain=None,
        breakeven_move=debit / chain.spot,
        implied_move=chain.implied_move(expiry) or 0.0,
        quote_spread_pct=_spread_pct([(call, 1), (put, 1)]),
        days_to_expiry=_days(chain, expiry),
        legs=((call.symbol, "buy", 1), (put.symbol, "buy", 1)),
        staleness_penalty=_penalty([(call, 1), (put, 1)]),
    )


def credit_spread(chain: ChainSnapshot, expiry: str, right: str) -> Structure | None:
    """Defined-risk short premium. The long wing is not optional.

    `right="P"` is a bull put spread (wins if the underlying does not fall far);
    `right="C"` is a bear call spread. The break-even is usually on the far side
    of today's price, which is why `breakeven_move` is SIGNED and why the sizer
    reads it through `direction` rather than as a magnitude.
    """
    pool = _by(chain, expiry, right)
    short = _nearest_delta(pool, TARGET_SHORT_DELTA)
    if not short:
        return None
    wing_pool = [c for c in pool if (c.strike < short.strike if right == "P" else c.strike > short.strike)]
    wing = _nearest_delta(wing_pool, TARGET_SHORT_DELTA / 2.0)
    if not wing:
        return None

    credit = short.executable_bid - wing.executable_ask
    width = abs(short.strike - wing.strike)
    if credit <= 0 or credit >= width:
        return None

    breakeven_price = short.strike - credit if right == "P" else short.strike + credit
    return Structure(
        symbol=f"{short.symbol}/{wing.symbol}",
        kind="bull_put_spread" if right == "P" else "bear_call_spread",
        direction="up" if right == "P" else "down",
        entry_cost=-credit * MULT,        # negative: we receive it
        max_loss=(width - credit) * MULT,
        max_gain=credit * MULT,
        breakeven_move=(breakeven_price - chain.spot) / chain.spot,
        implied_move=chain.implied_move(expiry) or 0.0,
        quote_spread_pct=_spread_pct([(short, -1), (wing, 1)]),
        days_to_expiry=_days(chain, expiry),
        legs=((short.symbol, "sell", 1), (wing.symbol, "buy", 1)),
        staleness_penalty=_penalty([(short, -1), (wing, 1)]),
    )


def iron_condor(chain: ChainSnapshot, expiry: str) -> Structure | None:
    """Short both tails, defined risk on both sides.

    The structure a STEP-shaped signal licenses: a flat top decile is a measured
    opinion that the tail is empty, and selling a tail you have evidence is empty
    is the honest way to express that. It is emphatically NOT the default trade
    -- it wins small and often, which is exactly the payoff a five-session rank
    contest rewards least.
    """
    put_side = credit_spread(chain, expiry, "P")
    call_side = credit_spread(chain, expiry, "C")
    if not put_side or not call_side:
        return None

    credit = -(put_side.entry_cost + call_side.entry_cost)   # both are negative
    if credit <= 0:
        return None
    # Only one side can finish in the money, so the condor's worst case is the
    # worse single wing less the credit already collected from the other.
    max_loss = max(put_side.max_loss, call_side.max_loss)
    if max_loss <= 0:
        return None
    inner = min(abs(put_side.breakeven_move), abs(call_side.breakeven_move))
    return Structure(
        symbol=f"{put_side.symbol}|{call_side.symbol}",
        kind="iron_condor",
        direction="inside",
        entry_cost=-credit,
        max_loss=max_loss,
        max_gain=credit,
        breakeven_move=inner,
        implied_move=chain.implied_move(expiry) or 0.0,
        quote_spread_pct=(put_side.quote_spread_pct + call_side.quote_spread_pct) / 2.0,
        days_to_expiry=_days(chain, expiry),
        legs=put_side.legs + call_side.legs,
        staleness_penalty=put_side.staleness_penalty + call_side.staleness_penalty,
    )


def enumerate_all(chain: ChainSnapshot, expiry: str) -> list[Structure]:
    """Every structure this chain supports at this expiry. Order is not a ranking."""
    builders = (
        lambda: long_option(chain, expiry, "C"),
        lambda: long_option(chain, expiry, "P"),
        lambda: debit_spread(chain, expiry, "C"),
        lambda: debit_spread(chain, expiry, "P"),
        lambda: straddle(chain, expiry),
        lambda: credit_spread(chain, expiry, "P"),
        lambda: credit_spread(chain, expiry, "C"),
        lambda: iron_condor(chain, expiry),
    )
    out = []
    for build in builders:
        try:
            s = build()
        except ValueError:
            # `Structure` refused it -- an unbounded or malformed worst case.
            # Dropping it here is correct: the refusal already did its job.
            continue
        if s is not None:
            out.append(s)
    return out
