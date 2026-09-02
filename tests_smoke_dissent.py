"""Smoke: E1 -- PRICE THE DISSENT. The generator's verdict is stamped onto every
sealed holding, travels onto the graded outcome rows, and changes NO selection.

    python run_tests.py -k dissent      (never `python tests_smoke_dissent.py`)

WHAT THIS PINS, AND WHY EACH PIN EXISTS
=======================================
RZLV lost -17.30% on 2026-09-01 at 10% of hack4 while its own row in the SAME
sealed file read `claims: false`, rank 576 of 766, failing `b_rating` by 0.017.
On the 2026-09-02 seal, 25 of 30 hack3+hack6 holdings are names `murat_rule_v1`
declined. Both numbers were already in the same JSON and no key joined them.

  1. THE JOIN IS NOT A GATE. The stamped block must produce byte-identical
     holdings -- same symbols, same weights, same order -- as the unstamped one.
     A recorded disagreement that quietly changed the book would be an
     unannounced strategy change wearing an instrumentation commit.
  2. THE FIELDS REACH THE OUTCOME ROWS. `decision_outcomes` is where the four
     populations (held x claimed) accrue; a stamp that stops at the seal needs
     a hand-written join nobody will run.
  3. AN OLD SEAL STILL REPLAYS. Books sealed before 2026-09-02 carry no stamp.
     They must stay readable, and their absence must read as UNKNOWN, never as
     `claims: false` -- a name whose verdict was never computed is not a name
     the rule declined, and folding the two would poison the very population
     this experiment measures.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import drivers, murat_rule as mr                    # noqa: E402
from alpha import tracker as tr                                # noqa: E402
from alpha.brains import tracker_portfolio                     # noqa: E402
from scripts import decision_writeback as wb                   # noqa: E402
from scripts import prediction_book as pb                      # noqa: E402
from scripts import scenario_lab as lab                        # noqa: E402


# --------------------------------------------------------------- the stamp itself

print("-- generator_stamp: three outcomes, and the third is not the second")

_claimed = {"symbol": "AAA", "generator": "murat_rule_v1", "claims": True, "rank": 3,
            "failed_clauses": [], "exp_return": 0.0574, "downside_5pct": -0.19}
_declined = {"symbol": "BBB", "generator": "murat_rule_v1", "claims": False, "rank": 576,
             "failed_clauses": ["b_rating", "e_drawdown"],
             "exp_return": 0.0138, "downside_5pct": -0.38}

s_claimed = pb.generator_stamp(_claimed)
s_declined = pb.generator_stamp(_declined)
s_unknown = pb.generator_stamp(None)

check("a CLAIMED name stamps generator_claimed=True and dissent=False",
      s_claimed["generator_claimed"] is True and s_claimed["dissent"] is False)
check("a DECLINED name stamps generator_claimed=False and dissent=True",
      s_declined["generator_claimed"] is False and s_declined["dissent"] is True)
check("NO VERDICT stamps UNKNOWN, not False",
      s_unknown["generator_claimed"] is None and s_unknown["dissent"] is None,
      str(s_unknown["generator_claimed"]))
check("the unknown basis says so in words", "NO VERDICT" in s_unknown["dissent_basis"])
check("the declined stamp carries the failed clauses",
      s_declined["generator_failed_clauses"] == ["b_rating", "e_drawdown"])
check("the declined stamp carries the generator's own rank",
      s_declined["generator_rank"] == 576)
check("generator_score is the generator's own ranking expression",
      abs(s_declined["generator_score"] - mr.rank_key(_declined)) < 1e-9,
      f"{s_declined['generator_score']} vs {mr.rank_key(_declined)}")

# `rank_key` returns -inf for a row missing either number. `-Infinity` is not
# JSON: a sealed book carrying it cannot be re-read by a strict parser, and the
# whole value of the seal is that anyone can re-read it.
_no_numbers = {"symbol": "CCC", "claims": False, "rank": 700, "failed_clauses": ["a_target_ratio"]}
s_none = pb.generator_stamp(_no_numbers)
check("an unrankable row stamps generator_score=None, never -Infinity",
      s_none["generator_score"] is None)
check("every stamp is strict JSON",
      "Infinity" not in json.dumps([s_claimed, s_declined, s_unknown, s_none]))
check("the stamp never raises on a malformed prediction row",
      pb.generator_stamp({})["generator_claimed"] is None)


# ------------------------------------------------- the join changes NO selection

print("\n-- the stamp is a recorded join, not a gate")

_raw = [lab._row(symbol=f"ZZD{i}", mean_target=40.0 + i * 0.75,
                 sector=("Industrials", "Healthcare", "Technology")[i % 3])
        for i in range(8)]
_trows = tr.build_rows([dict(r) for r in _raw])
tr.apply_status(_trows)
_preds: dict[str, dict] = {}
for _t in _trows:
    _rr = lab._rule_row(_t)
    _v = mr.evaluate(_rr)
    _s = mr.score(_rr, _v, lab.FROZEN_PRIOR)
    for _k in ("exp_return", "downside_5pct", "confidence", "p_up_21d"):
        _t[_k] = _s.get(_k)
    _t["numbers_source"] = "rule"
    # Half of them are made to DECLINE, so both populations exist in the census.
    _claims = _v["fires"] and (int(_t["symbol"][-1]) % 2 == 0)
    _preds[_t["symbol"]] = {
        "symbol": _t["symbol"], "generator": "murat_rule_v1", "claims": bool(_claims),
        "rank": int(_t["symbol"][-1]) + 1,
        "failed_clauses": [] if _claims else ["b_rating"],
        **_s,
    }

_p = next(x for x in tr.PERSONALITIES if x.book == "hack4")
_port = tr.build_portfolio(_trows, _p)
_driver_of, _ = drivers.resolve([t["symbol"] for t in _trows])

_plain = pb._portfolio_block(_port, _p, _driver_of)
_stamped = pb._portfolio_block(_port, _p, _driver_of, _preds)

check("the synthetic book actually selected names (an empty book proves nothing)",
      _stamped["n_selected"] > 0, str(_stamped["n_selected"]))
_sel = lambda blk: [(h["symbol"], h["notional"], h["rank_value"]) for h in blk["holdings"]]
check("stamping changes NO selection: same symbols, weights and order",
      _sel(_plain) == _sel(_stamped), f"{_sel(_plain)} vs {_sel(_stamped)}")
check("stamping changes no other field of the block",
      {k: v for k, v in _plain.items() if k not in ("holdings", "generator_dissent")}
      == {k: v for k, v in _stamped.items() if k not in ("holdings", "generator_dissent")})

_STAMP_KEYS = {"generator", "generator_claimed", "generator_score", "generator_rank",
               "generator_failed_clauses", "dissent", "dissent_basis"}
check("every stamped holding carries the whole stamp",
      all(_STAMP_KEYS <= set(h) for h in _stamped["holdings"]))
check("an unstamped block carries the stamp as UNKNOWN, never as False",
      all(h["generator_claimed"] is None and h["dissent"] is None
          for h in _plain["holdings"]))

_cen = _stamped["generator_dissent"]
check("the dissent census counts every holding exactly once",
      _cen["claimed"] + _cen["declined"] + _cen["unknown"] == _cen["held"] == len(_stamped["holdings"]),
      str(_cen))
check("the census agrees with the per-holding stamps",
      _cen["declined"] == sum(1 for h in _stamped["holdings"] if h["dissent"] is True))
check("the census says RECORDED, NOT ENFORCED", "NOT ENFORCED" in _cen["note"])
check("a stamped block is strict JSON", "Infinity" not in json.dumps(_stamped, default=str))


# ------------------------------------------------- the fields reach the outcomes

print("\n-- the stamp travels onto the (day, symbol, book) outcome rows")


def _sealed(with_stamp: bool) -> dict:
    h = {
        "RZLV": {"symbol": "RZLV", "notional": 0.10, "exp_return": 0.5, "downside_5pct": -0.38},
        "NB": {"symbol": "NB", "notional": 0.10, "exp_return": 0.4, "downside_5pct": -0.42},
    }
    if with_stamp:
        h["RZLV"].update(pb.generator_stamp(_declined))
        h["NB"].update(pb.generator_stamp(_claimed))
    return {"book": "hack4", "day": "2026-09-01", "content_sha256": "6e69" * 16,
            "ranking": "rank_profit_max", "holdings": h}


_rows_new = wb.assemble(_sealed(True), [])
_rows_old = wb.assemble(_sealed(False), [])
_by = {r["symbol"]: r for r in _rows_new}
check("the decision row carries the generator's verdict",
      _by["RZLV"]["sealed"]["generator_claimed"] is False
      and _by["NB"]["sealed"]["generator_claimed"] is True)
check("the decision row carries dissent",
      _by["RZLV"]["sealed"]["dissent"] is True and _by["NB"]["sealed"]["dissent"] is False)
check("the decision row carries the failed clauses",
      _by["RZLV"]["sealed"]["generator_failed_clauses"] == ["b_rating", "e_drawdown"])

_closes = {"RZLV": [("2026-09-01", 10.0), ("2026-09-02", 8.27)],
           "NB": [("2026-09-01", 10.0), ("2026-09-02", 9.55)]}
_grades = wb.grade_rows(_rows_new, _closes)
check("grades matured for both names at h=1", len(_grades) == 2, str(len(_grades)))
check("every grade row carries the verdict it must be grouped by",
      all("generator_claimed" in g and "dissent" in g for g in _grades))
_gd = {g["symbol"]: g for g in _grades}
check("the four populations are separable from the grade rows alone",
      _gd["RZLV"]["dissent"] is True and _gd["NB"]["dissent"] is False)


# ------------------------------------------------------- an old seal still replays

print("\n-- a book sealed by the OLD schema is still readable")

check("assembling an unstamped seal does not invent a verdict",
      all("generator_claimed" not in r["sealed"] and "dissent" not in r["sealed"]
          for r in _rows_old))
_grades_old = wb.grade_rows(_rows_old, _closes)
check("unstamped decisions still grade", len(_grades_old) == 2)
check("an unstamped grade row carries no fabricated verdict",
      all("generator_claimed" not in g for g in _grades_old))

with tempfile.TemporaryDirectory() as _td:
    _dir = Path(_td) / "predictions"
    _dir.mkdir(parents=True)
    _old_book = {
        "schema": "prediction-book-3", "day": "2026-08-31",
        "content_sha256": "old" * 8, "sealed_at_utc": "2026-08-31T07:05:00+00:00",
        "portfolios": {"hack4": {
            "book": "hack4", "ranking": "rank_profit_max", "k_target": 5, "n_selected": 1,
            "ranking_is_degenerate": False, "constraints": {},
            # The pre-2026-09-02 holding shape, verbatim: no stamp anywhere.
            "holdings": [{"symbol": "RZLV", "notional": 0.10, "sector": "Technology",
                          "rank_value": 3.63, "exp_return": 0.0138,
                          "downside_5pct": -0.38, "confidence": 0.6,
                          "numbers_source": "rule"}],
        }},
    }
    (_dir / "2026-08-31.json").write_text(json.dumps(_old_book), encoding="utf-8")
    _saved = tracker_portfolio.BOOKS
    try:
        tracker_portfolio.BOOKS = _dir
        _read = tracker_portfolio.sealed_holdings("2026-08-31", book="hack4")
        check("an old sealed book still opens through the artery",
              set(_read["holdings"]) == {"RZLV"})
        check("its holding carries no stamp, and nothing pretends otherwise",
              "generator_claimed" not in _read["holdings"]["RZLV"])
        _old_rows = wb.assemble(_read, [])
        check("and it still writes back one decision row per sealed name",
              len(_old_rows) == 1 and _old_rows[0]["symbol"] == "RZLV")
    finally:
        tracker_portfolio.BOOKS = _saved


print()
if fails:
    print(f"FAILED {len(fails)}: " + ", ".join(fails))
    raise SystemExit(1)
print("dissent stamp: ALL PASS")
