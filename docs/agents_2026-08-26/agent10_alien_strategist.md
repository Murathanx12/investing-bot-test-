# AGENT 10 — ALIEN STRATEGIST: ten strategies that share no primary signal with Aegis

**Licence:** every strategy below is proposed under `PRODUCT_EXPERIMENT`. Nothing here is a claim.
**Prohibited as primary signal (and not used):** momentum, value, profitability, analyst revisions,
post-earnings drift, standard sentiment, option-implied volatility, insider trading, index membership.
**Read for avoidance only:** `docs/ROADMAP_2026-08-26_CAUSAL_WORLD_MODEL.md`, `alpha/brains/*`,
`docs/FINDING_*.md`, `alpha/universe.py`. Nothing modified except this file.

**Discipline shared by all ten.** Every source below is a PUBLIC RECORD with its own timestamp
(`acceptanceDateTime`, `filing_date`, `posted_date`, `release_date`, `last_update_posted`). The
signal is used STRICTLY AFTER that stamp, which means every backtest is a `join_pit_series`-style
`side="left"` join on the record's publication time, never on its period-of-report. A record whose
stamp is a DATE and not a datetime is used from the NEXT session's open. Every strategy names a
placebo that has the same publication mechanics and no economic content — that is what separates
"the record moved the price" from "the record was published on a day when prices moved".

Ranking rubric at the end: `score = P(real) × edge (bp/trade, net) × tradability (0-1)`.

---

## S1 — DEF-14A / 8-K 5.02 "CFO walked" (executive departure without successor)

- **Mechanism.** A CFO or Chief Accounting Officer who resigns *effective immediately* with no
  named successor and no "to pursue other opportunities" boilerplate is a private information
  event: the person who signs the SOX certification has decided not to sign the next one. The
  market underreacts because the 8-K arrives after hours, is one line, and carries no number;
  sell-side does not publish on it; the negative information is realised at the next 10-Q/10-K
  (restatement, material weakness, going-concern language) 30-90 days later. Slow, not wrong.
- **Signal.** From EDGAR full-text search, Item 5.02 8-Ks in the last session. Parse:
  `role ∈ {CFO, Chief Accounting Officer, Controller, Chief Financial Officer}`,
  `effective_immediately = 1` if "effective immediately"/"effective [date ≤ filing date]",
  `successor_named = 1` if an appointment appears in the same item, `boilerplate = 1` if
  "not the result of any disagreement" is ABSENT (its absence is the rarer, stronger case).
  `score = effective_immediately × (1 − successor_named) × (2 − boilerplate)`; trade `score ≥ 2`.
- **Source (free, PIT).** EDGAR full-text search `https://efts.sec.gov/LatestSearch/index?q="chief financial officer" "effective immediately"&forms=8-K&dateRange=custom` (JSON), and
  `https://data.sec.gov/submissions/CIK##########.json` (already wrapped in `alpha/sources/sec.py`).
  `acceptanceDateTime` is the stamp.
- **Entry.** Short at the next session's open after acceptance (after-hours filings → next open).
- **Exit.** 40 sessions, or the next periodic filing's acceptance (10-Q/10-K), whichever first;
  hard stop +12% against.
- **Sizing.** Equal risk: notional = 0.5% equity / p95 3-day overnight gap of the name (the engine's
  stress-loss charge). Cap 8 concurrent. Borrow must be `easy_to_borrow` in the Alpaca asset record.
- **Cost model.** Half-spread from SIP quote + 5 bp impact per 1% of ADV + borrow at 1%/yr GC;
  hard-to-borrow refused.
- **Falsifier.** Mean 40-session market-adjusted return of `score ≥ 2` names ≥ −1.0% with n ≥ 80
  → `DEPRIORITIZED`. Prediction: −4 to −7%, hit rate ≥ 58%.
- **Placebo.** 5.02 filings that are *appointments only* (new director joins) — same form, same
  after-hours timing, no departure. Must show ~0.
- **Matched control.** Same dv_bucket, same Finnhub industry, nearest-neighbour by 60-day realised
  volatility, no 5.02 in ±30 sessions.
- **Expected failure mode.** Half the signal is already in the price by the open (a −8% gap), and
  the remaining drift is a short whose gap-risk-adjusted size is tiny. The number to watch is
  `drift_after_open / total_move`; below 0.3 the edge is in the gap and untradable.
- **Stock expression.** Short common; if not shortable, refuse (`CASH:` row).
- **Option expression.** Where a chain exists: buy 45-60 DTE put spread, 25Δ/10Δ — the claim is a
  TAIL shape (restatement) and the spread caps vega cost.
- **Backtest plan (3 lines).** (1) EFTS query 2019-2026 for 5.02 8-Ks with the CFO regex, join
  `acceptanceDateTime` → next session; (2) SIP daily bars from Alpaca for name + industry ETF,
  40-session market-adjusted CAR, by `score` and by `dv_bucket`; (3) placebo = appointment-only 5.02s
  through the same code path, report both t's and the drift/gap ratio.
- **Shadow record.** `{cik, symbol, acceptanceDateTime, role, effective_immediately, successor_named,
  boilerplate, score, next_open, entry_px, borrow_flag, stop, exit_rule, market_adj_car_5/20/40,
  next_periodic_filing_date, restatement_flag_at_resolution}`.

## S2 — NT 10-K / NT 10-Q late-filing notices (Form 12b-25) — the reason field

- **Mechanism.** A 12b-25 is filed by ~600 issuers a year; ~20% cite auditor/accounting reasons
  rather than "additional time". The market treats all NTs as one category (small negative gap) but
  the subgroup that cites "the Company's auditor", "material weakness", "restatement", "not been
  able to complete its assessment" delists or restates at several times the base rate. The filing
  is a free-text form nobody parses in bulk.
- **Signal.** From the 12b-25 Part III narrative, `accounting_reason = 1` if any of
  {"auditor","material weakness","restate","internal control","investigation","audit committee"}
  appear; else 0. Trade `accounting_reason = 1` AND the issuer is in the universe.
- **Source.** EFTS `forms=NT 10-K,NT 10-Q` with `q="material weakness" OR "restatement"`;
  `data.sec.gov` submissions for stamps. Free, no key (User-Agent required, already set in `sec.py`).
- **Entry.** Short next open after acceptance. **Exit.** Filing of the late report or 30 sessions.
- **Sizing.** As S1. Refuse if `median_dollar_volume < $5M` (borrow reality).
- **Cost model.** As S1 plus 3%/yr borrow assumption for names below $300M dv_bucket "small".
- **Falsifier.** Accounting-reason NTs vs "additional time" NTs: difference in 30-session
  market-adjusted CAR < 2 pp or t < 2 on n ≥ 100 → `FAILED_VARIANT`.
- **Placebo.** "Additional time" NTs with no accounting keyword — same form, same day-of-filing gap.
- **Matched control.** As S1, plus matching on trailing 12-month return (so the short is not a
  distressed-loser factor in disguise — a control we must state because "value" is barred).
- **Failure mode.** The universe filter (`$3M/day`) removes most NT filers; n in-universe may be
  < 30 per year. If so this is a Aegis-Finance CRSP backtest, not a competition lane.
- **Stock / option.** Short common; puts rarely exist on these names — shares only.
- **Backtest.** (1) Pull all 12b-25s 2015-2026 by EFTS, classify by regex; (2) CRSP dsf in
  aegis-finance for 30-session CARs with delisting returns MEASURED (`dsedelist` is joined);
  (3) split accounting-reason vs other, and by year, and report `n_delist_measured`.
- **Shadow record.** `{cik, symbol, form, acceptanceDateTime, reason_text_hash, accounting_reason,
  keywords_hit, entry, exit_reason, car_30, late_report_filed_date, delisted_within_180d}`.

## S3 — USAspending contract awards before the 8-K (procurement leads the press release)

- **Mechanism.** Federal contract obligations post to USAspending/FPDS within days of award; the
  recipient's 8-K or press release follows days to weeks later, sometimes never. For small and mid
  caps where one award is > 10% of trailing revenue, the government's own ledger prints the number
  before the company does. Slow because nobody in the sell-side reads FPDS by recipient UEI daily.
- **Signal.** Daily query of new awards where `recipient_parent_name` maps to a listed issuer (build
  the map once from SEC `company_tickers.json` + recipient names, fuzzy-matched then hand-audited),
  `award_amount / trailing_4q_revenue ≥ 0.10` (revenue from XBRL `companyfacts` `Revenues`), and
  no 8-K Item 1.01/8.01 mentioning the contract has been accepted yet.
- **Source.** `https://api.usaspending.gov/api/v2/search/spending_by_award/` (POST, free, no key;
  filter `time_period` on `action_date`, `award_type_codes` A-D);
  `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` for revenue.
  `action_date` is the stamp; FPDS posting lag is 1-3 business days — use the API's `last_modified`
  as the availability time, not `action_date`, or the backtest is a lookahead.
- **Entry.** Long next open after the award appears in the API with `last_modified` ≤ prior close.
- **Exit.** 8-K/press-release acceptance about the award + 2 sessions, or 20 sessions.
- **Sizing.** 1% equity per name, cap 5. **Cost.** Half-spread + impact; these are small caps, so
  impact assumed 10 bp per 1% ADV and refused above 3% ADV.
- **Falsifier.** Mean 20-session market-adjusted return < +1.5% or the event-day return on the
  later 8-K is not positive on average (which would mean the company's release was already priced)
  → `DEPRIORITIZED`.
- **Placebo.** Awards where `award_amount / revenue < 0.01` (immaterial) — same posting mechanics.
- **Matched control.** Same industry (NAICS from the award itself — a bonus), same dv_bucket, no
  award in ±60 sessions.
- **Failure mode.** Name-matching error: recipient is a subsidiary of a large parent, the award is
  immaterial to the parent, and the model "finds" a 30% revenue award on a $50B company. The
  UEI→ticker map is the whole risk and must carry a hand-audit receipt.
- **Stock.** Long common. **Option.** 30-45 DTE call spread when the later 8-K date is unknown —
  a STEP shape (the announcement), so a spread, not a straddle.
- **Backtest.** (1) USAspending bulk download 2018-2026, filter awards ≥ $20M, map to CIK;
  (2) join `companyfacts` revenue by `filed` date (PIT), keep ratio ≥ 0.10; (3) Alpaca SIP bars for
  20-session CAR from `last_modified` +1, versus immaterial-award placebo; report the map's
  hand-audit precision on 100 random rows.
- **Shadow record.** `{award_id, recipient_uei, symbol, cik, action_date, last_modified, amount,
  trailing_rev, ratio, naics, agency, entry, later_8k_date, car_5/20, map_confidence}`.

## S4 — FDA PDUFA / AdCom calendar: the *no-news* window on a scheduled date

- **Mechanism.** A PDUFA goal date is public months ahead; biotechs that receive a CRL or an
  approval issue a press release within hours. When the goal date passes with NO release for two
  full sessions, one of two things is true: a quiet extension (FDA asked for more, usually a
  3-month "major amendment" — bad) or the company is sitting on an approval it must disclose
  under Reg FD (rare). The base rate of silence → CRL/extension is high, but retail holders anchor on
  "no news is good news". The mechanism is inaction under a hard deadline, not a factor.
- **Signal.** `silent_days = sessions since PDUFA date with no 8-K Item 8.01 and no press release
  in Alpaca news for the ticker`. Trade `silent_days = 2`.
- **Source.** PDUFA dates: FDA's "Novel Drug Approvals" and advisory-committee calendar
  (`https://www.fda.gov/advisory-committees/advisory-committee-calendar`), plus each company's own
  10-K/10-Q "PDUFA target action date" via EFTS query `"PDUFA" "target action date"` (the date is
  stated in the filing, PIT by acceptance). ClinicalTrials.gov v2 API
  (`https://clinicaltrials.gov/api/v2/studies?query.spons=...`) for sponsor/NCT mapping. All free.
- **Entry.** Short at open of session PDUFA+3 if silent. **Exit.** First 8-K/news on the drug, or
  15 sessions. Stop +15%.
- **Sizing.** 0.5% equity per name (biotech gaps are the p95 the engine measures); cap 4.
- **Cost.** Borrow 5-20%/yr assumed for small biotech; refused if not `easy_to_borrow`.
- **Falsifier.** Post-silence 15-session return not more negative than the XBI-matched control by
  ≥ 3 pp, n ≥ 40 → `FAILED_VARIANT`.
- **Placebo.** Same names, a random date 60-120 sessions before the PDUFA date with no news for two
  sessions — "silence" without a deadline.
- **Matched control.** XBI constituents by market cap tercile and cash-runway bucket (XBRL
  `CashAndCashEquivalentsAtCarryingValue` / trailing opex), no catalyst in ±30 sessions.
- **Failure mode.** The PDUFA date extraction is wrong by a quarter (companies restate dates in
  later filings) and we short into an approval. Every date must be re-verified against the LATEST
  filing before entry; the receipt stores the filing it came from.
- **Stock.** Short. **Option.** Long put 20-30 DTE, 30Δ; the claim is a TAIL, so an outright put,
  sized by premium.
- **Backtest.** (1) EFTS 2019-2026 for stated PDUFA dates, dedupe to latest per NDA; (2) for each,
  count news-free sessions after the date via SEC submissions + Alpaca news; (3) CAR vs XBI for
  silent vs prompt-news cases, and the resolution mix (approval / CRL / extension) at 30 days.
- **Shadow record.** `{symbol, nda_or_bla, pdufa_date, source_filing, silent_days, entry,
  resolution_type, resolution_date, car_5/15, xbi_car_15, borrow_rate}`.

## S5 — Grid stress → merchant-generator and power-equipment long (EIA hourly demand vs capacity)

- **Mechanism.** EIA publishes hourly demand, net generation and interchange per balancing
  authority with a ~1-hour lag. When ERCOT/PJM/MISO demand runs > 95% of the prior-year peak for
  three consecutive afternoons AND day-ahead reserve margins compress, real-time prices spike into
  the thousands of $/MWh; merchant generators (VST, NRG, CEG, TLN) and peaker-equipment names book
  that revenue but report it a quarter later. The market prices the heat wave on the weather
  forecast, not the realised dispatch — and realised scarcity is CONVEX (the roadmap's own §3:
  nothing until ~95%, then it explodes). This is `infrastructure_shadow_demand` measured, not
  narrated.
- **Signal.** `stress_t = demand_t / max(demand over prior 365d)` from EIA-930 for ERCO, PJM, MISO;
  trigger when the 3-day max of the daily peak `stress ≥ 0.95` and the NOAA 6-10 day outlook keeps
  the region above-normal. Long a merchant-power basket, short a regulated-utility basket
  (regulated names earn nothing from scarcity — the natural control).
- **Source.** `https://api.eia.gov/v2/electricity/rto/region-data/data/?api_key=...` (free key,
  hourly, `period` is the stamp); NOAA CPC outlooks
  `https://www.cpc.ncep.noaa.gov/products/predictions/610day/` (free). ERCOT public
  real-time price feed as confirmation.
- **Entry.** Next open after the third stressed day. **Exit.** Stress < 0.90 for two days or 10
  sessions. **Sizing.** 2% gross per side, dollar-neutral. **Cost.** Liquid large caps, half-spread
  + 2 bp.
- **Falsifier.** Long-short 10-session return < +1% or not different from entering on the weather
  FORECAST alone (the pre-registered rival: if the forecast captures it, the realised-dispatch
  signal adds nothing) → `FAILED_VARIANT`.
- **Placebo.** Same trigger computed on a balancing authority where the basket has no assets
  (e.g., stress in BPA/CAISO for a Texas-only basket).
- **Matched control.** The regulated-utility short leg IS the control; additionally XLU.
- **Failure mode.** ~4-8 triggers a year. Too few for the competition; a 5-year backtest has ~30.
  Also, the market may have learned this after Uri (2021) — check the pre/post-2021 split.
- **Stock.** VST/NRG/CEG/TLN vs DUK/SO/ED/XEL. **Option.** Long 30 DTE calls on the merchant
  basket — CONVEX claim, convex instrument.
- **Backtest.** (1) EIA-930 hourly since 2018 → daily peak stress per BA; (2) SIP/CRSP bars for the
  two baskets, event-study on triggers; (3) rival = trigger on NOAA anomaly alone; report both.
- **Shadow record.** `{ba, trigger_date, stress, prior_peak, noaa_outlook, rt_price_max, basket_long,
  basket_short, entry, exit_reason, ls_ret_5/10, forecast_only_ret}`.

## S6 — Patent-term and Orange Book "first generic filer" ladder (loss-of-exclusivity timing)

- **Mechanism.** Loss of exclusivity for a branded drug is a STEP whose date is written in the
  Orange Book patent/exclusivity file and in Paragraph IV certification lists. The branded seller's
  revenue cliff is known to specialists but priced slowly because (a) the date shifts with
  litigation/30-month stays and (b) the generic entrants' upside is spread over several small
  names. Slow, not wrong: FDA's own list moves before the sell-side model does.
- **Signal.** Weekly diff of the Orange Book exclusivity file and the Paragraph IV list. Event =
  a new PIV certification on a product whose sales (from the brand's 10-K product table, EFTS
  full-text) are ≥ 8% of the brand's revenue. Long the generic filer(s), short the brand, 1:1 gross.
- **Source.** Orange Book data files `https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files` (zip, weekly), Paragraph IV list
  `https://www.fda.gov/drugs/abbreviated-new-drug-application-anda/paragraph-iv-patent-certifications`; product sales via EFTS. USPTO PatentsView
  `https://search.patentsview.org/api/v1/patent/` for expiry confirmation. All free.
- **Entry.** Next open after the list update. **Exit.** 60 sessions or the first court ruling.
- **Sizing.** 1% per leg, cap 3 pairs. **Cost.** Half-spread + 3 bp; borrow GC on large pharma.
- **Falsifier.** Pair return over 60 sessions ≤ 0 or t < 1.5 on n ≥ 30 pairs → `DEPRIORITIZED`.
- **Placebo.** PIV certifications on products < 1% of brand revenue.
- **Matched control.** Brand vs same-cap pharma without an LOE in 24 months; generic vs same-cap
  generic without a new PIV.
- **Failure mode.** Update cadence is weekly and the date on the list lags the actual filing by up
  to 30 days; the information may be in the price before the list shows it. Measure the return in
  the 30 sessions BEFORE the list update — if it is where the move is, the list is not PIT enough.
- **Stock.** Pair. **Option.** None (STEP with an uncertain date — a spread on the brand only if a
  court date is known).
- **Backtest.** (1) Archive.org snapshots of the PIV list 2016-2026 → event dates; (2) revenue
  materiality from EFTS product tables; (3) CRSP pair CARs, pre-window vs post-window.
- **Shadow record.** `{product, nda, brand_symbol, generic_symbols, piv_list_date, list_lag_days,
  product_rev_share, entry, pair_ret_20/60, pre_window_ret_30, court_event_date}`.

## S7 — Cross-listed ADR overnight information transfer (home-market close → US open)

- **Mechanism.** For Asian and European ADRs, the ordinary share trades a full session before the
  US open; the ADR's prior US close carries stale information. US pre-market ADR quotes are thin,
  and the opening auction under-adjusts for the home move when the home move is large relative to
  its own volatility (the CROSS-country leading indicator, one hop, no LLM). This is not momentum:
  it is the same asset at two clocks.
- **Signal.** `gap = home_close_ret_t × FX_adj − ADR_premarket_implied_ret`; trade when
  `|gap| ≥ 1.5 × home 20-day daily σ` and the US open has not yet closed the gap (compare the
  opening print to `home_close × FX / ratio`).
- **Source.** Home closes: Stooq (`https://stooq.com/q/d/l/?s=2330.tw&i=d`, free CSV, PIT by
  date) or Yahoo (already installed in aegis-finance); FX from FRED (`DEXJPUS` etc., or intraday
  via Stooq `usdjpy`); ADR pre-market/open from Alpaca SIP minute bars (`extended hours`).
- **Entry.** At the US open, direction of the un-closed residual. **Exit.** US close same day
  (≤ 6.5h hold). **Sizing.** 2% notional, cap 6 names. **Cost.** Half-spread at the open (measured
  from the auction quote) + 2 bp; the whole edge lives above this line and must be reported net.
- **Falsifier.** Mean net open-to-close return in the residual's direction < 5 bp or t < 2 on
  n ≥ 200 → `FAILED_VARIANT`.
- **Placebo.** Same rule with the home return LAGGED one extra day (the information is already in
  the ADR's previous US session — must show ~0).
- **Matched control.** US-listed peers in the same industry with no home-market listing (e.g., TSM
  vs a US semi) — the residual should not predict them.
- **Failure mode.** The opening auction already clears it; the residual after the open is a bid-ask
  bounce. The tell: gross edge positive, net edge zero. Quote the spread at the open, not the
  average.
- **Stock.** ADRs: TSM, ASML, SONY, TM, BABA, NVO, SAP, SHOP-like names in the universe.
- **Option.** None — intraday.
- **Backtest.** (1) Stooq home closes + FX for 25 ADRs 2022-2026; (2) Alpaca SIP minute bars for the
  9:30 open and 16:00 close; (3) residual vs open-to-close net of measured half-spread, and the
  lagged placebo.
- **Shadow record.** `{adr, home_symbol, home_close_ret, fx_ret, ratio, implied_open, actual_open,
  residual_sigma, direction, half_spread_bp, entry, exit, net_ret_bp}`.

## S8 — Court-docket outcome timing (CourtListener RECAP: order entered, opinion not yet released)

- **Mechanism.** In securities/patent/antitrust litigation the docket entry ("ORDER granting motion
  for summary judgment", "Judgment entered", "Markman order") appears on PACER/RECAP hours before
  the opinion text is read and before the company's 8-K. Docket entries are free on CourtListener's
  RECAP API when any RECAP user has fetched them; the entry's `date_filed` and `date_created` are
  PIT. Market slowness is a reading-speed problem: the entry is one line, the opinion is 60 pages.
- **Signal.** Alert on new docket entries in cases where a listed issuer is a party and the
  entry description matches `ORDER (GRANTING|DENYING) .* (summary judgment|injunction|dismiss|
  class certification)`; direction from party role (plaintiff/defendant) × granted/denied. The
  LLM is allowed exactly one job: classify the entry into {favours issuer, harms issuer, unclear} —
  and "unclear" is refused, not traded.
- **Source.** `https://www.courtlistener.com/api/rest/v4/docket-entries/?docket__case_name__icontains=...`
  and `/search/?type=r&q=...` (free API key, generous limits); party→CIK map via EFTS 10-K "Legal
  Proceedings" sections (the case names are stated there).
- **Entry.** Next open after `date_created` (the RECAP upload time — NOT `date_filed`, which can be
  earlier than public availability). **Exit.** Company 8-K/press release + 1 session, or 10 sessions.
- **Sizing.** 1% per name, cap 4. **Cost.** As S1.
- **Falsifier.** Signed 10-session CAR < +1% or t < 2, n ≥ 60 → `DEPRIORITIZED`.
- **Placebo.** Procedural entries (scheduling orders, notices of appearance) in the same cases.
- **Matched control.** Same industry/dv_bucket, no docket activity in ±20 sessions.
- **Failure mode.** RECAP coverage is sparse for non-famous cases: the entry appears on
  CourtListener only when someone with the extension pays PACER for it, so `date_created` can lag
  `date_filed` by days and the 8-K may precede it. The lag distribution IS the first receipt.
- **Stock.** Long/short common. **Option.** For a known hearing date: a directional vertical, never
  a straddle (the direction is the claim — `feedback_a_forecast_sd_is_a_claim`).
- **Backtest.** (1) CourtListener bulk docket-entries for cases matched to the universe's 10-K
  legal-proceedings sections 2020-2026; (2) classify entries by regex, 10-session CARs from
  `date_created`+1; (3) report the `date_created − date_filed` lag distribution and the share of
  cases where the 8-K came first.
- **Shadow record.** `{docket_id, case_name, symbol, party_role, entry_no, description, date_filed,
  date_created, classification, entry, exit_reason, car_2/10, company_8k_date}`.

## S9 — Sanctions / Entity List additions → supplier revenue exposure (BIS Federal Register)

- **Mechanism.** An Entity List addition is a STEP at an effective date; it is announced in the
  Federal Register with a public-inspection copy the day before. Listed US suppliers disclose
  China/customer concentration in their 10-K (XBRL `ConcentrationRiskPercentage` and the
  "customers accounting for ≥10% of revenue" text). The first-order names react on day 0; the
  SECOND-order suppliers with 10-30% revenue exposure to the listed customer drift for weeks
  because the exposure is in a footnote, not a headline. `geopolitical_substitution` with a
  measured exposure table instead of a narrative.
- **Signal.** For each new Entity List addition, `exposure_i = % of revenue from the added entity
  or its parent` parsed from supplier 10-Ks (EFTS: `"Huawei" "% of our revenue"`-style queries,
  extended to the new entity's name). Short suppliers with `exposure ≥ 10%` that did NOT move
  ≥ 1σ on day 0.
- **Source.** Federal Register API `https://www.federalregister.gov/api/v1/documents.json?conditions[agencies][]=industry-and-security-bureau&conditions[term]="Entity List"` (free; `publication_date`
  and public-inspection `filed_at` are the stamps); EFTS + XBRL `companyfacts` for exposure.
- **Entry.** Next open after publication. **Exit.** 20 sessions or the supplier's own 8-K.
- **Sizing.** 1% per name, cap 5. **Cost.** As S1.
- **Falsifier.** 20-session CAR of exposed-but-unmoved suppliers ≥ −1.5% or t > −2 on n ≥ 40 →
  `DEPRIORITIZED`.
- **Placebo.** Suppliers with stated exposure < 2% to the same entity.
- **Matched control.** Same industry, no disclosed exposure, matched on day-0 move.
- **Failure mode.** The exposure text is 12-18 months old; the supplier already diversified. The
  receipt stores the filing date of the exposure sentence, and exposures older than 15 months are
  down-weighted to zero.
- **Stock.** Short. **Option.** 30-45 DTE put spread (STEP then GRADIENT — a spread, and roll it).
- **Backtest.** (1) Federal Register Entity List documents 2019-2026; (2) EFTS for each added
  entity's name in 10-K revenue-concentration text, build exposure table with filing dates;
  (3) CARs by exposure bucket and day-0 move, placebo at < 2%.
- **Shadow record.** `{fr_document, entity_added, publication_date, supplier_symbol, exposure_pct,
  exposure_filing_date, day0_move_sigma, entry, car_5/20, later_8k}`.

## S10 — 13F-position-size cliff on the filing deadline (the 45-day disclosure and the crowding unwind)

- **Mechanism.** 13F holdings are public 45 days after quarter-end and arrive in a burst on the
  deadline day (Feb/May/Aug/Nov 14-15). Names where the top-5 hedge-fund holders' aggregate stake
  ROSE above 25% of float in the quarter are crowded by definition; the deadline is the first day
  every other holder can see it. Not "insider" (these are outside institutions) and not momentum
  (the prior return is explicitly controlled): the claim is that DISCLOSURE of crowding, on a known
  date, produces a same-week unwind in small caps where the crowd is a large share of float.
- **Signal.** From 13F-HR XBRL infotables, `crowd = Σ(top-5 holders' shares)/shares_outstanding`
  (float from XBRL `EntityCommonStockSharesOutstanding`); `Δcrowd` vs prior quarter. Short names
  with `crowd ≥ 0.25` AND `Δcrowd ≥ 0.05` in the two sessions after the deadline; long the bottom
  `Δcrowd` decile as the hedge.
- **Source.** EDGAR 13F structured data sets
  `https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets` (quarterly zips, free)
  and `data.sec.gov` submissions for `acceptanceDateTime` of each 13F; the SIGNAL date is the
  deadline day, and anything accepted after it is excluded (late filers are lookahead).
- **Entry.** Deadline + 1 open. **Exit.** 10 sessions. **Sizing.** 1% per name, cap 10, dollar-neutral.
- **Cost.** As S1; borrow assumed 2%/yr on small caps, refused if not ETB.
- **Falsifier.** Long-short 10-session return < +1% or t < 2 across ≥ 12 deadlines → `FAILED_VARIANT`.
- **Placebo.** Same construction computed from the PRIOR quarter's 13F (already-known crowding):
  must show ~0, or the effect is stale crowding, not disclosure.
- **Matched control.** Same size and same trailing 3-month return decile (explicit, because
  crowding correlates with past winners and momentum is barred).
- **Failure mode.** Only 4 events a year; competition sees at most one (Nov 14 is after the
  deadline — none). This is an Aegis-Finance CRSP experiment; in the competition it is a shadow
  record of the Aug 14 cohort only.
- **Stock.** Pair. **Option.** None.
- **Backtest.** (1) 13F data sets 2014-2026, compute `crowd`/`Δcrowd` per CUSIP per quarter;
  (2) map CUSIP→permno via CRSP `stocknames`, 10-session CARs from deadline+1 with the momentum-
  decile control; (3) placebo on the prior quarter's numbers.
- **Shadow record.** `{quarter, deadline, symbol, crowd, delta_crowd, top5_filers, float,
  mom_3m_decile, entry, ls_ret_5/10, late_filers_excluded}`.

---

## Ranking — `P(real) × edge (bp net/trade) × tradability`

| rank | strategy | P(real) | edge bp | tradability | score | why |
|---|---|---|---|---|---|---|
| 1 | **S7 ADR overnight residual** | 0.45 | 15 | 0.9 | **6.1** | one-hop, same asset two clocks, n ≥ 200 in weeks, falsifiable in the competition window; net-of-spread is the whole question |
| 2 | S1 CFO walked | 0.50 | 300 | 0.35 | 5.3 | strong mechanism, ~150 events/yr, but shorts with gap risk |
| 3 | S3 USAspending before the 8-K | 0.40 | 250 | 0.45 | 4.5 | public ledger prints before the company; map risk is the cost |
| 4 | S8 Court dockets | 0.40 | 250 | 0.4 | 4.0 | reading-speed edge; RECAP lag decides it |
| 5 | S9 Entity List second-order | 0.35 | 200 | 0.5 | 3.5 | measured exposure table; stale-exposure risk |
| 6 | S2 NT 10-K reason field | 0.55 | 400 | 0.15 | 3.3 | probably real, mostly unborrowable / out of universe |
| 7 | S4 PDUFA silence | 0.35 | 500 | 0.15 | 2.6 | big edge, tiny n, date-extraction risk |
| 8 | S5 Grid stress | 0.35 | 120 | 0.6 | 2.5 | 4-8 triggers/yr; forecast-only rival may absorb it |
| 9 | S10 13F crowding cliff | 0.30 | 150 | 0.4 | 1.8 | 4 events/yr, none in the window |
| 10 | S6 Orange Book PIV ladder | 0.30 | 150 | 0.3 | 1.4 | weekly cadence, likely pre-empted |

### Build first: S7 — ADR overnight residual

Why: it is the only one of the ten that produces **≥ 40 gradeable rows per week** inside the five
remaining equity sessions, the falsifier is a t-test on net-of-spread open-to-close returns with
no LLM in the loop, the placebo (lag the home return one more day) is a one-line change, and it
is the roadmap's `cross_country_leading_indicator` template reduced to a single measured hop — so
its Brier row feeds the psychohistory calibration table directly. If it fails it fails in a week,
publicly, with a number, which is also what the judges rewarded.

First five lines of the code-level plan:

1. `alpha/sources/stooq.py` — `home_close(symbol_home, days=30) -> list[(date, close)]` via
   `https://stooq.com/q/d/l/?s=...&i=d`, through `alpha.sources.http.get_json`'s sibling
   `get_text`; refuse (`SourceRefusal`) on < 20 rows or a stale last date; FX from FRED series via
   the same pattern. Receipt: `state/adr_home_closes/{date}.json`.
2. `alpha/brains/adr_residual.py` — `forecast(client, adr, horizon_days=0.27)` returning the
   base `Forecast` with `centre = residual`, `width = home_20d_sigma`, `claim = "direction"`, and
   `NotApplicable` when `|residual| < 1.5σ` or the open has already closed it (read from Alpaca SIP
   1-minute bars at 09:30-09:31).
3. `scripts/adr_residual_backtest.py` — 25 ADRs × 2022-2026: residual → open-to-close net of the
   measured opening half-spread; the lagged placebo through the same function; writes
   `state/adr_residual_backtest.json` with `n, mean_bp, t, hit, placebo_t, half_spread_bp_median`.
4. Register the brain in `alpha/runner.py`'s brain table as SHADOW-ONLY with `action: SHADOW_ONLY`
   until the backtest's `t ≥ 2 AND placebo_t < 1` line is green; promotion is a flag flip, attended.
5. Shadow record schema in `state/forecasts.jsonl` extended with the S7 fields above; the daily
   autopsy (`scripts/daily_autopsy.py`) reads `net_ret_bp` per row so the first grade lands the
   session after the first forecast.

---

## The attack: why `HIGH_DISPERSION_US_v1` will produce noise, with a number

`alpha/universe.py` screens 4,634 names on price ≥ $2 and median $3M/day, then feeds every
scheduled printer through one brain and reads the daily autopsy for "what won and why". The
argument against it is arithmetic, not taste.

**The universe multiplies the number of hypotheses tested each day by ~300× (15 → 4,634) while
the number of independent outcomes per day stays 1 (one market session), so the daily
candidate report is a maximum over ~4,600 draws, and the expected best-of-N z-score of pure noise
at N = 4,634 is `E[max Z] ≈ sqrt(2 ln N) ≈ 4.1`.** Any "why" the autopsy compiles for the top
mover is therefore an explanation of a 4σ draw that noise produces EVERY DAY. Concretely: with
a cross-sectional daily σ of ~3% in the small/micro dv_buckets (which are ~60% of the members),
the expected largest daily move among 4,634 names under no information at all is `4.1 × 3% ≈ +12%`,
and the top ten will all exceed ~+8% — the same bucket boundary the PEAD brain uses as its "big
move" cut. The autopsy will find a plausible template for each of them (the compiler is asked to,
and it never returns "no reason"), tally the template, and the `knowable-before` count will
drift upward on survivorship alone. Over the five remaining sessions the report will name 50
winners, the compiler will explain 50, and **the number of those explanations that would have
selected the name prospectively at a false-positive rate below 1/4,634 is, by construction of
the screen, statistically indistinguishable from zero** — because a prospective rule with even
0.5% daily false-positive rate fires on 23 names a day, and the engine cannot hold 23 names.

The whole-market search is only an edge if the screen is on a MECHANISM with a base rate well
above 1/N — an 8-K 5.02, a docket entry, a PDUFA date — so that the candidate set is 5-30 names
with a stated reason BEFORE prices are looked at. The `UNIVERSE_COLLAPSE` audit guards against the
wrong failure: the danger is not that the search returns the old fifteen, it is that it returns
a fresh random ten every day and a story for each.

---

**File:** `C:\Users\mrthn\aegis-alpha-terminal\docs\agents_2026-08-26\agent10_alien_strategist.md`
