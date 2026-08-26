# AGENT 9 — PORTFOLIO ADVERSARY: Murat's book, 25 Aug 2026 weights

Receipt: `state/agents_2026-08-26/portfolio_factor_decomposition.json`
(script: `state/agents_2026-08-26/agent9_analysis.py`; bars:
`state/agents_2026-08-26/factor_bars.json`, Alpaca SIP daily closes from
2024-01-02, pulled 2026-08-26). Factor window 2025-02-14 → 2026-08-25, 383
sessions (bounded by AARD's listing). Sizing window 2025-08-01 → 2026-08-25,
268 sessions. Log returns; no costs (a static book, so costs are not the
argument).

Book: SLDP 30.1 · DKNG 27.8 · HUBS 7.8 · BHVN 5.7 · AMSC 4.6 · KYTX 4.6 ·
PRCH 4.3 · NTLA 4.2 · ABSI 3.8 · QUBT 2.8 · AARD 2.6 · SOC 1.6 (≈$176k).

---

## 1. FACTOR DECOMPOSITION

Six orthogonalised factors: MKT = SPY; SMB = IWM residual on SPY; BIO = XBI
residual on SPY; GROWTH = ARKK residual on SPY; RATES = TLT; CREDIT = HYG
residual on SPY+TLT. Loadings per name (daily OLS, annualised vol):

| name | w% | MKT | SMB | BIO | GROWTH | RATES | R² | vol | idio vol |
|---|---|---|---|---|---|---|---|---|---|
| SLDP | 30.1 | 1.93 | 2.21 | −0.53 | 1.14 | −0.70 | 0.29 | 98% | 82% |
| DKNG | 27.8 | 1.04 | 0.32 | −0.08 | 0.46 | −0.32 | 0.19 | 52% | 47% |
| HUBS | 7.8 | 1.11 | −0.27 | −0.27 | 0.55 | 0.32 | 0.13 | 66% | 61% |
| BHVN | 5.7 | 1.47 | 0.41 | 1.54 | 0.11 | −0.47 | 0.26 | 92% | 79% |
| AMSC | 4.6 | 2.57 | 2.24 | −0.48 | 0.60 | −0.57 | 0.40 | 85% | 66% |
| KYTX | 4.6 | 1.73 | 1.04 | 1.36 | 0.53 | −0.44 | 0.29 | 100% | 84% |
| PRCH | 4.3 | 2.07 | 0.82 | −0.48 | 0.80 | 0.44 | 0.19 | 100% | 90% |
| NTLA | 4.2 | 1.71 | 1.33 | 1.05 | 1.07 | −0.87 | 0.35 | 99% | 80% |
| ABSI | 3.8 | 2.13 | 1.01 | 1.00 | 1.04 | 0.36 | 0.40 | 96% | 74% |
| QUBT | 2.8 | 2.74 | 1.91 | −0.09 | 1.30 | −0.74 | 0.36 | 108% | 87% |
| AARD | 2.6 | 1.82 | 0.30 | 0.84 | 0.08 | 1.54 | 0.12 | 131% | 122% |
| SOC | 1.6 | 1.42 | 0.27 | −0.64 | 0.50 | −0.47 | 0.05 | 144% | 140% |

**Book effective betas:** MKT **1.63** · SMB **1.10** · GROWTH **0.74** ·
BIO **−0.003** · RATES −0.34 · CREDIT −1.00 (CREDIT is noise: HYG-residual
has tiny variance, hence the huge per-name coefficients and 0.2% of book
variance). Simple betas of the book's daily return: 1.60 to SPY, 1.54 to IWM,
0.86 to ARKK; **downside beta to SPY 1.46 vs upside 1.28** — it falls harder
than it rises.

Two things the reviewer's framing gets wrong:

1. **This is not a biotech book.** The five biotechs' +BIO loadings (BHVN
   1.54, KYTX 1.36, NTLA 1.05, ABSI 1.00, AARD 0.84) are exactly cancelled by
   the negative BIO loadings of SLDP, AMSC, PRCH, SOC, HUBS. Net BIO beta is
   zero and BIO explains **0.0%** of book variance. The `bio_residual` work
   measured the right thing on the wrong 21% of the book.
2. **The dominant factor is not the market either; it is one idiosyncratic
   position.** Book vol 48.9%/yr. Factor share 61% (MKT 34%, GROWTH 15%, SMB
   6%), idiosyncratic 39% — and **66% of the idiosyncratic variance is SLDP
   alone** (DKNG 18%). SLDP's total risk contribution is **50.1%** of book
   variance on 30.1% of weight; SLDP+DKNG = 66%.

**How many independent bets?**

| measure | value | reading |
|---|---|---|
| eigenvalues of the 12×12 correlation matrix | 3.27, 1.34, 1.16, 1.01, 0.94 | PC1 = 27% of variance; mean pairwise ρ 0.19 |
| effective N, equal-weight correlation view | **7.8** | the *names* are reasonably distinct |
| weight Herfindahl 1/Σw² | 5.3 | |
| effective N, **weighted** covariance (Σλ)²/Σλ² | **1.85** | the *book* is two bets |
| top eigenvalue share, weighted covariance | **71.4%** | |

The selection has ~8 degrees of freedom; the sizing collapses them to fewer
than two. Independence was bought and then thrown away.

What PC1 of the twelve actually is: correlation 0.82 with ARKK, 0.76 with IWM,
0.71 with QTUM, 0.65 with XBI, 0.64 with SPY, 0.05 with TLT. It is
**speculative small-cap growth**, and the top PC1 loaders are AMSC 0.37, ABSI
0.35, QUBT 0.35, NTLA 0.34, SLDP 0.34 — the biotechs and the non-biotechs sit
on the same axis. Highest pairwise correlations: SLDP–AMSC 0.44, SLDP–QUBT
0.40, NTLA–ABSI 0.40, AMSC–PRCH 0.39, SLDP–NTLA 0.38. SLDP–DKNG is only
0.16, which is the one genuine diversification in the book, and it is between
the two positions that together lost the most money.

Conditional correlation does **not** spike: mean pairwise ρ is 0.19 overall,
0.18 on SPY's worst decile, 0.16 on IWM's worst decile. The joint-scenario
risk here is not contagion between names; it is that eleven of twelve carry
β_MKT ≥ 1.0 and β_ARKK ≥ 0.5 at the same time. Linear exposure, not
correlation breakdown, is what kills this book.

---

## 2. JOINT CATASTROPHE

Shocks are pushed through the raw-ETF loadings (SPY, IWM, XBI, ARKK, TLT;
`raw_etf_loadings` in the receipt — collinear, so read only the book totals,
not the per-ETF coefficients). Calibration check first: the **Apr-2025
de-rating** (2025-02-19 → 2025-04-08: SPY −18.8%, IWM −22.6%, XBI −24.6%,
ARKK −38.4%, TLT +0.8%) — model says **−35.4%**, the book at today's weights
actually did **−38.0%**. The model under-states by ~3 pts; treat every figure
below as a floor.

**S1 — Biotech funding window shuts + rates up** (XBI −35%, TLT −12%,
SPY −8%, IWM −15%, ARKK −20%; the 2021-H2 shape at half its length):
**book −19.2%.** Per name: ABSI −50%, KYTX −48%, AARD −48%, BHVN −48%,
NTLA −43% — the five biotechs lose half — but they are 20.9% of the book, and
SLDP (−11%) and DKNG (−7%) barely notice. This is the scenario the reviewer
worried about and it is the *mildest* of the three. The biotech thesis is
sized small enough that its own catastrophe is a bad quarter.

**S2 — Single-name blow-up with 58% in two names.** Observed already inside
the data: SLDP worst day **−20.7%** (2025-11-06; that day was the book's worst,
−11.5%), worst 5 days −31.9%, max drawdown since Jan-2024 **−76.5%**. DKNG
worst day −13.5% (2026-02-13), max drawdown −61.3%. Modelled:
- SLDP −60% idiosyncratic (a failed cell qualification / dilution):
  **−18.1%** direct. Spill through other names' residual betas on SLDP's
  residual is **0.0%** — AMSC +0.15, NTLA +0.17, QUBT +0.14 are offset by
  BHVN −0.23; the spill is genuinely nil, which means there is no defence in
  the other eleven either.
- DKNG −40% (a tax/regulatory print; it has done −13.5% in a day):
  **−11.1%**.
- Both in the same month: **−29.2%**, with the market flat.
A pre-tax-lot rule of thumb: every 10% SLDP moves is 3.0% of Murat's net
worth, every 10% DKNG moves is 2.8%. Those two numbers are the portfolio.

**S3 — Growth de-rating.** Apr-2025 replay: **−35.4% modelled / −38.0%
realised** (above). A 2022-style bust (SPY −20%, IWM −25%, XBI −45%,
ARKK −60%, TLT −20% — Nov-2021 → Jun-2022): **book −50.2%**; every name
except SOC (−20%) loses 31–78%, ABSI −78%, NTLA −69%, KYTX −68%, QUBT −68%.
And it has already rehearsed: the book's worst realised 20-day window in the
factor sample is **−27.0%** (Nov 2025), when SPY was −4%, XBI **+1%**,
ARKK −19%, QTUM −13%, AMSC −50%, QUBT −39%, SLDP −20%. Biotech was flat and
the book lost a quarter — which is the empirical version of section 1: the
axis is speculative growth, not biotech.

Historical 1-day 99% VaR at these weights: −7.3%; daily σ 3.1%; five worst
days −11.5 / −8.3 / −7.9 / −7.6 / −7.2%.

---

## 3. SIZING VERDICT — is selection better than sizing?

Same twelve names, 2025-08-01 → 2026-08-25, $1 start. Inverse-vol weights
use the PRIOR year (2024-08 → 2025-07) so they are PIT. Buy-and-hold (B&H)
starts at the stated weights; constant-mix (CM) rebalances to them daily
(costless — an upper bound).

| weighting | B&H terminal | B&H max DD | B&H daily σ | CM terminal | CM max DD | CM daily σ |
|---|---|---|---|---|---|---|
| (a) actual weights | **0.898** | −50.9% | 3.66% | 1.016 | −43.6% | 3.02% |
| (b) equal 1/12 | **1.097** | −46.1% | 3.36% | 1.240 | −38.3% | 2.92% |
| (c) inverse-vol | **1.019** | −44.6% | 3.13% | 1.127 | −36.2% | 2.64% |
| actual weights ex-SLDP/DKNG (renormalised) | 1.208 | −43.5% | 3.44% | | | |
| SLDP+DKNG only (30.1/27.8) | 0.674 | −65.5% | 4.75% | | | |
| implied 2025-08 start weights if today's are pure drift | 0.682 | −55.1% | 3.47% | | | |

Benchmarks over the same window: **XBI 1.977**, IWM 1.407, SPY 1.246,
ARKK 1.214. Single names: ABSI 3.32, KYTX 2.57, PRCH 1.42, NTLA 1.18,
BHVN 0.98, SLDP 0.75, AARD 0.60, DKNG 0.59, QUBT 0.57, AMSC 0.55,
HUBS 0.48, SOC 0.16.

Reading:

- **The reviewer is right that sizing is worse than selection — but both
  lose.** Equal weight beats the actual weights by 20 pts of terminal wealth
  (1.097 vs 0.898) at *lower* vol and *lower* drawdown; inverse-vol beats
  actual on every column. The two names given 58% of capital returned
  0.674 together; the other ten, at their own relative weights, returned
  1.208. The sizing rule, whatever it was, put the most money in the two
  worst risk-adjusted positions (DKNG alpha −55%/yr, SLDP idio vol 82%).
- **Selection is not good either, only less bad.** Equal-weight 1.097 loses
  to SPY (1.246), IWM (1.407) and XBI (1.977). Eight of twelve names lost
  money in a year when every relevant index made 21–98%. Median name 0.60.
  The whole positive return is ABSI + KYTX, at a combined 8.4% of the book.
- **The "selection" that worked was on the biotech side and it was sized
  smallest.** The four biotechs that beat XBI were 1.2%–2.4% each at the
  start of the window (implied start weights: KYTX 1.2%, ABSI 0.8%, NTLA
  2.4%). They are 4–5% now only because they tripled. If the stated weights
  are pure drift from a year ago, the actual buy-and-hold path was **0.682**,
  −32% in a year the market made +25%.

Verdict on the question asked: sizing cost ~20 pts of terminal wealth versus
naive equal weight and ~12 vs inverse-vol; selection cost a further ~15–90
pts versus the indices. Fixing sizing alone would have turned a −10% year
into a +10% year and still trailed SPY by 15 pts.

---

## 4. ATTACK ON `alpha/admission.py`

What the four rules say about this book, mechanically (shares: `max_loss` =
notional, theta = 0, per-name σ = 63-day daily):

| rule | verdict on this book | verdict on the *same twelve at 1/12* |
|---|---|---|
| 1. free ≥ 10% under aggregate cap | REFUSE (100% notional in shares → free = 0) | REFUSE |
| 2. per-underlying ≤ 15% | REFUSE SLDP (30.1%), DKNG (27.8%) | pass (8.3%) |
| 3. theta burn ≤ 0.75%/day | pass (0) | pass |
| 4. Σ\|δ$\|·2σ ≤ 10% | **pass: 9.32%** | **REFUSE: 11.94%** |

Four defects:

1. **Rule 1 cannot admit any shares book.** `structure.max_loss` for a share
   leg is the notional, so a fully invested equity book sits at 100% "true
   max loss" against any aggregate cap < 100% and every order is refused.
   The rule is an options rule; applied to shares it is a permanent red line,
   and CLAUDE.md says what those teach a reader to do.
2. **Rule 4 prefers the concentrated book.** It is a sum of per-name
   *daily* sigmas, so it rewards putting 58% in the two lowest-σ names (SLDP
   3.9%/d, DKNG 3.8%/d) and punishes spreading into ABSI (7.6%/d), AARD
   (9.1%/d), SOC (12.8%/d). The book with effective N = 1.85 passes; the
   book with effective N = 7.2 is refused. A stress that ranks these two the
   wrong way round is not a floor on the stress, it is a sizing incentive
   in the wrong direction. It is also the wrong horizon: a one-day 2σ move
   is 9% but the 20-day realised worst was −27% and the Apr-2025 window
   −38%; the thing that hurts is a month, not a day.
3. **Rule 2 only sees names.** After SLDP and DKNG are cut to 15% each and
   the surplus redistributed, per-name passes, rule 4 passes at ~10%, and the
   book still has β_MKT ≈ 1.7, β_ARKK ≈ 0.7 and a modelled 2022-style
   drawdown of ≈ −50%. Concentration in an underlying is caught;
   concentration in a **cause** is invisible.
4. **Nothing in the module knows what the twelve have in common.** Every
   one of them is the same trade: an unprofitable or pre-revenue company
   whose equity is a call option on cheap capital — solid-state batteries,
   sports-betting take-rate, gene editing, quantum, HTS wire, home-warranty
   fintech, an offshore driller. The measured evidence: eleven of twelve
   have β_ARKK ≥ 0.5, nine have β_MKT ≥ 1.4, PC1 correlates 0.82 with ARKK,
   and BIO nets to zero because the non-biotechs are anti-biotech but
   pro-growth. A per-name cap admits this book one name at a time, which is
   exactly the 25 Aug failure the module's own docstring describes for
   options, reproduced for shares.

**Proposed fifth admission test — COMMON-SHOCK LOSS (thesis concentration).**

Let `g` be the observable proxy for the book's own first principal component
(ARKK here; choose it as the ETF with the highest correlation to PC1 of the
post-trade book, recomputed monthly, so it is *derived* from the book rather
than assumed). Let β_i be each name's 250-day OLS beta to `g`, σ_g its daily
sigma, and H = 21 sessions. Then

```
L_cs(post-trade) = Σ_i  w_i · β_i · ( −2.33 · σ_g · √H )        (99% one-month move of the common factor)

REFUSE if  L_cs < −L_MAX,   with L_MAX = the profile's declared one-month
                             drawdown tolerance (balanced 15%, aggressive 25%).
Also report  N_eff = (Σλ)² / Σλ²  of  diag(w)·Σ·diag(w)  and REFUSE if N_eff < 3.
```

On this book: σ_ARKK = 2.68%/d, so the 99% one-month shock is −28.6%;
weighted β = 0.86; **L_cs = −24.6%** — refused at balanced, marginal at
aggressive. Using the book's own PC1 instead of ARKK: **−29.7%**. And the
number that proves the test is measuring something the other four cannot:
**equal-weighting the same twelve gives L_cs = −26.5% (PC1: −32.4%) — no
better.** Rules 2 and 4 would be satisfied by re-weighting; the common-shock
loss is not, because it is a property of *what was selected*, not how it was
sized. Only swapping names out of the growth axis (or adding a name with
β_g ≤ 0) moves it. N_eff catches the other half: 1.85 here, refused; 7.2
at equal weight, passed. The two together separate "too much in one name"
from "too much in one cause", which is the distinction the module currently
cannot make.

---

## 5. VERDICT

The book is not diversified across twelve names, twelve theses or even two
sectors; it is a 1.6-beta, 1.1-small-cap, 0.74-ARKK position wrapped around
one 30% idiosyncratic bet, with an effective N of 1.85 and 71% of variance on
its first eigenvector. The biotech exposure the reviewer measured nets to
**zero** at book level and its own catastrophe (S1) is the mildest scenario
at −19%; the real catastrophes are a growth de-rating (−35% modelled, −38%
delivered in Apr-2025, −50% in a 2022 replay) and the two-name blow-up
(−29% with the market flat), and both have partial rehearsals inside the last
twelve months (−27% in Nov-2025 with XBI flat). Sizing is provably worse than
selection — naive equal weight would have added 20 pts of terminal wealth at
lower vol and drawdown — but selection itself trails every benchmark by 15–90
pts, so "fix the sizing" is necessary and nowhere near sufficient. The parent
admission rules would refuse this book for the wrong reasons (a shares book
can never satisfy rule 1) and would admit its equal-weighted twin for the
wrong reason too, while rule 4 actively prefers the concentrated version;
none of the four can see that all twelve are the same option on cheap
capital. The common-shock test above puts a number on that (−25% to −30% per
99% factor month, unchanged by re-weighting) and is the one rule this book
would fail after every cosmetic fix.
