"""Decision B.1 4a -- hygiene-only, PREPARED AND NOT ENABLED; and the Monday dry run.

Run: python tests_smoke_band_mode.py  (via `python run_tests.py` -- never bare)

THE ONE CHECK THAT MATTERS MOST is the first: with `AAT_BAND_MODE` unset, every
number and every gate is byte-identical to the live fleet's. A switch prepared
for Murat that quietly changes what a live book admits is not a prepared switch,
it is a deployed one.

The rest pin the three things the flag changes -- and they pull in OPPOSITE
directions, which is exactly why they are one switch and not three:

  1. the ratio >= 4.0 bar stops EXCLUDING and becomes an indicator  (ADMITS)
  2. the hard price floor rises $1 -> $2                            (EXCLUDES)
  3. a target window wider than 5x is UNREADABLE and is barred      (EXCLUDES)

Plus the dry run's own arithmetic, where a units error would be silent:
`Personality.max_notional` is a FRACTION OF EQUITY, and the first draft of
`contract_for` multiplied it by a stop as if it were dollars, printing a $1.00
risk budget on a $6,640 worst case.
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")
os.environ.pop("AAT_BAND_MODE", None)

fails: list[str] = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import murat_rule as mr
from alpha import tracker as tk

TOXIC = {"target_ratio": 6.0, "close": 10.0, "coverage": 4,
         "target_high": 20.0, "target_low": 15.0}

print("decision B.1 4a -- the band as a guide, not a rule")

print("\n-- UNSET is the live fleet, unchanged")
check("the default mode is `returns`", mr.band_mode() == mr.BAND_MODE_RETURNS)
check("the live default price floor is still $1", tk.min_price_usd() == tk.MIN_PRICE_USD)
check("hygiene_only() is False without the flag", tk.hygiene_only() is False)
_d = mr.band_overlay(TOXIC)
check("the ratio>=5 return constant still APPLIES by default",
      _d["applies"] is True and _d["exp_return_monthly"] < 0, str(_d.get("exp_return_monthly")))
_v = tk.classify(dict(TOXIC, upside=6.0, consensus=4.5, past_winner=False,
                        days_to_catalyst=5, tradable=True), prev=None)
check("and a ratio >= 4.0 name is still BARRED from candidacy by default",
      _v.status == "WATCH" and any("4.0" in b or "400%" in b for b in _v.blocked_by), str(_v))

print("\n-- hygiene is about READABILITY, and separates 'fails' from 'cannot check'")
check("a clean row passes", mr.hygiene(TOXIC)["ok"] is True)
_sub2 = mr.hygiene(dict(TOXIC, close=1.50))
check("under $2 FAILS, and says 'no opinion' rather than 'historically bad'",
      _sub2["ok"] is False and "UNINFORMATIVE" in _sub2["fails"][0], str(_sub2))
_thin = mr.hygiene(dict(TOXIC, coverage=1))
check("one analyst FAILS the >= 2 condition every cell was measured under",
      _thin["ok"] is False and "1 < 2" in _thin["fails"][0], str(_thin))
_split = mr.hygiene(dict(TOXIC, target_high=100.0))
check("a target window wider than 5x is UNREADABLE, named as a share-basis defect",
      _split["ok"] is False and "split" in _split["fails"][0], str(_split))
_blind = mr.hygiene({"target_ratio": 6.0})
check("a condition that cannot be EVALUATED lands in `unreadable`, not in `fails`",
      _blind["fails"] == [] and len(_blind["unreadable"]) == 2, str(_blind))
check("SPLIT_SUSPECT_RATIO is the SAME 5x analyst_targets uses, not a second constant",
      mr.SPLIT_SUSPECT_RATIO == 5.0)
check("the hygiene thresholds ARE the BAND_PRIOR's measured conditions",
      mr.BAND_PRIOR["min_price"] == 2.0 and mr.BAND_PRIOR["min_coverage"] == 2)

print("\n-- under the flag: no return constant, and the ratio survives as an indicator")
_h = mr.band_overlay(TOXIC, mode=mr.BAND_MODE_HYGIENE_ONLY)
check("no band APPLIES, so `score` keeps the panel base rate",
      _h["applies"] is False and "exp_return_monthly" not in _h, str(_h))
check("the ratio's band is still REPORTED -- an indicator a model can read",
      _h["band"] == "ratio 5..inf", str(_h.get("band")))
check("the row carries the hygiene verdict for the eligibility chain to read",
      _h["hygiene_ok"] is True and "hygiene_fails" in _h)
check("the basis names the decision out loud", "B.1 4a" in _h["basis"])

os.environ["AAT_BAND_MODE"] = "hygiene_only"
try:
    check("the flag is read at CALL time, not import time",
          mr.band_mode() == mr.BAND_MODE_HYGIENE_ONLY and tk.hygiene_only() is True)
    check("the price floor rises to $2 -- this EXCLUDES names", tk.min_price_usd() == 2.0)
    _v2 = tk.classify(dict(TOXIC, upside=6.0, consensus=4.5, past_winner=False,
                             days_to_catalyst=5, tradable=True), prev=None)
    check("a ratio >= 4.0 name is NO LONGER barred -- this ADMITS names",
          _v2.status != "WATCH" or not any("Barred" in b for b in _v2.blocked_by), str(_v2))
    check("it is REPORTED instead, as a guide",
          any("REPORTED as an indicator" in b for b in _v2.blocked_by) or _v2.status != "WATCH",
          str(_v2))
    _drop = tk.classify({"close": 1.50, "upside": 0.5, "consensus": 4.5,
                           "past_winner": False, "tradable": True}, prev=None)
    check("a $1.50 name is DROPPED under the flag (it was admissible at the $1 floor)",
          _drop.status == "DROP" and "$2.00" in _drop.reasons[0], str(_drop))

    pers = next(p for p in tk.PERSONALITIES if p.book == "hack4")
    names = [getattr(c, "__name__", "?") for c in tk._eligibility_checks(pers)]
    check("a hygiene check joins the eligibility chain, FIRST", names[0] == "_hygiene", str(names))
    _fail_row = {"symbol": "AAA", "hygiene_ok": False,
                 "hygiene_fails": ["close $1.50 < $2"], "hygiene_unreadable": []}
    got = tk._eligibility_checks(pers)[0](_fail_row)
    check("and it fails with the reason NAMED, not a bare rejection",
          got is not None and "B.1 4a" in got[0] and "1.50" in got[1], str(got))
    check("a row that never carried a band overlay is 'not evaluated', not 'passed'",
          tk._eligibility_checks(pers)[0]({"symbol": "BBB"})[0].startswith("hygiene not evaluated"))
finally:
    os.environ.pop("AAT_BAND_MODE", None)

check("and the flag is OFF again afterwards -- no test leaks a live setting",
      mr.band_mode() == mr.BAND_MODE_RETURNS and tk.hygiene_only() is False)

print("\n-- the Monday dry run: units, attribution, and it can never seal")
from scripts import monday_dry_run as dr

check("it prints the three tracker books", dr.BOOKS == ("hack3", "hack4", "hack6"))
_b = dr.binding({"excluded_marginal": {
    "fails": {"big but redundant": 500, "the real one": 20},
    "fails_only": {"big but redundant": 0, "the real one": 18}}})
check("BINDING sorts by fails_only -- what relaxing the rule ALONE would buy",
      _b[0][0] == "the real one" and _b[0][2] == 18, str(_b))
check("a rule with many `fails` and zero `fails_only` sorts LAST: redundant, not binding",
      _b[-1][0] == "big but redundant")

check("max_notional is treated as a FRACTION of equity, not dollars",
      dr.contract_for("hack3", "2026-09-08", 0.083, 0.08)["risk_budget_usd"] == 664.0,
      str(dr.contract_for("hack3", "2026-09-08", 0.083, 0.08)["risk_budget_usd"]))
check("the equity it computes against is FROZEN and stated, not a live balance",
      dr.ASSUMED_EQUITY_USD == 100_000.0)
check("the stop width comes from the FLEET's profile, not the Personality",
      dr.profile_for("hack3") == "basket" and dr.profile_for("hack6") == "aggressive")
_c = dr.contract_for("hack3", "2026-09-08", 0.083, 0.08)
check("the contract it prints is the TRACKER contract: 21 sessions, min hold 10",
      _c["expected_horizon_sessions"] == 21 and _c["min_normal_hold_sessions"] == 10, str(_c))
check("and it carries no profit target -- a +2.5% target on a 21-session thesis is noise",
      _c["profit_target_frac"] is None)

_src = Path("scripts/monday_dry_run.py").read_text(encoding="utf-8")
# CODE, not prose: this file's own docstrings NAME `state/predictions` and
# `--publish` in order to say it never touches them, so a substring test over
# the whole source would fail on its own explanation. Test the constructs.
_code = " ".join(l for l in _src.splitlines()
                 if not l.lstrip().startswith("#") and '"""' not in l)
check("the dry run defaults its output to a TEMP dir",
      'tempfile.mkdtemp(prefix="aat-dry-run-")' in _code)
check("and never CONSTRUCTS a predictions path", '"predictions"' not in _code)
for forbidden in ('.submit(', '"--live"', 'close_position', '"--publish"'):
    check(f"the dry run never calls {forbidden!r}", forbidden not in _code)
check("`--live` is not even an accepted argument of the dry run",
      '"--live"' not in _code and "add_argument('--live'" not in _code)

_pb = Path("scripts/prediction_book.py").read_text(encoding="utf-8")
check("tracker_rows' replay `asof` is KEYWORD-ONLY, so a live seal cannot pass it by position",
      "def tracker_rows(day: str | None = None, *, asof: str | None = None)" in _pb)
check("and the live seal still passes NO asof (measured against today)",
      "tracker_rows()" in _pb)

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
