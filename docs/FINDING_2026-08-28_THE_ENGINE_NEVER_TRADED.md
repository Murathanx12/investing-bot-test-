# The engine did not underperform. It never took a position.

*2026-08-28. Evidence: `scripts/pnl_forensics`, a sweep of every `positions.json`
and `nav.jsonl` under `aegis-finance/backend/data/`.*

## The claim under test

"Our engine simply performs worse than both me and the S&P 500."

That is the natural reading of two paper accounts down $27,780 while SPY rose.
It is wrong in a way that matters, because the two halves of the estate failed
for *opposite* reasons and the fixes are opposite too.

## What the sweep found

**Ten Aegis arena books have never marked a NAV.** `find backend/data -name
nav.jsonl` returns **zero files**. The two `copy_lab` trackers — `ACTIVIST_13D`
(13D activist stakes) and `CORPORATE_INSIDER_CLUSTER` (Form 4 cluster buys),
the two books that copy how real investors invested — were seeded on
2026-08-14, ran **once**, and read:

    cash = 100000.0    positions = {}    last_nav = None    last_marked = None

`ACTIVIST_13D` considered **0 events**. Neither has held a share.

So the Aegis paper estate did not lose to the S&P 500. It has no track record
at all. **"Demonstrated edge is 0%" has always meant "no evidence", and it was
being read as "evidence of no edge".** Those are different claims and only the
first one is supported.

## What actually lost the money

Everything realised came from the two Alpaca books in this repo, and it entered
on **one day**:

| structure | dev | exp1 | total |
|---|---|---|---|
| `long_straddle` | −11,510 | −10,507 | **−22,017** |
| `iron_condor` (NVDA only) | −9,140 | −5,175 | **−14,315** |
| `long_call` | −1,161 | +156 | −1,005 |
| | | | **−37,337** |

100% of it entered on **2026-08-25**, across three brains (`vol_gap`,
`narrative_dispersion`, `options_attention`). Slippage was $757 — 2.0% of the
loss. Execution was never the story.

## The shape of the error, in one sentence

The book was **long volatility on six names with no catalyst** (SPY, QQQ, TSLA,
AMD, AVGO, META) and **short volatility on the one name that had one** — NVDA,
into its 26 Aug print, which then moved +9.6% against a short condor.

Both legs of that are the same mistake with opposite signs: the structure was
chosen from a forecast sd, and never from which asset had an event.

## Why this reframes the work

A system with no track record and a system with a bad one need opposite
remedies. Ours needs **positions**, not more guards. On 2026-08-27 the default
universe produced ZERO forecasts and no test could see it, because *refusing
correctly and having nothing to refuse print identically*. That is the same
defect as ten books with no NAV: an engine that never acts cannot be measured,
and an engine that cannot be measured cannot improve.

The competition is the first forcing function this project has had that
**requires** a position to exist. That is its real value, above the prize.
