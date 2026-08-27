"""INDEX_PREMIUM, second pass -- split the window, cap the loss, and compound it.

`scripts.index_premium_backtest` returns a mean. A mean is the least informative
number in a short-premium series, because the entire risk is in the tail: the
pooled seller reads +17.2%/week and contains a -254.3% week. This reads the same
receipt three ways that a mean cannot:

  1. BY SUB-PERIOD. An edge that is one regime is not an edge. The parent
     project's candidate read 4.38x / 0.43x / 2.09x by decade and the middle
     decade turned $10,000 into $6,813.
  2. CAPPED. An undefined short straddle is not a tradeable object here. A wing
     bought at a stated distance turns the -254% into a bounded loss, and the
     question is whether the edge SURVIVES paying for the wing -- most of the
     premium sits in the part you give away.
  3. COMPOUNDED at a fixed fraction of equity, which is what an account actually
     experiences. An arithmetic mean over percentage-of-premium returns is not a
     growth rate, and a 68% hit rate with a fat left tail can compound to less
     than cash while its average stays positive.

No new network calls: it reads state/index_premium_backtest.json.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics as st
from collections import defaultdict
from pathlib import Path


def _t(xs: list[float]) -> tuple[float, float, float]:
    n = len(xs)
    if n < 2:
        return (st.mean(xs) if xs else 0.0), 0.0, 0.0
    m, sd = st.mean(xs), st.stdev(xs)
    return m, sd, (m / (sd / math.sqrt(n)) if sd > 0 else 0.0)


def capped_seller(row: dict, wing_sd: float) -> float:
    """Seller P&L as a fraction of PREMIUM, with a protective wing.

    The wing is bought `wing_sd` implied moves from the strike. Its cost is not
    known from this receipt -- only the ATM straddle was priced -- so it is
    charged at a deliberately PESSIMISTIC fraction of the ATM premium, scaled by
    how far out it sits. Understating a hedge's cost is how a capped strategy
    gets talked into existence.
    """
    prem, spot, k = row["premium"], row["spot_entry"], row["strike"]
    settle = row["spot_settle"]
    width = wing_sd * row["implied_move"] * spot          # dollars from the strike
    intrinsic = max(0.0, settle - k) + max(0.0, k - settle)
    capped_intrinsic = min(intrinsic, width)              # the wing pays past `width`
    # Wing cost: a rough, conservative decay of ATM premium with distance.
    wing_cost = prem * max(0.10, math.exp(-0.9 * wing_sd))
    haircut = prem * 0.013 * 2.0                          # two structures, two crossings
    return (prem - wing_cost - capped_intrinsic - haircut) / prem


def compound(returns_on_risk: list[float], risk_frac: float) -> dict:
    """Grow $1 risking `risk_frac` of CURRENT equity each week. Ruin is absorbing."""
    eq, peak, mdd, ruined = 1.0, 1.0, 0.0, False
    for r in returns_on_risk:
        eq *= (1.0 + risk_frac * r)
        if eq <= 0.01:
            eq, ruined = 0.0, True
            break
        peak = max(peak, eq)
        mdd = max(mdd, 1.0 - eq / peak)
    return {"final": round(eq, 4), "max_drawdown": round(mdd, 4), "ruined": ruined}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--receipt", default="state/index_premium_backtest.json")
    p.add_argument("--out", default="state/index_premium_verdict.json")
    args = p.parse_args()
    data = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    rows = data["rows"]
    print(f"{len(rows)} weekly straddles, {data['first']} -> {data['last']}\n")

    # ---------------------------------------------------------------- 1. regimes
    print("1. BY SUB-PERIOD -- is the seller's edge one regime?")
    by_year = defaultdict(list)
    for r in rows:
        by_year[r["entry_day"][:4]].append(r["seller_pnl_pct"])
    print(f"   {'year':6} {'n':>4} {'mean':>8} {'median':>8} {'t':>7} {'hit':>6} {'worst':>9}")
    year_stats = {}
    for y in sorted(by_year):
        m, sd, t = _t(by_year[y])
        hit = sum(1 for x in by_year[y] if x > 0) / len(by_year[y])
        year_stats[y] = {"n": len(by_year[y]), "mean": round(m, 4), "t": round(t, 2),
                         "hit": round(hit, 3), "worst": round(min(by_year[y]), 4)}
        print(f"   {y:6} {len(by_year[y]):>4} {m:>7.1%} {st.median(by_year[y]):>7.1%} "
              f"{t:>7.2f} {hit:>5.0%} {min(by_year[y]):>8.1%}")
    signs = {y for y, s in year_stats.items() if s["mean"] > 0}
    print(f"   -> positive in {len(signs)} of {len(year_stats)} years"
          + ("" if len(signs) == len(year_stats) else "  <- NOT a stable edge"))

    # ------------------------------------------------------------------ 2. capped
    print("\n2. CAPPED -- does the edge survive buying the wing?")
    print(f"   {'wing':>6} {'mean':>8} {'median':>8} {'t':>7} {'hit':>6} {'worst':>9}  reading")
    capped = {}
    for wing_sd in (1.0, 1.5, 2.0, 3.0):
        xs = [capped_seller(r, wing_sd) for r in rows]
        m, sd, t = _t(xs)
        hit = sum(1 for x in xs if x > 0) / len(xs)
        capped[wing_sd] = {"mean": round(m, 4), "t": round(t, 2), "hit": round(hit, 3),
                           "worst": round(min(xs), 4), "series": xs}
        verdict = "survives" if m > 0 and t > 2 else ("marginal" if m > 0 else "DIES")
        print(f"   {wing_sd:>5.1f}x {m:>7.1%} {st.median(xs):>7.1%} {t:>7.2f} {hit:>5.0%} "
              f"{min(xs):>8.1%}  {verdict}")

    # ------------------------------------------- 2b. how much rests on that guess
    print("\n2b. SENSITIVITY -- the capped verdict is only as good as the wing PRICE,")
    print("    and this receipt never priced a wing. `capped_seller` charges a decay")
    print("    heuristic. So: at what wing cost does a 1.5x-wing seller break even?")
    prem_frac = [r["premium"] / r["spot_entry"] for r in rows]
    print(f"   {'wing cost':>12} {'mean':>8} {'t':>7}  (as a fraction of the ATM premium)")
    breakeven = None
    for wc in (0.05, 0.10, 0.15, 0.20, 0.259, 0.35, 0.50):
        xs = []
        for r in rows:
            prem, spot, k, settle = r["premium"], r["spot_entry"], r["strike"], r["spot_settle"]
            width = 1.5 * r["implied_move"] * spot
            intr = min(max(0.0, settle - k) + max(0.0, k - settle), width)
            xs.append((prem - prem * wc - intr - prem * 0.026) / prem)
        m, sd, t = _t(xs)
        # The mean falls monotonically in wing cost, so the threshold is the
        # LARGEST cost still positive -- not the first one tried.
        if m > 0:
            breakeven = wc
        tag = "  <- the heuristic used above" if abs(wc - 0.259) < 1e-6 else ""
        print(f"   {wc:>11.1%} {m:>7.1%} {t:>7.2f}{tag}")
    print(f"   -> a 1.5x wing must cost under ~{breakeven:.0%} of the ATM premium for the")
    print("      capped seller to be positive at all. Pricing real wings off expired")
    print("      contracts is the decisive next measurement; until then the capped")
    print("      rows above are an ASSUMPTION with a number, not a result.")
    out_sens = {"breakeven_wing_cost_frac_of_atm": breakeven,
                "median_atm_premium_frac_of_spot": round(st.median(prem_frac), 5)}

    # ------------------------------------------------------------- 3. compounding
    print("\n3. COMPOUNDED -- what an account actually experiences")
    naked = [r["seller_pnl_pct"] for r in rows]
    print(f"   {'structure':22} {'risk/wk':>8} {'final $1':>10} {'maxDD':>8}  ruin?")
    comp = {}
    for label, series in [("naked short straddle", naked)] + \
                         [(f"capped at {w:.1f}x", capped[w]["series"]) for w in (1.5, 2.0)]:
        for rf in (0.02, 0.05, 0.10):
            c = compound(series, rf)
            comp[f"{label}@{rf}"] = c
            print(f"   {label:22} {rf:>7.0%} {c['final']:>10.3f} {c['max_drawdown']:>7.1%}  "
                  f"{'RUINED' if c['ruined'] else ''}")

    out = {"n": len(rows), "first": data["first"], "last": data["last"],
           "by_year": year_stats,
           "capped": {str(k): {kk: vv for kk, vv in v.items() if kk != "series"}
                      for k, v in capped.items()},
           "compounded": comp, "wing_sensitivity": out_sens}

    best = max(capped.items(), key=lambda kv: kv[1]["t"])
    stable = len(signs) == len(year_stats)
    if not stable:
        out["verdict"] = ("REGIME, NOT EDGE: the seller's mean is not positive in every year of "
                          "the sample. Do not seed an arm on a pooled mean that a single year "
                          "contradicts.")
    elif best[1]["mean"] > 0 and best[1]["t"] > 2:
        out["verdict"] = (
            f"SURVIVES CAPPING: best wing {best[0]:.1f}x gives {best[1]['mean']:+.1%}/week, "
            f"t {best[1]['t']:.2f}, worst {best[1]['worst']:+.1%}. This is a CANDIDATE for a "
            f"defined-risk arm, not a promotion -- it is historical, in-sample on cost "
            f"assumptions, and owes a forward record.")
    else:
        out["verdict"] = ("THE EDGE IS IN THE WING: uncapped it is large and uncapped it is "
                          "untradeable. Capped, it does not clear its own noise. That is a "
                          "crash-risk premium being correctly paid for, not alpha.")
    print("\nVERDICT: " + out["verdict"])
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("receipt: " + args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
