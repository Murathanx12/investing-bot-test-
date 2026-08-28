"""RESEARCH_COUNCIL_v1 -- the cube is code, the skeptic is independent, nothing trades.

Runs with no network and no LLM: the roles' prompts are strings, the cube is
arithmetic, and the assignment is a pure function of a probe result.
"""

from __future__ import annotations

import sys

from alpha.council import providers, roles, run

fails = 0


def check(name, ok, detail=""):
    global fails
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        fails += 1


print("\n-- surprise cube: the SentinelOne case (revenue RAISED, EPS LOWERED, in one release)")
facts = roles.normalise_rows({"rows": [
    {"metric": "Revenue", "basis": "GAAP", "period": "FY27", "value_low": 1.202e9, "value_high": 1.207e9, "unit": "USD", "kind": "guide_new", "quote": "Revenue $1.202 - 1.207 billion"},
    {"metric": "Non-GAAP diluted EPS", "basis": "non-GAAP", "period": "FY27", "value_low": 0.30, "value_high": 0.32, "unit": "per_share", "kind": "guide_new", "quote": "EPS $0.30 - 0.32"},
    {"metric": "Non-GAAP operating income", "basis": "non-GAAP", "period": "FY27", "value_low": 124e6, "value_high": 128e6, "unit": "USD", "kind": "guide_new", "quote": "$124 - 128 million"},
    {"metric": "Revenue", "basis": "GAAP", "period": "Q2 FY27", "value_low": 291.981e6, "value_high": 291.981e6, "unit": "USD", "kind": "actual", "quote": "Revenue $291,981"},
]})
expectations = {
    "prior_guidance": [
        {"metric": "revenue", "basis": "GAAP", "period": "FY27", "value_low": 1.195e9, "value_high": 1.205e9},
        {"metric": "eps_non_gaap", "basis": "non-GAAP", "period": "FY27", "value_low": 0.32, "value_high": 0.38},
    ],
    "consensus": [
        {"metric": "revenue", "basis": "unknown", "period": "Q2FY27", "value_low": 290.25e6, "value_high": 290.25e6, "source_quote": "Sales $291.981M Beats $290.25M Est"},
        {"metric": "eps_non_gaap", "basis": "unknown", "period": "FY27", "value_low": 0.35, "value_high": 0.35, "source_quote": "vs $0.35 Est"},
    ],
}
cube = roles.surprise_cube(facts, expectations)
by = {(c["axis"], c["metric"]): c for c in cube["cells"]}
check("revenue guide vs prior guide is a cell with sign +1", by.get(("guide_vs_prior_guide", "revenue"), {}).get("sign") == 1, str(by.keys()))
check("EPS guide vs prior guide is a cell with sign -1", by.get(("guide_vs_prior_guide", "eps_non_gaap"), {}).get("sign") == -1)
check("EPS guide vs consensus is a cell with sign -1 (0.31 vs 0.35), basis assumed and FLAGGED",
      by.get(("guide_vs_consensus", "eps_non_gaap"), {}).get("sign") == -1 and by[("guide_vs_consensus", "eps_non_gaap")]["basis_assumed"] is True)
check("Q2 revenue actual vs consensus matched across 'Q2 FY27' / 'Q2FY27' spellings", ("actual_vs_consensus", "revenue") in by)
check("operating income guide has NO prior -> listed incomparable, never subtracted",
      any(i["axis"] == "guide_vs_prior_guide" and i["metric"][0] == "operating_income" for i in cube["incomparable"]))
check("the cube carries opposite signs on one release -- what a single 'direction' cannot",
      {c["sign"] for c in cube["cells"] if c["axis"] == "guide_vs_prior_guide"} == {1, -1})

print("\n-- surprise cube: the Workday case (prior TOTAL revenue vs new SUBSCRIPTION revenue)")
facts_w = roles.normalise_rows({"rows": [
    {"metric": "Subscription revenue", "basis": "GAAP", "period": "FY27", "value_low": 9.940e9, "value_high": 9.950e9, "unit": "USD", "kind": "guide_new", "quote": "subscription revenue of $9.940 billion to $9.950 billion"},
    {"metric": "Non-GAAP operating margin", "basis": "non-GAAP", "period": "FY27", "value_low": 31.0, "value_high": 31.0, "unit": "percent", "kind": "guide_new", "quote": "operating margin guidance to 31.0%"},
]})
exp_w = {"prior_guidance": [
    {"metric": "Total revenues", "basis": "GAAP", "period": "FY27", "value_low": 10.635e9, "value_high": 10.660e9},
    {"metric": "subscription_revenue", "basis": "GAAP", "period": "FY27", "value_low": 9.925e9, "value_high": 9.950e9},
    {"metric": "operating_margin", "basis": "non-GAAP", "period": "FY27", "value_low": 30.5, "value_high": 30.5},
], "consensus": []}
cube_w = roles.surprise_cube(facts_w, exp_w)
byw = {(c["axis"], c["metric"]): c for c in cube_w["cells"]}
sub = byw.get(("guide_vs_prior_guide", "subscription_revenue"))
check("subscription guide is compared to the SUBSCRIPTION prior (+0.08%), not to total revenue",
      sub is not None and abs(sub["relative"] - ((9.945e9 / 9.9375e9) - 1)) < 1e-4, str(sub))
check("the -6.5% 'cut' a total-vs-subscription subtraction would produce does NOT exist",
      not any(c["relative"] is not None and c["relative"] < -0.05 for c in cube_w["cells"]))
check("operating margin raised is a +1 cell", byw.get(("guide_vs_prior_guide", "operating_margin"), {}).get("sign") == 1)

print("\n-- assignment: the skeptic never shares a family with the synthesiser")
live = {"deepseek": {"state": "live"}, "hf_deepseek_v4": {"state": "live"}, "nvidia_kimi": {"state": "down"},
        "nvidia_minimax": {"state": "live"}, "hf_glm": {"state": "down"}, "nvidia_gemma": {"state": "down"}}
who = run.assign(live)
check("fact -> deepseek family", providers.PROVIDERS[who["fact"]].family == "deepseek")
check("skeptic drawn from a different family than synthesis",
      providers.PROVIDERS[who["skeptic"]].family != providers.PROVIDERS[who["synthesis"]].family, str(who))
only_ds = {"deepseek": {"state": "live"}, "hf_deepseek_v4": {"state": "live"}}
who2 = run.assign(only_ds)
check("with one family live, the skeptic is still assigned (and the packet will say NOT independent)",
      who2["skeptic"] is not None and providers.PROVIDERS[who2["skeptic"]].family == "deepseek")
check("distinct_families counts families, not rows", providers.distinct_families(["deepseek", "hf_deepseek_v4", "hf_glm"]) == 2)

print("\n-- the council package imports no broker code")
import alpha.council.run as _r, alpha.council.roles as _ro, alpha.council.providers as _p
src = open(_r.__file__, encoding="utf-8").read() + open(_ro.__file__, encoding="utf-8").read() + open(_p.__file__, encoding="utf-8").read()
check("no `alpha.broker` import in the council package", "alpha.broker" not in src and "submit(" not in src)

print("\n-- historical analog: deterministic, band-keyed, honest when there is no reaction")
ha = roles.historical_analog("ZZZZ", None, mega_names=frozenset(), wide=None, mega=None)
check("no reaction -> not available, says why", ha["available"] is False and "no observable" in ha["why"])
wide = {"names_covered_by_sec": 2532, "legs": 25856, "benchmark": "beta*QQQ", "by_band": {"3.5-8.2%": {"t": 1.39}},
        "by_sign_mid_band": {"down": {"t": 4.29}}}
ha2 = roles.historical_analog("ZZZZ", -0.06, mega_names=frozenset(), wide=wide, mega=None)
check("-6% wide print -> mid band, DOWN sign, by-sign stats attached", ha2["band"] == "3.5-8.2%" and ha2["sign"] == "down" and ha2["by_sign_mid_band"]["t"] == 4.29)

print(f"\n{fails} failures" if fails else "\nALL PASS")
if __name__ == "__main__":
    sys.exit(1 if fails else 0)
