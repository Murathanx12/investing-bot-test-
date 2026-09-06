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

famous = Forecast("post_event_drift", "NVDA", 2.0, 0.0072, 0.03, 1.0, "x", "declared:gradient", {"r_day0": 0.05}, claim="direction")
anon = Forecast("post_event_drift", "ENTITY_48391", 2.0, 0.0072, 0.03, 1.0, "x", "declared:gradient", {"r_day0": 0.05}, claim="direction")
check("identical numbers, different name -> identical score", score(famous) == score(anon), f"{score(famous):.4f} vs {score(anon):.4f}")
import inspect
from scripts import candidates as cand_mod
src = inspect.getsource(cand_mod.main)
sort_line = [l for l in src.splitlines() if "spoke.sort" in l][0]
check("the candidate sort key reads centre/sd/conviction only", "centre" in sort_line and "symbol" not in sort_line and "market_cap" not in sort_line, sort_line.strip())
check("policy string present on the report", "NO score" in src)

# --- OBSERVATION IS NOT EXECUTION (2026-08-31) -----------------------------
# WBUY was ranked FIRST by the news engine and moved 20%. It trades ~$25k/day,
# so the single $3m constant deleted it from the universe entirely -- no state
# row, no tracker entry, no seal, no opinion. Being unbuyable at our size must
# be a PROPERTY of a row, not the reason the row is missing.

a = universe.execution_authority(25_000.0, equity=99_200.0)
check("a $25k/day name is OBSERVE_ONLY, not deleted", a["tier"] == "OBSERVE_ONLY", a["reason"])
check("and carries a real, tiny dollar authority", a["max_usd"] == 250.0, str(a["max_usd"]))
check("1% of ADV is the participation cap", a["max_usd"] == 25_000.0 * universe.MAX_ADV_PARTICIPATION)

a = universe.execution_authority(40_000_000.0)
check("a liquid name is FULL authority", a["tier"] == "FULL", a["reason"])

a = universe.execution_authority(5_000.0)
check("below the OBSERVE floor authorises nothing", a["tier"] == "NONE" and a["max_usd"] == 0.0)

# ABSENCE IS NOT ZERO AND NOT A MILLION. An unknown dollar volume must report
# unknown and authorise nothing, never be silently treated as either bound.
a = universe.execution_authority(None)
check("an unknown dollar volume is UNKNOWN, not 0 and not full",
      a["tier"] == "UNKNOWN" and a["max_usd"] == 0.0, a["reason"])

check("the execute floor is unchanged at $3m",
      universe.MIN_EXECUTE_DOLLAR_VOLUME == 3_000_000.0 == universe.MIN_DOLLAR_VOLUME)
check("the observe floor is far below it",
      universe.MIN_OBSERVE_DOLLAR_VOLUME < universe.MIN_EXECUTE_DOLLAR_VOLUME / 100)

# load() DEFAULTS TO EXECUTE, so no existing caller changes behaviour.
import inspect as _i
_sig = _i.signature(universe.load)
check("load defaults to execute scope", _sig.parameters["scope"].default == "execute")
check("build takes a scope too", "scope" in _i.signature(universe.build).parameters)
try:
    universe.load(scope="whatever")
    check("an unknown scope is refused", False)
except ValueError:
    check("an unknown scope is refused, not silently treated as execute", True)

# HONEST ABOUT WHAT IS ON DISK. The stored file was built at the execute floor,
# so observe cannot yet be wider. The test pins the CLAIM, not a hoped-for count.
_ex, _ob = universe.load(), universe.load(scope="observe")
check("observe is a superset of execute", set(m.symbol for m in _ex) <= set(m.symbol for m in _ob))
check("every execute member clears the execute floor",
      all((m.median_dollar_volume or 0) >= universe.MIN_EXECUTE_DOLLAR_VOLUME for m in _ex))

# --- SIZE-AWARE EXECUTE FLOOR (2026-09-07, night-lab lane N3) --------------
# The $3m flat floor is an institution's floor. A $100k book at 1% ADV
# participation, one-session build, 5%-of-equity per-name cap needs
# ($100,000 x 0.05) / (0.01 x 1) = $500,000/day, not $3m -- the brainstorm's
# own arithmetic, now pinned.
f, why = universe.size_aware_execute_floor(100_000.0)
check("a $100k book's size-aware floor is $500k/day", f == 500_000.0, str(f))
check("and it carries no refusal", why is None, str(why))

f1m, _ = universe.size_aware_execute_floor(1_000_000.0)
f10m, _ = universe.size_aware_execute_floor(10_000_000.0)
check("a $1m book's floor is $5m/day", f1m == 5_000_000.0, str(f1m))
check("a $10m book's floor is $50m/day", f10m == 50_000_000.0, str(f10m))
check("the floor scales LINEARLY with book size at fixed participation",
      f1m == f * 10 and f10m == f * 100)

f_none, why_none = universe.size_aware_execute_floor(None)
check("a missing book size REFUSES, not a permissive default",
      f_none is None and why_none is not None and "book_size_usd" in why_none, str(why_none))
f_bad, why_bad = universe.size_aware_execute_floor(100_000.0, participation=0.0)
check("a zero participation REFUSES rather than dividing by zero",
      f_bad is None and why_bad is not None, str(why_bad))
f_neg, why_neg = universe.size_aware_execute_floor(-1.0)
check("a non-positive book size REFUSES",
      f_neg is None and why_neg is not None, str(why_neg))

# `execution_authority` without `book_size_usd` is BYTE-FOR-BYTE the old
# behaviour -- no existing caller changes.
a_old = universe.execution_authority(25_000.0, equity=99_200.0)
check("execution_authority with no book_size_usd is unchanged (OBSERVE_ONLY)",
      a_old["tier"] == "OBSERVE_ONLY" and a_old["max_usd"] == 250.0, str(a_old))

# THE RESURRECTION: a name that dies at the flat $3m floor lives at a $100k
# book's size-aware $500k floor.
mdv_1m = 1_000_000.0  # under $3m, over the $100k book's $500k floor
a_flat = universe.execution_authority(mdv_1m, equity=100_000.0)
check("a $1m/day name is OBSERVE_ONLY under the flat $3m floor",
      a_flat["tier"] == "OBSERVE_ONLY", str(a_flat))
a_sized = universe.execution_authority(mdv_1m, equity=100_000.0, book_size_usd=100_000.0)
check("the SAME name is FULL under the $100k book's size-aware floor",
      a_sized["tier"] == "FULL" and a_sized["floor_basis"] == "size_aware", str(a_sized))
check("its execute_floor_usd is the $500k derived floor",
      a_sized["execute_floor_usd"] == 500_000.0, str(a_sized["execute_floor_usd"]))

# A size-aware request that cannot be resolved REFUSES -- it does not fall
# back to the flat institutional floor and silently authorise at $3m.
a_refused = universe.execution_authority(mdv_1m, book_size_usd=100_000.0, participation=0.0)
check("an unresolvable size-aware request is CANNOT_DETERMINE, not a fallback",
      a_refused["tier"] == "CANNOT_DETERMINE" and a_refused["max_usd"] == 0.0, str(a_refused))

if __name__ == "__main__":
    print(f"\n{len(fails)} failures" + (": " + ", ".join(fails) if fails else ""))
    raise SystemExit(1 if fails else 0)
