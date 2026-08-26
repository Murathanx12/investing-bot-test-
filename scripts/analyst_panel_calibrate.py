"""Calibrate the analyst panel BEFORE trusting anything it says.

    python -m scripts.analyst_panel_calibrate

WHY THIS RUNS FIRST
===================
The parent project's rule, paid for once already: **reproduce a known fact
before trusting a novel one.** `rev_breadth` was bounded at |1| from a formula
rather than measured from the data, silently dropped 16,024 rows -- and
precisely the most-revised names -- and the signal still "worked" while its
leaderboard row looked ordinary.

So before any cross-sectional claim comes out of this panel, it has to reproduce
facts a correct capture cannot violate:

  1 COVERAGE RISES WITH SIZE. Mega-caps carry dozens of analysts; micro-caps
    carry a handful or none. If this is flat, the join is wrong.
  2 SELL-SIDE IS OPTIMISTIC. Net breadth should sit well ABOVE zero across the
    market -- the well-documented bias. A balanced distribution would mean we
    are not reading recommendation counts.
  3 ANALYSTS EXTRAPOLATE. Breadth should be higher for names that have already
    risen. If breadth is unrelated to past momentum, the two columns are not
    describing the same companies.
  4 ZERO COVERAGE IS NOT ZERO BREADTH. Uncovered names must be None, not 0.0 --
    collapsing them is exactly the `rev_breadth` mistake.

A failure here invalidates every downstream result from this panel, including
ones already written down.
"""

from __future__ import annotations

import json
import math
import statistics as st
import sys
from pathlib import Path

PANEL = Path(__file__).resolve().parent.parent / "state" / "research" / "analyst_panel"

BUCKETS = ["mega", "large", "mid", "small", "micro"]


def spearman(pairs: list[tuple[float, float]]) -> float:
    if len(pairs) < 8:
        return float("nan")
    xs = sorted(range(len(pairs)), key=lambda i: pairs[i][0])
    ys = sorted(range(len(pairs)), key=lambda i: pairs[i][1])
    rx, ry = [0] * len(pairs), [0] * len(pairs)
    for r, i in enumerate(xs):
        rx[i] = r
    for r, i in enumerate(ys):
        ry[i] = r
    n = len(pairs)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def main() -> int:
    files = sorted(PANEL.glob("*.jsonl"))
    if not files:
        print(f"no panel captures in {PANEL}")
        return 1
    latest = files[-1]
    rows = [json.loads(l) for l in latest.open(encoding="utf-8") if l.strip()]
    print(f"CALIBRATION  {latest.name}  {len(rows)} rows\n")

    fails = []

    def check(name, ok, detail=""):
        print(("  ok   " if ok else "  FAIL ") + name + (f"  {detail}" if detail else ""))
        if not ok:
            fails.append(name)

    # 1 -- coverage rises with size
    print("1. analyst coverage must rise with size")
    by_bucket = {}
    for b in BUCKETS:
        cov = [r["coverage"] for r in rows if r.get("dv_bucket") == b and r.get("coverage") is not None]
        if cov:
            by_bucket[b] = st.median(cov)
            print(f"     {b:6s} n={len(cov):>4d}  median coverage {st.median(cov):>5.1f}")
    present = [b for b in BUCKETS if b in by_bucket]
    if len(present) >= 3:
        check("coverage is monotone-ish from mega to micro",
              by_bucket[present[0]] > by_bucket[present[-1]],
              f"{present[0]} {by_bucket[present[0]]:.0f} vs {present[-1]} {by_bucket[present[-1]]:.0f}")

    # 2 -- sell-side optimism
    print("\n2. sell-side is optimistic: net breadth should sit ABOVE zero")
    nb = [r["net_breadth"] for r in rows if r.get("net_breadth") is not None]
    if nb:
        pos = sum(1 for v in nb if v > 0)
        print(f"     n={len(nb)}  mean {st.mean(nb):+.3f}  median {st.median(nb):+.3f}  "
              f"{100*pos/len(nb):.0f}% positive")
        check("mean net breadth is clearly positive", st.mean(nb) > 0.15, f"{st.mean(nb):+.3f}")
        check("...but not saturated at +1 (that would mean a broken denominator)",
              st.mean(nb) < 0.95 and min(nb) < 0.0, f"min {min(nb):+.2f} max {max(nb):+.2f}")

    # 3 -- analysts extrapolate
    print("\n3. analysts extrapolate: breadth should be higher for names that rose")
    pairs = [(r["mom_12_1"], r["net_breadth"]) for r in rows
             if r.get("mom_12_1") is not None and r.get("net_breadth") is not None]
    if len(pairs) >= 30:
        rho = spearman(pairs)
        print(f"     n={len(pairs)}  spearman(momentum, net breadth) = {rho:+.3f}")
        check("breadth is POSITIVELY related to past momentum", rho > 0.05, f"rho {rho:+.3f}")
    else:
        print(f"     only {len(pairs)} usable pairs -- not enough to check")

    # 4 -- zero coverage is not zero breadth
    print("\n4. zero coverage must be None, never 0.0")
    zero_cov = [r for r in rows if (r.get("coverage") or 0) == 0]
    bad = [r for r in zero_cov if r.get("net_breadth") is not None]
    print(f"     {len(zero_cov)} rows with no coverage")
    check("uncovered names carry net_breadth=None, not 0.0",
          not bad, f"{len(bad)} collapsed to a number")

    # 5 -- the PIT stamp
    print("\n5. every row is stamped, and price targets are absent not invented")
    check("every row carries captured_utc", all(r.get("captured_utc") for r in rows))
    check("no row invented a price target",
          all(r.get("price_target") is None for r in rows))
    check("...and each says WHY it is absent",
          all(r.get("price_target_status") == "UNAVAILABLE_FREE_TIER" for r in rows))

    # composition, so the panel cannot quietly become a mega-cap list
    print("\n6. composition -- the panel must not collapse to famous names")
    comp = {b: sum(1 for r in rows if r.get("dv_bucket") == b) for b in BUCKETS}
    print(f"     {comp}")
    small_share = (comp.get("small", 0) + comp.get("micro", 0)) / max(1, len(rows))
    check("at least a third of the panel is small/micro", small_share > 0.33,
          f"{100*small_share:.0f}%")

    print()
    if fails:
        print(f"{len(fails)} CALIBRATION FAILURE(S): {fails}")
        print("A failure here invalidates every downstream result from this panel.")
        return 1
    print("CALIBRATION PASSED -- the panel reproduces what a correct capture must.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
