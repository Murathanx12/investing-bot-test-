"""The NARRATIVE_SHOCK_v1 record. Every axis is separate on purpose.

TRUTH AND IMPACT ARE NOT THE SAME VARIABLE
==========================================
A GTA VI leak can be false and still move TTWO. A politician's statement can be
economically empty and still move an exposed sector. A rumour can create
momentum and, when disproved, a reversal. Collapsing these into one "sentiment"
number throws away the part that is tradeable. So:

    truth_probability          P(the claim is factually correct)
    source_credibility         how reliable the ORIGINATING source is
    market_belief              how much the public appears to BELIEVE it
    market_impact_probability  P(price responds materially) -- independent of truth
    already_priced_fraction    how much of the expected move has ALREADY happened

and the BELIEF GAP falls out of the four:

    low truth  + high belief + little reaction   -> short-lived momentum / convexity
    low truth  + high belief + big completed move -> reversal candidate
    high truth + low attention                    -> under-reaction candidate
    high truth + high attention + repriced chain  -> REFUSE (we agree with the chain)

"NEUROSCIENCE", MADE MEASURABLE
===============================
The behavioural constructs are named as variables rather than as marketing:
novelty (prediction error), salience, arousal, repetition, habituation, social
proof, disagreement, surprise. They are LLM-estimated on [0, 1] and recorded
with the model and prompt hash that produced them, so a post-mortem can say
"the model said 0.9 novelty on a story it had seen twice" instead of "the AI
was wrong".
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = "NARRATIVE_SHOCK_v1"

#: The axes the extractor must return, with their allowed ranges. Kept as data
#: so the prompt and the validator are generated from ONE definition.
AXES: dict[str, tuple[float, float, str]] = {
    "truth_probability": (0, 1, "P(the core factual claim is true)"),
    "source_credibility": (0, 1, "reliability of the originating source, 0=anon rumour 1=primary filing"),
    "novelty": (0, 1, "prediction error: how new is this relative to what was already known"),
    "salience": (0, 1, "how attention-grabbing the framing is, independent of substance"),
    "arousal": (0, 1, "emotional intensity of the coverage"),
    "repetition": (0, 1, "how many times this story has already circulated"),
    "habituation": (0, 1, "how stale/expected this kind of story is for this name"),
    "social_proof": (0, 1, "how many INDEPENDENT sources or users repeat it"),
    "disagreement": (0, 1, "how much competing narratives exist about what it means"),
    "surprise": (0, 1, "deviation from prior expectations"),
    "sentiment": (-1, 1, "net tone toward the affected entity, -1 bearish +1 bullish"),
    "sentiment_dispersion": (0, 1, "how divided the tone is across sources"),
    "cross_platform_disagreement": (0, 1, "do news and social read it differently"),
    "market_belief": (0, 1, "how much the public appears to believe the claim"),
    "market_impact_probability": (0, 1, "P(a material price response), INDEPENDENT of truth"),
    "expected_direction": (-1, 1, "sign of the expected move if it responds, 0 = two-sided"),
    "expected_move": (0, 0.5, "expected absolute underlying move as a fraction, if it responds"),
    "expected_half_life_days": (0, 60, "days until the effect halves"),
    "already_priced_fraction": (0, 1, "share of the expected move that has ALREADY happened"),
}


@dataclass(frozen=True)
class NarrativeShock:
    schema: str
    event_id: str
    symbol: str
    headline: str
    summary: str
    observed_at_utc: str
    sources: list[dict[str, Any]]
    axes: dict[str, float]
    affected_entities: list[str]
    affected_sectors: list[str]
    event_type: str
    """rumour | leak | product | policy | geopolitical | macro | earnings | legal | other"""
    llm: dict[str, Any]
    """model, prompt_hash, tokens, cost_usd, latency_s -- so spend is attributed."""
    notes: str = ""
    theme: str = "none"
    """An `alpha.narrative.exposure` theme, or "none". The LLM classifies; the
    graph (written before the outcome) says which OTHER names are exposed."""

    @property
    def exposure_siblings(self) -> list[dict[str, Any]]:
        from alpha.narrative import exposure

        if self.theme == "none":
            return []
        return [{"symbol": e.symbol, "sign": e.sign, "uncertainty": e.uncertainty, "why": e.why}
                for e in exposure.exposures(self.theme) if e.symbol != self.symbol]

    @property
    def belief_gap(self) -> dict[str, Any]:
        a = self.axes
        truth, belief = a["truth_probability"], a["market_belief"]
        priced = a["already_priced_fraction"]
        if truth < 0.4 and belief > 0.6 and priced < 0.4:
            case = "false_but_believed_unpriced"
            reading = "momentum/convexity: belief is spreading faster than price"
        elif truth < 0.4 and belief > 0.6 and priced >= 0.7:
            case = "false_believed_fully_priced"
            reading = "reversal candidate when disproved; two-sided risk"
        elif truth > 0.7 and a["social_proof"] < 0.3 and priced < 0.4:
            case = "true_but_unnoticed"
            reading = "under-reaction candidate"
        elif truth > 0.7 and belief > 0.6 and priced >= 0.7:
            case = "true_believed_priced"
            reading = "REFUSE: we agree with the chain and would pay to say so"
        else:
            case = "indeterminate"
            reading = "no clean gap; contributes uncertainty only"
        return {"case": case, "reading": reading, "truth": truth, "belief": belief,
                "priced": priced}

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["belief_gap"] = self.belief_gap
        d["exposure_siblings"] = self.exposure_siblings
        return d


def validate_axes(raw: dict[str, Any]) -> dict[str, float]:
    """Clamp-and-refuse: missing axis -> refusal; out-of-range -> clamped and noted."""
    out: dict[str, float] = {}
    missing = [k for k in AXES if k not in raw]
    if missing:
        raise ValueError(f"extractor omitted axes: {missing}")
    for k, (lo, hi, _) in AXES.items():
        try:
            v = float(raw[k])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"axis {k} is not numeric: {raw[k]!r}") from exc
        out[k] = max(lo, min(hi, v))
    return out


def event_id(symbol: str, headline: str, observed_at: str) -> str:
    return hashlib.sha256(f"{symbol}|{headline.strip().lower()}|{observed_at[:10]}".encode()).hexdigest()[:16]


def prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def as_json(shock: NarrativeShock) -> str:
    return json.dumps(shock.to_dict(), indent=1, default=str)
