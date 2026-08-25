# AEGIS Alpha Terminal — one-page write-up (DRAFT, 2026-08-25; numbers to be replaced with the judged account's)

## What did not work (first, on purpose)

- **Zero P&L evidence at the time of writing.** One rehearsal fill, one day old.
- **Social sentiment is closed to a free script**: Reddit, StockTwits, GDELT and LunarCrush all refused. The narrative brain reads Benzinga news instead and lets the LLM estimate dispersion — an admitted substitute for the Twitter/StockTwits corpus the literature (Cookson et al., JFE 2024) used.
- **The free option feed's closing quotes disagreed with the underlying by 1.3% on put-call parity** (NVDA 212.5 straddle). Every decision now records the gap.
- **A brain that widens its own uncertainty wins the sizing comparison by construction.** Two of four brains are therefore shadow-only until they beat the others on the counterfactual scoreboard.
- **Inferred earnings dates include one macro day** (NVDA 2025-01-27, the DeepSeek selloff). The dates are printed on every forecast so a reader can see it.
- **The first counterfactual run marked a refused spread at −292% of its risk** — an inconsistent quote read as a "saved loss". Marks are now bounded by the structure's own max loss.

## AI logic

Four brains, independent by **data source**, each returning a return distribution (centre + sd + conviction), never a direction:

| Brain | Source | Claim |
|---|---|---|
| `vol_gap` | daily bars | EWMA realised vol vs the chain's implied move |
| `event_move` | fiscal calendar + bars | this company's OWN earnings-day move history vs the chain (NVDA median 7.5% vs 5.4% implied) |
| `options_attention` | option daily bars | abnormal unsigned volume on seasoned contracts → wider sigma, no sign |
| `narrative_dispersion` | news → DeepSeek | `NARRATIVE_SHOCK_v1`: truth, credibility, novelty, attention, disagreement, **market belief**, impact, **already priced** → a belief-gap case. The LLM emits numbers on declared axes and has no trade verb. Prediction-market prices (Polymarket/Kalshi) are recorded beside the LLM's belief; disagreement is a finding, not an average. |

The engine then enumerates eight option structures from the live chain, prices each at the side we would cross, computes its **minimum detectable move** (the underlying move at which entry-at-ask/exit-at-bid returns zero) and keeps a structure only if our distribution puts ≥5pp more mass beyond it than the chain's implied distribution does. Shape-aware construction (32 years of CRSP decile curves) says which signals are allowed to buy convexity at all.

Several brains, **one position per symbol, nothing averaged**: the champion is the largest approved risk; losers are written as shadow worlds and priced forward at equal risk.

## Risk gates

Every structure states a bounded worst case at entry (naked shorts are not representable). Spread > 25% of max loss → refused. Probability edge < 5pp → refused. Per-thesis and aggregate premium caps by profile (aggressive: 8% / 50%), binding *within* a pass. Limit orders only. Deadline liquidation at 10:45 ET on 4 Sep; never through an expiry; asymmetric targets/stops. Quote snapshot required on every order.

## Alpaca infrastructure

Trading API via a paper-only client (live host not on the allowlist; credentials in a separate `AAT_*` namespace; `PA` account prefix verified server-side). **MCP server started with the `trading` toolset withheld** — 44 tools vs 72, so the model has no `place_option_order` to call; measured by starting the server and asking it. Official CLI for the audit path. Market data: news, option chain snapshots, option daily bars/trades, stock bars/trades — all on the free plan, with delayed option quotes carried forward by delta/gamma and penalised.

## Evidence

Hash-chained ledgers: `decisions.jsonl` (every candidate, refused ones included), `forecasts.jsonl` (every brain, every pass, before pricing), `counterfactual.jsonl` (every road not taken, marked at equal risk), `fills.jsonl` (decision quote vs fill vs mark). One event card per catalyst: what happened, what sources said, truth, attention, disagreement, each brain's forecast, the chain's expectation, the chosen structure, the alternatives, the refusal reasoning, and the result.
