"""SOURCE_PEAD_v1 -- take the first positive t on record apart before trusting it.

    python -m scripts.source_pead_decompose [--json]

`scripts.post_event_relay` reported source PEAD at +1.13% 3-day excess, hit 64%,
t 2.72 on n=108 source legs. That t is computed as if 108 legs were 108
independent draws. They are not:

  * eleven names supply all 108 legs, so one name can carry it;
  * earnings CLUSTER -- several sources print in the same week and their 3-day
    forward windows overlap the same market, so the legs share a shock;
  * a "continuation in the day-0 direction" test on a market that rose over the
    sample is partly long drift whenever day 0 was an up day.

This script asks those three questions of the SAME legs (no re-pull; the receipt
is `state/post_event_relay.json`) and then the only one that decides a trade:
does +1.13% survive an option spread? Canon: n_effective counts DATE BLOCKS.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from alpha import config


def _state_dir() -> Path:
    return Path(config.__file__).resolve().parent.parent / "state"


def _t_stat(vals: list[float]) -> float | None:
    if len(vals) < 3:
        return None
    sd = statistics.pstdev(vals)
    if sd <= 0:
        return None
    return statistics.mean(vals) / (sd / math.sqrt(len(vals)))


def grade(rows: list[dict], *, cost: float = 0.0) -> dict:
    """Mean forward excess signed into the day-0 direction, minus a cost."""
    same = [r["forward_excess_3d"] * (1 if r["r_source_0"] > 0 else -1) - cost
            for r in rows if r["r_source_0"] != 0]
    if not same:
        return {"n": len(rows)}
    t = _t_stat(same)
    return {"n": len(rows),
            "mean": round(statistics.mean(same), 4),
            "median": round(statistics.median(same), 4),
            "hit": round(sum(1 for v in same if v > 0) / len(same), 3),
            "t": round(t, 2) if t is not None else None}


def _fmt(g: dict) -> str:
    if "mean" not in g:
        return f"n={g['n']:3d}  (too few)"
    tail = f"t {g['t']:+.2f}" if g["t"] is not None else "t n/a"
    return (f"n={g['n']:3d}  mean {g['mean']:+.2%}  median {g['median']:+.2%}  "
            f"hit {g['hit']:.0%}  {tail}")


def _week(day: str) -> str:
    y, m, d = (int(x) for x in day.split("-"))
    iso = date(y, m, d).isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def block_t(rows: list[dict], keyfn) -> dict:
    """One observation per block: the block's mean signed forward excess.

    If the legs inside a block share a shock, the block mean is the honest draw
    and the count of blocks is the honest n. This is the only t in the file that
    is allowed near a sizing decision."""
    blocks: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if r["r_source_0"] == 0:
            continue
        blocks[keyfn(r)].append(r["forward_excess_3d"] * (1 if r["r_source_0"] > 0 else -1))
    means = [statistics.mean(v) for v in blocks.values()]
    t = _t_stat(means)
    return {"n_blocks": len(means),
            "mean": round(statistics.mean(means), 4) if means else None,
            "hit": round(sum(1 for v in means if v > 0) / len(means), 3) if means else None,
            "t": round(t, 2) if t is not None else None}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    p.add_argument("--cost", type=float, default=0.0,
                   help="Round-trip cost charged to every leg, as a fraction of spot.")
    args = p.parse_args()

    src = _state_dir() / "post_event_relay.json"
    legs = [l for l in json.loads(src.read_text(encoding="utf-8"))["legs"] if l["is_source"]]
    if not legs:
        print("no source legs in the receipt", file=sys.stderr)
        return 1
    days = sorted({l["event_day"] for l in legs})
    names = sorted({l["source"] for l in legs})
    print(f"\nSOURCE_PEAD_v1 decomposition -- {len(legs)} source legs, {len(names)} names, "
          f"{len(days)} distinct event days, {days[0]} .. {days[-1]}\n")

    headline = grade(legs)
    print(f"  headline (every leg an independent draw)   {_fmt(headline)}")

    out: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(),
                 "source_receipt": str(src), "n_legs": len(legs), "n_names": len(names),
                 "n_event_days": len(days), "window": [days[0], days[-1]], "headline": headline}

    # --- 1. is it one name? -------------------------------------------------
    print("\n  BY NAME -- one name carrying it would make this a description of that name")
    by_name = {}
    for name in names:
        by_name[name] = grade([l for l in legs if l["source"] == name])
        print(f"    {name:6s} {_fmt(by_name[name])}")
    out["by_name"] = by_name

    print("\n  LEAVE ONE NAME OUT -- the headline with each name removed")
    loo = {}
    for name in names:
        loo[name] = grade([l for l in legs if l["source"] != name])
        print(f"    without {name:6s} {_fmt(loo[name])}")
    out["leave_one_name_out"] = loo
    worst = min(loo.items(), key=lambda kv: kv[1]["t"] if kv[1].get("t") is not None else 9.0)
    out["most_load_bearing_name"] = {"name": worst[0], **worst[1]}

    # --- 2. are the legs independent? ---------------------------------------
    print("\n  CLUSTERED -- one observation per block, because earnings weeks share a market")
    for label, fn in (("event day", lambda r: r["event_day"]),
                      ("calendar week", lambda r: _week(r["event_day"])),
                      ("name", lambda r: r["source"]),
                      ("month", lambda r: r["event_day"][:7])):
        b = block_t(legs, fn)
        out.setdefault("clustered", {})[label] = b
        tt = f"{b['t']:+.2f}" if b["t"] is not None else "n/a"
        print(f"    by {label:14s} blocks={b['n_blocks']:3d}  mean {b['mean']:+.2%}  "
              f"hit {b['hit']:.0%}  t {tt}")

    # --- 3. is it drift? ----------------------------------------------------
    print("\n  BY DAY-0 SIGN -- 'continuation' on an up day is long drift unless the down side works too")
    for label, rows in (("day 0 UP  ", [l for l in legs if l["r_source_0"] > 0]),
                        ("day 0 DOWN", [l for l in legs if l["r_source_0"] < 0])):
        g = grade(rows)
        out.setdefault("by_day0_sign", {})[label.strip()] = g
        print(f"    {label} {_fmt(g)}")

    # --- 4. where does it live? ---------------------------------------------
    print("\n  BY |DAY-0 MOVE| TERCILE -- a print the market barely reacted to is a different event")
    ranked = sorted(legs, key=lambda l: abs(l["r_source_0"]))
    third = max(len(ranked) // 3, 1)
    for label, rows in (("small", ranked[:third]), ("mid  ", ranked[third:2 * third]),
                        ("large", ranked[2 * third:])):
        g = grade(rows)
        lo = min(abs(r["r_source_0"]) for r in rows)
        hi = max(abs(r["r_source_0"]) for r in rows)
        out.setdefault("by_move_tercile", {})[label.strip()] = {**g, "abs_move_range": [round(lo, 4), round(hi, 4)]}
        print(f"    {label} |move| {lo:.1%}-{hi:.1%}  {_fmt(g)}")

    print("\n  BY YEAR")
    for y in sorted({l["event_day"][:4] for l in legs}):
        g = grade([l for l in legs if l["event_day"].startswith(y)])
        out.setdefault("by_year", {})[y] = g
        print(f"    {y}   {_fmt(g)}")

    # --- 5. does it survive being traded? -----------------------------------
    print("\n  NET OF COST -- charged to every leg, as a fraction of spot")
    for c in (0.0, 0.0025, 0.005, 0.01):
        g = grade(legs, cost=c)
        out.setdefault("net_of_cost", {})[f"{c:.4f}"] = g
        print(f"    cost {c:.2%}  {_fmt(g)}")
    print("\n  A 3-day directional option spread on a mega-cap pays far more than 1% of spot in")
    print("  half-spread alone. The stock-level number is the CEILING on what any structure keeps.")

    if args.json:
        path = _state_dir() / "source_pead_decompose.json"
        path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\n  receipt: {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
