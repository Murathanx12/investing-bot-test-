"""Close the learning loop: sealed decision -> execution outcome -> graded returns.

    python -m scripts.decision_writeback                          # today, this role
    python -m scripts.decision_writeback --day 2026-08-31 --role hack4
    python -m scripts.decision_writeback --grade                  # matured horizons

WHY THIS EXISTS (continuity checkpoint queue item 5, 2026-08-31)
================================================================
2026-08-31 produced the first live fills a sealed tracker book ever generated.
A fill that is never written back beside the DECISION that caused it teaches
nothing: the seal knows what the book wanted, the ledger knows what the runner
did, the broker knows the price it did it at -- and until this script, no
table held all three keyed the same way. This writes that table, append-only,
one row per (day, symbol, book), under `$AAT_LEDGER_DIR/decision_outcomes/`.

REFUSALS ARE ROWS, NOT ABSENCES
===============================
A sealed name the runner refused carries the refusal class and reason. A
sealed name the runner NEVER REACHED (pass crashed before it, symbol dropped
by the universe) is marked `never_reached` -- a different failure from a
recorded refusal, and the distinction is the whole lesson of the Finnhub 503
day. Grading covers EVERY sealed decision, filled or not: the forward return
of a refused name is the price of the refusal, which is the number the
opportunity-recall question (T15) needs and nobody was writing down.

IT JOINS, IT DOES NOT COLLECT
=============================
Assembly reads only what is already on the volume (the sealed book, the
ledger). It runs inside the account's container after the close -- agent_loop
wires it beside the autopsy -- because the ledger with the refusal rows lives
there. `--grade` makes the one network call (daily bars) to append matured
1/5/21/63/126/252-session close-to-close returns; an unreadable bar series is
recorded on the row, never invented.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from alpha import config, ledger
from alpha.brains import tracker_portfolio

log = logging.getLogger("writeback")

HORIZONS = (1, 5, 21, 63, 126, 252)

OUT_DIR = Path(os.getenv("AAT_LEDGER_DIR", Path(__file__).resolve().parent.parent / "state")) / "decision_outcomes"

# Ledger fields copied onto the execution block, when present on the row.
_EXEC_FIELDS = ("alpaca_order_id", "risk_fraction", "max_loss_usd", "instrument")
# Sealed-holding fields copied onto the decision row, when present.
#
# The last six are E1's stamp (`prediction_book.generator_stamp`): the per-name
# generator's verdict on a name the BOOK's selector chose. They travel here so
# the four populations -- held+claimed vs held+declined, each graded and
# ungraded -- fall out of this file as horizons mature, with no join to the
# sealed book required. A book sealed before 2026-09-02 carries none of them
# and simply contributes no rows to the split; absence is not False.
_SEAL_FIELDS = ("notional", "exp_return", "downside_5pct", "confidence", "rank_value", "sector",
                "numbers_source", "generator", "generator_claimed", "generator_score",
                "generator_rank", "generator_failed_clauses", "dissent")

#: The stamp fields repeated onto every GRADE row. A grade is the unit E1
#: actually averages, and requiring a reader to join it back to its decision row
#: to learn whether the generator agreed is how a population gets mis-counted.
_GRADE_STAMP = ("generator_claimed", "dissent")


def rows_for(rows: list[dict], *, day: str, role: str, brain: str = "tracker_portfolio") -> list[dict]:
    """The day's ledger rows for one role and one brain, oldest first."""
    out = []
    for r in rows:
        if (r.get("brain") == brain
                and (r.get("account_role") in (role, None))
                and str(r.get("ts_utc", ""))[:10] == day):
            out.append(r)
    return out


def _terminal(sym_rows: list[dict]) -> dict | None:
    """The row that settles a symbol's day: a submission outranks any refusal,
    and among equals the LAST row wins (later passes supersede earlier ones)."""
    submitted = [r for r in sym_rows if r.get("action") == "submitted"]
    if submitted:
        return submitted[-1]
    refused = [r for r in sym_rows if r.get("action") == "refused"]
    if refused:
        return refused[-1]
    return None


def assemble(sealed: dict, day_rows: list[dict]) -> list[dict]:
    """One decision row per sealed symbol. Pure -- no I/O, fully testable."""
    now = datetime.now(timezone.utc).isoformat()
    out = []
    for sym, h in sorted(sealed["holdings"].items()):
        term = _terminal([r for r in day_rows if r.get("symbol") == sym])
        if term is None:
            execution = {"action": "never_reached",
                         "note": "no ledger row for this sealed name today -- the runner "
                                 "never considered it, which is not a recorded refusal"}
        else:
            execution = {"action": term.get("action")}
            if term.get("refusal_reason"):
                execution["refusal_reason"] = term["refusal_reason"]
            for k in _EXEC_FIELDS:
                if term.get(k) is not None:
                    execution[k] = term[k]
        out.append({
            "type": "decision",
            "day": sealed["day"], "book": sealed["book"], "symbol": sym,
            "seal_sha": sealed.get("content_sha256"),
            "ranking": sealed.get("ranking"),
            "sealed": {k: h.get(k) for k in _SEAL_FIELDS if h.get(k) is not None},
            "execution": execution,
            "written_at_utc": now,
        })
    return out


def grade_rows(decisions: list[dict], closes_by_symbol: dict[str, list[tuple[str, float]]]) -> list[dict]:
    """Matured close-to-close returns for every sealed decision. Pure.

    `closes_by_symbol[sym]` is [(session_day, close), ...] ascending, and must
    INCLUDE the decision day itself -- the basis close. A horizon h matures
    when h further sessions exist after the basis. A symbol with no readable
    basis emits one `grade_unreadable` row instead of silence.
    """
    now = datetime.now(timezone.utc).isoformat()
    out = []
    for d in decisions:
        sym, day = d["symbol"], d["day"]
        series = closes_by_symbol.get(sym) or []
        idx = {s: i for i, (s, _) in enumerate(series)}
        if day not in idx:
            out.append({"type": "grade_unreadable", "day": day, "book": d["book"], "symbol": sym,
                        "note": f"no close for the decision day among {len(series)} bars",
                        "written_at_utc": now})
            continue
        i0 = idx[day]
        basis = series[i0][1]
        # E1's stamp, carried from the sealed holding onto every grade of it.
        # `.get` twice over: a decision row written before the stamp existed has
        # no `sealed` key for it, and the field is then absent rather than False.
        stamp = {k: (d.get("sealed") or {})[k]
                 for k in _GRADE_STAMP if k in (d.get("sealed") or {})}
        for h in HORIZONS:
            j = i0 + h
            if j >= len(series):
                break  # not matured yet; later runs append it
            then_day, close = series[j]
            out.append({"type": "grade", "day": day, "book": d["book"], "symbol": sym,
                        "horizon_sessions": h, "basis_close": basis,
                        "graded_day": then_day, "graded_close": close,
                        "ret": (close / basis) - 1.0 if basis else None,
                        "executed": d["execution"]["action"] in ("submitted", "filled"),
                        **stamp,
                        "written_at_utc": now})
    return out


def _key(row: dict) -> tuple:
    return (row.get("type"), row.get("day"), row.get("book"), row.get("symbol"),
            row.get("horizon_sessions"))


def append_missing(path: Path, rows: list[dict]) -> int:
    """Append only rows whose key is not already on the file. Append-only:
    an existing row is never rewritten, even if the new assembly differs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    have = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                have.add(_key(json.loads(line)))
    fresh = [r for r in rows if _key(r) not in have]
    if fresh:
        with path.open("a", encoding="utf-8") as f:
            for r in fresh:
                f.write(json.dumps(r, sort_keys=True) + "\n")
    return len(fresh)


def _out_path(day: str, book: str) -> Path:
    return OUT_DIR / f"{day}_{book}.jsonl"


def _read_decisions(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip() and json.loads(l).get("type") == "decision"]


def _closes(client, symbols: list[str], start_day: str) -> dict[str, list[tuple[str, float]]]:
    out: dict[str, list[tuple[str, float]]] = {}
    for sym in symbols:
        try:
            resp = client.stock_bars(sym, start=start_day, timeframe="1Day")
            bars = (resp.get("bars") or {}).get(sym) or []
            out[sym] = [(str(b["t"])[:10], float(b["c"])) for b in bars if b.get("c")]
        except Exception as exc:  # a rate limit reads as absence -- record it instead
            log.warning("%s: bars unreadable (%s) -- grade rows will say so", sym, exc)
            out[sym] = []
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--role", default=None, help="account role (default: AAT_ACCOUNT_ROLE)")
    p.add_argument("--day", default=None, help="session day YYYY-MM-DD (default: today)")
    p.add_argument("--grade", action="store_true",
                   help="also fetch bars and append matured horizon grades for every "
                        "decision_outcomes file of this role")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config.load_env()
    role = (args.role or os.getenv("AAT_ACCOUNT_ROLE", "")).strip().lower()
    if not role:
        print("decision_writeback: no role -- set AAT_ACCOUNT_ROLE or pass --role", file=sys.stderr)
        return 2

    # -- assemble today's rows ------------------------------------------------
    try:
        sealed = tracker_portfolio.sealed_holdings(args.day, book=role)
    except tracker_portfolio.PortfolioDeclined as exc:
        # Not an error: a role with no sealed book that day has nothing to
        # write back. Said out loud, exit 0 so the loop's step stays green.
        print(f"decision_writeback: nothing to write for {role}: {exc}")
        sealed = None
    wrote = 0
    if sealed is not None:
        day_rows = rows_for(ledger.read_all(), day=sealed["day"], role=role)
        rows = assemble(sealed, day_rows)
        path = _out_path(sealed["day"], sealed["book"])
        wrote = append_missing(path, rows)
        acted = sum(1 for r in rows if r["execution"]["action"] == "submitted")
        refused = sum(1 for r in rows if r["execution"]["action"] == "refused")
        never = sum(1 for r in rows if r["execution"]["action"] == "never_reached")
        dissent = sum(1 for r in rows if (r["sealed"].get("dissent") is True))
        unstamped = sum(1 for r in rows if "generator_claimed" not in r["sealed"])
        print(f"decision_writeback: {sealed['day']} {sealed['book']} -- "
              f"{len(rows)} sealed decisions (submitted={acted} refused={refused} "
              f"never_reached={never}), {wrote} new rows -> {path}")
        print(f"decision_writeback: E1 dissent -- {dissent} of {len(rows)} held names were "
              f"DECLINED by the generator; {unstamped} carry no verdict "
              f"({'sealed before the stamp existed' if unstamped else 'all stamped'})")

    # -- grade matured horizons ----------------------------------------------
    if args.grade:
        from alpha.broker.alpaca import AlpacaPaper
        client = AlpacaPaper(role=role)
        graded = 0
        for path in sorted(OUT_DIR.glob(f"*_{role}.jsonl")):
            decisions = _read_decisions(path)
            if not decisions:
                continue
            day = decisions[0]["day"]
            closes = _closes(client, sorted({d["symbol"] for d in decisions}), day)
            graded += append_missing(path, grade_rows(decisions, closes))
        print(f"decision_writeback: {graded} new grade rows for {role}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
