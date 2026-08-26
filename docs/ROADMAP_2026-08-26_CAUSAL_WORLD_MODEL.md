# ROADMAP — Aegis Causal World Model (codename PSYCHOHISTORY)

**Adopted 2026-08-26 from Murat's review.** Status of v0: BUILT, SHADOW-ONLY, one record on disk.
Applies to the competition repo now and to Aegis Finance after it (§6).

## 0. The change in the question

Aegis asks *"does this measured signal survive?"* well. It does not ask *"what mechanism is
forming in the world before it is a stock signal?"* at all. The Causal World Model is the
hypothesis-generation and world-modelling layer UPSTREAM of the verification machinery. The
LLM is a **compiler**, never a stock picker; nothing it emits carries trading authority.

> Don't ask "what stock does this news affect?"
> Ask "if this fact is true, what else must become more or less likely — and who captures or
> loses the economic value as the consequences propagate?"

The one rule, enforced by the prompt and the schema: **never news → ticker.**

```
EVENT → ECONOMIC SHOCK → BOTTLENECK → EXPOSURE → FUNDAMENTAL CHANGE
      → SURPRISE VS EXPECTATIONS → MARKET MISPRICING → INSTRUMENT
```

## 1. What v0 is (`alpha/psychohistory.py`, `scripts/psychohistory.py`)

| piece | v0 |
|---|---|
| input | an **evidence bundle**: authored facts with sources (`state/psychohistory_evidence/*.json`) + what the machine measures itself: the chain's implied move, the crowd's Polymarket ladder, our brains' centres/widths |
| compiler | DeepSeek, temperature 0.2, JSON-only, English pinned, non-Latin refused; `max_tokens` 6000 after a 2,200-token truncation on the first call |
| output | `causal_chain` (edges with confidence + lag), 3–5 `scenarios` (p sums to 1, each commits to a **day-0 move bucket**, revenue/guide vs consensus, intermediate observations, **falsifiers — a scenario with none is refused**), `priced_in`, `surprise_axis`, `second_order` (who captures/loses value), `templates_used`, `candidate_expression` (a hypothesis, not an order), `what_would_change_my_mind` |
| buckets | `<-8.2% · -8.2..-3.5% · -3.5..+3.5% · +3.5..+8.2% · >+8.2%` — the PEAD brain's own terciles, so a resolved record grades the cut the trading rule uses |
| the market's distribution | the same five buckets from the chain's implied move under `sigma = implied·√(π/2)` — the sizer's own conversion |
| disagreement | per-bucket model−market, tail mass, up/down mass, total variation — stored BEFORE the outcome |
| resolve | realised bucket → Brier and log score for the model AND the market, `model_beat_market`, which scenario was realised, per-template calibration rows. The original row is never rewritten; the resolved copy is appended |
| authority | `action: SHADOW_ONLY` on every row |

**First record — `PH:NVDA:2026-08-27:b29d506d`** (26 Aug 05:00 UTC, before the print; $0.0034):
priced-in **0.80**; surprise axis *gross margin ≥74% under memory-cost inflation, and the guide*;
templates: cost-pass-through, bottleneck-rent, cross-country leading indicator, pull-forward-cliff;
model buckets `0.06 / 0.23 / 0.37 / 0.28 / 0.06` vs chain `0.10 / 0.19 / 0.42 / 0.19 / 0.10` — the
model carries **less tail mass than the chain (12% vs 20%)**, the same direction as our 0/8 straddle
backtest, and a mild up-skew. Resolve after the 27 Aug close:
`python -m scripts.event_grade NVDA --expiry 2026-08-28 --post --resolve PH:NVDA:2026-08-27:b29d506d`.

## 2. Reasoning templates (learned by calibration, never hard-coded as trades)

1. **bottleneck_rent_migration** — final demand ↑, the rent goes to the scarce input (AI chips → HBM → advanced packaging → power equipment).
2. **capacity_substitution** — the dominant supplier is full; marginal orders spill to the second (Samsung +15% while TSMC is constrained).
3. **pull_forward_then_cliff** — a tariff/control deadline pulls orders forward; the first stage looks structural and is not.
4. **cost_pass_through_chain** — one firm's pricing power is another's margin compression (HBM ↑: memory ↑, NVDA pass-through ?, customers who cannot pass it on ↓).
5. **capex_echo** — shortage → margins → capacity → equipment boom → oversupply, years later.
6. **geopolitical_substitution** — controls on A → stockpiling → sourcing from B → erosion of A's leverage.
7. **infrastructure_shadow_demand** — GPUs → electricity → transformers → copper → cooling → land → generation.
8. **reflexive_feedback** — price ↑ → cheaper capital → capacity ↑ → reported growth ↑ → valuation ↑, until the economics stop.
9. **cross_country_leading_indicator** — customs, freight, utilities and suppliers reveal a quarter weekly; the firm reports it once.
10. **contradiction_trading** — management says one thing, five physical indicators say another; the discrepancy is the information.

Each resolved record writes a Brier per template it used. When there are enough of them, scenario
probabilities are **weighted by template calibration**, not by the LLM's confidence.

## 3. The response function is a SHAPE, not a coefficient

The farm's finding — ranking signals by scalar strength gives the wrong construction — applies
here unchanged. A tariff is a **STEP** at an effective date; a shortage is **convex/TAIL** (nothing
until ~95% utilisation, then lead times explode); export acceleration is a **GRADIENT**; a
sanctions regime is STEP then GRADIENT as substitution develops. v1 adds `shape` to every causal
edge and the candidate expression must match it (`alpha/engine/shape.py` already maps shape →
instrument).

## 4. The score, when there is enough history to fit it

`EDGE = Surprise × Exposure × PassThrough × Bottleneck × Timing × Evidence × (1 − PricedIn) × HistoricalSupport`,
with every uncertain hop penalised, so a four-hop story with weak links scores below a one-hop
mechanism with strong evidence. Not fitted in v0 — the terms are recorded so it can be.

## 5. Build order (competition first)

- [x] **v0 shadow logger** — schema, compiler, buckets, disagreement, resolve, smoke checks (`tests_smoke_psychohistory.py`), first NVDA record.
- [ ] **Resolve the first record** after 27 Aug close (`scripts.event_grade --post --resolve`).
- [ ] **Adversarial falsifier pass**: a second compiler call asked only to refute each scenario and to price the falsifiers as observations; posterior update recorded as a new row, never an edit.
- [ ] **Trade Pulse v0**: Taiwan/Korea/China monthly customs by HS code (public), Foxconn/TSMC monthly revenue — three series, one join, a surprise (actual − expected) per release; recorded as `kind: measured` evidence automatically.
- [ ] **Belief vs compiler**: the crowd's ladder (Polymarket) vs the scenario tree's implied ladder, per record.
- [ ] **Dashboard**: the record's scenario tree, its falsifiers, and after resolution the Brier line — the "why this and not the five alternatives" screen a judge asked for.
- [ ] **v1**: edge shapes; template-weighted probabilities; the score in §4; agent-based simulation only after the graph has calibrated edges (parameters would otherwise be fiction).

## 5b. Built the same day, from Murat's second review (afternoon 26 Aug)

- [x] **`alpha/universe.py` — HIGH_DISPERSION_US_v1**: the whole listed market (4,634 names after price ≥ $2
  and median $3M/day on SIP), ETF-like flagged, dollar-volume buckets, market cap read per candidate. The
  IEX feed's volume is 2-4% of consolidated; the screen MUST read SIP (`stock_bars_multi(feed="sip")`).
- [x] **`scripts/candidates.py`** — every printer on the market-wide calendar through `post_event_drift`,
  with `UNIVERSE_COLLAPSE` instrumentation and the CONTROL holdings; fed into the loop every 6 h and into
  `run_pass --candidates`. First run: BJ / OSIS / HOV, zero from the old fifteen.
- [x] **`scripts/pead_wide.py`** — source PEAD measured across the universe by size bucket, with 10/21-session
  HOLD horizons on the same legs (the "hold the winners longer" question, measured not assumed).
- [x] **`scripts/daily_autopsy.py`** — after every close: best/worst movers, measured why, compiled why
  (template, knowable-before, precursor), industry clusters, graded against the candidate lane; templates
  tallied in `state/autopsy_templates.jsonl`. **This is the daily self-improvement loop Murat asked for**:
  the engine does not learn "buy what went up"; it learns which KINDS of reason explained the winners and
  which were visible beforehand, and tomorrow's candidate report is read beside yesterday's autopsy.
- [x] Equity risk semantics: `max_loss` for shares is a **stress-loss charge** (stop + measured p95 overnight
  gap, raised to the implied move into an event), theoretical loss recorded, shorts flagged UNBOUNDED.
- [x] Psychohistory v0.1: evidence ids + origin roots + independence by root; per-scenario checkpoints with
  due dates (`checkpoints_due`); causal-edge ids persisted in `state/causal_graph.jsonl`; edge SHAPE.
- [ ] Causal-thesis concentration in admission (event node exists; sector/factor/theme nodes do not yet).
- [ ] Opportunity Replacement: every mega-cap candidate challenged by ten causal alternatives + cash.
- [ ] Lanes: BIOTECH_CATALYST (benchmark XBI), CONTRARIAN_BOTTLENECK (target < price AND physical signal up),
  REVISION_INFLECTION (Finnhub recommendation trends as evidence only — prior Spearman 0.017).
- [ ] Trade Pulse v0 (US Census HS-level, quantity vs value vs partner), EIA hourly demand, NY Fed GSCPI.
- [ ] RED_TEAM_CAUSAL (falsifier agent), reverse propagation, counterfactual worlds — after resolved records exist.

## 5c. Evening 26 Aug — the three reviews' P0-P10, and what they changed

| item | state | receipt |
|---|---|---|
| P0 freeze | held; one confirmed defect fixed (a benchmark-relative, log-return centre in an unhedged short) | `post_event_drift.py` |
| P1 horizon curve 1..21 | done — DOWN drift peaks at 5 sessions; UP trail-behind grows to 21 | `state/pead_adversarial.json` |
| P2 40 checks | done for what the data carries; **the lane closed** (raw simple +0.04%/+0.00%) | `docs/FINDING_2026-08-26_PEAD_ADVERSARIAL.md` |
| P3 selection oracle | done — no rank edge; picks are a 72%-vol screen; SHAP NOT run (no PIT panel) | `scripts/selection_oracle.py` |
| P4 state-change score | built, shadow, not scored on live names (needs XBRL runway/dilution) | `alpha/state_change.py` |
| P5 loser triage | built, ticker-blind; HUBS falsification passes; refuses without balance-sheet facts | `state/state_change.jsonl` |
| P6 bio residual | done — XBI beta 1.4-2.0, negative residuals, corr 0.07 | `state/bio_residual_2026-08-26.json` |
| P7 six expressions | shares variants measured (entry, horizon, stop, hedge, cost); option expressions argued by agent 4, NOT backtested on option bars | `docs/agents_2026-08-26/agent4_volatility_trader.md` |
| P8 shadow records | DKS live, HOV/OSIS/BJ post-window 21-session | `state/psychohistory.jsonl` |
| P9 Aug-27 prereg | IREN/AFRM/S/RBRK/ESTC baselines frozen + vol agent's calls | `state/event_grade/` |
| P10 agent round | six briefs, each with a strategy and an attack | `docs/agents_2026-08-26/` |

**Standing rule from the day:** every drift/reversal number is printed RAW beside its excess line, in the
trade's compounding convention, and the row says which one the trade earns. The whole-market lane is now a
PAIR to build (short loser / long IWM), not a short to run.

**Queue after the pair:** BROKEN_NARRATIVE (agent 2) and DEPARTURE PRINT (agent 1) re-graded raw-simple with
the battery; ADR overnight residual (agent 10, no LLM, 40 gradeable rows/week); common-shock admission test
(agent 9); XBRL companyfacts collector (runway, shares outstanding) — the input three shadow tools refused on.

## 6. Back into Aegis Finance

Three things port directly, in this order, after the competition:

1. **`alpha/engine/equity.py` + `alpha/admission.py`** → the arena. Shares as a bounded structure with a declared stop+gap; the prospective post-trade admission check (free headroom for tomorrow, per-name cap, theta burn, delta stress). The arena's books have never had the second.
2. **Psychohistory records** → `backend/data/optimus/` as a new gradeable output beside IIF-1, with `session_briefing` surfacing unresolved records. The Brier-per-template table is the first "which kinds of reasoning is Aegis good at" measurement.
3. **Every Aegis decision as one of `BUY / SHORT / HOLD / EXIT / CASH / INSUFFICIENT_EDGE`** with a counterfactual row — the competition ledger already does this (`action` + `CASH:` refusals + shadow rows); the arena should adopt the vocabulary.

4. **A HOLD lane for the real book.** Murat's stated aim for Aegis proper is to pick winners and hold them
   mid-to-long term, selling at the right time. The competition engine cannot express that (5 sessions).
   Aegis can: the farm already replays holding periods over 32 years; `pead_wide`'s 10/21-session horizons
   are the first measurement of whether an event-driven entry should be HELD; the daily autopsy's
   "knowable-before" tally says which precursors are worth waiting for. The sell rule is the research
   question, and it must be pre-registered as one (thesis invalidation / checkpoint failure / target),
   never "it went up a lot".

Then Murat's brokerage account, attended, under `CAPITAL_CANDIDATE` — nothing here relaxes that.
