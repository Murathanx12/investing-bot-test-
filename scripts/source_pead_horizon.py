"""SOURCE_PEAD_v1 -- when is the drift, and can a book that arrives LATE still take it?

    python -m scripts.source_pead_horizon [--json]

`scripts.post_event_relay` measures one number: the excess over days +1..+3 after
the print's first reflecting close, signed into the day-0 direction. That number
cannot answer the question the competition actually poses, which is a question
about ARRIVAL:

    the competition account is created at kickoff on 28 Aug. NVDA's first
    reflecting close is 27 Aug. If the whole drift is day +1, a book that opens
    on 28 Aug is buying the part that already happened.

So this splits the same excess by DAY -- +1, +2, +3 separately -- and grades the
cumulative trade from each possible entry, including an entry at the day+1 OPEN
(the earliest a book that was not alive at the day-0 close can act). An entry at
the open is deliberately the pessimistic read of an overnight signal: it pays the
gap away before it owns anything.

Same legs, same convention as `post_event_relay` (betas fitted on the 120
sessions BEFORE the print, forward excess is over beta * QQQ). Bars are re-pulled
because the receipt stores only the 3-day sum.
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
from alpha.brains.vol_gap import _daily_bars
from alpha.broker.alpaca import AlpacaPaper
from scripts.post_event_relay import SOURCES, BETA_WINDOW, _beta

FORWARD_DAYS = 3


def _state_dir() -> Path:
    return Path(config.__file__).resolve().parent.parent / "state"


def _series(bars: list[dict]) -> tuple[list[str], dict[str, dict]]:
    days = [b["t"][:10] for b in bars]
    px = {days[i]: {"o": float(bars[i]["o"]), "c": float(bars[i]["c"])} for i in range(len(days))}
    return days, px


def _t_stat(vals: list[float]) -> float | None:
    if len(vals) < 3:
        return None
    sd = statistics.pstdev(vals)
    return statistics.mean(vals) / (sd / math.sqrt(len(vals))) if sd > 0 else None


def grade(vals: list[float]) -> dict:
    if len(vals) < 3:
        return {"n": len(vals)}
    t = _t_stat(vals)
    return {"n": len(vals), "mean": round(statistics.mean(vals), 4),
            "median": round(statistics.median(vals), 4),
            "hit": round(sum(1 for v in vals if v > 0) / len(vals), 3),
            "t": round(t, 2) if t is not None else None}


def _fmt(g: dict) -> str:
    if "mean" not in g:
        return f"n={g['n']:3d}  (too few)"
    tail = f"t {g['t']:+.2f}" if g["t"] is not None else "t n/a"
    return f"n={g['n']:3d}  mean {g['mean']:+.2%}  median {g['median']:+.2%}  hit {g['hit']:.0%}  {tail}"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()
    events = json.loads((_state_dir() / "event_straddle_backtest.json").read_text(encoding="utf-8"))["events"]

    names = sorted(set(SOURCES) | {"QQQ"})
    data: dict[str, tuple[list[str], dict[str, dict]]] = {}
    for n in names:
        try:
            data[n] = _series(_daily_bars(client, n, 800))
        except Exception as exc:                                         # noqa: BLE001
            print(f"  {n}: no bars ({exc})")
    qdays, qpx = data["QQQ"]

    def ret(px: dict, days: list[str], i: int) -> float:
        return px[days[i]]["c"] / px[days[i - 1]]["c"] - 1.0

    rows = []
    for e in events:
        s = e["symbol"]
        if s not in SOURCES or s not in data:
            continue
        sdays, spx = data[s]
        if e["event_day"] not in sdays:
            continue
        i0 = sdays.index(e["event_day"])
        if i0 < BETA_WINDOW + 2 or i0 + FORWARD_DAYS >= len(sdays):
            continue
        fwd_days = sdays[i0 + 1:i0 + 1 + FORWARD_DAYS]
        if any(d not in qpx for d in fwd_days) or any(d not in spx for d in sdays[i0 - BETA_WINDOW:i0]):
            continue
        window = sdays[i0 - BETA_WINDOW:i0]
        qi = {d: qdays.index(d) for d in window + fwd_days if d in qdays}
        if len(qi) < len(window) + len(fwd_days):
            continue
        ys = [ret(spx, sdays, sdays.index(d)) for d in window]
        xs = [ret(qpx, qdays, qi[d]) for d in window]
        beta_q = _beta(xs, ys)
        sign = 1 if ret(spx, sdays, i0) > 0 else (-1 if ret(spx, sdays, i0) < 0 else 0)
        if sign == 0:
            continue
        # per-day excess over beta * QQQ, signed into the day-0 direction
        daily = [sign * (ret(spx, sdays, sdays.index(d)) - beta_q * ret(qpx, qdays, qi[d])) for d in fwd_days]
        # entry at the day+1 OPEN: give up the overnight gap, keep +1 close .. +3 close
        d1 = fwd_days[0]
        q_prev_close = qpx[qdays[qi[d1] - 1]]["c"]
        gap = sign * ((spx[d1]["o"] / spx[e["event_day"]]["c"] - 1.0)
                      - beta_q * (qpx[d1]["o"] / q_prev_close - 1.0))
        rows.append({"source": s, "event_day": e["event_day"], "abs_move_0": abs(ret(spx, sdays, i0)),
                     "sign": sign, "d1": daily[0], "d2": daily[1], "d3": daily[2], "gap_overnight": gap})

    if not rows:
        print("no rows", file=sys.stderr)
        return 1

    print(f"\nSOURCE_PEAD_v1 horizon -- {len(rows)} prints, {len({r['source'] for r in rows})} names, "
          f"{min(r['event_day'] for r in rows)} .. {max(r['event_day'] for r in rows)}")
    print("  all figures are excess over beta*QQQ, SIGNED into the day-0 direction\n")

    out: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n": len(rows),
                 "names": sorted({r["source"] for r in rows})}

    print("  WHERE THE DRIFT IS, day by day")
    for k, label in (("d1", "day +1"), ("d2", "day +2"), ("d3", "day +3")):
        g = grade([r[k] for r in rows])
        out.setdefault("per_day", {})[label] = g
        print(f"    {label}   {_fmt(g)}")
    g = grade([r["gap_overnight"] for r in rows])
    out["overnight_gap_day0_close_to_day1_open"] = g
    print(f"    overnight (day-0 close -> day+1 open, excess)   {_fmt(g)}")

    print("\n  WHAT EACH ARRIVAL KEEPS")
    arrivals = {
        "day-0 close -> +3 close  (the headline trade)": [r["d1"] + r["d2"] + r["d3"] for r in rows],
        "day+1 OPEN  -> +3 close  (a book that woke up late)": [r["d1"] + r["d2"] + r["d3"] - r["gap_overnight"] for r in rows],
        "day+1 close -> +3 close  (a full session late)": [r["d2"] + r["d3"] for r in rows],
        "day+2 close -> +3 close": [r["d3"] for r in rows],
    }
    for label, vals in arrivals.items():
        g = grade(vals)
        out.setdefault("by_arrival", {})[label] = g
        print(f"    {label:52s} {_fmt(g)}")

    print("\n  THE SAME, restricted to the mid |day-0 move| band the decomposition liked (3.5%-8.2%)")
    mid = [r for r in rows if 0.035 <= r["abs_move_0"] <= 0.082]
    for label, key in (("day-0 close -> +3 close", "full"), ("day+1 OPEN -> +3 close", "late")):
        vals = ([r["d1"] + r["d2"] + r["d3"] for r in mid] if key == "full"
                else [r["d1"] + r["d2"] + r["d3"] - r["gap_overnight"] for r in mid])
        g = grade(vals)
        out.setdefault("mid_band", {})[label] = g
        print(f"    {label:52s} {_fmt(g)}")

    if args.json:
        path = _state_dir() / "source_pead_horizon.json"
        path.write_text(json.dumps({**out, "rows": rows}, indent=1), encoding="utf-8")
        print(f"\n  receipt: {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
