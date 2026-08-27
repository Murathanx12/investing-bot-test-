# Session 17 — why the paper books lost, and what the evidence says to do instead

## RESULTS SCOREBOARD

| | |
|---|---|
| best historical net strategy vs the market | **NONE beats it.** Best five-day config over CRSP 1993-2024: +5.36%/yr against the market's **+10.61%** |
| best forward paper strategy | none — no book has forward evidence |
| independent selector count | still **1** |
| new actionable finding | **overnight vs intraday**, t=+7.92, positive in all four decades |
| realised P&L, both books | **−$37,337**, 100% entered on one day |
| LLM spend this session | $0 — no call would have changed a verdict |

**RESULT IMPROVEMENT: NONE in P&L. The improvement is that we now know why,
with 32 years of receipts instead of a hypothesis.**

---

## 1. The diagnosis, in one sentence

The book was **long volatility on six names with no catalyst** (SPY, QQQ, TSLA,
AMD, AVGO, META) and **short volatility on the one name that had one** — NVDA
into its 26 Aug print, which moved +9.6% against a short condor.

| structure | dev | exp1 | total |
|---|---|---|---|
| `long_straddle` | −11,510 | −10,507 | **−22,017** |
| `iron_condor` (NVDA only) | −9,140 | −5,175 | **−14,315** |
| `long_call` | −1,161 | +156 | −1,005 |

Slippage was $757 — 2.0% of the loss. **Execution was never the story, and
neither was stock selection.** The structure was the trade.

## 2. The Aegis side did not underperform. It never took a position.

`find backend/data -name nav.jsonl` returns **zero files**. Ten arena books have
never marked a NAV. Both `copy_lab` trackers — the ones that copy 13D activists
and Form 4 insider clusters — were seeded 14 Aug, ran once, and still read
`cash = 100000.0, positions = {}, last_nav = None`. `ACTIVIST_13D` considered
**0 events**.

So "demonstrated edge is 0%" has always meant *no evidence* and was being read
as *evidence of no edge*. Different claims; only the first is supported.
`docs/FINDING_2026-08-28_THE_ENGINE_NEVER_TRADED.md`.

## 3. The backtests, and the one that mattered

New harness: `alpha/lab.py` + `scripts/wealth_lab.py`. Blocks the overlapping
windows so the t has an honest denominator, and computes a **leaderboard noise
floor** — the max |t| you expect from N pure-noise books.

Over 1 and 2 years the winner was `mega-cap mom 6m k=5` at **t=2.99, 5.89x**.
Replayed on CRSP 1993-2024 with the same construction:

    terminal wealth 0.1x    CAGR -7.23%    2000-2009: 0.07x

**It turns $1 into ten cents.** Two causes, one of them mine:

1. `wealth_lab.UNIVERSE` is 216 tickers liquid **today** — survivorship bias
   that a point-in-time dollar-volume screen does not have.
2. Two years is one AI regime.

The mechanism is **variance drag**: mean +0.147% per window, terminal 0.1x. A
positive arithmetic mean and a catastrophic geometric one. `g ≈ m − σ²/2` is
the whole result, not a correction. `docs/FINDING_2026-08-28_VARIANCE_DRAG_ATE_THE_EDGE.md`.

**Breadth is the only lever that helped in every row** (k=5 → 0.09x, k=100 →
0.73x at the same signal), and a 200-session trend filter lifted almost every
cell, best config to 5.03x / +5.36%. Still half the market's +10.61%.

## 4. The structure question, answered by a null

`scripts/structure_lab` prices every structure over the **measured** five-session
returns rather than simulated ones. On an index book the long straddle we spent
$22,017 on has an **8.7% hit rate and −10.78% median**; the iron condor on that
same index returns **+2.82% at 79.4%**. Each was run on the wrong asset.

Then strip the drift and keep the fat tails:

| structure | with drift | drift removed |
|---|---|---|
| ATM call | +12.20% | **−10.95%** |
| far OTM call | +10.31% | **−18.69%** |
| long straddle | −4.36% | −7.33% |
| **short put spread 95/85** | +9.39% | **+2.09%** |

**Long premium levers a drift; it does not create one.** Ours carries t=2.62
against a 2.39 noise floor. So the default structure is the one that survives
the null.

## 5. The best thing found: it all happens overnight

CRSP 1993-2024, equal-weight top 200:

| segment | terminal | CAGR | vol | t |
|---|---|---|---|---|
| close-to-close | 13.36x | +8.45% | 23.3% | +2.75 |
| **overnight** | **164.64x** | **+17.31%** | 13.1% | **+7.92** |
| intraday | 0.09x | −7.26% | 19.6% | −1.74 |

Positive overnight in **all four decades**, including 2000-2009 (+13.54% while
our momentum candidate returned 0.07x). The microstructure objection fails its
own prediction: the effect is **largest in the top 50** by dollar volume, where
spreads are tightest.

It **dies above ~1.5bps** as a daily round trip, so we do not own it as a
strategy. What we own is the consequence: a continuous holder gets it free, and
**our next-open fill convention forfeits it in live execution**. Enter MOC.

Out of sample 2023-2026 it survives (73% of return at 63% of vol) but **AAPL
reverses it entirely** (0.786x overnight vs 2.295x intraday). It stays a tilt.
`docs/FINDING_2026-08-28_ALL_OF_IT_HAPPENS_OVERNIGHT.md`.

## 6. The book — `python -m scripts.competition_book`

Built in the order the evidence supports, not the order we used to ask:

0. **Regime gate** — cash if SPY is below its 200-session average.
1. **Core, 70% of risk** — SPY/QQQ/IWM short put spreads. Beta is the only term
   that has ever compounded.
2. **Satellite, 30%** — 12-1 momentum at k≥20, **in shares** (a defined-risk
   spread has a minimum size; a $9,000 satellite over 20 names deployed $910
   and skipped 16 of 18 before this was fixed), earnings names dropped.
3. **Structure** — short put spreads: long delta *and* long theta.
4. **Timing** — market-on-close.

Current output: **$24,282 defined risk (24.3%), 18 satellite names, 2.13
effective bets.** DELL and MRVL dropped for prints inside the window.

## 7. What is still open

- The overnight effect has no tradeable form at our costs. The question worth
  asking next is whether an **overnight-tilted hold** (never flatten intraday)
  beats a plain hold net of everything.
- `mega-cap mom 6m k=5` is **retired from the current search**, not
  MECHANISM_REJECTED — a 32-year negative closes this construction at this
  horizon and concentration, not cross-sectional selection.
- The three graded-session scripts for 27 Aug still need running after settle.
- **Registration closes at 11:00 ET on 28 Aug.**
