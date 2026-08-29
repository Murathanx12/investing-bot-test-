# FINDING 2026-08-29 — BLINDED NEWS HAS NO DIRECTION; DATED EVENT COUNTS DO

**Licence:** PRODUCT_EXPERIMENT (one run each, no multiplicity control). Not a
claim. Receipts: `state/tournament/receipt_20260829T_blind120.json`,
`state/corpus/features/ic_2026-08-29.json`, `state/corpus/features/build_receipt.json`.

## 1. The blind tournament (T1) — Murat's own protocol, re-run

Strip the company name, ticker, other tracked tickers, product codes, prices
and move-percentages from 30 days of a company's news; ask an LLM for the
direction and size of the next 21 sessions; seal; grade against the next-open
→ 20-sessions-later close (SIP, adjusted); compare with 200 shuffles.

- 231 cells (21 names × 11 month-ends, 2025-09 → 2026-07), 38 thin (<5 rows —
  SPY has **zero** corpus rows, so the control never ran); 120 asked, 120 sealed,
  0 refused, 110 graded. Provider: Featherless Qwen2.5-72B for all 120 (kimi
  was down). 221k tokens, 28 min.
- **Identification 0/120** (one guess, wrong); 4 canary cells, 0 identified.
  **The blinding holds.**

| | n | hit | null mean | p(hit) | IC | p(IC) | up-calls | down-calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| raw | 110 | 0.454 | 0.473 | 0.70 | −0.175 | 0.97 | +0.3% | +1.8% |
| vs SPY | 110 | 0.435 | 0.457 | 0.74 | −0.196 | 0.975 | −1.2% | +1.6% |
| vs sector ETF | 110 | 0.472 | 0.448 | 0.30 | −0.177 | 0.975 | −2.7% | −0.4% |

78 up / 30 down / 2 flat — a long bias. Confidence clumps at 0.70; the
high-confidence tercile (n=29) hits **0.28**. The IC sits at the 97th
percentile of the null on the LOW side (two-sided p ≈ 0.06): if anything the
blinded read is a weak anti-signal, the same shape as the Holm-surviving
"short-horizon winner-chasing is an anti-signal" (17-20 Aug) and AMNESIA-1's P5
(the masked LLM did not beat a 5-feature logistic).

**Verdict: NO INFORMATION.** Nothing about the protocol failed; the task is
what has no edge. A second family (hf_glm is live) is the cheap next run; a
larger n is not going to rescue an IC of −0.18.

## 2. The features panel — the same corpus as NUMBERS

`scripts/corpus_features.py`: 23 symbols, 2025-09-01 → 2026-08-28, 5,678
symbol-days; NVIDIA `nemotron-3-embed-1b` embeddings live (2048-d, 340 calls,
16,511 titles); Spearman IC vs forward returns (open t+1 → close t+h),
month-block bootstrap 90% CI.

| feature (20-day count) | IC 21d raw | 90% CI | IC 21d vs SPY |
|---|---:|---|---:|
| **ev_insider** (insider / stake / activist headlines) | **+0.140** | [+0.085, +0.204] | +0.148 |
| **ev_earnings** | +0.133 | [+0.022, +0.252] | +0.155 |
| ev_macro | +0.105 | [−0.009, +0.209] | +0.118 |
| ev_contract | +0.097 | [+0.001, +0.181] | +0.103 |
| ev_analyst_rating | +0.086 | [+0.012, +0.190] | +0.098 |
| n_target_notes_90d | +0.066 | [+0.007, +0.147] | +0.070 |
| ret_20d | −0.083 | [−0.170, +0.027] | −0.081 |
| novelty_5d | −0.070 | [−0.159, +0.009] | −0.089 |

Not carrying: `attention_z`, `sentiment_lex_5d`, `target_ratio`, `n_items_5d`,
`realised_vol`, `drawdown` — all |IC| ≤ 0.065 with CIs across zero.

## 3. What the two receipts say together

The LLM reading the prose of the news, blinded, has no direction. Counting
WHICH KIND of dated event happened (insider buying, a print, a contract, a
rating change) does, at +0.09 to +0.15 over 21 sessions on 4,451 symbol-days.
That is the cost rule of the VISION file measured: **code extracts the event
type; the LLM's narrative adds nothing a shuffle would not.** The premarket
digest's bets are narrative; the sealed book should be built from the event
panel first and use the LLM only for the causal-chain question.

Caveats that bind: 12 month-blocks; 21-day returns overlap; ~30 features
tested; the insider regex also matches "stake"/"activist"; the 20 names are
Murat's survivorship-shaped list plus SPY/QQQ/IWM with no corpus rows;
`days_to_next_catalyst` is null everywhere because every future row was
observed on 2026-08-29 (the calendar has no historical vintages — it starts
accruing them from today).

## 4. What follows (for the roadmap)

- T7 (live blind book) becomes a CONTROL beside the event-panel book, not a
  candidate.
- The sealed pre-open book's first numeric inputs: `ev_insider_20d`,
  `ev_earnings_20d`, `ev_contract_20d`, `ev_analyst_rating_20d`, `n_target_notes_90d`.
- T6 (rule cells) and T3 (sector lead) run on this panel next; T4 (coverage
  shock) needs the widened universe.
- Re-run T1 with hf_glm and with the SPY control once SPY rows exist.
