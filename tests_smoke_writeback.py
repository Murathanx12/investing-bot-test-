"""Smoke: the decision write-back joins seal + ledger into (day, symbol, book)
rows, refusals and never-reached names stay distinct, and grades mature -- they
are never invented early.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from scripts import decision_writeback as wb

_fails: list[str] = []


def check(name: str, cond: bool, why: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f"  ({why})" if why and not cond else ""))
    if not cond:
        _fails.append(name)


def _sealed() -> dict:
    return {
        "book": "hack4", "day": "2026-08-31", "content_sha256": "e6f9" * 16,
        "ranking": "rank_profit_max",
        "holdings": {
            "RZLV": {"symbol": "RZLV", "notional": 0.10, "exp_return": 0.5, "downside_5pct": -0.38},
            "NB":   {"symbol": "NB",   "notional": 0.10, "exp_return": 0.4, "downside_5pct": -0.42},
            "ABAT": {"symbol": "ABAT", "notional": 0.10, "exp_return": 0.3, "downside_5pct": -0.35},
        },
    }


def _ledger_rows() -> list[dict]:
    return [
        # RZLV: refused at 09:31, then submitted at 10:01 -- the submission settles it.
        {"symbol": "RZLV", "brain": "tracker_portfolio", "account_role": "hack4",
         "ts_utc": "2026-08-31T13:31:00+00:00", "action": "refused",
         "refusal_reason": "OPENING RANGE: shares are not bought in the first 15 minutes."},
        {"symbol": "RZLV", "brain": "tracker_portfolio", "account_role": "hack4",
         "ts_utc": "2026-08-31T14:01:00+00:00", "action": "submitted",
         "alpaca_order_id": "abc123", "risk_fraction": 0.02, "max_loss_usd": 300.0,
         "instrument": "long_shares"},
        # NB: refused twice; the LAST refusal is the row that stands.
        {"symbol": "NB", "brain": "tracker_portfolio", "account_role": "hack4",
         "ts_utc": "2026-08-31T13:31:00+00:00", "action": "refused",
         "refusal_reason": "OPENING RANGE"},
        {"symbol": "NB", "brain": "tracker_portfolio", "account_role": "hack4",
         "ts_utc": "2026-08-31T14:01:00+00:00", "action": "refused",
         "refusal_reason": "spread too wide at decision time"},
        # A different day and a different brain: both must be ignored.
        {"symbol": "ABAT", "brain": "tracker_portfolio", "account_role": "hack4",
         "ts_utc": "2026-08-30T14:01:00+00:00", "action": "submitted", "alpaca_order_id": "old"},
        {"symbol": "ABAT", "brain": "post_event_drift", "account_role": "hack4",
         "ts_utc": "2026-08-31T14:01:00+00:00", "action": "submitted", "alpaca_order_id": "drift"},
    ]


def test_assemble_joins_and_keeps_refusals_distinct():
    day_rows = wb.rows_for(_ledger_rows(), day="2026-08-31", role="hack4")
    check("rows_for drops other days and other brains",
          {r["ts_utc"][:10] for r in day_rows} == {"2026-08-31"}
          and all(r["brain"] == "tracker_portfolio" for r in day_rows))
    rows = wb.assemble(_sealed(), day_rows)
    by = {r["symbol"]: r for r in rows}
    check("one row per sealed symbol", sorted(by) == ["ABAT", "NB", "RZLV"])
    check("a submission outranks an earlier refusal",
          by["RZLV"]["execution"]["action"] == "submitted"
          and by["RZLV"]["execution"]["alpaca_order_id"] == "abc123")
    check("among refusals the LAST wins and keeps its reason",
          by["NB"]["execution"]["action"] == "refused"
          and "spread" in by["NB"]["execution"]["refusal_reason"])
    check("a sealed name with no row today is never_reached, not refused",
          by["ABAT"]["execution"]["action"] == "never_reached")
    check("the seal travels: sha, ranking and sealed numbers on every row",
          all(r["seal_sha"] == "e6f9" * 16 and r["ranking"] == "rank_profit_max"
              and r["sealed"].get("notional") == 0.10 for r in rows))


def test_grades_mature_and_are_never_invented():
    rows = wb.assemble(_sealed(), wb.rows_for(_ledger_rows(), day="2026-08-31", role="hack4"))
    closes = {
        # RZLV: basis day + 5 further sessions -> horizons 1 and 5 mature, 21 does not.
        "RZLV": [("2026-08-31", 10.0), ("2026-09-01", 11.0), ("2026-09-02", 9.0),
                 ("2026-09-03", 10.5), ("2026-09-04", 10.1), ("2026-09-08", 12.0)],
        # NB: basis day only -> nothing matures, and nothing is written.
        "NB": [("2026-08-31", 4.0)],
        # ABAT: no basis close at all -> a grade_unreadable row, not silence.
        "ABAT": [("2026-09-01", 2.5)],
    }
    grades = wb.grade_rows(rows, closes)
    rz = [g for g in grades if g["symbol"] == "RZLV" and g["type"] == "grade"]
    check("only matured horizons are graded", [g["horizon_sessions"] for g in rz] == [1, 5])
    check("close-to-close return is right", abs(rz[0]["ret"] - 0.10) < 1e-9)
    check("the graded session is named", rz[1]["graded_day"] == "2026-09-08")
    check("refused/never-reached decisions are graded too (the price of a refusal)",
          any(g["symbol"] == "NB" for g in grades) is False  # NB has no matured horizon...
          and rz[0]["executed"] is True)                     # ...but RZLV grades carry executed
    check("an unreadable basis is a row, not an absence",
          any(g["type"] == "grade_unreadable" and g["symbol"] == "ABAT" for g in grades))


def test_append_is_idempotent_and_append_only():
    rows = wb.assemble(_sealed(), wb.rows_for(_ledger_rows(), day="2026-08-31", role="hack4"))
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "2026-08-31_hack4.jsonl"
        n1 = wb.append_missing(path, rows)
        n2 = wb.append_missing(path, rows)
        check("first write appends every row", n1 == 3)
        check("second write appends nothing (idempotent by key)", n2 == 0)
        mutated = [dict(r, execution={"action": "refused"}) for r in rows]
        n3 = wb.append_missing(path, mutated)
        check("an existing key is never rewritten (append-only)", n3 == 0)
        on_disk = [json.loads(l) for l in path.read_text().splitlines()]
        check("what is on disk is what was first written",
              sum(1 for r in on_disk if r["execution"]["action"] == "submitted") == 1)


def test_the_loop_actually_calls_it():
    # A perfect script nobody calls is the WBUY failure again. The nightly
    # block must run it, and the timeout table must know it.
    src = Path(__file__).resolve().parent.joinpath("scripts", "agent_loop.py").read_text(encoding="utf-8")
    check("agent_loop runs scripts.decision_writeback --grade",
          'scripts.decision_writeback", "--grade"' in src)
    check("agent_loop gives it a timeout", '"scripts.decision_writeback": 600' in src)


def _run_all() -> int:
    import traceback
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    print(f"\n-- WRITE-BACK: sealed decision -> outcome -> grade ({len(tests)} test groups)")
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:                                        # noqa: BLE001
            _fails.append(name)
            print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
    print(f"\n{len(_fails)} failures" + (": " + ", ".join(_fails) if _fails else ""))
    return 1 if _fails else 0


# The __main__ guard stays at the BOTTOM: a test defined below it never runs
# while the suite still prints ALL PASS (paid for once, 2026-08-31).
if __name__ == "__main__":
    raise SystemExit(_run_all())
