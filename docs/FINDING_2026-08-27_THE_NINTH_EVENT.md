> **INTRADAY.** Written at ~13:45 ET on 27 Aug with the session still open, so
> the 27 Aug marks are the latest trade, not a settled close. Re-run
> `scripts/belief_to_position --event 2026-08-26` and reprice the straddle after
> 16:00 ET before quoting these as final. The signs and the ordering will not
> move; the last decimal will.

# FINDING — the ninth NVDA event broke the streak, and the straddle was still the wrong way to own it

## THE STREAK BROKE

`NVDA 0 for 8` has been this project's most-cited number. It licensed a guard,
it was the sole evidence behind `MEGA_CAP_PRINTERS`, and it is quoted in the
memory index.

The 26 August print is the ninth event, and the buyer won.

The backtest cannot see it — `event_straddle_backtest` reconstructs from expired
contract bars and the 28 Aug contracts have not expired, so it still reports
"8 of 11 inferred prints reconstructed". Priced directly instead:

| NVDA260828 @ 210 | 26 Aug close | 27 Aug latest | return |
|---|---|---|---|
| call | $6.25 | $19.94 | **+219%** |
| put | $6.20 | $0.07 | −99% |
| **straddle** | **$12.45** | **$20.01** | **+60.7%** |

Entry implied move **5.94%** (straddle/spot at the 26 Aug close of 209.66).
Realised **+9.61%**. It cleared the breakeven with room.

**So NVDA is 1 for 9, and the one is the most recent.** The row in
`alpha/refuted.py` now says so, and its reopening condition — twenty prints where
the realised move beats the entry straddle — now carries the count: **one of
twenty exists.**

Recording this was not optional. Hiding an inconvenient winner is the same
failure as hiding a loser, and it is worse here because the winner is evidence
against a guard I am enforcing.

## THE ROW STILL STANDS, AND HERE IS THE HONEST ARITHMETIC

Eight reconstructed events average **−45.8%** at paired t **−4.37**, hit rate
**0.0**. Adding a +60.7% ninth moves the mean to roughly **−34%**. One large
winner in nine does not overturn that, and the shape is the one this project has
learned to distrust: a mean carried by a single tail event.

It is the same shape as AVGO, where one +191% print was 62% of all positive
return, and as the index straddles, where the pooled mean hides a negative
median. The difference is that here I am on the side of the refusal, which is
exactly when the tail check is easiest to skip.

## THE PART THAT MATTERS MORE THAN THE STREAK

**Even on the event that broke it, the straddle was the wrong instrument.**

    call      +219%
    straddle   +60.7%

The straddle paid for both sides and the put expired at $0.07. Buying the
absolute move cost roughly two thirds of the return available to buying the
signed move — on an event where the sign was the thing we actually had a view
about. The sealed vector, the Q3-guide surprise and Murat's stated expectation
all pointed the same way.

That is `alpha/claims.py` stated in dollars: **a directional claim spent on a
sign-blind structure gives back most of what it was right about.** The claim
matrix now refuses that pairing before pricing, and it would have refused it here.

## AND WHAT THE BOOK ACTUALLY HELD

Neither. On 25 August the books opened an **AMD straddle** into NVDA's print and
**index straddles** on SPY and QQQ. Marked from the same 26 Aug close:

| | move | |
|---|---|---|
| **NVDA** | **+9.61%** | the source, never held |
| AVGO | +3.98% | |
| SMH | +2.93% | |
| QQQ | +1.26% | held, as a straddle |
| SPY | +0.79% | held, as a straddle |
| AMD | **−1.24%** | **held, as a straddle** |
| MU | **−2.65%** | the confirmed causal beneficiary |

Zero of six proxies beat the source. Two went the wrong way, including **MU**,
which `NEEDS_GRAPH` had independently ranked the most constrained node hours
before the filing disclosed commitments rising $119bn → $279bn *"primarily
related to the procurement of memory."* **The causal prediction was confirmed by
the primary document and the stock fell 2.65%** — after gapping +3.05% and giving
all of it back.

## THE THREE SENTENCES WORTH KEEPING

1. **The source beat every proxy**, including the two the causal graph most
   strongly implied. A causal arrow that exists is not an edge with a sign you
   can spend.
2. **The signed structure beat the sign-blind one by 3.6x** on the same event, in
   the same name, at the same entry.
3. **The book held the proxy, in the sign-blind structure.** Both decisions were
   wrong, independently, and each one is now a guard: `DIRECT_FIRST` via shares
   competing in the enumeration, and `alpha/claims.py` refusing the pairing.

The information existed. Every stage after it was where the money went.
