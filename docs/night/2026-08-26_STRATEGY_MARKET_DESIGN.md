# STRATEGY_MARKET_v1 / MODEL_DISAGREEMENT_v1 — design only (night lab, no execution mutation)

Status: ARCHITECTURE. Nothing here touches `alpha/`. Day promotes or rejects.

## 0. Why

The 1rok "AI Invest Arena" result the review cites (GPT-5.5 +26.35% vs QQQ +17.00%, several frontier
models below QQQ, Jan–May 2026) says two things: *"use an LLM" is not an edge*, and the models' **picks
were similar while their sizing differed**. Aegis today has one brain per mechanism and one arbiter; it has
no market in which reasoning processes compete for capital and lose it. The competition's judging rewards
P&L first, and a seven-day horizon is a different optimisation problem from the fund's.

## 1. The contract every sleeve must publish (the only thing the allocator reads)

```
SleeveQuote {
  sleeve_id, policy_hash, licence            # frozen identity; PRODUCT_EXPERIMENT unless promoted
  horizon_sessions                           # when the thesis resolves (<= sessions to Sep 4 for the competition)
  n_opportunities_before_deadline            # expected count, from the calendar (prints, Nikkei>2% days, ...)
  edge_per_opportunity: {mean_net, sd, t, n_hist, window}   # SIMPLE returns, net of the costs the executor pays
  loss_distribution: {p05, p01, worst_hist, path_aware}      # path-aware = intraday highs/lows, not closes (agent 7)
  capital_required, capital_lockup_sessions
  correlation_to_book                        # measured on the last 60 sessions of shadow P&L, or 1.0 if unknown
  evidence: {years, quarters_negative, two_way_t, placebo_status}
  expression: shares | option_structure       # and the spread paid, so theta/spread are subtracted
}
```
A sleeve that cannot fill a field publishes it as `UNKNOWN` and the allocator prices `UNKNOWN` as the worst
observed value in that field across sleeves — an incomplete quote can never out-score a complete one.

## 2. The allocator (competition personality)

Objective: `E[terminal P&L to Sep 4]` subject to `P(drawdown > 8%) < 5%` and rule compliance.

Score per sleeve, per opportunity:
```
S = mean_net * n_opps * capital_efficiency
  - lambda_theta * theta_and_spread
  - lambda_corr * correlation_to_book * sd
  - lambda_tail * p01_loss * capital_required
  - lambda_lock * capital_lockup_sessions / sessions_left
```
Capital is assigned by **Thompson sampling over the posterior of `mean_net`** (Normal-Normal on the sleeve's
own forward paper P&L, prior = its historical `edge_per_opportunity` shrunk by `1/sqrt(years)`), one draw
per session, so a sleeve that deteriorates loses capital within days and a sleeve proving itself gains it.
Pure variance maximisation is refused by construction: `mean_net <= 0` sleeves receive zero regardless of sd.

The allocator is an `alpha/` change and therefore a DAY change. Night ships the contract and the scorer as
`scripts/night_strategy_market.py` reading shadow quotes from `state/night_shadow/quotes/*.json`.

## 3. The tournament (MODEL_DISAGREEMENT_v1)

Not six prompts that converge. Six brains with **incompatible constraints**, same data, same costs:

| brain | may use | forbidden |
|---|---|---|
| `underfollowed` | names with < 3 analysts, dv < $50M | mega-caps |
| `short_only` | any | long positions |
| `physical` | customs, power, shipments, supplier prints | price history, analyst targets |
| `options_shape` | implied distributions vs fundamental scenario trees | delta-one shares |
| `relative_value` | pairs, baskets, ADR/parent, ETF/constituent | outright direction |
| `alien` | anything NOT in {momentum, value, quality, PEAD, sentiment, MA/RSI/MACD, consensus, surprise} | the mainstream set |

Each brain publishes a `SleeveQuote`; the first **disagreement register** is the cheapest new signal: where
two brains with different forbidden sets quote opposite directions on the same name with conviction > 0.7,
that name is logged and graded separately (`state/night_shadow/disagreement.jsonl`). Alpha, if it lives
anywhere in a tournament, lives there — the agreeing names are the ones every other bot has too.

## 4. What tonight's measurements already say about the first quotes

| sleeve | mean_net / opp | n_opps to Sep 4 | evidence | quote |
|---|---|---|---|---|
| wide PEAD unhedged short | +0.00% | many | 7/11 quarters negative | **zero** |
| wide PEAD pair vs IWM | −0.05% net | many | 7/11 negative | **zero** — do not build the executor |
| Nikkei-ADR fade (|N225| ≥ 2%) | +0.15% (5y) / +0.22% (2026) | ~1 | 2021-22 negative, 2025 carried | shadow only |
| mega-11 source PEAD | per existing brain | 2-3 prints (Aug 27-28) | preregistered | as today |

## 5. What day must decide

1. Whether `SleeveQuote` becomes the arbiter's input (an `alpha/` change) before or after the competition.
2. Whether the `alien` and `short_only` brains are built as LLM personalities (DeepSeek, ~$0.05/pass) or as
   code — recommendation: code for the data-constrained brains, LLM only for `alien`, graded per template.
