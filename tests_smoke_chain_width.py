"""Smoke checks for THE WIDTH OF THE CHAIN -- the three unit errors that made
every option look cheap until 27 Aug. No keys, no network.
Run: python tests_smoke_chain_width.py (also executed by tests_smoke.py).

Receipt: docs/FINDING_2026-08-27_THE_CHAIN_WAS_NEVER_CHEAP.md
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from statistics import NormalDist

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


# --------------------------------------------------------------- the identity
print("\n-- an ATM straddle IS the expected absolute move (no multiplier)")
from alpha.data.chain import ChainSnapshot, Contract

N = NormalDist().cdf


def _straddle(S, T, sig):
    d1 = 0.5 * sig * math.sqrt(T)
    d2 = -d1
    return (S * N(d1) - S * N(d2)) + (S * N(-d2) - S * N(-d1))


def _snap(S, straddle_px, expiry):
    half = straddle_px / 2.0
    mk = lambda right: Contract(                                   # noqa: E731
        symbol=f"X{expiry.replace('-','')[2:]}{right}00100000", underlying="X", expiry=expiry,
        right=right, strike=S, bid=half - 0.01, ask=half + 0.01, bid_size=50, ask_size=50,
        quote_ts=datetime.now(timezone.utc), staleness_penalty=0.0,
        quote_age_seconds=0.0, implied_vol=None, delta=None, gamma=None, theta=None,
        vega=None, open_interest=0, greeks_source="test")
    return ChainSnapshot(underlying="X", spot=S, spot_ts=datetime.now(timezone.utc),
                         spot_source="test", feed="test", fetched_at=datetime.now(timezone.utc),
                         contracts=[mk("C"), mk("P")], median_quote_age_seconds=0.0, n_raw=2)


worst = 0.0
for sig in (0.10, 0.20, 0.40, 0.80):
    for Td in (1, 2, 3, 7, 30):
        T = Td / 252.0
        S = 100.0
        px = _straddle(S, T, sig)
        truth = sig * math.sqrt(T) * math.sqrt(2 / math.pi)        # E|move| / S
        got = _snap(S, px, "2026-12-18").implied_move("2026-12-18")
        worst = max(worst, abs(got / truth - 1.0))
check("implied_move recovers E|move| to <1% across sigma 10-80%, 1-30d", worst < 0.01,
      f"worst error {worst:.3%}")
# The specific regression: a 0.85 haircut would show up as a 15% understatement.
px = _straddle(100.0, 3 / 252.0, 0.20)
got = _snap(100.0, px, "2026-12-18").implied_move("2026-12-18")
check("no 0.85 haircut survives", got > 0.9 * (0.20 * math.sqrt(3 / 252) * math.sqrt(2 / math.pi)),
      f"implied_move={got:.5f}")

# ------------------------------------------------------- sessions, not days
print("\n-- days_to_expiry counts TRADING SESSIONS, and skips weekends and holidays")
from alpha.engine.structures import _days


class _Chain:
    def __init__(self, t):
        self.fetched_at = t


fri_pre_open = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
check("Fri->Mon is ~2 sessions, not 3 calendar days",
      1.8 <= _days(_Chain(fri_pre_open), "2026-08-31") <= 2.05,
      f"{_days(_Chain(fri_pre_open), '2026-08-31'):.2f}")
labor = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
check("Labor Day is not a session",
      _days(_Chain(labor), "2026-09-08") < _days(_Chain(labor), "2026-09-09"),
      f"{_days(_Chain(labor), '2026-09-08'):.2f} < {_days(_Chain(labor), '2026-09-09'):.2f}")
check("an expiring structure still divides", _days(_Chain(labor), "2026-08-01") > 0.0)
mid = datetime(2026, 8, 26, 18, 0, tzinfo=timezone.utc)      # ~2h into a 6.5h session
check("a part-session counts as a fraction",
      2.0 < _days(_Chain(mid), "2026-08-28") < 2.7, f"{_days(_Chain(mid), '2026-08-28'):.2f}")

# ------------------------------------------------------- symmetric rescaling
print("\n-- the payoff sd is rescaled to the structure's life in BOTH directions")
from alpha.engine.payoff import economics
from alpha.engine.sizing import Structure


def _straddle_structure(dte):
    return Structure(symbol="X", kind="long_straddle", entry_cost=775.0, max_loss=775.0,
                     breakeven_move=0.0101, implied_move=0.0101, quote_spread_pct=0.02,
                     days_to_expiry=dte,
                     legs=(("SPY260828C00765000", "buy", 1), ("SPY260828P00765000", "buy", 1)))


sd3 = 0.0157
long_life = economics(_straddle_structure(6.0), 765.0, 0.0, sd3, horizon_days=3.0)
short_life = economics(_straddle_structure(1.0), 765.0, 0.0, sd3, horizon_days=3.0)
no_scale = economics(_straddle_structure(1.0), 765.0, 0.0, sd3, horizon_days=None)
check("a 6-session structure is underwritten WIDER than a 3-session forecast",
      long_life.ev_usd > no_scale.ev_usd)
check("a 1-session structure is underwritten NARROWER (this was the bug)",
      short_life.ev_usd < no_scale.ev_usd,
      f"1-session EV {short_life.ev_usd:,.0f} vs unscaled {no_scale.ev_usd:,.0f}")
check("shrinking a 3-session forecast onto 1 session turns this straddle -EV",
      short_life.ev_usd < 0 < no_scale.ev_usd,
      f"{short_life.ev_usd:,.0f} vs {no_scale.ev_usd:,.0f}")
check("horizon_days=None still disables rescaling entirely",
      abs(no_scale.ev_usd - economics(_straddle_structure(99.0), 765.0, 0.0, sd3,
                                      horizon_days=None).ev_usd) < 1e-6)

print("\nALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
