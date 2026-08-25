"""Smoke checks for OPTION_SURFACE_GEOMETRY, the event-variance strip, the Kalshi
ladder and the walk-forward assignment. No keys, no network.
Run: python tests_smoke_surface.py (also executed by tests_smoke.py)."""
from __future__ import annotations

import math
from datetime import date, datetime, timezone

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


# ------------------------------------------------------------ variance strip
print("\n-- variance strip recovers a planted event jump")
from alpha import surface
from alpha.data.chain import ChainSnapshot, Contract, _bs_price

S, R = 100.0, 0.045
ASOF = date(2026, 8, 25)
AMBIENT_VAR = 0.25 ** 2          # 25% annual ambient
JUMP_SD = 0.06                   # a 6% event


def _contract(expiry: str, right: str, k: float, iv: float) -> Contract:
    t = (date.fromisoformat(expiry) - ASOF).days / 365.0
    px = _bs_price(S, k, t, iv, right, R)
    return Contract(symbol=f"X{expiry}{right}{k}", underlying="X", right=right, strike=k, expiry=expiry,
                    bid=px * 0.995, ask=px * 1.005, bid_size=50, ask_size=50,
                    quote_ts=datetime.now(timezone.utc), quote_age_seconds=0.0, implied_vol=iv,
                    delta=None, gamma=None, theta=None, vega=None, open_interest=None, greeks_source="none")


def _planted(expiry: str) -> list[Contract]:
    t = (date.fromisoformat(expiry) - ASOF).days / 365.0
    iv = math.sqrt((AMBIENT_VAR * t + JUMP_SD ** 2) / t)      # flat surface at the total vol
    return [_contract(expiry, r, k, iv) for k in range(80, 121) for r in "CP"]


snap = ChainSnapshot(underlying="X", spot=S, spot_ts=datetime.now(timezone.utc), spot_source="test", feed="test",
                     fetched_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
                     contracts=_planted("2026-08-28") + _planted("2026-09-04"),
                     median_quote_age_seconds=0.0, n_raw=0)
strip = surface.variance_strip(snap, "2026-08-28", "2026-09-04", asof=ASOF)
check("strip runs", strip is not None)
if strip:
    check("market jump sd recovered within 5%", abs(strip["market_jump_sd"] - JUMP_SD) / JUMP_SD < 0.05,
          f"{strip['market_jump_sd']:.4f} vs {JUMP_SD}")
    check("ambient variance recovered within 10%", abs(strip["ambient_annual_var"] - AMBIENT_VAR) / AMBIENT_VAR < 0.10,
          f"{strip['ambient_annual_var']:.4f} vs {AMBIENT_VAR:.4f}")
    check("flat planted surface reads flat", strip["front_geometry"].get("shape") == "flat",
          str(strip["front_geometry"].get("curvature")))
check("back before front refuses", surface.variance_strip(snap, "2026-09-04", "2026-08-28", asof=ASOF) is None)

# a concave surface: wings priced BELOW the body
def _concave(expiry: str) -> list[Contract]:
    out = []
    for k in range(80, 121):
        iv = 0.60 - 0.010 * abs(k - S)
        out += [_contract(expiry, r, float(k), max(iv, 0.2)) for r in "CP"]
    return out


snap2 = ChainSnapshot(underlying="X", spot=S, spot_ts=datetime.now(timezone.utc), spot_source="test", feed="test",
                      fetched_at=datetime(2026, 8, 25, tzinfo=timezone.utc), contracts=_concave("2026-08-28"),
                      median_quote_age_seconds=0.0, n_raw=0)
g = surface.geometry(snap2, "2026-08-28", asof=ASOF)
check("concave surface detected", g is not None and g.get("shape") == "concave", str(g and g.get("curvature")))
check("symmetric concave surface has ~zero skew", g is not None and abs(g.get("skew", 1.0)) < 0.02, str(g and g.get("skew")))

# ------------------------------------------------------------ Kalshi ladder
print("\n-- Kalshi ladder -> buckets")
from scripts.event_contract_basis import ladder_to_buckets

ladder = [{"ticker": "KXPAYROLLS-26AUG-T-25000", "last": 0.85}, {"ticker": "KXPAYROLLS-26AUG-T0", "last": 0.74},
          {"ticker": "KXPAYROLLS-26AUG-T100000", "last": 0.24}, {"ticker": "KXPAYROLLS-26AUG-T50000", "last": 0.60},
          {"ticker": "KXPAYROLLS-26AUG-T125000", "last": 0.30}]   # 125k deliberately NON-monotone (0.30 > 0.24)
b = ladder_to_buckets(ladder)
check("bucket probabilities sum to 1", abs(sum(x["p"] for x in b) - 1.0) < 1e-6, str(sum(x["p"] for x in b)))
check("no negative bucket (monotone enforced)", all(x["p"] >= 0 for x in b))
check("buckets ordered by threshold", [x["hi"] for x in b][:-1] == sorted([x["hi"] for x in b][:-1]))
check("midpoints in thousands", any(x["mid"] == 25.0 for x in b), str([x["mid"] for x in b]))

# ------------------------------------------------------------ walk-forward assignment
print("\n-- walk-forward buckets use only earlier rows")
from scripts.event_surface_backtest import assign_walkforward

def row(sym, day, move, implied, jump):
    return {"symbol": sym, "entry_day": day, "signed_move": move, "realised_abs_move": abs(move),
            "implied_move": implied, "strip": {"market_jump_sd": jump}, "structures": {}}

rows = []
for i in range(30):
    d = f"2025-{1 + i // 4:02d}-{1 + (i % 4) * 7:02d}"
    rows.append(row("A", d, (-1) ** i * 0.05 * (1 + i % 3), 0.06, 0.07))
    rows.append(row("B", d, 0.02, 0.05, 0.06))
a = assign_walkforward([dict(r) for r in rows])
first_with_bucket = next(r for r in a if r.get("bucket_naive"))
check("no bucket before the pool is seeded", all(not r.get("bucket_naive") for r in a[:9]))
check("prior counted per name", all(r["prior_n"] <= 8 for r in a))
# perturb the FUTURE and the past assignments must not change
rows2 = [dict(r) for r in rows]
for r in rows2[-10:]:
    r["signed_move"] = 0.40
    r["realised_abs_move"] = 0.40
b2 = assign_walkforward(rows2)
same = all(x.get("bucket_naive") == y.get("bucket_naive") and x.get("gap_naive") == y.get("gap_naive")
           for x, y in zip(a[:-10], b2[:-10]))
check("perturbing later rows leaves earlier buckets unchanged", same)

print("\nALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
