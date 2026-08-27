"""COMPETITION_BOOK_v1 -- the five-session book the evidence actually supports.

Every constant here is a measured number with a receipt, not a preference. The
book that lost $37,337 had none of these limits, and each one is the direct
negative of something that went wrong on 2026-08-25.

WHAT THE EVIDENCE SAYS, IN THE ORDER IT CONSTRAINS THE BOOK
===========================================================

1. STRUCTURE BEFORE SELECTION. `scripts/structure_lab` priced every structure
   over the SAME measured five-session returns. On an index book a long
   straddle has an **8.7% hit rate and a -10.78% median**; the iron condor on
   that same index returns +2.82% at a 79.4% hit rate. We ran each on the wrong
   asset. Structure was the trade; direction barely participated.

2. THE NULL DECIDES THE STRUCTURE. With the drift removed and the fat tails
   kept, EVERY long-premium structure goes negative on the median (ATM call
   -10.95%, far OTM -18.69%, straddle -7.33%). Only the short put spreads stay
   positive (+2.09%, +0.52%). Our drift belief carries t=2.62 against a
   leaderboard noise floor of 2.39 -- weakly held. **A structure whose payoff
   requires a drift we cannot resolve is a bet on our own confidence.**

3. RANK ON THE MEDIAN. Five sessions is ONE draw. The existing ranker takes a
   33%-hit-rate call over a 56%-hit-rate share position because it optimises
   the mean (`docs/FINDING_2026-08-27_THE_RANKER_OPTIMISES_THE_MEAN.md`).

4. COUNT BETS, NOT TICKERS. `momentum 12-1 k=10` holds ten names at **1.32
   effective bets** -- one semiconductor bet wearing ten tickers. dev ran at
   1.51 and exp1 at 1.27 when they lost.

5. MOMENTUM IN LATE AUGUST IS AN UNHEDGED EARNINGS BOOK. The rules select MRVL
   (prints 28 Aug), PANW (2 Sep), DELL (3 Sep) -- all inside the window.
   Momentum picks what just ran, and what just ran often ran into a print.

6. ONE DAY IS ONE BET. 100% of the realised loss entered on 2026-08-25.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------- the limits
CORE_FRACTION = 0.70
"""Share of risk in BROAD exposure rather than in a tilt.

`FINDING_2026-08-28_VARIANCE_DRAG_ATE_THE_EDGE.md`: over CRSP 1993-2024 the
value-weighted market compounded at +10.61% while our best five-day
configuration managed +5.36% and the lab's crowned candidate returned -7.23%.
The tilt has a MEASURED NEGATIVE contribution over 32 years, so it is a
satellite that must earn its place, never the book."""

MIN_BREADTH_K = 20
"""Terminal wealth rose with k in EVERY row of the 32-year sweep:

    lookback 126d:  k=5 0.09x | k=20 0.47x | k=50 0.62x | k=100 0.73x

Concentration is not a risk preference here. It is a negative-return decision,
because a five-name book's variance drag exceeds its mean (+0.147% per window
against 0.1x terminal wealth)."""

MIN_EFFECTIVE_BETS = 2.0
"""Below this the book is one position with several names on it. dev was 1.51."""

MAX_LOSS_FRACTION = 0.30
"""Total defined risk as a fraction of equity. The August book had no cap and
gave back 21.8% of the account in a single session's entries."""

MAX_LOSS_PER_NAME = 0.06
"""One name may never cost more than this. NVDA alone was 41.9% of dev's loss."""

MAX_ENTRIES_PER_SESSION = 3
"""Entering the whole book on one day makes the entry date the only bet that
matters. Spread across sessions or the calendar is the position."""

MIN_DTE, MAX_DTE = 14, 45
"""Under 14 days gamma dominates and a five-day hold is a coin flip on one
print; over 45 the structure barely moves and the competition ends first."""


@dataclass(frozen=True)
class Leg:
    symbol: str
    kind: str                 # short_put_spread | call_debit_spread | long_shares
    detail: str
    max_loss_usd: float
    rationale: str


@dataclass
class Proposal:
    legs: list[Leg] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    effective_bets: float = float("nan")

    @property
    def total_risk(self) -> float:
        return sum(l.max_loss_usd for l in self.legs)

    def refuse(self, why: str) -> None:
        self.refusals.append(why)


class PlaybookRefusal(RuntimeError):
    pass


def core_satellite(equity: float) -> tuple[float, float]:
    """Risk dollars for the broad core and for the tilt."""
    total = equity * MAX_LOSS_FRACTION
    return total * CORE_FRACTION, total * (1.0 - CORE_FRACTION)


def breadth_ok(k: int) -> str | None:
    """A tilt narrower than the sweep's floor is refused with its own number."""
    if k < MIN_BREADTH_K:
        return (f"BREADTH: k={k} is below {MIN_BREADTH_K}. Over CRSP 1993-2024 at a "
                f"five-day hold, k=5 returned 0.09x terminal wealth where k=100 "
                f"returned 0.73x on the SAME signal. Narrow is not aggressive, "
                f"it is negative.")
    return None


def structure_for(conviction: float, has_catalyst: bool) -> str:
    """Pick the payoff from what we can defend, not from what we hope.

    `conviction` is how much of the measured drift we are willing to bet on.
    Because the null showed long premium is negative-median without a drift,
    convexity has to be EARNED by a belief we can state, and the default is the
    structure that survived the null.
    """
    if has_catalyst:
        # A catalyst inside the holding window means the five-day distribution
        # is not the one we measured. Refuse rather than reprice from nothing:
        # the whole NVDA condor loss is what repricing-from-nothing looks like.
        return "refuse_catalyst"
    if conviction >= 0.70:
        return "call_debit_spread"
    return "short_put_spread"


def check_book(effective_bets: float, n_names: int) -> list[str]:
    """Every refusal the book must survive before a single order is priced."""
    out = []
    if n_names == 0:
        out.append("EMPTY BOOK -- an engine that never acts cannot be measured. "
                   "Zero forecasts and a correct refusal print identically.")
    if effective_bets == effective_bets and effective_bets < MIN_EFFECTIVE_BETS:
        out.append(f"CONCENTRATION: {effective_bets:.2f} effective bets is below "
                   f"{MIN_EFFECTIVE_BETS}. dev ran at 1.51 and lost 21.8% in one day. "
                   "Widen the book or cut the size -- do not add correlated names.")
    return out


def name_budget(equity: float, n_names: int) -> float:
    """Dollars of DEFINED LOSS one name may carry.

    Two caps govern the book and they can disagree: 6% per name across 6 names
    is 36%, which breaches the 30% book cap. The first version of this module
    applied only the per-name cap and produced a 34.1% book that its own check
    then refused. A per-name limit that can breach the book limit is not a
    limit, so the binding one wins.
    """
    if n_names <= 0:
        return 0.0
    return min(equity * MAX_LOSS_PER_NAME, equity * MAX_LOSS_FRACTION / n_names)


def size_leg(budget_per_name: float, max_loss_per_contract: float) -> int:
    """Contracts, sized from the DEFINED LOSS -- never from premium or notional.

    Takes a BUDGET, not an equity: the cap arithmetic lives in `name_budget`
    and exists once. An earlier version took equity and re-derived the cap,
    which meant a caller that had already divided its budget divided it twice
    and deployed $9,450 of a $21,000 core.

    A spread's risk is (width - credit) x 100 and is known at entry. Sizing off
    notional is how an implicit-leverage bug bought with capital already locked
    in unsellable positions.
    """
    if max_loss_per_contract <= 0:
        raise PlaybookRefusal("a structure with no defined loss cannot be sized here")
    return max(0, int(max(0.0, budget_per_name) // max_loss_per_contract))
