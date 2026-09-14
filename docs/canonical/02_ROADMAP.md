# AEGIS ACTIVE ROADMAP

Status: CANONICAL ACTIVE ROADMAP. Update this file in place. Do not create another strategic `ROADMAP_YYYY-MM-DD_*.md`; dated findings and runbooks may continue as evidence/operations.

Last strategic reset: 2026-08-28, first hackathon session.

## Current diagnosis

AEGIS has built unusually strong downstream measurement, refusal, provenance, execution-ledger and falsification machinery. It has also built pieces of the intended upstream intelligence system — HIGH_DISPERSION_US, PSYCHOHISTORY, needs graph, candidate scan, daily autopsy, source registry, timezone lead work, premarket digest — but those pieces never became one continuous world-first pipeline.

The result is a coordination failure: good ideas exist in dated documents, while live opportunity generation still depends too much on preselected event/theme universes and famous names. The next phase is not "add more LLM agents." It is to join the sensors, causal graph, opportunity generation, historical evaluator and prediction ledger into one daily learning system.

## P0 — TODAY: preserve day-one evidence and diagnose the live book

No panic rewrite from the first minutes of P&L. The market opened immediately before a major Fed communication. Preserve all day-one receipts.

Required by the close:

- Capture the premarket digest/council state actually available before each entry.
- Capture every fill/refusal, live mark and broker/execution anomaly.
- Attribute hack1–hack6 P&L by lane, not account only: post_event_drift, theme_basket, council_vector, beta/options, execution/slippage.
- Specifically audit `theme_basket` in hack3/hack6: its causal prior is not validated alpha, yet it can create large aggregate gross exposure through many correlated names. Measure notional, stress loss, causal-theme concentration and opening-spread contribution before deciding how to change it.
- Run `daily_autopsy` after the close across the broad universe; compare actual top/bottom movers with the morning digest/candidate set and record misses.
- Resolve/grade the relevant PSYCHOHISTORY/event records.

Adaptation rule: operational defects can be fixed immediately. Strategy/model changes are allowed when evidence or a newly identified mechanism warrants them, preferably between sessions. Any position already entered remains attached to its original version/hash. Never rewrite the old rationale.

## P1 — THIS WEEKEND: Global Event Mesh v0

Goal: Monday's opportunity set must start from the world, not from ~141 already-known tickers.

Build a high-recall event pipeline over the full tradable US universe plus global upstream entities. The first version does not need every source on Earth; it needs the correct abstraction and enough independent source families to prove the loop.

Deliverables:

- `EventObservation` schema and append-only PIT store with source/independence/language/entity/event timestamps.
- Deduplication and entity resolution so one press release repeated by ten outlets remains one evidence root.
- Event taxonomy covering at least corporate results/guidance, financing/M&A, regulatory/clinical, government/policy/procurement, product/technology, supply-chain/commodity/capacity, ownership/insider/flow, and macro/geopolitical.
- Expand the source registry with publication lag, PIT quality, parser health and cost.
- Broad cheap scan first; LLM only after novelty/impact filtering.
- Asia session as a distinct first-class ingest window with original-language retention and an East->West propagation stage.
- Causal candidate generation that can emit a US company even when that company was never named in the initiating article.
- Opportunity Replacement: each famous candidate competes with causal alternatives, under-covered exposures and cash.

Do not solve this by asking DeepSeek to "read the whole internet." That is expensive, non-reproducible and biased toward what search already ranks. Code gathers and structures broadly; models reason deeply on the compressed frontier.

## P2 — THIS WEEKEND / NEXT SESSIONS: Prediction Ledger v2

Unify premarket bets, psychohistory, candidates, orders and refusals around one immutable prediction object.

Each serious opportunity gets probability/magnitude distributions at relevant horizons (for example 30m, close, 1d, 5d, 20d), priced-in estimate, evidence roots, causal path, falsifier, uncertainty, model/version/hash and decision. Resolve all predictions whether traded or not.

This turns "we thought X might happen" into a gradeable dataset and lets the engine learn from missed trades/refusals as well as P&L.

Postmortem classes should distinguish at least: thesis wrong; right thesis/wrong timing; already priced; macro override; liquidity/spread; execution; sizing; source false/late; entity/graph mapping; regime mismatch; and irreducible residual/noise.

## P3 — Coverage-normalized discovery of under-followed names

Build the anti-streetlight layer the user has repeatedly requested.

For the full listed universe, maintain attention/coverage context: normal article rate, analyst-count/dispersion where PIT data exists, liquidity/size, filing/event frequency, option availability, sector/industry and company self-history.

Candidate scoring should use relative novelty rather than fame. A small company with three independent pieces of new evidence can outrank NVDA with 500 repetitive articles, while sparse evidence also widens uncertainty.

Required tests:

- ranker cannot see ticker identity when identity is unnecessary;
- fame/coverage ablation on generative candidate discovery, not only packet scoring;
- recall test: how many of the next session/week's largest idiosyncratic movers were surfaced before the move?
- liquidity/cost-adjusted return by coverage bucket;
- false-positive rate and data-quality failures in micro/small caps.

Do not encode "few analysts = buy." The hypothesis is that sparse attention may create slower consensus; it must earn its weight out of sample.

## P4 — Three initial world-to-market research lanes

Instead of testing random technical patterns, choose event classes directly tied to the North Star and with reconstructable historical timestamps.

### A. BIOTECH_CATALYST

Scheduled regulatory/clinical events -> evidence state -> options/price expectations -> reaction/continuation. Benchmark biotech against XBI/appropriate industry factors rather than SPY. Build a reliable event-history dataset before claiming FDA-calendar alpha.

### B. CONTRARIAN_BOTTLENECK / NEEDS GRAPH

Physical-economy improvement or scarcity -> pricing power/value capture -> company exposure -> expectation disagreement. Examples include memory/HBM, power/transformers, cooling, copper/rare earths, batteries, robotics components and defense capacity. Direct capacity/backlog/lead-time evidence outranks narrative proxies when available.

### C. POLICY/CAPITAL PROPAGATION

Government proposal -> authorization -> appropriation -> award/procurement -> supplier revenue/capacity. Treat stages separately and propagate through contractor/supplier/substitute chains. Defense, energy/grid, semiconductor industrial policy and strategic materials are natural first domains.

Each lane gets PIT reconstruction, simple baseline, conditional cells, costed execution and a prediction-ledger shadow period before large live authority.

## P5 — Backtest factory: more testing, less indiscriminate hypothesis mining

The answer to "we are not backtesting enough" is a reusable event-replay factory, not thousands of unstructured indicators.

Build a common interface:

`event timestamp + information state -> candidate features -> decision at next executable time -> path outcomes -> benchmark/residual -> costed instrument return`

Every lane should automatically produce size/liquidity/sector/regime/year/horizon/entry-delay cells, stability charts, false-discovery bookkeeping and a comparison with trivial baselines/cash.

Backtest both selection and sizing. A candidate selector can be good while portfolio construction destroys its edge; Murat's historical list already showed this separation.

Use walk-forward/time-split validation and preserve a final untouched period where possible. Do not throw away conditional mechanisms because the pooled average is weak; inspect whether a pre-declared, economically coherent context changes the response. Conversely, do not invent a context after seeing every failure.

## P6 — Numeric learning stack before the big neural network

The neural network remains a goal, but it needs a clean target dataset first.

Stage 1: simple calibrated baselines on the prediction/event panel — logistic/linear/hierarchical models plus a tree ranker such as CatBoost/LightGBM. These establish what structured features can predict and expose leakage quickly.

Stage 2: mixture-of-experts / hierarchical conditional model. Route or gate by event type, sector, regime, size/liquidity and horizon instead of forcing one coefficient across all stocks.

Stage 3: temporal heterogeneous graph model. Inputs: entity graph, time-stamped events, market/financial state and learned text/event embeddings. Multi-task outputs: direction probabilities, magnitude distribution, realized volatility and horizon. Candidate architectures may include temporal GNN/graph transformer plus tabular/sequence towers.

Stage 4: portfolio policy only after forecast calibration. Do not train end-to-end "buy/sell" first; it is too easy for a network to learn costs, beta, leakage or unstable reward quirks.

Promotion rule: neural model stays SHADOW until it beats the strongest simple baseline out of sample after transaction costs and remains calibrated by relevant context cells.

## P7 — Flow, ownership and "follow the money" layer

Build this as evidence about positioning/price of risk, not omniscient hedge-fund tracking.

Combine PIT ownership/insider/regulatory filings, analyst revision vintages where licensed, options surface/skew/term structure, ETF/factor flows, short/borrow context where available and public fund/regulatory disclosures. The causal question is "what exposure or expectation is changing?" not "which whale secretly knows the future?"

For options, distinguish direction, future realized volatility and actual structure P&L. Backtest executable bid/ask paths. Control for borrow, earnings, liquidity and market/sector skew.

## P8 — Optimus/Fable/local-model integration

Optimus becomes the context/retrieval/executive layer over AEGIS research, not a second uncontrolled source of truth.

- Canonical Markdown first; embeddings/SQLite are derived.
- Generate a bounded context pack from `docs/canonical/` + latest verified state + task-relevant findings.
- Local model handles routing, extraction, clustering and compression.
- DeepSeek handles multilingual/high-value causal reasoning.
- Fable/overseer challenges hypotheses, experimental design, causal attribution and proposed promotions.
- Frontier models are escalations, not mandatory bulk processors.
- Every model call identifies which decision/uncertainty it can change and records provider/model/prompt hash/cost.

The existing research-gym idea becomes valuable once the prediction ledger is large enough: replay historical mistakes and score an agent on detecting leakage, confounds, wrong benchmarks, insufficient power and when to abstain.

## P9 — Context/document hygiene

This canonical set is the strategic source of truth. Historical roadmaps are archived evidence and should remain immutable when they contain claims/receipts.

Next implementation step is a deterministic context-pack builder driven by `docs/canonical/CONTEXT_MANIFEST.yaml`. It should emit a concise `state/context/AEGIS_CONTEXT_PACK.md` for Optimus/Fable/Claude-style sessions and include hashes/timestamps so a stale pack is obvious.

Future session handoffs contain only: verified live state, changes since last session, unresolved decisions, failures, and links to evidence. They must not duplicate the whole strategy.

## Completion definition

The roadmap has worked when a daily cycle can answer, with receipts:

"What changed in the world since the last US close; what did Asia reveal first; which economic needs/bottlenecks or policy flows changed; which US-listed companies are most exposed including obscure names; what is the market already pricing; what did our conditional historical evidence say; what did we predict at each horizon; what did we buy/hold/sell/refuse and why; what actually happened; and what specific sensor/model/rule should change because of the result?"
