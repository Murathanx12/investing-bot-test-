# AGENT 2 — SHORT SELLER · adversarial round 2026-08-26

Every number below was computed read-only from `state/pead_wide_legs_v1.jsonl` (25,856 SEC-dated legs,
2024-02 → 2026-08, 3-session beta·QQQ-adjusted forward, `signed` = forward in the day-0 direction) and from
SEC EDGAR `submissions` / `companyfacts` pulled 26 Aug 2026 (UA per `alpha/sources/sec.py`). Scratch scripts:
`legs.py`, `runway.py`, `interact.py`, `cell.py`, `dilution.py` (session scratchpad; to be re-homed as
`scripts/pead_broken_narrative.py`, §1.14). Nothing in the repo was modified.

**Headline: the candidate FINANCING_SHADOW mechanism was tested and it does not carry the drift. The drift lives
in CASH-GENERATIVE names whose PREVIOUS print was GOOD. I am proposing that instead.**

---

## 1. STRATEGY — `BROKEN_NARRATIVE_SHORT_v1`

### 1.1 Economic mechanism
A bad print is absorbed slowly when holders are positioned for the opposite. After an UP ≥3.5% print, the name has
been bought by momentum/PEAD longs, upgraded by the sell side, and added to "beat-and-raise" screens; the next
print's DOWN ≥3.5% reaction forces sequential, not simultaneous, unwinds (analyst cuts land over days, quant
rebalances are monthly, retail averages down). The information is public on day 0; the *positioning* it has to
work through is the friction. This is the classic under-reaction story with one conditioning variable that
identifies where the crowd is, and it needs NO dilution, NO distress and NO story — which is why it is worth more
to a short seller than the distress cohort (see 1.12: the distress cohort is where shorts get squeezed).

### 1.2 Exact signal (all point-in-time, computable at 15:55 ET on day 0)
1. Issuer has an 8-K Item 2.02 on EDGAR for this print — `alpha/sources/sec.earnings_releases` (bmo/amc from acceptance time).
2. Day-0 close-to-close return `r0 ≤ −3.5%` (SIP close). Both bands admitted (3.5–8.2% and >8.2%).
3. **Prior 8-K 2.02 print within 200 calendar days had `r0_prev ≥ +3.5%`** (the broken narrative).
4. Universe member (`HIGH_DISPERSION_US_v1`), `dv_bucket ∈ {small, mid}` (median $10M–$1B/day), price ≥ $5.
5. Venue flags `shortable AND easy_to_borrow` at decision time (Alpaca asset record). Otherwise REFUSED, logged.
6. Not within 7 days of a prior 2.02 by the same issuer (311 such duplicates in the file — restatements/preliminaries).

### 1.3 What the legs file says about that cell (`cell.py`)

| slice | n | mean signed 3d | hit | t iid | t week-blocks | t issuer-clusters |
|---|---|---|---|---|---|---|
| **prior-UP then DOWN, all buckets** | 2,164 | **+0.92%** | 56% | **+6.29** | **+2.33** (117 wks) | +5.05 (1,415 issuers) |
| control: DOWN with no prior-UP | 5,317 | +0.39% | 54% | +4.02 | **+0.36** | +2.02 |
| cell, small+mid | 1,434 | +0.71% | 55% | +4.18 | +1.68 | +3.08 |
| cell, small+mid, **bmo** | 609 | **+0.94%** | 56% | +3.69 | +0.64 | +2.98 |
| cell, prior UP > 8.2% | 1,195 | +0.91% | 57% | +4.32 | +2.06 | +3.51 |
| cell 2024 / 2025 / 2026 | 507 / 914 / 743 | +1.47 / +0.83 / +0.64% | | +4.7 / +4.1 / +2.4 | | |

The conditioning variable **more than doubles the base DOWN drift** (+0.92% vs +0.39%) and — the part that matters
for a 3-session book — is the only version whose week-block t survives (2.33 vs 0.36 for the unconditioned rule).
The parent's `pead_adversarial_v1` mid-band two-way t of 2.15 was for the unconditioned rule; this cell is not
weaker after clustering, it is stronger. By quarter, small+mid: 10 of 11 quarters positive (only 2026Q1 at −0.14%
on 190 legs; 2024Q1 is one leg). Compare the unconditioned mid band: 6 of 11 quarters negative.

Net of a round-trip charge (small+mid cell, n=1,434): 10 bp +0.61% (t 3.59) · 20 bp +0.51% (3.00) · **30 bp +0.41%
(2.41)** · 50 bp +0.21% (1.22). The mid band of the unconditioned rule dies at 50 bp; this cell is still positive.

Also measured and NOT used as a filter, so nobody mistakes it for one: beta 1.5–2.0 DOWN legs carry +1.85% (t 5.6,
n=575) but beta >2 carries +0.21% (t 0.4) — non-monotone, one bucket, not a rule. bmo prints drift more than amc
(+0.75% t 6.4 vs +0.41% t 3.7) across all DOWN legs; used as a tie-break in sizing only. Honest caveat: the cell was
found by looking (prior-UP was one of three prior-print states I cut), so it is `PRODUCT_EXPERIMENT` evidence, not a claim.

### 1.4 Point-in-time sources available here
- **EDGAR submissions JSON** (`alpha/sources/sec.py`) — 8-K 2.02 dates + acceptance time (bmo/amc). Already built.
- **EDGAR companyfacts** (`data.sec.gov/api/xbrl/companyfacts/CIK##########.json`) — every fact carries `filed`,
  so PIT is `filed < day0`. Used in 1.12 for runway; proposed parser `alpha/sources/sec.companyfacts_pit(symbol, asof)`.
- **EDGAR forms S-3 / S-3ASR / 424B5 / 424B4** from the same submissions JSON — shelf and take-downs, `filingDate` PIT.
- **Form 4** — same JSON, `form == "4"`; parsing the XML for open-market sales (transaction code S, not F/M) is a
  proposed extension, not used in v1.
- **Alpaca** — asset record `shortable`/`easy_to_borrow` (no fee rate on paper), SIP daily bars, next-open fills.
- **Finnhub** — `epsActual/epsEstimate` for the calendar cross-check (1.11); recommendation trends as evidence only.

### 1.5 Entry / exit
- Decide 15:55 ET day 0 (for amc prints, day 0 is the next session — the file's convention). Enter **short at the
  next session's open** (day+1 open). The mega-cap finding showed day+1 open keeps +1.08% of +1.13%; the wide
  version at day+1 open is *not yet measured* and is the first receipt the backtest must print (1.14).
- Exit at the **close of the 3rd session after entry** (hard), or earlier on: (a) adverse move ≥ 8% from entry
  (raw, not beta-adjusted — a stop must be executable), (b) a new 8-K from the issuer with Item 1.01/2.01/8.01
  (deal, guidance re-affirm, buyback), (c) borrow flag flips to not-ETB (cover, do not wait for recall).
- No re-entry on the same leg. No pyramiding.

### 1.6 Sizing ($100k paper)
- Gross short cap **40% of equity** ($40k); **per-name 4%** ($4k notional); max 10 concurrent names; per-day cap 5.
- Risk per name = `alpha/engine/equity.stress_charge` (5% stop + measured p95 overnight gap, raised to the implied move
  if an event is inside the window). At the cell's realised sd of ~6%, p5 −9.6%, expected charge ~10–12% of
  notional → $400–$500 at risk per name, $4–5k for the book. `theoretical_loss` row says UNBOUNDED; admission uses the charge.
- Prefer bmo prints and dv_bucket small over mid when the day's queue exceeds 5 (tie-break, not a filter).
- Beta hedge: none at v1 (3 sessions; the signal is beta-adjusted in measurement, the book carries the residual
  −beta exposure; recorded, not hedged, so the shadow P&L is attributable).

### 1.7 Transaction-cost model, INCLUDING borrow and hard-to-borrow refusal
| component | small bucket | mid bucket | source / rule |
|---|---|---|---|
| half-spread, entry + exit | 12 bp + 12 bp | 5 bp + 5 bp | SIP quotes at open; measured in `fill_audit.py` for the mega book, to be re-measured here |
| market impact at $4k notional | 0 | 0 | notional ≪ 0.1% of ADV at ≥$10M/day |
| **borrow fee, ETB** | 0.5%/yr ⇒ **0.6 bp / 3 sessions** | same | assumed; Alpaca paper charges nothing, so the charge is BOOKED synthetically onto the ledger row |
| **HTB** | **REFUSED** | REFUSED | no PIT fee rate exists on paper; a name that is not `easy_to_borrow` is not built (`equity.py` already logs this) |
| **Reg SHO SSR** | +10 bp adverse, 15% non-fill | +5 bp, 10% non-fill | a >10% intraday drop puts the name on SSR for day 0 AND day+1; a short must be priced above the NBB, i.e. the entry is passive. Every big-band leg is on SSR at entry. Modelled as slippage + a random non-fill, and printed |
| locate failure on ETB | 3% of legs unfilled | 1% | assumption; shadow counts actual refusals |
| **total round trip** | **~35–45 bp** | **~15–25 bp** | vs the cell's +0.71% gross; net ≈ +0.30–0.55% |

The 50 bp case is the break-even for the *unconditioned* rule (t −0.55); for this cell 50 bp still leaves
+0.21% (t 1.2) — thin, which is why the mid bucket is in the universe: it pays the smaller spread.

### 1.8 Falsifier (pre-declared)
- After **120 prospective legs** (≈ 2 earnings seasons): two-way (issuer × week) t of net signed return < 1.0, or
  mean net ≤ 0 → `DEPRIORITIZED`.
- After **200 legs**: cell mean minus matched-control mean (1.10) not > 0 → the *conditioning* is retired
  (`FAILED_VARIANT`) and only the base DOWN rule is kept for consideration.
- At any time: fill rate < 70% of decided legs → the cost model is wrong; halt and re-measure before any claim.

### 1.9 Placebo
1. **Specification placebo, already run:** prior-DOWN-then-DOWN (the mirror conditioning) gives +0.50%, week-t 1.26 —
   about the unconditioned base, not the cell. If positioning were irrelevant the two conditionings would match.
2. **Event placebo, to run:** the same rule on **non-earnings** days with a ≥3.5% beta-adjusted drop and a prior
   ≥3.5% up-day in the same window (needs bars only). If the non-earnings drop drifts the same, the 8-K is decoration.
3. **Date placebo:** shift every day 0 by +5 sessions; the drift must vanish.

### 1.10 Matched control
For each cell leg, the nearest DOWN leg by (dv_bucket, band, same ISO week) whose prior print was *not* UP ≥3.5%.
In the file: cell small+mid +0.71% vs control small+mid +0.42% → **+0.29%/leg attributable to positioning**, with
the control's week-t at 0.01. The paired difference, not the cell mean, is the number the shadow book is graded on.

### 1.11 Expected failure modes (ranked by how often the file says they happen)
- **Squeeze / snap-back:** 4.5% of cell legs move >10% against the short in 3 sessions; p1 = −17.5% across all DOWN
  legs; worst in the cell −26% (SATL 2026-05-12), −22.8% OLN, −22.3% NVTS. The stop at 8% caps most; a gap does not.
- **Buyout / activist 8-K:** a beaten-down small cap with a bullish shareholder base is a target; the 8-K exit rule
  (1.5b) is the only defence. Not measured in the file (no 8-K 1.01 join); the shadow record must log it.
- **The narrative was not broken — the market was:** 2026Q1 (−0.14% on 190 legs) coincides with the macro sell-off;
  prints during index-level drawdowns are absorbed by index selling, not positioning. Flag: when QQQ 5-day return
  < −5% on day 0, halve size (recorded as a variant, not baked in).
- **Grading by price reaction, not by surprise:** if the DOWN is a beat that sold off on guidance, fine; if it is
  an EPS miss already pre-announced, the "broken" narrative was broken weeks earlier and there is no crowd to unwind.
  Cross-check with Finnhub `epsActual/epsEstimate` sign as a recorded covariate.
- **Borrow recall** mid-trade: cover on flag flip; counts as a cost event.

### 1.12 The FINANCING_SHADOW candidate — measured, and the sign is wrong
Runway PIT from companyfacts (320 sampled DOWN issuers, small/micro/mid, 1,095 legs with facts filed before day 0):
`liquid = latest CashAndCashEquivalents (+ ShortTermInvestments at the same period end)`, `burn = −FY OCF` from the
latest 10-K filed before day 0, `runway_quarters = liquid / (burn/4)`; shelf = any S-3 in the prior 3 years;
recent offer = 424B5/B4 in the prior 12 months. All by `filed < day0`, never by period end.

| cohort | n | mean signed 3d | t | sd | share of legs where the short lost >10% |
|---|---|---|---|---|---|
| **cash-generative** (FY OCF ≥ 0) | 833 | **+0.60%** | **+3.01** | 5.7% | 3.0% |
| burning (FY OCF < 0) | 262 | +0.34% | +0.52 | 10.6% | 11.8% |
| burning, **runway < 4Q** | 60 | **−0.03%** | −0.02 | **13.6%** | **20.0%** |
| burning, runway < 6Q AND S-3 shelf | 80 | +1.21% | +0.85 | | |
| burning AND 424B5/B4 in prior 12m | 122 | −0.05% | −0.04 | | |
| any S-3 shelf < 3y / none | 592 / 503 | +0.38% / +0.73% | +1.12 / **+2.78** | | |

The financing-dependent cohort has **zero mean and 2.4× the dispersion**: a bad print in a name with <4 quarters of
cash is a coin flip between "the raise is priced tomorrow" and "the raise/partnership/short-squeeze is announced
tomorrow". One in five of those legs costs a short more than 10% in three sessions. That is exactly the cohort a
short seller must refuse in shares — and it is *not* where the drift is. The drift is in profitable companies
whose holders were positioned wrong. Sample is small (60 / 80 legs) and the interaction with a shelf (+1.21%,
t 0.85) is unresolved, not refuted; but nothing in it says "build FINANCING_SHADOW first". Recorded as
`DEPRIORITIZED` with n, not `MECHANISM_REJECTED`. Full-universe re-run is in the backtest plan (1.14).

### 1.13 Stock vs option expression
- **Short shares** whenever: ETB, price ≥ $5, dv ≥ $10M, FY OCF ≥ 0 or runway ≥ 8Q. Cost 15–45 bp round trip; the
  edge survives. This is the default and covers ~76% of the cell (cash-generative share of legs with facts).
- **Put spread** (long ATM / short ~−8% put, first weekly expiry ≥ 5 sessions out) ONLY when the name is in the
  binary cohort (runway < 4Q, or a 424B5 in the prior 12 months, or SSR with dv < $25M, or not ETB but optionable).
  Reason: the loss must be bounded where sd is 13.6%. Expectation is negative-to-flat: post-print IV crush costs
  more than the +0.0% drift, so the put spread in that cohort is *insurance the strategy does not buy* — it is
  listed so the refusal is explicit. Never a naked put for a 3-session drift; the repo's own finding is that
  "in options none of it survives".
- Never short a name into its own next catalyst window (PDUFA, readout, lock-up expiry) — that is the
  optionality trade of §2, and a short seller wants no part of a binary in either direction at 3 sessions.

### 1.14 Backtest plan on this repo's data
`python -m scripts.pead_broken_narrative --legs state/pead_wide_legs_v1.jsonl --universe latest` →
receipt `state/pead_broken_narrative_v1.json` with, mandatory: cell vs control by bucket/band/session/year/quarter;
two-way issuer×week t; matched-control paired mean and t; net-of-cost at 10/20/30/50 bp; SSR proxy (day-0 low vs
prior close ≤ −10%) with the +10 bp / 15 % non-fill haircut applied; ETB filter via `alpha.universe.load()`;
p1/p5/worst legs listed by symbol and date; the runway cohort re-run on the full universe (not a 320-issuer sample);
`--entry next_open` variant (needs bars, ~1 h) as the first receipt; `--placebo nonearnings` and `--placebo shift5`.
First line of the receipt: `RESULT: cell − control net, two-way t, n`.

### 1.15 Prospective shadow record
`state/shadow/broken_narrative/YYYY-MM-DD.jsonl`, one row per decided leg at 15:55 ET: symbol, day0, r0, prior print
date and r0_prev, dv_bucket, band, session, ETB flag, SSR flag (day-0 low ≤ −10%), runway_quarters + shelf flags
(PIT, companyfacts `filed`), cost model applied, decision `SHORT | CASH:reason`, entry price at day+1 open, exit
price and reason, signed net, control leg id — and the same row for every REFUSAL (a refusal is a finding). Frozen
policy hash on the first row; graded weekly by the same script; no row is ever rewritten.

---

## 2. ATTACK — "state-change optionality" is a call option you pay for with your own shares

The thesis: buy names with a large gap between the current state and a plausible future state (clinical biotechs,
SLDP, QUBT, SOC, AMSC, PRCH). The short seller's translation: you are long a call whose strike is the future state,
whose **time to expiry is the cash runway**, and whose **premium is paid in dilution** — and every time the option
is rolled, the strike moves and you own less of it. The question is not whether the transition can happen; it is
what the base rate is and who pays for the wait.

### 2.1 The premium, from EDGAR (companyfacts `EntityCommonStockSharesOutstanding`; submissions forms since 2023)

| name | shares outstanding, first → latest | × | shelf / take-downs since 2023 | cash+STI 30 Jun 2026 | FY2025 OCF | runway (Q) |
|---|---|---|---|---|---|---|
| **SOC** | 13.3M (Nov-23) → 191.9M (Aug-26) | **14.4×** | S-3 ×2, S-1 ×4, **424B5 ×9, 424B3 ×29** | $21.6M | **−$351.7M** | **0.25** |
| **QUBT** | 28.7M (Mar-21) → 226.3M (Aug-26) | **7.9×** | S-3/ASR ×3, S-1 ×4, 424B5 ×3, 424B3 ×3 | $954M | −$30.3M | 126 (raised it all at the top; FY25 revenue $0.7M) |
| BHVN | 68.2M → 151.0M | 2.2× | S-3ASR ×2, **424B5 ×11**, 424B7 ×4 | $268M | −$609.4M | **1.8** |
| NTLA | 67.7M → 140.1M | 2.1× | 424B5 ×5 | $438M | −$394.7M | 4.4 |
| ABSI | 92.6M → 171.6M | 1.9× | S-3 ×2, 424B5 ×6 | $201M | −$92.9M | 8.7 |
| AMSC | 27.6M → 48.4M | 1.8× | S-3/ASR ×3, 424B5 ×4, 424B7 ×2 | $144M | +$23.1M | generative |
| PRCH | 89.4M → 131.8M | 1.5× | S-3 ×3, S-8 ×5; **67 Form 4s since Aug-25** (to parse: sales vs grants) | $196M | +$66.4M | generative |
| KYTX | 43.2M → 61.8M (in 12 months) | 1.4× | S-3 ×2, 424B5 ×4 | $199M | −$153.7M | 5.2 |
| SLDP | 172.6M → 228.2M | 1.3× | S-3ASR, 424B5 ×2 | $243M | −$73.4M | 13 |
| AARD | 21.7M → 21.9M | 1.0× | 424B5 ×1 | $74M | −$54.2M | 5.4 |

Read the top row. **SOC has 14× the share count it had 33 months ago, 38 take-down/resale prospectuses, and $21.6M
of cash against $352M of annual operating burn — a quarter of runway.** The "future state" (production restart)
may arrive; the shareholder who bought the option in 2023 owns 7% of what he thought he owned of it. QUBT raised
~$1B by issuing 7.9× its shares — the transition it is selling (revenue $0.7M, OCF −$30M) has not begun, and the
cash is now the *only* thing the price is made of. Four of the ten (SOC, BHVN, NTLA, KYTX) have under six quarters
of runway at the reported burn: the next raise is inside the holding period of any "mid-to-long term" thesis, and
the market knows it — which is why the "gap between current and future state" is wide: **part of the gap IS the
expected dilution.**

### 2.2 The base rate of the transition is lower than the narrative implies
- **Clinical-stage:** industry phase-transition base rates (BIO / Informa / QLS, 2011–2020, ~12,700 transitions):
  Phase I → approval **7.9%**, Phase II → approval **~15%**, Phase III → approval ~55%; Phase II → III 28.9%.
  A "plausible future state" for a Phase II asset is a 1-in-7 event, and the raise before the readout is ~1-in-1.
  The list's biotech names (KYTX, ABSI, NTLA, AARD, BHVN) are mid-clinical: annual dilution 20–50% (KYTX +43% in
  one year, BHVN +48%) against a ~15% terminal probability.
- **Survivorship in the list itself** (`FINDING_2026-08-26_MURATS_LIST_GRADED.md`): the watchlist's +47% mean
  **matched XBI (+55.9%)**; the *portfolio* median was **−15.2%**; the five biggest losers (APLT −88, SLDP −66, QS
  −65, KLAR −61, TVRD −55) are all state-change stories. Names with >200% "analyst upside" — the widest
  state gaps — were the distress markers (APLT, TVRD, ATYR, AARD, SOC all negative). Spearman(upside, realised) = 0.017.
- **The parent farm's own result:** an extreme screen value in a small name "selects the sick, not the cheap"
  (`value_bm` monotone in the wrong direction, −0.90). A large state gap is an extreme screen value.
- **Time is not free for the long.** In the legs file the burning cohort's post-print sd is 10.6% vs 5.7% for the
  generative cohort: the optionality book's variance is bought, not earned, and a book with 58% in two such
  names (SLDP + DKNG today) carries a stress charge the admission controller would refuse.

### 2.3 What would rescue the thesis (so the attack is falsifiable)
It survives only as a **portfolio of many small, uncorrelated options with the premium measured**: ≥20 names,
≤3% each, entered *after* a raise (runway ≥8Q, no 424B5 in 12 months), each with a dated checkpoint, benchmarked
against XBI/ARKK not SPY, and graded on `return − sector beta − dilution`. Held as five names at 58% concentration
with runways of 0.25–5 quarters, it is a levered short-vol position on financing windows, and the counterparty is
the S-3.

---

## 3. VERDICT — $100k paper tomorrow

**Short:** the `BROKEN_NARRATIVE_SHORT_v1` queue — every small/mid-cap name that prints DOWN ≥3.5% on 26 Aug amc /
27 Aug bmo whose previous 8-K 2.02 print was UP ≥3.5%, ETB, price ≥ $5, FY OCF ≥ 0 or runway ≥ 8Q; short shares at
the 27/28 Aug open, $4k each, ≤5 names/day, ≤$40k gross, cover at the third close or +8% adverse or a new 8-K;
expected +0.4–0.6% net per leg on the file's numbers, two-way t 2.3, 10 of 11 quarters positive. The names come
from `scripts/candidates.py` run against the calendar — I will not name tickers I have not run the filter on.
**Refuse:** (i) any name with <4 quarters of runway or a 424B5 in the last year — measured mean 0.0%, sd 13.6%, one
leg in five costs >10% (SOC-class); (ii) Murat's holdings as a revenge trade — §2 attacks the *long's* expected
value over quarters, not a 3-session short signal, and shorting a burner into a possible raise is the same coin
flip from the other side; (iii) mega-caps (cell mean +0.03%, n=55) and NVDA into its print (0/8 straddle backtest
says the chain already overprices it); (iv) any name not `easy_to_borrow` — no fee rate exists on paper, so a paper
P&L on it would be fiction; (v) the UP-side reversal (−0.87% small, t −3.6) is real but lives in the smallest,
widest-spread names on SSR — a v2 candidate, not tomorrow's trade.
