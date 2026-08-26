"""Attack the wide-PEAD result before it is allowed to size anything (review P2, the 40 checks).

    python -m scripts.pead_adversarial [--legs state/pead_wide_legs.jsonl] [--out state/pead_adversarial.json]

The finding under attack (`docs/FINDING_2026-08-26_PEAD_WIDE.md`): outside the eleven
mega-caps a day-0 DROP of 3.5-8.2% drifts a further +0.44% over 3 sessions (t 4.29
raw, 2.30 on weekly blocks) and a RISE reverses (-0.22%, t -1.99).

Every check below is a way that number could be an artefact rather than a mechanism,
and each prints a verdict the reader can disagree with. Checks that need a field the
legs file does not carry (opens, price, industry -- added to `pead_wide` on
2026-08-26) print NOT MEASURABLE ON THIS FILE instead of a number.

The checks (numbers are the review's):
   1-2   response CURVE by 1% bins of |day-0| -- is the edge smooth or a bin artefact?
   3-4   standard errors clustered by ISSUER, by WEEK, and TWO-WAY (Cameron-Gelbach-Miller)
   5-6   share of the sample in the 50 most recurring issuers; leave-one-issuer-out
   8     leave-one-year-out and leave-one-QUARTER-out (prints cluster in earnings seasons)
   10-13 exclusions: micro bucket, mega bucket, thin dollar volume, price < $5, biotech
   16-18 duplicate events within 5 sessions of each other; bmo vs amc
   21-24 residualise against IWM / XBI / SPY / raw instead of beta*QQQ
   25    30 / 50 / 100 bp round-trip cost
   29-35 overnight gap vs from-next-open; day-0 gap vs intraday
   38-40 horizon curve 1..21 sessions, by band; monotonicity with |day-0|
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

MID = "3.5-8.2%"
BIOTECH_WORDS = ("biotech", "pharma", "life sciences")


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _t(xs: list[float]) -> float:
    if len(xs) < 3:
        return 0.0
    sd = statistics.pstdev(xs)
    return statistics.mean(xs) / (sd / math.sqrt(len(xs))) if sd > 0 else 0.0


def week_of(d: str) -> str:
    dt = datetime.fromisoformat(d)
    return f"{dt.isocalendar()[0]}-{dt.isocalendar()[1]:02d}"


def quarter_of(d: str) -> str:
    dt = datetime.fromisoformat(d)
    return f"{dt.year}Q{(dt.month - 1) // 3 + 1}"


def cluster_t(rows: list[dict], key: str, clusters: list[str]) -> dict:
    """t of the MEAN with one-way / two-way cluster-robust SE (CGM 2011: V_a + V_b - V_ab)."""
    xs = [r[key] for r in rows]
    n = len(xs)
    if n < 3:
        return {"n": n}
    m = statistics.mean(xs)
    e = [x - m for x in xs]

    def v_by(fn) -> float:
        s: dict[str, float] = defaultdict(float)
        for r, ei in zip(rows, e):
            s[fn(r)] += ei
        return sum(v * v for v in s.values()) / (n * n)

    fns = {"issuer": lambda r: r["symbol"], "week": lambda r: week_of(r["day0"]),
           "quarter": lambda r: quarter_of(r["day0"]),
           "issuer_x_week": lambda r: r["symbol"] + "|" + week_of(r["day0"])}
    out = {"n": n, "mean": round(m, 5), "t_iid": round(_t(xs), 2)}
    for c in clusters:
        v = v_by(fns[c])
        out[f"t_{c}"] = round(m / math.sqrt(v), 2) if v > 0 else None
        out[f"n_{c}"] = len({fns[c](r) for r in rows})
    if "issuer" in clusters and "week" in clusters:
        v2 = v_by(fns["issuer"]) + v_by(fns["week"]) - v_by(fns["issuer_x_week"])
        out["t_two_way_issuer_week"] = round(m / math.sqrt(v2), 2) if v2 > 0 else None
    return out


def g(rows: list[dict], key: str = "signed") -> dict:
    xs = [r[key] for r in rows if key in r and r[key] is not None]
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "mean": round(statistics.mean(xs), 5), "hit": round(sum(x > 0 for x in xs) / len(xs), 3),
            "t": round(_t(xs), 2)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--legs", default="state/pead_wide_legs.jsonl")
    p.add_argument("--out", default="state/pead_adversarial.json")
    args = p.parse_args()
    rows = load(Path(args.legs))
    has = lambda k: any(k in r for r in rows[:50])  # noqa: E731
    rep: dict = {"legs": args.legs, "n_legs": len(rows), "generated": datetime.utcnow().isoformat() + "Z",
                 "fields_present": {k: has(k) for k in ("overnight_gap_signed", "price0", "industry", "signed_21", "raw_iwm_3")}}
    down = [r for r in rows if r["r0"] < 0]
    up = [r for r in rows if r["r0"] > 0]
    mid_down = [r for r in down if r["band"] == MID]
    mid_up = [r for r in up if r["band"] == MID]
    print(f"\nPEAD ADVERSARIAL on {args.legs}: {len(rows)} legs, mid-band DOWN n={len(mid_down)}, UP n={len(mid_up)}")

    # 1-2 response curve ---------------------------------------------------------
    print("\n[1-2] response curve, DOWN side (drift in the day-0 direction, 3 sessions), 1% bins of |day-0|")
    curve = {}
    for side, rs in (("down", down), ("up", up)):
        curve[side] = {}
        for lo in range(0, 20):
            hi = lo + 1 if lo < 19 else 99
            sel = [r for r in rs if lo / 100 <= abs(r["r0"]) < hi / 100]
            curve[side][f"{lo}-{hi}%"] = g(sel)
    for k, v in curve["down"].items():
        if v["n"]:
            print(f"    DOWN |r0| {k:7s} n={v['n']:5d} mean {v['mean']:+.2%} hit {v['hit']:.0%} t {v['t']:+.2f}")
    for k, v in curve["up"].items():
        if v["n"] and v["n"] > 100:
            print(f"    UP   |r0| {k:7s} n={v['n']:5d} mean {v['mean']:+.2%} hit {v['hit']:.0%} t {v['t']:+.2f}")
    rep["response_curve"] = curve
    # monotonicity (#40): rank corr of signed with |r0| on the DOWN side
    d_abs = [abs(r["r0"]) for r in down]
    d_sig = [r["signed"] for r in down]
    rep["down_spearman_abs_r0_vs_signed"] = round(_spearman(d_abs, d_sig), 4)
    print(f"    Spearman(|day-0|, drift) on the DOWN side: {rep['down_spearman_abs_r0_vs_signed']:+.3f}")

    # 3-4 clustering -------------------------------------------------------------
    print("\n[3-4] clustered standard errors, mid-band DOWN")
    cl = cluster_t(mid_down, "signed", ["issuer", "week", "quarter"])
    rep["mid_down_clustered"] = cl
    print(f"    iid t {cl['t_iid']:+.2f} | by issuer ({cl['n_issuer']}) t {cl['t_issuer']:+.2f} | by week ({cl['n_week']}) "
          f"t {cl['t_week']:+.2f} | by quarter ({cl['n_quarter']}) t {cl['t_quarter']:+.2f} | TWO-WAY issuer x week t {cl['t_two_way_issuer_week']:+.2f}")
    clb = cluster_t([r for r in down if r["band"] == ">8.2%"], "signed", ["issuer", "week", "quarter"])
    rep["big_down_clustered"] = clb
    print(f"    big band DOWN: iid {clb['t_iid']:+.2f} | issuer {clb['t_issuer']:+.2f} | week {clb['t_week']:+.2f} | quarter {clb['t_quarter']:+.2f} | two-way {clb['t_two_way_issuer_week']:+.2f}")
    clu = cluster_t(mid_up, "signed", ["issuer", "week", "quarter"])
    rep["mid_up_clustered"] = clu
    print(f"    mid band UP:   iid {clu['t_iid']:+.2f} | issuer {clu['t_issuer']:+.2f} | week {clu['t_week']:+.2f} | quarter {clu['t_quarter']:+.2f} | two-way {clu['t_two_way_issuer_week']:+.2f}")

    # 5-6 recurring issuers, leave-one-out ------------------------------------------
    print("\n[5-6] issuer concentration, mid-band DOWN")
    cnt = Counter(r["symbol"] for r in mid_down)
    top50 = cnt.most_common(50)
    share = sum(c for _, c in top50) / len(mid_down)
    rep["top50_issuer_share"] = round(share, 4)
    rep["max_obs_one_issuer"] = top50[0]
    print(f"    top-50 issuers hold {share:.1%} of the sample; the most frequent is {top50[0]}")
    loo = []
    base_sum = sum(r["signed"] for r in mid_down)
    for sym, c in cnt.items():
        rest = [r["signed"] for r in mid_down if r["symbol"] != sym]
        loo.append((round(_t(rest), 3), sym, c))
    loo.sort()
    rep["leave_one_issuer_out"] = {"min_t": loo[0], "max_t": loo[-1]}
    print(f"    leave-one-issuer-out t: min {loo[0][0]:+.2f} (drop {loo[0][1]}, {loo[0][2]} prints) .. max {loo[-1][0]:+.2f} (drop {loo[-1][1]})")

    # 8 leave-one-period-out ----------------------------------------------------
    print("\n[8] leave-one-period-out, mid-band DOWN")
    rep["leave_one_out"] = {}
    for name, fn in (("year", lambda r: r["day0"][:4]), ("quarter", lambda r: quarter_of(r["day0"]))):
        periods = sorted({fn(r) for r in mid_down})
        res = {}
        for per in periods:
            inn = [r["signed"] for r in mid_down if fn(r) == per]
            out = [r["signed"] for r in mid_down if fn(r) != per]
            res[per] = {"n_in": len(inn), "mean_in": round(statistics.mean(inn), 5), "t_in": round(_t(inn), 2),
                        "t_without": round(_t(out), 2)}
        rep["leave_one_out"][name] = res
        for per, v in res.items():
            print(f"    {name} {per}: in-period n={v['n_in']:4d} mean {v['mean_in']:+.2%} t {v['t_in']:+.2f} | without it t {v['t_without']:+.2f}")
    neg_q = [per for per, v in rep["leave_one_out"]["quarter"].items() if v["mean_in"] < 0]
    rep["quarters_with_negative_mean"] = neg_q

    # 10-13 exclusions -------------------------------------------------------------
    print("\n[10-13] exclusions, mid-band DOWN")
    ex = {
        "no_micro": [r for r in mid_down if r["dv_bucket"] != "micro"],
        "no_mega": [r for r in mid_down if r["dv_bucket"] != "mega"],
        "dollar_volume_ge_10M": [r for r in mid_down if r["dollar_volume"] >= 10e6],
        "dollar_volume_ge_50M": [r for r in mid_down if r["dollar_volume"] >= 50e6],
        "shortable_liquid_only_dv_ge_25M": [r for r in mid_down if r["dollar_volume"] >= 25e6],
    }
    if has("price0"):
        ex["price_ge_5"] = [r for r in mid_down if (r.get("price0") or 0) >= 5]
        ex["price_ge_10"] = [r for r in mid_down if (r.get("price0") or 0) >= 10]
    if has("industry"):
        known = [r for r in mid_down if r.get("industry")]
        ex["no_biotech_(industry_known_only)"] = [r for r in known if not any(w in (r["industry"] or "").lower() for w in BIOTECH_WORDS)]
        ex["biotech_only"] = [r for r in known if any(w in (r["industry"] or "").lower() for w in BIOTECH_WORDS)]
    rep["exclusions"] = {k: g(v) for k, v in ex.items()}
    for k, v in rep["exclusions"].items():
        if v["n"]:
            print(f"    {k:36s} n={v['n']:5d} mean {v['mean']:+.2%} hit {v['hit']:.0%} t {v['t']:+.2f}")
        else:
            print(f"    {k:36s} n=0 (industry is known for too few names -- NOT MEASURABLE)")
    if not has("price0"):
        print("    price < $5 / biotech: NOT MEASURABLE ON THIS FILE (needs the 2026-08-26 re-run)")

    # 16-18 duplicates, session --------------------------------------------------
    print("\n[16-18] duplicate events and release session, mid-band DOWN")
    by_sym: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        by_sym[r["symbol"]].append(r["day0"])
    dup = 0
    for sym, ds in by_sym.items():
        ds.sort()
        for a, b in zip(ds, ds[1:]):
            if (datetime.fromisoformat(b) - datetime.fromisoformat(a)).days <= 7:
                dup += 1
    rep["events_within_7_days_of_prior_same_issuer"] = dup
    print(f"    prints within 7 calendar days of the same issuer's prior print: {dup} of {len(rows)}")
    rep["by_session"] = {s: g([r for r in mid_down if r["session"] == s]) for s in ("bmo", "amc")}
    for s, v in rep["by_session"].items():
        print(f"    {s}: n={v['n']} mean {v['mean']:+.2%} t {v['t']:+.2f}")

    # 21-24 residualisation --------------------------------------------------------
    print("\n[21-24] the benchmark, mid-band DOWN (drift in the day-0 direction = SHORT return)")
    if has("raw_iwm_3"):
        alt = {}
        for name in ("raw_3", "raw_qqq_3", "raw_iwm_3", "raw_xbi_3", "raw_spy_3"):
            if name == "raw_3":
                xs = [-r["raw_3"] for r in mid_down]
                label = "raw (no benchmark)"
            else:
                xs = [-(r["raw_3"] - r[name]) for r in mid_down]
                label = f"minus {name[4:-2].upper()} (beta 1)"
            alt[label] = {"n": len(xs), "mean": round(statistics.mean(xs), 5), "t": round(_t(xs), 2)}
        alt["minus beta*QQQ (the finding)"] = g(mid_down)
        rep["residualisation"] = alt
        for k, v in alt.items():
            print(f"    {k:30s} n={v['n']} mean {v['mean']:+.2%} t {v['t']:+.2f}")
    else:
        print("    NOT MEASURABLE ON THIS FILE (needs the 2026-08-26 re-run)")

    # 25 costs ---------------------------------------------------------------------
    print("\n[25] round-trip cost, mid-band DOWN (borrow NOT included -- a separate, per-name number)")
    m = statistics.mean(r["signed"] for r in mid_down)
    sd = statistics.pstdev([r["signed"] for r in mid_down])
    rep["net_of_cost"] = {}
    for bp in (10, 30, 50, 100):
        net = m - bp / 1e4
        t = net / (sd / math.sqrt(len(mid_down)))
        rep["net_of_cost"][f"{bp}bp"] = {"mean": round(net, 5), "t": round(t, 2)}
        print(f"    {bp:3d} bp: mean {net:+.2%} t {t:+.2f}")
    small_down = [r for r in mid_down if r["dv_bucket"] == "small"]
    ms = statistics.mean(r["signed"] for r in small_down)
    sds = statistics.pstdev([r["signed"] for r in small_down])
    rep["net_of_cost_small_bucket"] = {f"{bp}bp": {"mean": round(ms - bp / 1e4, 5), "t": round((ms - bp / 1e4) / (sds / math.sqrt(len(small_down))), 2)} for bp in (30, 50, 100)}
    print("    small bucket: " + " | ".join(f"{k} {v['mean']:+.2%} t {v['t']:+.2f}" for k, v in rep["net_of_cost_small_bucket"].items()))

    # 29-35 timing -------------------------------------------------------------------
    print("\n[29-35] timing: where in the 3 sessions is the drift?")
    if has("overnight_gap_signed"):
        tm = {k: g(mid_down, k) for k in ("overnight_gap_signed", "from_open1_signed")}
        tm["day0_gap_share"] = {"mean_gap": round(statistics.mean(r["day0_gap"] for r in mid_down if "day0_gap" in r), 5),
                                "mean_intraday": round(statistics.mean(r["day0_intraday"] for r in mid_down if "day0_intraday" in r), 5)}
        rep["timing"] = tm
        print(f"    close_0 -> open_1 (the gap a next-open entry MISSES): mean {tm['overnight_gap_signed']['mean']:+.2%} t {tm['overnight_gap_signed']['t']:+.2f}")
        print(f"    open_1 -> close_3 (what a next-open entry EARNS):    mean {tm['from_open1_signed']['mean']:+.2%} t {tm['from_open1_signed']['t']:+.2f} hit {tm['from_open1_signed']['hit']:.0%}")
        print(f"    day 0 itself: gap {tm['day0_gap_share']['mean_gap']:+.2%} vs intraday {tm['day0_gap_share']['mean_intraday']:+.2%} (DOWN prints)")
        for bk in ("micro", "small", "mid", "large"):
            v = g([r for r in mid_down if r["dv_bucket"] == bk], "from_open1_signed")
            print(f"      from open_1, {bk:5s}: n={v['n']} mean {v['mean']:+.2%} t {v['t']:+.2f}")
        rep["timing_from_open1_by_bucket"] = {bk: g([r for r in mid_down if r["dv_bucket"] == bk], "from_open1_signed") for bk in ("micro", "small", "mid", "large", "mega")}
    else:
        print("    NOT MEASURABLE ON THIS FILE (needs the 2026-08-26 re-run)")

    # 38-40 horizon curve ------------------------------------------------------------
    print("\n[38-40] horizon curve (cumulative drift in the day-0 direction, sessions 1..21)")
    if has("signed_21"):
        hc = {}
        for label, sel in (("mid_down", mid_down), ("big_down", [r for r in down if r["band"] == ">8.2%"]),
                           ("mid_up", mid_up), ("big_up", [r for r in up if r["band"] == ">8.2%"]),
                           ("small_bucket_mid_down", small_down)):
            hc[label] = {h: g(sel, f"signed_{h}") for h in range(1, 22)}
            line = " ".join(f"{h}:{hc[label][h]['mean']:+.2%}({hc[label][h]['t']:+.1f})" for h in (1, 2, 3, 5, 10, 15, 21) if hc[label][h]["n"])
            print(f"    {label:22s} {line}")
        rep["horizon_curve"] = hc
    else:
        print("    NOT MEASURABLE ON THIS FILE (needs the 2026-08-26 re-run)")

    Path(args.out).write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(f"\nreceipt -> {args.out}")
    return 0


def _spearman(a: list[float], b: list[float]) -> float:
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for k, i in enumerate(order):
            r[i] = k
        return r
    ra, rb = ranks(a), ranks(b)
    ma, mb = statistics.mean(ra), statistics.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else 0.0


if __name__ == "__main__":
    sys.exit(main())
