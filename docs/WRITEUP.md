# AEGIS Alpha Terminal — one-page write-up (DRAFT, 2026-08-26; numbers to be replaced with the judged account's)

## What did not work (first, on purpose)

Every item below is a receipt in `state/`, reproducible with one command, walk-forward where a rule is involved.

- **Buying the print was the wrong side.** 117 real earnings prints (2024–26, exact SEC 8-K dates, expired-contract closes): median long straddle **−18%**, 43% clear break-even. **NVDA 0 of 8.** The agent had planned that exact NVDA straddle at 18.5% risk; the evidence withdrew it before the print.
- **Isolating the event variance did not help.** Solving two expiries for ambient + jump variance is the textbook method; as a *predictor* of the realised move it lost to the raw front-expiry number (corr 0.18 vs 0.33), and our own history of the name lost to both (0.29). The chain knows more than the company's last eight prints.
- **No short structure is a free lunch either.** Iron butterfly +5% of max loss (t 0.7); the iron condor wins 63% of the time and loses money. The conditional rule (name's history vs chain → long or short) survives walk-forward only on the short side, weakly (n=46, t 1.4).
- **The skew does not know the direction** (45% hit on 106 prints). Concave surfaces move slightly more and pay convexity buyers worse (RoF 2025), too weakly to trade.
- **Expressing a print through its peers is priced.** 290 peer straddles on originator print days: mean −4.2%, hit 34%, t −2.0; the history/implied ratio that ranks peers does not sort outcomes. This afternoon's "ARM and TSM are the cheap place to own NVDA's print" would have lost.
- **Prediction markets give width, not side.** Kalshi's payrolls ladder mapped through 28 first-print surprises → SPY 10:45 move: corr 0.03, walk-forward −0.57. The crowd's dispersion is usable; its centre is not.
- **Two unlocked writers corrupted the tamper-evident ledger** (6 interleaved lines, chain break at line 1203) and **the "one position per symbol" rule was per pass, not per book** — the restarted loop re-bought the same straddle every 30 minutes. Both found by reading the live book, both fixed and tested, the corrupt lines left in place and counted.
- **Social sentiment is closed to a free script** (Reddit, StockTwits, GDELT, LunarCrush refused); the narrative brain reads Benzinga via the LLM instead. **The free option feed is seconds, not minutes, late** (measured 3–4 s) — the $99 feed was declined on evidence.

## AI logic

Five brains, independent by **data source**, each returning a return distribution (centre + sd + conviction), never a direction. The LLM emits numbers on declared axes (`NARRATIVE_SHOCK_v1`: truth, credibility, novelty, attention, disagreement, market belief, impact, already-priced → a belief-gap case) and **has no trade verb** — the MCP server is started with the trading toolset withheld (44 tools vs 72).

| Brain | Source | Executes on |
|---|---|---|
| `vol_gap` | daily bars vs chain | dev (**assigned**, not earned) |
| `event_move` | SEC print history vs chain, last 8 prints | dev |
| `options_attention` | option tape, seasoned contracts | exp1 (**assigned**) |
| `narrative_dispersion` | news → DeepSeek axes + Polymarket/Kalshi belief | exp1 |
| `relay` | peer co-movement on originator prints | shadow only (refuted, above) |

The engine enumerates eight defined-risk structures from the live chain at the side we would cross, computes each one's **minimum detectable move**, and keeps it only if our distribution puts ≥5pp more mass beyond it than the chain's. Geometry 2 reads the surface back (ATM IV, skew, curvature, event-variance strip) so the card can say "the market has already bought the tail". Several brains, **one position per symbol per book, nothing averaged**; losers are written as shadow worlds and priced forward at equal risk. Positions that cite the same scheduled event share one **event-node budget** (25%).

## Two accounts, two arms — and neither is a champion yet

`dev` and `exp1` run different brain sets on the same sessions with the account stamped on every ledger row, so "do attention and narrative earn execution?" gets answered by fills and marks rather than by a prior.

**The split is a design choice, not a result, and we will not claim otherwise.** The counterfactual ledger holds 267,802 rows and looks like a scoreboard; it spans **two calendar days**. On it `vol_gap` appears best at +13.8% mean return-on-risk — but its top 3 of 27 observations carry 113% of that sum, decision ids are minute-derived so one view of META across three passes of one afternoon counts as three decisions, and collapsing to date blocks halves every n. **META went up on 25 August and three brains had shadow exposure to it.** Even the comforting reading — *every road not taken lost money* — decomposes into long premium decaying over two flat sessions, and on the short-premium side those refusals were mildly wrong (`bear_call_spread` refusals: +2.2% median, 59% win).

Receipt: `docs/FINDING_2026-08-26_THE_SCOREBOARD_IS_TWO_DAYS.md`. **A 285 MB ledger feels like evidence. File size is not sample size.**

First pass (25 Aug): both bought QQQ straddles, exp1 at twice the size; both sold NVDA condors into the print.

## Risk gates

Bounded worst case at entry (naked shorts not representable). Spread > 25% of max loss → refused. Edge < 5pp → refused. Per-thesis / aggregate / event-node caps binding *within* a pass. Limit orders only; no order without a quote snapshot; flat by 10:45 ET on judging day; never through an expiry. A 5-minute exit pass whose starvation by a slow entry pass is **bounded and measured, not prevented**: entry passes run a median 368s (p90 439s), the ceiling was cut 1500s → 600s, and an exit pass now runs immediately after every entry pass, so worst-case lateness fell from ~26 min to ~11. The earlier claim here — that it *can never* be starved — was wrong.

## Alpaca infrastructure

Paper-only client (live host not on the allowlist; separate `AAT_*` credential namespace; `PA` prefix verified server-side). MCP server with the trading toolset withheld; official CLI for the audit path. Market data on the free plan: news, chain snapshots, **expired** option bars (the backtests above), stock bars/trades. Unattended loop containerised (`Dockerfile`, `railway.toml`).

## Evidence

Hash-chained, cross-process-locked ledgers: `decisions.jsonl` (every candidate, refused ones included), `forecasts.jsonl` (every brain, every pass, before pricing), `counterfactual.jsonl` (every road not taken, marked at equal risk), `fills.jsonl` (decision quote vs fill vs mark), `belief_series.jsonl` (the crowd, hourly). One event card per catalyst; one dashboard (`scripts/dashboard.py`) that shows the refusals because they are the product. Eight backtest receipts, six of them negative.
