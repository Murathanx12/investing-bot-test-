"""VOL_GAP -- the first brain, and the one that needs no LLM to be right.

THE MECHANISM
=============
The option chain quotes an expected move. History quotes a realised one. When
they disagree by enough to clear the spread, that is a trade -- and unlike a
directional call it does not require knowing which way anything is going.

    forecast sd  =  EWMA realised volatility, scaled to the horizon
    forecast centre = short-horizon momentum, damped hard
    market sd    =  the ATM straddle's implied move

The sizer does the comparison. If realised has been running well above implied,
the straddle wins the enumeration on its own; if well below, the condor does.
Nothing here says "buy a straddle" -- it says how wide the distribution is, and
the structure follows.

WHY THE CENTRE IS DAMPED SO HARD
================================
`mom_12_1` was measured over 32 years as a TAIL signal, and a tail signal's
information lives in the extreme decile of a CROSS SECTION -- not in the level
of one name's trailing return. Reading a single stock's five-day drift as a
point forecast is a different and much weaker claim than the one the research
supports, so `MOMENTUM_DAMPING` deliberately shrinks it to a tilt.

The honest version of the momentum edge needs a ranked universe, which is the
`TAIL_MOMENTUM` brain and not this one. What this brain contributes is the
uncertainty, which is the part the option market prices directly.

WHY EWMA AND NOT A SIMPLE STANDARD DEVIATION
============================================
Volatility clusters. A twenty-day equal-weighted sigma gives a shock from
nineteen days ago the same weight as yesterday, so it stays high long after the
market has calmed down and low into the start of a storm. Both errors are
one-directional and both are expensive: the first sells straddles that are
correctly priced, the second buys condors into a break.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from alpha.brains.base import Forecast

#: EWMA half-life in trading days. Ten days is short enough to notice a regime
#: change inside a one-week competition and long enough not to be one bad day.
HALF_LIFE_DAYS = 10.0

#: How much of trailing drift survives into the centre of the forecast. Momentum
#: is a cross-sectional TAIL signal; one name's drift is a tilt, not a target.
MOMENTUM_DAMPING = 0.15

#: Minimum daily bars before this brain will speak at all.
MIN_BARS = 30


class InsufficientHistory(RuntimeError):
    """Not enough bars to estimate anything. A refusal, not a fallback."""


def forecast(client, symbol: str, horizon_days: float, *, lookback: int = 90) -> Forecast:
    """A return distribution for `symbol` over `horizon_days`."""
    bars = _daily_bars(client, symbol, lookback)
    if len(bars) < MIN_BARS:
        raise InsufficientHistory(
            f"{symbol}: {len(bars)} daily bars, need {MIN_BARS}. Refusing rather than "
            "estimating a volatility from a handful of days -- an under-estimated sigma "
            "makes every long-premium structure look cheap."
        )

    closes = [b["c"] for b in bars]
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]
    if len(rets) < MIN_BARS - 1:
        raise InsufficientHistory(f"{symbol}: only {len(rets)} usable returns.")

    daily_sd = _ewma_sd(rets, HALF_LIFE_DAYS)
    horizon_sd = daily_sd * math.sqrt(max(horizon_days, 0.25))

    # Trailing five-day drift, damped, and scaled to the horizon rather than
    # asserted as a total: a 5-day drift is not a 1-day forecast.
    drift_window = rets[-5:]
    drift_per_day = sum(drift_window) / len(drift_window)
    centre = drift_per_day * horizon_days * MOMENTUM_DAMPING

    # Conviction falls when the recent tape is unlike the sample the sigma came
    # from -- a ratio far from 1 means the EWMA is chasing rather than describing.
    recent_sd = _ewma_sd(rets[-10:], 5.0) if len(rets) >= 10 else daily_sd
    ratio = recent_sd / daily_sd if daily_sd > 0 else 1.0
    conviction = max(0.3, min(1.0, 1.0 - abs(math.log(ratio)) ))

    return Forecast(
        brain="vol_gap",
        symbol=symbol,
        horizon_days=horizon_days,
        centre=centre,
        sd=horizon_sd,
        conviction=conviction,
        rationale=(
            f"EWMA realised vol {daily_sd * math.sqrt(252):.1%} annualised "
            f"({daily_sd:.2%}/day, half-life {HALF_LIFE_DAYS:.0f}d) implies a "
            f"{horizon_sd:.2%} move over {horizon_days:.1f} days. Trailing 5-day drift "
            f"{drift_per_day * 5:+.2%}, damped to a {centre:+.2%} tilt because momentum "
            f"is a cross-sectional tail signal, not a single-name point forecast."
        ),
        signal_shape="tail",
        evidence={
            "daily_sd": daily_sd,
            "annualised_sd": daily_sd * math.sqrt(252),
            "horizon_sd": horizon_sd,
            "drift_5d": drift_per_day * 5,
            "recent_over_baseline_sd": ratio,
            "n_returns": len(rets),
            "last_close": closes[-1],
            "first_bar": bars[0].get("t"),
            "last_bar": bars[-1].get("t"),
        },
    )


def _ewma_sd(rets: list[float], half_life: float) -> float:
    """Exponentially weighted standard deviation, most recent return heaviest."""
    if not rets:
        return 0.0
    lam = 0.5 ** (1.0 / half_life)
    weights = [lam ** i for i in range(len(rets) - 1, -1, -1)]
    total = sum(weights)
    mean = sum(w * r for w, r in zip(weights, rets)) / total
    var = sum(w * (r - mean) ** 2 for w, r in zip(weights, rets)) / total
    return math.sqrt(max(var, 1e-12))


def _daily_bars(client, symbol: str, lookback: int) -> list[dict]:
    """Adjusted daily bars. Split-adjusted, because the alternative is a corpse.

    The parent project marked share counts at RAW prices for months, so every
    split was booked as a return -- one reverse split was +36% of a single day's
    "excess" and the top session of twelve years for two signals. Fixing it moved
    a signal from t=0.26 to t=2.55. `adjustment=all` is not a detail.
    """
    start = (datetime.now(timezone.utc) - timedelta(days=int(lookback * 1.6))).strftime("%Y-%m-%d")
    data = client.stock_bars(symbol, start=start, timeframe="1Day", adjustment="all")
    return (data.get("bars") or {}).get(symbol) or []
