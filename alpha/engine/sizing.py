"""Position sizing for a SIX-DAY tournament -- and the power check that gates it.

TWO IDEAS, BOTH BORROWED FROM THE PARENT PROJECT AND BOTH UNUSUAL HERE.

-------------------------------------------------------------------------------
1. THE MINIMUM DETECTABLE MOVE (MDM)
-------------------------------------------------------------------------------
The parent project spent five months learning to ask, before "what did the data
say?", the prior question: **could this sample have answered at all?** Its tool
is the minimum detectable effect,

        MDE = z * tracking_error / sqrt(T)

and the lesson it produced is blunt: on a 32-year CRSP replay, ZERO of thirteen
signals produced an effect the window could resolve. Every leaderboard printed
before that check was a ranking with no resolution behind it.

An options position has the same question and a much cleaner answer, because
the market quotes the denominator. A structure bought at the real ASK and
closed at the real BID does not break even at zero; it breaks even at a
specific underlying move. Call that the **minimum detectable move**:

        MDM = the underlying move at which this structure, entered at the
              quoted ask and exited at the quoted bid, returns zero

Then the position is only interesting if the model's predicted distribution
puts materially more mass beyond MDM than the option market's own implied
distribution does:

        edge = P_model(|move| > MDM) - P_implied(|move| > MDM)

If `edge` is small, the trade is a coin flip with a fee, however confident the
thesis sounds. This is the same discipline as the MDE gate, and it costs one
subtraction. Almost nobody does it, because the spread is invisible unless you
go and read the quote -- which is why the quality of the option feed matters so
much here, and why `alpha/data/chain.py` charges an explicit staleness penalty
when it has to carry a delayed quote forward rather than pretending it is live.

The MDM is computed from REAL QUOTES, never from a mid-price. A mid-price
break-even is a break-even you cannot trade.

-------------------------------------------------------------------------------
2. THE OBJECTIVE IS RANK, NOT SHARPE
-------------------------------------------------------------------------------
The parent project maximises long-run utility and is right to. This agent runs
for **five and a fraction trading days** and is judged, first criterion, on
P&L against a field of a few hundred other agents. Those are different problems
and they have different optimal policies.

Maximising expected log wealth over six days with N competitors does not
maximise P(top 3). The rank objective is convex in terminal equity: the
difference between +2% and +4% is nearly worthless, and the difference between
+15% and +30% is the whole prize. So the sizer optimises

        P(finish in the top of the field)

which produces genuinely different behaviour at the edges:

  * BEHIND, LATE   -> increase convexity. A safe loss is worth the same as a
                      large one; only the upside branch has value.
  * AHEAD, LATE    -> protect. Converting a lead into a coin flip is negative
                      in rank terms even when it is neutral in return terms.
  * EARLY          -> survive to see the catalysts. The window contains a known
                      list of them and being stopped out before Wednesday
                      forfeits the ones that have not happened yet.

**"Risky" is not "random", and it is not "undefined".** Every structure this
agent opens has a maximum loss that is known at entry and enforced at the
order level. That is what makes 25% of equity at risk a decision rather than an
accident: a defined-risk book cannot gap through its own stop overnight, and
the overnight gap is how a six-day account actually dies. Naked short options
are refused outright -- they are the one structure whose worst case is not
bounded, and their reward is a premium we do not need.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class TournamentPhase(str, Enum):
    EARLY = "early"        # >60% of the window remains
    MIDDLE = "middle"
    LATE = "late"          # <25% remains
    FINAL = "final"        # last session before the deadline


@dataclass(frozen=True)
class TournamentState:
    """Where we stand, which is an INPUT to sizing rather than a scoreboard."""

    equity: float
    starting_equity: float
    fraction_of_window_remaining: float
    """1.0 at kickoff, 0.0 at the submission deadline."""
    field_leader_estimate: float | None = None
    """Best guess at the return needed for a podium, as a fraction (0.15 = +15%).
    `None` when unknown -- and it is unknown for most of the week, so the sizer
    must behave sensibly without it rather than treating None as zero."""

    @property
    def total_return(self) -> float:
        return self.equity / self.starting_equity - 1.0

    @property
    def phase(self) -> TournamentPhase:
        r = self.fraction_of_window_remaining
        if r > 0.60:
            return TournamentPhase.EARLY
        if r > 0.25:
            return TournamentPhase.MIDDLE
        if r > 0.08:
            return TournamentPhase.LATE
        return TournamentPhase.FINAL

    @property
    def behind(self) -> bool:
        """Behind the return we believe a podium needs. Unknown target -> not
        behind: we do not take desperate risk to beat a number we invented."""
        if self.field_leader_estimate is None:
            return False
        return self.total_return < self.field_leader_estimate * 0.5


@dataclass(frozen=True)
class Structure:
    """A proposed options structure, priced at REAL quotes.

    `max_loss` is the defined, enforced worst case in dollars per unit. A
    structure that cannot state one is not representable here, which is how
    naked short options are excluded -- by the type, not by a check someone
    might forget to run.
    """

    symbol: str
    kind: str                 # long_call, debit_spread, long_straddle, credit_spread...
    direction: str = "both"
    """Which region of the underlying's distribution this structure PAYS in.

    "up" / "down" for directional structures, "both" for a straddle or strangle,
    "inside" for defined-risk short premium, which wins when the move stays
    SMALLER than the break-even.

    This is not decoration. Scoring a long call against a two-sided probability
    credits it for a crash -- the position would be sized up by the very outcome
    that makes it expire worthless. Every probability in this module routes
    through `direction`, so the mistake is not expressible."""
    entry_cost: float = 0.0   # per unit, at the ASK (debit) or credit received
    max_loss: float = 0.0     # per unit, > 0
    breakeven_move: float = 0.0
    """The underlying move at which this unit returns zero, as a fraction of spot.

    SIGNED for "up"/"down" structures (a bull put spread's break-even is usually
    negative -- below today's price); a MAGNITUDE for "both"/"inside"."""
    implied_move: float = 0.0 # the option market's own expected move over the life
    quote_spread_pct: float = 0.0   # (ask-bid)/mid on the structure, at decision time
    days_to_expiry: float = 1.0
    max_gain: float | None = None
    legs: tuple = ()
    staleness_penalty: float = 0.0
    """How much of `entry_cost` is our own charge for carrying a delayed quote
    forward. Recorded so a post-mortem can separate 'the thesis was wrong' from
    'we paid for stale data'."""
    quote: dict | None = None
    """For a SHARE structure (`alpha/engine/equity.py`): the stock quote seen at
    decision time, since the option-chain snapshot cannot carry it."""

    def __post_init__(self) -> None:
        if self.max_loss <= 0:
            raise ValueError(
                f"{self.kind} declared max_loss={self.max_loss}. Every structure this "
                "agent trades must state a positive, bounded worst case at entry. "
                "An unbounded structure is not sized down here -- it is not "
                "representable."
            )


#: A structure whose round-trip spread exceeds this fraction of its own maximum
#: loss is refused. The parent project's house failure mode is a correct
#: calculation against the wrong world; a beautiful edge inside a 40%-wide
#: option spread is exactly that.
MAX_SPREAD_TO_MAXLOSS = 0.25

#: RISK ENVELOPES, declared rather than argued about.
#:
#: The instruction for this competition is to go aggressive, and `aggressive` is
#: the default. What does NOT scale with the profile is the requirement that
#: every worst case be BOUNDED -- that is a property of the structures, not of
#: the size, and `maximum` is a much bigger bet rather than an unbounded one.
#:
#: Several profiles can run simultaneously against separate paper accounts (see
#: `config.known_roles()`), which turns "how aggressive should we be" from an
#: argument into a measurement with five days of real fills behind it.
PROFILES = {
    "conservative": {"per_thesis": 0.03, "aggregate": 0.20, "edge_scale_cap": 1.5},
    "aggressive":   {"per_thesis": 0.08, "aggregate": 0.50, "edge_scale_cap": 2.5},
    "maximum":      {"per_thesis": 0.15, "aggregate": 0.75, "edge_scale_cap": 3.5},
    # FLEET profiles (2026-08-28, alpha/fleet.py). `basket` is for a HUMAN PRIOR
    # spread over many names: 15 x 6% rather than 3 x 25%, because concentration
    # was measured as a negative-return decision (k=5 0.09x -> k=100 0.73x on
    # CRSP) and a prior has no edge to scale by (cap 1.0). `convex` is long
    # premium only: 5% per name of premium at risk, 40% aggregate.
    "basket":       {"per_thesis": 0.06, "aggregate": 0.80, "edge_scale_cap": 1.0},
    "convex":       {"per_thesis": 0.05, "aggregate": 0.40, "edge_scale_cap": 2.0},
}

#: Profiles that put more than half of equity at risk are competition-week
#: profiles: before kickoff they need `AAT_ALLOW_MAXIMUM=1`.
GATED_PROFILES = ("maximum", "basket")

DEFAULT_PROFILE = "aggressive"


def profile(name: str | None = None) -> dict:
    import os

    key = (name or os.getenv("AAT_RISK_PROFILE", DEFAULT_PROFILE)).strip().lower()
    if key not in PROFILES:
        raise ValueError(f"unknown risk profile {key!r}; have {sorted(PROFILES)}")
    if key in GATED_PROFILES and not maximum_allowed():
        raise ValueError(
            f"the {key!r} profile is disabled before kickoff: no mechanism has a "
            "positive live or counterfactual score yet, and 75% of equity at risk is a "
            "bet on a mechanism, not a rehearsal. Set AAT_ALLOW_MAXIMUM=1 to override."
        )
    return PROFILES[key]


def maximum_allowed(now=None) -> bool:
    """`maximum` is a competition-week profile. Before kickoff it needs an explicit
    override, so a rehearsal account cannot run it by habit."""
    import os
    from datetime import datetime, timezone

    if os.getenv("AAT_ALLOW_MAXIMUM", "").strip() == "1":
        return True
    try:
        from alpha import config
        kickoff = datetime.fromisoformat(config.COMPETITION["kickoff_utc"].replace("Z", "+00:00"))
    except Exception:                                                   # noqa: BLE001
        return False
    return (now or datetime.now(timezone.utc)) >= kickoff


#: Kept as module constants for the smoke tests and for anything that wants the
#: default envelope without threading a profile through.
BASE_RISK_PER_THESIS = PROFILES[DEFAULT_PROFILE]["per_thesis"]

#: Hard ceiling on TOTAL premium at risk across all open convex positions. The
#: complement is what guarantees the agent is still alive on Friday morning to
#: trade the jobs report -- being fully deployed on Tuesday and unable to touch
#: the biggest catalyst of the week is a way to lose that has nothing to do with
#: being wrong.
MAX_AGGREGATE_CONVEX_RISK = PROFILES[DEFAULT_PROFILE]["aggregate"]


@dataclass(frozen=True)
class SizingVerdict:
    approved: bool
    risk_fraction: float
    """Fraction of CURRENT equity to put at defined risk. 0.0 when refused."""
    mdm_edge: float
    """P_model(beyond breakeven) - P_implied(beyond breakeven)."""
    reason: str
    economics: dict | None = None
    """`payoff.Economics.as_dict()` once the ranker has integrated the payoff.
    The GATE (this verdict) says whether the trade may exist; the economics say
    whether it is worth more than cash and how it ranks against its siblings."""


def implied_probability_beyond(move: float, implied_move: float,
                               direction: str = "both") -> float:
    """The option market's own probability that |return| exceeds `move`.

    The market's expected absolute move over the life maps to a lognormal sigma
    by E|Z| = sigma*sqrt(2/pi), so sigma = implied_move * sqrt(pi/2). Then the
    two-sided tail is 2*(1 - Phi(move/sigma)).

    This is a deliberately plain model of the market's view -- it uses ONE
    number the chain gives us honestly (the at-the-money implied move) rather
    than pretending to reconstruct a full risk-neutral density from a handful of
    wide quotes. A more elaborate reconstruction would be more precise about a
    quantity whose input error dominates it.
    """
    if implied_move <= 0:
        return 0.0
    sigma = implied_move * math.sqrt(math.pi / 2.0)
    return _tail_mass(move, 0.0, sigma, direction)


def model_probability_beyond(move: float, predicted_move: float, predicted_sd: float,
                             direction: str = "both") -> float:
    """Our probability that |return| exceeds `move`, from the agent's forecast.

    `predicted_move` is the CENTRE of the forecast (signed), `predicted_sd` its
    uncertainty. Both come from the brains; a brain that cannot state an
    uncertainty does not get sized, because a point forecast with no spread
    silently asserts certainty.
    """
    if predicted_sd <= 0:
        raise ValueError(
            "predicted_sd must be positive. A forecast with no stated uncertainty "
            "is an assertion of certainty and will size itself to the ceiling."
        )
    return _tail_mass(move, predicted_move, predicted_sd, direction)


def _tail_mass(move: float, centre: float, sd: float, direction: str) -> float:
    """Probability the outcome lands in the region this structure PAYS in.

    `move` is read differently per direction, and the difference is load-bearing:

      "up" / "down"   a SIGNED break-even return. A bull put spread whose
                      break-even sits BELOW the current price wins across most
                      of the distribution, and its threshold is negative. Taking
                      an absolute value here would flip that into a demand that
                      the stock RISE by the same amount -- turning the safest
                      structure on the board into the most demanding one.
      "both"/"inside" a MAGNITUDE. A straddle does not care which way.
    """
    if sd <= 0:
        return 0.0
    if direction == "up":
        return 1.0 - _norm_cdf((move - centre) / sd)
    if direction == "down":
        return _norm_cdf((move - centre) / sd)
    m = abs(move)
    outside = (1.0 - _norm_cdf((m - centre) / sd)) + _norm_cdf((-m - centre) / sd)
    if direction == "both":
        return outside
    if direction == "inside":
        return max(0.0, 1.0 - outside)
    raise ValueError(f"unknown direction {direction!r}")


def size(
    structure: Structure,
    predicted_move: float,
    predicted_sd: float,
    state: TournamentState,
    *,
    open_convex_risk: float = 0.0,
    conviction: float = 1.0,
    risk_profile: str | None = None,
) -> SizingVerdict:
    """How much defined risk this structure earns, or why it earns none."""
    env = profile(risk_profile)

    # -- Gate 1: can we even trade the quote we are looking at? -----------------
    spread_cost = structure.quote_spread_pct * structure.entry_cost
    if structure.max_loss > 0 and spread_cost / structure.max_loss > MAX_SPREAD_TO_MAXLOSS:
        return SizingVerdict(
            False, 0.0, 0.0,
            f"round-trip spread is {spread_cost / structure.max_loss:.0%} of max loss "
            f"(ceiling {MAX_SPREAD_TO_MAXLOSS:.0%}). The edge is inside the spread; "
            "this is a fee, not a trade.",
        )

    # -- Gate 2: the MDM power check ------------------------------------------
    p_model = model_probability_beyond(structure.breakeven_move, predicted_move,
                                       predicted_sd, structure.direction)
    p_implied = implied_probability_beyond(structure.breakeven_move, structure.implied_move,
                                           structure.direction)
    edge = p_model - p_implied

    if edge <= 0.0:
        return SizingVerdict(
            False, 0.0, edge,
            f"minimum detectable move is {structure.breakeven_move:.2%}; our forecast "
            f"puts {p_model:.1%} of mass beyond it against the market's {p_implied:.1%}. "
            "We do not disagree with the chain -- we agree with it and would pay to "
            "say so.",
        )

    # An edge that exists but is smaller than the noise in our own forecast is
    # the "0 of 13 signals were resolvable" failure in miniature: real-looking,
    # unresolvable, and it would size itself like a conviction if we let it.
    if edge < 0.05:
        return SizingVerdict(
            False, 0.0, edge,
            f"disagreement with the chain is {edge:+.1%} of probability mass -- below "
            "the 5pp floor. Directionally right and too small to pay the spread to "
            "express. Logged, not traded.",
        )

    # -- Sizing ---------------------------------------------------------------
    # Base risk scales with the probability edge, capped. An edge of 20pp is a
    # strong disagreement with a liquid market and is already near the ceiling;
    # anything larger usually means our forecast is wrong, not that the market is.
    base = (env["per_thesis"]
            * min(edge / 0.10, env["edge_scale_cap"])
            * max(0.0, min(conviction, 1.5)))

    multiplier, phase_note = _tournament_multiplier(state)
    risk = base * multiplier

    headroom = env["aggregate"] - open_convex_risk
    if headroom <= 0:
        return SizingVerdict(
            False, 0.0, edge,
            f"aggregate convex risk is already {open_convex_risk:.0%} of equity "
            f"(ceiling {env['aggregate']:.0%}). Refused so the agent is still "
            "solvent for the catalysts that have not happened yet.",
        )
    risk = min(risk, headroom)

    return SizingVerdict(
        True, risk, edge,
        f"MDM {structure.breakeven_move:.2%}: model {p_model:.1%} vs chain {p_implied:.1%} "
        f"= {edge:+.1%} edge. {phase_note} Risking {risk:.1%} of equity, max loss bounded.",
    )


def _tournament_multiplier(state: TournamentState) -> tuple[float, str]:
    """Rank-objective scaling. This is where 'risky' becomes a decision."""
    phase = state.phase
    ret = state.total_return

    if phase is TournamentPhase.EARLY:
        return 1.0, "Early: sizing normally to survive to the known catalysts."

    if phase is TournamentPhase.MIDDLE:
        if state.behind and ret >= 0.0:
            return 1.4, "Middle and behind the podium estimate: leaning into convexity."
        if state.behind:
            return 1.0, (
                f"Middle and behind, but {ret:+.1%} on the session's own capital: leaning "
                "into convexity FROM RED is how a drawdown compounds. Lean in from flat.")
        return 1.1, "Middle: full participation."

    # Late and final. The rank objective diverges hardest from the utility
    # objective here, in both directions.
    if ret > 0.20:
        return 0.4, (
            f"Late with {ret:+.1%} banked: converting a lead into a coin flip is "
            "negative in RANK terms even when it is neutral in return terms. Protecting."
        )
    if ret < 0.0:
        # THE CLAMP. The rank argument is sound and it is also how a drawdown
        # becomes a disqualification: a book that is DOWN and doubling is one
        # bad session from unrecoverable, and the judged criteria ask for risk
        # gates. Convexity is bought from flat, not from red. (Audit defect 2,
        # `docs/night/2026-08-26_EXECUTION_AUDIT.md`.)
        return 1.0, (
            f"Late at {ret:+.1%}: the rank objective says maximise convexity when behind, "
            "and it is right that a small loss and a large loss score alike. It is also "
            "how -2% becomes -20%. Sizing normally; the multiplier is clamped at 1.0 "
            "while the return is negative."
        )
    if state.behind:
        mult = 2.0 if phase is TournamentPhase.FINAL else 1.6
        return mult, (
            f"Late at {ret:+.1%} and off the podium: a small loss and a large loss score "
            "the same, so only the upside branch has value. Maximum convexity, still "
            "defined-risk."
        )
    return 1.0, "Late and mid-field: sizing normally."


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
