# FINDING — Source PEAD across the whole market: bad news drifts, good news fades

`python -m scripts.pead_wide --years 2.5` · receipt `state/pead_wide.json`, legs `state/pead_wide_legs.jsonl`
Universe HIGH_DISPERSION_US_v1 minus ETF-like names: 3,059 names; **2,532 with SEC 8-K Item 2.02 dates** (464
foreign filers / uncovered); **25,856 prints**, 2024-02-26 → 2026-08. Forward = next 3 sessions' log return
minus beta·QQQ (beta on the 120 prior sessions); `signed` = forward in the day-0 direction. SIP closes.

## 1. The mega-cap result does not generalise — and it reproduces

| slice | n | mean signed 3d | hit | t | t by week blocks |
|---|---|---|---|---|---|
| the old 15 names | 107 | **+1.09%** | 60% | **+2.72** | +2.48 |
| everything else | 25,749 | +0.05% | 50% | +1.15 | +0.82 |
| mid band (3.5–8.2%), all | 7,436 | +0.11% | 51% | +1.39 | +2.23 |

The +1.13% two-sided drift is a property of the eleven mega-caps it was measured on (reproduced here on a
different bar feed and a longer window). Across the market the two-sided rule is worth 5 bp.

## 2. What is there instead: an asymmetry

| mid band (3.5–8.2%) | n | mean in day-0 direction | hit | t | by year (t) |
|---|---|---|---|---|---|
| **day-0 DOWN → keeps falling** | 3,690 | **+0.44%** | 54% | **+4.29** (weeks +2.30) | 2024 +1.74 · 2025 +3.57 · 2026 +2.13 |
| day-0 UP → **reverses** | 3,746 | **−0.22%** | 48% | **−1.99** | |
| big band (>8.2%) DOWN | 3,790 | +0.64% | 55% | **+5.16** | |
| big band (>8.2%) UP | 3,649 | −0.44% | 47% | **−3.23** | |

By size, DOWN mid band: micro +0.30% (t 0.9) · **small +0.73% (t 4.08)** · mid +0.24% (1.5) · large +0.45% (2.1) ·
mega +0.42% (0.8, n=81). UP mid band is negative in every bucket except mega (n=64).

So the market-wide mechanism is **short the print that fell; never chase the print that rose.** This is the
opposite sign of "PEAD" as usually told for the up side, and consistent with the parent project's Holm-surviving
finding that short-horizon winner-chasing is an anti-signal.

## 3. What it is worth, honestly

+0.44% over three sessions on a 6.3% dispersion is a small edge with a large n: t 4.3 raw, **2.3 on weekly
blocks** (prints cluster). In shares the round trip is a few bp, so most of it survives; in options none of it
does. Borrow is the constraint — the lane needs `shortable and easy_to_borrow` from the venue, which 3,776 of
4,634 names have. Small caps carry the best number and the widest spreads; the stress-loss charge
(`alpha/engine/equity.py`) is measured per name and will be larger there.

## 4. What changed in code

`alpha/brains/post_event_drift.py`: outside the eleven measured names (`MEGA_MEASURED`) the brain **refuses an
UP day-0** ("good news fades", t −1.99/−3.23) and forecasts the **DOWN side as a short** with the wide numbers
scaled to the sessions left (`WIDE_DOWN`), the big band no longer discounted. The eleven names keep their own
rule. Every forecast row names which rule it used (`evidence.universe_rule`) and its receipt.

## 5. Not yet measured

- The 10/21-session HOLD horizons were added to the scan after this run started; the SEC cache now makes a
  re-run cheap on the SEC side (bars still ~1 h). Run `python -m scripts.pead_wide` again for
  `hold_horizons_mid_band`.
- Costs of borrow on small caps; overnight gap risk on shorts (the stress charge is measured but the
  theoretical loss is unbounded and the row says so).
- Whether the asymmetry is the same when the print is graded by EPS surprise sign rather than price reaction
  (the market-wide calendar carries `epsActual/epsEstimate` — the next cut).
