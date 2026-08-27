"""Expected ECONOMICS of a structure under our own forecast -- the ranker.

THE SEPARATION THIS MODULE ENFORCES
===================================
Until 26 Aug the runner chose, among the structures that cleared the MDM gate,
the one the sizer approved the LARGEST RISK FRACTION for. That conflates three
questions that have three different answers:

    1. should this trade exist?          MDM / spread / liquidity  (the GATE)
    2. which structure makes the most     integrate the actual payoff over the
       money if we are right?             forecast distribution     (the RANKER)
    3. how much should we bet?            risk fraction / tournament / caps
                                                                    (the SIZER)

A 20pp probability edge over the chain's tail says nothing about DOLLARS: a
condor, a straddle, a debit spread and a credit spread have radically different
payoff shapes, and "beyond the break-even" is one point on each of them. So
every structure's piecewise terminal payoff is integrated over the brain's
predicted distribution and the structure is ranked on `ev / max_loss` --
expected return on the capital it puts at risk -- with the MDM verdict left as
the admission ticket and the risk fraction left as the size.

The distribution is the brain's own: a normal in return space with the
forecast's centre and sd, evaluated at expiry. The chain's implied distribution
is NOT used here -- the gate already compared against it; the ranker asks what
happens if we are right, and charges the round-trip spread for being right.

WHAT IT REFUSES
===============
`ev <= 0` after spread is a refusal, however wide the probability edge was. The
25 Aug close showed the reason: the refusal portfolio was +0.8% of risk while
every brain was negative. Cash is a structure with EV exactly zero, and any
structure that cannot beat it does not get to be the champion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict

from alpha.engine.sizing import Structure

MULT = 100.0
GRID = 801
WIDTH_SD = 6.0


@dataclass(frozen=True)
class Economics:
    ev_usd: float
    """Expected P&L per unit at expiry, after the round-trip spread."""
    ev_over_max_loss: float
    p_profit: float
    median_usd: float
    es_5_usd: float
    """Expected shortfall of the worst 5% of outcomes (a negative dollar figure)."""
    p_max_loss: float
    """Probability of losing at least 95% of the stated maximum."""
    p_gain_50: float
    """Probability of making at least 50% of max loss (a return of +50% on risk)."""
    spread_cost_usd: float
    max_loss_usd: float

    def as_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(self).items()}

    def summary(self) -> str:
        return (f"EV ${self.ev_usd:,.0f}/unit = {self.ev_over_max_loss:+.0%} of max loss, "
                f"P(profit) {self.p_profit:.0%}, median ${self.median_usd:,.0f}, "
                f"ES5 ${self.es_5_usd:,.0f}, P(max loss) {self.p_max_loss:.0%}")


def _decode(symbol: str) -> tuple[str, float]:
    return symbol[-9], float(symbol[-8:]) / 1000.0


def terminal_pnl(structure: Structure, spot: float, terminal: float) -> float:
    """P&L per unit at expiry if the underlying settles at `terminal`. Dollars.

    Every leg is an OCC symbol; the structure's own `entry_cost` (positive for a
    debit, negative for a credit received) is what we paid. The spread is NOT
    charged here -- `economics` charges it once, on top.
    """
    value = 0.0
    for symbol, side, ratio in structure.legs:
        sign = 1.0 if side == "buy" else -1.0
        if _is_share(symbol):
            # A share is worth the terminal price; the unit is one share.
            value += sign * ratio * terminal
            continue
        right, strike = _decode(symbol)
        intrinsic = max(0.0, terminal - strike) if right == "C" else max(0.0, strike - terminal)
        value += sign * ratio * intrinsic * MULT
    return value - structure.entry_cost


def _is_share(symbol: str) -> bool:
    return not (len(symbol) >= 15 and symbol[-8:].isdigit())


def _norm_pdf(z: float) -> float:
    return math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)


def economics(structure: Structure, spot: float, centre: float, sd: float,
              *, horizon_days: float | None = None) -> Economics:
    """Integrate the payoff over a normal forecast of the return to expiry.

    `centre`/`sd` describe the return over the brain's horizon; the structure
    pays at ITS expiry. So the sd is rescaled to the structure's life by
    sqrt(dte/horizon) -- IN BOTH DIRECTIONS.

    Until 27 Aug this scaled UP when the structure outlived the horizon and did
    nothing when the horizon outlived the structure. That asymmetry is not a
    conservatism: it is a one-directional error that always widens the forecast
    relative to the quote, so long premium always looks cheap and short premium
    always looks dear. With a hardcoded 3-day horizon it priced a 1-session
    option at sqrt(3) = 1.73x its real width, and it got WORSE as expiry
    approached -- exactly when theta is most lethal.
    See docs/FINDING_2026-08-27_THE_CHAIN_WAS_NEVER_CHEAP.md.

    Pass `horizon_days=None` to disable rescaling entirely. That is the right
    call for a sd that is not diffusive -- a `direction` brain's sd is already
    the chain's width over the structure's life, and an EVENT sd does not shrink
    with sqrt(time) because the event either falls inside the life or it does
    not. The caller owns that judgement; this function will not guess it.
    """
    if sd <= 0 or spot <= 0:
        raise ValueError("economics needs a positive spot and forecast sd")
    if horizon_days and horizon_days > 0:
        sd = sd * math.sqrt(structure.days_to_expiry / horizon_days)
    if not structure.legs:
        raise ValueError(f"{structure.kind} has no legs; its payoff cannot be integrated")

    spread_cost = abs(structure.quote_spread_pct * structure.entry_cost)
    lo, hi = centre - WIDTH_SD * sd, centre + WIDTH_SD * sd
    step = (hi - lo) / (GRID - 1)
    pnls: list[float] = []
    weights: list[float] = []
    for i in range(GRID):
        r = lo + i * step
        w = _norm_pdf((r - centre) / sd) * step / sd
        pnl = terminal_pnl(structure, spot, spot * (1.0 + r)) - spread_cost
        pnls.append(pnl)
        weights.append(w)
    total_w = sum(weights) or 1.0
    weights = [w / total_w for w in weights]

    ev = sum(p * w for p, w in zip(pnls, weights))
    p_profit = sum(w for p, w in zip(pnls, weights) if p > 0)
    p_max = sum(w for p, w in zip(pnls, weights) if p <= -0.95 * structure.max_loss)
    p_gain = sum(w for p, w in zip(pnls, weights) if p >= 0.5 * structure.max_loss)

    order = sorted(range(GRID), key=lambda i: pnls[i])
    acc, median, es_acc, es_w = 0.0, pnls[order[-1]], 0.0, 0.0
    for i in order:
        if es_w < 0.05:
            take = min(weights[i], 0.05 - es_w)
            es_acc += pnls[i] * take
            es_w += take
        acc += weights[i]
        if acc >= 0.5:
            median = pnls[i]
            break
    es5 = es_acc / es_w if es_w > 0 else pnls[order[0]]

    return Economics(
        ev_usd=ev, ev_over_max_loss=ev / structure.max_loss if structure.max_loss else 0.0,
        p_profit=p_profit, median_usd=median, es_5_usd=es5, p_max_loss=p_max,
        p_gain_50=p_gain, spread_cost_usd=spread_cost, max_loss_usd=structure.max_loss,
    )


def liquidation_value(structure: Structure, quotes: dict[str, dict]) -> float | None:
    """What one unit could be CLOSED for right now: longs at the bid, shorts at the ask."""
    value = 0.0
    for symbol, side, ratio in structure.legs:
        q = quotes.get(symbol) or {}
        px = q.get("bid") if side == "buy" else q.get("ask")
        if px is None:
            return None
        mult = 1.0 if _is_share(symbol) else MULT
        value += (1.0 if side == "buy" else -1.0) * ratio * float(px) * mult
    return value
