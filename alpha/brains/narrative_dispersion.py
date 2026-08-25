"""NARRATIVE_DISPERSION_v1 -- social disagreement as a forecast of variance.

THE MAPPING
===========
When attention spikes AND sources disagree AND truth is uncertain, the honest
forecast is not a direction, it is a WIDER distribution. That is the same
statement `rev_dispersion` makes about analysts, measured over 32 years as a
TAIL-shaped signal, and a tail-shaped payoff is a straddle. So:

    narrative shock records (LLM axes, from `alpha.narrative.extract`)
      + attention velocity (Wikipedia pageviews, option volume)
        -> variance multiplier on the ordinary-day sigma
        -> compared, by the sizer, against the chain's implied move

The LLM never touches the trade. It produces axes; this brain turns them into a
spread; `alpha.engine.sizing` decides whether the chain already charges for it.

THE CENTRE
==========
Mostly zero. A tilt is allowed only when the belief-gap case is one of the two
directional ones AND the extractor's expected_direction is non-zero, and it is
damped like momentum in `vol_gap` -- the parent project's finding is that
short-horizon direction from text is the weakest claim on the shelf.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from alpha.brains.base import Forecast
from alpha.brains.vol_gap import _daily_bars, _ewma_sd
from alpha.narrative import extract, schema
from alpha.sources import attention, belief
from alpha.sources.http import SourceRefusal

DIRECTION_DAMPING = 0.25
MAX_WIDEN = 2.0


class NothingToRead(RuntimeError):
    pass


def gather(client, symbol: str, *, hours: int = 36, max_items: int = 12) -> list[dict[str, Any]]:
    start = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    items = attention.alpaca_news(client, [symbol], limit=max_items, start=start)
    return [{"source": it.get("source"), "created_at": it.get("created_at"),
             "headline": it.get("headline"), "summary": it.get("summary"),
             "url": it.get("url"), "symbols": it.get("symbols")} for it in items]


def widen_from_shock(s: schema.NarrativeShock, att_velocity: float | None) -> tuple[float, str]:
    a = s.axes
    disagreement = 0.5 * a["disagreement"] + 0.3 * a["sentiment_dispersion"] + 0.2 * a["cross_platform_disagreement"]
    uncertainty = 1.0 - abs(2 * a["truth_probability"] - 1.0)   # 1 at p=0.5, 0 at p in {0,1}
    impact = a["market_impact_probability"] * (1.0 - a["already_priced_fraction"])
    vel = max(0.0, math.log(att_velocity)) if att_velocity and att_velocity > 0 else 0.0
    core = impact * (0.5 + 0.5 * disagreement) * (0.5 + 0.5 * uncertainty)
    widen = 1.0 + 1.2 * core + 0.15 * vel
    return min(MAX_WIDEN, widen), (
        f"impact {impact:.2f} x disagreement {disagreement:.2f} x truth-uncertainty {uncertainty:.2f}"
        f" + attention log-velocity {vel:.2f} -> sigma x{min(MAX_WIDEN, widen):.2f}"
    )


def forecast(client, symbol: str, horizon_days: float, *, shocks: list[schema.NarrativeShock] | None = None,
             context: str = "") -> Forecast:
    items = gather(client, symbol)
    if not items:
        raise NothingToRead(f"{symbol}: no news items in the window")
    if shocks is None:
        lead = items[0]
        shocks = [extract.extract(symbol, lead["headline"] or "", lead.get("summary") or "",
                                  items, context=context, observed_at=lead.get("created_at"))]
    try:
        att = attention.wiki_attention(symbol)
        velocity = att.get("velocity")
    except SourceRefusal:
        att, velocity = None, None

    bars = _daily_bars(client, symbol, 90)
    closes = [float(b["c"]) for b in bars]
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    daily_sd = _ewma_sd(rets, 10.0)

    # The strongest shock sets the width; the others are recorded.
    widened = [(widen_from_shock(s, velocity), s) for s in shocks]
    (widen, why), lead_shock = max(widened, key=lambda t: t[0][0])
    sd = daily_sd * math.sqrt(max(horizon_days, 0.25)) * widen

    gap = lead_shock.belief_gap
    centre = 0.0
    if gap["case"] in ("false_but_believed_unpriced", "true_but_unnoticed"):
        centre = lead_shock.axes["expected_direction"] * lead_shock.axes["expected_move"] * DIRECTION_DAMPING
    elif gap["case"] == "false_believed_fully_priced":
        centre = -lead_shock.axes["expected_direction"] * lead_shock.axes["expected_move"] * DIRECTION_DAMPING * 0.5

    # The crowd's belief as a PRICE, beside the LLM's estimate. Not merged: when
    # they disagree the disagreement is the finding.
    try:
        markets = belief.polymarket_search(symbol, limit=5)[:5]
    except SourceRefusal:
        markets = []

    a = lead_shock.axes
    conviction = max(0.3, min(1.0, 0.4 + 0.3 * a["source_credibility"] + 0.3 * (1 - a["habituation"])))
    refuse_note = " REFUSE-CASE: chain likely already priced it." if gap["case"] == "true_believed_priced" else ""

    return Forecast(
        brain="narrative_dispersion", symbol=symbol, horizon_days=horizon_days,
        centre=centre, sd=sd, conviction=conviction,
        rationale=(
            f"'{lead_shock.headline[:90]}' -- truth {a['truth_probability']:.2f}, belief {a['market_belief']:.2f}, "
            f"impact {a['market_impact_probability']:.2f}, priced {a['already_priced_fraction']:.2f} "
            f"=> {gap['case']}: {gap['reading']}. {why}.{refuse_note}"
        ),
        signal_shape="tail",
        evidence={
            "shocks": [s.to_dict() for s in shocks], "attention": att, "daily_sd": daily_sd,
            "prediction_markets": markets, "theme": lead_shock.theme,
            "exposure_siblings": lead_shock.exposure_siblings,
            "widen": widen, "belief_gap": gap, "n_items": len(items), "last_close": closes[-1],
            "llm_cost_usd": round(sum(s.llm.get("cost_usd", 0.0) for s in shocks), 6),
        },
    )
