"""C2 -- ADVERSARIAL REVIEW OF THE EXIT RULE ON SYNTHETIC PRICE PATHS.

    python run_tests.py -k labor_exits      # the ONLY supported way

THE QUESTION
============
`alpha/contract.py` was written on 2026-09-05 because **60% of the fleet's
round trips finished in the same session they opened** on books whose sealed
thesis is a 21-session drift. The repair is a minimum hold that only a TYPED
reason may pre-empt. A repair like that is not proved by one hand-built case:
the rule has to hold over every path the market can draw, including the ones
nobody would have thought to write down.

So: 200 seeded random 21-session paths per (role, profile) cell, walked one
session at a time through `exits.evaluate`, with three assertions.

  A. NO CLOSE BEFORE `min_normal_hold_sessions` WITHOUT A TYPED REASON. The
     close, if any, must carry a code from `contract.EMERGENCY_EXIT_REASONS`.
     "The price moved 3%" is not one of them, and that sentence is the entire
     content of the S39 finding.
  B. THE STOP FIRES AT THE PROFILE WIDTH, AND IS BOOKED `HARD_RISK_LIMIT`.
     Not at a flat 3%: `alpha/exits.py` charged 3% on every book while
     `alpha/protect.py` placed 8% at the venue for the basket profile, so the
     exit pass pre-empted the stop the position had been sized against. The
     first session a path crosses `-stop_fraction(profile)` must close, and it
     must close under that code.
  C. NOTHING CLOSES INSIDE THE STOP, INSIDE THE HORIZON, BEFORE THE HOLD. The
     complement of A: the rule must also not be vacuous.

AND ONE QUESTION OF FACT: **what IS hack2's contract?** The lane C mandate says
to assert it is not the EVENT defaults, or to document exactly what it is. It
is documented below, in the receipt, and pinned here -- because the answer is
"the event defaults, with the horizon replaced by whatever the forecast said,
and a minimum hold of ZERO", and a minimum hold of zero makes assertion A
VACUOUS on that book. A test that passes because it tests nothing is worse than
one that fails.

SEEDED. `np.random.default_rng(seed)` per cell, seed recorded in the receipt.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

os.environ["AAT_LEDGER_DIR"] = tempfile.mkdtemp(prefix="aat-labor-c2-")
os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")

import numpy as np                                       # noqa: E402

from alpha import contract as contract_mod               # noqa: E402
from alpha import exits, fleet, runner                   # noqa: E402
from alpha.engine import equity as equity_mod            # noqa: E402
from alpha.engine import sizing                          # noqa: E402

fails: list[str] = []
ran = 0
FINDINGS: list[dict] = []


def check(name: str, cond: bool, why: str = "") -> bool:
    global ran
    ran += 1
    if cond:
        print(f"  ok   {name}")
    else:
        fails.append(name)
        print(f"  FAIL {name}  {why}")
    return bool(cond)


DEADLINE = "2027-12-31T15:00:00Z"        # the mandate end; never a live date
N_PATHS = 200
N_SESSIONS = 21
SEED = 20260907

#: A Monday, so `_sessions_since` (weekdays, holidays ignored) is walkable.
ENTRY_UTC = datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc)


def session_datetime(i: int) -> datetime:
    """UTC at 15:00 ET on the i-th weekday AFTER entry (i=0 is the entry day)."""
    d = ENTRY_UTC
    left = i
    while left > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            left -= 1
    return d.replace(hour=19, minute=0)   # 15:00 ET, before SHARES_HORIZON_EXIT_ET


def entry_row(symbol: str, role: str, *, horizon_days: float | None = 21.0,
              contract: dict | None = None) -> dict:
    out: dict = {"decision_id": "c2", "ts_utc": ENTRY_UTC.isoformat(), "symbol": symbol,
                 "brain": "tracker_portfolio", "action": "submitted",
                 "instrument": "long_shares", "account_role": role, "outcome": {}}
    if horizon_days is not None:
        out["outcome"]["horizon_days"] = horizon_days
    if contract is not None:
        out["outcome"]["contract"] = contract
    return out


def position(symbol: str, plpc: float, entry: float = 100.0, qty: int = 100) -> dict:
    px = entry * (1.0 + plpc)
    return {"symbol": symbol, "asset_class": "us_equity", "qty": str(qty),
            "avg_entry_price": f"{entry:.2f}", "cost_basis": f"{entry * qty:.2f}",
            "market_value": f"{px * qty:.2f}", "current_price": f"{px:.4f}",
            "unrealized_pl": f"{(px - entry) * qty:.2f}",
            "unrealized_plpc": f"{plpc:.8f}"}


def paths(rng, n: int, sessions: int, daily_sd: float) -> np.ndarray:
    """`n` cumulative-return paths of `sessions` steps. Fat-tailed on purpose:
    a Student-t(4) innovation puts real mass through the stop, which a Gaussian
    at 2% daily barely does -- and a stop assertion that never fires is not an
    assertion."""
    z = rng.standard_t(df=4, size=(n, sessions)) / np.sqrt(4 / 2.0)
    return np.cumsum(z * daily_sd, axis=1)


# ===========================================================================
print("\nC2-0  WHAT IS hack2's CONTRACT, EXACTLY?")
# ===========================================================================
os.environ["AAT_ACCOUNT_ROLE"] = "hack2"
os.environ["AAT_RISK_PROFILE"] = fleet.FLEET["hack2"].profile
h2_defaults = contract_mod.defaults_for("hack2", profile=fleet.FLEET["hack2"].profile)
h2_event = contract_mod.defaults_for("__no_such_book__",
                                     profile=fleet.FLEET["hack2"].profile)
same_shape = {k: h2_defaults[k] == h2_event[k] for k in h2_event}
ok0a = check("hack2 is NOT one of contract.TRACKER_BOOKS",
             "hack2" not in contract_mod.TRACKER_BOOKS)
ok0b = check("  so `defaults_for('hack2')` IS the EVENT default shape, field for field",
             all(same_shape.values()), str(same_shape))
ok0c = check("  horizon 3, minimum hold ZERO, profit target 2.5%, EVENT falsifiers",
             h2_defaults["expected_horizon_sessions"] == 3
             and h2_defaults["min_normal_hold_sessions"] == 0
             and abs(float(h2_defaults["profit_target_frac"]) - 0.025) < 1e-9
             and h2_defaults["hard_falsifiers"] == contract_mod.EVENT_FALSIFIERS,
             str(h2_defaults))

# What the LIVE code actually stamps on a hack2 order, which is not the same
# object: `runner.contract_for` overrides the horizon with the FORECAST's own
# horizon_days for any role outside TRACKER_BOOKS.
from alpha.brains.base import Forecast                    # noqa: E402

_f = Forecast(brain="post_event_drift", symbol="NVDA", horizon_days=5.0,
              centre=0.01, sd=0.03, claim="direction")
_s = sizing.Structure(symbol="NVDA", kind="long_shares", entry_cost=100.0, max_loss=5.0,
                      implied_move=0.03, days_to_expiry=5.0, legs=(("NVDA", 1, 100.0),),
                      quote={"bid": 99.9, "ask": 100.1})
h2_live = runner.contract_for(_f, _s, 10)
ok0d = check("  and the LIVE stamp takes its horizon from the FORECAST, not from the 3",
             int(h2_live["expected_horizon_sessions"]) == 5
             and int(h2_live["min_normal_hold_sessions"]) == 0,
             str({k: h2_live[k] for k in ("expected_horizon_sessions",
                                          "min_normal_hold_sessions", "profile")}))
h2_stop = contract_mod.from_payload(h2_live, book="hack2").stop_fraction()
ok0e = check("  the stop width is the AGGRESSIVE profile width, 3%",
             abs(h2_stop - equity_mod.STOP_FRACTION_BY_PROFILE["aggressive"]) < 1e-12,
             f"{h2_stop}")
FINDINGS.append({
    "question": "is hack2's contract the EVENT defaults?",
    "answer": "YES in shape, with two qualifications that matter more than the label",
    "detail": {
        "defaults_for('hack2')": {k: (list(v) if isinstance(v, tuple) else v)
                                  for k, v in h2_defaults.items()},
        "identical_to_event_defaults_field_for_field": same_shape,
        "live_stamp_from_runner.contract_for": {
            k: (list(v) if isinstance(v, tuple) else v) for k, v in h2_live.items()},
        "qualification_1": (
            "the HORIZON is not 3. `runner.contract_for` replaces it with "
            "ceil(forecast.horizon_days) for any role outside TRACKER_BOOKS, so hack2's "
            "sealed term is whatever post_event_drift declared on the day -- 5 in this "
            "probe. The '3' in defaults_for is only reached when the brain declares "
            "nothing."),
        "qualification_2": (
            "min_normal_hold_sessions is ZERO. hack2 therefore has NO minimum hold, so "
            "the S39 repair -- 'before the minimum hold only a typed reason may close' -- "
            "imposes nothing at all on this book. Every exit on hack2 is a NORMAL exit "
            "and is legal on session 1. That is a DECLARED property of an event book "
            "(its horizon IS the thesis), not a defect -- but it means hack2 cannot be "
            "used as evidence that the hold rule works, and the 60%-same-session "
            "measurement that motivated the rule would still read 60% on this book."),
        "qualification_3": (
            "hack2 is tier SAFE and manage_only=False, so the loop MAY originate on it "
            "(unlike hack1). Its allow_short is False, enforced since 2026-09-04."),
        "stop_fraction": h2_stop,
        "profile": fleet.FLEET["hack2"].profile,
    }})

# ===========================================================================
print("\nC2-1  200 SEEDED PATHS x 21 SESSIONS, PER (ROLE, PROFILE) CELL")
# ===========================================================================
CELLS = [
    ("hack1", "conservative"), ("hack2", "aggressive"), ("hack3", "basket"),
    ("hack4", "maximum"), ("hack5", "convex"), ("hack6", "aggressive"),
]
REPORT: list[dict] = []
violations_hold: list[str] = []
violations_stop: list[str] = []
violations_spurious: list[str] = []

for cell_i, (role, profile) in enumerate(CELLS):
    os.environ["AAT_ACCOUNT_ROLE"] = role
    os.environ["AAT_RISK_PROFILE"] = profile
    stop_frac = equity_mod.stop_fraction(profile)
    d = contract_mod.defaults_for(role, profile=profile)
    hold = int(d["min_normal_hold_sessions"])
    horizon_declared = int(d["expected_horizon_sessions"])
    row = entry_row("SYN", role, horizon_days=float(N_SESSIONS))
    rows = [row]
    # The contract the exit pass will actually resolve for this cell.
    k = contract_mod.resolve(row, day=session_datetime(1).date().isoformat(), profile=profile)
    horizon = int(k.expected_horizon_sessions)
    hold = int(k.min_normal_hold_sessions)

    rng = np.random.default_rng(SEED + cell_i)
    P = paths(rng, N_PATHS, N_SESSIONS, daily_sd=0.025)

    closes, codes, stop_hits, stop_correct, early_typed, early_untyped = 0, {}, 0, 0, 0, 0
    held_for: list[int] = []
    for pi in range(N_PATHS):
        for si in range(N_SESSIONS):
            plpc = float(P[pi, si])
            now = session_datetime(si + 1)
            v = exits.evaluate(position("SYN", plpc), deadline_utc=DEADLINE,
                               now=now, rows=rows)
            elapsed = exits._sessions_since(row["ts_utc"], (now + exits.ET_OFFSET).date())
            crossed = plpc <= -stop_frac
            if crossed:
                stop_hits += 1
                # B. the stop fires at the PROFILE width, booked HARD_RISK_LIMIT
                if v.close and v.code == "HARD_RISK_LIMIT":
                    stop_correct += 1
                else:
                    violations_stop.append(
                        f"{role}/{profile} path {pi} s{si}: plpc {plpc:+.4f} past "
                        f"-{stop_frac:.0%} but code={v.code} close={v.close}")
            if v.close:
                closes += 1
                held_for.append(elapsed)
                codes[v.code] = codes.get(v.code, 0) + 1
                # A. before the minimum hold, ONLY a typed emergency reason
                if elapsed < hold:
                    if v.code in contract_mod.EMERGENCY_EXIT_REASONS:
                        early_typed += 1
                    else:
                        early_untyped += 1
                        violations_hold.append(
                            f"{role}/{profile} path {pi}: closed on session {elapsed + 1} "
                            f"of a {hold}-session minimum hold with code={v.code!r} "
                            f"(plpc {plpc:+.4f})")
                break
            # C. a HOLD inside the stop, inside the horizon, before the hold, is
            #    the only legal answer -- and it must not be an accident of code.
            if (not crossed and elapsed < hold and v.code != "HELD"):
                violations_spurious.append(
                    f"{role}/{profile} path {pi} s{si}: not closed but code={v.code!r}")

    REPORT.append({
        "role": role, "profile": profile, "seed": SEED + cell_i,
        "paths": N_PATHS, "sessions": N_SESSIONS,
        "stop_fraction": stop_frac,
        "declared_horizon_sessions": horizon_declared,
        "resolved_horizon_sessions": horizon,
        "min_normal_hold_sessions": hold,
        "contract_source": k.source,
        "paths_that_closed": closes,
        "exit_codes": dict(sorted(codes.items())),
        "session_observations_past_the_stop": stop_hits,
        "of_those_booked_HARD_RISK_LIMIT": stop_correct,
        "closes_before_min_hold_typed": early_typed,
        "closes_before_min_hold_UNTYPED": early_untyped,
        "hold_rule_is_vacuous_on_this_book": hold == 0,
        # THE S39 NUMBER, RE-MEASURED ON SYNTHETIC PATHS. "60% of the fleet's
        # round trips finished in the same session they opened" is what the
        # contract work was built to fix; this is the same statistic computed
        # under the CURRENT rule, on a market with no drift at all.
        "median_sessions_held": (sorted(held_for)[len(held_for) // 2] if held_for else None),
        "share_closed_on_session_1_or_2": (
            round(sum(1 for e in held_for if e <= 1) / len(held_for), 3) if held_for else None),
    })
    _med = sorted(held_for)[len(held_for) // 2] if held_for else None
    _s12 = (sum(1 for e in held_for if e <= 1) / len(held_for)) if held_for else 0.0
    print(f"  {role:<6} {profile:<13} stop {stop_frac:.0%}  hold {hold:>2}  "
          f"horizon {horizon:>2}  closed {closes:>3}/{N_PATHS}  "
          f"past-stop {stop_hits:>4} -> HARD_RISK_LIMIT {stop_correct:>4}  "
          f"median hold {str(_med):>3} sessions  <=2 sessions {_s12:.0%}  "
          f"early: {early_typed} typed / {early_untyped} UNTYPED")

ok1 = check("A. no path closed before its minimum hold without a TYPED reason",
            not violations_hold, "; ".join(violations_hold[:3]))
ok2 = check("B. every session past the profile-width stop closed as HARD_RISK_LIMIT",
            not violations_stop, "; ".join(violations_stop[:3]))
ok3 = check("C. no spurious code on a path that was held",
            not violations_spurious, "; ".join(violations_spurious[:3]))
ok4 = check("  the stop actually FIRED somewhere (an assertion that never binds "
            "is not an assertion)",
            sum(r["session_observations_past_the_stop"] for r in REPORT) > 100,
            str([r["session_observations_past_the_stop"] for r in REPORT]))
ok5 = check("  and the stop width DIFFERS by profile (3% / 6% / 8%), not a flat 3%",
            len({r["stop_fraction"] for r in REPORT}) >= 3,
            str(sorted({r["stop_fraction"] for r in REPORT})))

vacuous = [r["role"] for r in REPORT if r["hold_rule_is_vacuous_on_this_book"]]
ok6 = check("  assertion A is VACUOUS on the event books, and this test says so "
            "rather than counting their silence as a pass",
            set(vacuous) == {"hack1", "hack2", "hack5"},
            f"books with min_normal_hold_sessions == 0: {vacuous}")

# ===========================================================================
print("\nC2-2  THE HOLD RULE BINDS WHERE IT IS SUPPOSED TO")
# ===========================================================================
# The tracker books declare hold=10. A path that wanders inside the stop for
# ten sessions must produce NO close at all -- that is the whole S39 repair, and
# a deterministic path proves it without leaning on the RNG.
os.environ["AAT_ACCOUNT_ROLE"] = "hack3"
os.environ["AAT_RISK_PROFILE"] = "basket"
row = entry_row("SYN", "hack3", horizon_days=21.0)
inside = [0.02, -0.02, 0.04, -0.05, 0.06, -0.06, 0.03, -0.03, 0.05, -0.04]
verdicts = [exits.evaluate(position("SYN", p), deadline_utc=DEADLINE,
                           now=session_datetime(i + 1), rows=[row])
            for i, p in enumerate(inside)]
ok7 = check("ten sessions of +-6% inside an 8% basket stop close NOTHING",
            not any(v.close for v in verdicts),
            str([(v.close, v.code) for v in verdicts if v.close][:3]))
ok8 = check("  and every one of them is coded HELD, not left untyped",
            all(v.code == "HELD" for v in verdicts))
# ... and the same book at -9% closes on session 1, because the stop outranks
# the hold and always did.
v_stop = exits.evaluate(position("SYN", -0.09), deadline_utc=DEADLINE,
                        now=session_datetime(1), rows=[row])
ok9 = check("  but -9% on session 1 closes immediately as HARD_RISK_LIMIT",
            v_stop.close and v_stop.code == "HARD_RISK_LIMIT", v_stop.reason[:120])
ok10 = check("  and the old FLAT 3% would have closed on session 4 (-5%): "
             "the width is the profile's, not a constant",
             not exits.evaluate(position("SYN", -0.05), deadline_utc=DEADLINE,
                                now=session_datetime(4), rows=[row]).close)

# ===========================================================================
print("\nC2-3  EVERY EXIT CODE THE ADVERSARY PRODUCED IS IN THE ENUM")
# ===========================================================================
seen = sorted({c for r in REPORT for c in r["exit_codes"]} | {"HELD"})
ok11 = check("every code observed over 1,200 paths is a declared EXIT_REASON",
             all(c in contract_mod.EXIT_REASONS for c in seen), str(seen))
ok12 = check("  and the emergency/normal split is the one contract.py declares",
             set(contract_mod.EMERGENCY_EXIT_REASONS).isdisjoint(
                 contract_mod.NORMAL_EXIT_REASONS))

# ===========================================================================
RECEIPT = (os.path.dirname(os.path.abspath(__file__)) +
           "/state/labor_day_lab_2026-09-07/C2_exit_adversary.json")


def write_receipt() -> None:
    import subprocess
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                cwd=os.path.dirname(os.path.abspath(__file__)),
                                timeout=30).stdout.strip()
    except Exception:                                                   # noqa: BLE001
        commit = "unknown"
    os.makedirs(os.path.dirname(RECEIPT), exist_ok=True)
    with open(RECEIPT, "w", encoding="utf-8") as fh:
        json.dump({
            "item": "C2", "lane": "C", "lab": "labor_day_lab_2026-09-07",
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "argv": sys.argv, "git_commit": commit,
            "config": {"seed_base": SEED, "paths_per_cell": N_PATHS,
                       "sessions": N_SESSIONS, "innovation": "student-t(df=4), daily sd 2.5%",
                       "entry_utc": ENTRY_UTC.isoformat(), "deadline_utc": DEADLINE,
                       "network": "no venue client is constructed at all",
                       "AAT_LEDGER_DIR": os.environ["AAT_LEDGER_DIR"]},
            "inputs_opened": ["(none -- every path is generated from the seed above; "
                              "the only file this suite touches is its own receipt)"],
            "modules_under_test": ["alpha.exits", "alpha.contract", "alpha.engine.equity",
                                   "alpha.runner.contract_for", "alpha.fleet"],
            "cells": REPORT,
            "assertions": {
                "A_no_close_before_min_hold_without_a_typed_reason":
                    {"violations": violations_hold, "pass": not violations_hold},
                "B_stop_fires_at_profile_width_booked_HARD_RISK_LIMIT":
                    {"violations": violations_stop, "pass": not violations_stop},
                "C_no_spurious_code_on_a_held_path":
                    {"violations": violations_spurious, "pass": not violations_spurious},
            },
            "hack2_contract": FINDINGS,
            "checks_run": ran, "checks_failed": len(fails), "failed": fails,
        }, fh, indent=2, default=str)
    print(f"\nreceipt: {RECEIPT}")


write_receipt()
print("\n" + "=" * 72)
print(f"C2 exit adversary: {ran} checks, {len(fails)} failed, "
      f"{N_PATHS * len(CELLS)} paths x {N_SESSIONS} sessions")
if fails:
    print("FAILED: " + ", ".join(fails))
    sys.exit(1)
print("ALL PASS")
