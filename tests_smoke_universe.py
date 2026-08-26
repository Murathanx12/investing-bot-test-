"""Smoke checks for HIGH_DISPERSION_US_v1 and the bias instrumentation. No keys, no network.

Run: python tests_smoke_universe.py  (also executed by tests_smoke.py)
"""
from __future__ import annotations

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import universe
from alpha.brains.base import Forecast

print("\n-- buckets and ETF detection")
check("dv bucket thresholds", universe.dv_bucket(5e6) == "micro" and universe.dv_bucket(60e6) == "mid" and universe.dv_bucket(3e9) == "mega")
check("cap bucket", universe.cap_bucket(1.5e9) == "small" and universe.cap_bucket(50e9) == "large" and universe.cap_bucket(None) is None)
check("ETF-like names flagged", universe.looks_like_etf("SPDR S&P 500 ETF Trust") and not universe.looks_like_etf("Intellia Therapeutics, Inc. Common Stock"))

print("\n-- UNIVERSE_COLLAPSE instrumentation")
mem = [universe.Member(s, s, "NASDAQ", 10.0, dv, 60, True, True, True, False, universe.dv_bucket(dv))
       for s, dv in (("NVDA", 20e9), ("TSLA", 15e9), ("SPY", 30e9), ("NTLA", 50e6), ("SLDP", 8e6), ("KYTX", 4e6), ("ZZZ", 5e6))]
a = universe.collapse_audit(["NVDA", "TSLA", "SPY", "NTLA"], mem)
check("3 of 4 candidates from the old universe -> UNIVERSE_COLLAPSE", a["verdict"] == "UNIVERSE_COLLAPSE", str(a["share_old_universe"]))
b = universe.collapse_audit(["NTLA", "SLDP", "KYTX", "ZZZ", "NVDA"], mem)
check("1 of 5 old, 1 of 5 mega -> OK", b["verdict"] == "OK", str(b))
check("control holdings named in the audit", set(b["control_holdings_in_candidates"]) == {"NTLA", "SLDP", "KYTX"})
check("empty list is EMPTY, not OK", universe.collapse_audit([], mem)["verdict"] == "EMPTY")
comp = universe.composition(mem)
check("composition lists control holdings present and missing", "NTLA" in comp["control_holdings_present"] and "DKNG" in comp["control_holdings_missing"])

print("\n-- FAME_BIAS: the ranking score cannot see the ticker")
def score(f: Forecast) -> float:
    return abs(f.centre) / f.sd * f.conviction

famous = Forecast("post_event_drift", "NVDA", 2.0, 0.0072, 0.03, 1.0, "x", "gradient", {"r_day0": 0.05}, claim="direction")
anon = Forecast("post_event_drift", "ENTITY_48391", 2.0, 0.0072, 0.03, 1.0, "x", "gradient", {"r_day0": 0.05}, claim="direction")
check("identical numbers, different name -> identical score", score(famous) == score(anon), f"{score(famous):.4f} vs {score(anon):.4f}")
import inspect
from scripts import candidates as cand_mod
src = inspect.getsource(cand_mod.main)
sort_line = [l for l in src.splitlines() if "spoke.sort" in l][0]
check("the candidate sort key reads centre/sd/conviction only", "centre" in sort_line and "symbol" not in sort_line and "market_cap" not in sort_line, sort_line.strip())
check("policy string present on the report", "NO score" in src)

if __name__ == "__main__":
    print(f"\n{len(fails)} failures" + (": " + ", ".join(fails) if fails else ""))
    raise SystemExit(1 if fails else 0)
