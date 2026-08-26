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

## 6. Back into Aegis Finance

Three things port directly, in this order, after the competition:

1. **`alpha/engine/equity.py` + `alpha/admission.py`** → the arena. Shares as a bounded structure with a declared stop+gap; the prospective post-trade admission check (free headroom for tomorrow, per-name cap, theta burn, delta stress). The arena's books have never had the second.
2. **Psychohistory records** → `backend/data/optimus/` as a new gradeable output beside IIF-1, with `session_briefing` surfacing unresolved records. The Brier-per-template table is the first "which kinds of reasoning is Aegis good at" measurement.
3. **Every Aegis decision as one of `BUY / SHORT / HOLD / EXIT / CASH / INSUFFICIENT_EDGE`** with a counterfactual row — the competition ledger already does this (`action` + `CASH:` refusals + shadow rows); the arena should adopt the vocabulary.

Then Murat's brokerage account, attended, under `CAPITAL_CANDIDATE` — nothing here relaxes that.
