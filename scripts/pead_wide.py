"""SOURCE PEAD across the WHOLE universe -- does the mechanism survive outside mega-caps?

    python -m scripts.pead_wide [--years 2.5] [--max-names 0] [--sec-rate 8]

The +1.13%/3d, t 2.72 result was measured on ELEVEN mega-caps. The engine now
searches ~2,000 names, and the literature (Bernard-Thomas 1989 onward) says
post-earnings drift is LARGER in small, less-covered names -- which is a claim,
not a measurement, until it is measured on this data with this event source.

For every member of HIGH_DISPERSION_US_v1 with SEC 8-K Item 2.02 filings:
    day 0     = first close reflecting the release (bmo same day, amc next)
    r_0       = log close-to-close across day 0
    forward   = sum of the next 3 sessions' log returns, minus beta_QQQ * QQQ's,
                beta fitted on the 120 sessions before the print
    signed    = forward * sign(r_0)        (the drift IN the day-0 direction)
graded by dollar-volume bucket, by |r_0| band, by day-0 sign, with the honest n
(one observation per calendar week per bucket) beside the raw one.

SEC submissions are cached on disk (`state/sec_cache/`) and fetched at
<= --sec-rate requests/second (EDGAR asks for <= 10). Bars come from the SIP
feed (consolidated), 1 request per 200 names per page.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpha import config, universe
from alpha.broker.alpaca import AlpacaPaper
from alpha.sources import sec
from alpha.sources.http import SourceRefusal, get_json

logger = logging.getLogger(__name__)
CACHE = Path("state") / "sec_cache"
OUT = Path("state") / "pead_wide.json"
FORWARD = 3
HOLD_HORIZONS = (10, 21)
ALT_BENCH = ("IWM", "XBI", "SPY")
BETA_WINDOW = 120
BANDS = (("<3.5%", 0.0, 0.035), ("3.5-8.2%", 0.035, 0.082), (">8.2%", 0.082, 9.0))


def releases_cached(symbol: str, *, max_age_days: int = 3) -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{symbol}.json"
    if p.exists() and (time.time() - p.stat().st_mtime) < max_age_days * 86400:
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("error"):
            raise SourceRefusal(d["error"])
        return d["releases"]
    try:
        rel = sec.earnings_releases(symbol)
    except SourceRefusal as exc:
        p.write_text(json.dumps({"error": str(exc)}), encoding="utf-8")
        raise
    p.write_text(json.dumps({"releases": rel}), encoding="utf-8")
    return rel


def _t(xs: list[float]) -> float:
    if len(xs) < 3:
        return 0.0
    sd = statistics.pstdev(xs)
    return statistics.mean(xs) / (sd / math.sqrt(len(xs))) if sd > 0 else 0.0


def grade(rows: list[dict], key: str = "signed") -> dict:
    xs = [r[key] for r in rows if key in r]
    if not xs:
        return {"n": 0}
    weeks: dict[str, list[float]] = {}
    for r in rows:
        d = datetime.fromisoformat(r["day0"])
        if key in r:
            weeks.setdefault(f"{d.isocalendar()[0]}-{d.isocalendar()[1]:02d}", []).append(r[key])
    wk = [statistics.mean(v) for v in weeks.values()]
    return {"n": len(xs), "mean": round(statistics.mean(xs), 5), "median": round(statistics.median(xs), 5),
            "hit": round(sum(1 for x in xs if x > 0) / len(xs), 3), "t": round(_t(xs), 2),
            "n_weeks": len(wk), "t_week_blocks": round(_t(wk), 2), "mean_week_blocks": round(statistics.mean(wk), 5)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--years", type=float, default=2.5)
    p.add_argument("--max-names", type=int, default=0, help="0 = whole universe")
    p.add_argument("--sec-rate", type=float, default=8.0)
    p.add_argument("--include-etf", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config.load_env()
    client = AlpacaPaper()
    members = universe.load()
    if not members:
        print("no universe on disk; build it first (alpha.universe.build)")
        return 1
    names = [m for m in members if args.include_etf or not m.etf_like]
    names.sort(key=lambda m: -m.median_dollar_volume)
    if args.max_names:
        names = names[:args.max_names]
    by_sym = {m.symbol: m for m in names}
    symbols = [m.symbol for m in names]
    logger.info("%d names (%d etf-like excluded)", len(symbols), sum(1 for m in members if m.etf_like))

    # -- bars, SIP, one shot ----------------------------------------------------
    start = (datetime.now(timezone.utc) - timedelta(days=int(args.years * 365) + 250)).strftime("%Y-%m-%d")
    t0 = time.time()
    bars = client.stock_bars_multi(symbols + ["QQQ"] + list(ALT_BENCH), start=start)
    logger.info("bars: %d symbols in %.0fs", len(bars), time.time() - t0)
    q = bars.get("QQQ") or []
    qdays = [b["t"][:10] for b in q]
    qr = {qdays[i]: math.log(float(q[i]["c"]) / float(q[i - 1]["c"])) for i in range(1, len(q))}
    # alternative benchmarks for residualisation (review P2 #21-24): raw returns kept per
    # leg so the adversarial script can subtract any of them, beta-fitted or not
    alt: dict[str, dict[str, float]] = {}
    for a in ALT_BENCH:
        ab = bars.get(a) or []
        ad = [b["t"][:10] for b in ab]
        alt[a] = {ad[i]: math.log(float(ab[i]["c"]) / float(ab[i - 1]["c"])) for i in range(1, len(ab))}

    # -- SEC dates, cached, rate-limited -----------------------------------------
    rows: list[dict] = []
    covered = refused = 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=int(args.years * 365))).date().isoformat()
    last = 0.0
    for k, sym in enumerate(symbols):
        b = bars.get(sym) or []
        if len(b) < BETA_WINDOW + FORWARD + 10:
            continue
        cached = (CACHE / f"{sym}.json").exists()
        if not cached:
            wait = (1.0 / args.sec_rate) - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
            last = time.time()
        try:
            rel = releases_cached(sym)
        except SourceRefusal:
            refused += 1
            continue
        covered += 1
        days = [x["t"][:10] for x in b]
        closes = [float(x["c"]) for x in b]
        idx = {d: i for i, d in enumerate(days)}
        rets = {days[i]: math.log(closes[i] / closes[i - 1]) for i in range(1, len(b))}
        for r in rel:
            d = r["date"]
            if d < cutoff:
                continue
            target = d if r["session"] == "bmo" else next((x for x in days if x > d), None)
            if target is None or target not in idx:
                continue
            i0 = idx[target]
            if i0 < BETA_WINDOW + 1 or i0 + FORWARD >= len(days):
                continue
            r0 = math.log(closes[i0] / closes[i0 - 1])
            win = days[i0 - BETA_WINDOW:i0]
            xs = [qr.get(dd, 0.0) for dd in win]
            ys = [rets.get(dd, 0.0) for dd in win]
            mx, my = statistics.mean(xs), statistics.mean(ys)
            vx = sum((x - mx) ** 2 for x in xs)
            beta = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / vx if vx > 0 else 1.0
            fwd_days = days[i0 + 1:i0 + 1 + FORWARD]
            fwd = sum(rets.get(dd, 0.0) for dd in fwd_days) - beta * sum(qr.get(dd, 0.0) for dd in fwd_days)
            sgn = 1 if r0 > 0 else -1
            # HOLD horizons: the same excess over every horizon 1..21, so "hold the
            # winners for weeks?" and "does the edge decay?" are one CURVE on the same
            # legs (review P1: a response curve, not another binary verdict).
            hold = {}
            for h in range(1, max(HOLD_HORIZONS) + 1):
                hd = days[i0 + 1:i0 + 1 + h]
                if len(hd) == h:
                    hold[f"signed_{h}"] = round((sum(rets.get(dd, 0.0) for dd in hd)
                                                 - beta * sum(qr.get(dd, 0.0) for dd in hd)) * sgn, 5)
            # TIMING (review P2 #29-35): the 3-session drift is split into the overnight
            # gap after day 0 (close_0 -> open_1) and the rest (open_1 -> close_3). A
            # lane that enters at the next open only ever earns the second part.
            o1 = float(b[i0 + 1]["o"]) if i0 + 1 < len(b) and float(b[i0 + 1]["o"]) > 0 else None
            timing = {}
            if o1 and i0 + FORWARD < len(b):
                gap = math.log(o1 / closes[i0])
                timing["overnight_gap_signed"] = round(gap * sgn, 5)
                timing["from_open1_signed"] = round((math.log(closes[i0 + FORWARD] / o1)
                                                     - beta * sum(qr.get(dd, 0.0) for dd in fwd_days)) * sgn, 5)
                # intraday day 0 vs overnight into day 0: was the print reacted to in the
                # gap (amc/bmo) or during the session?
                o0 = float(b[i0]["o"])
                if o0 > 0:
                    timing["day0_gap"] = round(math.log(o0 / closes[i0 - 1]), 5)
                    timing["day0_intraday"] = round(math.log(closes[i0] / o0), 5)
            # raw benchmark sums for the alternative residualisations
            bench = {f"raw_{a.lower()}_3": round(sum(alt[a].get(dd, 0.0) for dd in fwd_days), 5) for a in ALT_BENCH}
            bench["raw_qqq_3"] = round(sum(qr.get(dd, 0.0) for dd in fwd_days), 5)
            bench["raw_3"] = round(sum(rets.get(dd, 0.0) for dd in fwd_days), 5)
            band = next(name for name, lo, hi in BANDS if lo <= abs(r0) < hi)
            rows.append({"symbol": sym, "day0": target, "session": r["session"], "r0": round(r0, 5),
                         "fwd_excess": round(fwd, 5), "signed": round(fwd * sgn, 5), **hold, **timing, **bench,
                         "price0": round(closes[i0], 3), "beta": round(beta, 3), "band": band,
                         "dv_bucket": by_sym[sym].dv_bucket, "dollar_volume": by_sym[sym].median_dollar_volume,
                         "industry": by_sym[sym].industry, "market_cap_usd": by_sym[sym].market_cap_usd})
        if (k + 1) % 200 == 0:
            logger.info("  %d/%d names, %d legs so far", k + 1, len(symbols), len(rows))

    # -- grades -----------------------------------------------------------------
    def sub(pred):
        return grade([r for r in rows if pred(r)])

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(), "universe": universe.NAME,
        "names_covered_by_sec": covered, "names_refused_no_8k": refused, "legs": len(rows),
        "window_from": cutoff, "forward_sessions": FORWARD, "benchmark": "beta*QQQ, beta on 120 prior sessions",
        "headline_all": grade(rows),
        "by_dv_bucket": {bk: sub(lambda r, bk=bk: r["dv_bucket"] == bk) for bk in ("micro", "small", "mid", "large", "mega")},
        "by_band": {name: sub(lambda r, name=name: r["band"] == name) for name, _, _ in BANDS},
        "mid_band_by_bucket": {bk: sub(lambda r, bk=bk: r["dv_bucket"] == bk and r["band"] == "3.5-8.2%")
                               for bk in ("micro", "small", "mid", "large", "mega")},
        "by_sign_mid_band": {"up": sub(lambda r: r["band"] == "3.5-8.2%" and r["r0"] > 0),
                             "down": sub(lambda r: r["band"] == "3.5-8.2%" and r["r0"] < 0)},
        "hold_horizons_mid_band": {f"{h}_sessions": grade([r for r in rows if r["band"] == "3.5-8.2%"], f"signed_{h}") for h in HOLD_HORIZONS},
        "hold_horizons_mid_band_by_bucket": {bk: {f"{h}_sessions": grade([r for r in rows if r["band"] == "3.5-8.2%" and r["dv_bucket"] == bk], f"signed_{h}")
                                                  for h in HOLD_HORIZONS} for bk in ("micro", "small", "mid", "large", "mega")},
        "old_universe_only": sub(lambda r: r["symbol"] in universe.OLD_UNIVERSE),
        "not_old_universe": sub(lambda r: r["symbol"] not in universe.OLD_UNIVERSE),
        "mechanism_note": ("measured on ELEVEN mega-caps before this run; every bucket here is a NEW measurement "
                           "of the same rule, same event source (SEC 8-K 2.02), same benchmark"),
    }
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    (Path("state") / "pead_wide_legs.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    print(f"\nSOURCE PEAD, WIDE -- {covered} names with SEC dates ({refused} without), {len(rows)} legs since {cutoff}")
    print(f"  ALL            {_fmt(report['headline_all'])}")
    print(f"  old 15 names   {_fmt(report['old_universe_only'])}")
    print(f"  NOT old        {_fmt(report['not_old_universe'])}")
    print("  by $-volume bucket:")
    for bk, g in report["by_dv_bucket"].items():
        print(f"    {bk:6s}       {_fmt(g)}")
    print("  by |day-0| band:")
    for name, g in report["by_band"].items():
        print(f"    {name:9s}    {_fmt(g)}")
    print("  MID band (3.5-8.2%) by bucket:")
    for bk, g in report["mid_band_by_bucket"].items():
        print(f"    {bk:6s}       {_fmt(g)}")
    print("  HOLD the mid band longer (same legs):")
    for h, g in report["hold_horizons_mid_band"].items():
        print(f"    {h:12s} {_fmt(g)}")
    print(f"  mid band UP    {_fmt(report['by_sign_mid_band']['up'])}")
    print(f"  mid band DOWN  {_fmt(report['by_sign_mid_band']['down'])}")
    print(f"\nreceipt -> {OUT}")
    return 0


def _fmt(g: dict) -> str:
    if not g or not g.get("n"):
        return "n=0"
    return (f"n={g['n']:5d}  mean {g['mean']:+.2%}  median {g['median']:+.2%}  hit {g['hit']:.0%}  t {g['t']:+.2f}  "
            f"| weeks {g['n_weeks']} t {g['t_week_blocks']:+.2f}")


if __name__ == "__main__":
    sys.exit(main())
