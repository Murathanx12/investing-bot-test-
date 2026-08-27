"""SHAPE-AWARE CONSTRUCTION -- the idea this whole agent is built on.

THE CLAIM
=========
Every trading agent in this competition will decide **which way** a name is
going. Almost none will decide **what shape** the edge has, and the shape is
what picks the instrument.

A signal's *quantile curve* -- mean forward return by decile of the score --
comes in recognisably different shapes, and each shape is structurally a
different financial instrument:

    TAIL          d1..d9 flat, d10 jumps          the payoff IS an option
                  -> buy convexity. Small premium, large payoff, usually zero.

    STEP          a cliff, then a PLATEAU         the payoff is a stock book
                  -> buy breadth. No convexity exists to pay for; a top-k
                     slice sits on the flattest part of the curve, and if you
                     want options at all you should be SELLING them, because a
                     flat top decile is a paid opinion that the tail is empty.

    GRADIENT      monotone, no jump               position size, not structure.

    INVERTED      monotone the WRONG way          the reversed signal is the
                                                  candidate; the signal is not.

    DEGENERATE    a high t on 3 distinct names    one bucket, not an edge.
                                                  Refuse it.

Buying a call on a STEP signal is paying for a tail the data says is not there.
Buying a hundred names on a TAIL signal is diluting the only decile that pays.
Both are ordinary, both look like "using options", and both are wrong for a
reason that is measurable in advance.

WHERE THE SHAPES COME FROM
==========================
Not from this week. They were measured in the parent research project
(Aegis-Finance, source commit 44c8352) by replaying a frozen CRSP daily history
-- 1993-2024, 32 years, ~500-name PIT universe -- and reading the decile curve
for each signal BEFORE building any portfolio from it. Three independent data
sources feed them: CRSP prices, WRDS accounting ratios (PIT-stamped by
`public_date`), and IBES analyst consensus.

The numbers in `SHAPE_PRIOR` below are that measurement. They are a PRIOR, and
they are labelled as one: a 32-year decile curve is a statement about a
characteristic's long-run cross section, not a promise about five trading days
in September 2026. The agent re-measures what it can on the live universe and
records both; where they disagree, the disagreement is the finding and the
position shrinks.

WHAT THIS IS NOT
================
It is not a claim of alpha. The parent project's own power arithmetic says
these effects need decades to resolve against a matched benchmark, and it says
so on the record. What survives that arithmetic and is useful *here* is the
much weaker, much better-supported statement:

    the SHAPE of a signal's payoff is a stable property of the signal,
    and it tells you which instrument can express it.

That statement needs far less evidence than "this signal makes money", because
it is a claim about the geometry of the payoff rather than its magnitude.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Shape(str, Enum):
    TAIL = "tail"
    STEP = "step"
    GRADIENT = "gradient"
    INVERTED = "inverted"
    DEGENERATE = "degenerate"


class Instrument(str, Enum):
    LONG_CONVEXITY = "long_convexity"      # debit spread / long call / long straddle
    SHORT_CONVEXITY = "short_convexity"    # defined-risk credit spread / condor
    WIDE_EQUITY = "wide_equity"            # many names, no options
    SIZED_EQUITY = "sized_equity"          # a few names, size by conviction
    REFUSE = "refuse"


@dataclass(frozen=True)
class SignalShape:
    """A measured decile curve, reduced to the facts that pick an instrument."""

    name: str
    shape: Shape
    decile_lift: float
    """Top decile mean annual return minus the median decile's, in %/yr.

    This is the number that says whether a tail exists to buy. A STEP signal can
    have a large *level* edge and a near-zero decile lift; that combination is
    exactly what makes buying calls on it wrong.
    """
    ic_t: float
    """Rank-IC t-statistic over NON-OVERLAPPING dates. Ranks signals; does NOT
    pick the instrument -- momentum beats ROE on terminal wealth with a WEAKER
    ic_t, which is the whole reason this module exists."""
    monotonicity: float
    """Spearman correlation of decile index against decile mean return, [-1, 1]."""
    distinct_names_per_slot: float
    """Turnover-of-identity. `size_large` scores ic_t 2.35 on 3.6 distinct names
    per slot across 32 years -- a high t on one bucket. Only the holdings census
    can see this, and without it the leaderboard looks fine."""
    source: str = "aegis-finance@44c8352 farm diagnose, CRSP 1993-2024"
    notes: str = ""
    live_reestimate: float | None = field(default=None, compare=False)
    """Filled in when the tournament re-measures this signal on the live
    universe. `None` means not yet checked, which is different from checked and
    agreeing -- so it is stored as None and never as 0.0."""


#: THE PRIOR. Every entry is a measurement with a receipt in the parent project,
#: not a guess. Signals that FAILED are kept, because a library that only lists
#: its winners cannot warn you about the shape of a loser.
SHAPE_PRIOR: dict[str, SignalShape] = {
    "mom_12_1": SignalShape(
        name="mom_12_1",
        shape=Shape.TAIL,
        decile_lift=5.1,           # 14.1 -> 19.2 across deciles
        ic_t=3.1,
        monotonicity=0.85,
        distinct_names_per_slot=28.0,
        notes=(
            "12-1 price momentum. The canonical TAIL: the top decile carries the "
            "edge and widening the book spends it. Beat an age-matched control by "
            "+9.23%/yr at k=20 on a WEAKER ic_t than profit_roe -- the reason ic_t "
            "must not pick the instrument. Systematically selects acquisition "
            "targets, so its exits are event-heavy."
        ),
    ),
    "rev_dispersion": SignalShape(
        name="rev_dispersion",
        shape=Shape.TAIL,
        decile_lift=8.4,           # 10.6 -> 19.0
        ic_t=3.14,
        monotonicity=0.88,
        distinct_names_per_slot=41.0,
        notes=(
            "Dispersion of sell-side analyst estimates (IBES). The strongest TAIL "
            "on the grid: top-decile lift +7.6 against +2.3 for the composite that "
            "contains it. Equal-weight z-averaging a TAIL with GRADIENT signals "
            "washes the tail out -- always check a stack against its own best "
            "component. HIGH ANALYST DISAGREEMENT IS ITSELF AN OPTIONS THESIS: "
            "it is a forecast of realised dispersion, which is what a straddle is "
            "long. This is the signal that most deserves an option."
        ),
    ),
    "profit_roe": SignalShape(
        name="profit_roe",
        shape=Shape.STEP,
        decile_lift=0.5,           # PLATEAU 14.3-14.8 across deciles 7-10
        ic_t=4.18,
        monotonicity=0.90,
        distinct_names_per_slot=95.0,
        notes=(
            "Return on equity (WRDS finratio, PIT by public_date). The strongest "
            "cross-sectional evidence in the parent project AND one of its weakest "
            "books -- because a top-4% slice sits on the plateau. ~9%/yr cliff "
            "below the median, then flat across deciles 7-10. Tested for and NOT "
            "confounded by listing age (age pct 49.5 at k=100). Build it WIDE. "
            "Buying calls on this is paying for a tail that was measured to be absent."
        ),
    ),
    "value_bm": SignalShape(
        name="value_bm",
        shape=Shape.INVERTED,
        decile_lift=-4.2,
        ic_t=-2.1,
        monotonicity=-0.90,
        distinct_names_per_slot=60.0,
        notes=(
            "Book-to-market. Monotone in the WRONG direction on a mega-liquid "
            "top-500 universe: extreme high B/M there selects distress, not value. "
            "The REVERSED signal is the candidate. Kept in the library as a live "
            "example of a shape that says 'you have the sign backwards', which no "
            "amount of terminal-wealth reporting would have told us."
        ),
    ),
    "size_large": SignalShape(
        name="size_large",
        shape=Shape.DEGENERATE,
        decile_lift=1.1,
        ic_t=2.35,
        monotonicity=0.4,
        distinct_names_per_slot=3.6,
        notes=(
            "Market cap. ic_t 2.35 on THREE POINT SIX distinct names per slot over "
            "32 years -- it is a list, not a rule. Only the holdings census can see "
            "this; the leaderboard row looked ordinary. REFUSED."
        ),
    ),
    "liquid": SignalShape(
        name="liquid",
        shape=Shape.DEGENERATE,
        decile_lift=2.0,
        ic_t=2.55,
        monotonicity=0.5,
        distinct_names_per_slot=10.0,
        notes=(
            "Dollar volume. Best t on the 2013-2024 grid and a FAANG list: MSFT in "
            "123 of 124 samples, GOOG 87, AAPL 81. Breadth slope -1.11, gone by "
            "k=20, negative by k=30 -- the signature of a description of its own "
            "decade rather than a rule. REFUSED."
        ),
    ),
}


#: shape -> instrument. The mapping IS the thesis; it is a table so it can be
#: read, argued with, and shown to a judge on one slide.
INSTRUMENT_FOR_SHAPE: dict[Shape, Instrument] = {
    Shape.TAIL: Instrument.LONG_CONVEXITY,
    Shape.STEP: Instrument.WIDE_EQUITY,
    Shape.GRADIENT: Instrument.SIZED_EQUITY,
    Shape.INVERTED: Instrument.REFUSE,      # the reverse is a DIFFERENT signal
    Shape.DEGENERATE: Instrument.REFUSE,
}

#: Below this decile lift there is no tail worth paying a premium for, however
#: good the signal's t-statistic is. Set at the plateau width measured for
#: `profit_roe` (0.5 %/yr) with headroom -- a signal has to clear the flattest
#: thing we have ever called flat by a real margin before we buy convexity on it.
MIN_DECILE_LIFT_FOR_CONVEXITY = 2.0

#: How many times the curve's own typical decile step the top decile must clear
#: before we call it a discontinuity rather than the end of a ramp. A linear
#: curve scores about 2.5 here by construction, so the bar sits well above it.
TAIL_STEP_RATIO = 4.0

#: How much of the curve's total range the TOP THREE deciles may span before we
#: stop calling them a plateau. A genuine step flattens out (profit_roe spans
#: 14.5-14.8 across a 10.6-wide curve, ~3%); a straight ramp spans ~22% here and
#: is a GRADIENT, to be expressed by size rather than by breadth.
MAX_PLATEAU_RANGE = 0.15

#: A signal that recycles fewer than this many distinct names per slot is a
#: watchlist someone wrote down, not a cross-sectional rule.
MIN_DISTINCT_NAMES_PER_SLOT = 8.0


@dataclass(frozen=True)
class ConstructionVerdict:
    signal: str
    shape: Shape
    instrument: Instrument
    breadth: int
    """Names (or option positions) to hold. Derived from the shape, not chosen."""
    reason: str
    tradeable: bool


def classify(curve: list[float], distinct_names_per_slot: float) -> Shape:
    """Reduce a measured decile curve to a shape.

    `curve` is decile mean forward return, index 0 = lowest score decile. It is
    read as GEOMETRY, not as a ranking: the questions are "does it rise", "is the
    rise concentrated at the top", and "is there anything here at all".
    """
    if len(curve) < 5:
        raise ValueError(f"need at least 5 deciles to read a shape, got {len(curve)}")
    if distinct_names_per_slot < MIN_DISTINCT_NAMES_PER_SLOT:
        return Shape.DEGENERATE

    n = len(curve)
    ranks = list(range(n))
    mono = _spearman(ranks, curve)
    if mono < -0.5:
        return Shape.INVERTED

    # The top decile's lift over the plateau beneath it. Measured against the
    # mean of the upper half EXCLUDING itself: measured against the whole curve,
    # a strong cliff at the MEDIAN would masquerade as a tail.
    upper = curve[n // 2 : -1]
    upper_mean = sum(upper) / len(upper) if upper else curve[-2]
    top_vs_plateau = curve[-1] - upper_mean

    # A lift in %/yr is not by itself evidence of a tail, and this is the trap
    # worth spelling out: on a perfectly LINEAR curve the top decile also sits
    # above the mean of the ones below it, by about two and a half steps. Read
    # absolutely, every monotone signal looks like a tail and the agent buys
    # convexity on all of them. So the lift is judged against the curve's OWN
    # typical step -- a tail is a DISCONTINUITY, and a discontinuity is only
    # visible relative to the continuous part.
    steps = [curve[i + 1] - curve[i] for i in range(n - 2)]  # excludes the last step
    typical_step = sorted(abs(s) for s in steps)[len(steps) // 2] if steps else 0.0

    is_discontinuity = (
        top_vs_plateau >= MIN_DECILE_LIFT_FOR_CONVEXITY
        and (typical_step <= 0 or top_vs_plateau / typical_step >= TAIL_STEP_RATIO)
    )
    if is_discontinuity:
        return Shape.TAIL

    # STEP: a large level edge across the curve whose TOP is FLAT. Two
    # conditions, and the second is the one that is easy to forget.
    #
    # The cliff: upper half against lower half, not top against median -- on a
    # step curve the median sits ON the plateau and the cliff is invisible from
    # there.
    lower = curve[: n // 2]
    lower_mean = sum(lower) / len(lower)
    upper_half_mean = sum(curve[n // 2 :]) / len(curve[n // 2 :])
    cliff = upper_half_mean - lower_mean

    # The plateau: a straight RAMP also has a high upper half and a low lower
    # half, and without this second test every monotone signal is a STEP and
    # gets built sixty names wide. What distinguishes a step from a ramp is that
    # a step stops rising -- so measure whether the top actually flattens.
    full_range = max(curve) - min(curve)
    top = curve[-3:]
    plateau_flatness = (max(top) - min(top)) / full_range if full_range > 0 else 1.0

    if cliff >= MIN_DECILE_LIFT_FOR_CONVEXITY and plateau_flatness <= MAX_PLATEAU_RANGE:
        return Shape.STEP

    if mono >= 0.5:
        return Shape.GRADIENT
    return Shape.DEGENERATE


def construction_for(signal: str, *, prior: dict[str, SignalShape] | None = None) -> ConstructionVerdict:
    """The instrument and breadth this signal's shape licenses.

    Refuses an unknown signal rather than guessing a shape for it. An unmeasured
    signal is not a GRADIENT with unknown parameters -- it is a signal whose
    geometry nobody has looked at, and the entire point of this module is that
    you look first.
    """
    table = prior if prior is not None else SHAPE_PRIOR
    if signal not in table:
        return ConstructionVerdict(
            signal=signal,
            shape=Shape.DEGENERATE,
            instrument=Instrument.REFUSE,
            breadth=0,
            reason=(
                f"{signal!r} has no measured decile curve. An unmeasured signal is "
                "refused, not defaulted: picking an instrument without a shape is "
                "the exact mistake this module exists to prevent."
            ),
            tradeable=False,
        )

    s = table[signal]
    instrument = INSTRUMENT_FOR_SHAPE[s.shape]

    if s.shape is Shape.TAIL and s.decile_lift < MIN_DECILE_LIFT_FOR_CONVEXITY:
        # Belt and braces: a curve can be labelled TAIL by a prior and still not
        # clear the premium bar once re-measured.
        return ConstructionVerdict(
            signal=signal,
            shape=s.shape,
            instrument=Instrument.SIZED_EQUITY,
            breadth=20,
            reason=(
                f"labelled TAIL but decile lift {s.decile_lift:.1f}%/yr is below the "
                f"{MIN_DECILE_LIFT_FOR_CONVEXITY:.1f}%/yr premium bar -- express it as "
                "equity, not convexity."
            ),
            tradeable=True,
        )

    if instrument is Instrument.REFUSE:
        why = {
            Shape.INVERTED: (
                f"monotonicity {s.monotonicity:+.2f} -- the curve runs the wrong way. "
                "The REVERSED signal is the candidate and it has to be measured "
                "separately; flipping a sign is not a re-measurement."
            ),
            Shape.DEGENERATE: (
                f"{s.distinct_names_per_slot:.1f} distinct names per slot -- a "
                f"watchlist, not a rule (ic_t {s.ic_t:.2f} notwithstanding)."
            ),
        }[s.shape]
        return ConstructionVerdict(signal, s.shape, instrument, 0, why, tradeable=False)

    breadth = {
        Instrument.LONG_CONVEXITY: 4,    # NARROW: the tail is the whole payoff
        Instrument.WIDE_EQUITY: 60,      # WIDE: cut tracking error on a plateau
        Instrument.SIZED_EQUITY: 20,
    }[instrument]

    reason = {
        Instrument.LONG_CONVEXITY: (
            f"TAIL: top decile lifts {s.decile_lift:+.1f}%/yr over the plateau, so the "
            "payoff is already shaped like an option -- buy the convexity NARROW "
            f"(n={breadth}) rather than diluting it across a book."
        ),
        Instrument.WIDE_EQUITY: (
            f"STEP: the top of the curve is a PLATEAU (lift {s.decile_lift:+.1f}%/yr), "
            "so there is no tail to pay a premium for. Build WIDE "
            f"(n={breadth}): breadth cuts tracking error at no cost to the edge, "
            "which is the cheap lever the parent project measured and never pulled."
        ),
        Instrument.SIZED_EQUITY: (
            f"GRADIENT (monotonicity {s.monotonicity:+.2f}): express by SIZE, not by "
            "structure -- there is no discontinuity for an option to sit on."
        ),
    }[instrument]

    return ConstructionVerdict(signal, s.shape, instrument, breadth, reason, tradeable=True)


def _spearman(a: list[float], b: list[float]) -> float:
    ra, rb = _rank(a), _rank(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra) ** 0.5
    vb = sum((y - mb) ** 2 for y in rb) ** 0.5
    return 0.0 if va == 0 or vb == 0 else cov / (va * vb)


def _rank(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


# ---------------------------------------------------------------------------
# SHAPE CLAIMS ON A FORECAST -- measured, or said out loud to be otherwise.
#
# Found by `python -m scripts.reachability` on 2026-08-27: this module, whose
# own first line calls it "the idea this whole agent is built on", was imported
# by NOTHING. Zero call sites. `construction_for` -- the function that decides
# whether a curve licenses convexity at all -- had never run in production.
#
# Meanwhile five of six brains hardcode `signal_shape="tail"` on every forecast
# they emit, and TAIL is the shape whose entry above reads "the payoff IS an
# option -> buy convexity". So the justification for buying premium was a string
# literal, asserted six times, measured zero times, and written onto every
# ledger row where a later reader would see six brains agreeing.
#
# The two namespaces had also drifted apart without anyone noticing:
# `SHAPE_PRIOR` is keyed by SIGNAL name (`mom_12_1`, `profit_roe` -- the parent
# project's cross-sectional characteristics), while `Forecast.signal_shape`
# holds a SHAPE name (`tail`). `construction_for("vol_gap")` would have returned
# REFUSE. Nothing was wrong with either half; they simply never met.
#
# The fix is NOT to gate on the prior. These brains forecast a time-series
# volatility gap; the prior describes cross-sectional decile curves. They are
# different objects and forcing one through the other would refuse everything.
#
# The fix is that a shape claim must carry its own provenance. `declared:tail`
# is a hypothesis about geometry that nobody has measured for this brain, and it
# reads that way on the row. `tail` unqualified is reserved for a claim backed
# by a curve in `SHAPE_PRIOR`, and `Forecast` refuses anything else.

DECLARED_PREFIX = "declared:"

#: Shapes for which a measured decile curve exists in this module, by shape.
#: Derived, never typed twice -- a literal list here could disagree with the
#: prior and there would be no test that noticed.
def measured_shapes() -> set[str]:
    return {s.shape.value for s in SHAPE_PRIOR.values()}


def parse_claim(signal_shape: str | None) -> tuple[str | None, bool]:
    """(shape, is_measured) for a `Forecast.signal_shape` value.

    `None` -> (None, False). A brain that makes no shape claim is honest and
    this says nothing against it.
    """
    if not signal_shape:
        return None, False
    if signal_shape.startswith(DECLARED_PREFIX):
        return signal_shape[len(DECLARED_PREFIX):], False
    return signal_shape, True


def validate_claim(signal_shape: str | None, *, brain: str = "") -> None:
    """Raise unless the claim is either measured FOR THIS SIGNAL, or declared.

    Called from `Forecast.__post_init__`, which is the only place every forecast
    in the system must pass through -- and the reason this check lives there
    rather than in the runner is that a brain used in a script, a backtest or a
    notebook must not be able to skip it.

    The measurement must belong to THIS signal. An earlier draft asked only
    whether any curve in `SHAPE_PRIOR` had the claimed shape, which passes
    `"tail"` for every brain on the strength of `mom_12_1`'s curve -- borrowing
    a measurement from an unrelated signal because the two share an adjective.
    That is the same evidence-by-analogy the refuted-routes rewrite removed
    this morning, reintroduced in the check written to prevent it.
    """
    if signal_shape is None:
        return
    shape, measured = parse_claim(signal_shape)
    if shape not in {s.value for s in Shape}:
        raise ValueError(
            f"{brain}: signal_shape={signal_shape!r} is not a shape. Valid: "
            f"{sorted(s.value for s in Shape)}, optionally prefixed {DECLARED_PREFIX!r}.")
    if not measured:
        return
    curve = SHAPE_PRIOR.get(brain)
    if curve is None:
        raise ValueError(
            f"{brain}: claims signal_shape={signal_shape!r} unqualified, which asserts a "
            f"decile curve measured for {brain!r}. SHAPE_PRIOR has no entry for it -- it "
            "forecasts a time-series volatility gap, not a cross-sectional characteristic, "
            f"so there is no curve to have. Write {DECLARED_PREFIX + shape!r} if the shape is "
            "a hypothesis about geometry. Five brains asserted 'tail' -- 'the payoff IS an "
            "option, buy convexity' -- as a string literal, and that literal was the standing "
            "justification for buying premium while the chain was overpricing it.")
    if curve.shape.value != shape:
        raise ValueError(
            f"{brain}: claims shape {shape!r} but its measured curve is "
            f"{curve.shape.value!r} ({curve.source}).")


def licenses_convexity(signal_shape: str | None, *, brain: str = "") -> tuple[bool, str]:
    """May this shape claim be CITED as evidence for buying convexity?

    Not a refusal on its own -- `alpha/claims.py` decides admissibility and the
    sizer decides economics. This answers the narrower question a ledger reader
    needs: was 'tail' on this row a measurement, or a word?
    """
    shape, measured = parse_claim(signal_shape)
    if measured and brain and brain not in SHAPE_PRIOR:
        return False, (f"{shape!r} is claimed as measured but SHAPE_PRIOR has no curve for "
                       f"{brain!r}; the claim borrows another signal's geometry")
    if shape is None:
        return False, "no shape claim"
    if not measured:
        return False, (f"{shape!r} is DECLARED, not measured -- no decile curve backs it, so "
                       "it is a hypothesis about geometry and may not be cited as evidence "
                       "that a tail exists to buy")
    if shape != Shape.TAIL.value:
        return False, f"{shape!r} is measured and is not TAIL; convexity is not what it licenses"
    return True, "measured TAIL curve"
