# AEGIS NORTH STAR

Status: CANONICAL. This document records strategic intent. Change it only when the project goal itself changes.

## Mission

Build an autonomous or human-supervised investment-intelligence system that can discover asymmetric opportunities before consensus, explain the mechanism, estimate timing/magnitude/uncertainty, choose the best tradable expression, manage the position, and grade its own reasoning afterward.

AEGIS should search broadly enough to find an under-covered future winner before it becomes an obvious mega-cap headline. It should be able to discover a future MU/MRVL/NVDA through upstream evidence such as demand, shortages, policy, supplier revenue, capex, customs, scientific/regulatory events, contracts, hiring, pricing power, ownership/flow and cross-country lead indicators — not because the ticker was famous enough to dominate news volume.

The project has two money-making horizons that share an intelligence layer but must be evaluated separately:

- SHORT: intraday through roughly 1–20 sessions — catalysts, reactions, continuation/reversal, volatility, options and event-driven dislocations.
- LONG: months through years — secular bottlenecks, structural demand, policy/capex cycles, technological adoption, company quality and thesis invalidation. Long-horizon winners require HOLD and EXIT logic, not a five-session contest rule.

## The central reasoning chain

World first, ticker later:

`OBSERVATION -> EVENT/STATE CHANGE -> ECONOMIC SHOCK -> NEED/BOTTLENECK -> EXPOSURE -> VALUE CAPTURE/LOSS -> FUNDAMENTAL CHANGE -> EXPECTATION GAP -> PRICED-IN STATE -> COMPANY/INSTRUMENT -> POSITION OR ABSTAIN`

This extends the existing PSYCHOHISTORY rule. News-to-ticker shortcuts are allowed only as retrieval hints; they are not sufficient investment reasoning.

## What information counts

The sensory layer is deliberately interdisciplinary. Relevant evidence can come from markets, corporate filings, earnings and guidance, analyst revisions, options surfaces, ownership/insider filings, government budgets and procurement, regulation, FDA/clinical events, patents, product launches, hiring/layoffs, supply chains, customs/trade, commodities, energy, freight, geopolitics, local-language Asian sources, scientific developments, consumer behavior and physical-world capacity/lead-time signals.

Asia is a first-class information session, not an afterthought. China, Hong Kong, Japan, Korea and Taiwan produce policy, corporate, supply-chain and market information many hours before New York opens. AEGIS should consume the evidence in its original language when useful and propagate the implications into US-listed companies before the US premarket decision pack is sealed.

## Small/under-covered companies

Low analyst coverage is an opportunity hypothesis, not a free alpha factor. Sparse coverage can mean slower consensus formation, but also poor liquidity, bad data, manipulation and binary risk. AEGIS must compare companies using coverage-aware and uncertainty-aware normalization rather than raw article counts or raw analyst upside.

Preferred comparison frame:

`opportunity = impact x novelty x (1 - priced_in) x evidence_confidence x capped_information_scarcity x tradability x historical_support`

with explicit penalties for sparse evidence, source dependence, liquidity, execution cost and uncertain causal hops.

Every feature that naturally scales with fame/size should have a within-entity history and/or peer normalization: percentile/z-score versus the company's own history; sector/industry/size/liquidity cohort residual; analyst-coverage-adjusted surprise; news novelty relative to normal attention; and hierarchical shrinkage rather than pretending three estimates equal thirty estimates.

## Conditional, situational alpha

Do not search for one universal rule that must work on every stock. Some invariants are universal — point-in-time data, transaction costs, position limits, provenance, no look-ahead, attribution — but alpha is usually conditional.

The target model is closer to:

`global/regime prior + event-type effect + sector/industry effect + size/liquidity effect + company state + causal exposures + interactions + residual`

A biotech FDA catalyst, a memory shortage, a defense appropriation, a Chinese export restriction and a consumer earnings miss should not be forced through the same response function.

## Role of intuition and LLMs

Human or model intuition is valuable as a hypothesis generator. It is not allowed to erase measurement.

An intuition becomes useful when it compiles into: evidence, causal chain, alternatives, expected direction, expected magnitude, horizon, already-priced estimate, confidence/uncertainty, falsifiers, and the observation that would change the decision. A small exploration sleeve may test genuinely novel hypotheses before there is a large backtest, but the uncertainty and provenance must travel with the position.

LLMs are therefore researchers/compilers/critics, not magical numeric forecasters. Multilingual models should read and structure information that deterministic code cannot cheaply understand. Numeric models and historical evidence estimate calibration, magnitude and conditional probability. Portfolio/execution code decides sizing and instrument under explicit risk constraints.

## Agility without self-deception

AEGIS is adaptive, not frozen. Strategies, models, features and source weights can change when new information or evidence warrants it — including between sessions during a competition. What never changes retroactively is the contract under which an existing decision was made.

Every order and refusal retains its decision timestamp, data vintage, model/version/hash, feature state and thesis. A later improvement creates a new version. It does not rewrite yesterday's rationale. This permits fast iteration while preserving causal attribution.

Do not change a strategy merely because the first 20 minutes are red. First attribute the loss: thesis error, timing, already-priced event, macro override, liquidity/spread, execution, sizing, source error, entity mapping, regime shift or ordinary residual variance. Adapt to evidence, not pain alone.

## Learning target

The system must score predictions, not just trades. For every candidate worth considering — including refused ones — record expected return/move distribution at multiple horizons, causal rationale and falsifier. After the horizon expires, compare forecast to outcome and classify why it succeeded or failed. The learning loop should answer both:

1. Which signals/templates/sources/model families are calibrated in which contexts?
2. Which important winners/losers were never surfaced at all, and what knowable-before evidence could have found them?

This is how the system learns to find new opportunity classes rather than only optimizing the names it already watches.

## Cost principle

Spend expensive tokens where they can change a decision. Bulk collection, parsing, deduplication, embeddings, entity linking, standard event extraction and basic scoring should be deterministic or local/cheap whenever possible. DeepSeek/frontier/panel calls should be reserved for multilingual ambiguity, causal synthesis, adversarial critique and high-value unresolved cases.

A $3 nightly LLM budget should not buy repeated prose summaries of routine earnings calls. It should buy incremental information or reasoning the cheaper pipeline cannot produce.

## Success criteria

AEGIS succeeds only if it improves out-of-sample portfolio outcomes after realistic costs while maintaining an auditable explanation of why. Research quality, refusal quality and elegant architecture are means, not substitutes for returns. Conversely, a lucky P&L path without repeatable evidence is not proof of alpha.

The long-run ambition is institutional-quality research and portfolio intelligence. Claims must remain proportional to evidence: today AEGIS can use institutional methods without pretending it already has an institution's live data, execution infrastructure, team depth or multi-year live track record.
