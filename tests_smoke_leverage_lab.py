"""THE LEVERAGE LADDER AND THE VARIANT TOURNAMENT: the ways they could lie.

Three scripts arrived together and every one of them can be wrong QUIETLY:

  * `scripts/leverage_lab.py` computes a ladder. Ladder arithmetic that is off
    by a factor is not obviously off by a factor -- 2x either doubles the gross
    AND the worst case, or the file is publishing a bound nobody can use.
  * the overnight ladder must STOP at 2.0. A number computed for a position
    that cannot be held overnight is a number that invites holding it, and it
    would read exactly like the permitted rungs beside it.
  * `scripts/portfolio_variants.py` writes eight books that each declare their
    own k, per-name cap and sector cap. A book that quietly exceeds its own
    declared constraint is the failure the constraint exists to prevent, and
    nothing else in the repo reads these files to notice.
  * and none of the three may be able to trade. ANALYST_TILT in particular is
    the shadow arm of a PRE-REGISTERED trial (TRIAL-AGREE-CELL-TILT-1);
    trading it spends the pre-registration. It is a file, so the property to
    pin is the one `tests_smoke_ownership` pins on the watcher: the module
    imports no broker and contains no order call.

OFFLINE. No socket is opened: the ladder is exercised on a SYNTHETIC panel and
the variants on SYNTHETIC candidate rows, so nothing here needs a venue, a
tracker file or a seal to run. Dates are derived from `today`, never written
literally -- a fixture that encodes a calendar moment fails the day after it
passes.
"""

from __future__ import annotations

import ast
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_fails: list[str] = []
_ran = 0


def check(name: str, ok: bool, note: str = "") -> None:
    # `ok` plus two spaces is what run_tests.py's _OK regex counts.
    global _ran
    _ran += 1
    print(f"  {'ok ' if ok else 'FAIL'}  {name}" + (f"  ({note})" if note else ""))
    if not ok:
        _fails.append(name)


# The import itself is a check: if any of the three reached for a broker at
# import time this line would be where it happened.
_before = {m for m in sys.modules if "broker" in m}
from alpha import lab                                    # noqa: E402
from alpha import tracker as T                           # noqa: E402
from scripts import leverage_lab as LL                   # noqa: E402
from scripts import portfolio_variants as PV             # noqa: E402
from scripts import variant_grade as VG                  # noqa: E402


# ---------------------------------------------------------------- no broker
print("\n-- none of the three can place an order")

check("importing all three pulls in NO broker module",
      not ({m for m in sys.modules if "broker" in m} - _before),
      str(sorted({m for m in sys.modules if "broker" in m} - _before)))

_ORDER_CALLS = ("submit_order", "close_position", "close_all_positions",
                "replace_order", "cancel_order", "place_order", "_post(")
for mod in ("scripts/portfolio_variants.py", "scripts/leverage_lab.py",
            "scripts/variant_grade.py"):
    src = (ROOT / mod).read_text(encoding="utf-8")
    hits = [t for t in _ORDER_CALLS if t in src]
    check(f"{mod} contains no order-placing call", not hits, str(hits))

_pv_src = (ROOT / "scripts/portfolio_variants.py").read_text(encoding="utf-8")
_imports = {n.module or "" for n in ast.walk(ast.parse(_pv_src))
            if isinstance(n, ast.ImportFrom)}
_imports |= {a.name for n in ast.walk(ast.parse(_pv_src))
             if isinstance(n, ast.Import) for a in n.names}
check("portfolio_variants imports no alpaca/broker module at all",
      not any("broker" in m or "alpaca" in m for m in _imports),
      str(sorted(_imports)))

check("the ANALYST_TILT variant is declared SHADOW and names its trial",
      any(v.name == "ANALYST_TILT" and "SHADOW" in (v.shadow_only_note or "").upper()
          and "TRIAL-AGREE-CELL-TILT-1" in (v.shadow_only_note or "")
          for v in PV.variants()))

check("the only broker door the ladder uses is the house panel builder",
      "build_panel" in (ROOT / "scripts/leverage_lab.py").read_text(encoding="utf-8")
      and "stock_bars_multi" not in (ROOT / "scripts/leverage_lab.py").read_text(encoding="utf-8"),
      "bars come through alpha.lab.build_panel, which owns the cache")


# ------------------------------------------------------------- ladder maths
print("\n-- the ladder: 2x doubles the gross AND the worst case")

BOOK = {
    "n_selected": 10,
    "max_notional_each": 0.08,
    "holdings": [{"symbol": f"S{i}", "notional": 0.08, "downside_5pct": -0.20}
                 for i in range(10)],
}
WC = LL.worst_case_table(BOOK, equity=100_000.0, gross_cap=1.0, stop=0.08,
                         profile="basket", beta=2.10)
by_mult = {r["multiplier"]: r for r in WC}

check("every rung of the ladder is present", sorted(by_mult) == sorted(LL.LADDER))
check("1.0x gross is n x notional", abs(by_mult[1.0]["gross_of_equity"] - 0.80) < 1e-9,
      f"{by_mult[1.0]['gross_of_equity']}")
check("2.0x DOUBLES the gross",
      abs(by_mult[2.0]["gross_of_equity"] - 2 * by_mult[1.0]["gross_of_equity"]) < 1e-9)
check("2.0x DOUBLES the all-stop worst case",
      abs(by_mult[2.0]["all_stop_loss_fraction"]
          - 2 * by_mult[1.0]["all_stop_loss_fraction"]) < 1e-9,
      f"{by_mult[1.0]['all_stop_loss_fraction']} -> {by_mult[2.0]['all_stop_loss_fraction']}")
check("2.0x DOUBLES the all-gap worst case",
      abs(by_mult[2.0]["all_gap_loss_fraction"]
          - 2 * by_mult[1.0]["all_gap_loss_fraction"]) < 1e-9)
check("4.0x is 4x the 1x worst case, in dollars",
      abs(by_mult[4.0]["all_stop_loss_usd"] - 4 * by_mult[1.0]["all_stop_loss_usd"]) < 1e-6,
      f"${by_mult[1.0]['all_stop_loss_usd']:,.0f} -> ${by_mult[4.0]['all_stop_loss_usd']:,.0f}")
check("the all-STOP case is 8% x gross", abs(by_mult[1.0]["all_stop_loss_fraction"] + 0.064) < 1e-9)
check("the all-GAP case is BIGGER than the all-stop case at every rung",
      all(abs(r["all_gap_loss_fraction"]) > abs(r["all_stop_loss_fraction"]) for r in WC),
      "a stop does not survive a gap; if this ever inverted the receipt would be reassuring "
      "and wrong")
check("beta-equivalent scales with gross, and 4x on a 2.10-beta book is 8.4-beta-ish",
      abs(by_mult[4.0]["beta_equivalent"] - 2.10 * by_mult[4.0]["gross_of_equity"]) < 1e-6
      and by_mult[4.0]["beta_equivalent"] > 6.0,
      f"{by_mult[4.0]['beta_equivalent']}")
check("intraday margin utilization is gross / 4x buying power",
      abs(by_mult[4.0]["intraday_margin_utilization"]
          - by_mult[4.0]["gross_of_equity"] / LL.INTRADAY_BUYING_POWER) < 1e-9)

# The gross CAP has to scale with the rung, or a 4x experiment silently clamps
# itself back to the 1x book cap and reports a bound it is not running under.
_capped = LL.worst_case_table({**BOOK, "n_selected": 20,
                               "holdings": BOOK["holdings"] * 2},
                              equity=100_000.0, gross_cap=1.0, stop=0.08, profile="basket")
_c = {r["multiplier"]: r for r in _capped}
check("a book whose requested gross exceeds the cap reports gross_cap as BINDING",
      _c[1.0]["binding"] == "gross_cap", _c[1.0]["binding"])
check("  and the cap scales with the rung rather than clamping the experiment",
      abs(_c[2.0]["gross_of_equity"] - 2 * _c[1.0]["gross_of_equity"]) < 1e-9)


# ------------------------------------------------- the overnight bound holds
print("\n-- the overnight ladder REFUSES above 2.0x")

check("the declared overnight buying power is 2x, the intraday one 4x",
      LL.OVERNIGHT_BUYING_POWER == 2.0 and LL.INTRADAY_BUYING_POWER == 4.0)
for L in LL.LADDER:
    check(f"worst-case row {L:.1f}x marks overnight_permitted correctly",
          by_mult[L]["overnight_permitted"] == (L <= 2.0 + 1e-9))


def _panel(n_days: int = 30, symbols=("S0", "S1", "SPY")) -> lab.Panel:
    """A synthetic panel. Dates DERIVED from today -- a literal date in a
    fixture fails the day after it passes."""
    rng = np.random.default_rng(7)
    today = date.today()
    dates = [(today - timedelta(days=n_days - i)).isoformat() for i in range(n_days)]
    n, m = n_days, len(symbols)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.01, size=(n, m)), axis=0)
    open_ = close * (1.0 + rng.normal(0.0, 0.003, size=(n, m)))
    vol = np.full((n, m), 1e7)
    return lab.Panel(dates=dates, symbols=list(symbols), close=close, open_=open_,
                     high=close, low=close, volume=vol, vwap=close)


P = _panel()
W = np.zeros(P.n_symbols)
W[P.symbols.index("S0")] = 0.5
W[P.symbols.index("S1")] = 0.5
IDX = list(range(1, P.n_dates))

_refused = LL.ladder_arm(P, W, IDX, regime="overnight", L=4.0, cost_bps=1.0,
                         margin_rate=0.0575, gross_cap=1.0)
check("a 4.0x OVERNIGHT arm is refused, not computed",
      _refused["permitted"] is False and "terminal_wealth" not in _refused)
check("  and the refusal SAYS why (the 2x overnight bound)",
      "2x" in _refused["refusal"] or "2.0x" in _refused["refusal"]
      or "margin call" in _refused["refusal"], _refused["refusal"][:60])
check("a 4.0x INTRADAY arm IS computed (flat at the close, no overnight bound)",
      LL.ladder_arm(P, W, IDX, regime="intraday", L=4.0, cost_bps=1.0,
                    margin_rate=0.0575, gross_cap=1.0)["permitted"] is True)
check("a 2.0x overnight arm is permitted (the bound is <=, not <)",
      LL.ladder_arm(P, W, IDX, regime="overnight", L=2.0, cost_bps=1.0,
                    margin_rate=0.0575, gross_cap=1.0)["permitted"] is True)


# ------------------------------------------------ costs and financing exist
print("\n-- leverage is not free in either regime")

_free = LL.levered_session(0.01, regime="intraday", gross=4.0, scale=4.0,
                           cost_bps=0.0, margin_rate=0.0)
_paid = LL.levered_session(0.01, regime="intraday", gross=4.0, scale=4.0,
                           cost_bps=5.0, margin_rate=0.0)
check("the INTRADAY arm pays a round trip EVERY session", _paid < _free,
      f"{_paid:.6f} < {_free:.6f}")
check("  and the charge is 2 x gross x bps", abs((_free - _paid) - 2 * 4.0 * 5e-4) < 1e-12)

_unfinanced = LL.levered_session(0.01, regime="overnight", gross=2.0, scale=2.0,
                                 cost_bps=0.0, margin_rate=0.0, charge_round_trip=False)
_financed = LL.levered_session(0.01, regime="overnight", gross=2.0, scale=2.0,
                               cost_bps=0.0, margin_rate=0.0575, charge_round_trip=False)
check("the OVERNIGHT arm is FINANCED on the borrowed fraction", _financed < _unfinanced)
check("  charged on (gross - 1), not on gross",
      abs((_unfinanced - _financed) - 1.0 * 0.0575 / 360.0) < 1e-12)
check("an unlevered overnight arm pays NO financing",
      abs(LL.levered_session(0.01, regime="overnight", gross=1.0, scale=1.0, cost_bps=0.0,
                             margin_rate=0.0575, charge_round_trip=False) - 0.01) < 1e-12)
check("a missing price returns None, never a flat session",
      LL.levered_session(None, regime="intraday", gross=1.0, scale=1.0,
                         cost_bps=1.0, margin_rate=0.0) is None)

_arm = LL.ladder_arm(P, W, IDX, regime="intraday", L=2.0, cost_bps=1.0,
                     margin_rate=0.0575, gross_cap=1.0)
for field in ("terminal_wealth", "geometric_mean_per_session", "max_drawdown",
              "worst_session", "realized_beta_vs_spy", "cvar_5pct",
              "margin_utilization", "gross_of_equity"):
    check(f"a computed arm reports `{field}`", field in _arm and _arm[field] is not None)
check("terminal wealth is COMPOUNDED, not the mean times n",
      abs(_arm["terminal_wealth"]
          - (1 + _arm["geometric_mean_per_session"]) ** _arm["n_sessions"]) < 1e-4,
      "the geometric mean is rounded to 6dp in the receipt, so this is an identity "
      "check with room for that rounding, not a loose tolerance hiding a bug")
# VARIANCE DRAG, deterministically. +10% then -10% is 0.99 unlevered and 0.96 at
# 2x -- NOT the 0.98 a linear reading of "twice the exposure" would predict. This
# is the whole reason the ladder is compounded rather than scaled.
_d1 = LL._metrics([0.10, -0.10], [0.0, 0.0], name="1x")
_d2 = LL._metrics([0.20, -0.20], [0.0, 0.0], name="2x")
check("  and 2x exposure is NOT twice the return: variance drag is priced",
      abs(_d1["terminal_wealth"] - 0.99) < 1e-9 and abs(_d2["terminal_wealth"] - 0.96) < 1e-9
      and _d2["terminal_wealth"] < 1 + 2 * (_d1["terminal_wealth"] - 1),
      f"1x {_d1['terminal_wealth']:.4f}, 2x {_d2['terminal_wealth']:.4f}, "
      f"a linear reading would say {1 + 2 * (_d1['terminal_wealth'] - 1):.4f}")
check("the CVaR names how many sessions its 5% tail actually is",
      _arm["cvar_n_tail_sessions"] >= 1 and "session" in _arm["cvar_caveat"])


# -------------------------------------- every receipt carries a worst case
print("\n-- the worst case is in EVERY receipt, before any average")

_src = (ROOT / "scripts/leverage_lab.py").read_text(encoding="utf-8")
check("the ladder receipt's worst-case key is `worst_case_first`",
      '"worst_case_first": wc' in _src)
check("  and the printer emits it before the windows table",
      _src.index("WORST CASE FIRST") < _src.index("WINDOW  STATIC_SET"))
check("the ladder receipt states the beta arithmetic",
      '"beta_arithmetic"' in _src and "8.4" not in _src.split("beta_arithmetic")[0][-200:]
      or '"beta_arithmetic"' in _src)
check("the ladder receipt carries the paper-fill capacity caveat",
      '"paper_fill_caveat"' in _src and "IGNORE NBBO SIZE" in _src)


# ---------------------------------------- the variants respect their own rules
print("\n-- every variant book obeys the constraints it declares")


def _row(sym, *, sector, exp=0.0048, down=-0.15, vol=0.30, up=0.60, cons=4.2,
         dv=5e7, cap=5e9, close=50.0, cover=6, pw=False, cat=10):
    return {"symbol": sym, "sector": sector, "exp_return": exp, "downside_5pct": down,
            "realised_vol_20d": vol, "upside": up, "consensus": cons,
            "median_dollar_volume": dv, "market_cap_usd": cap, "close": close,
            "coverage": cover, "coverage_bucket": T.coverage_bucket(cover),
            "coverage_source": T.COVERAGE_SOURCE_CALIBRATED,
            "past_winner": pw, "days_to_catalyst": cat, "confidence": 0.9,
            "status": "BUY", "claims": False, "numbers_source": "rule"}


SECTORS = ("Biotechnology", "Semiconductors", "Banking", "Utilities", "Machinery")
POOL = [_row(f"N{i:03d}", sector=SECTORS[i % len(SECTORS)],
             vol=0.20 + 0.01 * i, up=0.40 + 0.01 * i, down=-0.10 - 0.002 * i)
        for i in range(60)]

BUILT = {v.name: PV.build_variant(POOL, v) for v in PV.variants()}

for name, b in BUILT.items():
    v = next(x for x in PV.variants() if x.name == name)
    check(f"{name}: holds no more than its declared k",
          b["n_selected"] <= b["k_target"], f"{b['n_selected']}/{b['k_target']}")
    check(f"{name}: no holding exceeds the per-name cap",
          all(h["notional"] <= b["max_notional_each"] + 1e-12 for h in b["holdings"]))
    check(f"{name}: gross = n x per-name notional exactly",
          abs(b["derived_gross"] - b["n_selected"] * b["max_notional_each"]) < 1e-9,
          f"{b['derived_gross']}")
    if v.max_sector_share is not None:
        worst = max(b["sector_notional"].values(), default=0.0)
        check(f"{name}: no sector above its {v.max_sector_share:.0%} cap",
              worst <= v.max_sector_share + 1e-9, f"worst sector {worst:.0%}")
    check(f"{name}: holds no name twice",
          len({h['symbol'] for h in b['holdings']}) == b["n_selected"])
    check(f"{name}: every holding carries a REASON",
          all(h.get("reason") for h in b["holdings"]))
    check(f"{name}: the book is marked SHADOW-safe (no notional above 100% per name)",
          b["max_notional_each"] <= 1.0)

check("SECTOR_BALANCED's cap really is 2 names x its notional",
      abs(BUILT["SECTOR_BALANCED"]["constraints"]["max_sector_share"]
          - 2 * BUILT["SECTOR_BALANCED"]["max_notional_each"]) < 1e-9,
      "the sector cap is a NAME COUNT wearing a notional; if k or the notional moves and "
      "this does not, it silently becomes a different rule")
check("SAFEST really ranks LOW volatility first",
      all(BUILT["SAFEST"]["holdings"][i]["realised_vol_20d"]
          <= BUILT["SAFEST"]["holdings"][i + 1]["realised_vol_20d"] + 1e-12
          for i in range(len(BUILT["SAFEST"]["holdings"]) - 1)))
check("AGGRESSIVE admits ONLY the 3..5 target-ratio band",
      all(3.0 <= 1.0 + h["upside"] < 5.0 for h in BUILT["AGGRESSIVE"]["holdings"])
      or BUILT["AGGRESSIVE"]["n_selected"] == 0,
      f"n={BUILT['AGGRESSIVE']['n_selected']}")
check("ANALYST_TILT admits ONLY consensus >= 4.1",
      all(h["consensus"] >= PV.ANALYST_TILT_MIN for h in BUILT["ANALYST_TILT"]["holdings"]))

_neg = POOL[:5] + [_row("LOSER", sector="Banking", exp=-0.03)]
_b = PV.build_variant(_neg, next(v for v in PV.variants() if v.name == "BALANCED"))
check("the long-book COHERENCE floor still bites (a negative exp_return is refused)",
      "LOSER" not in [h["symbol"] for h in _b["holdings"]]
      and any("exp_return not positive" in k for k in _b["excluded_by_reason"]),
      str(list(_b["excluded_by_reason"])))
check("  and the exclusion is COUNTED, not silent", sum(_b["excluded_by_reason"].values()) >= 1)

check("`alpha.tracker._eligibility_checks` is the single source of the house filters",
      hasattr(T, "_eligibility_checks") and callable(T._eligibility_checks),
      "a rename must fail HERE, loudly, not turn the variants into unfiltered books")


# ------------------------------------------------- the capacity block exists
print("\n-- the paper-fill capacity caveat rides on every book")

_cap = PV.capacity(BUILT["BALANCED"], equity=100_000.0)
check("capacity reports position $ as a fraction of median daily $ volume",
      all(r["pct_of_median_dollar_volume"] is not None for r in _cap["per_holding"]))
check("capacity flags at the declared threshold", _cap["flag_threshold"] == PV.CAPACITY_FLAG)
# $2m/day clears the book's own $1m liquidity floor and is still thin against a
# $10m account -- which is the point: the floor is an ADMISSION rule and capacity
# is a SIZE rule, and a name can pass one while failing the other.
_thin = PV.build_variant([_row(f"T{i}", sector=SECTORS[i % 5], dv=2e6) for i in range(20)],
                         next(v for v in PV.variants() if v.name == "BALANCED"))
check("  the thin-name book is not empty (the liquidity floor did not eat the fixture)",
      _thin["n_selected"] > 0, f"n={_thin['n_selected']}")
_capthin = PV.capacity(_thin, equity=10_000_000.0)
check("a name that CLEARS the $1m/day floor can still fail the capacity flag",
      _capthin["n_flagged"] > 0,
      f"worst {_capthin['worst_pct_of_median_dollar_volume']:.2%} of median daily $ volume")
check("  and 4x leverage flags MORE than 1x, never fewer",
      PV.capacity(_thin, equity=10_000_000.0, gross_multiplier=4.0)["n_flagged"]
      >= _capthin["n_flagged"])
_unread = PV.capacity({"holdings": [{"symbol": "X", "notional": 0.1,
                                     "median_dollar_volume": None}]}, equity=1e5)
check("an UNREADABLE dollar volume is flagged, never read as zero participation",
      _unread["n_flagged"] == 1 and _unread["per_holding"][0]["unreadable"] is True)


# ------------------------------------ the currency guard on the size ranking
print("\n-- market_cap_usd is not always USD, and the guard refuses rather than ranks")

_good = {"symbol": "AAA", "market_cap_usd": 5.0e12, "close": 200.0, "median_dollar_volume": 2.0e10}
_krw = {"symbol": "BBB", "market_cap_usd": 1.2e18, "close": 160.0, "median_dollar_volume": 4.5e9}
_thin_adr = {"symbol": "CCC", "market_cap_usd": 1.0e12, "close": 43.0,
             "median_dollar_volume": 7.2e6}
check("a genuine USD mega-cap is accepted", PV.usd_market_cap(_good)[0] is not None)
check("a KRW-denominated cap is REFUSED on the implied share count",
      PV.usd_market_cap(_krw)[0] is None and "shares" in PV.usd_market_cap(_krw)[1])
check("a TWD-denominated cap is REFUSED on days-to-trade",
      PV.usd_market_cap(_thin_adr)[0] is None and "days" in PV.usd_market_cap(_thin_adr)[1])
check("a row with no close cannot be checked, so it is REFUSED not passed",
      PV.usd_market_cap({"market_cap_usd": 1e12, "close": None})[0] is None)
check("the refusal always names WHY", all(PV.usd_market_cap(r)[1]
                                          for r in (_good, _krw, _thin_adr)))
_dual = [dict(_good, symbol="AAA"), dict(_good, symbol="AAB"),
         dict(_good, symbol="AAC", market_cap_usd=4.0e12)]
for r in _dual:
    r.update(sector="Tech", exp_return=0.0024, downside_5pct=-0.1,
             realised_vol_20d=0.2, upside=0.1, consensus=4.0, coverage=6,
             coverage_bucket="4-10", coverage_source=T.COVERAGE_SOURCE_CALIBRATED,
             past_winner=False, days_to_catalyst=5, confidence=0.9, status="BUY")
_sp = PV.build_variant(_dual, next(v for v in PV.variants() if v.name == "SP_TOPN"))
check("SP_TOPN holds one line per COMPANY (a dual share class is one bet, not two)",
      len(_sp["holdings"]) == 2, str([h["symbol"] for h in _sp["holdings"]]))
check("  and the dual-class drop is counted with a reason",
      any("dual share class" in k for k in _sp["excluded_by_reason"]))
check("SP_TOPN is labelled a regime-conditional SENSOR, not a capital candidate",
      "SENSOR" in (_sp["shadow_only_note"] or "").upper()
      and "REGIME-CONDITIONAL" in (_sp["shadow_only_note"] or "").upper())


# --------------------------------------------------- the grading convention
print("\n-- the tournament's grading convention")

check("the grader records three legs", set(VG.LEGS) == {"intraday", "overnight_hold", "gap"})
_p2 = _panel(6, symbols=("S0", "SPY"))
_w2 = np.zeros(_p2.n_symbols)
_w2[_p2.symbols.index("S0")] = 1.0
_legs = VG.raw_legs(_p2, _w2, _p2.dates[2])
j = _p2.symbols.index("S0")
check("intraday is open(D) -> close(D)",
      abs(_legs["intraday"] - (_p2.close[2, j] / _p2.open_[2, j] - 1.0)) < 1e-12)
check("overnight_hold is open(D) -> open(D+1) -- entry at the OPEN, never the prior close",
      abs(_legs["overnight_hold"] - (_p2.open_[3, j] / _p2.open_[2, j] - 1.0)) < 1e-12)
check("gap is close(D) -> open(D+1)",
      abs(_legs["gap"] - (_p2.open_[3, j] / _p2.close[2, j] - 1.0)) < 1e-12)
_last = VG.raw_legs(_p2, _w2, _p2.dates[-1])
check("the LAST day's overnight leg is PENDING, not zero, until the next open exists",
      _last["overnight_hold"] is None and _last["intraday"] is not None)
check("a day with no bar at all grades to None on every leg",
      all(v is None for v in VG.raw_legs(_p2, _w2, "1999-01-04").values()))
check("the benchmark is LEVERED too in the excess column",
      "levered" in (ROOT / "scripts/variant_grade.py").read_text(encoding="utf-8"),
      "comparing a 4x book to a 1x index credits leverage with alpha")
check("the grade file is append-only and keyed for idempotency",
      "(day, book, arm, leg)" in (ROOT / "scripts/variant_grade.py").read_text(encoding="utf-8"))
check("the standings compound TERMINAL WEALTH rather than averaging",
      "wealth" in VG.standings.__doc__ and "TERMINAL WEALTH" in VG.standings.__doc__)


# -------------------------------------------------------- reachability
print("\n-- every new module has a caller")

for mod, users in (("scripts/portfolio_variants.py",
                    ("scripts/leverage_lab.py", "scripts/variant_grade.py")),
                   ("scripts/leverage_lab.py", ("scripts/variant_grade.py",))):
    stem = Path(mod).stem
    check(f"{mod} has a caller ({users[0]})",
          any(stem in (ROOT / u).read_text(encoding="utf-8") for u in users),
          "a module with no caller is a discovery three weeks later")
check("this suite is the caller of record for all three",
      all(Path(m).stem in Path(__file__).read_text(encoding="utf-8")
          for m in ("scripts/portfolio_variants.py", "scripts/leverage_lab.py",
                    "scripts/variant_grade.py")))


print(f"\n{_ran} checks")
if _fails:
    print(f"FAILED: {len(_fails)} -> {_fails}")
    raise SystemExit(1)
print("ALL PASS tests_smoke_leverage_lab")
