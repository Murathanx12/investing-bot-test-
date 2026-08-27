"""HUMAN_THESIS_ARM_v1 + CLAIM_EXPRESSION_MATRIX_v1, replayed against 26 Aug NVDA.

The case: Murat said NVDA would beat before the print. The books held broad
index straddles and a peer straddle on AMD. NVDA guided Q3 to $108.0bn against
$104.2bn and rose ~6.8% against a ~5.4% implied move.

These checks ask two things:
  1. can that view enter the machine at all, typed, before the catalyst;
  2. once it is in, is it structurally barred from buying a sign-blind payoff.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

fails: list[str] = []
ran = 0


def check(name: str, cond: bool, why: str = "") -> None:
    global ran
    ran += 1
    if cond:
        print(f"  ok   {name}")
    else:
        fails.append(name)
        print(f"  FAIL {name}  {why}")


print("human thesis arm + claim/expression matrix")

_tmp = tempfile.mkdtemp(prefix="aat_human_")
os.environ["AAT_LEDGER_DIR"] = _tmp

from alpha import claims, human                              # noqa: E402

human.STATE_DIR = Path(_tmp)

NOW = datetime.now(timezone.utc)
SOON = (NOW + timedelta(hours=6)).isoformat()


def thesis(**kw):
    base = dict(author="murat", symbol="NVDA", direction="up", magnitude="unknown",
                catalyst="Q2 FY27 print", catalyst_at_utc=SOON, horizon_days=3.0,
                reason="AI demand accelerating faster than the guide implies",
                falsifier="Q3 revenue guide at or below $104bn, or a Q3 GM guide below 74%",
                expected_move=0.06, conviction=0.9)
    base.update(kw)
    return human.Thesis(**base)


def refuses(**kw):
    try:
        thesis(**kw)
        return None
    except human.ThesisRefusal as exc:
        return str(exc)


# --- the thesis can be stated ----------------------------------------------
t = thesis()
check("the 26 Aug NVDA view is expressible as a typed thesis", t.symbol == "NVDA")
check("a direction-only thesis maps to claim='direction'", t.claim == "direction",
      f"got {t.claim!r}")
check("it enters under its own brain name, not anonymously", t.brain == "human:murat")

both = thesis(magnitude="wider")
check("direction + width maps to claim='distribution'", both.claim == "distribution")
width_only = thesis(direction="none", magnitude="narrower", expected_move=None)
check("width-only maps to claim='dispersion'", width_only.claim == "dispersion")

# --- what it refuses --------------------------------------------------------
check("'up' with no expected move is REFUSED",
      (r := refuses(expected_move=None)) is not None and "does not pick" in r, str(r))
check("  and the refusal explains WHY a number is needed (2% vs 9% buy opposites)",
      r is not None and "5.4%" in r and "opposite" in r)
check("a direction/expected-move sign disagreement is REFUSED",
      (r := refuses(direction="up", expected_move=-0.06)) is not None
      and "disagree on the sign" in r, str(r))
check("no direction AND no width claim is REFUSED",
      (r := refuses(direction="none", magnitude="unknown", expected_move=None)) is not None
      and "is not a thesis" in r, str(r))
check("a missing falsifier is REFUSED",
      (r := refuses(falsifier="looks good")) is not None and "falsifier is required" in r, str(r))
check("a thesis stated AFTER its own catalyst is REFUSED",
      (r := refuses(catalyst_at_utc=(NOW - timedelta(hours=1)).isoformat())) is not None
      and "is a memory" in r, str(r))
check("  and it says why backdating poisons the arm",
      r is not None and "calibration" in r)
check("direction='none' carrying a non-zero move is REFUSED",
      (r := refuses(direction="none", magnitude="wider", expected_move=0.06)) is not None
      and "wearing a width label" in r, str(r))

# --- the forecast it produces ----------------------------------------------
f = t.to_forecast()
check("the forecast carries the human's centre", abs(f.centre - 0.06) < 1e-9)
check("its sd is a PLACEHOLDER, flagged as one", f.evidence["sd_is_placeholder"] is True,
      "a human states which way and how far, never a sigma")
check("the falsifier travels onto the forecast", "104bn" in f.evidence["falsifier"])
check("the catalyst becomes an event_date, so the event-node cap sees it",
      f.evidence["event_date"] == SOON[:10])

wf = width_only.to_forecast(implied_move=0.054)
check("a width thesis is scaled off the CHAIN's implied move",
      abs(wf.sd - 0.054 * 0.75) < 1e-9, f"sd={wf.sd}")
try:
    width_only.to_forecast(implied_move=None)
    got = None
except human.ThesisRefusal as exc:
    got = str(exc)
check("a width thesis with NO chain width REFUSES rather than substituting realised vol",
      got is not None and "realised-vol" in got, str(got))

# --- persistence ------------------------------------------------------------
tid = human.record(t)
check("it is recorded append-only", human.path().exists() and len(tid) == 16)
check("and reloads", any(x.thesis_id() == tid for x in human.load_all()))
check("it is OPEN before its catalyst", any(x.thesis_id() == tid for x in human.open_theses()))
check("and CLOSED after it", not human.open_theses(NOW + timedelta(days=1)))
check("forecasts_for picks it up for the right symbol",
      len(human.forecasts_for(["NVDA", "AMD"])) == 1)
check("and not for others", human.forecasts_for(["AMD"]) == [])

# --- the module may not touch capital --------------------------------------
# Checked on the PARSED module, not on its text: the docstring says the words
# "broker" and "order" while explaining that it uses neither, and a substring
# search cannot tell an explanation from an import.
import ast                                                   # noqa: E402

tree = ast.parse(Path("alpha/human.py").read_text(encoding="utf-8"))
imported = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        imported.update(a.name for a in node.names)
    elif isinstance(node, ast.ImportFrom):
        imported.add(node.module or "")
        imported.update(f"{node.module}.{a.name}" for a in node.names)
check("alpha/human.py imports no broker", not any("broker" in m for m in imported),
      f"imports: {sorted(imported)}")
called = {n.func.attr for n in ast.walk(tree)
          if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
for verb in ("submit", "post", "place", "cancel"):
    check(f"alpha/human.py calls nothing named {verb!r}", verb not in called,
          "the human arm is a forecast source, never an order path")

# --- CLAIM_EXPRESSION_MATRIX ------------------------------------------------
check("a DIRECTION claim may NOT buy an iron condor",
      not claims.admissible("direction", "iron_condor"))
check("  and the refusal names the sign-blindness, with the NVDA measurement",
      "sign-blind" in claims.why_not("direction", "iron_condor")
      and "+0.72%" in claims.why_not("direction", "iron_condor"))
check("a DIRECTION claim may NOT buy a straddle",
      not claims.admissible("direction", "long_straddle"))
for kind in ("long_shares", "long_call", "bull_call_spread", "bull_put_spread",
             "bear_put_spread", "bear_call_spread", "short_shares", "long_put"):
    check(f"a DIRECTION claim MAY buy {kind}", claims.admissible("direction", kind),
          "the matrix removes what the claim cannot say, it does not pick the trade")
check("a DISPERSION claim may NOT buy shares", not claims.admissible("dispersion", "long_shares"))
check("a DISPERSION claim MAY buy a straddle", claims.admissible("dispersion", "long_straddle"))
check("a DISPERSION claim MAY sell a condor", claims.admissible("dispersion", "iron_condor"))
check("a DISTRIBUTION claim may buy anything it can defend",
      all(claims.admissible("distribution", k) for k in claims.KNOWN))
check("an UNKNOWN structure kind is admissible, not silently dropped",
      claims.admissible("direction", "some_new_structure_v9"),
      "a matrix that filters what it has not heard of is an invisible filter")
check("every structure the engine builds is classified",
      claims.unclassified(["long_call", "long_put", "bull_call_spread", "bear_put_spread",
                           "long_straddle", "bull_put_spread", "bear_call_spread",
                           "iron_condor", "long_shares", "short_shares"]) == [],
      "an unclassified kind means this file is out of date with structures.py")

# --- and it must be WIRED ---------------------------------------------------
rsrc = Path("alpha/runner.py").read_text(encoding="utf-8")
check("runner imports claims", "claims" in rsrc)
check("runner filters candidates on the matrix", "claims.admissible(" in rsrc)
i_claim = rsrc.find("claims.admissible(")
i_size = rsrc.find("verdict = sizing.size(")
check("filtered BEFORE sizing -- an inexpressible structure is never priced",
      -1 < i_claim < i_size, f"{i_claim} vs {i_size}")
check("the removed structures are RECORDED, not dropped in silence",
      "inexpressible" in rsrc and "rejected.append" in rsrc)

print(f"\n{ran} checks")
print("ALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
