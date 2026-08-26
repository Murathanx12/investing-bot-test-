"""FAME_BIAS_v1 verdict: is the drift bigger than the model's own noise?

    python -m scripts.fame_bias_report

Reads `state/research/fame_bias_v1.json` and answers one question: when the
numbers are identical and only the NAME changes, does the score change by more
than it changes when NOTHING changes?

Every cell examined is charged to the `fame_bias` family in
RESEARCH_ALPHA_BUDGET -- the overall test and each stratum. Slicing by fame
stratum is exactly the manoeuvre that manufactures a discovery, so it costs
budget.
"""

from __future__ import annotations

import json
import math
import statistics as st
import sys
from pathlib import Path

from alpha import alpha_budget

SRC = Path(__file__).resolve().parent.parent / "state" / "research" / "fame_bias_v1.json"


def paired_t(diffs: list[float]) -> tuple[float, float]:
    """(mean, t). Returns t=0.0 when there is no variation to test."""
    n = len(diffs)
    if n < 2:
        return (diffs[0] if diffs else 0.0), 0.0
    m = st.mean(diffs)
    sd = st.stdev(diffs)
    if sd <= 0:
        return m, (float("inf") if m != 0 else 0.0)
    return m, m / (sd / math.sqrt(n))


def main() -> int:
    if not SRC.exists():
        print(f"no data at {SRC} -- run `python -m scripts.fame_bias` first.")
        return 1
    d = json.loads(SRC.read_text(encoding="utf-8"))
    rows = d["rows"]

    by: dict[str, dict[str, list[int]]] = {}
    stratum_of: dict[str, str] = {}
    for r in rows:
        by.setdefault(r["symbol"], {}).setdefault(r["condition"], []).append(r["score"])
        stratum_of[r["symbol"]] = r["stratum"]

    complete = {s: v for s, v in by.items()
                if len(v.get("anon", [])) >= 2 and len(v.get("revealed", [])) >= 2}
    print(f"FAME_BIAS_v1  --  {d['model']} @ T={d['temperature']}, {len(rows)} replies, "
          f"{len(complete)} companies with all four draws\n")

    # THE NOISE FLOOR, computed first. A drift smaller than this is not a result.
    noise = [abs(v["anon"][0] - v["anon"][1]) for v in complete.values()] + \
            [abs(v["revealed"][0] - v["revealed"][1]) for v in complete.values()]
    noise_mean = st.mean(noise) if noise else 0.0
    noise_sd = st.pstdev(noise) if len(noise) > 1 else 0.0
    print(f"NOISE FLOOR (same condition, two draws): mean |diff| {noise_mean:.2f} points, "
          f"sd {noise_sd:.2f}, max {max(noise) if noise else 0}")
    print("  a drift below this is the model talking to itself, not fame.\n")

    drift = {s: st.mean(v["revealed"]) - st.mean(v["anon"]) for s, v in complete.items()}

    print(f"{'symbol':8s} {'stratum':17s} {'anon':>11s} {'revealed':>11s} {'drift':>7s}")
    for s in sorted(drift, key=lambda x: -drift[x]):
        v = complete[s]
        print(f"{s:8s} {stratum_of[s]:17s} {str(v['anon']):>11s} {str(v['revealed']):>11s} "
              f"{drift[s]:>+7.1f}")

    # COULD THIS HAVE ANSWERED? Asked before reporting what it said.
    ds = list(drift.values())
    sd_d = st.stdev(ds) if len(ds) > 1 else 0.0
    mde = 2.8 * sd_d / math.sqrt(len(ds)) if ds else float("inf")
    scores = sorted({r["score"] for r in rows})
    print(f"\nPOWER: drift sd {sd_d:.2f}p over n={len(ds)} -> MDE at 80% power is "
          f"{mde:.2f} points.")
    print(f"  the model used {len(scores)} distinct scores in total: {scores}")
    print("  a coarse, clustered output scale is itself a limit on what any drift test here")
    print("  can resolve -- a null below the MDE is 'not detected', never 'not present'.\n")

    cells = []
    m, t = paired_t(list(drift.values()))
    cells.append(("ALL", m, t, len(drift)))
    for stratum in ("household", "investor_famous", "sector_known", "obscure"):
        ds = [drift[s] for s in drift if stratum_of[s] == stratum]
        if len(ds) >= 2:
            mm, tt = paired_t(ds)
            cells.append((stratum, mm, tt, len(ds)))

    print(f"\n{'cell':18s} {'n':>3s} {'mean drift':>11s} {'t':>7s}  reads")
    for name, mm, tt, n in cells:
        verdict = ("above the noise floor" if abs(mm) > noise_mean else
                   "BELOW the noise floor")
        print(f"{name:18s} {n:>3d} {mm:>+10.2f}p {tt:>7.2f}  {verdict}")

    best = max(cells, key=lambda c: abs(c[2]) if math.isfinite(c[2]) else 0)
    # CHARGE ONCE PER EXPERIMENT, NOT ONCE PER RENDER. Re-reading a result is not
    # re-running it, and the first version of this script drained the family from
    # 0.100 to 0.023 across two renders of the SAME 78 replies. A budget that a
    # report can spend is not a budget on experiments; it is a tax on curiosity,
    # and it would eventually refuse a real discovery for having been read twice.
    stamp = f"run={d['run_utc']}"
    already = [h for h in alpha_budget.history("fame_bias") if stamp in (h.get("note") or "")]
    if already:
        prior = already[0]
        print(f"\nALPHA BUDGET  [{'PROMOTABLE' if prior.get('promoted') else 'NOT PROMOTABLE'}]"
              f"  (already charged for this run; not charging again)")
        print(f"  {prior.get('reason')}")
    else:
        v = alpha_budget.record_batch(
            "fame_bias",
            f"revealing the ticker moves the score; best cell {best[0]}",
            best_t=abs(best[2]) if math.isfinite(best[2]) else 0.0,
            n_tests=len(cells),
            note=f"{stamp} {len(complete)} companies, {len(rows)} replies, "
                 f"noise floor {noise_mean:.2f}p, MDE {mde:.2f}p")
        print(f"\nALPHA BUDGET  [{'PROMOTABLE' if v.promoted else 'NOT PROMOTABLE'}]")
        print(f"  {v.reason}")
        print(f"  family wealth {v.wealth_before:.4f} -> {v.wealth_after:.4f}")

    print("\nVERDICT")
    all_mean = cells[0][1]
    if abs(all_mean) <= noise_mean:
        print(f"  Overall drift {all_mean:+.2f} points does NOT clear the {noise_mean:.2f}-point")
        print(f"  noise floor, and the window could only have resolved {mde:.2f} points anyway.")
        print("  NOT DETECTED, which is not the same as NOT PRESENT: a fame effect smaller than")
        print(f"  {mde:.2f} points would be invisible here. On this evidence there is no measured")
        print("  case for anonymising packets, and no measured case for calling the LLM unbiased.")
    else:
        print(f"  Overall drift {all_mean:+.2f} points EXCEEDS the {noise_mean:.2f}-point noise")
        print("  floor. Identical numbers score differently when the name is attached, which is")
        print("  a measured argument for anonymising evidence packets in the candidate funnel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
