"""T6 (Murat's rule cells) and T3 (sector lead vs laggard), on the features panel.

    python -m scripts.rule_cells                 # both tests
    python -m scripts.rule_cells --t6            # just the rule cells
    python -m scripts.rule_cells --t3            # just the sector test
    python -m scripts.rule_cells --json

T6 -- MURAT'S RULE, AS CELLS
============================
His green rows satisfy, together: (a) analyst target / price >= ~1.5,
(b) consensus rating >= ~4.1/5, (c) sector fit, (d) a dated catalyst inside 12
months, (e) already down from a recent level. The question is whether the
CONJUNCTION pays more than its parts, so the null is the rule with ONE CONDITION
DROPPED, not a coin.

**(b) CANNOT BE TESTED AND IS NOT.** `rating_counts_mean` is non-null on 21 of
5,678 symbol-days in the original panel, because `analyst_panel` is a PIT panel
recording FORWARD from 2026-08-26 and has four days of history. Using today's
ratings on a 2025 date is precisely the lookahead that panel exists to prevent,
so (b) is reported as UNAVAILABLE with its coverage and left out of every cell.
This test is (a) x (e), stated as such, and it becomes (a) x (b) x (e) when the
panel has vintages.

T3 -- THE SECTOR-LEAD THESIS
============================
Murat: sector-level bullish news moves correlated names, so find the demand and
then go to the best stock. The testable form: when >= `T3_MIN_NAMES` names in
one DECLARED driver take a positive attention shock in the same week, does the
driver's 20-day LAGGARD beat its LEADER over the next 21 sessions? Nulls: the
leader, and an unweighted average of the driver's other members.

WHY THE PANEL HAD TO BE WIDENED FIRST
=====================================
On the 23-symbol panel this question could not be ASKED: the only declared
drivers with three names were `murat_book` (a bag of picks, not a mechanism),
`UNCLASSIFIED` and `index_beta`. Every real theme had one name. The panel is
built with `corpus_features --universe corpus`.

THE HONEST n
============
A 21-session forward return computed on daily observations overlaps 20 of its 21
days with the next one. So every cell reports n_symbol_days AND n_blocks --
non-overlapping 21-session windows -- and the block count is the one that
governs. A t-statistic on the overlapping count is a number about the calendar,
not about the rule.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from alpha import config, drivers
from alpha.sources import corpus

PANEL = corpus.CORPUS / "features"
BENCH = "SPY"
HORIZONS = (21, 63)

#: Murat's own bars (roadmap section 3, reconstructed from his spreadsheets).
UPSIDE_BAR = 1.5
DRAWDOWN_BAR = -0.20
RATING_BAR = 4.1

#: T3: names in one driver that must take a shock in the same week.
T3_MIN_NAMES = 3
#: What counts as an attention shock. `attention_z` is items-vs-baseline, so 1.0
#: is one standard deviation of that name's OWN coverage -- normalised by
#: construction, which is the point: a 390:1 coverage ratio must not decide it.
T3_SHOCK_Z = 1.0


def load_panel() -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    rows: dict[str, list[dict]] = {}
    bars: dict[str, list[dict]] = {}
    for p in sorted(PANEL.glob("*.jsonl")):
        sym = p.stem
        if sym.startswith("bars_"):
            continue
        rows[sym] = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    for p in sorted(PANEL.glob("bars_*.json")):
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        bars[blob.get("symbol") or p.stem[5:]] = blob.get("bars") or []
    return rows, bars


def forward(bars: list[dict], h: int) -> dict[str, float]:
    """day -> return from the OPEN of day+1 to the CLOSE of day+h.

    Entry at the next open, never today's close: a feature computed from today's
    bar cannot trade today's close (Alpaca refuses `cls` after 15:50 ET).
    """
    out: dict[str, float] = {}
    for i, b in enumerate(bars):
        if i + h >= len(bars):
            break
        o = float(bars[i + 1].get("o") or 0.0)
        c = float(bars[i + h].get("c") or 0.0)
        if o > 0 and c > 0:
            out[str(b.get("t") or "")[:10]] = c / o - 1.0
    return out


def _blocks(days: list[str], h: int) -> int:
    """Non-overlapping h-session windows the observations actually span."""
    uniq = sorted(set(days))
    if not uniq:
        return 0
    n, last = 0, None
    for d in uniq:
        if last is None or (datetime.fromisoformat(d) - datetime.fromisoformat(last)).days >= h * 1.4:
            n += 1
            last = d
    return n


def _cell(vals: list[float], days: list[str], h: int) -> dict:
    if not vals:
        return {"n": 0, "n_blocks": 0, "mean": None, "median": None, "verdict": "empty"}
    nb = _blocks(days, h)
    mean = st.mean(vals)
    sd = st.pstdev(vals) if len(vals) > 1 else 0.0
    # MDE at 80% power, 5% two-sided, on the BLOCK count -- the honest n.
    mde = 2.8 * sd / math.sqrt(nb) if nb > 0 and sd > 0 else None
    # TERMINAL WEALTH, not the mean. Measured on CRSP over 32 years: 6-month
    # momentum top-5 held 5 days had a mean of +0.147% per window and a terminal
    # wealth of 0.1x -- the variance drag IS the result, and a cell ranked on its
    # mean recommends the book that loses. Compounded over non-overlapping
    # windows only, because compounding overlapping ones counts the same days
    # twenty times.
    # The cell as an EQUAL-WEIGHT PORTFOLIO of whatever it held in that window,
    # not one name plucked from it. A first cut compounded `sorted(zip(days,
    # vals))` and so picked the LOWEST value on each block-start day, which is a
    # portfolio of the cell's worst name and reported 0.01x on a cell whose mean
    # was +4.5%.
    per_day: dict[str, list[float]] = defaultdict(list)
    for d, v in zip(days, vals):
        per_day[d].append(v)
    wealth, last = 1.0, None
    for d in sorted(per_day):
        if last is None or (datetime.fromisoformat(d) - datetime.fromisoformat(last)).days >= h * 1.4:
            wealth *= (1.0 + st.mean(per_day[d]))
            last = d
    return {
        "n": len(vals), "n_blocks": nb,
        "mean": round(mean, 4), "median": round(st.median(vals), 4),
        "terminal_wealth_non_overlapping": round(wealth, 3),
        "sd": round(sd, 4),
        "share_positive": round(sum(1 for v in vals if v > 0) / len(vals), 3),
        "mde_at_80pct_power": round(mde, 4) if mde else None,
        "verdict": ("too few blocks to read" if nb < 3 else
                    "below its own MDE" if mde and abs(mean) < mde else "above its MDE"),
    }


# ------------------------------------------------------------------------- T6


def t6(rows: dict[str, list[dict]], bars: dict[str, list[dict]]) -> dict:
    bench = {h: forward(bars.get(BENCH) or [], h) for h in HORIZONS}
    have_rating = sum(1 for rs in rows.values() for r in rs if r.get("rating_counts_mean") is not None)
    total = sum(len(rs) for rs in rows.values())

    cells: dict[str, dict[int, tuple[list[float], list[str]]]] = defaultdict(
        lambda: {h: ([], []) for h in HORIZONS})
    for sym, rs in rows.items():
        if sym == BENCH:
            continue
        fwd = {h: forward(bars.get(sym) or [], h) for h in HORIZONS}
        for r in rs:
            day = r["day"]
            tr, dd = r.get("target_ratio"), r.get("drawdown_from_60d_high")
            if tr is None or dd is None:
                continue
            a = tr >= UPSIDE_BAR
            e = dd <= DRAWDOWN_BAR
            name = ("a_and_e" if (a and e) else "a_only" if a else "e_only" if e else "neither")
            for h in HORIZONS:
                if day in fwd[h] and day in bench[h]:
                    cells[name][h][0].append(fwd[h][day] - bench[h][day])
                    cells[name][h][1].append(day)

    out = {
        "test": "T6 -- Murat's rule cells, SPY-relative",
        "conditions": {
            "(a) target/price >= 1.5": "TESTED -- PIT from dated broker notes",
            "(b) rating >= 4.1": (f"UNAVAILABLE: non-null on {have_rating} of {total} symbol-days. "
                                  "`analyst_panel` records FORWARD from 2026-08-26; using today's "
                                  "rating on a 2025 date is the lookahead it exists to prevent."),
            "(e) drawdown <= -20%": "TESTED -- from bars",
            "(c) sector fit / (d) dated catalyst": "not cells here; (c) is a filter, (d) is T5",
        },
        "cells": {name: {f"fwd_{h}d_rel": _cell(v[h][0], v[h][1], h) for h in HORIZONS}
                  for name, v in sorted(cells.items())},
    }
    # The null IS the leave-one-out cell: a_and_e against a_only and e_only.
    reads = []
    for h in HORIZONS:
        both = cells["a_and_e"][h][0]
        if not both:
            continue
        b = _cell(both, cells["a_and_e"][h][1], h)
        for alt in ("a_only", "e_only", "neither"):
            o = _cell(cells[alt][h][0], cells[alt][h][1], h)
            if b["mean"] is None or o["mean"] is None:
                continue
            reads.append(f"{h}d: a_and_e {b['mean']:+.2%} (n={b['n']}, blocks={b['n_blocks']}) "
                         f"vs {alt} {o['mean']:+.2%} -> diff {b['mean'] - o['mean']:+.2%}")
    out["leave_one_out"] = reads
    return out


# ------------------------------------------------------------------------- T3


def t3(rows: dict[str, list[dict]], bars: dict[str, list[dict]]) -> dict:
    syms = [s for s in rows if s != BENCH]
    driver_of, note = drivers.resolve(syms)
    members: dict[str, list[str]] = defaultdict(list)
    for s in syms:
        members[driver_of[s]].append(s)
    usable = {d: m for d, m in members.items()
              if len(m) >= T3_MIN_NAMES and d not in (drivers.UNCLASSIFIED, drivers.INDEX_DRIVER)
              and not d.startswith("murat_book")}

    bench = forward(bars.get(BENCH) or [], 21)
    fwd = {s: forward(bars.get(s) or [], 21) for s in syms}
    by_day: dict[str, dict[str, dict]] = defaultdict(dict)
    for s, rs in rows.items():
        for r in rs:
            by_day[r["day"]][s] = r

    picks = {"laggard": ([], []), "leader": ([], []), "others_mean": ([], [])}
    events = 0
    for day in sorted(by_day):
        for drv, mem in usable.items():
            present = [s for s in mem if s in by_day[day]]
            shocked = [s for s in present
                       if (by_day[day][s].get("attention_z") or -9) >= T3_SHOCK_Z
                       and (by_day[day][s].get("sentiment_lex_5d") or 0) >= 0]
            if len(shocked) < T3_MIN_NAMES:
                continue
            ranked = [(by_day[day][s].get("ret_20d"), s) for s in present
                      if by_day[day][s].get("ret_20d") is not None
                      and day in fwd.get(s, {}) and day in bench]
            if len(ranked) < T3_MIN_NAMES:
                continue
            ranked.sort()
            events += 1
            lag, lead = ranked[0][1], ranked[-1][1]
            picks["laggard"][0].append(fwd[lag][day] - bench[day])
            picks["laggard"][1].append(day)
            picks["leader"][0].append(fwd[lead][day] - bench[day])
            picks["leader"][1].append(day)
            others = [fwd[s][day] - bench[day] for _, s in ranked[1:-1]]
            if others:
                picks["others_mean"][0].append(st.mean(others))
                picks["others_mean"][1].append(day)

    return {
        "test": "T3 -- sector lead vs laggard after a shared attention shock, SPY-relative, 21d",
        "driver_taxonomy": note,
        "drivers_usable": {d: sorted(m) for d, m in sorted(usable.items())},
        "excluded_drivers": sorted(set(members) - set(usable)),
        "exclusion_reason": ("fewer than 3 names, or not a mechanism: UNCLASSIFIED is by "
                            "definition not a driver, index_beta is the market, and "
                            "murat_book is a list of picks"),
        "shock_rule": f"attention_z >= {T3_SHOCK_Z} and sentiment_lex_5d >= 0, "
                      f"for >= {T3_MIN_NAMES} names in one driver on one day",
        "n_events": events,
        "arms": {k: _cell(v[0], v[1], 21) for k, v in picks.items()},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t6", action="store_true")
    ap.add_argument("--t3", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    config.load_env()
    both = not (args.t6 or args.t3)

    rows, bars = load_panel()
    print(f"panel: {len(rows)} symbols, {sum(len(v) for v in rows.values())} symbol-days, "
          f"{len(bars)} bar series")
    out: dict = {"computed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "panel_symbols": len(rows),
                 "panel_symbol_days": sum(len(v) for v in rows.values())}

    if both or args.t6:
        out["t6"] = t6(rows, bars)
        r = out["t6"]
        print(f"\n{r['test']}")
        for k, v in r["conditions"].items():
            print(f"  {k:<38} {v}")
        print(f"\n  {'cell':<10}{'horizon':<9}{'n':>7}{'blocks':>8}{'mean':>9}{'median':>9}"
              f"{'wealth':>8}{'MDE':>9}  verdict")
        for name, hs in r["cells"].items():
            for h, c in hs.items():
                if not c["n"]:
                    continue
                print(f"  {name:<10}{h:<9}{c['n']:>7}{c['n_blocks']:>8}{c['mean']:>+9.2%}"
                      f"{c['median']:>+9.2%}{c['terminal_wealth_non_overlapping']:>8.2f}"
                      + (f"{c['mde_at_80pct_power']:>9.2%}" if c["mde_at_80pct_power"] else f"{'-':>9}")
                      + f"  {c['verdict']}")
        print("\n  LEAVE ONE OUT (the null is the rule minus a condition, not a coin):")
        for line in r["leave_one_out"]:
            print(f"    {line}")

    if both or args.t3:
        out["t3"] = t3(rows, bars)
        r = out["t3"]
        print(f"\n{r['test']}")
        print(f"  drivers usable: {list(r['drivers_usable'])}")
        print(f"  excluded: {r['excluded_drivers']}")
        print(f"    ({r['exclusion_reason']})")
        print(f"  shock rule: {r['shock_rule']}")
        print(f"  events: {r['n_events']}")
        if r["n_events"]:
            print(f"\n  {'arm':<14}{'n':>7}{'blocks':>8}{'mean':>9}{'median':>9}{'wealth':>8}"
                  f"{'MDE':>9}  verdict")
            for k, c in r["arms"].items():
                if not c["n"]:
                    continue
                print(f"  {k:<14}{c['n']:>7}{c['n_blocks']:>8}{c['mean']:>+9.2%}{c['median']:>+9.2%}"
                      f"{c['terminal_wealth_non_overlapping']:>8.2f}"
                      + (f"{c['mde_at_80pct_power']:>9.2%}" if c["mde_at_80pct_power"] else f"{'-':>9}")
                      + f"  {c['verdict']}")
        else:
            print("  NO EVENTS: the shock rule never fired on a driver with enough names. "
                  "That is a fact about coverage, not a verdict on the thesis.")

    dest = corpus.CORPUS / f"rule_cells_{datetime.now(timezone.utc).date().isoformat()}.json"
    dest.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nreceipt: {dest}")
    if args.json:
        print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
