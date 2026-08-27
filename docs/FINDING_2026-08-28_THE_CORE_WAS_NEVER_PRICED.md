# The 70% core is refuted by thirty years of its own prices

*2026-08-28. `scripts/optionmetrics_core_replay` (Aegis repo), OptionMetrics
`opprcd` 1996-2025, 11,859,415 real bid/offer rows on SPY/QQQ/IWM/SMH.*

## What was believed, and on what evidence

`COMPETITION_BOOK_v1` put **70% of its risk** into short put spreads on
SPY/QQQ/IWM. The stated evidence was `scripts/structure_lab`, which priced every
structure over measured underlying returns using Black-Scholes at an assumed
sigma, and found short put spreads to be the only family with a positive median
once the drift was stripped out.

That test cannot answer the question it was asked. It says *given this
volatility assumption, this payoff shape has this distribution*. It cannot say
whether the market's actual price for the shape was generous, **because the
price was an input**. The option seller is paid for variance the underlying goes
on to realise; the entire question is whether the payment exceeded it.

The book's own pricing function made the gap literal:

```python
width  = max(1.0, round(px * 0.05))
credit = width * 0.30          # <- the thing under test, assumed
risk_per = (width - credit) * 100.0
```

Three inventions in three lines, and the third — max loss — is the number the
whole sizing chain divides by.

## The measurement

Real listed quotes. Entry sells the ~25-delta put and buys ~5% lower, ~30 DTE,
held five sessions and marked at a real two-sided quote (~25 DTE remaining).
Execution crosses the spread **against us on all four crossings**: sell at the
bid and buy at the offer, entry and exit. Blocks are non-overlapping.

| short put spread | SPY | QQQ | IWM |
|---|---|---|---|
| blocks | 884 | 1062 | 1013 |
| years | 20.5 | 26.4 | 24.8 |
| median | +2.94% | +2.21% | +1.76% |
| hit rate | 68.8% | 58.8% | 57.7% |
| **mean** | **+0.67%** | **−1.27%** | **−0.65%** |
| **t** | **+2.16** | **−3.54** | **−1.94** |
| worst block | −62.6% | −66.7% | −52.9% |
| **terminal wealth** @20% risk/block | **2.79x** | **0.05x** | **0.21x** |
| buy and hold, same window | **5.39x** | **5.14x** | **2.50x** |

**It fails on two of the three underlyings and beats buy-and-hold on none.**

QQQ is the cleanest statement of the failure: a **+2.21% median** and a **58.8%
hit rate** that turns one dollar into **five cents**. That is
`FINDING_2026-08-28_VARIANCE_DRAG_ATE_THE_EDGE.md` again in a different
instrument — a book wins most weeks and loses everything, because the losses are
many times the wins and the mean is what compounds.

## Every alternative, on the same blocks

Each structure is priced from the same two dates, and a block missing any one of
them is dropped from all of them.

| SPY, 884 blocks | median | mean | hit | t | wealth |
|---|---|---|---|---|---|
| long shares | +3.70% | +2.19% | 62.0% | **+3.58** | **26.30x** |
| long ATM call | +1.49% | +4.21% | 50.8% | +2.47 | 20.75x |
| call debit spread | +2.37% | +3.34% | 51.5% | +2.09 | 7.11x |
| short put spread | +2.94% | +0.67% | 68.8% | +2.16 | 2.79x |
| **long straddle** | **−7.97%** | **−3.58%** | **26.5%** | **−5.66** | **0.00x** |

Two results carry beyond the competition:

1. **Long shares is the only structure positive on all three underlyings with a
   positive t.** Beta is not the boring fallback; on this evidence it is the
   result.
2. **The long straddle is annihilated** — t between **−5.66 and −8.72**, 0.00x
   on all three, a negative median in every era. The August book's largest
   single loss was a long straddle (−$22,017). Twenty-six years of real prices
   say that was not bad luck.

## The era breakdown, which is the usual story

| short put spread | ≤2007 | 2008-2012 | 2013-2019 | 2020-2025 |
|---|---|---|---|---|
| SPY wealth | 1.12x | 1.08x | **1.95x** | 1.18x |
| QQQ wealth | **0.02x** | 0.91x | **2.41x** | 1.13x |
| IWM wealth | **0.21x** | 0.74x | 1.30x | 1.09x |

QQQ before 2008 runs **t −8.55**. The whole positive result is 2013-2019, and
2020-2025 is flat. This has now happened to every candidate this project has
tested, which is itself the finding: **one favourable regime is the default
shape of a false positive here.**

## Two biases found in my own test, both correctable, one severe

**1. The delta filter deleted the losing tail.** The first pull filtered
`abs(delta) between 0.03 and 0.62`. Delta is not a fixed property of a contract:
a short put sold at −0.25 that goes badly wrong has a delta of −0.85 five
sessions later. The entry quote passed the filter and the **exit quote did not**,
so the block was dropped as "contract not quoted at exit" — 117 of 409 SPY
blocks, and precisely the ones that lost. The filter is now on **moneyness**,
which a strike cannot escape.

**2. The benchmark spanned a different window.** SPY's option history starts in
2005 while its price file starts in 1999, so a 20-year strategy was being
compared against a 26-year buy-and-hold that included six years of the dot-com
recovery. The reference now spans exactly the block window.

A third convention was corrected rather than being a bias: "risk" for shares was
notional, which cannot be lost over five sessions, so an allocator thinking in
max-loss dollars under-sized shares by roughly 8x. Shares are now sized on the
**measured worst five-session loss**, stated as in-sample.

## What this does to the book

`COMPETITION_BOOK_v1` is withdrawn, not patched. The core it was built around
does not survive its own prices, and three further defects meant it could not
have been placed at all — see
`FINDING_2026-08-28_THE_BOOK_COULD_NOT_HAVE_BEEN_PLACED.md`.

The replacement carries no fixed core. `alpha/tournament.py` auctions risk to
whichever opportunity most improves the objective, and on this evidence beta
wins that auction on merit rather than by being written into a constant.

## Status

`PRODUCT_EXPERIMENT` measurement. One pre-specified structure family, tested
once, on real quotes, with pessimistic execution. There is no leaderboard here
and therefore no multiplicity to correct — but there is also no positive claim
being made. The finding is a **refutation**, and the direction of every
correction found along the way made the refuted thing look *better*, not worse.

> We did not find that selling index put spreads is unprofitable in general.
> We found that **this** structure, at **this** horizon, over **these** thirty
> years, loses to simply holding the index on all three underlyings — and that
> nothing we had run before could have told us either way.
