# What the book is actually betting tonight, priced against our own eight prints

**2026-08-26, session 13, unattended, ~12:15 ET.** Read-only. Nothing was traded.
Sources: the live dev book, and `state/event_straddle_backtest.json` — eight
**SEC-dated** NVDA prints (`date_source: sec_8k_item_2.02`), not press-scraped.

## The position

NVDA last 210.34. Two iron condors, both expiring **2026-08-28**:

| | short put | long put | short call | long call | credit | max loss |
|---|---|---|---|---|---|---|
| A x19 | 200.00 (−4.9%) | 192.50 | 225.00 (+7.0%) | 232.50 | $3,876 | $12,445 |
| B x15 | 200.00 (−4.9%) | 192.50 | 222.50 (+5.8%) | 232.50 | $3,885 | $12,825 |

Combined credit **$7,761**, combined max loss **$25,270 = 25.9% of equity**.
Our own measured implied move for this expiry is **5.10%**, so the short strikes
sit at roughly ±1.0–1.4 implied moves.

## A correction to my own first pass

My first calculation scored any breach as a **full** loss and concluded the
structure needed a 76–77% win rate against a 62% base rate — i.e. negative EV.
**That was wrong in the pessimistic direction.** A condor breached slightly loses
far less than max, and three of the eight historical moves land in exactly that
partial zone.

Computing the **exact expiry payoff** at each historical move instead:

| historical move | combined P&L |
|---|---|
| −8.96% | **−17,739** |
| −6.55% | −3,926 |
| −5.77% | +1,652 |
| −3.14% | +7,761 |
| −1.81% | +7,761 |
| −0.78% | +7,761 |
| +0.52% | +7,761 |
| +3.18% | +7,761 |

```
mean    +2,349   (+2.41% of equity)
median  +7,761
worst  -17,739   (-18.18% of equity)
wins       6/8
```

**The structure is EV-positive on our own base rate.** The crude version was a
bad approximation, and the difference between the two is the whole result.

## What supports it

Median realised/implied across the eight prints is **0.45** — the chain has
priced roughly twice the move that arrived. That is the same fact as
"NVDA straddles 0/8, median −46%", seen from the selling side, and it is the
reason short premium into this print is defensible at all.

## What should worry us anyway

**The strikes are asymmetric against the history.** Six of eight prints moved
**down** (median −4.46%); two moved up (median +1.85%). The short put is at
**−4.9%** and the short calls at **+5.8% / +7.0%** — so the **tighter** side
faces the direction that has produced **every single historical breach**
(−8.96%, −6.55%, −5.77%).

That is not an argument that the position is wrong. It is an argument that its
*worst* case and its *most likely* direction are the same side, which is the
configuration where a fat left tail actually gets hit.

**And the tail is 18.18% of equity on one night.**

## The honest limits

- **n = 8.** A 6/8 win rate has a 95% interval running roughly 30%–92%. This
  sample cannot distinguish +2.4% EV from 0, and it certainly cannot support a
  sizing decision on its own.
- Historical moves are close-to-close over the event window; the condors settle
  at Friday expiry, two sessions out. Close enough to compare, not identical.
- Every one of the eight prints had a different implied move (5.9%–10.9%) and
  different strike distances. Applying **today's** strike percentages to **past**
  moves assumes the relationship between strike placement and implied move is
  stable, which is exactly the kind of assumption that has burned this project
  before.
- No transaction or assignment cost is modelled.

## Why this is recorded and not acted on

The purpose was to know what the book is betting, not to change it. The
structures are frozen positions in a forward record, the calculation is
`n = 8`, and I am unattended. **Recorded, not traded.**

The one thing worth carrying into the competition account's sizing: a structure
whose fat tail points the same way as the underlying's historical drift deserves
**smaller** size than its EV suggests, not the same size.
