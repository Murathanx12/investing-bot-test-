"""RISK_NODE_ALLOCATOR_v1 -- cap CAUSES, not ticker counts.

THE FAILURE THIS ANSWERS
========================
`alpha/concentration.py` already showed that a 24-issuer book behaved like 1.43
independent bets, and that dev ran at 1.51 when it lost 21.8% in a day. The
competition book absorbed that lesson for its SATELLITE -- `check_book` refuses
below 2.0 effective bets -- and then quietly broke it in the CORE:

    CORE = ["SPY", "QQQ", "IWM"]     # "three diversified positions"

Three bullish index credit spreads are not three bets. They are one bet on
`MARKET_BETA` plus one bet on `SHORT_VARIANCE`, wearing three tickers. A book
that caps "6% per name" and holds three names has not capped 18% across three
risks; it has put 18% on one.

MEASURED WHERE IT CAN BE, DECLARED WHERE IT CANNOT
==================================================
Two kinds of loading, kept visibly separate because they carry different
authority:

  * MEASURED -- `MARKET_BETA` loading is the realised beta of the underlying to
    SPY over a lookback, computed from returns. Nobody's opinion.
  * STRUCTURAL -- `SHORT_VARIANCE` is a property of the payoff, not of the
    market: if we sold premium, we are short variance, and no regression is
    needed to know it. Same for `SINGLE_EVENT` when a catalyst sits inside the
    holding window.

A loading that is asserted rather than derived is marked as such in the
attribution, so a reader can see which caps rest on measurement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# --- the nodes ---------------------------------------------------------------
MARKET_BETA = "MARKET_BETA"
SHORT_VARIANCE = "SHORT_VARIANCE"
LONG_VARIANCE = "LONG_VARIANCE"
SINGLE_EVENT = "SINGLE_EVENT"
SMALL_CAP = "SMALL_CAP"
SEMI_AI = "SEMI_AI"
LABOR_MACRO = "LABOR_MACRO"

#: Max fraction of EQUITY that may be lost if one node goes fully against us.
#: The book cap is 30% (`playbook.MAX_LOSS_FRACTION`); no single cause may be
#: more than 70% of it, which is what makes "the core is one bet" survivable
#: rather than fatal.
NODE_CAPS = {
    MARKET_BETA: 0.21,
    SHORT_VARIANCE: 0.21,
    LONG_VARIANCE: 0.10,
    SINGLE_EVENT: 0.06,
    SMALL_CAP: 0.10,
    SEMI_AI: 0.10,
    LABOR_MACRO: 0.08,
}

DEFAULT_CAP = 0.10


@dataclass(frozen=True)
class Position:
    """A proposed position, described by what it RISKS rather than what it costs."""
    symbol: str
    structure: str            # short_put_spread | call_debit_spread | long_shares | ...
    max_loss_usd: float
    has_catalyst: bool = False
    tags: tuple[str, ...] = ()   # extra declared nodes, e.g. SEMI_AI


@dataclass
class Attribution:
    by_node: dict[str, float] = field(default_factory=dict)
    basis: dict[str, str] = field(default_factory=dict)
    breaches: list[str] = field(default_factory=list)

    def add(self, node: str, usd: float, basis: str) -> None:
        self.by_node[node] = self.by_node.get(node, 0.0) + usd
        self.basis.setdefault(node, basis)


def realised_beta(rets: np.ndarray, mkt: np.ndarray) -> float | None:
    """Ordinary beta of a return series to the market's. None if undetermined.

    Returned as None rather than 1.0 when it cannot be computed: a default of
    1.0 is a claim about the position, and an unmeasured claim is exactly what
    this module exists to stop.
    """
    m = np.isfinite(rets) & np.isfinite(mkt)
    if m.sum() < 20:
        return None
    x, y = mkt[m], rets[m]
    v = float(np.var(x))
    if v <= 0:
        return None
    return float(np.cov(y, x)[0, 1] / v)


def is_short_premium(structure: str) -> bool:
    return structure in ("short_put_spread", "short_call_spread", "iron_condor",
                         "cash_secured_put", "covered_call")


def is_long_premium(structure: str) -> bool:
    return structure in ("call_debit_spread", "put_debit_spread", "long_call",
                         "long_put", "long_straddle", "long_strangle")


def attribute(positions: list[Position], *, equity: float,
              betas: dict[str, float | None] | None = None) -> Attribution:
    """Spread each position's DEFINED LOSS across the nodes that would cause it.

    A position is not split into shares of one dollar -- the same dollar can be
    lost through more than one cause and each node is asked "if THIS cause goes
    fully against us, how much is at risk?". So the node totals deliberately sum
    to more than the book's total risk. That is the correct accounting for a
    cap: the question a cap answers is "how much rides on this one thing", not
    "how do I divide the money up".
    """
    betas = betas or {}
    att = Attribution()
    for p in positions:
        loss = float(p.max_loss_usd)
        if loss <= 0:
            continue

        b = betas.get(p.symbol)
        if b is None:
            att.add(MARKET_BETA, loss, "DECLARED (beta not measurable; charged in full)")
        else:
            att.add(MARKET_BETA, loss * abs(b),
                    f"MEASURED (realised beta to SPY, |b| used)")

        if is_short_premium(p.structure):
            att.add(SHORT_VARIANCE, loss,
                    "STRUCTURAL (we sold premium; a vol expansion is the loss)")
        elif is_long_premium(p.structure):
            att.add(LONG_VARIANCE, loss,
                    "STRUCTURAL (we bought premium; quiet markets are the loss)")

        if p.has_catalyst:
            att.add(SINGLE_EVENT, loss,
                    "STRUCTURAL (a scheduled print inside the window)")

        for t in p.tags:
            att.add(t, loss, "DECLARED (tag supplied by the caller)")

    for node, usd in sorted(att.by_node.items(), key=lambda kv: -kv[1]):
        cap = NODE_CAPS.get(node, DEFAULT_CAP)
        frac = usd / equity if equity > 0 else float("inf")
        if frac > cap + 1e-9:
            att.breaches.append(
                f"{node}: ${usd:,.0f} = {frac:.1%} of equity against a "
                f"{cap:.0%} cap [{att.basis.get(node, '')}]")
    return att


def effective_node_count(att: Attribution) -> float:
    """How many independent causes this book really carries.

    The inverse Herfindahl of node risk. It answers the same question
    `concentration.effective_bets` asks of correlated tickers, one level up: a
    book with 90% of its risk on MARKET_BETA scores near 1 however many nodes
    it happens to touch.
    """
    v = np.array([x for x in att.by_node.values() if x > 0], dtype=float)
    if v.size == 0:
        return 0.0
    w = v / v.sum()
    return float(1.0 / np.sum(w ** 2))


def report(att: Attribution, equity: float) -> str:
    lines = [f"  {'node':<16}{'risk $':>12}{'% equity':>10}{'cap':>7}  basis"]
    for node, usd in sorted(att.by_node.items(), key=lambda kv: -kv[1]):
        cap = NODE_CAPS.get(node, DEFAULT_CAP)
        flag = "  BREACH" if usd / equity > cap + 1e-9 else ""
        lines.append(f"  {node:<16}{usd:>12,.0f}{usd / equity:>10.1%}"
                     f"{cap:>7.0%}  {att.basis.get(node, '')}{flag}")
    lines.append(f"  effective NODES: {effective_node_count(att):.2f} "
                 f"(tickers are not bets; causes are)")
    return "\n".join(lines)
