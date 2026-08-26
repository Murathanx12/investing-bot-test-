"""Smoke checks for POST_EVENT_DRIFT_v1. No keys, no network.

Run: python tests_smoke_pead.py  (also executed by tests_smoke.py)

No live name has printed in the last two sessions, so the brain declines on
every real symbol today -- which is correct and proves nothing. These checks
build a synthetic bar series with a planted print and walk the arrival clock
through it, because the only behaviour worth pinning is what the brain does on
the ONE day a year each name gives it.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha.brains import post_event_drift as ped
from alpha.brains import BRAINS


# ---------------------------------------------------------------- fake market
def sessions(n: int) -> list[str]:
    """n weekday dates ending today, oldest first."""
    out, d = [], date(2026, 8, 26)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return list(reversed(out))


def bars_with_print(*, day0_move: float, elapsed: int, n: int = 200) -> tuple[list[dict], str]:
    """A calm series with one planted jump, `elapsed` sessions before the end."""
    days = sessions(n)
    i0 = len(days) - 1 - elapsed
    px, closes = 100.0, []
    for i in range(len(days)):
        step = day0_move if i == i0 else (0.004 if i % 2 else -0.0035)
        px *= math.exp(step)
        closes.append(px)
    return ([{"t": f"{d}T00:00:00Z", "o": c, "h": c, "l": c, "c": c, "v": 1e6}
             for d, c in zip(days, closes)], days[i0])


class FakeClient:
    def __init__(self, bars):
        self._bars = bars

    def stock_bars(self, symbol, **kw):
        return {"bars": {symbol: self._bars}}


def run(*, day0_move: float, elapsed: int, session: str = "amc", symbol: str = "NVDA"):
    bars, event_day = bars_with_print(day0_move=day0_move, elapsed=elapsed)
    releases = [{"date": event_day, "session": session, "date_source": "sec_8k_item_2.02"}]
    real = ped.event_days_from_sec

    def fake(_bars, _symbol):
        days = [b["t"][:10] for b in _bars]
        closes = [float(b["c"]) for b in _bars]
        i = days.index(event_day)
        return [{"period_end": None, "event_day": event_day, "release_date": event_day,
                 "session": session, "move": math.log(closes[i] / closes[i - 1]),
                 "date_source": "sec_8k_item_2.02"}]

    ped.event_days_from_sec = fake
    try:
        return ped.forecast(FakeClient(bars), symbol, 3.0)
    finally:
        ped.event_days_from_sec = real


# ------------------------------------------------------------ arrival clock
# The checks below describe the MEGA-11 rule, so they run as NVDA. The wide rule
# (every other name) is pinned at the end of this file.
print("\n-- post_event_drift: the arrival clock")

try:
    run(day0_move=0.06, elapsed=0)
    check("day-0 still forming is refused", False)
except ped.NotApplicable as exc:
    check("day-0 still forming is refused", "still forming" in str(exc))

f1 = run(day0_move=0.06, elapsed=1)
check("one session elapsed -> quotes the +0.72% arrival", abs(f1.centre - 0.0072) < 1e-9,
      f"centre {f1.centre:+.4%}")
check("one session elapsed -> two sessions of window left", f1.horizon_days == 2.0)

f2 = run(day0_move=0.06, elapsed=2)
check("two sessions elapsed -> quotes the +0.41% arrival", abs(f2.centre - 0.0041) < 1e-9,
      f"centre {f2.centre:+.4%}")
check("the later arrival is worth strictly less", f2.centre < f1.centre)
check("the later arrival is less convinced", f2.conviction < f1.conviction)

try:
    run(day0_move=0.06, elapsed=3)
    check("spent window is refused", False)
except ped.NotApplicable as exc:
    check("spent window is refused", "drift window" in str(exc))

# ------------------------------------------------------------------ direction
print("\n-- post_event_drift: direction and the bands")

down = run(day0_move=-0.06, elapsed=1)
check("a down print forecasts DOWN", down.centre < 0, f"centre {down.centre:+.2%}")
check("down and up are mirror images", abs(down.centre + f1.centre) < 1e-12)
check("the down side is not penalised (it is the stronger half in the data)",
      down.conviction == f1.conviction)

try:
    run(day0_move=0.02, elapsed=1)
    check("a flat print is refused", False)
except ped.NotApplicable as exc:
    check("a flat print is refused", "flat tercile" in str(exc))

big = run(day0_move=0.15, elapsed=1)
check("an over-extended print halves conviction", big.conviction < f1.conviction,
      f"{big.conviction} vs {f1.conviction}")
check("an over-extended print still forecasts the same centre", big.centre == f1.centre)
check("the band is named in the rationale", "over-extended" in big.rationale)

# ------------------------------------------------------------------ the spread
print("\n-- post_event_drift: the spread it is allowed to claim")

check("sd is never below the measured floor", f1.sd >= ped.ARRIVAL[1][1] - 1e-12,
      f"sd {f1.sd:.2%} floor {ped.ARRIVAL[1][1]:.2%}")
check("sd is positive", f1.sd > 0)
check("the edge is a TILT, not a tail", f1.centre / f1.sd < 0.5, f"{f1.centre / f1.sd:.2f}")
check("labelled a gradient, so shape.py does not buy convexity for it",
      f1.signal_shape == "gradient")

# a violently volatile name must widen the spread above the floor, not sit on it
vol_bars, event_day = bars_with_print(day0_move=0.06, elapsed=1)
for i, b in enumerate(vol_bars[:-3]):
    b["c"] = 100.0 * math.exp(0.05 * (1 if i % 2 else -1) * (i % 7) / 7.0)
real = ped.event_days_from_sec
ped.event_days_from_sec = lambda _b, _s: [
    {"period_end": None, "event_day": event_day, "release_date": event_day, "session": "amc",
     "move": 0.06, "date_source": "sec_8k_item_2.02"}]
try:
    wide = ped.forecast(FakeClient(vol_bars), "NVDA", 3.0)
    check("a volatile name widens above the floor", wide.sd > f1.sd, f"{wide.sd:.2%} > {f1.sd:.2%}")
finally:
    ped.event_days_from_sec = real

# --------------------------------------------------- the WIDE-universe rule
print("\n-- post_event_drift: outside the eleven names (state/pead_wide.json)")
try:
    run(day0_move=0.06, elapsed=1, symbol="TEST")
    check("wide universe: an UP print is refused (good news fades)", False)
except ped.NotApplicable as exc:
    check("wide universe: an UP print is refused (no edge, NOT 'reversal' -- raw it rises +0.25%)",
          "NO EDGE" in str(exc) and "REVERSES" not in str(exc), str(exc)[:80])
try:
    run(day0_move=-0.04, elapsed=1, symbol="TEST")
    check("wide universe: a 4% drop is refused (response curve dead below 5%)", False)
except ped.NotApplicable as exc:
    check("wide universe: a 4% drop is refused (response curve dead below 5%)", "less than 5%" in str(exc), str(exc)[:80])
# The wide DOWN side: in SIMPLE returns the unhedged short earns +0.04% / +0.00%
# (the log drift was the index rising). REFUSED until a pair structure exists.
for mv, label in ((-0.06, "5-8.2%"), (-0.15, ">8.2%")):
    try:
        run(day0_move=mv, elapsed=1, symbol="TEST")
        check(f"wide universe: a {label} DROP is refused unhedged (simple-return short is worth nothing)", False)
    except ped.NotApplicable as exc:
        check(f"wide universe: a {label} DROP is refused unhedged (simple-return short is worth nothing)",
              "SIMPLE returns" in str(exc) and "PAIR" in str(exc), str(exc)[:90])
check("the refusal is a switch, not a deletion: the pair numbers are on record",
      ped.WIDE_UNHEDGED_SHORT_ENABLED is False and ped.WIDE_HEDGED_IWM_SIMPLE["mid"][1] > 2.0)
# If the switch is ever flipped, the forecast must be the RAW from-open number, not the excess.
ped.WIDE_UNHEDGED_SHORT_ENABLED = True
try:
    wd = run(day0_move=-0.06, elapsed=1, symbol="TEST")
    check("(switch on) wide DOWN centre = RAW 0.272% x 2/3 sessions left, NOT the 0.44% excess-vs-QQQ",
          abs(wd.centre + 0.00272 * 2 / 3) < 1e-9, f"{wd.centre:+.4%}")
    check("(switch on) wide conviction is cut and the hedged number rides along",
          wd.conviction < 1.0 and wd.evidence["hedged_vs_iwm"]["t"] == 3.95 and wd.evidence["raw_2026_3d"] < 0)
finally:
    ped.WIDE_UNHEDGED_SHORT_ENABLED = False
check("the eleven keep their two-sided rule", run(day0_move=0.06, elapsed=1, symbol="AVGO").centre > 0)

# ----------------------------------------------------------------- provenance
print("\n-- post_event_drift: provenance and wiring")

check("registered as a brain", "post_event_drift" in BRAINS)
run_pass = __import__("scripts.run_pass", fromlist=["x"])
check("runs by default", "post_event_drift" in run_pass.DEFAULT_BRAINS)
check("NOT shadowed -- it narrows sigma, which is not what that list is for",
      "post_event_drift" not in run_pass.DEFAULT_SHADOW)

from alpha import runner
check("lands in the print's own event node, not a node of its own",
      runner.event_node(f1) == f"print:{f1.evidence['event_day']}")
check("every receipt behind the number is named",
      all(r.startswith("state/") for r in f1.evidence["receipts"]) and len(f1.evidence["receipts"]) == 3)
check("the headline it rests on travels with it",
      f1.evidence["headline"]["n"] == 108 and f1.evidence["headline"]["week_block_t"] == 2.23)
check("the day-0 move is in the evidence, not only the rationale",
      abs(f1.evidence["r_day0"] - 0.06) < 1e-9)

# the measured table must stay ordered: arriving later can never be worth more
print("\n-- post_event_drift: the measured table cannot invert")
ordered = [ped.ARRIVAL[k] for k in sorted(ped.ARRIVAL)]
check("centre falls with lateness", all(a[0] > b[0] for a, b in zip(ordered, ordered[1:])))
check("window shrinks with lateness", all(a[2] > b[2] for a, b in zip(ordered, ordered[1:])))
check("the refuse-below band is inside the over-extended band",
      ped.MIN_ABS_MOVE < ped.OVEREXTENDED_MOVE)

# --------------------------------------------- the claim, and the condor bug
print("\n-- claim: a directional brain may not be spent on a sign-blind structure")

from alpha.brains.base import Forecast, CLAIMS
from alpha.engine import sizing as sz

check("the brain declares a DIRECTION claim", f1.claim == "direction")
check("the default claim is unchanged for every other brain",
      Forecast("x", "Y", 3.0, 0.0, 0.02).claim == "distribution")
try:
    Forecast("x", "Y", 3.0, 0.01, 0.02, claim="nonsense")
    check("an undeclared claim is refused", False)
except ValueError as exc:
    check("an undeclared claim is refused", "must be one of" in str(exc))
try:
    Forecast("x", "Y", 3.0, 0.01, 0.02, claim="dispersion")
    check("a dispersion-only brain may not tilt", False)
except ValueError as exc:
    check("a dispersion-only brain may not tilt", "may not tilt" in str(exc))


class FakeStructure:
    def __init__(self, implied_move):
        self.kind = "probe"
        self.implied_move = implied_move


check("a distribution brain keeps its own spread",
      runner.effective_sd(Forecast("x", "Y", 3.0, 0.0, 0.02), FakeStructure(0.05)) == (0.02, "brain"))
sd_dir, src = runner.effective_sd(f1, FakeStructure(0.05))
check("a direction brain is integrated at the CHAIN's width", src == "chain_implied_move")
check("the chain width uses the same sigma conversion as the MDM gate",
      abs(sd_dir - 0.05 * math.sqrt(math.pi / 2.0)) < 1e-12, f"{sd_dir:.4f}")
check("the substituted width is wider than the brain's own here", sd_dir > f1.sd)
try:
    runner.effective_sd(f1, FakeStructure(0.0))
    check("no quoted width -> REFUSE, never fall back to the brain's sd", False)
except runner.ChainWidthUnavailable as exc:
    check("no quoted width -> REFUSE, never fall back to the brain's sd",
          "which way into a view about how far" in str(exc))

print("\nALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
