"""VARIANT GRADE -- the tournament, accruing one session at a time.

    python -m scripts.variant_grade                 # grade every gradeable day
    python -m scripts.variant_grade --day 2026-09-02
    python -m scripts.variant_grade --standings     # the table, no new grading
    python -m scripts.variant_grade --dry-run

WHAT IT GRADES
==============
Every shadow variant book in `state/variant_books/<day>/`, every sealed paper
book (hack3 / hack4 / hack6) for the same day, and every rung of the leverage
ladder on each of them. One row per (day, book, arm) appended to
`state/variant_books/grades.jsonl`.

THE CONVENTION, WRITTEN DOWN BECAUSE A GRADE WITHOUT ONE IS A NUMBER
====================================================================
A book for day D is sealed BEFORE D's open. So:

    intraday        open(D)  -> close(D)     flat at the close
    overnight_hold  open(D)  -> open(D+1)    entered at the open, held out
    gap             close(D) -> open(D+1)    diagnostic; what intraday skips

Entry is the OPEN, never the prior close: a book sealed pre-open cannot
transact at a price that has already happened. `overnight_hold` is therefore
NOT gradeable on day D -- it needs D+1's open -- and it is recorded as PENDING
and filled on a later run rather than silently omitted. A leg that is missing
because tomorrow has not happened and a leg that is missing because the data
failed are different facts, and only one of them is a bug.

Every leg is also recorded SPY-relative, because the competition ranks P&L and
the honest question about a five-day book is whether it beat holding the index.

IDEMPOTENT. The append key is (day, book, arm, leg). A row already on the file
with a non-null value is never rewritten, so this can be run after every close,
twice, or on a backfill, without inventing sessions. Re-running is how PENDING
legs get filled.

READ-ONLY toward everything else. It reads variant books, sealed books and
daily bars, and appends to its own file. No broker module is imported, nothing
is sized and nothing is ordered.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alpha import config                                   # noqa: E402
from alpha import lab                                      # noqa: E402
from scripts import leverage_lab as LL                     # noqa: E402
from scripts import portfolio_variants as PV               # noqa: E402

GRADES = PV.OUT / "grades.jsonl"
BENCH = LL.BENCH

#: The three legs, and which price pair each one is.
LEGS = ("intraday", "overnight_hold", "gap")

SEALED_BOOKS = ("hack3", "hack4", "hack6")


# --------------------------------------------------------------------------
# The legs
# --------------------------------------------------------------------------

def _weights(panel: lab.Panel, holdings: list[dict]) -> tuple[np.ndarray, list[str]]:
    w = np.zeros(panel.n_symbols)
    missing = []
    for h in holdings:
        s = h["symbol"]
        if s in panel.symbols:
            w[panel.symbols.index(s)] = float(h["notional"])
        else:
            missing.append(s)
    return w, missing


def _dot(panel: lab.Panel, w: np.ndarray, a: np.ndarray, b: np.ndarray) -> float | None:
    ok = np.isfinite(a) & np.isfinite(b) & (a > 0) & (w != 0)
    if not ok.any():
        return None
    r = np.zeros_like(w)
    r[ok] = b[ok] / a[ok] - 1.0
    # A name with no readable price is DROPPED, not redistributed: the book
    # held nothing there, and re-normalising the rest would invent a position.
    return float(np.sum(w * r))


def raw_legs(panel: lab.Panel, w: np.ndarray, day: str) -> dict[str, float | None]:
    """The three legs for `day`, or None where the bar does not exist yet."""
    if day not in panel.dates:
        return {k: None for k in LEGS}
    i = panel.dates.index(day)
    nxt = i + 1 if i + 1 < panel.n_dates else None
    return {
        "intraday": _dot(panel, w, panel.open_[i], panel.close[i]),
        "overnight_hold": (None if nxt is None
                           else _dot(panel, w, panel.open_[i], panel.open_[nxt])),
        "gap": (None if nxt is None
                else _dot(panel, w, panel.close[i], panel.open_[nxt])),
    }


def _bench_weights(panel: lab.Panel) -> np.ndarray:
    w = np.zeros(panel.n_symbols)
    if BENCH in panel.symbols:
        w[panel.symbols.index(BENCH)] = 1.0
    return w


# --------------------------------------------------------------------------
# Books to grade
# --------------------------------------------------------------------------

def variant_books(day: str) -> dict[str, dict]:
    d = PV.OUT / day
    out = {}
    if not d.exists():
        return out
    for p in sorted(d.glob("*.json")):
        if p.name == "receipt.json":
            continue
        try:
            b = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        out[b.get("variant") or p.stem] = {
            "holdings": b["holdings"], "source": "variant",
            "n_selected": b["n_selected"],
            "max_notional_each": b["max_notional_each"],
            "derived_gross": b["derived_gross"], "sha256": None}
    return out


def sealed_books(day: str) -> dict[str, dict]:
    out = {}
    for book in SEALED_BOOKS:
        try:
            b = LL.sealed_book(day, book)
        except SystemExit:
            continue
        if not b["holdings"]:
            # An EMPTY sealed book is a valid decision, and it is graded as a
            # zero-return session rather than dropped -- otherwise a book that
            # correctly refuses to trade disappears from its own tournament.
            out[f"SEALED_{book}"] = {
                "holdings": [], "source": "sealed", "n_selected": 0,
                "max_notional_each": b["max_notional_each"],
                "derived_gross": 0.0, "sha256": b["content_sha256"],
                "empty_book": True}
            continue
        out[f"SEALED_{book}"] = {
            "holdings": b["holdings"], "source": "sealed",
            "n_selected": b["n_selected"],
            "max_notional_each": b["max_notional_each"],
            "derived_gross": round(sum(h["notional"] for h in b["holdings"]), 4),
            "sha256": b["content_sha256"], "empty_book": False}
    return out


def gradeable_days(day: str | None) -> list[str]:
    if day:
        return [day]
    days = sorted(p.name for p in PV.OUT.glob("2026-*") if p.is_dir())
    seals = sorted(p.stem for p in (ROOT / "state" / "predictions").glob("2026-*.json")
                   if "resealed" not in p.name)
    return sorted(set(days) | set(seals))


# --------------------------------------------------------------------------
# Grading one day
# --------------------------------------------------------------------------

def grade_day(day: str, *, cost_bps: float, margin_rate: float,
              sessions_back: int = 12) -> list[dict]:
    books = {**variant_books(day), **sealed_books(day)}
    if not books:
        return []
    symbols = sorted({h["symbol"] for b in books.values() for h in b["holdings"]})
    panel = LL._panel(symbols, sessions=sessions_back, end=None)
    bw = _bench_weights(panel)
    bench = raw_legs(panel, bw, day)

    stamp = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []
    for name, b in books.items():
        w, missing = _weights(panel, b["holdings"])
        legs = raw_legs(panel, w, day) if b["holdings"] else {k: 0.0 for k in LEGS}
        gross_1x = float(np.sum(np.abs(w)))
        for L in LL.LADDER:
            for regime, leg_name in (("intraday", "intraday"),
                                     ("overnight", "overnight_hold")):
                permitted = (regime != "overnight"
                             or L <= LL.OVERNIGHT_BUYING_POWER + 1e-9)
                gross = gross_1x * L
                raw = legs[leg_name]
                net = (LL.levered_session(raw, regime=regime, gross=gross, scale=L,
                                          cost_bps=cost_bps, margin_rate=margin_rate,
                                          charge_round_trip=True)
                       if permitted else None)
                braw = bench[leg_name]
                rows.append({
                    "day": day,
                    "book": name,
                    "arm": f"{regime}_{L:.1f}x",
                    "leg": leg_name,
                    "source": b["source"],
                    "sha256": b["sha256"],
                    "n_holdings": b["n_selected"],
                    "gross_of_equity": round(gross, 4),
                    "multiplier": L,
                    "regime": regime,
                    "permitted": permitted,
                    "raw_return": (None if raw is None else round(raw, 6)),
                    "net_return": (None if net is None else round(net, 6)),
                    "spy_return": (None if braw is None else round(braw, 6)),
                    "excess_vs_spy": (None if (net is None or braw is None)
                                      else round(net - braw * L, 6)),
                    "excess_basis": ("net book return minus L x SPY over the SAME leg. The "
                                     "benchmark is levered TOO: comparing a 4x book to a 1x "
                                     "index credits leverage with alpha."),
                    "status": ("REFUSED_OVERNIGHT_BOUND" if not permitted
                               else "GRADED" if net is not None
                               else "PENDING" if raw is None and leg_name != "intraday"
                               else "NO_BARS"),
                    "missing_bars": missing,
                    "cost_bps_one_way": cost_bps,
                    "margin_rate": margin_rate,
                    "convention": ("intraday = open(D)->close(D); overnight_hold = "
                                   "open(D)->open(D+1). Entry is the OPEN, never the prior "
                                   "close: a book sealed pre-open cannot transact at a price "
                                   "that has already happened."),
                    "graded_at_utc": stamp,
                })
        rows.append({
            "day": day, "book": name, "arm": "diagnostic", "leg": "gap",
            "source": b["source"], "sha256": b["sha256"],
            "n_holdings": b["n_selected"], "gross_of_equity": round(gross_1x, 4),
            "multiplier": 1.0, "regime": "diagnostic", "permitted": True,
            "raw_return": (None if legs["gap"] is None else round(legs["gap"], 6)),
            "net_return": (None if legs["gap"] is None else round(legs["gap"], 6)),
            "spy_return": (None if bench["gap"] is None else round(bench["gap"], 6)),
            "excess_vs_spy": (None if (legs["gap"] is None or bench["gap"] is None)
                              else round(legs["gap"] - bench["gap"], 6)),
            "excess_basis": "close(D) -> open(D+1). What the intraday arm never holds.",
            "status": "GRADED" if legs["gap"] is not None else "PENDING",
            "missing_bars": missing, "cost_bps_one_way": 0.0, "margin_rate": 0.0,
            "convention": "gap leg, gross costs excluded -- it is a diagnostic, not a book.",
            "graded_at_utc": stamp,
        })
    return rows


# --------------------------------------------------------------------------
# The append-only file
# --------------------------------------------------------------------------

def existing_keys() -> set[tuple]:
    """(day, book, arm, leg) already on the file WITH a value. PENDING rows are
    NOT counted, so a re-run fills them instead of duplicating a blank."""
    got: set[tuple] = set()
    if not GRADES.exists():
        return got
    for line in GRADES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("net_return") is not None or r.get("status") == "REFUSED_OVERNIGHT_BOUND":
            got.add((r.get("day"), r.get("book"), r.get("arm"), r.get("leg")))
    return got


def append(rows: list[dict]) -> int:
    have = existing_keys()
    fresh = [r for r in rows
             if (r["day"], r["book"], r["arm"], r["leg"]) not in have
             and r["status"] in ("GRADED", "REFUSED_OVERNIGHT_BOUND")]
    if not fresh:
        return 0
    GRADES.parent.mkdir(parents=True, exist_ok=True)
    with GRADES.open("a", encoding="utf-8") as fh:
        for r in fresh:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(fresh)


def standings() -> dict:
    """Compound each (book, arm) over the sessions it has been graded on.

    TERMINAL WEALTH, not the mean. A book with a positive mean and a negative
    compounded path is a losing book, and ranking on the mean is how one came
    back at 0.1x terminal wealth with a +0.147%/window average (S17).
    """
    if not GRADES.exists():
        return {"n_rows": 0, "books": {}}
    rows = []
    for line in GRADES.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    agg: dict[tuple, dict] = {}
    for r in rows:
        if r.get("net_return") is None or r.get("regime") == "diagnostic":
            continue
        key = (r["book"], r["arm"])
        a = agg.setdefault(key, {"wealth": 1.0, "n": 0, "days": [],
                                 "excess_sum": 0.0, "worst": 0.0})
        a["wealth"] *= (1.0 + r["net_return"])
        a["n"] += 1
        a["days"].append(r["day"])
        a["worst"] = min(a["worst"], r["net_return"])
        if r.get("excess_vs_spy") is not None:
            a["excess_sum"] += r["excess_vs_spy"]
    out = {f"{b}|{arm}": {"book": b, "arm": arm, "n_sessions": v["n"],
                          "terminal_wealth": round(v["wealth"], 6),
                          "total_return": round(v["wealth"] - 1.0, 6),
                          "sum_excess_vs_levered_spy": round(v["excess_sum"], 6),
                          "worst_session": round(v["worst"], 6),
                          "days": sorted(set(v["days"]))}
           for (b, arm), v in agg.items()}
    return {"n_rows": len(rows), "books": out}


def _print_standings(s: dict, *, arm: str | None = None) -> None:
    books = s["books"]
    if not books:
        print("no graded rows yet")
        return
    rows = [v for v in books.values() if arm is None or v["arm"] == arm]
    rows.sort(key=lambda v: -v["terminal_wealth"])
    n = max((v["n_sessions"] for v in rows), default=0)
    print(f"\nSTANDINGS  ({len(rows)} book-arms, max {n} graded session(s))")
    if n < 5:
        print(f"  n = {n}. This is a RECORD, not a ranking: at this length the ordering is "
              "a draw from the market, and the top row is a maximum of many draws.")
    print(f"  {'book':<18} {'arm':<18} {'n':>3} {'wealth':>9} {'total':>9} "
          f"{'vs levered SPY':>15} {'worst':>8}")
    for v in rows[:40]:
        print(f"  {v['book']:<18} {v['arm']:<18} {v['n_sessions']:>3} "
              f"{v['terminal_wealth']:>9.4f} {v['total_return']:>9.2%} "
              f"{v['sum_excess_vs_levered_spy']:>15.2%} {v['worst_session']:>8.2%}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--day", help="one day; default every day with books on disk")
    ap.add_argument("--cost-bps", type=float, default=lab.EQUITY_BPS)
    ap.add_argument("--margin-rate", type=float, default=LL.MARGIN_RATE)
    ap.add_argument("--standings", action="store_true", help="print the table, grade nothing")
    ap.add_argument("--arm", help="restrict the standings to one arm, e.g. intraday_1.0x")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    config.load_env()
    if args.standings:
        _print_standings(standings(), arm=args.arm)
        return 0

    total = 0
    for day in gradeable_days(args.day):
        rows = grade_day(day, cost_bps=args.cost_bps, margin_rate=args.margin_rate)
        if not rows:
            continue
        graded = sum(1 for r in rows if r["status"] == "GRADED")
        pending = sum(1 for r in rows if r["status"] == "PENDING")
        print(f"{day}: {len(rows)} rows  graded {graded}  pending {pending} "
              f"(waiting on the next open)")
        if not args.dry_run:
            total += append(rows)
    print(f"\nappended {total} new grade rows -> {GRADES}")
    _print_standings(standings(), arm=args.arm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
