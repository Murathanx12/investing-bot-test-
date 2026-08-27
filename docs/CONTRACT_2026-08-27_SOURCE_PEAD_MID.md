# STRATEGY CONTRACT — `SOURCE_PEAD_MID_v1` (account role `pead`)

**Licence:** `PRODUCT_EXPERIMENT` — internal simulation + external PAPER brokerage.
**Frozen:** 2026-08-27, BEFORE the account's first decision. Account `PA3LY4QK3A6A`, $100,000.00, untraded.
**Hash:** see `state/contracts/source_pead_mid_v1.json` (`python -m scripts.contract --verify pead`).

A `PRODUCT_EXPERIMENT` needs no significance gate, no MDE and no preregistration. It needs THIS: a
frozen statement of what will be traded, written down before the first decision, so that what the
book did later cannot be re-described afterwards.

---

## 0 — What this account is NOT testing

"PEAD" generically is dead here and this contract does not revive it:

- **The pre-event RELAY is refuted** (t −2.0).
- **The post-event PEER relay is refuted** — on 290 relay legs the peer straddle lost (mean −4.2%, hit 34%).
- **The WIDE whole-market unhedged short is CLOSED.** `WIDE_UNHEDGED_SHORT_ENABLED=False` and it stays
  False. Its +0.44%/3d was excess-over-QQQ; raw it was +0.03%, and in simple returns the unhedged
  short is +0.04%. 6 of 11 quarters negative, 2026 negative, and UP prints RISE raw.

This account tests exactly one surviving mechanism, and nothing adjacent to it.

## 1 — The hypothesis, stated so it can fail

> **A name that has just printed drifts in the SIGN of its own day-0 move, over the following three
> sessions, measured as excess over `beta * QQQ` — and the effect is concentrated in the MIDDLE of
> the day-0 move distribution.**

Not "earnings drift". Not "the market underreacts". This one sentence, with the tercile.

## 2 — Qualifying event (all must hold; any failure is a REFUSAL, not a smaller trade)

| condition | value | why this and not something wider |
|---|---|---|
| event source | **SEC 8-K Item 2.02**, exact filing date and session | a wire headline is not a dated event; `bmo` is the same session, `amc` the next |
| day-0 bar | **closed** | daily bars cannot distinguish an in-progress session; the brain refuses while it forms |
| \|r_0\| lower bound | **≥ 3.5%** | small tercile is t 0.66 — a print the market shrugged at has nothing to continue |
| \|r_0\| upper bound | **≤ 8.2%** for full conviction; above it conviction HALVES | large tercile t 1.26 — a 20% move has already over-reacted |
| sessions elapsed | **≤ 3** since the print | the drift is +0.41/+0.31/+0.41% over +1/+2/+3 and is spent after that |
| direction | either, but the **DOWN side is the stronger half** (hit 72%, t 2.37 vs up 54%, t 1.65) | recorded so an up-side loss is not read as a surprise |

The mid tercile is where the evidence is: **t 3.45 at hit 81%**, against 0.66 and 1.26 either side.

## 3 — Instrument, and the reason it is not an option

**SHARES, or a debit spread whose round-trip is inside the cost budget. Never a wide long option.**

The whole edge is about **1% of spot**. At a 1% round-trip cost the mean falls to +0.13% and t to 0.32
— *it dies of costs, not of doubt*. A long option gives the entire edge back in half-spread, and the
tercile split says the jump it would be paying for is not in this signal. The shape is **GRADIENT**
(centre/sd ≈ 0.21): a tilt, not a tail.

**Cost budget: the modelled round trip must be < 0.50% of spot.** Above that the trade is REFUSED,
because at 1% there is provably nothing left.

## 4 — Fill convention

- **Entry: the day+1 OPEN.** Measured, not assumed — entering there keeps +1.08% of the +1.13% at
  t 2.82. The overnight gap is worth only +0.05% (t 0.42), so chasing the close of day 0 buys nothing.
- **Arriving late is allowed and priced:** a full session late still keeps +0.72% at t 2.17. When one
  session has elapsed the brain quotes the LATER arrival's number, not the headline.
- **Exit: the day+3 close**, or earlier on the declared stop.
- Costs are charged on both legs. Zero-cost is not a permitted diagnostic on this account.

## 5 — Objective

Terminal wealth of the `pead` account under the **balanced** personality, measured against **two**
benchmarks, both named in advance:

1. the `market` arm (`PA3I7VTCC0BM`, buy-and-hold) — the PRODUCT question;
2. the same events traded with the sign FLIPPED — the SIGNAL question. Two books can beat the market
   for the same reason and neither of them be the reason.

## 6 — Risk

| limit | value |
|---|---|
| risk per event | ≤ 2% of equity at the declared stop |
| concurrent events | ≤ 5 |
| single-thesis share of book max loss | ≤ 20% |
| effective N by RISK | ≥ 2.0 before a 6th position |
| daily latch | −3% |

The DOWN side is traded **only as a pair** (short the loser, long IWM). The unhedged short stays
refused — that is the one thing the wide study settled.

## 7 — What would retire this arm

- The mid-tercile edge fails to clear the flipped-sign control over 20 qualifying events; **or**
- realised round-trip cost exceeds 0.50% of spot on a majority of fills, at which point the mechanism
  is real and untradeable and should be said so; **or**
- the +1..+3 window stops containing the drift.

**None of these is "it lost money this quarter."** 6 of 11 quarters were negative in the wide study
and that is compatible with a live edge; a retirement needs the measurement above, not a drawdown.

## 8 — What is frozen

The version. Once this account takes its first decision, `SOURCE_PEAD_MID_v1` does not change: a new
threshold, a new tercile, a new instrument or a new exit is `_v2` on a different account or a
declared restart, never an edit here. Edits to this file after the first decision are a contract
breach and the ledger will show the timestamps.

**NOT YET SEEDED.** This contract exists so the arm *can* be seeded. Seeding is attended and Murat
flips it. Until then `pead` holds $100,000 and has never traded.
