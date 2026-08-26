"""AI_DEPRECIATION_REALITY_GAP_v1 -- is accounting life being stretched?

    python -m scripts.depreciation_gap

THE CLAIM BEING TESTED
======================
Murat raised it from a Coffeezilla recollection; the correction is that the
concern is **hyperscaler** accounting, not NVIDIA's own books. If Microsoft,
Meta, Alphabet and Amazon extend the assumed useful life of servers and AI
equipment, annual depreciation falls, reported profit rises, and the economics
of the AI build-out look better than they are -- until the gap closes.

That is a *checkable* claim, and it does not need anyone's opinion.

THE TEST, FROM XBRL AND NOTHING ELSE
====================================
    implied useful life  =  gross property, plant & equipment / annual depreciation

If a company depreciates $100bn of PP&E at $25bn a year, it is behaving as if
the assets last four years. **If that ratio RISES over time, the assumed life is
being stretched** -- whatever any 10-K footnote says in words.

This reads SEC XBRL company facts directly (`data.sec.gov`), so it is the
companies' own filed numbers, not a vendor's normalisation and not a scrape of
prose.

WHAT IT CANNOT SEE
==================
- **Mix.** PP&E is buildings, land and servers together. Datacentre shells last
  decades and GPUs do not, so a company shifting spend toward *shells* raises the
  implied life honestly. A rising ratio is a QUESTION, not a verdict.
- **The stated assumption.** The literal "we extended useful life from 4 to 6
  years" sentence lives in the text of the filing, not in these tags.
- **Economic life.** Nothing here says what the assets are actually worth. That
  needs used-GPU pricing and performance-per-dollar decay, which is the next
  phase and is not attempted.

So this measures the *accounting* side of the gap only. Stated plainly, because
half a measurement presented as a whole one is how a plausible story becomes a
believed one.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from collections import defaultdict

UA = "Aegis Research mrthnabdullaev@gmail.com"
CIK = {"MSFT": 789019, "META": 1326801, "GOOGL": 1652044, "AMZN": 1018724,
       "ORCL": 1341439, "NVDA": 1045810, "AAPL": 320193}

#: Tag preference order. Filers differ, so try several and record WHICH was used
#: -- a number whose provenance is unknown cannot be compared across companies.
DEPREC = ["Depreciation", "DepreciationDepletionAndAmortization",
          "DepreciationAmortizationAndAccretionNet"]
GROSS = ["PropertyPlantAndEquipmentGross"]
NET = ["PropertyPlantAndEquipmentNet"]
CAPEX = ["PaymentsToAcquirePropertyPlantAndEquipment",
         "PaymentsToAcquireProductiveAssets"]


def facts(cik: int) -> dict:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except Exception as e:                                     # noqa: BLE001
        return {"_error": f"{type(e).__name__}"}


def annual(f: dict, tags: list[str]) -> tuple[dict[int, float], str | None]:
    """{fiscal year: value} for the first tag that has annual data, and the tag."""
    us = (f.get("facts") or {}).get("us-gaap") or {}
    for tag in tags:
        node = us.get(tag)
        if not node:
            continue
        best: dict[int, tuple[str, float]] = {}
        for unit, rows in (node.get("units") or {}).items():
            if unit != "USD":
                continue
            for r in rows:
                if r.get("form") not in ("10-K", "20-F"):
                    continue
                fy, fp = r.get("fy"), r.get("fp")
                if fp != "FY" or fy is None:
                    continue
                # keep the LATEST filing of each year, so a restatement wins over
                # the original -- comparing an original to a restated year would
                # manufacture a trend out of a correction
                end = r.get("end") or ""
                if fy not in best or end > best[fy][0]:
                    best[fy] = (end, float(r.get("val") or 0))
        if best:
            return {k: v[1] for k, v in best.items()}, tag
    return {}, None


def main() -> int:
    print("AI_DEPRECIATION_REALITY_GAP_v1 -- implied useful life from SEC XBRL\n")
    print("implied life = gross PP&E / annual depreciation. A RISING number means")
    print("the assumed life is being stretched.\n")
    out = {}
    for sym, cik in CIK.items():
        f = facts(cik)
        time.sleep(0.4)
        if f.get("_error"):
            print(f"{sym:6s} UNAVAILABLE ({f['_error']}) -- excluded, not guessed")
            continue
        dep, dtag = annual(f, DEPREC)
        gross, gtag = annual(f, GROSS)
        net, ntag = annual(f, NET)
        base, btag = (gross, gtag) if gross else (net, ntag)
        if not dep or not base:
            print(f"{sym:6s} no usable annual tags (dep={dtag}, ppe={btag}) -- excluded")
            continue
        years = sorted(set(dep) & set(base))[-7:]
        if len(years) < 3:
            print(f"{sym:6s} only {len(years)} comparable years -- too few to read a trend")
            continue
        lives = {y: base[y] / dep[y] for y in years if dep[y] > 0}
        out[sym] = {"lives": lives, "dep_tag": dtag, "ppe_tag": btag,
                    "ppe_basis": "gross" if gross else "NET (gross unavailable)"}
        span = f"{years[0]}-{years[-1]}"
        first, last = lives[years[0]], lives[years[-1]]
        arrow = "RISING" if last > first * 1.05 else ("falling" if last < first * 0.95 else "flat")
        # MISSING YEARS. A "6.6y -> 12.8y" read across a five-year hole is not a
        # trend, it is two points. Filers change tags, and a gap must be visible
        # or the endpoints get quoted as if the series were continuous.
        gaps = [y for y in range(years[0], years[-1] + 1) if y not in lives]
        out[sym]["missing_years"] = gaps
        print(f"{sym:6s} {span}  " + "  ".join(f"{y}:{lives[y]:.1f}y" for y in years))
        note = f"  [{out[sym]['ppe_basis']}, dep tag {dtag}]"
        if gaps:
            note += f"\n       *** {len(gaps)} MISSING YEAR(S) {gaps} -- the endpoints are two"
            note += "\n           points across a hole, NOT a continuous trend ***"
        print(f"       {arrow}: {first:.1f}y -> {last:.1f}y  "
              f"({100*(last/first-1):+.0f}%){note}")

    # THE CONTROL. If the rise were an AI-datacentre story, a company without
    # hyperscale AI build-out should NOT show it. Apple does, strongly. That is
    # the single most important row in the table and it argues against the
    # AI-specific reading, so it is stated rather than left for a reader to spot.
    rising = [s for s, d in out.items()
              if len(d["lives"]) >= 3
              and list(d["lives"].values())[-1] > list(d["lives"].values())[0] * 1.05]
    print(f"\n  CONTROL: {len(rising)} of {len(out)} names show a rising implied life "
          f"({', '.join(rising)}).")
    if "AAPL" in rising:
        print("  **AAPL is among them.** Apple is not building AI datacentres at hyperscaler")
        print("  scale, so a rise there means this is NOT cleanly an AI-capex story -- it is")
        print("  large-cap tech generally, or a mix shift toward long-lived assets, or both.")
    if "NVDA" in out and "NVDA" not in rising:
        print("  NVDA moves the OTHER way, which is the one thing the original claim got")
        print("  right: the concern is customer accounting, not NVIDIA's own books.")

    print("\nWHAT THIS DOES AND DOES NOT SHOW")
    print("  PP&E mixes datacentre SHELLS (decades) with servers (a few years), so a")
    print("  company shifting spend toward shells raises implied life honestly. A rising")
    print("  ratio is a QUESTION, not a verdict, and the stated assumption lives in the")
    print("  filing TEXT rather than in these tags.")
    print("  Nothing here measures ECONOMIC life -- that needs used-GPU pricing and")
    print("  performance-per-dollar decay, which is the next phase and is not attempted.")
    print("  This is the ACCOUNTING half of the gap only.")

    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "state" / "research" / "depreciation_gap.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"source": "SEC XBRL companyfacts", "rows": out}, indent=1),
                 encoding="utf-8")
    print(f"\n  -> {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
