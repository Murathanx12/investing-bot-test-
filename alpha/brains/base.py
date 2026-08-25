"""What a brain must produce, and why it must include its own uncertainty.

A brain does NOT say "bullish". It returns a DISTRIBUTION over the underlying's
return to a horizon: a centre and a spread. That requirement is the difference
between this agent and the commodity project of the week, and it is enforced by
the type rather than by a convention:

  * `sizing.model_probability_beyond` needs a spread to compute anything at all,
    and raises on a non-positive one. A point forecast with no stated
    uncertainty is an assertion of certainty and would size itself to the
    ceiling every time.
  * The structure that gets chosen depends on the SHAPE of the forecast, not on
    its sign. Centre +1.2% with spread 1.0% buys a call spread; centre 0 with
    spread 2.5% buys a straddle; centre 0 with spread 0.3% sells a condor. An
    agent that only emits a direction can only ever buy calls and puts, which is
    why so many of them do.

`conviction` is separate from `sd` on purpose. `sd` is how wide the brain
believes the outcome distribution is; `conviction` is how much the brain trusts
ITSELF right now -- a momentum reading taken in a quiet tape is a different
object from the same reading during a vol shock. Collapsing them would let a
confident brain widen its distribution to look humble while still sizing large.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Forecast:
    brain: str
    symbol: str
    horizon_days: float
    centre: float
    """Expected return over the horizon, as a signed fraction of spot."""
    sd: float
    """Standard deviation of that return. Must be > 0."""
    conviction: float = 1.0
    """[0, 1.5]. The brain's confidence in its own reading right now."""
    rationale: str = ""
    signal_shape: str | None = None
    """Which measured shape licensed this, if any -- see `alpha/engine/shape.py`."""
    evidence: dict[str, Any] = field(default_factory=dict)
    """Every number that produced the forecast, so the ledger row can be argued
    with later. A rationale string alone is a story; the evidence is the receipt."""

    def __post_init__(self) -> None:
        if self.sd <= 0:
            raise ValueError(
                f"{self.brain} returned sd={self.sd} for {self.symbol}. A forecast must "
                "state its own uncertainty -- a zero spread is a claim of certainty and "
                "would size to the ceiling on every trade."
            )
