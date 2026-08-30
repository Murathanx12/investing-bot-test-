# NEXT SESSION FOR OPUS — 2026-08-30 (b) — MAKE THE BOOKS DECIDE, THEN BUILD THE ERA REPLAY

Written by Fable, Sunday 30 Aug ~15:00 SGT (02:00 ET). Monday's open is
31 Aug 09:30 ET = 21:30 SGT. Labor Day is 7 Sep, so 31 Aug is a normal session.
Five sessions left: 31 Aug, 1–3 Sep, 4 Sep until 11:00 ET.

Read first: `../aegis-finance/docs/AEGIS_VISION_2026-08-30_LOG_REVISION_ERA_REPLAY.md`
(Murat's new instruction, validated) and your own `REPLY_TO_FABLE_2026-08-30_OPUS.md`.

---

## 0. RESULTS SCOREBOARD (Sun 30 Aug 02:00 ET)

| | |
|---|---|
| fleet equity | **$570,801 of $600,000 = −4.87%** (hack1 99,250 · hack2 99,239 · hack3 91,107 · hack4 99,080 · hack5 91,419 · hack6 90,706) |
| orders since kickoff | hack1 2 · hack2 2 · hack3 24 · hack4 5 · hack5 8 · hack6 29 |
| sealed book 30 Aug | 151 names, **0 claims** (`CLAIMING` derived from CIs that all cross zero) |
| refusal counterfactual | hack1: 60 refused, 10 false refusals, NVDA long put +$1,767 refused; hack3/hack6 "gate is discarding edge" (edge on risk −0.19 / −0.42) — caveat: marks 0h old, i.e. bid-ask |
| best historical net | overnight EW top-200, CRSP 1993-2024, t +7.92 (a tilt, not a strategy) |
| independent selectors live | 1 (post_event_drift over HIGH_DISPERSION_US_v1; 64 printers declined, 12 candidates) |
| tests asked | T1 −, T2 table, T3 − (mirror: calendar), T6 below MDE, T12 running (87%) |
| LLM spend this weekend | ~$1.35 (classification) + ~$0.04 |
| **RESULT IMPROVEMENT** | **NONE on P&L.** Session 4 improved measurement and unblocked a fourth provider. |

## 1. SESSION 4 VALIDATED — what I checked and what I found

- CI green: run 33296336096 on `e5e64b5`. The budget-gate finding is real and
  the fix is the right shape (existing file wins; guard on archived docs paths).
  I confirmed `docs/BUILD1/` had 71 ledger rows and the move made `spent_usd()`
  read $0.00.
- Key: correct — I was wrong to call it truncated; two pastes existed.
- T3 mirror: the same-day pairing is the right null and the refusal to ship
  the hack6 shadow lane is correct. Keep both nulls in the receipt.
- T12: 56,000 / 64,525 labelled at 02:00 ET; the 90% gate is a few minutes
  away. Report it as pre-registered: `ev_real_*` vs `ev_all_20d` control,
  per-day terciles, BH-FDR q=0.10, and **the 5-day horizon first** (Tetlock's
  stale-news reversal is a one-week effect).
- Your commit-message correction (2,358 not 2,376) is noted; nothing to fix.
- One thing you did not do and I want done before Monday: **the catalyst
  calendar is empty** — `state/corpus/horizon_2026-08-29.json` has 0 watched
  events. Every "dated catalyst" rule (Murat's (d), convex ≥10 DTE, T5) is
  silently inert without it. Pull Finnhub earnings + FDA/PDUFA where present
  for the 94-name universe through 30 Sep before anything else in §2.

## 2. MONDAY — MAKE THE ENGINE DECIDE (P&L item, do first, ≤ 4 hours)

Murat's diagnosis is correct: the book cannot claim by construction. Fix by
ADDING a generator, not by loosening a gate. Nothing below touches the
GROSS / opening-range / convex guards.

### 2a. Second generator for `scripts/prediction_book.py`: `murat_rule_v1`

Licence `PRODUCT_EXPERIMENT`. Frozen contract before the first seal. Claims
`direction=up` when, on the sealed day, with PIT inputs only:

- (a) `target_ratio` = consensus target / last close ≥ 1.5 (Benzinga PT rows,
  90-day window, already in the panel — 14/20 of Murat's names pass);
- (b) rating ≥ 4.1 **only if** a same-day reading exists; else the rule runs
  without (b) and the row says so (`rule_variant: "a_d_e"`);
- (d) a dated catalyst inside 21 sessions (needs §1's calendar);
- (e) `drawdown_from_60d_high` ≤ −15%.

Size claim = `min(expected_abs_move_21d, 0.15)`. Every row carries the four
inputs so the grade can say WHICH clause was wrong. Grade at 5 and 21 sessions
like the other generator; the two generators sit side by side in one book so
Friday's autopsy can compare a rule that claims with a panel that does not.

### 2b. Let hack3 (THESIS basket) act on it

hack3 already runs the basket profile (3% risk per name, 36% aggregate, gross
cap 100%). Route `murat_rule_v1` claims into hack3's candidate list as a
`PRODUCT_EXPERIMENT` selector — **its own selector, not a weight in the
composite** (CLAUDE.md bottleneck rule). Entry **market-on-close** (the
overnight finding; `cls` must be submitted before 15:50 ET), never in the
09:30–09:45 range. Worst case, printed before you change anything:

```
n ≤ 12 names × ≤ 8.3% notional (gross cap 100% / 12) × 8% stop = −8.0% of equity
```

That is inside the −9% Monday-safety bound; do not raise any of the three
numbers. If the rule yields fewer than 3 names on Monday, the book holds
cash and the row says `REFUSED: fewer than 3 names` — a refusal is a finding.

### 2c. hack2 (DRIFT) takes the 12 post_event_drift candidates with the drift exit

It has placed 2 orders in a week. Check why: the log shows the council
declining 64 printers. Print the refusal-class histogram for hack2 alone
(`alpha/refusal_classes.py`) and fix the single biggest **book-state** class if
it is a mis-set input (it was `last_equity=0` once). If the biggest class is an
evidence class, leave it and say so.

### 2d. hack5 (CONVEXITY): close the break-even calls Murat agreed to close

Only if he confirms in chat. Otherwise leave.

### 2e. Seal Monday's book LOCALLY before 09:15 ET (Murat runs this)

`python -m scripts.prediction_book --seal` then `--verify`. Two generators
must appear in `generator`.

## 3. T12 → close it out (after the 90% gate)

Report per horizon (5d first), per tercile, with the withdrawn `ev_all_20d`
control on the same rows. If `ev_real_5d` or `stale_share_20d` clears BH-FDR in
ANY tercile: it becomes the third generator (`relevance_v1`) on Tuesday's
book — claim direction by the sign the panel measured, never by intuition.
If nothing clears: T12 is DEPRIORITIZED, and the encoding (not the corpus)
moves to §4's richer record.

## 4. T13 — THE ERA REPLAY (Murat's design, improved; build after §2)

Full spec in the Aegis vision addendum §3. Build order:

1. **`scripts/anonymise.py`** — one pass over the corpus with gpt-5-nano
   (`reasoning_effort="minimal"`, ≈ $2.40 for 80k rows). Output record:
   `{era_month, sector, size_bucket, event_type, is_new_fact, subject,
   expectation_gap, tone, summary_no_names}` + a **sealed side table**
   `company_id → ticker` that only the grader imports. Strip names with the
   alias table FIRST (regex, $0) so the model never sees them.
2. **`scripts/era_replay.py --designer`** — LLM-A writes the test file
   (universe rule, dates, cadence, allowed inputs, nulls, cost rate,
   objective) and it is hashed. LLM-A and LLM-B are different providers
   (designer = DeepSeek; decider = OpenAI or Featherless) so "independent" is
   literal.
3. **`--decide`** — LLM-B at each decision date sees: the window's bundle, its
   previous diary line, its previous weights. Returns weights (Σ ≤ 1,
   long-only), horizon, one reason per company_id, **and the canary answer:
   "what year is this, which companies?"** Sealed before grading.
4. **`--grade`** — code only. Terminal wealth vs the same-era equal-weight
   basket of the same names, costs per rebalance from the farm's rate. Three
   nulls: shuffled companies, shuffled dates within era, same-day paired.
   Report the year-identification rate BESIDE the wealth; if > 20%, the era is
   `NOT_BLIND` and the wealth number is not evidence.
5. **Eras and data:** 2025-26 = our corpus (run first, tonight); 2016-19 =
   pull Alpaca news history (`/v1beta1/news`, Benzinga, from 2015) for the 94
   names — new backfill flag `--start 2015-01-01`; 2010-13 = EDGAR 8-K ex-99.1
   + 10-K/10-Q only, prices from the Aegis farm's CRSP pull. Report per era.
6. **Cadence grid** {1w, 1m, 3m, 6m} × {diary on, diary off}. The diary is the
   variable that measures Murat's "keep it in memory."

Budget: ≤ $15 total across providers for the first full grid on the 2025-26
era; `spend.justify()` on every call. Do not run the 2010 era until the
2025-26 receipt shows the canary rate.

## 5. THE LIVE FUNNEL (after §4.1 exists — same encoder, today's news)

`scripts/premarket_digest.py` gains a numeric block built from §4.1's records
for the last 5 sessions: per name — `n_new_facts_5d`, `subject_share`,
`expectation_gap_mean`, `tone_mean`, `days_to_next_catalyst`. Then the four
questions Murat named, each as a RANKED LIST with the numbers beside the
names, not a paragraph: today's candidates · next-month candidates · dated
events inside 21 sessions · worries (names with negative expectation gap AND a
catalyst). The LLM writes the one-line reason; the numbers come from code.

## 6. Providers (unchanged) and one addition

DeepSeek default + fallback → Featherless → NVIDIA (embeddings; 429 for chat)
→ OpenAI (`gpt-5-nano` minimal for bulk, `gpt-5-mini` for the decider). HF
OFF. Local llama OFF — anonymisation at $0.03/1k items is cheaper than the
laptop's time. Register `openai` in the probe order behind DeepSeek so the
loops can fall through to it.

## 7. What NOT to do

- No new guard unless a failure shows it is needed.
- No change to `GROSS_NOTIONAL_CAP`, notional caps, stops, opening range.
- No deploy without `python -m scripts.fleet --check-all` green and the
  worst-case line printed in the commit message.
- Do not pool eras, do not pool horizons, do not read a verdict off a partial
  label set (you already caught yourself on this — keep the gate).

## 8. Order of work

1. Catalyst calendar (§1) → 2. `murat_rule_v1` generator + hack3 routing (§2a-b)
→ 3. hack2 refusal histogram (§2c) → 4. T12 report (§3) → 5. anonymiser
(§4.1) → 6. era replay on 2025-26 (§4.2-4, 4.6) → 7. funnel block (§5) →
8. 2016 backfill (§4.5). Handoff opens with the scoreboard in §0, updated.
