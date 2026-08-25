# HANDOFF — read this first

**Updated 2026-08-25, ~07:30 ET.** Competition derivative of the Aegis-Finance
research project (`AEGIS_SOURCE_COMMIT=44c8352`).

---

## COMPETITION SCOREBOARD

```
competition account equity      NOT YET CREATED (create at kickoff 28 Aug 15:00 UTC)
dev account                     PA32Q5IW7TAS  $100,000  options level 3  crypto active
experiment account exp1         PA3AOJPJTSBW  $100,000  options level 3
competition return              n/a
best live strategy              vol_gap -> structure enumeration; ONE rehearsal order sent
best shadow strategy            shadow arena NOT BUILT
active independent brains       1 of 5 planned (vol_gap)
options trades / win-loss       1 submitted (TSLA 350 straddle x3, queued) / 0-0
max drawdown                    n/a
unused buying power             $400,000 (dev)
LLM calls / spend               0 / $0
execution failures              0
service uptime                  not deployed
submission readiness            engine works end-to-end; no dashboard, no MCP/CLI, no writeup
COMPETITION RESULT IMPROVEMENT  FIRST ORDER PLACED. Engine is live but untested against a fill.
```

---

## Step by step — what Murat does, in order

**1. Now — nothing.** The dev account (`PA32Q5IW7TAS`) and experiment account
(`exp1`, `PA3AOJPJTSBW`) are wired and working. Keys are in a gitignored `.env`.

**2. Rotate the leaked LIVE keys.** The first pair pasted into chat
(`AK32UD5...`) were **live-host keys**, account `349598088` — not paper. Equity
was $0 so nothing could happen, but they are now in a chat log and were briefly
in a local file. Delete them at `app.alpaca.markets` → API keys. The repo's
guard caught them independently (`_verify_paper` refuses any account number
without a `PA` prefix), which is the guard doing its job on its first real
input.

**3. 28 Aug, at kickoff (15:00 UTC = 23:00 Hong Kong, Friday evening):**
   - re-pull the rules page and diff it against `docs/RULES_SNAPSHOT_2026-08-25.md`;
   - create a **brand-new** paper account, balance exactly **$100,000**;
   - generate keys, put them in `AAT_COMPETITION_KEY_ID` / `AAT_COMPETITION_SECRET_KEY`;
   - run `AAT_ACCOUNT_ROLE=competition python -m scripts.preflight` — it checks
     paper status, the $100k, **freshness** (zero orders, zero positions),
     options level and the data feed;
   - **never place a test order on it.** Freshness is the one property that
     cannot be repaired: resetting the account is itself a reuse.

**4. Optional, decide 27 Aug: buy Algo Trader Plus ($99).** See below — it is
now a measured decision rather than a guess, and the answer is "not required".

---

## The $99 question, answered with measurements

**You do not have to buy it.** Here is the actual evidence.

Asking for `feed=opra` on your account returns **403 "OPRA agreement is not
signed"**. That message reads like paperwork and is not — Alpaca support
confirms it means the Algo Trader Plus subscription is absent, and no agreement
exists that avoids it. So the free plan means the `indicative` feed.

Measured on `PA32Q5IW7TAS`, SPY, expiries within ten days:

| | free `indicative` |
|---|---|
| contracts returned | 1000 (the page limit — coverage is not the problem) |
| with **both** bid and ask | **1000 (100%)** |
| with greeks / IV | 462 (46%) |
| relative spread | median 5.3%, p25 1.5%, p75 18.2% |
| contracts at ≤5% spread | 400 |

**The free feed is not missing data. It is late** — roughly 15 minutes during
market hours. That is a different problem and it has an engineering answer,
which is now built:

1. **Delta-adjusted quotes.** The underlying is real-time and free (IEX). A
   stale option quote is carried forward with `mid + delta·dS + ½·gamma·dS²`.
2. **A staleness penalty.** The bigger the carry-forward, the more the assumed
   execution price is widened — so delayed data costs edge instead of being
   silently treated as live.
3. **Missing greeks are computed.** Black-Scholes from the recovered IV, and
   `greeks_source` records whether a number came from the venue or from us
   (measured: 461 from feed, 536 computed, 3 unrecoverable).
4. **A hard refusal past ~25 minutes of market-time staleness.**
5. **One-sided quotes refused.** AVGO came back with a bid and an ask of exactly
   **zero** on IEX while SPY was clean. A mid from that is half the real price
   and would flow silently into every delta adjustment, so the underlying price
   comes from the last **trade** (which has no sides) and the quote is only a
   fallback.

**What this costs, stated plainly:** the agent **cannot trade reactions.** If
AVGO gaps 8% on its Wednesday print, our chain shows the pre-print world for a
quarter of an hour and no delta adjustment invents the volatility repricing.

**Why that is survivable:** the entire strategy in `docs/STRATEGY.md` is
**positioning ahead of scheduled catalysts**, not reacting to them. Buying an
AVGO straddle at 14:00 ET for a 16:05 ET print is a question about whether the
implied move is mispriced, and a 15-minute-old quote answers it fine.

**Buy the $99 if, and only if, one of these becomes true:**
- measured slippage between our computed executable price and actual fills
  exceeds ~15% of expected edge (the rehearsal orders will tell us — that is
  what the quote snapshots in the ledger are for);
- we decide the Friday 4 Sep jobs-report trade (08:30 ET, deadline 11:00 ET) is
  worth doing, which is a genuinely fast 75-minute window;
- the scanner needs more than 30 streaming symbols.

Decide on 27 Aug with the slippage numbers in hand, not before.

---

## What now exists and is proven against a real account

| File | State |
|---|---|
| `alpha/config.py` | credentials, allowlists, `.env` loader, arbitrary experiment roles |
| `alpha/broker/alpaca.py` | paper-only client; account/positions/orders/chain/bars/trades/crypto |
| `alpha/data/chain.py` | chain snapshot, BS greeks, delta carry-forward, staleness penalty |
| `alpha/engine/shape.py` | **differentiator 1** — decile shape → instrument |
| `alpha/engine/sizing.py` | **differentiator 2** — MDM gate, rank objective, 3 risk profiles |
| `alpha/engine/structures.py` | 8 structures enumerated from a live chain, priced at the crossed side |
| `alpha/brains/vol_gap.py` | first brain: EWMA realised vol vs implied, damped momentum tilt |
| `alpha/runner.py` | the decision pass; ledger writes on every candidate |
| `alpha/ledger.py` | hash-chained append-only record, refusals included |
| `scripts/run_pass.py` | `python -m scripts.run_pass --expiry 2026-08-28 --live` |
| `scripts/preflight.py` | account verification |
| `tests_smoke.py` | 24 checks, no keys, no network |

**Verified against the live broker, not asserted:**
- multi-leg order accepted — TSLA 350 straddle ×3, limit $13.35, `accepted`;
- replaying the same decision → **422 `client_order_id must be unique`**, so a
  crash-restart cannot double a position;
- an order without a quote snapshot → refused locally;
- a non-`PA` account number → every subsequent call refused.

### The enumeration is the demo

Same code, same chain, three different forecasts:

| Forecast | Winner | Edge |
|---|---|---|
| mild bull (μ +1.2%, σ 1.0%) | bull call spread | +38.7% |
| big move (μ 0, σ 2.5%) | **long straddle** | +30.7% |
| very quiet (μ 0, σ 0.3%) | **iron condor** | +29.8% |

Nothing is hardcoded. The instrument falls out of the disagreement between our
distribution and the chain's. That is the single best thing to put in front of a
judge, and it is one screen.

### Four bugs that running it found and reading it would not have

1. A two-sided probability **credited a long call for a crash** — the position
   would have been sized up by the outcome that makes it worthless. `direction`
   is now a required property of every structure. And break-even is **signed**
   for directional structures: a bull put spread's break-even sits *below* spot,
   so an `abs()` turned the safest structure on the board into the most demanding.
2. The aggregate risk ceiling **did not bind within a pass** — six candidates
   each sized against the risk at the start of the loop, each passing a 50% test,
   totalling 300%. It read as enforced and was not.
3. The staleness guard **refused every structure while the market was closed**,
   which is exactly when the next session gets planned. Age is now measured in
   *market* time.
4. A straight ramp **classified as a TAIL**, so the agent would have bought
   convexity on every monotone signal.

---

## Next, in priority order

1. **Measure the fill.** The TSLA straddle fills at Tuesday's open. Compare the
   actual fill against `quote_snapshot` in the ledger. That number decides the
   $99 and it is the single most valuable measurement available this week.
2. **Exit management.** There is currently **no exit logic** — the agent can
   open and cannot close. Needs: profit target, stop, time stop, and the hard
   **10:45 ET 4 Sep** liquidation deadline. This is the largest gap and it is
   the one that turns a good week into a bad one.
3. **MCP + CLI.** Both are competition requirements and neither is done. CLI as
   the deterministic JSON audit path; MCP as the "why did you make this trade?"
   demo surface. Do not route the tick loop through MCP.
4. **Shadow arena.** N virtual $100k books off the same frozen decision state.
   `exp1` already gives one real second account for a second risk profile.
5. **Dashboard.** Judging criterion 4. The screen that matters most is the
   **refused candidates** — nobody else will have it.
6. **More brains.** `rev_dispersion` (analyst disagreement → straddle) is the
   one most worth having: the signal and the instrument are the same statement.
7. **Crypto sleeve.** 29–30 Aug have no equity market. Crypto is 25% of the
   calendar and is real-time and free.
8. **Railway deploy.** The agent must not need the laptop.
9. **First social post.** Separate $500 prize, engagement cannot be back-filled.

## Do NOT

- **Do not build a bull/bear/risk debate.** A competitor already is, and the
  parent project measured that specialist personas are correlated forecasters
  in costume.
- **Do not average mechanisms into one composite.** That is the parent
  project's diagnosed bottleneck — ten books that all select on one signal
  because everything was averaged. Each brain gets its own book, and a composite
  is always checked against its own best component.
- **Do not exploit the paper simulator.** Alpaca models neither market impact
  nor order size against displayed NBBO. `chain.MIN_QUOTE_SIZE` and limit-only
  orders are our own check. Fake P&L fails criterion 1 the moment a judge reads
  the contracts.
- **Do not use market orders.** A market order in a thin option fills at a price
  that never existed.
- **Do not continue the ordinary Aegis roadmap.**

## The two ideas everything rests on

**Shape decides the instrument.** A TAIL signal *is* an option — buy convexity,
narrow. A STEP signal is a stock book — buy breadth, wide. `mom_12_1` and
`rev_dispersion` are tails; `profit_roe` is a plateau and the agent **refuses**
to buy calls on it despite it having the strongest statistical evidence in the
whole programme. No prompt-based agent makes that refusal.

**Ask whether the trade can resolve before asking whether it wins.** A structure
bought at the ask and sold at the bid breaks even at a specific underlying move.
Unless our forecast puts materially more probability beyond it than the chain
does, we agree with the market and would pay to say so.
