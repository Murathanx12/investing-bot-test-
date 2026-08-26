"""NON_PRINT_BOUNCE_v1 through the battery that killed wide PEAD.

    python -m scripts.bounce_battery

THE CANDIDATE
=============
Session 11's placebo established that a >=5% one-day loser with NO earnings
print within +-5 sessions BOUNCES (+0.37% raw/3d, +2.14% raw/21d over 46,361
events), where a print loser does not (diff t 5.0). The print stops the bounce.
That is a clean mechanism result. The open question was whether the bounce is a
TRADE.

THE BATTERY, and it is the same one, in the same order
======================================================
Wide PEAD died in four steps, each of which looked fine until the next ran:
benchmark excess -> raw log -> simple returns -> realistic costs. Every step is
applied here, plus the two the PEAD post-mortem said were missing: per-QUARTER
stability (6 of 11 quarters were negative and the pooled t hid it) and the
liquidity bucket (the whole `liquid` edge in the parent project was ten names).

WHAT THE BATTERY IS FOR
=======================
Not to confirm the bounce. To find the units in which it stops existing. A
candidate that survives all of them is worth building; the point of running them
in order is that each one is cheap and the ordering is by how often it has
killed something before.

Reads `state/night_shadow/attention_placebo_rows.jsonl` (written by
`scripts.night_attention_placebo`). No network, no LLM, no cost.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as st
from collections import defaultdict
from pathlib import Path

ROWS = Path("state") / "night_shadow" / "attention_placebo_rows.jsonl"
OUT = Path("state") / "bounce_battery.json"

#: Round-trip cost on a stock, in simple-return terms. Same figure the PEAD
#: battery used, so the two verdicts are comparable.
COST_STOCK = 0.0030


def two_way_t(rows: list[dict], key: str) -> dict:
    """iid t, issuer-clustered t, week-clustered t, and the two-way minimum.

    The pooled iid t is the one that has been wrong every time: 46,361 events
    over 2,434 names and 126 weeks are not 46,361 independent observations.
    """
    vals = [r[key] for r in rows if key in r and r[key] is not None]
    n = len(vals)
    if n < 30:
        return {"n": n, "verdict": "CANNOT DETERMINE: n < 30"}
    mean = st.mean(vals)
    sd = st.stdev(vals)
    t_iid = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0

    def clustered(keyfn) -> tuple[float, int]:
        by = defaultdict(list)
        for r in rows:
            if key in r and r[key] is not None:
                by[keyfn(r)].append(r[key])
        means = [st.mean(v) for v in by.values() if v]
        k = len(means)
        if k < 5:
            return 0.0, k
        s = st.stdev(means)
        return (st.mean(means) / (s / math.sqrt(k)) if s > 0 else 0.0), k

    t_iss, n_iss = clustered(lambda r: r["symbol"])
    t_wk, n_wk = clustered(lambda r: r["day0"][:7])
    return {"n": n, "mean": round(mean, 5), "t_iid": round(t_iid, 2),
            "t_issuer": round(t_iss, 2), "n_issuer": n_iss,
            "t_month": round(t_wk, 2), "n_month": n_wk,
            "t_two_way": round(min(abs(t_iss), abs(t_wk)) * (1 if mean > 0 else -1), 2)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rows", default=str(ROWS))
    p.add_argument("--no-guard", dest="guard", action="store_false",
                   help="skip the corporate-action / calendar-gap guard, to see "
                        "what the contaminated numbers looked like")
    a = p.parse_args()

    path = Path(a.rows)
    if not path.exists():
        print(f"MISSING {path}. Rebuild with `python -m scripts.night_bars` then "
              "`python -m scripts.night_attention_placebo`.")
        return 2

    rows = [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]
    down_np = [r for r in rows if r["sign"] < 0 and not r["is_print"]]
    print(f"loaded {len(rows):,} rows; DOWN non-print = {len(down_np):,} "
          f"over {len({r['symbol'] for r in down_np}):,} names\n")

    report: dict = {"n_rows": len(rows), "n_down_nonprint": len(down_np), "steps": {}}

    # ------------------------------------------------------- STEP 0: the instrument
    # Distrust the number before the result. Two contaminations live in the bar
    # cache and BOTH inflate the bounce:
    #
    #  1. Alpaca's `adjustment=all` does not adjust a Chapter 11 share exchange
    #     or some microcap reverse splits. WOLF closes 1.21 and opens 18.00 the
    #     next session; that is not a 1,388% return, it is new shares.
    #  2. The placebo walks a symbol's OWN bar list, so `days[i0+1:i0+1+h]` takes
    #     the next h AVAILABLE bars regardless of calendar distance. AKTS has no
    #     bar after 2024-12-17; its "3-day" window jumps the delisting gap and
    #     lands on a post-reorganisation price.
    #
    # Both are MEASURED and REPORTED here, never silently filtered: a bound
    # asserted from a formula is a filter, and a filter on the informative tail
    # is invisible.
    if a.guard:
        from scripts.night_bars import load as load_bars
        bars = load_bars()
        daylist = {s: [x["t"][:10] for x in b] for s, b in bars.items()}
        idx = {s: {d: i for i, d in enumerate(ds)} for s, ds in daylist.items()}

        from datetime import date

        def spans_gap(r: dict, h: int, slack: float = 2.0) -> bool:
            """Did the h-session window take more than ~h*slack CALENDAR days?"""
            ds, ix = daylist.get(r["symbol"]), idx.get(r["symbol"])
            if not ds or not ix or r["day0"] not in ix:
                return True
            i0 = ix[r["day0"]]
            if i0 + h >= len(ds):
                return True
            d0 = date.fromisoformat(ds[i0])
            dh = date.fromisoformat(ds[i0 + h])
            return (dh - d0).days > max(7, h * slack + 4)

        gapped = [r for r in down_np if spans_gap(r, 3)]
        extreme = [r for r in down_np if abs(r.get("raw_3", 0.0)) > 1.0]
        bad = {id(r) for r in gapped} | {id(r) for r in extreme}
        clean = [r for r in down_np if id(r) not in bad]

        print("STEP 0  the instrument, before the result")
        print(f"  window spans a CALENDAR GAP (delisting/halt): {len(gapped):,} rows "
              f"({len(gapped) / len(down_np):.2%})")
        print(f"  |3-day log| > 1.0, suspected corporate action: {len(extreme):,} rows "
              f"({len(extreme) / len(down_np):.3%})")
        for r in sorted(extreme, key=lambda x: -abs(x["raw_3"]))[:6]:
            print(f"      {r['symbol']:<6} {r['day0']}  log3={r['raw_3'] * -1:+.2f}  "
                  f"simple={math.exp(r['raw_3'] * -1) - 1:+,.0%}  {r['dv_bucket']}")
        print(f"  DROPPED {len(down_np) - len(clean):,}; {len(clean):,} rows survive\n")
        report["steps"]["guard"] = {
            "gapped": len(gapped), "extreme": len(extreme),
            "dropped": len(down_np) - len(clean), "kept": len(clean),
            "extreme_examples": [{"symbol": r["symbol"], "day0": r["day0"],
                                  "log3": round(r["raw_3"] * -1, 3)}
                                 for r in sorted(extreme, key=lambda x: -abs(x["raw_3"]))[:12]],
        }
        down_np = clean

    # ---------------------------------------------------------------- step 1-2
    print("STEP 1-2  the bounce, raw vs excess over beta*QQQ")
    print("          (signed in the DAY-0 direction: negative = it bounced)")
    print(f"{'horizon':<10}{'raw mean':>11}{'raw t2w':>9}{'exc mean':>11}{'exc t2w':>9}")
    for h in (1, 3, 5, 21):
        rw = two_way_t(down_np, f"raw_{h}")
        ex = two_way_t(down_np, f"exc_{h}")
        report["steps"][f"h{h}"] = {"raw": rw, "exc": ex}
        print(f"{h:<10}{-rw['mean']:>+10.2%}{-rw['t_two_way']:>9}"
              f"{-ex['mean']:>+10.2%}{-ex['t_two_way']:>9}")
    print("  (printed with the sign FLIPPED so a positive number reads as a bounce)")

    # ------------------------------------------------------------------ step 3
    # A long earns the SIMPLE return. The rows carry log sums, so the long's
    # actual take is exp(sum) - 1, and the gap between the two is convexity --
    # the same term that made the wide short look tradeable when it was not.
    print("\nSTEP 3  what a LONG actually receives: simple returns net of costs")
    print(f"{'horizon':<10}{'log mean':>11}{'simple':>11}{'convexity':>11}{'net of 30bp':>13}")
    for h in (3, 21):
        logs = [r[f"raw_{h}"] * -1 for r in down_np if f"raw_{h}" in r]  # un-sign: actual log return
        if not logs:
            continue
        mlog = st.mean(logs)
        simple = st.mean([math.exp(x) - 1.0 for x in logs])
        net = simple - COST_STOCK
        report["steps"][f"long_h{h}"] = {"log_mean": round(mlog, 5),
                                         "simple_mean": round(simple, 5),
                                         "convexity": round(simple - mlog, 5),
                                         "net": round(net, 5)}
        print(f"{h:<10}{mlog:>+10.2%}{simple:>+10.2%}{simple - mlog:>+10.2%}{net:>+12.2%}")

    # ------------------------------------------------------------------ step 4
    print("\nSTEP 4  per-QUARTER stability of the EXCESS (the step PEAD failed)")
    byq = defaultdict(list)
    for r in down_np:
        y, m = int(r["day0"][:4]), int(r["day0"][5:7])
        byq[f"{y}Q{(m - 1) // 3 + 1}"].append(r)
    pos3 = pos21 = tot = 0
    print(f"{'quarter':<10}{'n':>7}{'exc 3d':>10}{'exc 21d':>10}")
    for q in sorted(byq):
        g = byq[q]
        e3 = -st.mean([r["exc_3"] for r in g if "exc_3" in r])
        e21 = -st.mean([r["exc_21"] for r in g if "exc_21" in r])
        tot += 1
        pos3 += e3 > 0
        pos21 += e21 > 0
        print(f"{q:<10}{len(g):>7,}{e3:>+9.2%}{e21:>+9.2%}")
    report["steps"]["quarters"] = {"n": tot, "positive_3d": pos3, "positive_21d": pos21}
    print(f"  excess positive in {pos3}/{tot} quarters at 3d, {pos21}/{tot} at 21d")

    # ------------------------------------------------------------------ step 5
    print("\nSTEP 5  liquidity buckets (the parent project's `liquid` edge was ten names)")
    print(f"{'bucket':<10}{'n':>8}{'names':>7}{'exc 3d':>10}{'t2w':>7}{'exc 21d':>10}{'t2w':>7}")
    report["steps"]["buckets"] = {}
    for bk in ("micro", "small", "mid", "large"):
        g = [r for r in down_np if r.get("dv_bucket") == bk]
        if len(g) < 30:
            continue
        e3, e21 = two_way_t(g, "exc_3"), two_way_t(g, "exc_21")
        report["steps"]["buckets"][bk] = {"exc_3": e3, "exc_21": e21}
        print(f"{bk:<10}{len(g):>8,}{len({r['symbol'] for r in g}):>7,}"
              f"{-e3['mean']:>+9.2%}{-e3['t_two_way']:>7}"
              f"{-e21['mean']:>+9.2%}{-e21['t_two_way']:>7}")

    # ------------------------------------------------------------------ step 6
    # The micro cell is the one that looks like a SHORT in excess terms. A short
    # is paid -(e^r - 1), so its arithmetic mean is dominated by the losers'
    # right tail. This is where the wide PEAD short died and it is the first
    # place to check any new short.
    print("\nSTEP 6  the micro cell as a SHORT: log vs simple, the convexity charge")
    micro = [r for r in down_np if r.get("dv_bucket") == "micro"]
    if micro:
        logs3 = [r["raw_3"] * -1 for r in micro if "raw_3" in r]
        mlog = st.mean(logs3)
        short_simple = st.mean([-(math.exp(x) - 1.0) for x in logs3])
        print(f"  micro 3d: stock log {mlog:+.2%}  ->  short simple "
              f"{short_simple:+.2%}  (convexity charge {short_simple + mlog:+.2%})")
        print(f"  net of {COST_STOCK:.2%} costs: {short_simple - COST_STOCK:+.2%}")
        report["steps"]["micro_short"] = {
            "log_mean": round(mlog, 5), "short_simple": round(short_simple, 5),
            "convexity_charge": round(short_simple + mlog, 5),
            "net": round(short_simple - COST_STOCK, 5)}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
