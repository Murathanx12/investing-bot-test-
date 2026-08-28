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
a name whose 20-session drawdown is worse than `MAX_DRAWDOWN_20` -- a basket
name down more than that in a month is a falling knife the human's own rule
("if it has dropped a lot recently" is a reason to LOOK, not to buy blind)
does not cover, and the rows are declined with the number so the census of
refusals is itself a finding.
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
MAX_DRAWDOWN_20 = -0.55
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
    if dd20 < MAX_DRAWDOWN_20:
        raise NotInBasket(f"{symbol}: {dd20:+.0%} from its 20-session high is past {MAX_DRAWDOWN_20:+.0%}; declined, not bought blind")
    sd_h = sd_daily * math.sqrt(max(horizon_days, 1.0))
    centre = TILT_SIGMA * sd_h
    return Forecast(
        brain=NAME, symbol=symbol, horizon_days=horizon_days, centre=centre, sd=sd_h,
        conviction=CONVICTION, claim="direction", signal_shape=None,
        rationale=f"human prior: +{TILT_SIGMA:g} sigma tilt on {','.join(themes)}; rv60 {sd_daily * math.sqrt(252):.0%}, dd20 {dd20:+.0%}",
        evidence={"themes": themes, "tilt_sigma": TILT_SIGMA, "sd_daily": sd_daily, "dd20": dd20,
                  "ret_20": closes[-1] / closes[-21] - 1.0, "stated_by": seed.get("author"),
                  "measured_edge": None, "seed": seed.get("name")},
    )
