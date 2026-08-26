"""ATTENTION_AFTERSHOCK_v1 -- is the post-print "detachment" an EARNINGS effect or a BIG-MOVE effect?

    python -m scripts.night_attention_placebo [--move 0.05]

Agent 7 found the drift lives in the day+1 session and the UP side shows the
same clock, which is the signature of ATTENTION / liquidity, not information.
The placebo: every session in the same universe with a |log return| >= --move
that is NOT within +-5 sessions of an SEC 8-K 2.02 print (`state/sec_cache/`),
measured with the SAME statistics as the print legs (raw, excess vs beta*QQQ,
short-from-next-open simple, pair vs IWM net of costs, horizon curve). If the
two populations are indistinguishable the mechanism is "big move", earnings
adds nothing, and the whole PEAD family folds into a generic aftershock study.
Reads the night bar cache; writes `state/night_shadow/attention_placebo.json`.
"""
from __future__ import annotations

import argparse, json, math, statistics
from collections import defaultdict
from pathlib import Path

from alpha import universe
from scripts.night_bars import load as load_bars
from scripts.pead_adversarial import cluster_t

CACHE = Path("state") / "sec_cache"
OUT = Path("state") / "night_shadow" / "attention_placebo.json"
BETA_WINDOW, EXCL = 120, 5
HORIZONS = (1, 2, 3, 5, 10, 21)
COST_STOCK, COST_ETF = 0.0030, 0.0004


def _rets(b):
    days = [x["t"][:10] for x in b]
    c = [float(x["c"]) for x in b]
    return days, c, {days[i]: math.log(c[i] / c[i - 1]) for i in range(1, len(b))}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--move", type=float, default=0.05)
    p.add_argument("--since", default="2024-02-26")
    a = p.parse_args()
    bars = load_bars()
    members = {m.symbol: m for m in universe.load()}
    qd, _, qr = _rets(bars["QQQ"])
    _, _, ir = _rets(bars["IWM"])
    rows: list[dict] = []
    for sym, m in members.items():
        b = bars.get(sym)
        if not b or len(b) < BETA_WINDOW + 30 or m.etf_like:
            continue
        pf = CACHE / f"{sym}.json"
        if not pf.exists():
            continue
        rel = json.loads(pf.read_text(encoding="utf-8"))
        if rel.get("error"):
            continue
        days, closes, rets = _rets(b)
        idx = {d: i for i, d in enumerate(days)}
        print_idx = set()
        for r in rel["releases"]:
            d = r["date"]
            t = d if r["session"] == "bmo" else next((x for x in days if x > d), None)
            if t in idx:
                print_idx.add(idx[t])
        near = set()
        for i in print_idx:
            near.update(range(i - EXCL, i + EXCL + 1))
        for i0 in range(BETA_WINDOW + 1, len(days) - 22):
            if days[i0] < a.since:
                continue
            r0 = rets[days[i0]]
            if abs(r0) < a.move:
                continue
            is_print = i0 in print_idx
            if not is_print and i0 in near:
                continue
            win = days[i0 - BETA_WINDOW:i0]
            xs = [qr.get(dd, 0.0) for dd in win]; ys = [rets.get(dd, 0.0) for dd in win]
            mx, my = statistics.mean(xs), statistics.mean(ys)
            vx = sum((x - mx) ** 2 for x in xs)
            beta = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / vx if vx > 0 else 1.0
            sgn = 1 if r0 > 0 else -1
            o1 = float(b[i0 + 1]["o"])
            if o1 <= 0:
                continue
            row = {"symbol": sym, "day0": days[i0], "r0": round(r0, 5), "is_print": is_print, "sign": sgn,
                   "dv_bucket": m.dv_bucket, "beta": round(beta, 3),
                   "overnight_gap_signed": round(math.log(o1 / closes[i0]) * sgn, 5),
                   "s1_open_close_signed": round(math.log(closes[i0 + 1] / o1) * sgn, 5)}
            for h in HORIZONS:
                hd = days[i0 + 1:i0 + 1 + h]
                raw = sum(rets.get(dd, 0.0) for dd in hd)
                row[f"raw_{h}"] = round(raw * sgn, 5)
                row[f"exc_{h}"] = round((raw - beta * sum(qr.get(dd, 0.0) for dd in hd)) * sgn, 5)
            hd = days[i0 + 1:i0 + 4]
            log_stock = math.log(closes[i0 + 3] / o1)
            if sgn < 0:
                ss = -(math.exp(log_stock) - 1.0)
                row["short_simple_net"] = round(ss - COST_STOCK, 5)
                row["pair_iwm_net"] = round(ss + (math.exp(sum(ir.get(dd, 0.0) for dd in hd)) - 1.0) - COST_STOCK - COST_ETF, 5)
            rows.append(row)
    keys = ["overnight_gap_signed", "s1_open_close_signed", "raw_1", "raw_3", "raw_5", "raw_21", "exc_1", "exc_3", "exc_5", "exc_21",
            "short_simple_net", "pair_iwm_net"]
    rep = {"move": a.move, "since": a.since, "n_rows": len(rows), "cells": {}}

    def cell(name, pred):
        sub = [r for r in rows if pred(r)]
        rep["cells"][name] = {k: cluster_t([r for r in sub if k in r], k, ["issuer", "week"]) for k in keys}
        rep["cells"][name]["n"] = len(sub)
        rep["cells"][name]["n_names"] = len({r["symbol"] for r in sub})
        return sub

    for sg, lab in ((-1, "DOWN"), (1, "UP")):
        for ip, lab2 in ((True, "print"), (False, "nonprint")):
            cell(f"{lab}_{lab2}", lambda r, sg=sg, ip=ip: r["sign"] == sg and r["is_print"] == ip)
            for bk in ("micro", "small", "mid", "large"):
                cell(f"{lab}_{lab2}_{bk}", lambda r, sg=sg, ip=ip, bk=bk: r["sign"] == sg and r["is_print"] == ip and r["dv_bucket"] == bk)
    # difference print - nonprint, Welch t, DOWN side, 3 sessions
    diff = {}
    for k in keys:
        pa = [r[k] for r in rows if r["sign"] < 0 and r["is_print"] and k in r]
        pb = [r[k] for r in rows if r["sign"] < 0 and not r["is_print"] and k in r]
        if len(pa) > 2 and len(pb) > 2:
            ma, mb = statistics.mean(pa), statistics.mean(pb)
            se = math.sqrt(statistics.variance(pa) / len(pa) + statistics.variance(pb) / len(pb))
            diff[k] = {"print": round(ma, 5), "nonprint": round(mb, 5), "diff": round(ma - mb, 5), "t_welch": round((ma - mb) / se, 2) if se else None}
    rep["down_print_minus_nonprint"] = diff
    OUT.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    (OUT.parent / "attention_placebo_rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    print(f"ATTENTION PLACEBO |move|>={a.move:.0%} since {a.since}: {len(rows)} movers")
    for name in ("DOWN_print", "DOWN_nonprint", "UP_print", "UP_nonprint"):
        c = rep["cells"][name]
        print(f"  {name:14s} n={c['n']:5d} names={c['n_names']:4d} " + "  ".join(
            f"{k}={c[k]['mean']*100:+.2f}%({c[k].get('t_two_way_issuer_week')})" for k in ("overnight_gap_signed", "s1_open_close_signed", "raw_3", "exc_3", "exc_5", "exc_21") if c[k].get("n")))
        for k in ("short_simple_net", "pair_iwm_net"):
            if c[k].get("n"):
                print(f"      {k}: {c[k]['mean']*100:+.3f}% t2w {c[k].get('t_two_way_issuer_week')}")
    print("  DOWN print minus non-print:")
    for k, v in diff.items():
        print(f"    {k:22s} print {v['print']*100:+.2f}%  nonprint {v['nonprint']*100:+.2f}%  diff {v['diff']*100:+.2f}%  t {v['t_welch']}")
    print(f"receipt -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
