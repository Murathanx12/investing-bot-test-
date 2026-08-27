"""HUMAN_THESIS_ARM_v1 -- a typed wire from Murat's view into the tournament.

    python -m scripts.thesis --symbol NVDA --direction up --expected-move 0.06 \
        --catalyst "Q2 FY27 print" --catalyst-at 2026-08-26T20:20Z \
        --horizon 3 --conviction 0.9 \
        --reason "AI demand accelerating faster than the guide implies" \
        --falsifier "Q3 revenue guide at or below $104bn, or GM guide below 74%"

WHY THIS EXISTS
===============
On 26 Aug NVIDIA guided Q3 to $108.0bn against $104.2bn expected, China-free,
and the stock rose ~6.8% against an implied move of ~5.4%. Murat had said
beforehand that NVDA would beat. The sealed research vector independently ranked
the Q3 guide the #1 variable and flagged memory as the constrained node, hours
before the filing confirmed a $160bn memory commitment.

The books held broad index straddles and a peer straddle on AMD, and lost.

The information existed and never became a position. Not because anything
overruled it -- because **there was no channel through which a human thesis could
enter the tournament at all.** It lived in a chat message. A chat message is not
an input.

WHAT THIS IS NOT
================
Not an override. A thesis recorded here becomes a FORECAST, and a forecast goes
through the identical path as every brain: the claim matrix, the chain's own
width, the sizer, the refuted routes, admission, the book limits, the daily
latch. It cannot skip one of them, and `alpha/human.py` contains no order code
and imports no broker.

It is also not a place to be vague. The reason the field list is long is that a
free-form "I like NVDA" cannot be graded, cannot be falsified, and -- the
expensive part -- cannot pick an instrument. "Up" and "up more than the chain
charges" are different bets and buy different things.

THE FIELDS, AND WHY EACH ONE REFUSES
====================================
direction + magnitude   TOGETHER they choose the instrument. `direction` alone
                        buys shares or a vertical; `magnitude` alone buys or
                        sells the absolute move; both buy a shaped directional
                        structure. Declaring NEITHER is not a thesis and is
                        refused. See `alpha/claims.py`.
expected_move           a signed number, required with a direction. "Up" is not
                        actionable: up 2% against a 5.4% implied move is an
                        argument for SELLING premium, and up 9% is an argument
                        for buying it. Same view, opposite trades.
catalyst + catalyst_at  what resolves this, and when. Without a date there is no
                        horizon, and a thesis with no horizon can never be
                        graded, only remembered fondly.
falsifier               what would make this WRONG, stated before the outcome.
                        Required. On 26 Aug the sealed vector's bear trigger --
                        "a Q3 GM guide below 74%" -- landed exactly on its line,
                        and that was only meaningful because it was written down
                        in advance.
stated_at < catalyst_at a thesis recorded after its catalyst is a memory. This
                        refuses rather than accepting a backdated timestamp,
                        because the whole value of the arm is that it is
                        PROSPECTIVE.

GRADING
=======
Every thesis is written to `state/human_theses.jsonl` and enters the ordinary
counterfactual machinery under the brain name `human:<author>`. Over enough
theses the measurable question is not "was Murat right" but **in which domains
is the human arm better than the engine, and at which stage** -- direction,
instrument, or size. Those are different skills and the ledger can separate them.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alpha.brains.base import Forecast

#: Which way. `none` is a legitimate answer -- it means "I have a width view and
#: no directional one", not "I have no view".
DIRECTIONS = ("up", "down", "none")

#: The width claim, stated RELATIVE TO THE CHAIN. Not "volatile" -- the chain is
#: already charging for volatility, and the only tradeable claim is that its
#: price is wrong in a named direction.
MAGNITUDES = ("wider", "narrower", "unknown")

STATE_DIR = Path(os.getenv("AAT_LEDGER_DIR") or "state")
LOG = "human_theses.jsonl"

#: Placeholder spread for a pure DIRECTION thesis. It is never used: the runner
#: integrates a `direction` claim at the CHAIN's own implied move
#: (`runner.effective_sd`), which is exactly right here -- a human states which
#: way and by how much, and has no business supplying a sigma. `Forecast`
#: requires sd > 0, so this exists only to satisfy that constructor, and it is
#: named rather than inlined so nobody later mistakes it for an estimate.
_SD_PLACEHOLDER_UNUSED = 0.01


class ThesisRefusal(ValueError):
    """The thesis is missing something without which it cannot be graded."""


def _parse_ts(value: str, field_name: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ThesisRefusal(f"{field_name}={value!r} is not an ISO timestamp.") from exc
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class Thesis:
    author: str
    symbol: str
    direction: str
    magnitude: str
    catalyst: str
    catalyst_at_utc: str
    horizon_days: float
    reason: str
    falsifier: str
    expected_move: float | None = None
    """Signed expected return over the horizon, as a fraction of spot."""
    conviction: float = 1.0
    stated_at_utc: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.direction not in DIRECTIONS:
            raise ThesisRefusal(f"direction must be one of {DIRECTIONS}, got {self.direction!r}.")
        if self.magnitude not in MAGNITUDES:
            raise ThesisRefusal(f"magnitude must be one of {MAGNITUDES}, got {self.magnitude!r}.")
        if self.direction == "none" and self.magnitude == "unknown":
            raise ThesisRefusal(
                "a thesis with no direction and no width claim is not a thesis. State which "
                "way, or state that the chain's price for the move is wrong, or both."
            )
        if self.direction != "none":
            if self.expected_move is None:
                raise ThesisRefusal(
                    f"direction={self.direction!r} needs an --expected-move. 'Up' does not pick "
                    "an instrument: up 2% against a 5.4% implied move argues for SELLING "
                    "premium and up 9% argues for buying it. Same view, opposite trades."
                )
            if self.expected_move == 0.0:
                raise ThesisRefusal("expected_move=0 with a stated direction contradicts itself.")
            if (self.expected_move > 0) != (self.direction == "up"):
                raise ThesisRefusal(
                    f"direction={self.direction!r} and expected_move={self.expected_move:+.4f} "
                    "disagree on the sign."
                )
        elif self.expected_move not in (None, 0.0):
            raise ThesisRefusal(
                "direction='none' may not carry a non-zero expected_move -- that is a "
                "directional claim wearing a width label."
            )
        if len(self.falsifier.strip()) < 15:
            raise ThesisRefusal(
                "a falsifier is required and must be specific enough to check. What "
                "OBSERVATION would make this thesis wrong? Without one the thesis can only "
                "ever be remembered, never graded."
            )
        if len(self.reason.strip()) < 10:
            raise ThesisRefusal("state the reason; it is what gets distilled into a pattern.")
        if not 0.0 < self.conviction <= 1.5:
            raise ThesisRefusal(f"conviction must be in (0, 1.5], got {self.conviction}.")
        if self.horizon_days <= 0:
            raise ThesisRefusal("horizon_days must be positive.")

        stated = _parse_ts(self.stated_at_utc or datetime.now(timezone.utc).isoformat(),
                           "stated_at_utc")
        object.__setattr__(self, "stated_at_utc", stated.isoformat(timespec="seconds"))
        catalyst_at = _parse_ts(self.catalyst_at_utc, "catalyst_at_utc")
        object.__setattr__(self, "catalyst_at_utc", catalyst_at.isoformat(timespec="seconds"))
        if stated >= catalyst_at:
            raise ThesisRefusal(
                f"stated_at {stated.isoformat()} is not before the catalyst at "
                f"{catalyst_at.isoformat()}. A thesis recorded after its own catalyst is a "
                "memory, and recording it as a forecast would poison every calibration "
                "number this arm exists to produce."
            )

    # ------------------------------------------------------------------ claim
    @property
    def claim(self) -> str:
        """Which part of the distribution this thesis has evidence for.

        Maps onto `Forecast.claim`, so `alpha/claims.py` decides the admissible
        instruments and `runner.effective_sd` decides the width it is
        integrated at. A human does not get a private path through the engine.
        """
        has_dir = self.direction != "none"
        has_width = self.magnitude != "unknown"
        if has_dir and has_width:
            return "distribution"
        return "direction" if has_dir else "dispersion"

    @property
    def brain(self) -> str:
        return f"human:{self.author}"

    def thesis_id(self) -> str:
        body = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(body.encode()).hexdigest()[:16]

    # --------------------------------------------------------------- forecast
    def to_forecast(self, *, implied_move: float | None = None) -> Forecast:
        """The tournament's own object. No special privileges attach to it.

        For a `direction` claim the sd is a placeholder the runner replaces with
        the chain's implied move. For a width claim it must come from somewhere
        real, so `implied_move` is REQUIRED and the thesis's own magnitude word
        tilts it: `wider` says the outcome exceeds the quote, `narrower` says it
        falls short. The tilt is a fixed 25% rather than a number the human
        picks, because a human who could name that number would have named a
        sigma instead of a word.
        """
        if self.claim == "direction":
            sd = _SD_PLACEHOLDER_UNUSED
        else:
            if not implied_move or implied_move <= 0:
                raise ThesisRefusal(
                    f"a {self.claim!r} claim is a claim that the CHAIN's width is wrong, so it "
                    "needs the chain's width to be relative to. None was available for "
                    f"{self.symbol}; refusing rather than substituting a realised-vol estimate, "
                    "which is the substitution that made every long option look cheap."
                )
            tilt = 1.25 if self.magnitude == "wider" else 0.75
            sd = implied_move * tilt

        return Forecast(
            brain=self.brain,
            symbol=self.symbol,
            horizon_days=float(self.horizon_days),
            centre=float(self.expected_move or 0.0),
            sd=sd,
            conviction=float(self.conviction),
            claim=self.claim,
            rationale=f"{self.reason} [catalyst: {self.catalyst}]",
            evidence={
                "source": "human_thesis",
                "thesis_id": self.thesis_id(),
                "author": self.author,
                "stated_at_utc": self.stated_at_utc,
                "catalyst": self.catalyst,
                "event_date": self.catalyst_at_utc[:10],
                "falsifier": self.falsifier,
                "direction": self.direction,
                "magnitude": self.magnitude,
                "sd_is_placeholder": self.claim == "direction",
                **self.evidence,
            },
        )


def path() -> Path:
    return STATE_DIR / LOG


def record(t: Thesis) -> str:
    """Append the thesis. Returns its id. Append-only: a thesis is not editable."""
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    row = {"thesis_id": t.thesis_id(), **asdict(t)}
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    return row["thesis_id"]


def load_all() -> list[Thesis]:
    p = path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        d.pop("thesis_id", None)
        try:
            out.append(Thesis(**d))
        except ThesisRefusal:
            continue                  # a row that no longer validates is not silently repaired
    return out


def open_theses(now: datetime | None = None) -> list[Thesis]:
    """Theses whose catalyst has not passed -- the ones a pass may still act on."""
    now = now or datetime.now(timezone.utc)
    return [t for t in load_all() if _parse_ts(t.catalyst_at_utc, "catalyst_at_utc") > now]


def forecasts_for(symbols, *, implied_moves: dict[str, float] | None = None,
                  now: datetime | None = None) -> list[Forecast]:
    """Forecasts from every open thesis on `symbols`. Skips what it cannot build.

    A width thesis with no chain width available is DROPPED with its reason, not
    substituted -- see `to_forecast`.
    """
    wanted = {s.upper() for s in symbols}
    implied_moves = implied_moves or {}
    out = []
    for t in open_theses(now):
        if t.symbol.upper() not in wanted:
            continue
        try:
            out.append(t.to_forecast(implied_move=implied_moves.get(t.symbol.upper())))
        except ThesisRefusal:
            continue
    return out
