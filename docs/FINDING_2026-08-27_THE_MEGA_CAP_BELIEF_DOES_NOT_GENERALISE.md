# FINDING — "the chain overprices mega-cap prints" does not generalise. It is two names.

`AAT_ACCOUNT_ROLE=dev python -m scripts.event_straddle_backtest --symbols AAPL MSFT
GOOGL AMZN META TSLA AMD MU --json` · receipt `state/event_straddle_backtest.json`
· 2026-08-27.

## THE STANDING BELIEF

The project has carried, in its memory index and in the first draft of
`alpha/refuted.py`, the claim that **the chain overprices mega-cap earnings
moves** — sourced to NVDA being 0 for 8. That claim was what licensed
`MEGA_CAP_PRINTERS = {NVDA, AAPL, MSFT, GOOGL, AMZN, META, TSLA, AVGO}` refusing
long premium on all eight names.

This morning that guard was rewritten because the sample contained one name. This
afternoon the other names were measured.

## THE TABLE

ATM straddle bought at the close before the print and sold at the close after.
`MDE` is the smallest per-event effect this sample size could detect at 80%
power. `drop-max` re-runs without the single best event.

| name | n | mean | median | t | win | MDE | drop-max mean/t |
|---|---|---|---|---|---|---|---|
| AAPL | 10 | −16.8% | −27.6% | −1.63 | **20%** | 29% | −23.7% / −2.82 |
| AMD | 10 | +7.7% | −16.1% | 0.40 | 30% | 54% | −4.3% / −0.25 |
| AMZN | 10 | −13.2% | −19.5% | −0.88 | 30% | 42% | −22.8% / −1.79 |
| GOOGL | 10 | −12.9% | −34.5% | −0.80 | 40% | 45% | −23.5% / −1.71 |
| META | 9 | +5.1% | +3.7% | 0.27 | 56% | 53% | −5.5% / −0.31 |
| MSFT | 10 | +14.1% | +0.4% | 0.66 | 50% | 60% | +1.2% / 0.06 |
| MU | 10 | −2.6% | +8.4% | −0.16 | 50% | 45% | −9.4% / −0.58 |
| TSLA | 17 | +20.8% | +7.1% | 1.26 | 59% | 46% | +11.0% / 0.78 |

**NOT ONE OF THE EIGHT CLEARS ITS OWN MDE.** Every observed effect is smaller
than the smallest effect its sample could have detected. Ask whether the sample
could have answered before asking what it said — and here, eight times, it could
not.

So: **no new refusals are licensed.** NVDA (0 for 8) and PANW (0 for 6, t −2.5)
remain the only two names where buying the print straddle is refutable. Six of
the eight are noise, and two of them (MSFT, TSLA) lean the *other* way.

## WHY POOLING DOES NOT RESCUE IT

Pooled across all 86 events: mean **+1.9%**, median **−11.8%**, t **0.31**, win
rate 43%, MDE 17%. Still nothing.

And pooling is the wrong instrument here anyway. It assumes the names behave
alike, and they demonstrably do not: **PANW is 0 for 6 at t −2.5 while TSLA is
+20.8% over 17 events.** A pooled t across a heterogeneous population is an
average of different things, and its narrow confidence interval is a statement
about the average, not about any name you can trade.

The mean/median split is the tell. Mean +1.9% against a median of −11.8% means a
few large winners carry the average while the typical event loses — the same
shape as AVGO, where one +191% event was 62% of all positive return.

## WHAT THIS CHANGES

1. **The belief is narrowed, not repealed.** "The chain overprices mega-cap
   prints" becomes "the chain overprices NVDA's and PANW's prints, measurably;
   for six other mega-caps we have looked and cannot tell." That sentence is
   less satisfying and it is what the data supports.
2. **It is the strongest evidence yet for this morning's rewrite.** The old guard
   refused long premium on eight names from one name's sample. Six of those eight
   now have their own samples and none of them supports the refusal — two lean
   the opposite way. **The guard was wrong on the majority of the names it
   covered**, and nothing would have revealed that except measuring them.
3. **`MIN_ABS_MOVE` and hit rate matter more than the mean.** AAPL wins 2 events
   in 10 and still cannot be refused on t. A 20% hit rate with an unresolvable
   mean is a warning, not a verdict, and it goes in `UNMEASURED` as one.

## WHAT WOULD SETTLE IT

More events per name, which arrive four times a year. AAPL needs roughly
`(2.8 × sd / 0.168)²` ≈ 28 events for its observed effect — **seven years**. That
is the same wall the parent project hit with `sqrt(T)`: the lever is not more
history, it is a construction with lower dispersion. A debit spread instead of a
straddle cuts sd at the cost of the tail, and is the obvious next test.

None of this is urgent. **None of these eight names prints inside the contest.**
It is recorded because it was cheap, because the belief it corrects was being
used, and because `UNMEASURED` now points at a table instead of at silence.
