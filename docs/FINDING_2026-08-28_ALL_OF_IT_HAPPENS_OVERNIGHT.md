# The entire equity return arrives overnight. The trading day destroys value.

*2026-08-28. `scripts/crsp_when_return_happens` (Aegis repo), CRSP 1993-2024,
equal-weight, point-in-time dollar-volume screen decided on the PRIOR session.*

## Why the question was asked

Every strategy this project has built asks **which names**. The 32-year test
(`FINDING_2026-08-28_VARIANCE_DRAG_ATE_THE_EDGE.md`) says that question is worth
less than nothing at a five-day horizon — our best configuration compounded at
+5.36% against the market's +10.61%.

So: ask **when** instead. The daily return splits exactly into two disjoint
pieces we already had the columns for, and nothing in this repo had ever looked
at them separately.

## The measurement

Equal-weight top 200, 32 years, gross of costs:

| segment | terminal | CAGR | ann. mean | ann. vol | t (5d blocks) |
|---|---|---|---|---|---|
| close-to-close | 13.36x | +8.45% | +10.82% | 23.3% | +2.75 |
| **overnight (close→open)** | **164.64x** | **+17.31%** | +16.84% | **13.1%** | **+7.92** |
| intraday (open→close) | 0.09x | −7.26% | −5.61% | 19.6% | −1.74 |

**Overnight earns more than the whole day, at 56% of the volatility.** Intraday
is not merely weaker — it is a 32-year loss.

And it holds in **every decade**, including the one that destroyed everything
else we have tested:

| | total | overnight | intraday |
|---|---|---|---|
| 1993-1999 | +24.93% | **+39.68%** | −10.14% |
| 2000-2009 | −4.53% | **+13.54%** | −15.54% |
| 2010-2019 | +11.01% | +9.83% | +1.15% |
| 2020-2024 | +9.47% | +11.83% | −1.74% |

2000-2009 is the decade in which our momentum candidate returned 0.07x. Holding
only overnight made **+13.54%/yr** through it.

## The obvious objection, and the control that answers it

The standard critique is microstructure: the opening print is a bid or an ask,
so a close→open return is measuring the spread, not a return. That predicts the
effect should be **largest in the least liquid names**, where spreads are widest.

It is the other way round:

| universe | overnight CAGR | intraday CAGR |
|---|---|---|
| top **50** by dollar volume | **+19.33%** | −10.22% |
| top 200 | +17.31% | −7.26% |
| top 500 | +15.97% | −5.35% |

The effect is **strongest where spreads are tightest**. That is the opposite
sign to the contamination story, so the microstructure explanation does not
survive its own prediction. It does not make the effect tradeable — see below —
but it does mean this is not an artefact of the open price.

## What kills it, stated up front

As a **standalone daily round trip** it trades every session and pays the spread
twice a day:

| round-trip cost | terminal | CAGR |
|---|---|---|
| 1 bp | 32.90x | +11.55% |
| 2 bps | 6.57x | +6.07% |
| 5 bps | 0.05x | −8.82% |

Above ~1.5bps it stops beating simple close-to-close, and by 5bps it is
destroyed. **A result that dies at realistic costs is not a result**, so the
standalone version is not a strategy we own.

## What survives, and it is not small

The cost objection applies to *round-tripping daily*. It does not apply to
**holding**, and two things follow immediately:

1. **A continuous holder captures the overnight return for free.** Every leg of
   the +17.31% is inside a buy-and-hold. This is not a new trade; it is a reason
   to prefer holding over any strategy that flattens intraday, and every
   intraday-flat design in this repo has been unknowingly shorting the only
   segment that pays.

2. **Our own fill convention forfeits it.** `replay` and the lab decide at the
   close of `t` and fill at the open of `t+1`, which hands the `t → t+1`
   overnight to nobody. That is honest for a BACKTEST — you cannot transact at a
   close you are still deciding on. It is a **defect in live execution**, where
   a market-on-close order is available. The competition book should enter MOC,
   not next-open.

## Out of sample: 2023-2026, on the instruments we would actually trade

CRSP stops at 2024 and the competition trades now, so the same split was run on
Alpaca SIP bars, 755 sessions, 2023-08-24 to 2026-08-27:

| | close-close | overnight | intraday |
|---|---|---|---|
| equal-weight, 214 names | 1.969x | 1.665x | 1.187x |
| | +25.95%/yr | **+18.95%/yr** | +6.01%/yr |
| | 17.6% vol | **11.1% vol** | 14.7% vol |

Overnight is **73% of the return at 63% of the volatility** — the tilt survives.
Two honest qualifications:

- **Intraday is POSITIVE here (+6.01%)**, against −7.26% over 32 years. "The
  trading day destroys value" is a 32-year statement and it is *not* true of the
  last three years. What is true in both samples is that overnight pays more per
  unit of risk.
- **AAPL reverses it completely**: overnight **0.786x** against intraday
  **2.295x**. SMH (4.362x / 0.888x) and NVDA (5.125x / 0.939x) are the extreme
  version of the effect; Apple is the extreme version of its opposite.

That single row is the reason this stays a tilt and never becomes a rule. Same
shape as `[[run-the-control-you-would-not-have-chosen]]`: the name that was in
the list by convenience is the most informative one in it.

## The cost objection dies on ONE ETF — but only for some of them

The cost that killed the standalone version is a property of **the basket**, not
of the effect: 200 names round-tripped daily. SPY quotes about a cent on ~$770,
which is **0.13bp**. So the trade was re-run on single ETFs at a deliberately
pessimistic **0.5bp one way**, and compared at **matched volatility** — levering
the lower-risk overnight leg until its realised vol equals buy-and-hold's,
because comparing them raw just rewards whoever took more risk.

`scripts/overnight_tradeable`, Alpaca SIP, 755 sessions:

| | buy & hold | overnight (net) | intraday | overnight at matched vol |
|---|---|---|---|---|
| SPY | 1.830x / Sh 1.40 | 1.434x / 1.31 | +3.16% | 1.757x — **does not beat** |
| QQQ | 2.025x / 1.26 | 1.684x / 1.41 | +1.13% | 2.224x — beats |
| IWM | 1.696x / 0.94 | 1.582x / 1.17 | −2.68% | 1.962x — beats |
| SMH | 3.875x / 1.42 | **4.046x / 2.03** | −6.27% | 7.581x — beats |

**SMH needs no leverage at all**: overnight-only returns more than holding
(4.046x vs 3.875x) at **two-thirds the volatility**, which is dominance rather
than a risk-adjusted argument.

Three limits, all of which bind:

1. **SPY — the most important instrument — does not beat.** The effect
   concentrates in higher-vol tech and small caps, the same place AAPL's
   reversal said it would.
2. **Three years is one regime.** The 32-year evidence is at BASKET level; the
   cost-survival evidence is at INSTRUMENT level over three years. Nobody has
   shown instrument-level survival over 32 years and this document does not
   claim it.
3. **Financing is not charged** on the levered rows. At ~5%/yr on the borrowed
   half that is not a rounding error, and it is roughly the size of the margin
   the levered rows win by.

### And it is NOT the trade for this competition

Over five sessions, overnight-only holds QQQ for five nights and is flat five
days: roughly +0.37% expected against +0.51% for simply holding, at lower risk.
That is not a margin worth **ten extra executions** and the operational risk of
a missed MOC or MOO fill in a five-day contest. **The finding is for the
research programme; the competition book still just holds.**

## Status

`PRODUCT_EXPERIMENT` measurement. It is a decomposition, not a selection: one
pre-specified split, no ranking, no leaderboard, so there is no multiplicity to
correct and the t=+7.92 is not a maximum of anything. It is the highest t this
project has produced by a wide margin, and the honest summary is:

> We have not found a way to *trade* it. We have found that everything we own
> should stop *fighting* it.
