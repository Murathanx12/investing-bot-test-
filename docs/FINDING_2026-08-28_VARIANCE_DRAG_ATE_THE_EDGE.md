# The best signal we own compounds at +5.36%. The market did +10.61%.

*2026-08-28. `scripts/crsp_five_day_momentum` (Aegis repo) over CRSP 1993-2024,
32 years, next-open fills, 10bps each way. Companion to
`scripts/wealth_lab`, which is where the wrong answer came from.*

## What I found first, and why it was wrong

The Alpaca lab ranked 32 five-session strategies over one and two years. The
winner was **`mega-cap mom 6m k=5`** — six-month momentum, top five names, held
five sessions:

| window | wealth | mean/5d | t | vs noise floor |
|---|---|---|---|---|
| 1 year (51 blocks) | 3.28x | +2.61% | +2.62 | floor 2.39 |
| 2 years (100 blocks) | **5.89x** | +2.08% | **+2.99** | floor 2.35 |

Consistent across both windows, above the leaderboard noise floor, control
behaved (leaders beat laggards). Everything a candidate is supposed to do.

**It does not replicate.** The same rule on CRSP, same construction, same fill
convention, 1993-2024:

    windows 7918   blocks 1584   mean +0.147%   t +0.66
    terminal wealth 0.1x   CAGR -7.23%   worst window -48.81%

    1993-1999   3.20x   +19.66%/yr   t +1.49
    2000-2009   0.07x   -23.75%/yr   t -1.10      <- lost 93% of capital
    2010-2019   1.20x    +1.85%/yr   t +0.66
    2020-2024   1.37x    +6.52%/yr   t +0.94

## Two reasons the lab was wrong, and one is my fault

**1. Survivorship bias in my own universe.** `scripts/wealth_lab.UNIVERSE` is
216 tickers I hand-listed because they are liquid *today*. Two years ago, which
of them would lead was knowable only in hindsight, and everything that blew up
and left is absent. The CRSP test screens the top 200 by dollar volume *at each
date* from the whole tape, so it has no such list. **When a hand-picked
universe and a point-in-time screen disagree, the screen is right.**

**2. Two years is one regime.** 2024-2026 is an AI bull market. 2000-2009 is
in the CRSP window and it took the same rule to 0.07x.

## The mechanism, which is the part worth keeping

Look again at the 32-year row: **mean +0.147% per window, terminal wealth 0.1x.**
A positive arithmetic mean and a catastrophic geometric one. That gap is
**variance drag**, and on a five-name book with a −48.81% worst window it is
enormous. `g ≈ m − σ²/2` is not a correction term here; it is the whole result.

This is the same defect as
`FINDING_2026-08-27_THE_RANKER_OPTIMISES_THE_MEAN.md`, now with a number on it.
The ranker prefers a 33%-hit-rate call to a 56%-hit-rate share position because
it maximises `m`. Over five sessions you draw once from that distribution; over
a career you compound it. **Neither of those is `m`.**

## Breadth is the lever, and a trend filter is nearly free

Sweeping the same replay over 32 years, terminal wealth, no filter:

| lookback | k=5 | k=20 | k=50 | k=100 |
|---|---|---|---|---|
| 21d | 0.00x | 0.06x | 0.23x | 0.38x |
| 63d | 0.00x | 0.16x | 0.33x | 0.58x |
| 126d | 0.09x | 0.47x | 0.62x | 0.73x |
| 252d | 0.23x | **2.58x** | 1.54x | 1.08x |

Wealth rises with `k` in every row — the farm's "breadth is the cheap lever",
confirmed at a five-day hold. And **concentration is not a risk preference here,
it is a negative-return decision.**

Adding a 200-session trend filter on the equal-weight universe (cash when
below) improves nearly every cell, and the best configuration becomes:

    252d lookback, k=20, trend-filtered:  5.03x   CAGR +5.36%   t +1.78

## The number that ends the argument

Over the same 32 years, on the same panel:

| book | terminal | CAGR |
|---|---|---|
| **CRSP value-weighted market** | **25.16x** | **+10.61%** |
| equal-weight top-500 (gross of the rebalance cost) | 148.53x | +16.93% |
| our best five-day configuration | 5.03x | +5.36% |
| the candidate the lab crowned | 0.09x | −7.23% |

**The passive market beat our best strategy by 5x in terminal wealth.** Not
after a subtle adjustment — outright, on the same fills, with the strategy given
the benefit of a filter chosen after seeing the failure it fixes.

## What this licenses

Nothing here says selection is impossible. It says **this** selection, at
**this** horizon, at **this** concentration, is worse than doing nothing, and
that no engineering fixes it because the defect is arithmetic.

So for a five-session book the order of operations inverts. Stop asking *which
names*. Ask, in order:

1. **How much beta, and does it cost anything to hold?** That term compounded
   at +10.61% for 32 years while every signal we own underperformed it.
2. **How broad?** Wealth rose with `k` in every row of the sweep.
3. **What structure?** Long premium has a negative median without a drift, and
   we have just failed to demonstrate a drift.
4. *Only then*, which names — and the tilt should be small, because its
   measured contribution over 32 years is negative.
