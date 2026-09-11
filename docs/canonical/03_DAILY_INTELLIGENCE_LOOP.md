# AEGIS DAILY INTELLIGENCE LOOP

Status: CANONICAL OPERATING TARGET. This describes the information/research cycle; live execution modules continue to enforce their own safety contracts.

The purpose of premarket is not to publish a list of famous earnings names. It is to seal a gradeable view of what changed in the world before New York trades, surface both obvious and under-covered beneficiaries/losers, and make the later autopsy able to say what AEGIS knew, predicted, missed and learned.

## 1. Continuous collection — 24 hours

Collectors run cheaply throughout the day and append observations to the PIT event store. They do not call an expensive LLM for every article/transcript.

For every new observation:

`timestamp -> source/independence -> language -> entity link -> event class -> dedupe -> novelty -> potential exposure graph -> queue priority`

Routine filings/news can be parsed by code/local models. A full earnings call is first converted to structured changes — guidance, margins, demand, capex, capacity, product/customer statements, contradictions versus prior quarter/consensus — before any expensive causal review.

## 2. Asia-first window

From the prior US close through the Asian session, AEGIS explicitly scans China/Hong Kong/Japan/Korea/Taiwan plus relevant commodities, FX, rates and supply-chain information.

The output is not merely "Asia risk-on/risk-off." It is a set of structured state changes and causal paths:

`Asian observation -> affected need/input/industry -> US/global exposures -> expected lag/horizon -> counterevidence`

Examples of the intended reasoning shape:

- memory contract price/exports or supplier revenue -> HBM/memory scarcity -> accelerator/server economics -> exposed producers/customers;
- China export control/industrial policy -> strategic material availability -> substitute supplier/country -> US-listed miner/refiner/manufacturer;
- Japan/Korea/Taiwan supplier/capacity data -> US customer's future margins/revenue before that customer reports;
- government robotics/automation policy -> component demand -> actuator/sensor/vision/power suppliers -> revenue timing;
- defense appropriation/procurement -> prime contractor -> constrained subsystem/material supplier -> value capture.

DeepSeek is preferred when original Chinese-language reasoning materially matters. Preserve the original claim/source and the model's English extraction separately.

## 3. Europe/pre-US window

Continue ingestion as Europe opens: policy, commodities, rates, industrial/company news and cross-market reactions. Update causal paths rather than replacing the Asian snapshot.

A new European/US observation can confirm, contradict or make an Asian precursor already priced. Source independence matters: ten rewrites of one issuer release remain one root.

## 4. Broad opportunity generation

Before expensive council calls, generators operate across the full eligible US universe rather than a hand-picked ticker list.

Candidate families include:

- direct catalyst names;
- graph-propagated second/third-order beneficiaries/losers;
- under-covered names whose evidence novelty is high relative to normal attention;
- bottleneck/value-capture names;
- policy/procurement exposures;
- ownership/insider/positioning changes;
- volatility/options dislocations;
- contradictions between price/narrative and physical/fundamental evidence;
- control/cash alternatives.

Every famous idea must undergo Opportunity Replacement: "If this mechanism is true, what less-obvious listed companies have higher exposure/torque, lower priced-in state or better risk/reward?"

## 5. Coverage normalization

Do not rank on headline volume. For each candidate compare the new information to that company's normal information environment and to peers.

Inputs should include self-history novelty, sector/size/liquidity cohort residuals, normal attention density, analyst coverage/dispersion where PIT data exists, source independence, liquidity, causal-hop confidence and already-priced signals.

Sparse coverage increases uncertainty. It can create opportunity only when independent evidence/causal exposure compensates for that uncertainty.

## 6. Causal compiler and red team

Only the top novel/high-impact or ambiguous candidates are escalated to expensive models.

Compiler output:

`event -> mechanism -> exposures -> expected fundamental effect -> expectation gap -> price/vol effect -> horizons -> scenarios -> p_already_priced -> falsifiers -> alternatives`

A separate red-team pass attacks the weakest causal hop, finds a competing explanation, asks what evidence would reverse the view, and checks whether the move may already have occurred elsewhere.

The models do not place orders.

## 7. Historical/conditional evidence lookup

For each shortlisted hypothesis, retrieve the most relevant historical evidence by event type and context rather than forcing a universal rule.

Return:

- comparable event definition and PIT quality;
- sample size and context cells;
- return/magnitude distribution and path;
- benchmark/factor residual;
- transaction-cost/executable result;
- stability by year/regime/size/liquidity;
- known negative results/confounds;
- whether evidence is strong, weak, absent or contradictory.

If no good analogue exists, say so. The candidate can remain a labelled exploration hypothesis with reduced authority rather than inventing a backtest.

## 8. Seal the PRE-OPEN PREDICTION BOOK

Before the chosen pre-open cutoff, write an immutable prediction row for every high-priority candidate and important refusal.

Minimum fields:

- evidence timestamp/root IDs and languages;
- company/security and event type;
- causal chain and alternative explanation;
- direction probability and magnitude distribution;
- horizons: intraday/close/1d/5d/20d as applicable;
- p_already_priced and uncertainty;
- historical-support summary;
- expected catalyst/checkpoint and falsifier;
- preferred instrument/why, or CASH/INSUFFICIENT_EDGE;
- model/provider/version/hash and feature version.

The seal answers the later question: "What did we actually believe before price revealed the answer?"

## 9. Portfolio decision pack

The portfolio layer considers the user's/current paper positions alongside new opportunities:

`BUY / ADD / HOLD / REDUCE / EXIT / SHORT / HEDGE / CASH / INSUFFICIENT_EDGE`

Each action includes expected incremental return/risk, thesis concentration and what existing position would be displaced. A new idea must compete for capital, not merely pass a standalone gate.

Long-horizon holdings use thesis/checkpoint logic. Short-horizon catalysts use time/event exits. Do not use the contest's five-session mechanics as the permanent definition of investing.

## 10. Intraday event loop

During the US session, AEGIS does not re-read everything continuously with an LLM. Event triggers update the relevant candidates when a new filing/headline/price dislocation/macro release/falsifier arrives.

A material update creates a new prediction version linked to the old one. Existing positions retain the entry contract. The system may add/reduce/exit when the new evidence changes expected value enough to justify costs.

Intraday options decisions require suitable quote freshness/liquidity. If the live feed is delayed/indicative, do not pretend it supports reactive gamma trading.

## 11. Close and after-close autopsy

After each close:

A. Book attribution: P&L by lane, thesis, factor/sector, instrument, slippage/spread, sizing and macro exposure.

B. Prediction grading: Brier/calibration/direction/magnitude/path error at horizons that have resolved; score traded and untraded predictions.

C. Opportunity recall: identify the day's largest idiosyncratic winners/losers across the broad universe. For each, determine the strongest evidence that existed before the move, whether AEGIS saw it, and where the chain failed if not.

D. Failure classification: thesis_wrong, timing_wrong, already_priced, macro_override, liquidity/spread, execution, sizing, source_false/late, entity_mapping, regime_mismatch, or residual_noise.

E. Learning proposal: propose source weight/routing/template/feature/strategy changes, with evidence. Do not automatically promote changes from one observation.

## 12. Overnight research queue

The autopsy creates ranked research questions, not a random hypothesis farm. Examples:

- "Why did these three obscure suppliers move before/after the same policy event?"
- "Does this clinical-event class continue after the day-0 reaction versus XBI?"
- "Does an Asian customs/supplier surprise lead the US downstream names by 1–20 sessions?"
- "Was the theme-basket loss a thesis failure, opening-spread/execution failure, or correlated macro shock?"

Backtest the highest expected-information-gain questions. Cheap/local tools do the bulk work; expensive panels review decisions that might change live authority.

## 13. Morning output for a human

The human-facing premarket report should be concise even though the ingestion is broad. It should contain:

1. world state changes and Asia->West causal implications;
2. the highest-ranked under-covered opportunities and why they beat obvious alternatives;
3. important holdings: buy/add/hold/reduce/exit plus catalyst/falsifier;
4. today's scheduled event map (earnings, regulatory/clinical, macro, policy, company events);
5. option/flow/positioning changes where reliable;
6. what is likely already priced;
7. explicit predictions that will be graded after the close;
8. data-source failures/blind spots.

Broad sensing should create a short high-information decision surface, not a 500-ticker wall of prose.
