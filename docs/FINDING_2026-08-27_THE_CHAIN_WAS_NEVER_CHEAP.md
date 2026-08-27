# FINDING 2026-08-27 — the chain was never cheap

**Status:** three unit errors found, fixed, pinned by test (`tests_smoke_chain_width.py`, 10 checks).
**Receipts:** `state/decisions.jsonl` (8,461 rows), `state/fills.jsonl` (872), live Alpaca account reads.
**What it explains:** why dev is −5.28% and exp1 −6.73% from $100,000 in three sessions while holding,
between them, five long index straddles.

## The symptom

Across 6,070 decisions carrying both a forecast and a quote, the machine believed the option chain was
**CHEAP on 96.4% of observations**, at a pooled median forecast-sigma / implied-move ratio of **1.96**.
A system that thinks the market under-prices volatility 96% of the time is not finding an edge. It is
reporting a units error.

43 of its 71 entry-shaped decisions were `long_straddle`. Both books went into the NVDA print long premium.

## What it was NOT — four hypotheses killed before the right one

Each of these was my first guess, and each is refuted by measurement, not by argument.

| hypothesis | test | verdict |
|---|---|---|
| the EWMA sigma is too high | replicate it from bars, 15 symbols | **REFUTED.** ratio to independently computed truth = **1.00** on every name |
| the IEX feed inflates realised vol via noisy closes | Parkinson vs close-to-close, AR(1), VR(5) | **REFUTED.** AR(1) ≈ +0.01, VR(5) ≈ 1.05 — no bid-ask-bounce signature |
| IEX differs from the real consolidated tape | pull the same 90 days on `sip` and diff | **REFUTED.** median IEX/SIP vol ratio **1.00**, max close gap 1.3% |
| the bid-ask spread eats the premium | fill audits deduped to 19 unique orders, first mark after fill | **mostly refuted.** median round-trip haircut **2.6%**, not the 20%+ needed |

The realised volatility is real. MSFT genuinely ran ~39% annualised in this window. The error is on the
**chain** side, and it is arithmetic.

> A note on a number that looks like evidence and is not: summing `pnl_usd_if_closed_now` over all 750
> audit rows gives −$302,818, which is nonsense — the auditor re-marks the same 22 orders hundreds of
> times. Dedupe by `alpaca_order_id` before reading any total out of that file.

## Error 1 — a 15% haircut on every quote the chain ever gave us

`ChainSnapshot.implied_move` returned `0.85 * straddle / spot`.

At the money the straddle price **is** the expected absolute move. It is an identity, not a rule of thumb:

```
straddle = E[(S−K)⁺] + E[(K−S)⁺] = E|S−K|      when K is the forward
```

Verified numerically at σ ∈ {10%, 20%, 40%, 80%} × T ∈ {1, 2, 3, 7, 30} days: **E|move| / straddle =
1.0000** in all twenty cells. The correct conversion has **no multiplier at all**.

Downstream, `runner.effective_sd` multiplies by `√(π/2)` to turn an expected absolute move into a standard
deviation — which is right *only if what it is handed really is E|move|*. With the haircut, the chain read
**17.6% cheaper than it was quoting**, on every symbol, on every pass, since the beginning.

The old comment argued the opposite of what the old code did: *"a straddle costs roughly 0.8 · E|move|"*
implies **dividing** by 0.8 (×1.25), not multiplying by 0.85. The comment was closer to right than the code.

Same haircut, same line, second site: `alpha/surface.py`. Both fixed.

## Error 2 — calendar days used as a volatility clock

`structures._days` returned **calendar** days, and every consumer of `Structure.days_to_expiry` uses it to
scale a **per-trading-day** volatility (`payoff.economics`, `equity.stress_charge`, the vol-of-vol check).
A Friday position facing a Monday expiry had three calendar days and one session — claiming **√3 = 1.73×**
the variance the market can actually deliver.

`_days` now counts trading sessions, skips weekends and a named holiday list, and prices the part-session
in progress as a fraction. Black-Scholes discounting still uses calendar time on `Contract.years_to_expiry`;
they are deliberately two different clocks.

## Error 3 — a one-directional rescale

```python
if horizon_days and structure.days_to_expiry > horizon_days:      # scales UP only
    sd = sd * math.sqrt(structure.days_to_expiry / horizon_days)
```

It widened the forecast when the structure outlived the horizon and did **nothing** when the horizon
outlived the structure. That is not conservatism — it is an error that only ever points one way: long
premium always looks cheap, short premium always looks dear. With `--horizon` hardcoded at **3.0**, a
1-session option was priced at √3 of its real width, and the error grew as expiry approached, which is
exactly when theta is most lethal.

Now symmetric. `horizon_days=None` still disables rescaling, which stays correct for a `direction` brain
(already the chain's width) and for an event sd, which does not shrink with √time. The caller owns that
judgement; the function no longer guesses it.

`run_pass --horizon` now **derives** the horizon from `--expiry` instead of defaulting to 3.0.

## The size of it, on a real trade

`20260825T1534:narrative_dispersion:SPY` — long SPY 765 straddle, paid $775/unit, breakeven move 1.01%.

| | forecast sd | verdict |
|---|---|---|
| as coded | 1.57% over "3 days" | **EV +$168/unit** → submitted |
| shrunk onto its actual life | 1 session | **EV −$237/unit** |

Same quotes, same brain, same day. The trade was arithmetic.

## AND A FOURTH THING, WHICH IS NOT A BUG — two brains inflate sigma

With the units corrected, one question survives: whose sigma? Measured against EWMA truth computed from
bars strictly **before** 25 Aug (no lookahead), on 25 Aug:

| brain | n | median sigma / measured truth | share >1.15× | trades submitted |
|---|---|---|---|---|
| `event_move` | 77 | **1.51×** | 100% | 0 |
| `options_attention` | 1,541 | **1.17×** | 57% | 4 |
| `narrative_dispersion` | 1,476 | **1.16×** | 54% | 5 |
| `relay` | 263 | 1.03× | 0% | 0 |
| `vol_gap` | 1,673 | **0.97×** | 0% | 13 |

`vol_gap` — the brain with no LLM in it — is **accurate**. The two brains that inflate sigma by ~16% are
the ones that bought the SPY and IWM straddles that are now the largest losses in exp1. A 16% inflation is
on its own enough to flip a straddle's sign, because the entire edge is `forecast_sd − implied_sd` and
implied_sd is close to truth.

This is **not** fixed here. It is a claim about two brains' calibration and it needs its own measurement
against more than one day. Recorded as a lead, with a number attached.

## What this does and does not license

It does **not** license "so now we sell premium." The corrected arithmetic says the chain is fairly priced
to slightly rich, which mostly licenses **refusing** — cash is a structure with EV exactly zero and most of
these straddles could not beat it. Turning the same broken comparison upside down and shorting gamma into
an event would be the identical mistake with the sign flipped.

**The running loops are not affected until they restart** — Python cached these modules at process start.
The restart is attended, and it must happen before the next pass, because today's expiry is **one session
away**, which is where the horizon error was largest.
