"""How many bets is this book ACTUALLY making? -- effective N by RISK.

THE NUMBER THAT LIES
====================
Counting positions, or inverting a Herfindahl over weights, answers "how spread
out is the capital". That is not the question. The question is "how many
independent things can go wrong", and when the names share a thesis those two
numbers are not close.

Measured on Situational Awareness LP's Q2 2026 13F -- a $20.2bn book, 24
issuers, filed 14 Aug 2026, the portfolio it carried into the July drawdown:

    effective N by WEIGHT (1/HHI)     5.34
    average pairwise correlation      0.538
    effective N by RISK               1.43      <- 3.7x overstated

On its worst session, **20 of 21 priced names fell together**. A book that looks
like five independent bets and behaves like 1.4 is not diversified; it is one
position with twenty-one tickers on it.

WHY THIS LIVES HERE AND NOT IN admission.py (yet)
=================================================
Measuring is safe; gating changes what the account trades. This module reports.
Whether `MAX_THESIS_CLUSTER` becomes a refusal, and at what threshold, is an
attended promotion decision -- the same rule that keeps night research away from
the execution surface.

The calibration point is what makes a threshold arguable at all: 1.43 is the
value a real $20bn book had at the moment leverage plus a correlated drawdown
forced its liquidation.

THE ARITHMETIC
==============
Portfolio variance with the real correlation matrix, against the same weights
and volatilities if the names were independent:

    N_risk = (var_independent / var_real) * N_weight

At zero correlation the two variances agree and `N_risk == N_weight`. As
correlation rises, `var_real` grows and `N_risk` falls toward 1. It is a
continuous, unit-free reading of "how many bets", and it needs only returns and
weights.

WEIGHTS: RISK, NOT MARKET VALUE
===============================
For an options book, market value is the wrong weight -- a long call worth $500
that can lose $500 and a short spread worth -$8,000 that can lose $2,000 are not
comparable at their marks. `weights_from_book` uses each structure's TRUE MAX
LOSS, which is the number the book is already charged at and the only one that
means the same thing across instruments.
"""

from __future__ import annotations

import math
import re
import statistics as st
from dataclasses import dataclass
from typing import Any

#: Effective-N-by-risk of Situational Awareness LP's Q2 2026 book, measured from
#: its 13F and 41 sessions of prices. Kept as a named constant because a
#: threshold argued from a real blow-up is worth more than one picked round.
SITUATIONAL_AWARENESS_Q2_2026_N_RISK = 1.43

_OCC = re.compile(r"^([A-Z]+)\d{6}[CP]\d{8}$")


def underlying_of(symbol: str) -> str:
    m = _OCC.match(symbol or "")
    return m.group(1) if m else (symbol or "")


def _corr(a: list[float], b: list[float]) -> float:
    if len(a) < 3 or len(b) < 3:
        return 0.0
    ma, mb = st.mean(a), st.mean(b)
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    if da <= 0 or db <= 0:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (da * db)


@dataclass
class Concentration:
    names: int
    n_weight: float
    n_risk: float
    avg_rho: float
    vol_real: float
    vol_independent: float
    sessions: int
    unpriced: list[str]

    @property
    def overstatement(self) -> float:
        return self.n_weight / self.n_risk if self.n_risk > 0 else float("inf")

    def summary(self) -> str:
        return (f"{self.names} underlyings, effective N by weight {self.n_weight:.2f}, "
                f"by RISK {self.n_risk:.2f} (avg rho {self.avg_rho:+.2f}, "
                f"{self.overstatement:.1f}x overstated), daily vol {100*self.vol_real:.2f}% "
                f"vs {100*self.vol_independent:.2f}% if independent"
                + (f"; UNPRICED: {','.join(self.unpriced)}" if self.unpriced else ""))


def measure(weights: dict[str, float], returns: dict[str, list[float]]) -> Concentration | None:
    """`weights` need not be normalised. `returns` are per-underlying log returns.

    Underlyings with no return series are DROPPED and named, never treated as
    uncorrelated -- silently dropping a name would raise the diversification
    reading, which is the direction that flatters the book.
    """
    unpriced = sorted(s for s in weights if not returns.get(s))
    w = {s: abs(v) for s, v in weights.items() if returns.get(s) and abs(v) > 0}
    if len(w) < 2:
        return None
    tw = sum(w.values())
    if tw <= 0:
        return None
    w = {k: v / tw for k, v in w.items()}
    n = min(len(returns[s]) for s in w)
    if n < 5:
        return None
    R = {s: returns[s][-n:] for s in w}
    ks = list(w)
    sd = {s: st.pstdev(R[s]) for s in ks}
    rho = {(i, j): _corr(R[ks[i]], R[ks[j]])
           for i in range(len(ks)) for j in range(i + 1, len(ks))}

    var_real = 0.0
    for i in range(len(ks)):
        for j in range(len(ks)):
            r = 1.0 if i == j else rho[(min(i, j), max(i, j))]
            var_real += w[ks[i]] * w[ks[j]] * sd[ks[i]] * sd[ks[j]] * r
    var_ind = sum((w[s] * sd[s]) ** 2 for s in ks)
    n_weight = 1.0 / sum(v * v for v in w.values())
    if var_real <= 0:
        return None
    n_risk = (var_ind / var_real) * n_weight
    return Concentration(names=len(ks), n_weight=n_weight, n_risk=n_risk,
                         avg_rho=st.mean(rho.values()) if rho else 0.0,
                         vol_real=math.sqrt(var_real),
                         vol_independent=math.sqrt(var_ind),
                         sessions=n, unpriced=unpriced)


def weights_from_book(book: Any) -> dict[str, float]:
    """Per-underlying TRUE MAX LOSS, which is what the book is charged at.

    Market value would compare a long call at its mark against a credit spread
    at a negative mark, which are not the same kind of number. Max loss is.
    """
    out: dict[str, float] = {}
    for s in getattr(book, "structures", []):
        sym = underlying_of(getattr(s, "symbol", "") or "")
        risk = float(getattr(s, "max_loss_per_unit", 0.0) or 0.0) * int(getattr(s, "contracts", 0) or 0)
        if sym and risk > 0:
            out[sym] = out.get(sym, 0.0) + risk
    return out


def marginal(weights: dict[str, float], returns: dict[str, list[float]]
             ) -> list[tuple[str, float, float, float]]:
    """Per underlying: (symbol, share of risk, N_risk WITHOUT it, delta).

    Standalone size answers "how big is this position". It does not answer the
    question that matters for a concentrated book, which is **which position is
    costing the most diversification** -- and those give different orderings,
    because a large position uncorrelated with the rest can raise effective N
    while a small one that duplicates the book's main bet lowers it.

    A POSITIVE delta means the book is more diversified without that name: it is
    the one to cut first. Cutting by size alone would cut the wrong thing.
    """
    base = measure(weights, returns)
    if base is None:
        return []
    total = sum(abs(v) for v in weights.values()) or 1.0
    out = []
    for sym in weights:
        rest = {k: v for k, v in weights.items() if k != sym}
        alt = measure(rest, returns)
        if alt is None:
            continue
        out.append((sym, abs(weights[sym]) / total, alt.n_risk, alt.n_risk - base.n_risk))
    return sorted(out, key=lambda r: -r[3])


def verdict(c: Concentration | None) -> tuple[str, str]:
    """A reading, and the sentence that says what it means. Never a refusal."""
    if c is None:
        return "UNKNOWN", ("not enough priced underlyings or sessions to measure "
                           "concentration. This is not evidence of diversification.")
    ref = SITUATIONAL_AWARENESS_Q2_2026_N_RISK
    if c.n_risk <= ref:
        return "CONCENTRATED", (
            f"effective N by RISK is {c.n_risk:.2f}, at or below the {ref:.2f} that Situational "
            f"Awareness LP's $20bn book carried into its July 2026 drawdown. The book holds "
            f"{c.names} underlyings and behaves like {c.n_risk:.1f} bet(s); the weight-based "
            f"count of {c.n_weight:.2f} overstates it {c.overstatement:.1f}x.")
    if c.n_risk < 2.5:
        return "CLUSTERED", (
            f"effective N by RISK {c.n_risk:.2f} against {c.n_weight:.2f} by weight "
            f"({c.overstatement:.1f}x overstated, avg rho {c.avg_rho:+.2f}). More than one bet, "
            f"but not the {c.names} the position count suggests.")
    return "SPREAD", (f"effective N by RISK {c.n_risk:.2f} across {c.names} underlyings "
                      f"(avg rho {c.avg_rho:+.2f}).")
