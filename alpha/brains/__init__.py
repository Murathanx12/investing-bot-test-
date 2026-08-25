"""The brains. Each returns a `Forecast` (centre + sd + conviction) or raises.

    vol_gap               EWMA realised vol vs the chain          price only, no LLM
    event_move            this name's own history of prints       price + Finnhub dates
    options_attention     abnormal option volume, unsigned        option tape
    narrative_dispersion  LLM axes on news -> variance            Alpaca news + DeepSeek + attention

They are INDEPENDENT by data source, not by formula -- the parent project's
lesson is that thirteen signals on one file are one signal. `forecast_all`
runs every brain that applies to a symbol and records the ones that decline.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from alpha.brains import event_move, narrative_dispersion, options_attention, vol_gap
from alpha.brains.base import Forecast

logger = logging.getLogger(__name__)

BRAINS: dict[str, Callable[..., Forecast]] = {
    "vol_gap": lambda client, sym, h, **kw: vol_gap.forecast(client, sym, h),
    "event_move": lambda client, sym, h, **kw: event_move.forecast(client, sym, h),
    "options_attention": lambda client, sym, h, **kw: options_attention.forecast(
        client, sym, h, expiries=kw["expiries"]),
    "narrative_dispersion": lambda client, sym, h, **kw: narrative_dispersion.forecast(client, sym, h),
}


def forecast_all(client, symbols: list[str], horizon_days: float, *, brains: list[str],
                 expiries: list[str]) -> tuple[list[Forecast], list[dict[str, Any]]]:
    """Every (brain, symbol) that speaks, and every one that declined, with why."""
    out, declined = [], []
    for name in brains:
        fn = BRAINS[name]
        for sym in symbols:
            try:
                out.append(fn(client, sym, horizon_days, expiries=expiries))
            except Exception as exc:                                    # noqa: BLE001
                declined.append({"brain": name, "symbol": sym, "why": f"{type(exc).__name__}: {str(exc)[:160]}"})
                logger.info("%s/%s declined: %s", name, sym, str(exc)[:120])
    return out, declined
