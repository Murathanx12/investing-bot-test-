"""A SMALL, EXPLICIT exposure graph. Not a geopolitical reasoning engine.

The LLM's job on a world event is `event -> exposure vector + sign + uncertainty
+ horizon`. It does that against THIS table, which names the liquid Alpaca
tradables each theme touches and the sign of first-order exposure. Every edge
used in a decision is written to the ledger BEFORE the outcome, and the
counterfactual marks it afterwards -- Falcon (lablab, May 2026) was marked down
for exactly the post-hoc version of this, so the pre-registration is the point.

Signs are first-order priors, not forecasts: +1 = benefits from escalation of
the theme, -1 = hurt by it. `uncertainty` is how confident we are in the SIGN.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Edge:
    theme: str
    symbol: str
    sign: int
    uncertainty: float   # 0 = sign is well established, 1 = coin flip
    why: str


EDGES: list[Edge] = [
    # China tariffs / export controls
    Edge("china_export_controls", "NVDA", -1, 0.3, "China data-centre revenue at risk"),
    Edge("china_export_controls", "AMD", -1, 0.3, "same channel"),
    Edge("china_export_controls", "AVGO", -1, 0.4, "custom-silicon customers, mixed"),
    Edge("china_export_controls", "SMH", -1, 0.3, "sector ETF"),
    Edge("china_export_controls", "MU", -1, 0.4, "memory demand"),
    # Taiwan / Korea semiconductor supply
    Edge("taiwan_supply_shock", "NVDA", -1, 0.2, "TSMC sole-source"),
    Edge("taiwan_supply_shock", "AMD", -1, 0.2, "TSMC sole-source"),
    Edge("taiwan_supply_shock", "SMH", -1, 0.2, "sector ETF"),
    Edge("taiwan_supply_shock", "MU", +1, 0.6, "non-Taiwan memory supplier, weak"),
    # Middle East escalation
    Edge("middle_east_escalation", "XLE", +1, 0.3, "oil"),
    Edge("middle_east_escalation", "USO", +1, 0.2, "oil"),
    Edge("middle_east_escalation", "LMT", +1, 0.4, "defence"),
    Edge("middle_east_escalation", "UAL", -1, 0.4, "fuel + demand"),
    Edge("middle_east_escalation", "SPY", -1, 0.5, "risk-off, weak"),
    # Auto tariffs (live example: 50% Canada auto tariff, 24 Aug 2026)
    Edge("auto_tariffs", "F", -1, 0.2, "Canadian assembly"),
    Edge("auto_tariffs", "GM", -1, 0.2, "Canadian assembly"),
    Edge("auto_tariffs", "STLA", -1, 0.2, "Canadian assembly"),
    # GRADED 2026-08-24 (50% Canada auto tariff): F -3.4%, GM -1.1%, STLA -3.6%
    # vs SPY -0.3% -- the three 0.2-uncertainty edges were right. TSLA was
    # written +1 at 0.6 uncertainty and printed -3.9%. An edge whose sign we
    # were that unsure of should never have carried one: sign 0, kept as the
    # record of a wrong prior rather than deleted.
    Edge("auto_tariffs", "TSLA", 0, 0.6, "US-built; was +1, graded WRONG on 2026-08-24"),
    # EV policy
    Edge("ev_policy", "TSLA", +1, 0.4, "credits / mandates"),
    Edge("ev_policy", "NIO", +1, 0.5, "US-listed China EV, indirect"),
    Edge("ev_policy", "LI", +1, 0.5, "same"),
    Edge("ev_policy", "XPEV", +1, 0.5, "same"),
    # Gaming / product leaks (live example: GTA VI footage leak -> TTWO)
    Edge("gaming_product_leak", "TTWO", 0, 0.5, "attention up; sign depends on content"),
    Edge("gaming_product_leak", "EA", 0, 0.7, "read-through, weak"),
    # AI capex narrative
    Edge("ai_capex_doubt", "NVDA", -1, 0.3, "demand narrative"),
    Edge("ai_capex_doubt", "AVGO", -1, 0.3, "same"),
    Edge("ai_capex_doubt", "MSFT", -1, 0.5, "spender; mixed"),
    Edge("ai_capex_doubt", "META", -1, 0.5, "spender; mixed"),
    Edge("ai_capex_doubt", "CIEN", -1, 0.4, "optical interconnect demand"),
    # Rates / jobs
    Edge("hot_jobs_print", "QQQ", -1, 0.5, "rates up, duration down"),
    Edge("hot_jobs_print", "IWM", -1, 0.5, "small-cap financing"),
    Edge("hot_jobs_print", "SPY", -1, 0.6, "weak"),
]

THEMES = sorted({e.theme for e in EDGES})


def exposures(theme: str) -> list[Edge]:
    return [e for e in EDGES if e.theme == theme]


def themes_for(symbol: str) -> list[Edge]:
    return [e for e in EDGES if e.symbol == symbol]
