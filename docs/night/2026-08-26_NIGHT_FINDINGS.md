# NIGHT LAB 2026-08-26 — findings (LLM spend: $0.00; every test below is bars + arithmetic)

Boundary: `python -m scripts.night_guard` PASS. Nothing in `alpha/` changed; both loops (PIDs 3896, 31428)
ran untouched on their 26 Aug code. Night wrote only `state/night_shadow/`, `docs/night/`, `scripts/night_*.py`.

Each test was chosen because it could change a decision. Here is the decision each one changed.

## 1. DYNAMIC_RESIDUAL_PAIR_v1 — **do not build the pair executor** (`scripts/night_pair_regrade.py`)

The remnant of the whole-market PEAD was "short the ≥5% loser / long IWM, +0.35%, t~2". Re-graded in the
units the trade pays — simple returns, entry at the NEXT OPEN, 30 bp round trip on the stock + 4 bp on the
ETF, two-way clustered — on 5,923 legs:

| expression | mean | t iid | t two-way | t by quarter |
|---|---|---|---|---|
| unhedged short, simple, gross | +0.015% | 0.15 | 0.07 | 0.06 |
| unhedged short, net 30 bp | **−0.285%** | −2.71 | −1.29 | −1.02 |
| pair vs IWM 1:1, gross | +0.291% | 2.86 | 1.71 | 1.61 |
| **pair vs IWM 1:1, net 34 bp** | **−0.049%** | −0.49 | −0.29 | −0.27 |
| pair vs IWM, beta-scaled, gross | +0.261% | 2.58 | 1.72 | 1.46 |
| pair vs QQQ 1:1, gross | +0.618% | 5.98 | 2.92 | 3.10 |

Net pair by quarter: **7 of 11 negative** (2024Q3 −0.83%, 2026Q1 −0.99%, 2026Q3 −0.23%). By bucket the
net pair is ≤ +0.10% everywhere and negative in mid/large/mega. The only expression that clears costs is
"short loser / long QQQ" — and that is a statement about QQQ's 2024-26 tape, not about the loser
(`docs/FINDING_2026-08-26_PEAD_ADVERSARIAL.md` §1). **Decision: no pair engine. The whole-market PEAD family
is RETIRED_FROM_CURRENT_SEARCH as an expression; the attention placebo (§3) decides whether it survives as a
MECHANISM.**

## 2. TIMEZONE_LEAD_v1 → NIKKEI_ADR_FADE_v1 — a real regression, a regime as a trade (`scripts/night_timezone_lead.py`)

Question: does the Asian session lead the US session of the ADR and its customers? Regress the US
open→close on the same-date Asian session return, then add the rivals one at a time.

- **Taiwan/Korea → TSM, SMH, SPY, MU: the "lead" was the prior US session's own reversal.** Given the gap
  alone Asia carried t −2.9 to −4.0; given the gap AND the previous US close→close and open→close it is
  t −0.1 to −1.3. The Lou-Polk-Skouras intraday/overnight tug of war explains it. Dead.
- **Nikkei → every Japanese ADR survives every rival.** Given gap + prior US session + USDJPY + the parent's
  own Tokyo return: SONY b −0.155 (t −5.9), HMC −5.8, TAK −5.6, TM −5.2, MFG −4.0, NMR −3.0, SMFG −2.6,
  MUFG −2.1; the country ETFs EWJ/DXJ/BBJP weaker (−0.8 to −2.7). The Nikkei itself mean-reverts the next
  Tokyo session (b −0.099, t −2.6, 2023-26), so the ADRs' US session is **pricing tomorrow's Tokyo reversal**
  before Tokyo opens. Not FX (b_fx ~0). Not the parent (given the parent, the index effect is stronger).
- **As a trade it is a regime.** EW basket of the 8 ADRs, opposite the Nikkei, US open→close, 5 bp:

  | threshold | n (5y) | mean net | t | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
  |---|---|---|---|---|---|---|---|---|---|
  | 1.5% | 269 | +0.08% | 1.25 | −0.26% | −0.19% | −0.03% | +0.04% | **+0.52%** | +0.21% |
  | 2% | 148 | +0.15% | 1.40 | −0.29% | −0.41% | +0.04% | +0.01% | **+1.04%** | +0.22% |
  | 3% | 47 | +0.62% | 2.18 | — | −0.17% | — | +0.11% | +2.02% | +0.37% |

  The 3-year regression (t −5.6) was 2023-26; the 5-year trade is 2025-26 with 2021-22 negative and the
  April-2025 tariff days carrying the sum. The long-after-Nikkei-down side (+0.27%/trade at 2%) is
  consistently better than short-after-up (+0.04%). **Decision: DEPRIORITIZED as a lane; kept as a shadow
  quote (`docs/night/2026-08-26_STRATEGY_MARKET_DESIGN.md` §4) because the regression is the strongest
  non-price-history structure found tonight and it costs nothing to record.** Lesson filed: the 3-year t
  of −5.6 would have been believed; the 5-year window said 2021-22 were the other sign. Sample the window
  before believing the t.

## 3. ATTENTION_AFTERSHOCK_v1 — the attention rival is REFUTED; the mechanism is information (`scripts/night_attention_placebo.py`)

104,675 sessions with |log move| ≥ 5% in the same universe since 2024-02-26; 10,813 are 8-K 2.02 prints, the
rest are ≥ 5 sessions from any print. Same statistics on both (signed = in the day-0 direction, two-way t):

| DOWN ≥ 5% | n | gap after day 0 | day+1 open→close | raw 3d | raw 21d | excess 3d | excess 5d | short net 30 bp |
|---|---|---|---|---|---|---|---|---|
| **print** | 5,467 | −0.13% | **+0.16%** | +0.22% | −0.79% | **+0.66% (3.3)** | +0.70% (2.5) | −0.24% |
| **non-print** | 46,361 | +0.03% | −0.17% | **−0.37%** | **−2.14%** | +0.01% (0.0) | +0.02% | −3.52% |
| print − non-print | | −0.16% (t −4.3) | +0.33% (t 4.7) | +0.58% (t 5.0) | +1.35% (t 5.2) | +0.65% (t 5.9) | +0.68% (t 5.0) | |

A non-print 5% loser **bounces** (+0.37% raw over 3 sessions, +2.1% over 21) and shorting it costs −3.5%
net (squeeze tail). A print loser does not bounce — it holds its new level while the index rises. So the
post-print "detachment" is NOT a big-move/attention artefact: **the print is what stops the bounce**, which
is the information story (the drop was deserved) and the falsification agent 7's rival needed. UP side: print
winners trail QQQ (−0.42%, t −2.0) while non-print winners do not (+0.02%) — same asymmetry.
**Decisions:** (1) the wide PEAD survives as a MECHANISM for Psychohistory ("a print resets the level; a
non-print shock reverts") while remaining untradeable as an unhedged expression (§1); (2) the cheap new
candidate is the OTHER cell — the non-print ≥ 5% drop's bounce, +0.37%/3d raw on 46k events — and it goes
through the same battery tomorrow (simple returns from the next open, costs, per quarter, bucket) before
anyone quotes it.

## 4. SELECTION_PROVENANCE_v2 — the review was right: the documents carried rank information (`scripts/night_selection_provenance.py`)

52 of the 61 picks have document features (`upside` = analyst target gap, `rating`, colour mark) and bars
as of 2025-11-07; excess = forward return minus the pick's dv-bucket mean (2,824 controls). Medians: upside
0.43, 60d vol 0.69, drawdown from 252d high −0.28.

| cell (upside × vol × drawdown) | n | exc 21d | exc 63d | exc 126d | names |
|---|---|---|---|---|---|
| **hi upside, hi vol, deep dd** | 15 | +19.5% | +5.4% | +12.3% | ABSI ACVA AMSC BEAM BHVN ELF MP NTLA … |
| **hi upside, lo vol, deep dd** | 7 | +17.8% | **+50.6%** | +35.4% | ALMS BMRN CRSP DKNG HUBS MRNA MSTR |
| hi upside, hi vol, shallow | 3 | −24.5% | −24.3% | −43.5% | IMNM KYTX ORCL |
| lo upside, hi vol, shallow | 6 | −30.1% | −40.9% | −26.4% | AMPX BE CYTK QS **SLDP** TVTX |
| lo upside, hi vol, deep | 2 | −12.7% | −49.3% | −54.7% | QBTS RGTI |
| lo upside, lo vol, shallow | 16 | +0.9% | −4.7% | +7.1% | AMD AMZN AVGO … |

Marginals (hi − lo, 63d / 126d): **upside +33% / +20%, rating +29% / +24%**, vol −23% / −22%, drawdown
(deep − shallow) +25% / +17%. Colour mark: **green +29% (n 19) vs unmarked −18% (n 27)** at 63d.
v1 said "a volatility screen with no rank edge". Within the list, the DOCUMENT rule — high analyst upside
AND a deep drawdown — is the population that worked (22 names, both vol halves), and high vol WITHOUT
upside is the one that lost (SLDP, QS, AMPX, RGTI, QBTS: −26% to −55%). Volatility was the strongest
feature separating picks from controls; it was not the rule that separated winners from losers inside the
picks. n = 52, one as-of date, no multiplicity control — a hypothesis with a shape, not a claim.
**Decision:** build `STALE_TARGET_v1` / `CONSENSUS_BREAK_v1` as the next selector candidate — analyst
upside × drawdown on the WHOLE universe with target ages (needs a targets feed; Finnhub `price-target` is
the cheap probe), and re-run this scan at three more as-of dates before it is quoted. Also: the current
book's two largest weights, SLDP and DKNG, sit in opposite cells (−41% / +51%); the analysis says the
sizing is inverted relative to the rule that generated the list.

## 5. External projects (`docs/night/2026-08-26_EXTERNAL_PROJECTS_DIGEST.md`)

Nine repos cloned to `C:\Users\mrthn\reference-codes\trading-agents\`. None evidences alpha. The one controlled
multi-model contest (1rok, Jan–May 2026) put GPT-5.5 at +26.35% vs NDX +17.00% and **DeepSeek V4 last at
+6.92%**; picks converged (KO in 6 of 7 books) and the divergence was a SIZING LABEL that code turned into
weight. The projects that survived a broker moved all arithmetic out of the LLM. Real losses came from
order-lifecycle bugs (DAY-TIF stop children expiring at 16:00, selling into own bracket children, `int(qty)`
→ 0, double-fired exits) — audited against our surface in `docs/night/2026-08-26_EXECUTION_AUDIT.md`.
