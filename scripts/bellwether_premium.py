"""BELLWETHER_PREMIUM_v1 -- is NVDA's straddle dear because NVDA's print moves the MARKET?

    python -m scripts.bellwether_premium [--json]

Hypothesis (Non-Diversifiable Volatility Risk and Risk Premiums at Earnings
Announcements): the more systematically important a print is, the richer its
straddle is relative to the single name's realised move -- buyers pay extra
because the option also insures the index. If true it EXPLAINS the NVDA 0/8
rather than merely observing it, and it says where not to buy long vol.

Measured, per reconstructed print: |QQQ|, |SMH| and own close-to-close move on
the event day. Per name: systemic share = mean |QQQ move on its prints| / mean
|own move|, and the beta of QQQ's signed move on the name's. Then the cross
section of names: does systemic share line up with mean straddle return?

n = 12 names. A rank correlation on twelve points is a sketch, and it is
printed as one. The event-level regression (does |QQQ move| on the day explain
the straddle's return?) is ex post -- it explains, it does not predict.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from alpha import config
from alpha.brains.vol_gap import _daily_bars
from alpha.broker.alpaca import AlpacaPaper


def _state_dir() -> Path:
    return Path(config.__file__).resolve().parent.parent / "state"


def _moves(bars: list[dict]) -> dict[str, float]:
    days = [b["t"][:10] for b in bars]
    cl = [float(b["c"]) for b in bars]
    return {days[i]: cl[i] / cl[i - 1] - 1.0 for i in range(1, len(days))}


def _rank(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    for k, i in enumerate(order):
        r[i] = float(k)
    return r


def spearman(a: list[float], b: list[float]) -> float | None:
    if len(a) < 4:
        return None
    ra, rb = _rank(a), _rank(b)
    ma, mb = statistics.mean(ra), statistics.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()
    events = json.loads((_state_dir() / "event_straddle_backtest.json").read_text(encoding="utf-8"))["events"]
    qqq = _moves(_daily_bars(client, "QQQ", 800))
    smh = _moves(_daily_bars(client, "SMH", 800))
    all_q = [abs(v) for v in qqq.values()]
    base_q = statistics.median(all_q)

    per_event = []
    for e in events:
        d = e["event_day"]
        if d not in qqq:
            continue
        per_event.append({**e, "qqq_move": qqq[d], "smh_move": smh.get(d), "own_move": e["signed_move"]})
    by_sym: dict[str, list[dict]] = {}
    for r in per_event:
        by_sym.setdefault(r["symbol"], []).append(r)

    table = []
    for sym, rs in sorted(by_sym.items()):
        own = [abs(r["own_move"]) for r in rs]
        q = [abs(r["qqq_move"]) for r in rs]
        s = [abs(r["smh_move"]) for r in rs if r["smh_move"] is not None]
        xs, ys = [r["own_move"] for r in rs], [r["qqq_move"] for r in rs]
        mx, my = statistics.mean(xs), statistics.mean(ys)
        vx = sum((x - mx) ** 2 for x in xs)
        beta = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / vx if vx > 0 else 0.0
        table.append({
            "symbol": sym, "n": len(rs),
            "mean_abs_own": statistics.mean(own), "mean_abs_qqq_on_prints": statistics.mean(q),
            "mean_abs_smh_on_prints": statistics.mean(s) if s else None,
            "qqq_over_baseline": statistics.mean(q) / base_q,
            "systemic_share": statistics.mean(q) / statistics.mean(own) if statistics.mean(own) > 0 else 0.0,
            "beta_qqq_on_own": beta,
            "mean_straddle_return": statistics.mean(r["straddle_return"] for r in rs),
            "median_implied_over_realised": statistics.median(r["implied_move"] / r["realised_abs_move"]
                                                              for r in rs if r["realised_abs_move"] > 0),
        })
    table.sort(key=lambda t: -t["systemic_share"])
    print(f"\nBELLWETHER_PREMIUM_v1 -- {len(per_event)} prints, {len(table)} names; QQQ median |move| any day {base_q:.2%}\n")
    print(f"{'name':6s} {'n':>3s} {'|own|':>7s} {'|QQQ|':>7s} {'QQQ/base':>8s} {'sys.share':>9s} {'beta':>6s} {'straddle':>9s} {'impl/real':>9s}")
    for t in table:
        print(f"{t['symbol']:6s} {t['n']:3d} {t['mean_abs_own']:7.2%} {t['mean_abs_qqq_on_prints']:7.2%} "
              f"{t['qqq_over_baseline']:8.2f} {t['systemic_share']:9.2f} {t['beta_qqq_on_own']:+6.2f} "
              f"{t['mean_straddle_return']:+9.1%} {t['median_implied_over_realised']:9.2f}")
    rho_share = spearman([t["systemic_share"] for t in table], [t["mean_straddle_return"] for t in table])
    rho_beta = spearman([t["beta_qqq_on_own"] for t in table], [t["mean_straddle_return"] for t in table])
    rho_rich = spearman([t["systemic_share"] for t in table], [t["median_implied_over_realised"] for t in table])
    print(f"\n  cross-section (n={len(table)} names -- a sketch): Spearman(systemic share, straddle return) = "
          f"{rho_share:+.2f}; Spearman(beta, straddle return) = {rho_beta:+.2f}; "
          f"Spearman(systemic share, implied/realised) = {rho_rich:+.2f}")
    print("  hypothesis says the first two NEGATIVE and the third POSITIVE.")
    # Event-level, ex post: on prints where QQQ moved a lot, did the straddle pay?
    big = [r for r in per_event if abs(r["qqq_move"]) > 2 * base_q]
    small = [r for r in per_event if abs(r["qqq_move"]) <= base_q]
    print(f"  ex post: straddle return when |QQQ| > 2x baseline (n={len(big)}): "
          f"{statistics.mean(r['straddle_return'] for r in big):+.1%}; when |QQQ| <= baseline (n={len(small)}): "
          f"{statistics.mean(r['straddle_return'] for r in small):+.1%}")
    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "qqq_median_abs_move": base_q,
           "names": table, "spearman_share_vs_straddle": rho_share, "spearman_beta_vs_straddle": rho_beta,
           "spearman_share_vs_richness": rho_rich,
           "ex_post_big_qqq": {"n": len(big), "mean_straddle": statistics.mean(r["straddle_return"] for r in big) if big else None},
           "ex_post_small_qqq": {"n": len(small), "mean_straddle": statistics.mean(r["straddle_return"] for r in small) if small else None}}
    if args.json:
        path = _state_dir() / "bellwether_premium.json"
        path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\n  receipt: {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
