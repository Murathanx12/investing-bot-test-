"""Which OPTION STRUCTURE expresses a five-session directional view best?

WHY THIS MODULE EXISTS
======================
The two paper books lost $37,337 and none of it was a stock-picking error. The
realised losses decompose as:

    long_straddle  -$22,017   long vol on names with NO catalyst
    iron_condor    -$14,315   short vol on the ONE name that had one
    long_call       -$1,005

The direction view was barely involved. The STRUCTURE was the trade, and it was
chosen by brains that ranked on a forecast sd rather than on a payoff. So this
module takes a return distribution we have actually MEASURED -- the empirical
five-session outcomes of a candidate book -- and prices each structure over it.

The pricing is Black-Scholes with the smile ignored. That is a real limitation
and it is the right one to accept here: we are comparing structures on the SAME
surface, so a shared bias cancels in the ranking even where it moves the levels.
What does NOT cancel is theta, which is the term that killed the book, and theta
is the term BS gets right.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

SQRT2 = math.sqrt(2.0)


def _nd(x: np.ndarray | float) -> np.ndarray:
    """Standard normal CDF, vectorised, no scipy dependency."""
    x = np.asarray(x, dtype=float)
    return 0.5 * (1.0 + np.vectorize(math.erf)(x / SQRT2))


def bs(S, K, T, sigma, r=0.04, call=True):
    """Black-Scholes price. T in years. Returns 0 for expired/degenerate input."""
    S = np.asarray(S, dtype=float)
    T = max(float(T), 1e-9)
    if sigma <= 0:
        intrinsic = np.maximum(S - K, 0.0) if call else np.maximum(K - S, 0.0)
        return intrinsic
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if call:
        return S * _nd(d1) - K * math.exp(-r * T) * _nd(d2)
    return K * math.exp(-r * T) * _nd(-d2) - S * _nd(-d1)


def delta(S, K, T, sigma, r=0.04, call=True):
    T = max(float(T), 1e-9)
    d1 = (np.log(np.asarray(S, float) / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return _nd(d1) if call else _nd(d1) - 1.0


@dataclass
class StructureResult:
    name: str
    mean_pnl: float          # per $1 of NET CAPITAL AT RISK
    median_pnl: float
    hit: float
    worst: float
    best: float
    capital: float           # debit paid, or margin held, per unit
    note: str = ""

    def line(self) -> str:
        return (f"{self.name:<30} {self.mean_pnl:+8.2%} {self.median_pnl:+8.2%} "
                f"{self.hit:6.1%} {self.worst:+8.2%} {self.best:+8.2%}")


def evaluate(rets: np.ndarray, *, sigma: float, holding_days: int = 5,
             dte: int = 30, spread_frac: float = 0.02) -> list[StructureResult]:
    """Price every structure over the SAME empirical five-day return draws.

    `rets` are the realised holding-period returns of the underlying book --
    not simulated, not normal. That matters: the whole reason a straddle can be
    a good idea is fat tails, and a lognormal simulation would put them in by
    assumption instead of letting the data decide.
    """
    rets = np.asarray([r for r in rets if np.isfinite(r)], dtype=float)
    S0 = 100.0
    S1 = S0 * (1.0 + rets)
    T0, T1 = dte / 365.0, (dte - holding_days) / 365.0

    def px(K, T, S, call=True):
        return np.asarray(bs(S, K, T, sigma, call=call), dtype=float)

    out: list[StructureResult] = []

    def add(name, entry_cost, exit_value, capital, note=""):
        """entry_cost/exit_value are per-unit; costs charged BOTH ways."""
        fee = abs(entry_cost) * spread_frac + np.abs(exit_value) * spread_frac
        pnl = (exit_value - entry_cost - fee) / capital
        out.append(StructureResult(name, float(np.mean(pnl)), float(np.median(pnl)),
                                   float(np.mean(pnl > 0)), float(np.min(pnl)),
                                   float(np.max(pnl)), capital, note))

    # --- long shares, the benchmark every structure must beat -----------------
    out.append(StructureResult("LONG SHARES (delta 1.0)", float(np.mean(rets)),
                               float(np.median(rets)), float(np.mean(rets > 0)),
                               float(np.min(rets)), float(np.max(rets)), 1.0,
                               "no theta, no convexity, no leverage"))

    # --- directional longs ----------------------------------------------------
    for label, K in (("ATM call (K=100)", 100.0),
                     ("OTM call (K=105)", 105.0),
                     ("far OTM call (K=110)", 110.0),
                     ("ITM call (K=90)", 90.0),
                     ("deep ITM call (K=80)", 80.0)):
        c0 = float(px(K, T0, S0))
        d = float(delta(S0, K, T0, sigma))
        add(f"{label} d={d:.2f}", c0, px(K, T1, S1), c0)

    # --- spreads: pay less theta by selling some of it back -------------------
    for label, kl, kh in (("call spread 100/110", 100.0, 110.0),
                          ("call spread 105/115", 105.0, 115.0),
                          ("call spread 95/105", 95.0, 105.0)):
        e = float(px(kl, T0, S0) - px(kh, T0, S0))
        add(label, e, px(kl, T1, S1) - px(kh, T1, S1), e, "debit, capped, less theta")

    # --- positive-theta longs: the structure the book never once used ---------
    for label, kl, kh in (("short put spread 100/90", 100.0, 90.0),
                          ("short put spread 95/85", 95.0, 85.0)):
        credit = float(px(kl, T0, S0, call=False) - px(kh, T0, S0, call=False))
        margin = (kl - kh) - credit
        exitv = px(kl, T1, S1, call=False) - px(kh, T1, S1, call=False)
        add(label, -credit, -exitv, margin, "LONG delta and LONG theta")

    # --- and the two that actually lost the money -----------------------------
    strad0 = float(px(100.0, T0, S0) + px(100.0, T0, S0, call=False))
    add("long straddle (what we did)", strad0,
        px(100.0, T1, S1) + px(100.0, T1, S1, call=False), strad0,
        "pays theta, needs a move in EITHER direction")
    ic_credit = float(px(105.0, T0, S0) - px(115.0, T0, S0)
                      + px(95.0, T0, S0, call=False) - px(85.0, T0, S0, call=False))
    ic_exit = (px(105.0, T1, S1) - px(115.0, T1, S1)
               + px(95.0, T1, S1, call=False) - px(85.0, T1, S1, call=False))
    add("iron condor (what we did)", -ic_credit, -ic_exit, 10.0 - ic_credit,
        "collects theta, loses on a big move in either direction")
    return out
