"""Smoke: E3 -- every candidate finishes in EXACTLY ONE typed terminal state, and
an ungraded counterfactual world is never counted as a win.

    python run_tests.py -k terminal_state

WHY THESE TWO THINGS ARE ONE SUITE
==================================
Both are the same failure wearing different clothes: a record that carries no
disposition reads as a disposition anyway. hack1/hack2/hack5 ran passes that
refused 100% of their candidates and the only record of why was prose, which
does not group -- so "the alpha layer is barren" and "the risk layer is too
strict", which call for opposite work, printed identically. And 45.4% of
counterfactual decisions carry `pnl_usd = 0.0` because nothing priced them,
which pooled into `win%` made `daily_latch` report 312 wins out of 312 on $0.00
saved and $0.00 cost.

WHAT IS PINNED
  * one state per record, and it is always in the closed enum;
  * unknown prose -> OTHER_TYPED **with the sentence preserved beside it** and
    COUNTED, so a gate added without a type surfaces as a number;
  * the derivation reuses `classify()` -- one vocabulary, not two tables;
  * win% is split graded / ungraded, and a guard with no graded rows prints
    neither 0% nor 100%;
  * a ledger row written before the field exists is still readable.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import fields as dc_fields
from pathlib import Path

os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import counterfactual, ledger, refusal_classes as rc     # noqa: E402
from scripts import refusal_regret as rr                            # noqa: E402

ROOT = Path(__file__).resolve().parent


# ------------------------------------------------------- the enum and the mapping

print("-- the enum is closed, and every class lands inside it")

REQUIRED = {"ADMITTED", "ALREADY_HELD", "RANKED_OUT", "NEGATIVE_EV", "CONFIDENCE",
            "LIQUIDITY", "CAPACITY", "GROSS", "CONCENTRATION", "OPENING_RANGE",
            "MANDATE", "STRUCTURE", "DATA_STALE", "DATA_MISSING", "RISK",
            "DUPLICATE", "OTHER_TYPED"}
check("the declared enum is exactly the seventeen states", set(rc.TERMINAL_STATES) == REQUIRED,
      str(REQUIRED.symmetric_difference(rc.TERMINAL_STATES)))
check("the enum has no duplicates", len(rc.TERMINAL_STATES) == len(set(rc.TERMINAL_STATES)))
check("every post-hoc class maps to a declared state",
      all(v in REQUIRED for v in rc.CLASS_TO_TERMINAL.values()))
check("every post-hoc class has a mapping (no class falls through to OTHER_TYPED)",
      {name for name, _ in rc.PATTERNS} <= set(rc.CLASS_TO_TERMINAL),
      str({name for name, _ in rc.PATTERNS} - set(rc.CLASS_TO_TERMINAL)))
check("every live-only pattern names a declared state",
      all(s in REQUIRED for s, _ in rc.TERMINAL_PATTERNS))
check("every action short-circuit names a declared state",
      all(v in REQUIRED for v in rc.ACTION_STATES.values()))

# The derivation REUSES the post-hoc table rather than restating it: the same
# sentence must get the same meaning in the live stamp and in the retrospective.
_SENTENCES = {
    "ADMISSION: GROSS: after this order the book would carry 310% of equity in notional (cap 200%).": "GROSS",
    "ADMISSION: DRIVER: after this order the book would carry 61% of equity on 'ai_capex'.": "CONCENTRATION",
    "CONCENTRATION: RZLV would carry 12.4% of equity in true max loss after this order.": "CONCENTRATION",
    "BOOK LIMIT: MAX_BOOK_STRESS 14.2% > 12.0%": "CAPACITY",
    "OPENING RANGE: shares are not bought in the first 15 minutes.": "OPENING_RANGE",
    "DAILY LOSS LATCH: the book is down 3.1% today.": "RISK",
    "NB already positioned in this book (1 legs); exits decide when it is free again": "ALREADY_HELD",
    "out-ranked on median/max-loss by long_call at 1.4x": "RANKED_OUT",
    "CASH beats it: cleared the MDM gate (+2.1%) but the EV is under cash.": "NEGATIVE_EV",
    "round-trip spread is 31% of max loss": "LIQUIDITY",
    "the disagreement with the chain is +0.4%, under the bar": "NEGATIVE_EV",
    "the move is under the minimum detectable move for this chain": "CONFIDENCE",
    "8 structures enumerated at 2026-08-28, none cleared the gates. aggregate convex risk is already 61%": "STRUCTURE",
    "CROSS-BOOK: NVDA is held by a peer book this session": "DUPLICATE",
    "CANNOT DETERMINE the day's drawdown": "DATA_MISSING",
    # live-only sentences: never in the counterfactual ledger, so never in PATTERNS
    "MU has 1 order(s) IN FLIGHT at the venue and unfilled": "DUPLICATE",
    "ABAT: a protective stop closed this name earlier today; no same-session re-entry": "DUPLICATE",
    "no equity to admit against": "DATA_MISSING",
}
_wrong = {s: (rc.terminal_state(s), want) for s, want in _SENTENCES.items()
          if rc.terminal_state(s) != want}
check("every real refusal sentence types to the state it means", not _wrong, str(_wrong)[:400])
check("the derivation agrees with the post-hoc class wherever one exists",
      all(rc.terminal_state(s) == rc.CLASS_TO_TERMINAL[rc.classify(s)]
          for s in _SENTENCES if rc.classify(s) != rc.UNCLASSIFIED))


# ------------------------------------------------------------- one state, never blank

print("\n-- exactly one state per record: never blank, never a crash")

rc.reset_unmapped()
_UNKNOWN = "GAMMA CURFEW: a gate invented tomorrow that nobody has typed yet (0.42 vs 0.30)"
check("unknown prose types to OTHER_TYPED", rc.terminal_state(_UNKNOWN) == "OTHER_TYPED")
check("and it is COUNTED, so it surfaces", sum(rc.UNMAPPED.values()) == 1, str(rc.UNMAPPED))
rc.terminal_state(_UNKNOWN.replace("0.42 vs 0.30", "9.99 vs 1.00"))
check("the same gate with different numbers counts as ONE unmapped sentence",
      len(rc.UNMAPPED) == 1 and sum(rc.UNMAPPED.values()) == 2, str(dict(rc.UNMAPPED)))
check("unmapped_report surfaces it commonest-first", rc.unmapped_report(1)[0][1] == 2)

for _bad in (None, "", "   ", 17, {"a": 1}, b"bytes"):
    got = rc.terminal_state(_bad)                       # type: ignore[arg-type]
    check(f"never raises and never blanks on {_bad!r}", got in REQUIRED, str(got))
check("a submitted row is ADMITTED without its prose being parsed",
      rc.terminal_state("approved 2.00% of $99,000", action="submitted") == "ADMITTED")
check("an intent row is ADMITTED (it is pre-POST, not a decline)",
      rc.terminal_state("intent persisted before POST", action="intent") == "ADMITTED")
check("a dry run is ADMITTED, not refused -- the order was BUILT",
      rc.terminal_state("dry run: order built and not sent", action="dry_run") == "ADMITTED")
check("an unknown ACTION still lands in the enum",
      rc.terminal_state("something new happened", action="teleported") in REQUIRED)
rc.reset_unmapped()


# --------------------------------------------------------- the ledger carries it

print("\n-- the ledger field exists, defaults to None, and stays last")

_names = [f.name for f in dc_fields(ledger.Decision)]
check("Decision carries `terminal_state`", "terminal_state" in _names)
check("and it is the LAST field, so positional construction still means what it meant",
      _names[-1] == "terminal_state", _names[-1])
_d = ledger.Decision("id", "t", "X", "b", None, "i", "", None, None, None, None, None, {},
                     "refused", "GROSS: over the cap", 0.0, 0.0, None)
check("an old-style positional Decision still builds", _d.symbol == "X")
check("and its terminal_state defaults to None, never to a guessed type",
      _d.terminal_state is None)

# The runner stamps it. Checked through the SOURCE rather than by running a pass:
# a pass needs a venue, and this is the one line that has to be there.
_runner_src = (ROOT / "alpha" / "runner.py").read_text(encoding="utf-8")
check("alpha/runner.py stamps terminal_state at write time",
      "terminal_state=refusal_classes.terminal_state(reason, action=action)" in _runner_src)
check("and it keeps the full prose beside it", "refusal_reason=None if action in" in _runner_src)
check("the forecast shadow row is deliberately untyped (it is arrival, not disposition)",
      "terminal_state=None," in _runner_src)


# ------------------------------------------------ graded vs ungraded, never pooled

print("\n-- an ungraded world is not a win")

check("Mark.graded is True only for a chain mark",
      counterfactual.Mark("d", "X", "k", "refused", "r", 1, 1.0, 2.0, 1.0, 5000.0,
                          "t", "chain").graded is True)
for _src in ("null", "unmarkable"):
    check(f"a {_src} mark is NOT graded",
          counterfactual.Mark("d", "X", "k", "refused", "r", 0, 0.0, 0.0, 0.0, 5000.0,
                              "t", _src).graded is False)

check("a new-schema row reads `graded` off the outcome",
      rr.is_graded({"outcome": {"graded": True, "pnl_usd": 12.0}}) is True)
check("an OLD row derives it from mark_source, so old ledgers are not lost",
      rr.is_graded({"quote_snapshot": {"mark_source": "chain"}}) is True)
check("an old unmarkable row is UNGRADED",
      rr.is_graded({"quote_snapshot": {"mark_source": "unmarkable"}, "outcome": {"pnl_usd": 0.0}}) is False)
check("a row with neither is UNGRADED, not assumed graded",
      rr.is_graded({"outcome": {"pnl_usd": 0.0}}) is False)

# The daily_latch shape, end to end: 4 refusals, none of them priced. The old
# table read this as 100% wins; the split must read it as 0 graded.
_LEDGER = [
    # three unmarkable worlds -- the `daily_latch` family
    *[{"action": "refused", "decision_id": f"lat{i}", "symbol": "NVDA", "instrument": "none",
       "ts_utc": "2026-08-26T13:31:00+00:00", "refusal_reason": "DAILY LOSS LATCH: down 3.1% today",
       "terminal_state": "RISK",
       "quote_snapshot": {"mark_source": "unmarkable"},
       "outcome": {"pnl_usd": 0.0, "graded": False}} for i in range(3)],
    # one genuinely priced world that LOST in the parallel run: a real save
    {"action": "refused", "decision_id": "mdm1", "symbol": "PANW", "instrument": "long_call",
     "ts_utc": "2026-08-26T13:31:00+00:00",
     "refusal_reason": "the move is under the minimum detectable move for this chain",
     "terminal_state": "CONFIDENCE",
     "quote_snapshot": {"mark_source": "chain"},
     "outcome": {"pnl_usd": -400.0, "graded": True}},
    # one priced world that WON: a real cost
    {"action": "refused", "decision_id": "mdm2", "symbol": "MU", "instrument": "long_call",
     "ts_utc": "2026-08-26T13:31:00+00:00",
     "refusal_reason": "the move is under the minimum detectable move for this chain",
     "terminal_state": "CONFIDENCE",
     "quote_snapshot": {"mark_source": "chain"},
     "outcome": {"pnl_usd": 900.0, "graded": True}},
]

with tempfile.TemporaryDirectory() as _td:
    _p = Path(_td) / "counterfactual.jsonl"
    _p.write_text("\n".join(json.dumps(r) for r in _LEDGER) + "\n", encoding="utf-8")
    # The venue guard is INHERITED from `run_tests.py`, never re-set here: a
    # suite that names that variable is itself the thing `tests_smoke_test_
    # isolation` exists to catch.
    _env = dict(os.environ, AAT_LEDGER_DIR=_td)
    _run = subprocess.run([sys.executable, "-m", "scripts.refusal_regret", "--path", str(_p)],
                          capture_output=True, text=True, cwd=str(ROOT), env=_env)
    _out = _run.stdout
    check("refusal_regret runs on a synthetic ledger", _run.returncode == 0, _run.stderr[-300:])
    check("it states the graded / ungraded split up front",
          "2 GRADED, 3 UNGRADED" in _out, _out.splitlines()[0] if _out else "")
    _latch_lines = [ln for ln in _out.splitlines() if "DAILY LOSS LATCH" in ln or ln.startswith("RISK")]
    check("a family with NO graded rows prints `--`, not 0% and not 100%",
          bool(_latch_lines) and all("--" in ln and "%" not in ln for ln in _latch_lines),
          str(_latch_lines))
    check("100% never appears for the unpriced family",
          "100%" not in _out, [ln for ln in _out.splitlines() if "100%" in ln])
    check("the typed-state table is printed", "terminal_state" in _out)
    _receipt = json.loads((Path(_td) / "refusal_regret.json").read_text(encoding="utf-8"))
    check("the receipt carries the split", _receipt["graded"] == 2 and _receipt["ungraded"] == 3,
          str({k: _receipt.get(k) for k in ("graded", "ungraded")}))
    _cls = _receipt["by_class"]
    check("the three unpriced rows are COUNTED and contribute exactly $0",
          _cls["UNCLASSIFIED"]["n"] == 3 and _cls["UNCLASSIFIED"]["ungraded"] == 3
          and _cls["UNCLASSIFIED"]["saved"] == 0.0 and _cls["UNCLASSIFIED"]["cost"] == 0.0,
          json.dumps(_cls))
    check("and the two priced rows carry every dollar in the table",
          _cls["EMPIRICAL"]["saved"] == 400.0 and _cls["EMPIRICAL"]["cost"] == 900.0,
          json.dumps(_cls))
    _states = _receipt["by_terminal_state"]
    check("the receipt groups by the typed state the gate stamped",
          _states["RISK"]["graded"] == 0 and _states["RISK"]["ungraded"] == 3,
          json.dumps(_states))
    check("and the graded family keeps its real 50% win rate",
          _states["CONFIDENCE"]["graded"] == 2 and _states["CONFIDENCE"]["wins"] == 1)

check("report() names the ungraded refusals rather than dropping them",
      {"refused_graded", "refused_ungraded"} <= set(counterfactual.report([
          counterfactual.Mark("a", "X", "k", "refused", "r", 1, 1.0, 0.5, -0.5, 5000.0, "t", "chain"),
          counterfactual.Mark("b", "Y", "k", "refused", "r", 0, 0.0, 0.0, 0.0, 5000.0, "t", "unmarkable"),
      ])))
_rep = counterfactual.report([
    counterfactual.Mark("a", "X", "k", "refused", "r", 1, 1.0, 0.5, -0.5, 5000.0, "t", "chain"),
    counterfactual.Mark("b", "Y", "k", "refused", "r", 0, 0.0, 0.0, 0.0, 5000.0, "t", "unmarkable"),
])
check("and it counts them apart: 1 graded, 1 ungraded",
      _rep["refused_graded"] == 1 and _rep["refused_ungraded"] == 1,
      f"{_rep['refused_graded']}/{_rep['refused_ungraded']}")


print()
if fails:
    print(f"FAILED {len(fails)}: " + ", ".join(fails))
    raise SystemExit(1)
print("terminal states: ALL PASS")
