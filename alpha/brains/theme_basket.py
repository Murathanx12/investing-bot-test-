"""THEME_BASKET -- a HUMAN PRIOR made executable, and labelled as one.

THE CLAIM
=========
Murat's future-state view (docs/seed/universe/THEMES_2026-08-28.json): robotics
sensors/actuators, quantum, nuclear, storage, grid/alt energy, raw materials.
The brain does not pretend to have measured an edge -- there is none on record
for a five-session horizon -- it states a DIRECTIONAL TILT of `TILT_SIGMA`
standard deviations over the horizon, with the sd taken from the name's own
realised volatility. That is what "I would start investing in them early even
though it's a risk" means in numbers: a +0.5 sigma prior on every basket name.

    centre = +TILT_SIGMA * sd_horizon          claim = "direction"
    sd     = realised vol (60 sessions, EWMA-free, plain) scaled to the horizon

The runner integrates a `direction` claim against the CHAIN's width, so the
structure that wins is decided by what the market charges, not by this file.
On a 100%-vol name that is a large tilt in dollars, which is why the mandate
that runs it (`alpha/fleet.py` role `thesis`) is one equity curve on its own.

WHAT REFUSES
============
A symbol not in the seed (the brain has no view on it), fewer than 30 bars, and
-- after the 28 Aug CRSP adjudication (see `forecast`) -- any name in the
MIDDLE of the drawdown range (-50%..-10% over 20 sessions), where the
construction measured -0.31%/5 sessions with t -2.35. Only the extreme
rebound cell (down >50% at >100% vol) and names near their highs are bought.
The rows are declined with the number so the census of refusals is a finding.
"""

from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpha import config
from alpha.brains.base import Forecast

NAME = "theme_basket"
SEED = Path(__file__).resolve().parent.parent.parent / "docs" / "seed" / "universe" / "THEMES_2026-08-28.json"
SEED_IN_IMAGE = Path("/app/seed/universe/THEMES_2026-08-28.json")
TILT_SIGMA = 0.5
REBOUND_DD = -0.50
REBOUND_RV = 1.00
NEAR_HIGH_DD = -0.10
CONVICTION = 0.8


class NotInBasket(RuntimeError):
    pass


def _seed() -> dict:
    for p in (SEED, SEED_IN_IMAGE):
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise NotInBasket("theme seed missing: run `python -m scripts.theme_screen`")


def themes_of(symbol: str, seed: dict | None = None) -> list[str]:
    d = seed or _seed()
    return [t for t, v in d["themes"].items() if symbol in v["symbols"]]


def _bars(client, symbol: str, days: int = 130) -> list[dict]:
    start = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    d = client._request("GET", f"/v2/stocks/{symbol}/bars", base=config.data_url(),
                        params={"timeframe": "1Day", "start": start, "limit": 200, "feed": config.stock_feed(),
                                "adjustment": "all"})
    return (d or {}).get("bars") or []


def forecast(client, symbol: str, horizon_days: float, *, bars: list[dict] | None = None) -> Forecast:
    seed = _seed()
    themes = themes_of(symbol, seed)
    if not themes:
        raise NotInBasket(f"{symbol} is not in the theme seed; this brain has no view on it")
    bars = bars if bars is not None else _bars(client, symbol)
    closes = [float(b["c"]) for b in bars]
    if len(closes) < 30:
        raise NotInBasket(f"{symbol}: {len(closes)} bars < 30")
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    sd_daily = statistics.pstdev(rets[-60:])
    if sd_daily <= 0:
        raise NotInBasket(f"{symbol}: zero realised vol")
    dd20 = closes[-1] / max(closes[-21:]) - 1.0
    rv = sd_daily * math.sqrt(252)
    # ADJUDICATED 2026-08-28 (Aegis scripts/knife_basket_backtest.py, CRSP
    # 2013-2024, 5-session hold, non-overlapping windows, vs the EW market):
    #   rv 60-180%, dd20 -50..-20%  : -0.31%/window excess, t -2.35, 0.2x vs 3.2x   <- the basket as first drawn
    #   rv 100-180%, dd20 < -50%    : +2.32%/window excess, t 2.60, hit 58%, 8.7x    <- the ONLY paying cell (n=88)
    #   rv 60-180%, dd20 > -10%     : -0.13%, t -0.7, flat
    # The human's rule "if it dropped a lot recently, look" is right only at the
    # extreme; the middle of the drawdown range is where the money was lost.
    # So: the rebound cell is bought at full tilt, names near their highs at a
    # quarter tilt, and the -50..-10% middle is DECLINED with the number.
    # SECOND PASS (scripts/knife_rebound_split.py, same session): the rebound
    # cell's +2.32% was an ARTEFACT of requiring >=5 names per window, which
    # selects crisis months. At >=3 names it is +0.19% mean / -0.63% MEDIAN /
    # hit 46% / t 0.40 / 0.75x vs 2.1x over 360 windows, and no year, hold
    # (1/3/5/10), edge (-40/-50/-60%, rv 80/100/150%) or size tercile has a
    # positive median. NO drawdown cell of this construction pays at five
    # sessions. Only names near their highs are bought, at half tilt, and the
    # row says the cell is flat.
    if dd20 > NEAR_HIGH_DD:
        tilt, cell = TILT_SIGMA * 0.5, "near-high(dd>-10%): -0.13%/5d, t -0.7 (flat)"
    else:
        raise NotInBasket(f"{symbol}: dd20 {dd20:+.0%} at rv {rv:.0%} -- every drawdown cell of this construction "
                          "measured a NEGATIVE median over 5 sessions (2013-2024; -20..-50%: -0.31%, t -2.35; "
                          "<-50%: median -0.63%, t 0.40). Declined with the number, not bought on the story.")
    sd_h = sd_daily * math.sqrt(max(horizon_days, 1.0))
    centre = tilt * sd_h
    return Forecast(
        brain=NAME, symbol=symbol, horizon_days=horizon_days, centre=centre, sd=sd_h,
        conviction=CONVICTION, claim="direction", signal_shape=None,
        rationale=f"human prior x adjudicated cell [{cell}]: +{tilt:g} sigma on {','.join(themes)}; rv60 {rv:.0%}, dd20 {dd20:+.0%}",
        evidence={"themes": themes, "tilt_sigma": tilt, "cell": cell, "sd_daily": sd_daily, "dd20": dd20, "rv60": rv,
                  "ret_20": closes[-1] / closes[-21] - 1.0, "stated_by": seed.get("author"),
                  "measured_edge": None, "seed": seed.get("name")},
    )
