"""The brains. Each returns a `Forecast` (centre + sd + conviction) or raises.

    vol_gap               EWMA realised vol vs the chain          price only, no LLM
    event_move            this name's own history of prints       price + Finnhub dates
    options_attention     abnormal option volume, unsigned        option tape
    narrative_dispersion  LLM axes on news -> variance            Alpaca news + DeepSeek + attention
    relay                 a peer's measured move on the originator's prints   price + SEC dates
    post_event_drift      the printer's own day-0 move, continued             price + SEC dates

They are INDEPENDENT by data source, not by formula -- the parent project's
lesson is that thirteen signals on one file are one signal. `forecast_all`
runs every brain that applies to a symbol and records the ones that decline.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from alpha.brains import (council_vector, event_move, narrative_dispersion, options_attention,
                          post_event_drift, relay, theme_basket, vol_gap)
from alpha.brains.base import Forecast

logger = logging.getLogger(__name__)

BRAINS: dict[str, Callable[..., Forecast]] = {
    "vol_gap": lambda client, sym, h, **kw: vol_gap.forecast(client, sym, h),
    "event_move": lambda client, sym, h, **kw: event_move.forecast(client, sym, h),
    "options_attention": lambda client, sym, h, **kw: options_attention.forecast(
        client, sym, h, expiries=kw["expiries"]),
    "narrative_dispersion": lambda client, sym, h, **kw: narrative_dispersion.forecast(client, sym, h),
    "relay": lambda client, sym, h, **kw: relay.forecast(client, sym, h),
    "post_event_drift": lambda client, sym, h, **kw: post_event_drift.forecast(client, sym, h),
    # Fleet brains (2026-08-28, alpha/fleet.py). `theme_basket` is a HUMAN PRIOR
    # labelled as one; `council_vector` reads the research council's synthesis.
    "theme_basket": lambda client, sym, h, **kw: theme_basket.forecast(client, sym, h),
    "council_vector": lambda client, sym, h, **kw: council_vector.forecast(client, sym, h),
}


#: Brains that may NOT trade until re-validated, and the reason.
#:
#: A quarantine is not a deletion: the brain still runs in shadow, still records
#: forecasts, and is still gradeable. What it may not do is spend money on a
#: model whose inputs were wrong when its track record was made.
QUARANTINED: dict[str, str] = {
    "vol_gap": (
        "QUARANTINED 2026-08-27. It opened 5 of the 6 losing structures in the dev book on "
        "25 Aug (NVDA condors -$5,629, AMD straddle -$4,125, TSLA put -$1,131) by comparing "
        "its realised-vol forecast against an implied move computed with the 0.85 haircut, "
        "calendar-days scaling a per-TRADING-day vol, and a payoff rescale that only ever "
        "scaled UP. Those three errors made the chain look CHEAP on 96.4% of 6,070 decisions "
        "(median sigma/implied 1.96). They were fixed on 2026-08-27 -- TWO DAYS AFTER these "
        "positions were opened -- so every number in this brain's track record was produced "
        "by arithmetic that no longer exists. "
        "REOPENS WHEN: its decisions are re-scored against the corrected implied move and it "
        "clears zero after costs on a held-out window. Not before."
    ),
}


def forecast_all(client, symbols: list[str], horizon_days: float, *, brains: list[str],
                 expiries: list[str], allow_quarantined: bool = False
                 ) -> tuple[list[Forecast], list[dict[str, Any]]]:
    """Every (brain, symbol) that speaks, and every one that declined, with why."""
    out, declined = [], []
    for name in brains:
        if name in QUARANTINED and not allow_quarantined:
            # Declined LOUDLY and once per pass, not silently dropped: a brain
            # that vanishes from the output reads exactly like a brain that had
            # nothing to say.
            logger.warning("brain %s is QUARANTINED and will not trade: %s", name, QUARANTINED[name])
            declined.append({"brain": name, "symbol": "*", "why": QUARANTINED[name]})
            continue
        fn = BRAINS[name]
        for sym in symbols:
            try:
                out.append(fn(client, sym, horizon_days, expiries=expiries))
            except Exception as exc:                                    # noqa: BLE001
                declined.append({"brain": name, "symbol": sym, "why": f"{type(exc).__name__}: {str(exc)[:160]}"})
                logger.info("%s/%s declined: %s", name, sym, str(exc)[:120])
    return out, declined
