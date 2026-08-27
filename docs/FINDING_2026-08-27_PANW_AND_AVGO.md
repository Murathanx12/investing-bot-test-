# FINDING — one hour of measurement, one refusal and one null

`AAT_ACCOUNT_ROLE=dev python -m scripts.event_straddle_backtest --symbols PANW AVGO --json`
· receipt `state/event_straddle_backtest.json` · 2026-08-27.

## WHY THESE TWO NAMES

`docs/FINDING_2026-08-27_THREE_EVENTS.md` established that the whole contest
gives `post_event_drift` three tradeable events. The obvious way to add more is
`event_move`, which buys the straddle into a scheduled print — and **PANW (1 Sep)
and AVGO (2 Sep) are the two liquid prints inside the window.**

Both were admissible for one reason only: nobody had measured them. `refuted.py`
was rewritten this morning precisely so that *unmeasured* would stop reading as
*safe*. So they got measured.

Method: for each inferred print, reconstruct the ATM straddle at the nearest
expiry after it, buy at the close **before** and sell at the close **after**.
Real expired-contract bars. Closes, not crossed quotes — so this is a direction
check that **flatters** the buyer, because a real straddle pays the spread twice.

## PANW — REFUSED. 0 for 6.

| print | straddle return |
|---|---|
| 2025-02-14 | **−63.5%** |
| 2025-05-21 | −2.5% |
| 2025-08-19 | **−57.0%** |
| 2025-11-20 | −6.5% |
| 2026-02-18 | −21.0% |
| 2026-06-03 | **−47.4%** |

Mean **−33.0%**, median **−34.2%**, paired t(realised − implied) **−2.5**.

**Every single event is negative.** This is not a mean dragged down by one
disaster — there is no event on which buying PANW's print straddle worked. The
chain prices PANW's earnings move at ~8% and PANW does not deliver it.

Added to `refuted.MEASURED_OWN_PRINT`. Scoped to PANW, to `long_straddle` /
`long_strangle`, and to its own print. **A directional PANW call is untouched** —
this is an absolute-move sample and says nothing about the signed move.

## AVGO — NOT REFUSED, AND NOT LICENSED

| print | straddle return |
|---|---|
| 2024-09-06 | +9.1% |
| **2024-12-13** | **+191.0%** |
| 2025-03-07 | −6.0% |
| 2025-06-06 | −35.0% |
| 2025-09-05 | +43.5% |
| 2025-12-12 | +41.0% |
| 2026-03-05 | −22.0% |
| 2026-06-04 | +34.1% |

Mean **+32.0%**, median +21.6%, 5 of 8 positive, paired t **+1.18**.

Read alone, that is an argument to buy AVGO's 2 Sep straddle. Three things say
otherwise, and the first is the one that matters:

1. **IT DOES NOT SURVIVE THE TAIL.** Drop the single 2024-12-13 event and the
   mean falls **+32.0% → +9.2%**, t **1.18 → 0.66**, and the hit rate becomes a
   coin flip. That one observation is **62% of all positive return in the
   sample.**
2. **THE SAMPLE COULD NOT HAVE RESOLVED IT.** sd is 75.6% per event, so the MDE
   at 80% power on n=8 is **74.8% per event** against an observed +32%. Ask
   whether the sample could have answered before asking what it said.
3. **THESE ARE CLOSES.** A real straddle crosses the spread twice on an option
   costing ~8.6% of spot. The +9.2% that survives the tail check does not
   obviously survive that.

So AVGO goes into `UNMEASURED` **with its numbers**, not into the refusal list —
and the entry says why it exists: *AVGO prints 2 Sep, inside the contest, and is
the obvious thing to buy; this row exists so nobody buys it on the +32%.*

Recording a null as a null. It is admissible; buying it is a coin flip with a
receipt, not an edge.

## WHAT THIS COST AND WHAT IT BOUGHT

About an hour. It removed one temptation with evidence, added one refusal that
would otherwise have been discovered by losing money on 1 September, and left
the third-largest event of the window honestly open.

The remaining mega-caps — AAPL, MSFT, GOOGL, AMZN, META, TSLA — are the same
command with a different `--symbols`. None of them prints inside this contest,
so it is not urgent; it is simply cheap, and `UNMEASURED` now says so in the
place someone will look.

**And the test that caught the sloppiness is worth naming.**
`tests_smoke_refuted.py` asserted `set(MEASURED_OWN_PRINT) == {"NVDA"}`. Adding
PANW failed it immediately — exactly the right way round. The test existed to
stop a symbol being added without its sample, and it made the author produce the
receipt before it would go green. It is now an invariant (every entry must carry
digits and a path) rather than a literal list, so it keeps working as the list
grows.
