"""DYNAMIC_RESIDUAL_PAIR_v1, step 0 -- does the PEAD pair survive in the units the trade is paid in?

    python -m scripts.night_pair_regrade

The wide short lane closed because a short is paid in SIMPLE returns and the raw
short was +0.04%. The remnant was the PAIR (short loser / long IWM, +0.35%, t~2
iid). Before an executor is built the pair must survive: simple returns, entry at
the NEXT OPEN (what the engine can do), per QUARTER, two-way clustered t, 30 bp
round trip on the stock leg + 4 bp on the ETF leg, and a beta-scaled hedge as the
alternative to a 1:1 hedge. Reads `state/pead_wide_legs.jsonl`; writes
`state/night_shadow/pair_regrade.json`. No broker, no LLM.
"""
from __future__ import annotations

import json, math, statistics
from collections import defaultdict
from pathlib import Path

from scripts.pead_adversarial import cluster_t, quarter_of

LEGS = Path("state") / "pead_wide_legs.jsonl"
OUT = Path("state") / "night_shadow" / "pair_regrade.json"
MIN_MOVE = 0.05
COST_STOCK, COST_ETF = 0.0030, 0.0004


def build(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        if r["r0"] >= 0 or abs(r["r0"]) < MIN_MOVE or "from_open1_signed" not in r:
            continue
        # from_open1_signed = (log(c3/o1) - beta*qqq3) * sgn, sgn = -1 for a DOWN leg
        log_stock = -r["from_open1_signed"] + r["beta"] * r["raw_qqq_3"]
        short_simple = -(math.exp(log_stock) - 1.0)
        for h, key in (("iwm", "raw_iwm_3"), ("qqq", "raw_qqq_3"), ("xbi", "raw_xbi_3"), ("spy", "raw_spy_3")):
            etf_simple = math.exp(r[key]) - 1.0          # close0->close3 (ETF has no open in the legs)
            r[f"pair_{h}_1to1"] = short_simple + etf_simple
            r[f"pair_{h}_beta"] = short_simple + r["beta"] * etf_simple
            r[f"pair_{h}_1to1_net"] = r[f"pair_{h}_1to1"] - COST_STOCK - COST_ETF
        r["short_simple"] = short_simple
        r["short_simple_net"] = short_simple - COST_STOCK
        out.append(r)
    return out


def main() -> int:
    rows = build([json.loads(l) for l in LEGS.read_text(encoding="utf-8").splitlines() if l.strip()])
    keys = ["short_simple", "short_simple_net", "pair_iwm_1to1", "pair_iwm_1to1_net", "pair_iwm_beta",
            "pair_qqq_1to1", "pair_spy_1to1", "pair_xbi_1to1"]
    rep = {"n": len(rows), "min_move": MIN_MOVE, "entry": "next open, exit close of session 3",
           "costs_bp": {"stock_round_trip": COST_STOCK * 1e4, "etf_round_trip": COST_ETF * 1e4},
           "caveat": "ETF leg is close0->close3 (legs carry no ETF open); stock leg is open1->close3",
           "headline": {k: cluster_t(rows, k, ["issuer", "week", "quarter"]) for k in keys}}
    by_q = defaultdict(list)
    for r in rows:
        by_q[quarter_of(r["day0"])].append(r)
    rep["by_quarter"] = {q: {"n": len(v), "short_simple": round(statistics.mean(x["short_simple"] for x in v), 5),
                             "pair_iwm_1to1_net": round(statistics.mean(x["pair_iwm_1to1_net"] for x in v), 5),
                             "pair_iwm_beta": round(statistics.mean(x["pair_iwm_beta"] for x in v), 5)}
                         for q, v in sorted(by_q.items())}
    rep["by_bucket"] = {b: cluster_t([r for r in rows if r["dv_bucket"] == b], "pair_iwm_1to1_net", ["issuer", "week"])
                        for b in ("micro", "small", "mid", "large", "mega")}
    rep["by_band"] = {b: cluster_t([r for r in rows if lo <= abs(r["r0"]) < hi], "pair_iwm_1to1_net", ["issuer", "week"])
                      for b, lo, hi in (("5-8.2%", 0.05, 0.082), ("8.2-15%", 0.082, 0.15), (">15%", 0.15, 9))}
    # leave-one-quarter-out on the net pair
    loqo = {}
    for q in by_q:
        sub = [r for r in rows if quarter_of(r["day0"]) != q]
        loqo[q] = round(statistics.mean(r["pair_iwm_1to1_net"] for r in sub), 5)
    rep["leave_one_quarter_out_pair_net"] = loqo
    neg = sum(1 for v in rep["by_quarter"].values() if v["pair_iwm_1to1_net"] < 0)
    rep["verdict"] = {"quarters_negative_net": f"{neg}/{len(by_q)}",
                      "pair_net_t_two_way": rep["headline"]["pair_iwm_1to1_net"].get("t_two_way_issuer_week"),
                      "pair_net_t_quarter": rep["headline"]["pair_iwm_1to1_net"].get("t_quarter")}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(f"PAIR REGRADE (simple returns, next-open entry, >= {MIN_MOVE:.0%} DOWN prints): n={len(rows)}")
    for k in keys:
        h = rep["headline"][k]
        print(f"  {k:22s} mean {h['mean']*100:+.3f}%  t iid {h['t_iid']:5.2f}  issuer {h.get('t_issuer')}  week {h.get('t_week')}  quarter {h.get('t_quarter')}  two-way {h.get('t_two_way_issuer_week')}")
    print("  by quarter (short_simple | pair_iwm_net | pair_iwm_beta):")
    for q, v in rep["by_quarter"].items():
        print(f"    {q}  n={v['n']:4d}  {v['short_simple']*100:+.2f}%  {v['pair_iwm_1to1_net']*100:+.2f}%  {v['pair_iwm_beta']*100:+.2f}%")
    print("  by bucket (pair_iwm_net):", {b: (v.get("n"), v.get("mean"), v.get("t_two_way_issuer_week")) for b, v in rep["by_bucket"].items()})
    print("  by band   (pair_iwm_net):", {b: (v.get("n"), v.get("mean"), v.get("t_two_way_issuer_week")) for b, v in rep["by_band"].items()})
    print("  verdict:", rep["verdict"])
    print(f"receipt -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
