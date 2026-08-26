# The $20bn book that was one bet — and so is ours

**2026-08-26, session 13, unattended.** `LEVERAGE_WITH_SURVIVAL_v1` phase 1.
Primary source: SEC EDGAR, CIK 0002045724, four 13F-HR filings.
Data: `state/research/situational_awareness_13f.json`.
Code: `alpha/concentration.py` · `python -m scripts.concentration`.

## Why this was blocked, and what unblocked it

The roadmap listed the Situational Awareness figures as **UNVERIFIED AND
BLOCKING** — the whole leverage lane would have been built on numbers from a
chat message. They are now verified from the filings themselves, and every one
was right:

| | claimed | filing (2026-06-30) |
|---|---|---|
| SNDK | ~28% | **28.03%** |
| MU | ~28% | **27.54%** |
| BE | ~9% | **9.60%** |
| TSM | ~6% | **6.37%** |
| Nebius | ~6% | **6.09%** |
| top 3 | ~65% | **65.2%** |

Total $20,242,292,228 across 26 rows / 24 issuers.

One secondary source (a 13F aggregator) reported BE at ~4.4%. It was counting
**shares only**: BE and TSM each carry call options on top of the share line.
**The aggregator dropped the leverage, which was the interesting part.**

## What the four quarters actually show

| quarter | total | issuers | top 3 | effective N by weight | put book |
|---|---|---|---|---|---|
| 2025 Q3 | $4.14bn | 25 | 51.0% | 8.1 | NVDA $299M, SMH $196M, CRWV $192M, AVGO $76M |
| 2025 Q4 | $5.52bn | 25 | 52.0% | 8.5 | ~none |
| 2026 Q1 | $13.68bn | 29 | 34.6% | **12.5** | **SMH $2,043M, NVDA $1,568M, ORCL $1,073M, AVGO $1,006M, AMD $969M, MU $584M** |
| 2026 Q2 | $20.24bn | 24 | **65.2%** | **5.7** | $5M |

**In one quarter the fund removed roughly $7.2bn of put protection and halved
its diversification.** Q1 was its most diversified book ever *and* carried a
large short-semis hedge. Q2 abandoned both and put 55.6% into two memory/storage
names. That is the portfolio it carried into July.

This is not a leverage story with a concentration footnote. **The hedge came off
and the concentration doubled in the same filing period.**

## Marking that book through the drawdown

21 of 24 issuers mapped to tradeable tickers = **96.98% of the book by weight**,
priced from our own bars, held static at Q2 weights, 2026-06-30 to 2026-08-26
(41 sessions).

| leverage | terminal | total return | max drawdown | first margin breach |
|---|---|---|---|---|
| **1.00x** | 0.767 | **−23.3%** | −42.2% | — |
| 1.25x | 0.699 | −30.1% | −50.3% | — |
| 1.50x | 0.631 | −36.9% | −57.6% | — |
| 2.00x | 0.500 | −50.0% | −69.6% | **2026-07-16** |
| 3.00x | 0.279 | −72.1% | −85.5% | **2026-07-01** |

Carrying the reported +439% into the window:

| leverage | ends at | vs inception |
|---|---|---|
| 1.00x | 4.13x | **+313%** |
| 1.50x | 3.40x | +240% |
| 2.00x | 2.70x | +170% |
| 3.00x | 1.50x | +50% |

> **The unlevered book survived.** −23% over two months is a bad quarter, not a
> failure. The economic thesis was not what killed it: at 1.0x the strategy still
> ends up more than four times inception. **+313% and solvent beats +439% and
> liquidated**, and that is the whole content of `LEVERAGE_WITH_SURVIVAL_v1`.

## The number that actually explains it

Counting positions, or inverting a Herfindahl over weights, answers *how spread
out is the capital*. The question is *how many independent things can go wrong*.

```
effective N by WEIGHT (1/HHI)      5.34
average pairwise correlation      +0.538   (range -0.68 .. +0.88)
portfolio daily vol, real          6.13%
...if the names were independent   3.17%
effective N by RISK                1.43     <- 3.7x overstated
```

**On its worst session, 2026-07-01, 20 of 21 priced names fell together.**
SNDK −11%, MU −11%, NBIS −17%, CRWV −14%, TSM −7%. Over the window every one of
the top eight lost: SNDK −34.0%, MU −18.4%, BE −28.7%, TSM −12.6%, NBIS −21.6%,
CRWV −12.1%, CORZ −31.3%, STM −34.0%.

A book that looks like five bets and behaves like 1.4 is **one position with
twenty-one tickers on it.**

## And ours is in the same regime

Same metric, same code, our live paper books, weighted by **true max loss**:

| book | underlyings | N by weight | avg rho | **N by RISK** | verdict |
|---|---|---|---|---|---|
| dev | 7 | 2.77 | +0.25 | **1.51** | CLUSTERED |
| exp1 | 6 | 3.44 | +0.30 | **1.27** | **CONCENTRATED** |
| *Situational Awareness Q2 2026* | *24* | *5.34* | *+0.54* | *1.43* | *(liquidated)* |

**exp1 is below the reference.** Its four largest max-loss lines are SPY 42.5%,
QQQ 22.0%, NVDA 17.9%, IWM 17.1% — four index and mega-cap products that are one
beta bet wearing four tickers.

And **dev carries 52.4% of its true max loss on NVDA, on the night NVDA
reports.**

## What was built, and what was deliberately not

`alpha/concentration.py` measures it:

```
N_risk = (var_independent / var_real) * N_weight
```

At zero correlation the two variances agree and the numbers coincide; as
correlation rises `N_risk` falls toward 1. Weights come from **true max loss**,
not market value — a long call at its mark and a credit spread at a negative
mark are not comparable numbers, and max loss is what the book is already
charged at. An underlying with no price series is **dropped and named**, never
treated as uncorrelated: silently dropping it would *raise* the diversification
reading, which is the direction that flatters the book.

**It reports; it does not refuse.** Turning `MAX_THESIS_CLUSTER` into an
admission gate changes what the account trades, and that is an attended
promotion decision — this ran unattended. What it supplies is the thing a
threshold argument needs: **1.43 is not a round number, it is the value a real
$20bn book carried at the moment it was forced to liquidate.**

## Caveats, because the reconstruction is a lower bound

- 13F is **long-only US equity**, quarterly, filed up to 45 days late. It omits
  shorts, non-US holdings, intra-quarter trades and the fund's actual financing.
- Q2 weights are held **static** through July; the fund certainly traded.
- The margin model is a simple maintenance test at constant leverage; a real
  prime-brokerage call has its own schedule.
- **+439% is a reported figure**, not one I verified from a filing. The
  reconstruction below it does not depend on it — the leverage table stands on
  its own.
- 3.02% of the Q2 book (SharonAI, Keel Infrastructure, Cerebras) had no
  tradeable price and is excluded.

## The rule worth keeping

> **Count bets, not tickers.** Position count and capital weight both answer a
> question nobody should be asking. The correlation-adjusted count is the one
> that predicts what a bad week does, and on both a $20bn fund and our own paper
> books it comes out between 1.2 and 1.7 while the position count says five to
> nine.
