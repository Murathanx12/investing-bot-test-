"""The opportunity-recall ledger, and the promise of a receipt every night.

Run: python tests_smoke_recall.py  (via `python run_tests.py` -- never bare)

OFFLINE BY CONSTRUCTION. `alpha/recall.py` is pure over passed-in sets, which is
the whole reason the classification lives there and not inside the script that
fetches movers. Dates are DERIVED FROM TODAY: a literal calendar moment in a
fixture is a test that rots the day after it passes.

WHAT THESE CHECKS ARE FOR
=========================
Each one corresponds to a way this ledger could be confidently wrong:

 1. the ladder implies its earlier rungs (no "bought but never observed" row);
 2. `sold_early` is TRI-STATE -- a position we still hold is not a failed hold;
 3. losers are classified too, and reported as AVOIDED rather than as misses,
    because a recall number computed on winners alone is maximised by a book
    that buys everything;
 4. a rate over zero movers is None, not 1.0 (the 312-wins-on-$0.00 lesson);
 5. with no seal or no ledger the day is written UNCLASSIFIED, because a
    missing seal would otherwise blame the MODEL and a missing ledger would
    blame EXECUTION for a job that simply did not run;
 6. every exit path of both autopsies writes a receipt -- an empty night writes
    a receipt saying it was empty.
"""
from __future__ import annotations

import ast
import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")

fails: list[str] = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import contract, recall

TODAY = date.today()
D1 = (TODAY - timedelta(days=1)).isoformat()

print("the opportunity-recall ledger")

print("\n-- the four miss types are a LADDER, earliest loss first")
check("MISS_TYPES is the declared order",
      recall.MISS_TYPES == ("NOT_OBSERVED", "GENERATED_NOT_RANKED",
                            "RANKED_NOT_BOUGHT", "BOUGHT_SOLD_EARLY"))
check("nowhere in any list -> NOT_OBSERVED",
      recall.classify("AAA")["miss_type"] == "NOT_OBSERVED")
check("observed, never ranked -> GENERATED_NOT_RANKED (the MODEL's stage)",
      recall.classify("AAA", observed=True)["miss_type"] == "GENERATED_NOT_RANKED")
check("ranked, never bought -> RANKED_NOT_BOUGHT (execution / an admission gate)",
      recall.classify("AAA", ranked=True)["miss_type"] == "RANKED_NOT_BOUGHT")
check("bought and closed inside the minimum hold -> BOUGHT_SOLD_EARLY",
      recall.classify("AAA", bought=True, sold_early=True)["miss_type"] == "BOUGHT_SOLD_EARLY")
check("bought and held -> CAPTURED, which is not a miss",
      recall.classify("AAA", bought=True)["miss_type"] == recall.CAPTURED)

_r = recall.classify("AAA", bought=True)
check("a bought name is implied ranked AND observed -- no impossible row",
      _r["ranked"] is True and _r["observed"] is True, str(_r))
check("sold_early=None means 'we hold it or cannot tell', NOT a passed hold",
      recall.classify("AAA", bought=True, sold_early=None)["miss_type"] == recall.CAPTURED)

print("\n-- both sides of the tape: a loser we did not buy is a SAVE, not a miss")
check("a WIN we did not capture is a missed_winner",
      recall.classify("AAA", side="WIN", observed=True)["recall_kind"] == "missed_winner")
check("a LOSS we did not capture is an avoided_loser",
      recall.classify("AAA", side="LOSS", observed=True)["recall_kind"] == "avoided_loser")
check("a LOSS we held is a held_loser -- the expensive one, named",
      recall.classify("AAA", side="LOSS", bought=True)["recall_kind"] == "held_loser")
check("a WIN we held is a captured_winner",
      recall.classify("AAA", side="WIN", bought=True)["recall_kind"] == "captured_winner")

print("\n-- classify_day keeps the evidence beside the verdict")
MOVERS = [
    {"symbol": "aaa", "side": "WIN", "pct": 18.0, "news_before_open": 3},
    {"symbol": "BBB", "side": "WIN", "pct": 12.0, "news_before_open": 0},
    {"symbol": "CCC", "side": "WIN", "pct": 9.0, "news_before_open": 1},
    {"symbol": "DDD", "side": "WIN", "pct": 8.0, "news_before_open": 0},
    {"symbol": "EEE", "side": "LOSS", "pct": -20.0, "news_before_open": 2},
    {"symbol": "FFF", "side": "LOSS", "pct": -15.0, "news_before_open": 0},
]
ROWS = recall.classify_day(MOVERS, observed={"BBB", "CCC", "DDD", "FFF"},
                           ranked={"CCC", "DDD", "FFF"}, bought={"DDD", "FFF"},
                           sold_early={"DDD": True})
by = {r["symbol"]: r["miss_type"] for r in ROWS}
check("symbols are upper-cased on the way in", "AAA" in by, str(sorted(by)))
check("one row per mover, all four stages represented",
      by == {"AAA": "NOT_OBSERVED", "BBB": "GENERATED_NOT_RANKED",
             "CCC": "RANKED_NOT_BOUGHT", "DDD": "BOUGHT_SOLD_EARLY",
             "EEE": "NOT_OBSERVED", "FFF": recall.CAPTURED}, str(by))
check("the mover's own evidence survives the classification",
      next(r for r in ROWS if r["symbol"] == "AAA")["news_before_open"] == 3)

print("\n-- the summary reports recall and avoidance TOGETHER")
S = recall.summarise(ROWS)
check("winner recall is captured winners / all winners",
      S["n_winners"] == 4 and S["winner_recall"] == 0.0, str(S))
check("loser avoidance is counted on the losers, separately",
      S["n_losers"] == 2 and S["loser_avoidance"] == 0.5, str(S))
check("by_miss_type covers every declared state",
      set(S["by_miss_type"]) == set(recall.RECALL_STATES))
EMPTY = recall.summarise([])
check("a rate over ZERO movers is None, never 1.0 and never 0.0",
      EMPTY["winner_recall"] is None and EMPTY["loser_avoidance"] is None, str(EMPTY))

print("\n-- discovery_autopsy: inputs are DERIVED or the day is UNCLASSIFIED")
from scripts import discovery_autopsy as da

with tempfile.TemporaryDirectory() as td:
    os.environ["AAT_LEDGER_DIR"] = td
    try:
        _ranked, _why = da.ranked_symbols(D1)
        check("no seal -> `ranked` is UNKNOWN and says so, not an empty ranking",
              _ranked == set() and _why.startswith("NO SEAL"), _why)
        _held, _sold, _bwhy = da.positions_from_ledger(D1)
        check("no ledger -> `bought` is UNKNOWN and says so",
              _held == set() and _bwhy.startswith("NO LEDGER"), _bwhy)

        led = Path(td) / "decisions.jsonl"
        led.write_text("\n".join(json.dumps(r) for r in [
            {"ts_utc": f"{D1}T13:40:00+00:00", "action": "submitted", "symbol": "DDD"},
            {"ts_utc": f"{D1}T14:40:00+00:00", "action": "submitted", "symbol": "FFF"},
            {"ts_utc": f"{D1}T18:00:00+00:00", "brain": "exit", "action": "closed",
             "symbol": "DDD", "outcome": {"exit_reason": "HARD_RISK_LIMIT"}},
            {"ts_utc": f"{D1}T18:00:00+00:00", "brain": "exit", "action": "closed",
             "symbol": "GGG", "outcome": {"exit_reason": ""}},
        ]) + "\n", encoding="utf-8")
        _held, _sold, _bwhy = da.positions_from_ledger(D1)
        check("entries on/before the day are the bought set",
              _held == {"DDD", "FFF"}, str(_held))
        check("a TYPED emergency exit on the day is sold-early",
              _sold.get("DDD") is True, str(_sold))
        check("an UNTYPED exit row is NOT counted as sold-early -- absence of a "
              "code is not evidence of one", "GGG" not in _sold, str(_sold))
        check("every emergency reason it tests against comes from the contract enum",
              "EMERGENCY_EXIT_REASONS" in Path("scripts/discovery_autopsy.py").read_text(
                  encoding="utf-8") or "contract.EMERGENCY_EXIT_REASONS" in Path(
                  "scripts/discovery_autopsy.py").read_text(encoding="utf-8"))
        check("HARD_RISK_LIMIT really is in that enum (the test is not self-satisfying)",
              "HARD_RISK_LIMIT" in contract.EMERGENCY_EXIT_REASONS)
    finally:
        os.environ.pop("AAT_LEDGER_DIR", None)

print("\n-- 'the WHOLE market' means the universe, not the screener's handful")
_ap = Path("state") / "autopsy"
check("universe_movers returns nothing (not an error) when daily_autopsy did not run",
      da.universe_movers("1999-01-01") == [])
with tempfile.TemporaryDirectory() as td:
    _fake = _ap / "0001-01-01.json"
    _ap.mkdir(parents=True, exist_ok=True)
    _fake.write_text(json.dumps({"session": "0001-01-01", "movers": [
        {"symbol": "nx", "side": "WIN", "ret_1d": 0.222, "industry": "Building"},
        {"symbol": "GWRE", "side": "LOSS", "ret_1d": -0.199, "industry": "Technology"},
        {"symbol": "", "side": "WIN", "ret_1d": 0.5}]}), encoding="utf-8")
    try:
        got = da.universe_movers("0001-01-01")
        check("whole-market movers are read out of the daily_autopsy receipt",
              [g["symbol"] for g in got] == ["NX", "GWRE"], str(got))
        check("WIN/LOSS maps onto the screener's gainers/losers vocabulary",
              [g["kind"] for g in got] == ["gainers", "losers"])
        check("the percentage is converted from a fraction, and NAMED as a source",
              got[0]["pct"] == 22.2 and got[0]["mover_source"] == "daily_autopsy universe",
              str(got[0]))
    finally:
        _fake.unlink(missing_ok=True)
_src_d = Path("scripts/discovery_autopsy.py").read_text(encoding="utf-8")
check("the recall ledger takes the UNION of both mover sources",
      "universe_movers(day)" in _src_d and "mover_source" in _src_d)

print("\n-- a receipt every night, on EVERY exit path, in both autopsies")
for mod in ("scripts/daily_autopsy.py", "scripts/discovery_autopsy.py"):
    src = Path(mod).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "main"), None)
    check(f"{mod} has a main()", fn is not None)
    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    check(f"{mod}: main() has more than one exit path (refusal + empty + ok)",
          len(returns) >= 3, f"{len(returns)} returns")
    writer = "write_receipt" if "daily_autopsy" in mod else "_write_receipt"
    check(f"{mod} routes every receipt through one writer, {writer}()",
          src.count(f"{writer}(") >= 4, str(src.count(f"{writer}(")))
    check(f"{mod} never dates a receipt off a bar that may not exist",
          'f"{session}.json"' not in src or "session = max(" not in src
          or "if session is None:" in src)

src = Path("scripts/daily_autopsy.py").read_text(encoding="utf-8")
check("daily_autopsy no longer returns 1 with no receipt on an empty universe",
      'print("no universe on disk")' not in src)
check("daily_autopsy derives its day from the ONE clock convention",
      "exits.session_day()" in src)

print("\n-- the after-close schedule: one clock, and a failed night is retried")
loop = Path("scripts/agent_loop.py").read_text(encoding="utf-8")
check("the ET hour comes from alpha.exits.ET_OFFSET, not a second -4",
      "_clock.ET_OFFSET).hour" in loop and "(datetime.now(timezone.utc).hour - 4)" not in loop)
check("and the alias is NOT the one _cycle rebinds locally (an UnboundLocalError "
      "on every cycle, caught by the suite on 2026-09-05)",
      "exits as _clock" in loop and "exits as _exits" in loop)
check("a non-zero autopsy exit does NOT mark the night done",
      "AUTOPSY_RETRY_S" in loop and "rc_a == 0 and rc_d == 0" in loop)
check("discovery_autopsy is still on the after-close block",
      "scripts.discovery_autopsy" in loop)

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
