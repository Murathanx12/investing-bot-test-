# AEGIS SYSTEM ARCHITECTURE

Status: CANONICAL TARGET ARCHITECTURE. Existing modules are reused where they fit; this document distinguishes BUILT from TARGET rather than pretending the whole graph already exists.

## 1. The architecture in one line

`GLOBAL EVENT MESH -> PIT EVENT STORE -> ENTITY/CAUSAL GRAPH -> OPPORTUNITY GENERATION -> CONDITIONAL VERIFICATION -> FORECAST/EXPRESSION -> PORTFOLIO/RISK -> EXECUTION -> PREDICTION LEDGER -> AUTOPSY/CALIBRATION -> MEMORY`

The current system is strongest from verification onward. The main missing capability is a high-recall, world-first sensory/generation layer that can continuously discover facts and companies outside the current event/theme lists.

## 2. Plane A — Global Event Mesh

Purpose: observe a broad world cheaply and continuously before asking an expensive model what matters.

TARGET source families:

- Corporate: exchange/company IR filings, SEC filings and ownership/insider disclosures, earnings/guidance, investor presentations, financing, M&A, product launches, layoffs/hiring, patents.
- Market: consolidated prices/volume, corporate actions, options surfaces/term structure/skew, borrow/short context when available, ETF/factor/sector moves, futures/rates/FX/commodities.
- Government/policy: budgets, appropriations, procurement/awards, trade/export controls, sanctions, industrial policy, regulatory notices, energy/defense/technology programs.
- Health/science: FDA/regulatory decisions, clinical-trial milestones/readouts, scientific publications and company disclosures.
- Physical economy: customs/trade by product and country, freight, power demand, capacity, utilization, lead times, inventories, commodity prices, supplier/customer monthly data.
- Global/local-language: China/Hong Kong/Japan/Korea/Taiwan official and reputable local sources plus major international reporting. Preserve original-language text and translated/structured claims separately.
- Attention/narrative: high-quality news, analyst revisions, social/search attention where lawful and useful. Attention is evidence about expectations, not truth.

BUILT pieces already include Alpaca/Benzinga news, GDELT attempts, `alpha/sources/registry.py`, the broad listed-market universe, event calendars, current market/filing/data integrations and the first `premarket_digest`. TARGET is much broader than its current ~141-name input.

Ingestion sequence should be cheap-first: fetch -> canonicalize timestamp -> deduplicate -> entity-link -> source/independence tag -> event classify -> novelty score -> store. LLM use comes after this filter, not before it.

## 3. Plane B — Point-in-time Event Store

Every raw observation is append-only and carries at minimum:

`observed_at, published_at, effective_period, source, source_type, source_url/id, language, entity_ids, event_type, raw_hash, independence_group, reliability, revision_policy, PIT_available, parser_version`

Revisions append a new observation rather than overwriting history. Historical simulation uses only observations that existed by the simulated decision timestamp.

The data-source registry remains authoritative about publication lag, reliability, independence, license/cost and parser health.

## 4. Plane C — Entity and Causal Graph

Node classes: company, security, product, technology, person, fund/institution, government/agency, country/region, commodity, facility, supplier/customer, regulation/program, event and macro variable.

Edge classes include supplier/customer, competitor/substitute, ownership, financing, regulatory exposure, subsidy/procurement, geography, commodity dependency, technology dependency, capacity/bottleneck, employment, management and index/factor exposure.

A graph edge is not automatically causal truth. It carries provenance, direction if known, lag/horizon, confidence, temporal validity and evidence roots. Graph hypotheses can be contradicted and retired.

Existing PSYCHOHISTORY templates seed the causal compiler: bottleneck-rent migration, capacity substitution, pull-forward/cliff, cost pass-through, capex echo, geopolitical substitution, infrastructure shadow demand, reflexive feedback, cross-country lead indicator and contradiction trading.

## 5. Plane D — Opportunity Generator

This plane answers: "What might matter before consensus, including names nobody asked for?"

It has several generators, not one stock picker:

1. Event generator — scheduled/unscheduled company catalysts.
2. Causal propagation generator — a world event walks the graph to beneficiaries/losers at multiple hops.
3. Needs/bottleneck generator — asks what the world will need and where pricing power/value capture sits.
4. Policy/capital generator — budget/appropriation/procurement/regulation -> industries -> exposed companies. Distinguish proposal, authorization, appropriation, award and actual spending because markets can react at different stages.
5. Flow/positioning generator — ownership revisions, insiders, option-price-of-risk, factor/ETF/fund flow context. Never pretend option skew reveals a named hedge fund.
6. Under-coverage generator — unusually important/novel evidence in names with sparse normal attention.
7. Contradiction generator — management/analyst narrative conflicts with physical/filing/market observations.
8. Cross-country lead generator — Asia/supplier/customs/policy observations that precede US disclosure or reaction.
9. Counterfactual replacement generator — every obvious mega-cap idea must compete against causal alternatives and cash.

The generator may use LLMs aggressively for hypotheses because generation has low authority. Promotion requires the verification layers below.

## 6. Plane E — Coverage Normalizer and Opportunity Ranker

Raw news count, analyst count, market cap and model familiarity cannot be compared directly.

For each candidate calculate where possible:

- self-history novelty percentile/z-score;
- sector/industry/size/liquidity residual;
- normal attention/coverage density and surprise relative to it;
- analyst-count/estimate-dispersion-aware uncertainty;
- event source independence;
- liquidity/execution penalty;
- priced-in evidence from price/options/attention;
- causal-hop uncertainty and contradiction count.

Use hierarchical shrinkage: sparse names receive wider uncertainty, not fake precision. Information scarcity may boost opportunity only up to a cap; it never cancels liquidity or evidence risk.

TARGET rank concept:

`Impact x Novelty x (1-PricedIn) x EvidenceConfidence x ScarcityBoost x Exposure x ValueCapture x Timing x HistoricalSupport x Tradability`

This is a feature decomposition to test, not a hand-tuned forever-formula.

## 7. Plane F — Conditional Research/Verification

Universal methodology, conditional alpha.

A candidate is routed by event/context into the relevant evaluator rather than one universal stock rule. Examples: earnings/reaction, biotech catalyst, regulation/procurement, bottleneck/physical signal, ownership/insider, volatility/surface, non-print shock, secular state change.

Historical testing uses PIT data, time splits, realistic next-tradable execution, transaction costs, liquidity, sector/factor benchmarks, regime/size buckets and stability checks. Report effect distributions and failure cells, not only average t-statistics.

Novel hypotheses with little history may enter a small labelled exploration/shadow sleeve, but their uncertainty is explicit. Lack of 30 years of identical events is not equivalent to evidence of zero edge.

## 8. Plane G — Model Stack

Do not build one giant neural network and call it the brain.

Recommended roles:

- Deterministic/local code: collection, parsing, timestamping, feature calculations, dedupe, standard event rules, backtests.
- Local embeddings/small model/Optimus: retrieval, entity linking, clustering, routing, compression, routine extraction, memory/context construction.
- DeepSeek: multilingual Asian-source extraction and high-value causal synthesis/critique.
- Other HF/Featherless models: independent panel diversity on shortlisted ambiguous cases.
- Fable/overseer role: adversarial research review, experiment design, contradiction/attribution checks; no unilateral broker authority.
- Numeric baseline models: logistic/linear/hierarchical Bayes, CatBoost/LightGBM or similar time-aware rankers first.
- TARGET neural models: heterogeneous temporal graph embeddings/GNN or graph-transformer plus sequence features, multi-task outputs for direction, magnitude, realized vol and horizon. Shadow-only until they beat simpler baselines after costs out of sample.

The LLM produces structured evidence and hypotheses. Numeric models estimate calibrated probabilities/distributions. The portfolio layer chooses exposure. Execution remains deterministic and auditable.

## 9. Plane H — Forecast and Instrument Expression

Every promoted candidate should produce a distribution, not merely BUY/SELL:

`direction probabilities, expected magnitude, uncertainty/quantiles, horizons, priced-in estimate, catalyst/timing, falsifier, regime, causal chain, supporting/opposing evidence`

Then expression compares shares, defined-risk options/spreads, hedged pair, or cash using executable market data, expected value, median/path risk, liquidity and thesis horizon. Delayed/indicative options data cannot support latency-sensitive reaction trading.

## 10. Plane I — Portfolio and Risk

Portfolio construction answers a different question than candidate selection. It must prevent the book from concentrating because many candidates are manifestations of one causal thesis, factor, commodity, theme or macro shock.

Track per-name, per-causal-thesis, sector, factor, liquidity and gross/net exposure. Preserve headroom for new information. Risk should scale with evidence quality and uncertainty, not with narrative excitement.

A human-prior/shadow-only idea must not acquire more aggregate authority merely because many correlated tickers express the same unvalidated story.

## 11. Plane J — Prediction Ledger

Log every material candidate and refusal, not just fills. Minimum schema:

`decision_id, observed_at, sources/evidence_ids, entities, event_type, model/provider/version/hash, feature_version, direction_distribution, magnitude_distribution, horizons, p_already_priced, confidence/uncertainty, causal_chain, alternatives, falsifier, decision, instrument, size/risk, reason_for_refusal`

Resolution adds actual 30m/close/1d/5d/20d outcomes where relevant, trade P&L and decomposition, plus a failure class such as thesis_wrong, timing_wrong, already_priced, macro_override, liquidity/spread, execution, sizing, source_false, entity_mapping, regime_mismatch or residual_noise.

Original prediction rows are immutable; resolutions append.

## 12. Plane K — Autopsy and Learning

Current `scripts/daily_autopsy.py` is the seed. TARGET autopsy has two sides:

A. Prediction calibration: which generated forecasts, sources, templates and model families were right, wrong or overconfident by context?
B. Opportunity recall: among the day's/week's major winners and losers, what was knowable beforehand, did AEGIS surface it, and if not, which sensor/edge/generator was missing?

This updates source reliability, template calibration, routing priors and the experiment queue. It does not automatically retrain or change live weights from one day.

## 13. Optimus context/memory boundary

Optimus is the persistent executive/context layer, not the broker. Canonical Markdown remains human-auditable truth; embeddings/indexes are derived retrieval structures. The context builder should ingest canonical docs first, then current verified machine state, then only task-relevant historical findings.

Large handoffs are archives, not default prompt stuffing. A session should retrieve a relevant old finding when needed instead of injecting 100 KB of stale instructions every time.
