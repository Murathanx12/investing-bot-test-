# FINDING 2026-08-27 — the index premium is real, decaying, and lives in the wing

**Receipts:** `state/index_premium_backtest.json`, `state/index_premium_verdict.json`
**Commands:** `python -m scripts.index_premium_backtest` → `python -m scripts.index_premium_verdict`
**Data:** 381 weekly ATM straddles on SPY/QQQ/IWM, held to expiry, 2024-02-05 → 2026-08-17.
Entry at the close four sessions before a Friday expiry, settled at intrinsic against the
expiry close. Costs charged: 1.3% of premium per side, measured from this account's own fills.

## Why this was run

The 27 Aug width fix says the chain is **not** cheap
(`FINDING_2026-08-27_THE_CHAIN_WAS_NEVER_CHEAP.md`). It does not say the chain is **rich**, and
"so now sell premium" would be the identical mistake with the sign flipped. This measures it.

## The headline, which is a trap

| | n | mean/wk | median | hit | t | worst week |
|---|---|---|---|---|---|---|
| **buyer** | 381 | −19.8% | −38.5% | 31% | **−5.90** | −100.8% |
| **seller** | 381 | **+17.2%** | +35.9% | 68% | **+5.12** | **−254.3%** |

Implied exceeded realised on 262 of 381 weeks. The seller's mean clears the sample's own MDE of
9.4%/week. Taken alone this reads as a large, resolvable, tradeable edge.

**It is not, for three reasons, and each one had to be looked for.**

## 1 — it is decaying, and this year it is gone

| year | n | mean/wk | t | hit | worst |
|---|---|---|---|---|---|
| 2024 | 141 | **+29.1%** | 5.86 | 75% | −174.4% |
| 2025 | 150 | +16.9% | 3.13 | 69% | −254.3% |
| **2026** | 90 | **−0.8%** | **−0.10** | 57% | −221.1% |

Positive in two years of three. The pooled t of 5.12 is substantially a 2024 result. An arm seeded
on the pooled mean would be seeded on a regime that the current year contradicts.

By symbol the same instability shows cross-sectionally: SPY +29.2% (t 5.42), IWM +22.5% (t 4.33),
**QQQ −0.1% (t −0.01)**. One of the three names our books actually bought carries no edge at all.

## 2 — capping it kills it

An undefined short straddle is not a tradeable object at $100k with a −254% week in the sample. So
buy a wing:

| wing | mean/wk | t | worst | reading |
|---|---|---|---|---|
| 1.0× implied move | −5.5% | −3.17 | −43.3% | **DIES** |
| 1.5× | −1.9% | −0.77 | −78.6% | **DIES** |
| 2.0× | +2.2% | 0.75 | −119.2% | marginal |
| 3.0× | +6.2% | 1.89 | −212.6% | marginal |

The edge only survives at wing distances so far out that the "cap" barely caps anything — at 3.0×
the worst week is still −212%. **The premium being collected is payment for exactly the outcome the
wing removes.** That is a crash-risk premium being correctly priced, not an inefficiency.

## 3 — compounded, the tradeable versions lose

Risking a fixed fraction of current equity each week, $1 over the 381 weeks:

| structure | 2%/wk | 5%/wk | 10%/wk | max DD at 10% |
|---|---|---|---|---|
| naked short straddle | 3.59 | 21.31 | **288.16** | 60.6% |
| capped at 1.5× | 0.85 | 0.62 | **0.31** | 92.4% |
| capped at 2.0× | 1.16 | 1.30 | 1.22 | 90.9% |

The un-runnable version is spectacular and the runnable versions are flat to negative. That
juxtaposition is the whole finding, and it is the shape of every short-volatility blow-up on record.

## THE WEAKEST LINK, NAMED

**This receipt never priced a wing.** `capped_seller` charges a decay heuristic
(`exp(−0.9·wing_sd)`, floored at 10%), and the capped conclusion is highly sensitive to it:

| assumed wing cost, as a fraction of the ATM premium | mean/wk at 1.5× | t |
|---|---|---|
| 5% | +19.0% | 7.63 |
| 15% | +9.0% | 3.62 |
| 20% | +4.0% | 1.61 |
| **25.9%** (the heuristic used) | −1.9% | −0.76 |
| 35% | −11.0% | −4.42 |

A 1.5× wing must cost **under ~20% of the ATM premium** for the capped seller to be positive at all.
Whether it does is a fact about real chains that this run did not look up. So conclusions 2 and 3
above are an **assumption with a number attached**, not a measurement, and they are labelled that
way in the tool's own output.

**The decisive next measurement** is pricing the actual wing contracts off expired OPRA bars — the
same data path `one_week` already uses, two extra strikes per week. Until that runs, conclusion 1
(the regime decay) is the only one standing on measured data alone, and conclusion 1 is on its own
sufficient to refuse the trade.

## VERDICT

**REGIME, NOT EDGE.** No premium-selling arm is seeded on this. Recorded as
`FAILED_VARIANT` for the *pooled-mean* version, **not** `MECHANISM_REJECTED` — the variance risk
premium is not refuted by a three-year sample in which it decayed, and the wing-price measurement
could still revive a defined-risk version.

What this **does** settle, and it is the useful part: the corrected width arithmetic licenses
**refusing** long premium, not reversing into short premium. Cash remains the structure to beat, and
on this sample it beats both tradeable versions.
