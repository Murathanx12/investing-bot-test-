"""PRE_PRINT_OPTION_FLOW_v1 -- does the option tape lean the right way before a print?

    python -m scripts.pre_print_option_flow [--json]

Johnson & So (2012) and Ge, Lin & Pearson (2016): option volume relative to
stock volume, and the put/call split of it, carry private information that is
revealed at the next earnings announcement -- traders who know lean into
options in the days before. We have the tape: Alpaca's daily option bars carry
volume per contract. For each reconstructed print, over the 3 sessions ending
at the entry close (all strictly BEFORE the print):

    call_vol, put_vol    summed over the 5 strikes nearest the money, both sides
    imbalance            (call_vol - put_vol) / (call_vol + put_vol)     in [-1, 1]
    o_s                  (call_vol + put_vol) * 100 / stock volume        (Johnson-So O/S)

and asks whether `imbalance` predicts the SIGN of the day-0 move, and whether
`o_s` predicts its SIZE (Johnson-So: high O/S -> larger absolute announcement
returns and, in their sample, lower returns).

Two things this cannot see: whether the volume was buyer- or seller-initiated
(the daily bar does not say), and open interest changes. It is the coarsest
version of the signal and it says so; a positive here earns the fine version,
a negative here does not kill it.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from alpha import config
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal
from alpha.brains.vol_gap import _daily_bars
from scripts.event_straddle_backtest import option_bars

LOOKBACK_SESSIONS = 3
STRIKES_EACH_SIDE = 2


def _state_dir() -> Path:
    return Path(config.__file__).resolve().parent.parent / "state"


def _strike_grid(k: float, inc: float) -> list[float]:
    return [round(k + i * inc, 2) for i in range(-STRIKES_EACH_SIDE, STRIKES_EACH_SIDE + 1)]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()
    events = json.loads((_state_dir() / "event_straddle_backtest.json").read_text(encoding="utf-8"))["events"]
    ubars: dict[str, list[dict]] = {}
    rows = []
    for e in events:
        sym = e["symbol"]
        if sym not in ubars:
            ubars[sym] = _daily_bars(client, sym, 800)
        days = [b["t"][:10] for b in ubars[sym]]
        vol_by_day = {b["t"][:10]: float(b.get("v") or 0) for b in ubars[sym]}
        if e["entry_day"] not in days:
            continue
        i = days.index(e["entry_day"])
        window = days[max(0, i - LOOKBACK_SESSIONS + 1): i + 1]
        exp = e["expiry"].replace("-", "")[2:]
        k = e["strike"]
        inc = 5.0 if k >= 200 else 2.5 if k >= 50 else 1.0
        syms = [f"{sym}{exp}{r}{int(round(s * 1000)):08d}" for s in _strike_grid(k, inc) for r in "CP"]
        try:
            bars = option_bars(client, syms, window[0], window[-1])
        except BrokerRefusal:
            continue
        call_v = put_v = 0.0
        n_contracts = 0
        for s in syms:
            b = bars.get(s) or []
            v = sum(float(x.get("v") or 0) for x in b if x["t"][:10] in window)
            if b:
                n_contracts += 1
            if s[-9] == "C":
                call_v += v
            else:
                put_v += v
        tot = call_v + put_v
        if tot <= 0 or n_contracts < 4:
            continue
        stock_v = sum(vol_by_day.get(d, 0.0) for d in window)
        rows.append({
            "symbol": sym, "event_day": e["event_day"], "entry_day": e["entry_day"],
            "call_vol": call_v, "put_vol": put_v, "n_contracts": n_contracts,
            "imbalance": (call_v - put_v) / tot, "o_s": (tot * 100.0 / stock_v) if stock_v else None,
            "signed_move": e["signed_move"], "abs_move": e["realised_abs_move"],
            "implied_move": e["implied_move"], "straddle_return": e["straddle_return"],
            "resid": e["realised_abs_move"] - e["implied_move"],
        })
    if len(rows) < 20:
        print("too few prints with option volume -- an absence, not a result")
        return 1

    def corr(a, b):
        ma, mb = statistics.mean(a), statistics.mean(b)
        sa, sb = statistics.pstdev(a), statistics.pstdev(b)
        return (sum((x - ma) * (y - mb) for x, y in zip(a, b)) / len(a)) / (sa * sb) if sa > 0 and sb > 0 else 0.0

    def t(xs):
        return statistics.mean(xs) / (statistics.pstdev(xs) / math.sqrt(len(xs))) if len(xs) > 2 and statistics.pstdev(xs) > 0 else None

    imb = [r["imbalance"] for r in rows]; sgn = [r["signed_move"] for r in rows]
    in_dir = [r["signed_move"] * (1 if r["imbalance"] > 0 else -1) for r in rows]
    hit = sum(1 for x in in_dir if x > 0) / len(in_dir)
    order = sorted(rows, key=lambda r: r["imbalance"]); n = len(order)
    terc_sign = [round(statistics.mean(r["signed_move"] for r in order[k * n // 3:(k + 1) * n // 3]), 4) for k in range(3)]
    with_os = sorted([r for r in rows if r["o_s"]], key=lambda r: r["o_s"]); m = len(with_os)
    terc_os_abs = [round(statistics.mean(r["abs_move"] for r in with_os[k * m // 3:(k + 1) * m // 3]), 4) for k in range(3)] if m >= 9 else None
    terc_os_strad = [round(statistics.mean(r["straddle_return"] for r in with_os[k * m // 3:(k + 1) * m // 3]), 4) for k in range(3)] if m >= 9 else None
    terc_os_resid = [round(statistics.mean(r["resid"] for r in with_os[k * m // 3:(k + 1) * m // 3]), 4) for k in range(3)] if m >= 9 else None
    # Extreme imbalance only: the sign call when the tape leans hard.
    strong = [r for r in rows if abs(r["imbalance"]) > 0.3]
    strong_dir = [r["signed_move"] * (1 if r["imbalance"] > 0 else -1) for r in strong]
    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n": len(rows),
           "lookback_sessions": LOOKBACK_SESSIONS, "strikes_each_side": STRIKES_EACH_SIDE,
           "corr_imbalance_vs_signed_move": round(corr(imb, sgn), 3),
           "sign_hit_rate": round(hit, 3), "mean_move_in_imbalance_direction": round(statistics.mean(in_dir), 4),
           "t_move_in_imbalance_direction": round(t(in_dir), 2) if t(in_dir) else None,
           "signed_move_by_imbalance_tercile": terc_sign,
           "strong_imbalance": {"n": len(strong), "hit": round(sum(1 for x in strong_dir if x > 0) / len(strong_dir), 3) if strong_dir else None,
                                "mean_in_direction": round(statistics.mean(strong_dir), 4) if strong_dir else None,
                                "t": round(t(strong_dir), 2) if strong_dir and t(strong_dir) else None},
           "abs_move_by_os_tercile": terc_os_abs, "straddle_return_by_os_tercile": terc_os_strad,
           "resid_by_os_tercile": terc_os_resid,
           "corr_os_vs_abs_move": round(corr([r["o_s"] for r in with_os], [r["abs_move"] for r in with_os]), 3) if m > 5 else None,
           "corr_os_vs_straddle": round(corr([r["o_s"] for r in with_os], [r["straddle_return"] for r in with_os]), 3) if m > 5 else None,
           "median_imbalance": round(statistics.median(imb), 3), "rows": rows}
    print(f"\nPRE_PRINT_OPTION_FLOW_v1 -- {len(rows)} prints, {LOOKBACK_SESSIONS} sessions of tape, {2 * STRIKES_EACH_SIDE + 1} strikes x 2 rights\n")
    print(f"  DIRECTION: corr(imbalance, signed day-0 move) {out['corr_imbalance_vs_signed_move']:+.3f}; sign hit {out['sign_hit_rate']:.0%}; "
          f"move in the tape's direction {out['mean_move_in_imbalance_direction']:+.2%} (t {out['t_move_in_imbalance_direction']})")
    print(f"     signed move by imbalance tercile (put-heavy -> call-heavy): {terc_sign}; median imbalance {out['median_imbalance']:+.2f}")
    s = out["strong_imbalance"]; print(f"     |imbalance| > 0.3: n={s['n']} hit {s['hit']} mean {s['mean_in_direction']} t {s['t']}")
    print(f"  SIZE (Johnson-So O/S): |move| by O/S tercile {terc_os_abs}; straddle return {terc_os_strad}; realised-implied {terc_os_resid}")
    print(f"     corr(O/S, |move|) {out['corr_os_vs_abs_move']}; corr(O/S, straddle return) {out['corr_os_vs_straddle']}")
    print("  reading: the daily bar cannot sign the volume; this is the coarse version. A sign hit near 50% here does not kill the fine version.")
    if args.json:
        path = _state_dir() / "pre_print_option_flow.json"
        path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\n  receipt: {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
