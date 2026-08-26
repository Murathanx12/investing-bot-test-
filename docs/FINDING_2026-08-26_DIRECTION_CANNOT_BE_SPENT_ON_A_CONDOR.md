# FINDING 2026-08-26 — the first positive t survives being taken apart, and the engine could not spend it

`PRODUCT_EXPERIMENT`. Paper accounts only. Receipts: `state/source_pead_decompose.json`,
`state/source_pead_horizon.json`, both derived from `state/post_event_relay.json`.

**RESULT IMPROVEMENT: no P&L (market closed all session).** What changed: the one
mechanism with a positive t is now decomposed, dated, cost-tested and built as a brain —
and building it exposed a defect in the core gate that had nothing to do with it.

---

## 1. The headline was taken apart and it held

`scripts/post_event_relay.py` reported source PEAD at **+1.13% 3-day excess, hit 64%,
t 2.72, n=108**. A t computed on 108 overlapping legs from 11 names is not evidence, so
`scripts/source_pead_decompose.py` asked the three questions that usually kill one.

| question | if it were an artefact | what it says |
|---|---|---|
| is it one name? | one name carries it | **no** — 10 of 11 positive; leave-one-out t never below **2.37**. The only negative name is GOOGL, and removing it *raises* the headline to 2.86 |
| are the legs independent? | clustering inflates t | **survives** — one observation per calendar week (62 blocks, the honest n) gives **t 2.23**; per event day, 2.78 |
| is it just long drift? | only up-days work | **no, and it is the reverse** — day-0 DOWN prints: hit **72%**, t **2.37**; day-0 UP: hit 54%, t 1.65. A bad print keeps being bad |

Two more cuts that shaped the brain rather than validating it:

- **it lives in the middle.** By |day-0 move| tercile — small (<3.5%) **t 0.66**, mid
  (3.5–8.2%) **t 3.45 at hit 81%**, large (>8.3%) t 1.26. A print the market shrugged at
  has nothing to continue; a 20% move has already over-reacted.
- **it dies of costs, not of doubt.** Charged to every leg: 0.25% → t 2.12, 0.50% →
  t 1.52, **1.00% → mean +0.13%, t 0.32.** The entire edge is about 1% of spot.

## 2. It survives arriving late — which is the only reason it is tradeable this week

The competition account is created at kickoff on **28 Aug**. NVDA's first reflecting close
is **27 Aug**. If the drift were day +1, a book that opens on 28 Aug would be buying the
part that already happened. `scripts/source_pead_horizon.py` splits the same excess:

```
day +1  +0.41%  t 1.61        overnight gap (day-0 close -> day+1 open)  +0.05%  t 0.42
day +2  +0.31%  t 1.26
day +3  +0.41%  t 1.67

arrival                                          keeps
day-0 close -> +3 close   (the headline)         +1.13%  hit 64%  t 2.72
day+1 OPEN  -> +3 close   (woke up late)         +1.08%  hit 62%  t 2.82
day+1 close -> +3 close   (a full session late)  +0.72%  hit 62%  t 2.17
day+2 close -> +3 close                          +0.41%  hit 55%  t 1.67
```

The drift is **flat across all three days** and the overnight gap is worth nothing, so
arriving at the day+1 open costs 5bp — the t actually *rises*, because dropping the gap
drops its variance. A signal concentrated on day +1 would have been the suspicious
outcome; this is not that.

## 3. The brain — `alpha/brains/post_event_drift.py`

Fires on an SEC 8-K Item 2.02 print whose first reflecting close is 1–2 sessions old.
Deliberately conservative in two places:

1. **It refuses while the day-0 bar is still forming.** Daily bars cannot tell an
   in-progress session from a closed one, and the measured entry is the day+1 open anyway.
2. **At one session elapsed it quotes the LATER arrival's number** (+0.72%, two sessions
   left) even when it may be entering at that session's open, where the measurement says
   +1.08%. Under-sizing is the safe error.

Refuses below |3.5%|; halves conviction above |8.2%|; mirror-symmetric on the down side,
because the down side is the stronger half. 38 checks in `tests_smoke_pead.py`, built on a
synthetic planted print — no live name has printed in the last two sessions, so the brain
correctly declines on all 15 today and that proves nothing.

## 4. THE DEFECT IT EXPOSED — a directional brain was handed an iron condor

Probing the finished forecast through the real engine on a live NVDA chain:

```
NVDA, centre +0.72% (UP print)    -> APPROVED  iron_condor  risk 4.5%  EV $54/unit
NVDA, centre -0.72% (DOWN print)  -> APPROVED  iron_condor  risk 4.5%  EV $48/unit
```

**The same condor, from opposite forecasts.** The sign of a mechanism measured across 108
prints moved the answer by $6 on $54 and changed nothing else.

The cause is not the ranker; it is `sd`. A brain's sd enters the gate as a claim that the
chain has the WIDTH wrong. A directional brain makes that claim by accident — its sd is a
two-day realised-vol estimate, implied sits above trailing realised most of the time, so
every long option looks overpriced and every short-premium structure looks free. The
biggest such "disagreement" available is always the condor, and the condor cannot see a
sign. **The engine was spending a directional edge on a volatility opinion the brain did
not have.**

This is `shape.py`'s own thesis failing in the mirror: not buying a tail that is not
there, but selling one it has no view on.

### The fix

`Forecast.claim` — `direction` | `dispersion` | `distribution`, defaulting to
`distribution` so every existing brain is byte-identical. A `direction` brain is
integrated at the **chain's own width** (`runner.effective_sd`: the structure's ATM
implied move converted with `sigma = implied * sqrt(pi/2)`, the same conversion
`sizing.implied_probability_beyond` already uses, so the gate compares like with like).
The brain supplies the centre; the market supplies the spread. A chain that cannot quote
its own width **refuses** rather than falling back — a fallback would silently restore the
bug on exactly the illiquid names where it does most damage. A `dispersion` brain that
tilts is refused at construction.

### What it does now

```
NVDA UP    -> candidates are long_call / bull_call_spread / bull_put_spread
NVDA DOWN  -> candidates are long_put  / bear_put_spread  / bear_call_spread
iron_condor -> "66.9% of mass vs the market's 67.2% -- we agree with the chain"
```

Perfectly mirrored, and the condor is gone from both sides.

## 5. And it still refuses, which is the honest answer

On the 28 Aug chain nothing clears: the directional disagreement is **3–5pp against a
5pp floor**, and where it clears (AMD `bull_call_spread`, +5.1%) **cash beats it on EV**
at −$6/unit. That is not a bug to tune away — it is §1's cost table arriving at the same
number by a different route. A 0.72% edge does not pay a mega-cap option spread.

**The 28 Aug expiry contains tonight's NVDA print**, so NVDA's implied is inflated by the
event and our shift looks small against it. When the brain actually fires — 28 Aug,
against a post-print expiry — implied will have collapsed and the same centre will be a
larger fraction of the chain's width. Whether it clears then is the measurement, and it
has not been made.

## What is NOT claimed

- Not a `RESEARCH_CLAIM`. The tercile band and the arrival table were chosen after looking
  at the data. `PRODUCT_EXPERIMENT` permits that; a claim would not.
- The 2026 sub-sample is the weakest (t 0.85 on n=30, a partial year). Not a dead signal,
  not an accelerating one.
- No live grade exists. The first is NVDA: prints 26 Aug amc → day 0 is 27 Aug → the brain
  can speak on 28 Aug → the window closes 1 Sep, inside the competition.
