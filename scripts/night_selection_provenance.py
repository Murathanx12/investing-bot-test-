"""SELECTION_PROVENANCE_v2 -- reconstruct Murat's decision rule from the DOCUMENTS, test the INTERACTION.

    python -m scripts.night_selection_provenance

The oracle (v1) inferred "a volatility screen" from returns. The review objects:
the source documents carried analyst 12-month targets, consensus ratings, a
colour mark, and a ">=50% upside with catalyst" rule. So: per pick, decision-time
features from the documents (`upside`, `rating`, `col`) and from bars as of
2025-11-07 (60d vol, drawdown from the 252d high, 63d prior return), forward
returns 21/63/126/200 sessions, and the same for every dv-bucket-matched
control in the universe. Then the INTERACTION cells, not the marginals:
  {upside hi/lo} x {vol hi/lo} x {drawdown deep/shallow}
and each cell's mean vs its own controls. Reads the night bar cache and
`state/murat_list_2025-11_grade.json`; writes `state/night_shadow/selection_provenance.json`.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from itertools import product
from pathlib import Path

from alpha import universe
from scripts.night_bars import load as load_bars

ASOF = "2025-11-07"
GRADE = Path("state") / "murat_list_2025-11_grade.json"
OUT = Path("state") / "night_shadow" / "selection_provenance.json"
H = (21, 63, 126, 200)


def feats(b, asof):
    days = [x["t"][:10] for x in b]
    c = [float(x["c"]) for x in b]
    i = max((k for k, d in enumerate(days) if d <= asof), default=-1)
    if i < 252 or i + 21 >= len(days):
        return None
    r = [math.log(c[k] / c[k - 1]) for k in range(i - 59, i + 1)]
    f = {"vol60": statistics.pstdev(r) * math.sqrt(252), "dd252": c[i] / max(c[i - 251:i + 1]) - 1.0,
         "ret63": c[i] / c[i - 63] - 1.0, "ret252": c[i] / c[i - 252] - 1.0}
    for h in H:
        f[f"fwd_{h}"] = (c[i + h] / c[i] - 1.0) if i + h < len(days) else None
    return f


def fmt(v):
    return f"{v * 100:+7.1f}%" if v is not None else "      -"


def main() -> int:
    bars = load_bars()
    members = {m.symbol: m for m in universe.load()}
    grade = json.loads(GRADE.read_text(encoding="utf-8"))
    picks, ctrls = {}, defaultdict(list)
    for s, m in members.items():
        if m.etf_like or s not in bars:
            continue
        f = feats(bars[s], ASOF)
        if f is None:
            continue
        f["dv_bucket"] = m.dv_bucket
        if s in grade:
            f.update({k: grade[s].get(k) for k in ("upside", "rating", "col", "grp")})
            picks[s] = f
        else:
            ctrls[m.dv_bucket].append(f)
    # control mean per bucket = the whole bucket (v1 drew 40 at random; the bucket mean is the population answer)
    cm = {}
    for b, v in ctrls.items():
        cm[b] = {}
        for h in H:
            xs = [x[f"fwd_{h}"] for x in v if x[f"fwd_{h}"] is not None]
            cm[b][h] = statistics.mean(xs) if xs else None
    for s, f in picks.items():
        for h in H:
            base = cm.get(f["dv_bucket"], {}).get(h)
            f[f"exc_{h}"] = (f[f"fwd_{h}"] - base) if f[f"fwd_{h}"] is not None and base is not None else None
    ups = [f["upside"] for f in picks.values() if f.get("upside") is not None]
    med = {"upside": statistics.median(ups) if ups else 0.5,
           "vol60": statistics.median(f["vol60"] for f in picks.values()),
           "dd252": statistics.median(f["dd252"] for f in picks.values()),
           "rating": statistics.median(f["rating"] for f in picks.values() if f.get("rating"))}
    rep = {"asof": ASOF, "n_picks": len(picks), "n_controls": sum(len(v) for v in ctrls.values()), "medians": med,
           "picks": picks, "control_means": cm}

    def cellname(f):
        return (("UPhi" if (f.get("upside") or 0) >= med["upside"] else "UPlo"),
                ("VOLhi" if f["vol60"] >= med["vol60"] else "VOLlo"),
                ("DDdeep" if f["dd252"] <= med["dd252"] else "DDshal"))

    cells = defaultdict(list)
    for s, f in picks.items():
        cells[cellname(f)].append(s)
    rep["interaction_cells"] = {}
    print(f"SELECTION PROVENANCE v2 as of {ASOF}: {len(picks)} picks with document features, {rep['n_controls']} controls")
    print(f"  medians: upside {med['upside']:.2f} vol60 {med['vol60']:.2f} dd252 {med['dd252']:.2f} rating {med['rating']:.2f}")
    print("  cell (upside x vol x drawdown)      n   exc21    exc63   exc126   exc200   names")
    for key in product(("UPhi", "UPlo"), ("VOLhi", "VOLlo"), ("DDdeep", "DDshal")):
        names = cells.get(key, [])
        row = {"n": len(names), "names": names}
        for h in H:
            xs = [picks[s][f"exc_{h}"] for s in names if picks[s][f"exc_{h}"] is not None]
            row[f"exc_{h}"] = round(statistics.mean(xs), 4) if xs else None
            row[f"hit_{h}"] = round(sum(1 for x in xs if x > 0) / len(xs), 2) if xs else None
        name = "x".join(key)
        rep["interaction_cells"][name] = row
        print(f"  {name:28s} {len(names):3d} {fmt(row['exc_21'])} {fmt(row['exc_63'])} {fmt(row['exc_126'])} {fmt(row['exc_200'])}   {','.join(names[:8])}")
    rep["marginals"] = {}
    print("  marginals (hi minus lo, exc63 / exc126):")
    for feat in ("upside", "vol60", "dd252", "rating"):
        hi = [f for f in picks.values() if (f.get(feat) or 0) >= med[feat]]
        lo = [f for f in picks.values() if (f.get(feat) or 0) < med[feat]]
        m = {}
        for h in (63, 126):
            a_ = [f[f"exc_{h}"] for f in hi if f[f"exc_{h}"] is not None]
            b_ = [f[f"exc_{h}"] for f in lo if f[f"exc_{h}"] is not None]
            m[h] = (round(statistics.mean(a_) - statistics.mean(b_), 4) if a_ and b_ else None, len(a_), len(b_))
        rep["marginals"][feat] = m
        print(f"    {feat:8s} 63: {m[63]}  126: {m[126]}")
    for k in ("col", "grp"):
        d = defaultdict(list)
        for f in picks.values():
            d[f.get(k)].append(f)
        out = {}
        for v, fs in d.items():
            out[str(v)] = {"n": len(fs)}
            for h in (63, 126):
                xs = [x[f"exc_{h}"] for x in fs if x[f"exc_{h}"] is not None]
                out[str(v)][f"exc_{h}"] = round(statistics.mean(xs), 4) if xs else None
        rep[f"by_{k}"] = out
        print(f"  by {k}: {out}")
    OUT.write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print(f"receipt -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
