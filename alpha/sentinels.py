"""SANITY_SENTINELS_v1 -- a broken measuring instrument loses the capital budget.

WHAT THIS GENERALISES
=====================
Across 6,070 decisions carrying both a forecast and a quote, the engine thought
the chain was CHEAP on **96.4%** of them. No liquid market is wrong one way 96%
of the time. Three unit errors were compounding, each small, all pointing the
same direction, and the books spent -$22,017 on long straddles before anybody
computed that fraction.

**The fraction was computable the whole time.** Every one of those decisions
wrote `predicted_sd` and `implied_move` to the ledger. Nothing read them
together.

So the sentinel is not a new measurement. It is the one that already existed,
run automatically, with an action attached.

WHAT IT MEASURES
================
For each brain, over a lookback window, the share of decisions where the brain's
own sigma exceeds the chain's:

    ratio = predicted_sd / (implied_move * sqrt(pi/2))

The `sqrt(pi/2)` matters and is the same conversion `sizing` uses: the chain
quotes E|move|, not a sigma. Comparing a sigma to an E|move| directly overstates
the brain by 25% on every row -- which is one of the three original errors, and
would be reintroduced here by anyone writing `predicted_sd / implied_move`.

A healthy brain disagrees with the market in BOTH directions. One that is above
the chain 96% of the time is not finding cheap options; it is holding a ruler
that reads long.

WHAT IT DOES ABOUT IT
=====================
Loses **new-position authority**, and nothing else. Never exit authority, never
management, never marking -- a component with a broken ruler must still be able
to close what it opened, and quarantining the exits would turn a measurement
problem into a trapped book.

The verdict is deliberately three-valued. `CANNOT_DETERMINE` on a thin sample is
not `OK`: "we could not look" and "it is fine" must not print the same.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Share of decisions on ONE side before a brain is considered broken.
#: 0.90, not 0.964: the observed pathology should be well inside the trigger,
#: not sitting on it.
ONE_SIDED_MAX = 0.90

#: Below this many comparable decisions the sentinel says CANNOT_DETERMINE.
#: A brain with six decisions can be 100% one-sided by luck.
MIN_DECISIONS = 50

OK, BROKEN, CANNOT_DETERMINE = "OK", "BROKEN", "CANNOT_DETERMINE"


@dataclass(frozen=True)
class Verdict:
    brain: str
    state: str
    n: int
    share_above_chain: float | None
    median_ratio: float | None
    detail: str

    @property
    def may_open(self) -> bool:
        """CANNOT_DETERMINE may still open. The sentinel exists to catch a
        measured pathology, not to block every brain that is new."""
        return self.state != BROKEN

    def line(self) -> str:
        share = "--" if self.share_above_chain is None else f"{self.share_above_chain:.1%}"
        med = "--" if self.median_ratio is None else f"{self.median_ratio:.2f}"
        return f"[{self.state:<16}] {self.brain:<22} n={self.n:<5} above chain {share:>6}  median ratio {med}"


def chain_sigma(implied_move: float) -> float:
    """E|move| -> sigma. The conversion whose absence was one of the three bugs."""
    return implied_move * math.sqrt(math.pi / 2.0)


def ratios(rows) -> dict[str, list[float]]:
    """brain -> [predicted_sd / chain_sigma], for rows that carry both."""
    out: dict[str, list[float]] = {}
    for r in rows:
        sd = r.get("predicted_sd")
        im = r.get("implied_move")
        brain = r.get("brain")
        if sd is None or not im or not brain or im <= 0 or sd <= 0:
            continue
        out.setdefault(brain, []).append(float(sd) / chain_sigma(float(im)))
    return out


def judge(brain: str, rs: list[float]) -> Verdict:
    n = len(rs)
    if n < MIN_DECISIONS:
        return Verdict(brain, CANNOT_DETERMINE, n, None, None,
                       f"only {n} comparable decisions against a floor of {MIN_DECISIONS}. "
                       "A thin sample can be 100% one-sided by luck, and 'we could not look' "
                       "must not print the same as 'it is fine'.")
    above = sum(1 for x in rs if x > 1.0) / n
    med = sorted(rs)[n // 2]
    if above > ONE_SIDED_MAX:
        return Verdict(brain, BROKEN, n, above, med,
                       f"thinks the chain is CHEAP on {above:.1%} of {n} decisions "
                       f"(median ratio {med:.2f}). No liquid market is wrong one way that "
                       "often. This is the 96.4% pathology: a ruler that reads long, not an "
                       "edge. NEW-POSITION AUTHORITY WITHDRAWN; exits and marking continue.")
    if (1.0 - above) > ONE_SIDED_MAX:
        return Verdict(brain, BROKEN, n, above, med,
                       f"thinks the chain is EXPENSIVE on {1 - above:.1%} of {n} decisions "
                       f"(median ratio {med:.2f}). The mirror image of the same defect, and "
                       "it sells premium instead of buying it. NEW-POSITION AUTHORITY "
                       "WITHDRAWN; exits and marking continue.")
    return Verdict(brain, OK, n, above, med,
                   f"disagrees with the chain in both directions: above on {above:.1%} of "
                   f"{n} decisions, median ratio {med:.2f}.")


def evaluate(rows) -> list[Verdict]:
    return sorted((judge(b, rs) for b, rs in ratios(rows).items()),
                  key=lambda v: (v.state != BROKEN, v.brain))


def broken(rows) -> set[str]:
    """Brains that may not open a new position."""
    return {v.brain for v in evaluate(rows) if v.state == BROKEN}
