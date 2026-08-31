"""Smoke: the fleet mandates are executable data, and the two fleet brains speak/refuse as declared."""
from __future__ import annotations

import json
import math
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from alpha import exits, fleet
from alpha.brains import BRAINS, council_vector, theme_basket
from alpha.engine import sizing

fails = 0


def check(name, ok, detail=""):
    global fails
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        fails += 1


print("\n-- fleet: six mandates, all executable")
check("six roles named hack1..hack6", list(fleet.FLEET) == [f"hack{i}" for i in range(1, 7)], str(list(fleet.FLEET)))
check("three tracker books (hack3/4/6) run the sealed selector, shares only",
      all(fleet.FLEET[r].brains == ("tracker_portfolio",) and fleet.FLEET[r].structure_kinds == ("long_shares",)
          for r in ("hack3", "hack4", "hack6")))
check("hack6's council blend survives as SHADOW (>=3 comparators)", len(fleet.FLEET["hack6"].shadow) >= 3)
check("hack3's adjudicated thesis brains survive as SHADOW", set(fleet.FLEET["hack3"].shadow) >= {"theme_basket", "murat_rule"})
check("1-2 safe, rest risky", 1 <= len(fleet.SAFE) <= 2 and len(fleet.RISKY) == 6 - len(fleet.SAFE), f"{fleet.SAFE} {fleet.RISKY}")
for r, m in fleet.FLEET.items():
    check(f"{r}: role name valid", r == r.lower() and r.replace("_", "").isalnum() and r not in ("dev", "competition"))
    check(f"{r}: brains registered", all(b in BRAINS for b in m.brains + m.shadow), str(m.brains + m.shadow))
    check(f"{r}: profile exists", m.profile in sizing.PROFILES, m.profile)
    check(f"{r}: gated profile needs explicit allow", m.profile not in sizing.GATED_PROFILES or m.allow_maximum)
    check(f"{r}: objective valid", m.rank_objective in (None, "mean", "median"))
    args = fleet.loop_args(m)
    check(f"{r}: loop args start with --brains", args[:2] == ["--brains", ",".join(m.brains)], str(args[:4]))
    env = fleet.env_for(m)
    check(f"{r}: env names the role", env["AAT_ACCOUNT_ROLE"] == r and env["AAT_LOOP_BRAINS"] == ",".join(m.brains))
    check(f"{r}: env has no --brains in LOOP_ARGS", "--brains" not in env["AAT_LOOP_ARGS"] and "--shadow" not in env["AAT_LOOP_ARGS"], env["AAT_LOOP_ARGS"][:80])
    check(f"{r}: railway commands name the service", f"aat-loop-{r}" in fleet.railway_commands(m))
    if m.structure_kinds:
        check(f"{r}: kinds env", env.get("AAT_STRUCTURE_KINDS") == ",".join(m.structure_kinds))
check("safe roles never run a gated profile", all(fleet.FLEET[r].profile not in sizing.GATED_PROFILES for r in fleet.SAFE))
check("the thesis account is a BASKET (<=6% per name, many names)", fleet.FLEET["hack3"].profile == "basket" and sizing.PROFILES["basket"]["per_thesis"] <= 0.06)
check("an options-only mandate exists and excludes shares",
      any(m.structure_kinds and "long_shares" not in m.structure_kinds and all("call" in k or "put" in k for k in m.structure_kinds)
          for m in fleet.FLEET.values()))
tpl = fleet.env_template()
check("env template lists every role's key pair", all(f"AAT_{r.upper()}_KEY_ID=" in tpl for r in fleet.FLEET))
check("env template has no secrets filled", all(line.endswith("=") for line in tpl.splitlines() if line.startswith("AAT_")))

print("\n-- theme seed: verified on the venue, and the caveat travels")
seed = json.loads(fleet.THEMES_SEED.read_text(encoding="utf-8"))
check("seed carries the survivorship caveat", "survivorship" in seed.get("caveat", ""))
check("tradable subset non-empty and options subset within it", len(seed["tradable"]) >= 20 and set(seed["with_options"]) <= set(seed["tradable"]))
check("every tradable name passed the venue screen",
      all(any(v["symbol"] == s and v["ok"] for t in seed["themes"].values() for v in t["verified"]) for s in seed["tradable"]))
check("no mega-cap or index ETF in the basket", not ({"SPY", "QQQ", "IWM", "NVDA", "AAPL", "MSFT"} & set(seed["tradable"])))
check("fleet reads the seed", set(fleet.theme_symbols()) == set(seed["tradable"])
      and set(fleet.theme_symbols(with_options_only=True)) == set(seed["with_options"]))

print("\n-- theme_basket: a human prior, labelled")


def bars(closes):
    return [{"c": c, "v": 1e6} for c in closes]


sym = seed["tradable"][0]
steady = [10.0 * (1 + 0.002 * ((i * 7) % 5 - 2)) for i in range(80)]
f = theme_basket.forecast(None, sym, 5.0, bars=bars(steady))
check("claim is direction, not distribution", f.claim == "direction")
check("centre = +tilt * sd", math.isclose(f.centre, f.evidence["tilt_sigma"] * f.sd, rel_tol=1e-9))
check("evidence says measured_edge None and who stated it", f.evidence["measured_edge"] is None and f.evidence["stated_by"] == "murat")
check("themes named", bool(f.evidence["themes"]))
try:
    theme_basket.forecast(None, "SPY", 5.0, bars=bars(steady))
    check("SPY refused (not in basket)", False)
except theme_basket.NotInBasket:
    check("SPY refused (not in basket)", True)
import random
random.seed(3)
noisy = [100.0]
for i in range(79):
    noisy.append(noisy[-1] * (1 + random.gauss(0, 0.07)))          # ~110% annualised vol
middle = noisy[:60] + [noisy[59] * (1 - 0.30 * i / 20) for i in range(1, 21)]   # -30% in 20 sessions
try:
    theme_basket.forecast(None, sym, 5.0, bars=bars(middle))
    check("MIDDLE cell (-30% at high vol) declined with the number", False)
except theme_basket.NotInBasket as exc:
    check("MIDDLE cell (-30% at high vol) declined with the number", "-0.31%" in str(exc), str(exc))
deep = noisy[:60] + [noisy[59] * (1 - 0.60 * i / 20) for i in range(1, 21)]     # -60% in 20 sessions
try:
    theme_basket.forecast(None, sym, 5.0, bars=bars(deep))
    check("DEEP cell (-60%) declined too -- its +2.32% was a >=5-names artefact", False)
except theme_basket.NotInBasket as exc:
    check("DEEP cell (-60%) declined too -- its +2.32% was a >=5-names artefact", "-0.63%" in str(exc), str(exc))
check("steady near-high name bought at half tilt", f.evidence["cell"].startswith("near-high") and f.evidence["tilt_sigma"] == theme_basket.TILT_SIGMA * 0.5)
try:
    theme_basket.forecast(None, sym, 5.0, bars=bars(steady[:20]))
    check("thin history refused", False)
except theme_basket.NotInBasket:
    check("thin history refused", True)

print("\n-- council_vector: reads the synthesis, refuses at every named stage")
ok_packet = {"symbol": "S", "verdict": "OK", "skeptic_independent": True, "families_used": ["deepseek", "zhipu"],
             "steps": {"synthesis": {"direction": "up", "magnitude": 0.06, "p_already_priced": 0.3, "timing": "days",
                                     "causal_confidence": 0.7, "falsifier": "ARR guide cut"}}}
f = council_vector.forecast(None, "S", 5.0, bars=bars(steady), packet=ok_packet)
check("centre = +mag*(1-priced)", math.isclose(f.centre, 0.06 * 0.7, rel_tol=1e-9), f"{f.centre}")
check("direction claim", f.claim == "direction" and f.evidence["falsifier"] == "ARR guide cut")
for label, mut in [("light verdict", {"verdict": "LIGHT"}), ("dependent skeptic", {"skeptic_independent": False})]:
    try:
        council_vector.vector_from({**ok_packet, **mut})
        check(f"refuses {label}", False)
    except council_vector.NoCouncil:
        check(f"refuses {label}", True)
for label, syn in [("direction none", {"direction": "none", "forced_none": "cube has zero comparable cells"}),
                   ("timing quarters", {"timing": "quarters"}), ("already priced", {"p_already_priced": 0.9}),
                   ("zero magnitude", {"magnitude": 0})]:
    pk = {**ok_packet, "steps": {"synthesis": {**ok_packet["steps"]["synthesis"], **syn}}}
    try:
        council_vector.vector_from(pk)
        check(f"refuses {label}", False)
    except council_vector.NoCouncil as exc:
        check(f"refuses {label}", True, str(exc))
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    # The ET TRADING day, not the UTC date. Writing the packet under the UTC
    # date made this suite pass for twenty hours a day and fail for the four
    # when UTC is already tomorrow and ET is not -- which is when it failed,
    # on 2026-08-30 at 00:5x UTC. Same definition as the writer and reader.
    day = exits.session_day()
    (root / "council" / day).mkdir(parents=True)
    (root / "council" / day / "S.json").write_text(json.dumps(ok_packet), encoding="utf-8")
    pk = council_vector.latest_packet("S", state=root)
    check("latest packet found by day folder", pk["symbol"] == "S" and bool(pk["_packet_day"]))
    try:
        council_vector.latest_packet("WDAY", state=root)
        check("no packet -> refusal", False)
    except council_vector.NoCouncil:
        check("no packet -> refusal", True)

print("\n-- runner: the kinds filter is applied AFTER the share structure joins")
src = Path("alpha/runner.py").read_text(encoding="utf-8")
i_share, i_filter, i_matrix = (src.find("candidates.append(share)"), src.find("AAT_STRUCTURE_KINDS"),
                               src.find("CLAIM_EXPRESSION_MATRIX (alpha/claims.py)"))
i_fn = src.find("def share_structure(")
check("share_structure tolerates snapshot=None (spot from the stock snapshot)",
      "snapshot.spot if snapshot is not None else 0.0" in src[i_fn:i_fn + 2500] and "latestTrade" in src[i_fn:i_fn + 2500])
i_ch = src.find("except chain_mod.ChainRefusal:")
check("chain refusal is tolerated for any direction claim", 'forecast.claim != "direction"' in src[i_ch:i_ch + 700])
check("order: share append < kinds filter < claim matrix", 0 < i_share < i_filter < i_matrix, f"{i_share} {i_filter} {i_matrix}")
check("no broker import in fleet brains",
      not any(t in Path(p).read_text(encoding="utf-8")
              for p in ("alpha/brains/theme_basket.py", "alpha/brains/council_vector.py", "alpha/fleet.py")
              for t in ("alpha.broker", "submit", "/v2/orders")))

print("\n-- daybreak: a NEW account (last_equity=0) derives day-one drawdown from genesis, or refuses")
import os

from alpha import daybreak, genesis


class _C:
    def __init__(self, eq, last):
        self._a = {"equity": str(eq), "last_equity": str(last)}

    def account(self):
        return self._a


with tempfile.TemporaryDirectory() as td:
    os.environ["AAT_ACCOUNT_ROLE"] = "fleettest"
    old_dir = genesis.STATE_DIR
    genesis.STATE_DIR = Path(td)
    try:
        st = daybreak.read(_C(100000, 0))
        check("no genesis -> refused, and names the missing step", st.latched and "genesis --freeze" in st.reason, st.reason)
        g = genesis.Genesis(role="fleettest", account_number="PA0", frozen_at_utc="t", starting_equity=100000.0,
                            position_count_at_genesis=0, order_count_at_genesis=0, rules_snapshot_path="r",
                            rules_snapshot_sha256="h", code_commit="c", competition={})
        genesis.path("fleettest").write_text(json.dumps(g.as_record()), encoding="utf-8")
        st = daybreak.read(_C(100000, 0))
        check("genesis present -> derived, not latched", st.derived and not st.latched and "GENESIS" in st.reason, st.reason)
        st = daybreak.read(_C(96500, 0))
        check("genesis present, -3.5% intraday -> latched", st.derived and st.latched and abs(st.drawdown + 0.035) < 1e-9, f"{st.drawdown}")
        st = daybreak.read(_C(100000, 100000))
        check("ordinary day untouched", st.derived and not st.latched and "GENESIS" not in st.reason)
    finally:
        genesis.STATE_DIR = old_dir
        os.environ.pop("AAT_ACCOUNT_ROLE", None)

print("\n-- sentinels: a direction brain is not judged on a width it never claims")
from alpha import sentinels

rows = [{"brain": "post_event_drift", "predicted_sd": 0.01, "implied_move": 0.05} for _ in range(60)]
rows += [{"brain": "vol_gap", "predicted_sd": 0.01, "implied_move": 0.05} for _ in range(60)]
rs = sentinels.ratios(rows)
check("post_event_drift is excluded from the width ratio", "post_event_drift" not in rs)
check("a width brain is still judged", "vol_gap" in rs and len(rs["vol_gap"]) == 60)
check("human theses are direction brains", sentinels.is_direction_brain("human:murat"))

print(f"\n{'ALL PASS' if not fails else f'{fails} FAIL'}")
sys.exit(1 if fails else 0)


# ---- 28 Aug live lesson: twelve tickers, one bet, one stop ---------------------
from alpha.engine import equity as _eq, sizing as _sz
from alpha import protect as _pt, runner as _rn
check("basket stop is ~1.3 daily sigma of a 100%-vol name, not 0.5", _eq.stop_fraction("basket") == 0.08)
check("safe profiles keep the 3% stop", _eq.stop_fraction("conservative") == 0.03 and _eq.stop_fraction("aggressive") == 0.03)
check("unknown profile falls back to the declared default", _eq.stop_fraction("nonsense") == _eq.STOP_FRACTION)
check("basket authority is ONE bet's size spread wide (12 x 3% = 36%)",
      _sz.PROFILES["basket"]["per_thesis"] == 0.03 and _sz.PROFILES["basket"]["aggregate"] == 0.36)
check("stopped_today is a refusal class", "stopped_today" in _rn.REFUSAL_CLASSES)


class _StopClient:
    def _request(self, m, path, **kw):
        assert kw["params"]["status"] == "closed" and "after" in kw["params"]
        return [{"symbol": "UEC", "status": "filled", "client_order_id": "aat-stop-abc"},
                {"symbol": "NVDA", "status": "filled", "client_order_id": "entry-xyz"},
                {"symbol": "SMR", "status": "canceled", "client_order_id": "aat-stop-def"}]


check("stopped_today = protective stops that FILLED today, nothing else", _pt.stopped_today(_StopClient()) == {"UEC"})
