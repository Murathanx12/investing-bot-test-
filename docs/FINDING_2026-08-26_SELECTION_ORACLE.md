# FINDING — Murat's selection: high dispersion, no rank edge; the book is two bets; the biotechs are XBI beta with negative residual

Three measurements from the review's P3/P6 and the portfolio adversary (agent 9), plus the first ticker-blind
loser triage (P5). Receipts: `state/selection_oracle_2025-11-07.json`, `state/bio_residual_2026-08-26.json`,
`state/agents_2026-08-26/portfolio_factor_decomposition.json`, `state/state_change.jsonl`.

## 1. MURAT_SELECTION_ORACLE_v1 (`python -m scripts.selection_oracle`)

61 names from the Nov-2025 research list, as-of 2025-11-07, each against 40 controls drawn from the same
dollar-volume bucket of HIGH_DISPERSION_US_v1 (2,343 controls; liquidity-matched, NOT size-matched — the venue
carries no market cap). Paired on each pick's own controls:

| horizon | picks | controls | diff | median diff | t | pick percentile | beat controls |
|---|---|---|---|---|---|---|---|
| 1s | +2.0% | +1.2% | +0.8% | +0.5% | 1.62 | 0.57 | 59% |
| 5s | −5.0% | −1.5% | −3.6% | +0.9% | −1.38 | 0.45 | 46% |
| 21s | +5.2% | +3.3% | +1.8% | +0.8% | 0.50 | 0.51 | 56% |
| **63s** | +0.6% | +8.9% | **−8.3%** | **−14.3%** | −1.61 | 0.40 | **33%** |
| 126s | +11.5% | +15.2% | −3.7% | −8.1% | −0.61 | 0.47 | 43% |

No selection edge at any horizon; at a quarter the median pick trailed its own controls by 14 points. What IS
different, and measurable point-in-time: **the picks' pre-selection volatility is 72%/yr against 35% for the
controls**, and their 63-session outcome dispersion is 0.40 vs 0.25 (best +173%, worst −69%). The list was a
volatility screen with an analyst-upside label on it. Sizing: inverse-vol beat equal weight at every horizon
(+2.7% vs +0.6% at 63s) — the same message as the live book below.

Not run, and the receipt says so: SHAP over point-in-time features (no PIT feature panel on this machine; 61
rows cannot carry it) and the user's actual weights for the list (unknown).

## 2. BIO_RESIDUAL_MOMENTUM_v1 — the five biotechs against XBI

Daily residual = r − β·r_XBI, β fitted on the window:

| name | β (63d) | resid 63d | resid 126d | resid 252d | 25 Aug residual |
|---|---|---|---|---|---|
| BHVN | 1.37 | +2.9% | −18.6% | **−98.6%** | +0.9% |
| KYTX | 1.47 | −32.4% | −31.1% | −35.3% | +2.7% |
| NTLA | 1.76 | −35.2% | −44.3% | **−78.6%** | +2.1% |
| ABSI | 2.39 | +3.0% | **+75.8%** (t 1.2) | +2.1% | +1.5% |
| AARD | 1.04 | +29.9% | −96.9% | **−117%** | +2.2% |

Mean pairwise residual correlation 0.07 — after XBI they are five separate names, not one bet. But four of the
five carry large NEGATIVE residuals over 6-12 months: the basket is 1.4-2.0× XBI with negative stock-picking on
top. The 25 Aug outperformance the review noticed was one day.

## 3. The book (agent 9, `docs/agents_2026-08-26/agent9_portfolio_adversary.md`)

- Net XBI residual beta is **0.00** — the biotech loadings are cancelled by SLDP/AMSC/PRCH/SOC. The book is
  β_MKT 1.63, β_SMB 1.10, β_ARKK 0.74; **SLDP alone is 50% of variance**; effective N **1.85** (top eigenvector
  71%) against 7.8 for the same twelve names equal-weighted. Selection had ~8 degrees of freedom; sizing threw
  them away.
- 2025-08 → 2026-08: actual weights 0.898× (max DD −51%), equal weight 1.097×, inverse-vol 1.019×; SLDP+DKNG
  0.674×, the other ten 1.208×. XBI 1.977×, IWM 1.407×, SPY 1.246×. **Sizing is worse than selection and both
  lose to the benchmarks.**
- Modelled joint scenarios: Apr-2025 replay −35% (realised −38%), growth de-rating −50%, SLDP −60% + DKNG −40%
  in one month −29% with the market flat.
- The admission module (`alpha/admission.py`) would refuse this book for the wrong reason (rule 1 cannot admit
  any shares book) and admit its equal-weight twin for the wrong reason (the 2σ test rewards concentration in
  low-σ names). Proposed extra test: common-shock loss `L_cs = Σ w_i β_i,g (−2.33 σ_g √21)` on the book's own PC1
  proxy plus N_eff ≥ 3 — this book scores −24.6%, its equal-weight twin −26.5%, which is the point: re-weighting
  does not fix an axis.

## 4. Loser triage, ticker-blind (`python -m scripts.state_change triage`, SHADOW_ONLY)

The compiler sees the facts with the name removed and must answer THESIS_BROKEN / PRICE_OVERREACTION /
CANNOT_DETERMINE, with a 21-session falsifier:

| case | facts as of day 0 | answer | p_over | damage est | reaction ratio |
|---|---|---|---|---|---|
| HUBS 06 Aug (−19%, beat, light adds; outcome +17% by 25 Aug NOT in evidence) | | **PRICE_OVERREACTION** | 0.60 | −8% | 2.6 |
| DKS 25 Aug (−31%, guide −17%, core comps +4.9%) | | **PRICE_OVERREACTION** | 0.65 | −17% | 2.2 |
| HOV 20 Aug (−7.5%) | no balance sheet / unit economics in the facts | CANNOT_DETERMINE | — | — | — |
| OSIS 21 Aug (−5.4%) | same | CANNOT_DETERMINE | — | — | — |
| DKNG 07 Aug (−12%) | same (recovered — the compiler did not know) | CANNOT_DETERMINE | — | — | — |

Two things the design got right on the first run: the HUBS falsification case classified correctly from
day-0 facts only, and the compiler REFUSED three of five for lack of guidance/balance-sheet facts rather than
filling the gap with "what companies like this usually do" (DKNG would have been a correct guess; a guess is
not the product). The cost was $0.0025 for five. DKS resolves 24 Sep (`grade --id SC:TRIAGE:DKS:2026-08-25:5aff1c76 --move`).

## 5. What it means for the roadmap

- `STATE_CHANGE_OPTIONALITY_v1` (`alpha/state_change.py`, shadow) is built and the short seller's base rates are
  stated to the compiler as priors. It is NOT yet scored on the live names — the missing input is the same one
  the triage refused on: runway, dilution history and catalyst dates, which need the EDGAR XBRL companyfacts
  collector before the score means anything.
- The user's method is not "state-change" in the data; it is **volatility selection**. The state-change factor
  is still worth testing — but as a hypothesis about how to pick WITHIN the high-vol set, with the oracle as its
  matched-control harness, not as an explanation of past picks.
- For the real book the first-order fix is sizing (effective N 1.85); the second is the axis (all twelve are
  cheap-capital options). Both are admission questions, and the admission module needs the common-shock test.
