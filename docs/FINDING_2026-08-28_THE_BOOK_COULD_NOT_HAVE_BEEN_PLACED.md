# The book was internally consistent and could not have been placed

*2026-08-28. Review of `COMPETITION_BOOK_v1` against Alpaca's actual order
semantics and against a live chain.*

`COMPETITION_BOOK_v1` obeyed every limit it declared, refused what it said it
would refuse, and passed 27 of its own checks. It would have failed at the venue.

## 1. It printed an order type that does not exist for its own core

Step 5 of the book read:

> **5. TIMING** enter MARKET-ON-CLOSE, not at the next open.

The instruction came from a real result — over CRSP 1993-2024 the overnight
segment compounded **+17.31%/yr** against intraday **−7.26%**. The finding is
sound. The order is not placeable, and the part that cannot place it is the
**70% core**:

- Alpaca supports `time_in_force` of **`day` only** for options, single-leg and
  multileg alike. `cls` returns *"order_time_in_force provided not supported for
  options trading"*.
- `cls`/`loc` exist for equities, but *"CLS orders submitted after 3:50pm but
  before 7:00pm ET will be rejected."*

This would have been discovered at 15:50 ET on a competition day, against the
judged account, with no rehearsed fallback.

### The quieter half

The 3:50 cutoff means **the signal cannot be computed from the 16:00 close it
intends to trade**. An MOC order must be in the book ten minutes before the price
it fills at exists. Any design reading today's close and sending today's MOC is
using information that did not exist when the order had to be submitted — the
same lookahead the replay is careful to avoid, reintroduced by the execution
layer.

`alpha/timing.py` encodes both: `entry_timing` refuses an MOC whose signal froze
after 15:45 ET, and refuses one whose freeze time is merely *unknown*, because an
unknown cannot be shown to precede the cutoff.

## 2. It invented the prices it was tested on

```python
width  = max(1.0, round(px * 0.05))
credit = width * 0.30
```

The strike grid is invented (real SPY chains are $1 near the money, $5 further
out — not a fixed 5% of spot), the credit is invented, and therefore so is max
loss, which the entire sizing chain divides by.

`alpha/spreads.py` reads the real chain and crosses the spread **against us on
both legs** — short leg at `executable_bid`, long leg at `executable_ask` — so
`credit` is a lower bound and `max_loss` an upper bound. `best_spread` returns
`None` rather than a fallback when nothing clears, and every rejection is
counted, so "no trade" is a measurement and not a silence.

### Running it live found two more defects

On SPY at $770.83 the constructor's first answer was **763P/762P — $1 wide, 1%
out of the money, paying 43% of width.** That looks like an enormous credit and
is close to a fair coin. Ranking a whole chain by credit/width reliably selects
the narrowest, nearest-the-money spread, which is the one closest to a coin flip.

The deeper problem is **evidence transfer**: the replay measures one specific
structure. Applying its distribution to whatever the chain prices most generously
today silently substitutes one bet for another, and the sample says nothing about
the substitute. `matching_spread` now selects the **replayed geometry** and the
credit ratio became a check on that structure rather than the thing maximised.

Second: the feed returns **no open interest**, so the liquidity gate had been
passing everything. A missing field read exactly like a field that cleared the
check. It is now reported as an **unrun check**.

## 3. It called one bet three

```python
CORE = ["SPY", "QQQ", "IWM"]   # "three diversified positions"
```

Three bullish index credit spreads are one `MARKET_BETA` node plus one
`SHORT_VARIANCE` node wearing three tickers. The book capped 6% per name, held
three names, and believed it had spread 18% across three risks.

`alpha/nodes.py` attributes each position's defined loss to the **causes** that
would produce it, measuring the beta loading from returns and declaring the
structural ones. The same three positions score **1.54 effective nodes**.

## 4. It ranked on the median and fixed 70/30 by fiat

A +0.4% median book is an excellent real-money book and a guaranteed mid-table
finish. `alpha/tournament.py` separates the two objectives that were being
conflated:

- **real account** — maximise expected **log wealth**; ruin is absorbing;
- **contest** — maximise **P(final ≥ target)** under a hard floor, because second
  place and last place pay the same.

A double-or-halve is worth exactly **zero** to the first and **+25%** to anyone
ranking on the arithmetic mean. The two objectives disagree about the same
gamble, which is why they cannot share a function.

Beta then has no entitlement to 70%: it wins increments in an auction or it does
not get the money.

## Four bugs the tests found in the replacement

The replacement was not born correct either. Each of these was caught by a check
rather than by inspection:

1. **The threshold objective has no gradient.** A greedy auction against a far
   target allocates *nothing*: no single $2,000 increment can turn $100k into
   $108k, so every marginal utility is zero — and that is precisely the ATTACK
   case the objective exists for. Fixed with block bids.
2. **The bid ladder had gaps.** Doubling offers 1x, 2x, 4x, 8x and never the
   exact remaining budget, so a target only the full budget could reach looked
   unreachable. The maximum feasible bid is now always offered.
3. **The per-name cap was defeated by decomposition.** SPY appears as
   `SPY:long_shares`, `SPY:long_atm_call`, `SPY:call_debit_spread`, each with its
   own $6,000 ceiling — so "6% per name" permitted 18% on one underlying, and the
   auction broke no rule it could see. Ceilings now aggregate per symbol.
4. **The cap was enforced against a different number than it was reported
   against.** The auction checked node caps *without* betas (21.0%, passing)
   while the report applied *measured* betas (24.1%, breaching).

And one design inconsistency worth naming separately: `mode_for` printed **BASE**
while the auction bought three index calls with medians of −3.8% and −7.4%,
because P(target) was the only thing being asked. The mode was advisory and the
objective was not listening. **The mode now selects the objective** — BASE
maximises log wealth, ATTACK maximises P(target).

## What it costs to be right about this

Under the growth objective on the measured evidence, the book gives up almost
nothing in P(target) — 32.9% against 35.9% — and improves p10 final equity from
$93,492 to $95,293. The contest objective is still available and still correct
when behind and out of sessions; it is simply no longer the default.

## Status

Engineering correction, not a research claim. The venue facts are quoted from
Alpaca's documentation and pinned by `tests_smoke_execution.py`; **the order
payloads have not yet been exercised against a live account**, which remains the
one thing on this page that is documented rather than demonstrated.
