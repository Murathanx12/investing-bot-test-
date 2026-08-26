# FINDING — Murat's stock list, graded to today, and what its logic actually was

**Inputs:** `my stocks old.pdf` (7 Nov 2025: 13 portfolio + 48 watchlist names, price / analyst 12-month target /
consensus rating, colour-coded), `stocks.pdf` (9 Sep 2025 report), `stock (1).pdf` and `stock research .pdf`
(13 Jan 2026 follow-ups with prices, sales, and the LLM research write-ups behind the picks).
**Prices:** Alpaca SIP daily closes, 7 Nov 2025 → 25 Aug 2026. Receipt: `state/murat_list_2025-11_grade.json`.

## 1. How the list was built (reconstructed from the documents)

The method is an **analyst-consensus upside screen, LLM-assisted**: for each name the report quotes the
TipRanks/MarketBeat 12-month consensus target, computes "expected return" = target/price − 1, adds a
narrative of catalysts and risks, and rates it "high risk / high reward". The Nov list is then hand-curated:
green = conviction, yellow = speculative, red = analyst target BELOW price (MU, BE, QS, SLDP, MRNA).
The 13 Jan follow-up re-prices everything, records sales (TVTX at 34.4, ALMS at 10, SLDP at 8.1) and
claims "2025 +115%" for the portfolio.

The themes, whether or not they were named: **clinical-stage biotech catalysts** (~25 names), **AI hardware and
memory** (MU, MRVL, COHU, AMD, TSM, NVDA, AVGO), **crypto/quantum proxies** (MSTR, GLXY, QUBT, QBTS, RGTI),
**speculative energy/batteries** (SOC, SLDP, AMPX, QS), and a few large-cap growth names.

## 2. What happened, 7 Nov 2025 → 25 Aug 2026

| | n | mean | median | hit > 0 |
|---|---|---|---|---|
| **watchlist** | 48 | **+47.0%** | +32.5% | 69% |
| **portfolio** | 13 | +32.3% | **−15.2%** | 46% |
| green-coded | 25 | +58.6% | +39.7% | |
| red-coded (target < price) | 5 | **+153.9%** | +60.8% | |
| yellow (MSTR, APLT) | 2 | −67.7% | | |
| SPY / IWM / **XBI** | | +15.1% / +24.8% / **+55.9%** | | |

Top: MRNA +547%, ALMS +408%, MU +292%, RVMD +246%, ABSI +189%, MRVL +165%, KYMR +116%, COHU +112%.
Bottom: APLT −88%, SLDP −66%, QS −65%, KLAR −61%, TVRD −55%, RGTI −50%, MSTR −48%, AAPG −47%, HUBS −40%.

## 3. The logic, tested

1. **The screen's own variable had NO predictive rank.** Spearman(analyst upside, realised return) = **0.017**
   across 61 names. The consensus rating did a little better (0.23). Names with >50% "expected return"
   averaged +47.6%; names with ≤20% averaged +27.1% — but that gap is entirely the biotech beta below.
   Extreme upside was a **distress marker**: APLT (+300% "upside") −88%, TVRD (+250%) −55%, ATYR (+400%)
   −30%, AARD (+210%) −29%, SOC (+420%) −12%. That is the farm's `value_bm` result again — an extreme
   screen value in a small name selects the sick, not the cheap.
2. **The list's return was mostly one factor.** XBI made +55.9% over the window; the green-coded names
   (mostly biotech) made +58.6%. The watchlist beat SPY and IWM handsomely and **matched its own sector**.
   Idiosyncratic skill on top of XBI beta is not visible in this sample.
3. **The best names were the ones the analysts disliked.** The five red-coded names — target below price —
   returned +154% mean, carried by MU (+292%) and MRNA (+547%), with BE +61%. Analyst targets LAG a cycle
   turn; a name in a physical bottleneck (memory pricing) with a stale target is precisely the
   `contradiction_trading` / `bottleneck_rent_migration` template from the Causal World Model roadmap. This
   was the most valuable thing in the list and the method scored it lowest.
4. **The portfolio was worse than the watchlist because of construction, not selection.** Median −15%:
   capital concentrated in MSTR, SLDP, APLT, RGTI, AMPX (five of the bottom nine) while the watchlist
   held the winners. Sales were early: ALMS sold at 10, now ~22 (+408% from list); TVTX sold at 34.4, now
   +107% from list. The list found return; the book did not keep it.
5. **Today's book has the same shape.** SLDP + DKNG are ~58% of it; DKNG is −15% since the list, SLDP −66%.

## 4. What this changes in the engine

- **`ANALYST_UPSIDE` is evidence, never a score.** Finnhub recommendation trends are now recorded beside
  candidates (`alpha/sources/finnhub.recommendation_trends`), with this 0.017 as the prior. The parent
  project's Holm-surviving result — short-horizon winner-chasing is an anti-signal — points the same way.
- **The lane worth building from this list is CONTRARIAN-BOTTLENECK**: target < price (or flat revisions)
  AND a physical-economy signal rising (memory contract prices, supplier monthly revenue, export
  quantities). MU was the case. That is Trade Pulse + Psychohistory, not a screener.
- **BIOTECH_CATALYST is a real lane and it must be benchmarked against XBI**, never SPY, or its beta will be
  reported as skill. Event dates (PDUFA, readouts) are the catalyst; the PEAD rule applies after them.
- **Construction is the fixable half.** The prospective admission controller (per-name cap, 10% free,
  causal-thesis concentration) exists so a book cannot put 58% into two names. Murat's twelve holdings are
  the CONTROL universe (`alpha/universe.CONTROL_HOLDINGS`): every candidate report says whether the engine
  would have found them and why, and never prefers them.
