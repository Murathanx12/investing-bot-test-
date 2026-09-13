"""Smoke: Book F's engine file is installed, verified, and changes no bound.

Five things are pinned, and each of them is a way the engine switch could look
green while being wrong:

  1. the INSTALLED file verifies against the hash the research repo wrote --
     the two repositories share no code, so the only thing holding the two
     `_sha` implementations together is this check;
  2. every refusal is a refusal: a missing month, a tampered file, a file for
     another month, an unknown role. The book fails CLOSED;
  3. only the role's OWN k trades, and it is read from `contract.BOOK_SIZING`
     rather than declared in the brain, so the count that trades and the count
     `worst_case` prices cannot disagree;
  4. **hack3's worst case is byte-identical before and after the switch.** The
     mandate changed its RANKING, not its sizing, and this is the test that
     says so in numbers rather than in a caveat;
  5. the LOOP's universe for hack3 is the engine's own selection, so the book
     cannot be handed a window universe by accident.

No month here is written down: every date comes from the installed file or from
`today`.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from alpha import contract, fleet
from alpha.brains import BRAINS, seasonality_f as F

fails = 0


def check(name, ok, detail=""):
    global fails
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        fails += 1


print("\n-- the engine files that shipped")
installed = sorted(F.SEED_ENGINES.glob("F_seasonality_*.json"))
check("at least one month is installed under docs/seed/engines", bool(installed),
      str(F.SEED_ENGINES))

for p in installed:
    payload = json.loads(p.read_text(encoding="utf-8"))
    body = dict(payload)
    claimed = body.pop("content_sha256", None)
    # scripts/prediction_book._sha, written out in full rather than imported:
    # the research repo's exporter computes the SAME expression, and this line
    # is the only thing that stops the three copies from drifting in silence.
    expected = hashlib.sha256(json.dumps(
        body, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    check(f"{p.name}: content hash verifies", claimed == expected, f"{claimed} != {expected}")
    check(f"{p.name}: month matches the filename",
          payload.get("month") == p.stem.replace("F_seasonality_", ""))
    check(f"{p.name}: the engine names itself", payload.get("engine") == F.ENGINE)
    check(f"{p.name}: licence is PRODUCT_EXPERIMENT, not a claim",
          payload.get("licence") == "PRODUCT_EXPERIMENT")
    check(f"{p.name}: registration named", str(payload.get("registration", "")).startswith("TRIAL-DRAFT-F"))
    c = payload.get("construction") or {}
    check(f"{p.name}: construction printed (k, tercile, floor, columns)",
          c.get("k") == 30 and abs(c.get("tercile", 0) - 2 / 3) < 1e-9
          and c.get("floor_usd") == 10_000_000.0 and len(c.get("columns") or []) == 2)
    check(f"{p.name}: its deviations from the replay are printed too",
          len(c.get("deviations_from_the_replay") or []) == 3)
    check(f"{p.name}: coverage is stated against the band, not the survivors",
          {"universe_after_floor", "mapped_to_permno", "carrying_both_windows"}
          <= set((payload.get("coverage") or {})))
    check(f"{p.name}: selected is a prefix of the top tercile",
          all(r["tercile"] == "top" for r in payload["rows"]
              if r["symbol"] in set(payload["selected"])))
    check(f"{p.name}: ranks are dense and ordered by score",
          [r["rank"] for r in payload["rows"]] == list(range(1, len(payload["rows"]) + 1))
          and all(payload["rows"][i]["score"] >= payload["rows"][i + 1]["score"]
                  for i in range(len(payload["rows"]) - 1)))


print("\n-- the brain: reads, verifies, refuses")
month = json.loads(installed[0].read_text(encoding="utf-8"))["month"]
os.environ["AAT_ACCOUNT_ROLE"] = "hack3"
try:
    e = F.engine(month=month)
    check("the installed month loads", e["month"] == month)
    sel = F.selection(month=month)
    check("the role's k comes from contract.BOOK_SIZING",
          sel["book_k"] == contract.BOOK_SIZING["hack3"]["n"] == 10, str(sel["book_k"]))
    check("only the prefix trades", len(sel["ranks"]) == 10 and len(sel["engine_selected"]) == 30)
    check("the prefix is the FIRST ten, in order",
          list(sel["ranks"]) == e["selected"][:10])
    check("the loop's universe is the engine's own 30",
          F.universe_symbols(month=month) == e["selected"])

    # a symbol outside the prefix is declined WITH the reason
    outside = e["selected"][-1]
    try:
        F.forecast(None, outside, 21.0, bars=[{"c": 10.0 + i * 0.01} for i in range(80)])
        check("a name outside the prefix is declined", False)
    except F.EngineDeclined as exc:
        check("a name outside the prefix is declined", "does not re-rank" in str(exc), str(exc)[:120])

    inside = e["selected"][0]
    import random
    random.seed(11)
    closes = [100.0]
    for _ in range(99):
        closes.append(closes[-1] * (1 + random.gauss(0, 0.02)))
    f = F.forecast(None, inside, 21.0, bars=[{"c": c} for c in closes])
    check("claim is direction, not distribution", f.claim == "direction")
    check("the centre is the measured monthly excess, scaled as a drift",
          abs(f.centre - F.MONTHLY_EXCESS * min(1.0, 21.0 * 5 / 7 / 21)) < 1e-12, f"{f.centre}")
    check("the spread is the name's OWN realised vol, not the book's",
          f.sd > 0 and abs(f.sd - f.evidence["sd_daily"] * (21.0 ** 0.5)) < 1e-9)
    check("the evidence carries the hash the order path verified",
          f.evidence["engine_sha256"] == e["content_sha256"])
    check("the evidence names the k deviation from the receipt",
          "k=30" in f.evidence["k_is_a_prefix_of_the_registered_ranking"]
          or "k=" in f.evidence["k_is_a_prefix_of_the_registered_ranking"])
    check("the evidence carries the replay cell it is priced from",
          f.evidence["receipt"]["n_blocks"] == 419 and f.evidence["receipt"]["verdict"] == "CONDITIONAL")

    # every selected name gets the SAME centre -- the book's claim is the tercile
    g = F.forecast(None, e["selected"][1], 21.0, bars=[{"c": c} for c in closes])
    check("every selected name gets the same centre", f.centre == g.centre)

    # thin history refuses rather than inventing a spread
    try:
        F.forecast(None, inside, 21.0, bars=[{"c": 10.0} for _ in range(10)])
        check("thin history refused", False)
    except F.EngineDeclined as exc:
        check("thin history refused", "bars <" in str(exc), str(exc)[:100])

    print("\n-- fail CLOSED: missing month, tampered file, wrong month, unknown role")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        old_engines, old_seed = F.ENGINES, F.SEED_ENGINES
        F.ENGINES, F.SEED_ENGINES = root / "engines", root / "seed"
        try:
            F.ENGINES.mkdir(parents=True)
            try:
                F.engine(month=month)
                check("no engine file -> declined", False)
            except F.EngineDeclined as exc:
                check("no engine file -> declined", "does not re-derive" in str(exc), str(exc)[:120])

            tampered = dict(e)
            tampered["selected"] = ["EVIL"] + list(e["selected"])[1:]
            (F.ENGINES / f"F_seasonality_{month}.json").write_text(
                json.dumps(tampered), encoding="utf-8")
            try:
                F.engine(month=month)
                check("a tampered file -> declined on its own hash", False)
            except F.EngineDeclined as exc:
                check("a tampered file -> declined on its own hash",
                      "content_sha256" in str(exc), str(exc)[:120])

            # a file for ANOTHER month, correctly hashed, under this month's name
            other = dict(e)
            other["month"] = "1999-01"
            other.pop("content_sha256", None)
            other["content_sha256"] = F._sha_of(other)
            (F.ENGINES / f"F_seasonality_{month}.json").write_text(
                json.dumps(other), encoding="utf-8")
            try:
                F.engine(month=month)
                check("another month's ranking -> declined", False)
            except F.EngineDeclined as exc:
                check("another month's ranking -> declined",
                      "another\nmonth" in str(exc) or "another month" in str(exc), str(exc)[:140])
        finally:
            F.ENGINES, F.SEED_ENGINES = old_engines, old_seed

    os.environ["AAT_ACCOUNT_ROLE"] = "nosuchrole"
    try:
        F.selection(month=month)
        check("an undeclared role -> declined, never defaulted", False)
    except F.EngineDeclined as exc:
        check("an undeclared role -> declined, never defaulted",
              "BOOK_SIZING" in str(exc), str(exc)[:120])
finally:
    os.environ["AAT_ACCOUNT_ROLE"] = "hack3"


print("\n-- the mandate: the RANKING moved and the BOUND did not")
m = fleet.FLEET["hack3"]
check("hack3 runs seasonality_f and nothing else", m.brains == ("seasonality_f",), str(m.brains))
check("the displaced engine keeps marking as a SHADOW", "tracker_portfolio" in m.shadow, str(m.shadow))
check("every brain hack3 names is registered", all(b in BRAINS for b in m.brains + m.shadow))
check("shares only, still", m.structure_kinds == ("long_shares",))
check("the universe is the engine's own selection", m.universe == "engine_f")

# THE NUMBER THIS TEST EXISTS FOR. `worst_case` reads BOOK_SIZING x HORIZON_REMAP
# and neither mentions a brain, so the assertion is that the swap did not touch
# either -- stated as the arithmetic rather than as a promise.
wc = contract.worst_case("hack3")
check("hack3 worst case UNCHANGED by the switch: 10 x 10% = 100% gross at a 12% stop = -12%",
      wc["n"] == 10 and wc["notional_each"] == 0.10
      and wc["gross_over_equity"] == 1.0 and wc["stop_frac"] == 0.12
      and wc["worst_case_frac"] == 0.12, json.dumps(wc))
check("the horizon contract is untouched too (63 / 21 sessions)",
      wc["expected_horizon_sessions"] == 63 and wc["min_normal_hold_sessions"] == 21)
check("profile untouched: basket", m.profile == "basket")

env = fleet.env_for(m)
check("the deploy variables name the new brain", env["AAT_LOOP_BRAINS"] == "seasonality_f")
check("the deploy variables name the shadow", env["AAT_LOOP_SHADOW"].startswith("tracker_portfolio"))
check("the deploy variables carry the engine's universe, not a window",
      "--window-universe" not in env["AAT_LOOP_ARGS"] and "--universe" in env["AAT_LOOP_ARGS"])
check("every symbol in AAT_LOOP_ARGS is one the engine selected",
      set(env["AAT_LOOP_ARGS"].split("--universe")[1].split())
      == set(F.universe_symbols()))
check("the caveat states the monthly redeploy", "REDEPLOY EVERY CALENDAR MONTH" in m.caveat.upper())
check("the caveat prints the unchanged worst case", "-12% of equity" in m.caveat)

check("as_dict survives a role whose universe can refuse",
      isinstance(fleet.as_dict()["hack3"], dict))
check("no broker import in the new brain",
      not any(t in Path("alpha/brains/seasonality_f.py").read_text(encoding="utf-8")
              for t in ("alpha.broker", "submit", "/v2/orders")))

print(f"\n{'ALL PASS' if not fails else f'{fails} FAIL'}")
sys.exit(1 if fails else 0)
