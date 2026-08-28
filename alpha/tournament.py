"""TOURNAMENT_UTILITY_v1 and OPPORTUNITY_AUCTION_v1 -- two objectives, kept apart.

WHY THERE MUST BE TWO
=====================
A five-session contest and a lifetime account do not want the same book, and
using one objective for both is how a system ends up either too timid to place
or too reckless to survive.

    REAL account  ->  maximise expected LOG wealth subject to survival.
                      Ruin is absorbing; a 50% drawdown needs a 100% gain.
    CONTEST       ->  maximise P(final equity >= target) subject to a hard floor.
                      Second place and last place pay the same, so variance is
                      only bad when we are ALREADY winning.

The contest objective is deliberately NOT median return. A book with a +0.4%
median and no dispersion is an excellent real-money book and a guaranteed
mid-table finish. Ranking by median is what produces "we did not lose again",
which was never the goal.

THE AUCTION
===========
The allocator does not ask "which signal is best?". It asks, for each increment
of risk budget:

    which opportunity most raises P(win) if it gets the NEXT $1,000?

and allocates one increment at a time, re-asking after each. That is why the
core has no entitlement to 70%: beta is the DEFAULT, meaning it wins increments
whenever nothing else bids higher, not that it starts with the money.

Diminishing returns fall out of this for free. Once an opportunity has enough
size that its upside clears the target on the paths where it wins, further
increments buy fewer new winning paths than a different opportunity would, and
the auction moves on without anyone writing a concentration rule.

EVERY DISTRIBUTION IS A MEASURED SAMPLE
=======================================
`Opportunity.samples` is an array of realised return-on-risk outcomes from a
replay -- OptionMetrics blocks, PEAD windows, NFP reactions. It is never a
fitted normal. The structures being allocated between have wildly different
skew (a credit spread wins small and often; a debit spread loses small and
often), and a mean/sd summary destroys exactly the property that distinguishes
them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from alpha import nodes as nodes_mod


@dataclass
class Opportunity:
    """One way to deploy risk, described by its MEASURED outcome distribution."""
    name: str
    samples: np.ndarray
    """Realised return on MAX LOSS. -1.0 is a total loss of the risked amount."""
    node_tags: tuple[str, ...] = ()
    structure: str = "unknown"
    symbol: str = ""
    increment_usd: float = 1_000.0
    max_usd: float = float("inf")
    group: str = ""
    """Opportunities sharing a group share ONE ceiling (`group_max_usd`).

    Without this the per-name cap is defeated by decomposition: SPY appears as
    SPY:long_shares, SPY:long_atm_call and SPY:call_debit_spread, each with its
    own $6,000 ceiling, so a '6% per name' rule silently permitted 18% on one
    underlying. Observed 2026-08-28 -- the auction put $6,000 into SPY calls and
    $5,000 into SPY call spreads and broke no rule it could see."""
    group_max_usd: float = float("inf")
    note: str = ""

    def draw(self, rng: np.random.Generator, n: int) -> np.ndarray:
        s = self.samples[np.isfinite(self.samples)]
        if s.size == 0:
            return np.zeros(n)
        return rng.choice(s, size=n, replace=True)


@dataclass
class Allocation:
    by_name: dict[str, float] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return sum(self.by_name.values())


def simulate(allocation: dict[str, float], opps: dict[str, Opportunity],
             equity: float, *, n_paths: int = 20_000, seed: int = 17
             ) -> np.ndarray:
    """Final equity across `n_paths`, drawing each opportunity independently.

    INDEPENDENT IS AN ASSUMPTION AND IT FLATTERS US. Real opportunities share
    nodes -- three index spreads lose together. The auction handles that with
    `nodes.NODE_CAPS`, which is a cap on the CAUSE rather than a correlation
    inside the simulation. Stated here because a reader who takes this
    distribution as the book's true dispersion will understate the left tail.
    """
    rng = np.random.default_rng(seed)
    pnl = np.zeros(n_paths)
    for name, usd in allocation.items():
        if usd <= 0:
            continue
        pnl += usd * opps[name].draw(rng, n_paths)
    return equity + pnl


def p_target(final: np.ndarray, target: float) -> float:
    return float((final >= target).mean())


def p_floor_breach(final: np.ndarray, floor: float) -> float:
    return float((final < floor).mean())


def expected_log_wealth(final: np.ndarray, equity: float) -> float:
    """The REAL-money objective. Ruin is -inf and that is the point."""
    f = np.maximum(final, 1e-9)
    return float(np.mean(np.log(f / equity)))


def contest_utility(final: np.ndarray, *, equity: float, target: float,
                    floor: float, floor_tolerance: float = 0.05) -> float:
    """P(hit target), with a hard veto when the floor is breached too often.

    The veto is not a soft penalty term. A book that busts the floor on 10% of
    paths is not 10% worse than one that never does -- it is disqualified, and
    a weighted objective would happily trade that away for upside.
    """
    if p_floor_breach(final, floor) > floor_tolerance:
        return -1.0
    return p_target(final, target)


def auction(opps: list[Opportunity], *, equity: float, target: float,
            floor: float, budget: float, n_paths: int = 8_000,
            seed: int = 17, max_rounds: int = 400,
            betas: dict[str, float | None] | None = None,
            objective: str = "target") -> Allocation:
    """Allocate `budget` of MAX LOSS one increment at a time, by marginal utility.

    `objective` selects WHAT is being maximised, and the MODE must choose it:

        "target"  P(final >= target) under the floor. Correct when behind and
                  out of time -- it will buy negative-median convexity, because
                  a structure that cannot reach the target is worthless however
                  reliable it is.
        "growth"  expected LOG wealth under the floor. Correct otherwise, and
                  the only objective a real-money account should ever use.

    Keeping one objective for both is how the two failure modes appear together:
    an earlier run had `mode_for` print BASE while the auction bought three
    index CALLS with medians of -3.8% and -7.4%, because P(target) was the only
    thing being asked. The mode was advisory and the objective was not listening.

    Returns an `Allocation` whose log records what won each increment and by how
    much, so the decision is auditable rather than a final vector of weights.
    """
    if objective not in ("target", "growth", "median"):
        raise ValueError(f"unknown objective {objective!r}")

    def utility(final: np.ndarray) -> float:
        if p_floor_breach(final, floor) > 0.05:
            return -1e9
        if objective == "target":
            return p_target(final, target)
        if objective == "median":
            # FIVE SESSIONS FOLLOW THE MEDIAN. E[log W] does not refuse a small
            # negative-median lottery ticket -- a $4k ATM call on $100k moves
            # E[log W] by nothing either way -- and on 28 Aug the BASE book
            # bought three index calls with medians of -3.8% and -7.4% under
            # "growth". The median of terminal wealth refuses them, because a
            # structure that loses on most paths lowers the path the contest
            # will actually realise.
            return float(np.median(final) / equity - 1.0)
        return expected_log_wealth(final, equity)
    alloc = Allocation()
    if not opps:
        alloc.refusals.append("no opportunities offered; cash is the book")
        return alloc

    book = {o.name: 0.0 for o in opps}
    index = {o.name: o for o in opps}
    spent = 0.0

    base_final = simulate(book, index, equity, n_paths=n_paths, seed=seed)
    base_u = utility(base_final)
    label = (f"P(>= ${target:,.0f})" if objective == "target"
             else "median terminal return" if objective == "median" else "E[log wealth]")
    alloc.log.append(f"objective = {objective}; cash-only {label} = {base_u:+.4f}")

    for _ in range(max_rounds):
        if spent >= budget:
            break
        best_name, best_size, best_gain, best_u = None, 0.0, 0.0, base_u

        # BLOCK BIDS, and the reason they are necessary
        # ---------------------------------------------
        # P(final >= target) is a THRESHOLD objective, so its gradient is flat
        # wherever no single increment can cross the threshold. A purely greedy
        # auction measured against a far target therefore allocates NOTHING: the
        # first $2,000 of a convex trade cannot by itself turn a $100k account
        # into $108k, so its marginal utility is exactly zero, and so is every
        # other candidate's, and the loop stops on a book of cash.
        #
        # That is the precise situation the ATTACK mode exists for -- being far
        # behind late -- so an allocator that goes to cash there is wrong in the
        # one case it was built for. Found by test, 2026-08-28.
        #
        # The fix is to let an opportunity bid for MORE than one increment: each
        # candidate is offered at 1, 2, 4, 8... increments up to what its own cap
        # and the remaining budget allow. Gains are compared PER DOLLAR so a big
        # bid does not win merely by being big.
        for o in opps:
            step = o.increment_usd
            # The ladder DOUBLES, so it can offer 1x, 2x, 4x, 8x... and never
            # the exact remaining budget. That gap is not cosmetic: with a
            # $10,000 budget in $2,000 steps the largest expressible bid was
            # $8,000, which fell short of a target only the full $10,000 could
            # reach, so the auction saw zero gain everywhere and bought nothing.
            # The maximum FEASIBLE bid is therefore always offered as well.
            room = [o.max_usd - book[o.name], budget - spent]
            if o.group:
                room.append(o.group_max_usd - sum(
                    v for n_, v in book.items() if index[n_].group == o.group))
            feasible = min(room)
            sizes, mult = [], 1
            while step * mult <= feasible:
                sizes.append(step * mult)
                mult *= 2
            if feasible > 0 and (not sizes or sizes[-1] < feasible):
                sizes.append(feasible)

            for size in sizes:
                if book[o.name] + size > o.max_usd or spent + size > budget:
                    continue
                if o.group:
                    used = sum(v for n_, v in book.items()
                               if index[n_].group == o.group)
                    if used + size > o.group_max_usd:
                        continue
                trial = dict(book)
                trial[o.name] += size

                # A node cap can veto a bid that looks attractive: this is where
                # "SPY/QQQ/IWM are one bet" actually binds.
                pos = [nodes_mod.Position(symbol=index[n].symbol or n,
                                          structure=index[n].structure,
                                          max_loss_usd=v,
                                          tags=index[n].node_tags)
                       for n, v in trial.items() if v > 0]
                # The SAME betas the caller will report with. An earlier
                # version omitted them here, so the auction enforced the cap on
                # unweighted loss (21.0%, passing) while the report applied
                # measured betas (24.1%, breaching). A cap checked against a
                # different number than it is reported against is not a cap.
                if nodes_mod.attribute(pos, equity=equity,
                                       betas=betas).breaches:
                    continue

                f = simulate(trial, index, equity, n_paths=n_paths, seed=seed)
                u = utility(f)
                gain_per_dollar = (u - base_u) / size
                if u > base_u + 1e-9 and gain_per_dollar > best_gain:
                    best_name, best_size = o.name, size
                    best_gain, best_u = gain_per_dollar, u

        if best_name is None:
            alloc.log.append(
                f"STOPPED after ${spent:,.0f}: no remaining bid, at any size up "
                f"to the budget, raises {label} without breaching a node cap or "
                "the loss floor. Unspent budget is CASH, deliberately.")
            break

        book[best_name] += best_size
        spent += best_size
        alloc.log.append(
            f"  +${best_size:,.0f} -> {best_name:<24} "
            f"{label} {base_u:+.4f} -> {best_u:+.4f}  "
            f"({best_gain * 10_000:+.5f} per $10k)")
        base_u = best_u

    alloc.by_name = {k: v for k, v in book.items() if v > 0}
    return alloc


def mode_for(equity: float, *, target: float, start_equity: float,
             sessions_left: int) -> tuple[str, str]:
    """BASE or ATTACK, from position and time remaining -- not from mood.

    Behind with little time, a positive-median low-variance book cannot reach the
    target and holding it is the risk-seeking choice, not the safe one. Ahead
    with little time, variance is pure downside.
    """
    gap = (target - equity) / start_equity
    if sessions_left <= 0:
        return "CLOSED", "no sessions remain"
    need_per_session = gap / sessions_left
    if gap <= 0:
        return "BASE", ("already at or above target; every remaining unit of "
                        "variance is downside. Reduce risk.")
    if need_per_session > 0.015:
        return "ATTACK", (f"need {need_per_session:.2%}/session to reach target "
                          f"with {sessions_left} left. A +0.4% median book "
                          f"cannot get there; spend risk on DEFINED-LOSS "
                          f"convexity where the upside can change rank.")
    return "BASE", (f"need {need_per_session:.2%}/session, which a positive-median "
                    f"book can plausibly deliver. No need to buy dispersion.")
