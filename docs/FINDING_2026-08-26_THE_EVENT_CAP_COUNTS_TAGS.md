# The event cap counts TAGS, and the brain holding half the book tags nothing

**2026-08-26, session 13, unattended.** `python -m scripts.reunderwrite`.
Found while building `CONTINUOUS_REUNDERWRITING`, not while looking for it.

## The defect

`runner.EVENT_NODE_CAP` refuses a position that would push one event node past a
share of equity. It reads `event_node(forecast)` — a **tag the brain assigns**.

`vol_gap` assigns none. It opens volatility structures and every row it writes
carries `event_node: null`.

Measured on the dev book at 12:20 ET today:

| | |
|---|---|
| structures in the book | 8, **all** from `vol_gap` |
| carrying an event node | **0** |
| NVDA iron condors | 2, risk **$25,270** |
| share of book risk | **52.5%** |
| share of equity | **25.9%** |
| NVDA earnings | **tonight** |

So more than half the book's risk is short volatility into a scheduled earnings
print, and **the cap that exists to prevent concentration into one event never
saw it**, because the brain that opened it does not speak the language the cap
listens to.

## Why it went unnoticed

The cap works. It fires, it refuses, it appears in the ledger. Nothing is broken
in a way any test would catch — a guard that is never *reached* passes every
test it has. This is the same shape as `detectability_gate` being unreachable
for two days, and as `monday_gate_check` reporting 0/9 forever: **the failure of
a guard is usually silence, not an error.**

It also survived because the two condors are individually defensible. Each is
defined-risk, each passed admission, each sits inside per-underlying
concentration. The book-level fact — *both are the same bet on the same night* —
is not visible from any single admission decision.

## The fix, and why it is not applied tonight

**Event exposure is a fact about the underlying, not a tag.** A structure whose
underlying reports before the structure expires is event-exposed whoever opened
it and whatever they called it.

`scripts/reunderwrite.py` now derives it from the earnings calendar and reports
it. Making `EVENT_NODE_CAP` derive it the same way is the correct fix and is
**not applied**: it changes what the account refuses, it would need to run
against the live loops, and it is being written unattended a few hours before
the print it would be reacting to. That is an attended change.

## A distinction the first version of this tool got wrong

The first draft bucketed these as **STALE**. They are the opposite. Stale means
the thesis is finished and the capital is idle; **event-exposed means the thesis
is hours from being decided and the capital is at its most live.** Reporting a
pre-print condor as dead weight would have been worse than not reporting it.

`stale` and `exposed` are now separate buckets with separate arithmetic.

## What it says about the book tonight

Nothing here is a recommendation to close anything. The condors are short
premium into a print, which is the side our own backtest supports (the chain
overprices mega-cap prints; NVDA straddles 0/8, median −46%). The finding is not
that the position is wrong. It is that **the size of it was chosen by nobody** —
no cap evaluated the combination, because the combination was invisible.

## The rule worth keeping

> **A guard that reads a label is only as good as the labelling discipline of
> every producer.** Derive the fact where the fact lives. `EVENT_NODE_CAP` asks
> the brain what it was doing; the earnings calendar knows regardless of what
> the brain thought.
