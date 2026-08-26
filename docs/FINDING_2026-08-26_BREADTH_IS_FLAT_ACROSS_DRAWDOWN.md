# Day one of the PIT panel: analyst bullishness carries no information about drawdown

**2026-08-26, session 13, unattended.** `python -m scripts.analyst_panel --n 700`
then `analyst_panel_calibrate`. 610 names, 607 with coverage, stratified across
dollar-volume buckets, captured 16:17Z. **CALIBRATION PASSED** on all six checks.

## The panel is trustworthy first

Before any claim, the facts a correct capture cannot violate:

| check | result |
|---|---|
| coverage rises with size | mega **43** → large 32 → mid 25 → small 15 → micro **11** |
| sell-side optimism present | mean net breadth **+0.625**, median +0.737, **93% positive** |
| ...but not saturated | range **−0.62 to +0.97** — a broken denominator would pin at +1 |
| analysts extrapolate | spearman(12-1 momentum, breadth) = **+0.138** |
| zero coverage ≠ zero breadth | 3 uncovered names, all `None`, none collapsed to 0.0 |
| not a mega-cap list | **46% small/micro** |

## The result, and it is negative

Net breadth by 52-week-drawdown quintile:

| quintile | median drawdown | median net breadth | median coverage |
|---|---|---|---|
| Q1 deepest | **−47.8%** | **+0.692** | 20 |
| Q2 | −27.1% | +0.750 | 20 |
| Q3 | −15.5% | +0.756 | 25 |
| Q4 | −7.8% | +0.714 | 21 |
| Q5 shallowest | **−2.4%** | **+0.700** | 23 |

**Flat.** Analysts are as bullish on a name down 48% as on one down 2%. The
spread across the whole range is 6 basis points of breadth, and it is not even
monotone.

## What that does to the screen

Murat's historical process was *large analyst upside × deep drawdown*. The
recommendation-breadth leg **cannot reproduce it**:

- **The conjunction is not rare.** 83 of 589 names — **14.1%** — are more than
  35% off the 52-week high *and* carry net breadth above +0.6. A screen that
  keeps one name in seven is not a screen.
- **It cannot be rare, because analysts are bullish on everything.** 93% of
  covered names have positive net breadth. Conditioning on "analysts are still
  positive" conditions on almost nothing.

So the discriminating variable is **not** whether analysts are bullish. It has
to be one of:

1. **the target GAP itself** — how far the target sits above the price. This is
   the actual content of ">50% upside", and it is **unavailable** on this data
   tier (HTTP 403), recorded as `UNAVAILABLE_FREE_TIER` and never approximated;
2. **target FRESHNESS** — a 100% gap on a target nobody has revised in ten
   months is a stale artefact, not a view. Also unavailable;
3. **revision DIRECTION**, which we *do* have: of 606 names with a one-month
   delta, **136 improving, 104 deteriorating, 366 flat**, median delta +0.00pp.

**Only (3) is measurable here**, and it is the leg the lane should be built on
until a data source with targets exists.

## The one thing that did come out the way the invariants predict

The deep-drawdown-and-still-liked cell is **45% small/micro**
(`{mega 8, large 21, mid 17, small 14, micro 23}`) with coverage of 8–13
analysts. That is exactly the region a mega-cap-anchored search never reaches —
`ASST` −88%, `BETR` −85%, `SOC` −84%, `BKKT` −82%, all with breadth above +0.75
on fewer than 14 analysts.

It is also the region where breadth is **least** trustworthy: eight opinions on
a broken microcap is not a consensus, and small-cap sell-side coverage is
systematically promotional. **The cell the method points at is the cell the
metric is weakest in.** That tension is the lane's real problem, and naming it
on day one is worth more than a spurious ranking.

## No forward return exists

Today is day one. Everything above **describes** a cross-section; none of it is
a signal, and none of it can be until these names have a future. That is the
whole reason the capture is scheduled daily — the panel becomes evidence by
ageing, and **every day it does not run is a day permanently missing.**

## The rule worth keeping

> **Check whether the condition you are conditioning on is rare.** "Analysts are
> still bullish" felt like information. It selects 93% of the market. A
> conjunction is only informative if at least one of its legs is.
