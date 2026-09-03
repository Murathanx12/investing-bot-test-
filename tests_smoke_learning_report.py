"""The daily learning report: one page, derived or refused, every number in a receipt.

Run: python tests_smoke_learning_report.py  (via `python run_tests.py` -- never bare)

OFFLINE BY CONSTRUCTION: every function under test is pure over synthesized
inputs, or reads files from a tmp dir this file creates. No broker object is
ever constructed. Dates are DERIVED FROM TODAY -- a literal calendar moment in
a fixture is a test that rots the day after it passes (session-start protocol
rule 5), and this suite must be as green in November as it is now.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha.exits import ET_OFFSET
from scripts import daily_learning_report as dlr

# Dates derived from today: D2 is "the report day", D1 the session before it,
# D0 one earlier still. Weekday-ness is irrelevant -- these functions take the
# calendar/files as given and never consult a wall clock of their own.
TODAY = date.today()
D2 = (TODAY - timedelta(days=2)).isoformat()
D1 = (TODAY - timedelta(days=3)).isoformat()
D0 = (TODAY - timedelta(days=4)).isoformat()


def utc_at_et(day: str, hm: str) -> datetime:
    """A UTC instant whose ET wall-clock reading is `day hm`, by the repo's own
    ET_OFFSET convention -- the same arithmetic the code under test uses."""
    return (datetime.fromisoformat(f"{day}T{hm}:00").replace(tzinfo=timezone.utc)
            - ET_OFFSET)


print("\n-- the day is the venue calendar's, and 'completed' means the CLOSE is past")
CAL = [{"date": D1, "open": "09:30", "close": "16:00"},
       {"date": D2, "open": "09:30", "close": "16:00"}]
check("after the close, the day itself is the answer",
      dlr.most_recent_completed_session(utc_at_et(D2, "16:01"), CAL) == D2)
check("mid-session, the answer is the PRIOR session -- today is not completed",
      dlr.most_recent_completed_session(utc_at_et(D2, "12:00"), CAL) == D1)
check("before any listed close, the answer is None (refuse, never guess)",
      dlr.most_recent_completed_session(utc_at_et(D1, "09:00"), CAL) is None)
HALF = [{"date": D2, "open": "09:30", "close": "13:00"}]
check("a 13:00 half-day close counts at 13:01, where a hardcoded 16:00 would not",
      dlr.most_recent_completed_session(utc_at_et(D2, "13:01"), HALF) == D2)
check("junk calendar rows are skipped, not fatal",
      dlr.most_recent_completed_session(utc_at_et(D2, "17:00"),
                                        [{"date": "not-a-date"}] + CAL) == D2)

print("\n-- the SPY window follows the benchmark_regret receipt's convention")
BARS = [{"t": f"{d}T04:00:00Z", "c": c}
        for d, c in ((D0, 100.0), (D1, 102.0), (D2, 101.0))]
w = dlr.spy_window(BARS, genesis_day=D1, day=D2)
check("start is the first bar ON/AFTER genesis, not before it",
      w["start_date"] == D1 and w["start_close"] == 102.0, str(w))
check("window return is end/start - 1",
      abs(w["return_pct"] - round((101.0 / 102.0 - 1) * 100, 3)) < 1e-9, str(w.get("return_pct")))
check("the day's own return uses the PRIOR bar",
      abs(w["day_return_pct"] - round((101.0 / 102.0 - 1) * 100, 3)) < 1e-9)
w2 = dlr.spy_window(BARS[:2], genesis_day=D1, day=D2)
check("no bar FOR the day -> CANNOT DETERMINE, with the day named",
      w2["status"] == dlr.CANNOT and D2 in w2["why"], str(w2))

print("\n-- scoreboard: every underivable number says so by name")
HIST = {D1: 100000.0, D2: 99000.0}
GEN = {"starting_equity": 100000.0}
SPY_OK = {"status": "ok", "return_pct": 0.5}
row = dlr.scoreboard_row("hack9", GEN, HIST, D2, SPY_OK)
check("day P&L is equity minus the prior session's equity",
      row["day_pnl_usd"] == -1000.0, str(row.get("day_pnl_usd")))
check("P&L vs genesis in dollars and percent",
      row["pnl_vs_genesis_usd"] == -1000.0 and row["pnl_vs_genesis_pct"] == -1.0)
check("benchmark regret = own return minus SPY's, in pp",
      row["benchmark_regret_pp"] == -1.5, str(row.get("benchmark_regret_pp")))
row2 = dlr.scoreboard_row("hack9", GEN, {D1: 100000.0}, D2, SPY_OK)
check("a day absent from portfolio history is CANNOT DETERMINE, day named",
      row2["status"] == dlr.CANNOT and D2 in row2["why"], str(row2))
row3 = dlr.scoreboard_row("hack9", None, HIST, D2, SPY_OK)
check("no genesis file -> the genesis columns refuse and NAME the missing file",
      row3["pnl_vs_genesis_usd"] is None and "genesis_hack9" in row3["pnl_vs_genesis_why"])
row4 = dlr.scoreboard_row("hack9", GEN, HIST, D2, {"status": dlr.CANNOT, "why": "x"})
check("a broken SPY window refuses the regret column only, not the whole row",
      row4["status"] == "ok" and row4["benchmark_regret_pp"] is None)

print("\n-- books vs fills: the seal is intent, the venue's orders are fact")
PORT = {"n_selected": 2, "holdings": [{"symbol": "AAA"}, {"symbol": "BBB"}]}
ORDERS = [
    {"symbol": "AAA", "side": "buy", "status": "filled", "order_type": "market",
     "filled_at": f"{D2}T14:00:00Z", "submitted_at": f"{D2}T13:55:00Z"},
    {"symbol": "BBB", "side": "buy", "status": "expired", "order_type": "limit",
     "submitted_at": f"{D2}T13:55:00Z"},
    {"symbol": "CCC", "side": "sell", "status": "filled", "order_type": "stop",
     "filled_at": f"{D2}T15:00:00Z", "submitted_at": f"{D1}T14:00:00Z"},
    {"symbol": "DDD", "side": "buy", "status": "filled", "order_type": "market",
     "filled_at": f"{D1}T14:00:00Z", "submitted_at": f"{D1}T13:00:00Z"},
]
b = dlr.books_vs_fills(PORT, ORDERS, D2)
check("sealed names that filled are counted AND named",
      b["sealed_filled"] == ["AAA"] and b["admitted"] == 2, str(b["sealed_filled"]))
check("sealed names that did not fill are named, not netted away",
      b["sealed_unfilled"] == ["BBB"])
check("an expired order is expired, not silently absent", b["expired"] == ["BBB"])
check("a filled stop-sell is a stop-out", b["stopped"] == ["CCC"])
check("fills outside the seal are surfaced", b["off_book_fills"] == ["CCC"])
check("another day's fill is another day's fact",
      "DDD" not in b["filled_buys"], str(b["filled_buys"]))
# The four-hour trap: 00:05 UTC is 20:05 ET the PREVIOUS calendar day.
late = [{"symbol": "EEE", "side": "buy", "status": "filled", "order_type": "market",
         "filled_at": utc_at_et(D2, "20:05").isoformat()}]
check("a 20:05 ET fill belongs to the ET session, not the UTC date",
      "EEE" in dlr.books_vs_fills(None, late, D2)["filled_buys"])
b2 = dlr.books_vs_fills(None, ORDERS, D2)
check("a role with no sealed block says so and still reports its fills",
      b2["status"] == "no sealed portfolio" and b2["n_orders_day"] == 3)

print("\n-- refusal regret: graded and ungraded never pool; absence refuses by name")
ROWS = [
    {"action": "refused", "decision_id": "a", "symbol": "NVDA",
     "refusal_reason": "daily latch: -3.1% against the previous close",
     "ts_utc": f"{D2}T14:00:00Z", "outcome": {"pnl_usd": -500.0, "graded": True}},
    {"action": "refused", "decision_id": "b", "symbol": "AMD",
     "refusal_reason": "minimum detectable move is 3.4%; forecast below it",
     "ts_utc": f"{D2}T14:10:00Z", "outcome": {"pnl_usd": 200.0, "graded": True}},
    {"action": "refused", "decision_id": "c", "symbol": "TSLA",
     "refusal_reason": "minimum detectable move is 9.9%; forecast below it",
     "ts_utc": f"{D2}T14:20:00Z", "outcome": {"pnl_usd": 0.0, "graded": False}},
    # a re-mark of decision "a" later the same day: only the LAST mark counts
    {"action": "refused", "decision_id": "a", "symbol": "NVDA",
     "refusal_reason": "daily latch: -3.1% against the previous close",
     "ts_utc": f"{D2}T15:00:00Z", "outcome": {"pnl_usd": -700.0, "graded": True}},
    {"action": "refused", "decision_id": "d", "symbol": "MU",
     "refusal_reason": "the null: cash", "ts_utc": f"{D2}T14:00:00Z",
     "outcome": {"pnl_usd": 0.0, "graded": False}},
    {"action": "refused", "decision_id": "e", "symbol": "OLD",
     "refusal_reason": "daily latch", "ts_utc": f"{D1}T14:00:00Z",
     "outcome": {"pnl_usd": -1.0, "graded": True}},
    {"action": "submitted", "decision_id": "f", "ts_utc": f"{D2}T14:00:00Z"},
]
rr = dlr.refusal_day_summary(ROWS, D2)
check("only the day's refusals are counted (3: a, b, c)",
      rr["status"] == "ok" and rr["n_refused_decisions"] == 3, str(rr.get("n_refused_decisions")))
check("graded/ungraded split survives into the summary",
      rr["n_graded"] == 2 and rr["n_ungraded"] == 1)
latch = rr["by_guard"].get("daily_latch")
check("the guard registry classifies the reason (daily_latch, TOURNAMENT)",
      latch is not None and latch["class"] == "TOURNAMENT", str(list(rr["by_guard"])))
check("the LAST mark per decision wins: saved is 700, not 500 and not 1200",
      latch and latch["saved_usd"] == 700.0, str(latch and latch["saved_usd"]))
mdm = rr["by_guard"].get("mdm_floor")
check("a graded winner is COST; an ungraded row adds count and no dollars",
      mdm and mdm["cost_usd"] == 200.0 and mdm["n"] == 2 and mdm["graded"] == 1, str(mdm))
check("'the null' rows are excluded by construction",
      all("MU" not in v["symbols"] for v in rr["by_guard"].values()))
check("the ledger tear is reported as a fact beside the numbers",
      "TORN" in rr["ledger_note"] and "NOT repaired" in rr["ledger_note"])
rr2 = dlr.refusal_day_summary([], D2)
check("no rows for the day -> CANNOT DETERMINE with the missing input NAMED",
      rr2["status"] == dlr.CANNOT and "counterfactual.jsonl" in rr2["why"], str(rr2))

print("\n-- tmp-dir state: watchlist, shadow, receipt")
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    os.environ["AAT_LEDGER_DIR"] = str(tmp)
    try:
        (tmp / "tracker").mkdir()
        (tmp / "tracker" / f"{D1}.jsonl").write_text(
            "\n".join(json.dumps({"symbol": s}) for s in ("AAA", "BBB", "CCC")),
            encoding="utf-8")
        (tmp / "tracker" / f"{D2}.jsonl").write_text(
            "\n".join(json.dumps({"symbol": s}) for s in ("BBB", "CCC", "DDD")),
            encoding="utf-8")

        check("prior_tracker_day finds the previous file, strictly before the day",
              dlr.prior_tracker_day(D2) == D1)
        syms = dlr.tracker_symbols(D2)
        w = dlr.watchlist_events(syms, dlr.tracker_symbols(D1), D2, D1)
        check("entrants and dropouts are set differences, named",
              w["entrants"] == ["DDD"] and w["dropouts"] == ["AAA"], str(w))
        w2 = dlr.watchlist_events(syms, None, D2, None)
        check("no prior day file -> CANNOT DETERMINE, still counts the day",
              w2["status"] == dlr.CANNOT and w2["n_watchlist"] == 3)
        w3 = dlr.watchlist_events(None, None, D2, None)
        check("no day file at all -> CANNOT DETERMINE naming the path",
              w3["status"] == dlr.CANNOT and f"{D2}.jsonl" in w3["why"])

        # shadow: REFUSED is a finding, its reasons are the payload
        sb = tmp / f"shadow_book_{D2}.json"
        sb.write_text(json.dumps({"status": "REFUSED",
                                  "refusal_reasons": ["only 12 of 30 names carry CORE inputs"],
                                  "model": {"kind": "lgbm_clf", "arm": "engine_feature"},
                                  "mandate": {"k": 10}}), encoding="utf-8")
        sh = dlr.shadow_section(sb)
        check("a REFUSED shadow book surfaces its reasons verbatim",
              sh["status"] == "REFUSED" and "CORE inputs" in sh["refusal_reasons"][0])
        sh2 = dlr.shadow_section(tmp / f"shadow_book_{D1}.json")
        check("a missing shadow file is 'not present', with the path, not an error",
              sh2["status"] == "not present" and D1 in sh2["path"])
        sb.write_text(json.dumps({"status": "SEALED",
                                  "model": {"kind": "lgbm_clf", "arm": "engine_feature"},
                                  "mandate": {"k": 2},
                                  "book": [{"symbol": "MU"}, {"symbol": "NVDA"}]}),
                      encoding="utf-8")
        sh3 = dlr.shadow_section(sb)
        check("a sealed shadow book lists its picks", sh3["symbols"] == ["MU", "NVDA"])

        # the receipt: every headline number, beside the console, not instead of it
        rep = {"day": D2, "roles": {"hack9": {"scoreboard": row}},
               "spy": w, "refusal_regret": rr, "shadow": sh3, "watchlist": w2}
        path = dlr.write_receipt(rep)
        check("the receipt lands at state/learning_report/<day>.json",
              path == tmp / "learning_report" / f"{D2}.json" and path.exists())
        back = json.loads(path.read_text(encoding="utf-8"))
        check("headline numbers survive the round trip",
              back["roles"]["hack9"]["scoreboard"]["day_pnl_usd"] == -1000.0
              and back["refusal_regret"]["n_refused_decisions"] == 3)

        # render never crashes on a mixed page and prints the refusals it owes
        rep_full = {"day": D2, "generated_utc": "t", "spy": {"status": dlr.CANNOT, "why": "w"},
                    "seal_sha256": None,
                    "roles": {"hack9": {"scoreboard": row, "books_vs_fills": b},
                              "hack8": {"scoreboard": row2,
                                        "books_vs_fills": {"status": dlr.CANNOT, "why": "venue"}}},
                    "refusal_regret": rr2, "shadow": sh2, "watchlist": w3}
        page = dlr.render(rep_full)
        check("the page renders and is one page, not a scroll",
              isinstance(page, str) and len(page.splitlines()) < 60,
              f"{len(page.splitlines())} lines")
        check("a refusing section prints CANNOT DETERMINE, never a quiet zero",
              page.count(dlr.CANNOT) >= 3)
        check("the ledger tear fact is on the page even when the section refuses",
              "TORN" in page)
    finally:
        os.environ.pop("AAT_LEDGER_DIR", None)

print("\n-- read-only, pinned in source: this report can never act")
src = Path("scripts/daily_learning_report.py").read_text(encoding="utf-8")
for forbidden in (".submit(", "cancel_order", "close_position", "submit_protective_stop",
                  "flatten"):
    check(f"source never calls {forbidden!r}", forbidden not in src)

print("\n-- the broker gained two GETs and nothing else for this report")
import ast

tree = ast.parse(Path("alpha/broker/alpaca.py").read_text(encoding="utf-8"))
methods = {n.name: n for cls in ast.walk(tree) if isinstance(cls, ast.ClassDef)
           and cls.name == "AlpacaPaper" for n in cls.body
           if isinstance(n, ast.FunctionDef)}
check("AlpacaPaper.calendar exists", "calendar" in methods)
check("AlpacaPaper.portfolio_history exists", "portfolio_history" in methods)
for name in ("calendar", "portfolio_history"):
    body_src = ast.get_source_segment(Path("alpha/broker/alpaca.py").read_text(encoding="utf-8"),
                                      methods[name]) or ""
    check(f"{name} issues only GETs", '"GET"' in body_src and '"POST"' not in body_src
          and '"DELETE"' not in body_src)

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
