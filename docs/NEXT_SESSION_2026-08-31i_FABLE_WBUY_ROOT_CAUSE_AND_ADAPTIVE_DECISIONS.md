# NEXT SESSION FOR FABLE / OPUS — 2026-08-31 (i)

## Murat's correction

The project must not turn a population-level result into a permanent company-level ban. The WBUY case exposed this.

AEGIS found WBUY through the new adaptive news-first universe before Murat would have found it manually. That is a success. It then could not produce a proper invest/avoid comparison because WBUY was excluded from the tracker/CompanyState by liquidity and upside-band rules. That is a design failure in OBSERVATION and CASE ADJUDICATION, not proof that WBUY is a buy.

Murat's rule: **make a decision, observe the result, update the model. There is no permanently fixed path. Population rules are priors unless they protect data integrity or account survival. Go to the root cause per company/sector/situation.**

Do not manually decide WBUY. Make AEGIS produce the decision card first; then validate the card against source evidence and later outcomes.

---

# 0. REFRAME ALL BANDS / LIMITS INTO FOUR CLASSES

Every current threshold must declare one of:

1. `DATA_INTEGRITY_HARD` — e.g. impossible share-basis target, stale timestamp, corporate-action mismatch. May exclude the corrupted observation.
2. `SURVIVAL_HARD` — gross/account breakers, broker state, max premium risk, opening-range protection. May limit capital.
3. `EXECUTION_FEASIBILITY` — liquidity/spread/participation. May block or reduce LIVE execution but must NOT remove the company from observation/research.
4. `STATISTICAL_PRIOR_SOFT` — e.g. >400% upside band historically bad, coverage bucket, sector band. It changes prior/confidence and triggers deeper adjudication. It must not automatically erase a candidate.

Audit every existing `MIN_DOLLAR_VOLUME`, `UPSIDE_IMPLAUSIBLE_AT`, coverage band and sector constraint against this taxonomy.

### Specific ruling on `UPSIDE_IMPLAUSIBLE_AT=4.0`

The 11-year result says the raw >400% band is contaminated and bad ON AVERAGE. It does NOT establish that every legitimate >400% opportunity is bad.

Change semantics from:

`upside > 4.0 -> reject name`

to:

`upside > 4.0 -> HIGH_UPSIDE_ANOMALY -> root-cause adjudication required`

Hard reject only when the root cause is a data failure: stale target, wrong share basis, split/reverse-split mismatch, outdated analyst date, currency/unit mismatch, target referring to another security/share class, etc.

If the target is real, recent and correctly adjusted, retain the name and classify WHY the upside is extreme.

---

# 1. BUILD `CASE_ADJUDICATION` / DECISION CARD

For every serious candidate, especially anomaly names, AEGIS must answer in numeric form rather than `I don't know`.

Minimum output per horizon 1d / 5d / 21d / 63d / 126d / 252d where evidence permits:

- `p_up`
- `expected_return`
- `downside_5pct`
- `confidence`
- `evidence_density`
- `already_priced_probability`
- `status`: STRONG_BUY / BUY / WATCH / HOLD / AVOID / DROP, horizon-specific
- `preferred_expression`: shares / defined-risk options / no execution
- `max_execution_authority`: independent from expected upside
- `bull_case`
- `base_case`
- `bear_case`
- `falsifiers`
- `why_this_is_better_or_worse_than_next_best_candidate`

The card must explicitly separate:

### Opportunity
How large can the payoff be if the thesis is right?

### Evidence quality
How much trustworthy information do we actually have?

### Execution feasibility
Can we enter/exit at our intended size without the spread/impact eating the edge?

### Capital authority
How much of the portfolio may this belief control today?

A nano-cap can therefore be:
`expected upside very high / confidence medium-low / execution authority tiny or zero`.
That is much more informative than deleting it.

---

# 2. ROOT-CAUSE DECOMPOSITION OF ANALYST / FAIR-VALUE TARGETS

Never store only `target_price` and `upside`.

For each external target/valuation, store:

- source/provider;
- evidence class: `SELL_SIDE_ANALYST`, `CONSENSUS`, `VENDOR_FAIR_VALUE`, `ALGORITHMIC_FORECAST`, `AEGIS_INTERNAL`;
- analyst/model name when lawful/readable;
- target date and last revision date;
- low/mean/median/high;
- analyst count;
- target dispersion;
- target revision velocity 30/60/90d;
- price at time target was issued;
- split/share-basis/currency adjustment verification;
- explicit assumptions if available: revenue, margin, EPS, cash flow, multiple, terminal growth, dilution/share count;
- catalyst assumptions;
- target horizon;
- source reliability/history once we can backtest it.

Build `target_anomaly_reason` taxonomy:

- `STALE_OR_SHARE_BASIS_ERROR`
- `BINARY_REGULATORY_BIOTECH`
- `DISTRESSED_TURNAROUND`
- `EARLY_STAGE_HIGH_GROWTH`
- `MICRO_NANOCAP_REPRICING`
- `COMMODITY/NAV_SENSITIVITY`
- `CAPITAL_STRUCTURE/DILUTION`
- `MAJOR_CONTRACT/ORDER_INFLECTION`
- `EARNINGS/MARGIN_INFLECTION`
- `MODEL_EXTRAPOLATION`
- `UNKNOWN`

Then backtest the cells separately. This is the direct implementation of Murat's instruction: do not generalize; find the root cause.

---

# 3. WBUY IS THE FIRST EXAM — ENGINE FIRST, VALIDATION SECOND

Do not manually add `BUY WBUY`.

First widen OBSERVATION so WBUY gets a complete state even if live execution remains infeasible.

Populate from:

- all SEC/6-K/20-F/prospectus/capital raises;
- current news cluster;
- analyst/consensus/fair-value sources available lawfully;
- capital structure / shares outstanding / recent issuance;
- institutional ownership where available;
- insider ownership / transactions;
- liquidity/spread/volume migration;
- revenue/bookings/earnings history;
- peer/travel-sector state;
- company-specific catalyst chronology.

The current public facts to force the engine to reconcile include:

- Aug 31: record NATAS bookings ~$4.76m, +42% vs March; bookings are NOT recognized revenue.
- Aug 2026 6-K: settlement of ~$557k payable through issuance of 728,484 shares at $0.765 (85% of Aug 11 close): dilution/capital-structure evidence.
- Mar 2026 6-K: up to $20m equity line of credit: potential future dilution/capital access.
- May 2026 6-K: Nasdaq minimum stockholders-equity deficiency was cured; 2025 stockholders' equity ~$3.29m.
- market cap around only a few million dollars at the Aug 28 close, making small changes in expectations/capital structure capable of huge percentage moves.
- premarket Aug 31 move itself: catalyst was already partially priced by the time Benzinga surfaced the mover.

The engine must answer:

1. Was the Aug 31 event genuinely new or continuation of a known trend?
2. What fraction of bookings plausibly converts to revenue/gross profit/cash?
3. How material is $4.76m relative to annual company economics?
4. How much dilution should be expected from the equity line and recent share settlement?
5. Is the external high price target a real recent sell-side target, a vendor fair-value model, an algorithmic forecast, or a mislabeled market range?
6. Does the target survive current share count and corporate actions?
7. What are the comparable companies/multiples?
8. Is the expected payoff dominated by operating growth, multiple rerating, dilution avoidance, or a low-float/liquidity squeeze?
9. What is the probability the premarket move already consumed the short-horizon edge?
10. At what price would expected return stop compensating for downside/liquidity?
11. What would make AEGIS prefer another candidate to WBUY today?

Seal the decision BEFORE the regular-session outcome and grade it later.

---

# 4. OBSERVATION UNIVERSE MUST BE MUCH WIDER THAN EXECUTION UNIVERSE

The WBUY lesson is decisive.

`OBSERVATION_UNIVERSE`: all practical US-listed equities/ADRs that can be entity-resolved, including nano/illiquid names.

`EXECUTION_UNIVERSE`: subset currently tradeable at a particular account size/instrument under measured spread, depth and participation constraints.

A name below the measured band stays in CompanyState with:

- actual median dollar volume;
- actual quote/spread when observable;
- `execution_cost_unknown` if outside our TAQ-calibrated range;
- `max_participation_estimate`;
- `live_trade_authority=0` until execution can be bounded;
- full opportunity forecast nevertheless.

Do not use `MIN_DOLLAR_VOLUME` to decide what AEGIS is allowed to know exists.

Build an explicit `nano_cap_observation` lane and daily opportunity-recall grade. Ask historically: how many top subsequent winners began below our previous execution floor?

---

# 5. EXTERNAL FORECASTS — BUY/USE AS TEACHERS, NOT ORACLES

AEGIS should use external estimates as FEATURES, competitors and labels to beat.

Store at least three independent valuation families:

1. sell-side consensus / analyst revisions;
2. external systematic fair-value model(s);
3. AEGIS internal sector-appropriate valuation.

The final decision is based on the disagreement and the assumptions underneath them, not a simple average.

### Internal valuation must be sector-aware

Do not force a single DCF everywhere.

- mature profitable: DCF + earnings/multiple + FCF yield;
- high-growth software/AI: revenue/FCF/margin-path + peer multiples + scenario DCF;
- biotech: probability-weighted rNPV by asset/phase + cash/runway/dilution;
- miners/materials: NAV + commodity-price sensitivity + capacity/cost curve;
- banks: book value/ROE/NIM/credit losses;
- travel/consumer: bookings -> recognized revenue -> gross margin -> operating leverage + peers;
- pre-revenue/nano-cap: scenario tree emphasizing dilution, cash runway, unit economics and catalysts.

Every AEGIS fair value is a DISTRIBUTION/scenario range, not one magic target.

---

# 6. SUBSCRIPTIONS / DATA BUY DECISION

### InvestingPro

Useful as a one-month research benchmark ONLY if Murat can lawfully export enough data. Investing.com explicitly says it offers no public API. Pro+ advertises 17 fair-value models and export capabilities, but that is not an automation API.

Therefore:
- do NOT build a scraper pretending consumer Pro is an API;
- if Murat buys one month, first export a 100-name stratified sample and test what fields/history/export limits are actually available;
- ingest exported fields with source/provenance and compare their historical calibration against AEGIS/IBES;
- if useful, do the largest lawful export during the month and archive the derived comparison features permitted by terms.

### WSJ

Useful for human/deep narrative research; poor candidate for core machine acquisition because no consumer public API and licensing/paywall constraints. Do not make daily copy-paste a required production lane.

Use free/global/primary mesh first: SEC/IR, Reuters where accessible, GDELT, Common Crawl/CC-NEWS, GlobeNewswire/BusinessWire/PRNewswire, government/regulatory sources, local-language sources.

### Better spend if purchasing one small alternative-data service

Quiver is relevant to Murat's new asks. Current pricing: $30/mo Hobbyist covers Congress trades/holdings, government contracts/lobbying/donors, dark-pool, politician profiles; institutional/13F/insider/top-shareholder API access is in $75/mo Trader. We already have WRDS 13F and SEC Form 4, so do not buy Trader merely for data we can derive. A one-month Hobbyist probe may be worth it for convenience/coverage of politics/contracts/dark-pool, but first compare with free official sources.

Koyfin Plus (~$39/mo annual-billing equivalent shown in current pricing) exposes global analyst price targets and consensus estimates and may be a cleaner human benchmark for estimates than scraping Investing.com. Again: verify export/API rights before automation.

Do not add a subscription without a predeclared question: `what unique field or latency does this buy that our free stack cannot?`

---

# 7. HOLDERS, HEDGE FUNDS, INSIDERS, POLITICIANS — BUILD FOUR DIFFERENT CLOCKS

Do not call all of these `smart money`.

## 7.1 Institutions / hedge funds — 13F

Quarterly and delayed. Not live. Track:

- institutional ownership % of shares outstanding/float;
- number of reporting managers;
- top 1/5/10 holder concentration;
- Herfindahl/crowding;
- QoQ shares/value change;
- largest-holder change;
- new positions / exits;
- manager quality/history conditional on sector/style;
- `known_by` = actual filing availability or conservative statutory deadline if the real filing timestamp is unavailable.

The existing finding that institutional selling had strong subsequent returns is a candidate mechanism, not a universal rule. Reproduce across eras/size/liquidity/sectors and test whether it represents forced selling, neglected value, distress, or another confound.

## 7.2 Corporate insiders — SEC Form 4

This is much closer to live and should be higher priority than 13F for short-horizon information.

Track purchase/sale/option exercise separately; open-market purchase is not the same as compensation exercise. Normalize transaction value by insider holdings, compensation and market cap.

## 7.3 Politicians — STOCK Act disclosures

Track immediately when PUBLICLY FILED, but never call them live trades: public disclosure can lag the actual transaction by weeks (up to ~45 days in current public datasets).

Keep `transaction_date`, `filed_date`, `first_seen_at` separate.

Build politician-specific historical skill after fees/lag rather than `Pelosi bought -> buy`.

Features:
- politician identity;
- committee exposure/relevance;
- party/chamber only as descriptive fields, not causal assumptions;
- trade-size range normalized by disclosed portfolio/net-worth estimate when lawful;
- sector expertise/history;
- reporting lag;
- subsequent excess return from FIRST PUBLIC OBSERVABILITY, not transaction date;
- matched ticker/date controls.

The prior Congress null stays a corpse/control; new conditional hypotheses are allowed.

## 7.4 Public investors / famous managers

Track only from dated public disclosures/interviews/letters/filings. Separate `opinion stated` from `position legally disclosed` and from `position inferred`.

---

# 8. ADAPTIVE DECISION LOOP — THE PROJECT'S OPERATING RULE

Every strategy/generator keeps a versioned state rather than being frozen forever.

For each decision:

`observe -> diagnose -> forecast -> compare candidates -> choose expression -> size -> seal -> trade/shadow -> grade -> update priors/model -> next decision`

When a rule fails on a live example, do NOT instantly delete the rule or manually override the stock. Ask which layer failed:

- sensor missed evidence;
- entity mapping;
- population prior too broad;
- case adjudication absent;
- valuation model wrong for sector;
- execution constraint too crude;
- portfolio construction;
- timing/already-priced;
- expression;
- sizing;
- exit/hold decision.

Then design the smallest test that distinguishes them.

All material rule changes receive a version. Existing positions remember the version that created them; new evidence may re-underwrite them explicitly.

---

# 9. PAPER ACCOUNT / LIVE EXPERIMENT TASKS

1. Finish the clean 08-31 tracker repair and full CompanyState vintage.
2. Publish the fresh seal and activate hack4 per Murat's already-recorded approval once integrity conditions pass.
3. Add WBUY and all news-first names to OBSERVATION regardless of execution-floor status.
4. Generate and seal a WBUY DecisionCard before today's open/next actionable checkpoint. Do not manually insert a BUY.
5. Record the engine's preferred alternative candidates and why they outrank/under-rank WBUY.
6. Grade WBUY at 1d/5d/21d and track whether the engine correctly handled `already_priced`.
7. Build `HIGH_UPSIDE_ANOMALY` shadow portfolio: all >400% legitimate-adjusted targets after root-cause adjudication, with matched controls. This tests whether useful subcells exist inside the aggregate bad band.
8. Build nano-cap observation/opportunity-recall dataset. No execution authority required.
9. Add holder/13F level + concentration fields to CompanyState.
10. Add Form 4 insider fields.
11. Add politician disclosure ingestion with true public-observability timestamps.
12. Continue EventCluster + global source mesh work.

---

# 10. REQUIRED EXIT REPORT

Explain in plain language:

- what the engine said on WBUY BEFORE the outcome;
- whether WBUY was observed, executable, both or neither;
- why every external target exists and what evidence class it belongs to;
- whether >400% was data error or legitimate extreme valuation;
- engine fair-value range by method;
- best bull/base/bear scenario and probabilities;
- alternative stocks the engine preferred and why;
- holder/insider/political state when observable;
- what happened afterward;
- which component of the decision was right/wrong;
- exact rule/model version changed as a result.

Do not finish with `WBUY went up, therefore buy`. The purpose is to determine whether AEGIS could have known enough, early enough, at an executable price, and whether its reasoning generalizes.