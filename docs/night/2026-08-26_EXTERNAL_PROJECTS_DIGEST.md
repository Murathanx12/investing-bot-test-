# External projects digest — 2026-08-26 (night)

Nine repos shallow-cloned to `C:\Users\mrthn\reference-codes\trading-agents\`
(read-only reference). Written for the Alpaca hackathon (28 Aug–4 Sep, P&L is
criterion #1, ~5 equity sessions). Everything below separates **claimed** from
**evidenced**. Sub-agent digests for five repos are condensed here; file paths
quoted are absolute in the clone.

| Repo | Stars | Last commit | LOC (py/ts) | One line |
|---|---|---|---|---|
| `logiqfish/shark-trading-agent` | 2 | 2026-07-02 | 6,968 | LLM boxed by a deterministic risk kernel; GTC bracket, 2R, journal w/ alpha vs SPY. **No returns published.** |
| `iAmGiG/AutoTrader-AgentEdge` | — | 2026-01-11 | 82,815 | MACD(13/34/8)+RSI voting, no LLM in the signal. Honest research log: most things it tested FAILED. Wick-risk simulator. |
| `achaljhawar/1rok` (= AI Invest Arena / investingbench) | — | 2026-05-13 | 23,323 | 7 LLMs × $100k paper, weekly, identical 32 tools. GPT-5.5 +26.35% vs NDX +17.00%, 20 Jan–22 May 2026. |
| `TauricResearch/TradingAgents` | (arXiv 2412.20138) | 2026-07-18 | 16,663 | The canonical debate framework. Paper: Sharpe 5.6–8.2 on **3 months, 2024 Q1**. No broker. |
| `huygiatrng/AlpacaTradingAgent` | 253 | 2026-07-18 | 39,951 | TradingAgents fork + Alpaca. LLM never picks tickers. **Zero returns evidence.** |
| `renee-jia/trading-bot` | 92 | 2026-08-10 | 7,917 | Momentum top-10 + Haiku sentiment. Claims +39.8% paper; its own backtest says "beta amplifier, worse Sharpe than equal-weight". Strategy core is **gitignored**. |
| `zhound420/swarm-trader` | 54 | 2026-03-22 | ~30,400 | ai-hedge-fund fork + Alpaca brackets. 9 days of paper: +0.82% vs SPY −0.20%. Auto-research kept a Sharpe 12.4 "strategy". |
| `yebof/quant-agent` | 9 | 2026-07-16 | 62,941 | 9 agents, 6 sessions/day, gpt-5.5 everywhere. **No backtest, no track record.** Best Alpaca footgun write-up (OTO stop TIF). |
| `packetloss404/tradefarm` | 1 | 2026-08-06 | 91,411 | "100 agents" = 40 tickers × 7 rules. Market-only, client-side stops. **No returns.** Mostly a VOD/streaming codebase. |

Failed: `1rok/ai-invest-arena` (does not exist; real repo is `achaljhawar/1rok`).
Unreachable: reddit thread `r/ChatGPT/comments/1t9wl4h` (www, old, redlib mirror
all blocked) — AI Invest Arena section uses the dev.to write-up + source instead.
`gh` is unauthenticated on this machine; GitHub search done via the public API.

---

## 1. shark-trading-agent (logiqfish)

**(a) Strategy.** Long-only whole-share swing on a watchlist (or Alpaca
most-actives ≥$1M vol, ≥$5, top 10 — `skills/shark/scripts/discovery-local/discover.py`).
Fires 3×/day (cron `0 10,13,15 * * 1-5` ET). Per fire: market gate → audit stops →
regime gate (`local-markov/local_markov.py`: SMA20/50 trend, Bear if 60-day DD ≥10%
or 20-day daily vol ≥4%) → bull/bear/referee debate → conviction 0–100 → floor 65
→ fixed-fractional sizing → GTC bracket. **Sizing** (`risk/risk.py` `size_v2`):
`shares = floor(risk_frac × equity / (entry − stop))`, risk_frac by conviction
band 65-69→0.50%, 70-79→0.75%, 80-89→1.00%, 90-100→1.25%; cap 20%/name, ≤8 open,
≥10% cash, R/R ≥2, −3% day-start-equity halt (latching), 1 trade/ticker/day, no
averaging down. **Exit** (`trade-manager/trade_manager.py`): target = entry + 2R,
scale half at +1R and lift stop to breakeven, runner to +2R; stops/targets nudged
off .00/.50 by 3¢ (`_dodge_round`). Phase-3 trailing (6% or chandelier 3×ATR22) off by default.

**(b) Data/LLM.** Alpaca IEX bars only; the "data fence" forbids the agent any
other source (prompt-enforced, not sandboxed). Any LLM via Hermes profile. LLM
picks *from* the candidate list and scores conviction; code decides everything else.

**(c) Returns.** **None.** README: "Not a stock-picking oracle. The point isn't
alpha; it's the architecture." Screenshot shows 4 paper longs (DKNG, GOOGL, HOOD,
UBER), no numbers.

**(d) Non-obvious lesson.** Fractional shares on Alpaca cannot co-rest two exits:
"a fractional position can rest only one exit (the stop reserves the shares; a
co-resting DAY limit is rejected)… verified live 2026-06-08, MRVL"
(`trade_manager.py` `plan_entry`). And the bracket-ambiguity rule in
`trade-manager/broker.py:113-118`: on a *timed-out* bracket POST, reconcile by
client-order-id before falling back — "a fallback market buy after a bracket
that actually landed" doubles the position.

**(e) Execution.** Entry `market` + `order_class: bracket`, `time_in_force: gtc`,
`take_profit.limit_price`, `stop_loss.stop_price`. Fallback on DEFINITIVE bracket
reject: market DAY buy + separate GTC stop ("never naked"); if the stop cannot be
confirmed → liquidate. Fractional: market DAY + DAY stop only, force-flat 15:45.

**(f) Copy:** the whole `risk.py` (stdlib, stdin JSON, exit codes 0/10), the
+1R scale-out/breakeven state machine, the idempotency-key reconcile, the
self-grading journal that logs alpha vs SPY per trade (`reflection/`).
**Avoid:** the 3×/day cadence with a 5% default stop — on a 5-session contest
one −3% day halts you. The prompt-only data fence.

**(g)** 6,968 LOC. `skills/shark/scripts/{risk,trade-manager,debate,reflection,
thesis,local-markov,discovery-local}/`, `SKILL.md` (the per-fire procedure),
`AGENTS.md` (policy), 80+ tests.

## 2. AutoTrader-AgentEdge (iAmGiG)

**(a) Strategy.** `VoterAgent`: MACD(13/34/8) + RSI(14, 30/70). Both agree →
100% size; one signals, other HOLD → 50%; conflict → cash
(`docs/03_reference/01_validation_results.md`). Default exits 8% TP / 5% SL
("balanced", `config_defaults/trading_config.yaml`), `position_sizing: fixed 1.0`
(all-in per trade). Daemon runs 09:20 and 15:50 ET. Watchlists are YAML.

**(b) Data/LLM.** Polygon + Alpha Vantage, SQLite cache. **The LLM is not in the
signal** — GPT-4o-mini only parses CLI intent ("buy 10 AAPL"). No ticker picking.

**(c) Returns — all BACKTEST, and mostly negative, which is the value here.**
- Exp #293, AAPL 2024 (252 days): voting Sharpe **0.856** vs MACD-only 0.841;
  return **12.62%** vs 13.34%; MDD −10.10%; 140 trades. Not benchmark-relative
  in the table.
- Extended 2024-01-02→2025-08-29 (417 days): voting **+36.6% vs buy-hold +90.6%**
  ("gap −54%"), Sharpe 0.771. README rewrites this as "Outperformed SPY".
- Project status table: OOS Sharpe on QQQ **0.468**.
- #518 MACD parameter stability: best OOS Sharpe **−0.223** ("least unprofitable").
- #519 academic TSMOM on SPY/QQQ: 19% pass rate, avg net Sharpe −0.259, STOP.
- #516 GEX filter: median improvement **−2.9%**, STOP.
- RAF ("ready-aim-fire") 0.553 Sharpe, 80% win rate — CONTINUE, not integrated.

**(d) Non-obvious lesson — wick risk.** `scripts/research/path_dependent_simulation.py`
(#525/#528): vectorised close-to-close backtests "overestimate Sharpe/Win rates
(ignores intraday stop-outs)". The engine walks Open→Low→High→Close and assumes
"if both SL and TP could be hit, the Stop Loss was hit first (worst-case)", fills
stops at `min(open, stop)` on gaps. `docs/08_research/README.md` lists it as a
**GAP: address before trusting backtest numbers for production sizing**. This is
exactly what our own agent 7 found last night (intraday-high stops close 77-91%
of PEAD legs) — an independent confirmation that a stop tested on closes is a
lower bound on damage.

**(e) Execution.** Alpaca via alpaca-py, market orders, GTT/partial-exit docs
(`docs/04_development/18_gtt_implementation.md`, `19_partial_exit_strategies.md`).
Backtest commission $0.005/share, no slippage.

**(f) Copy:** the path-dependent simulator (150 lines, pandas-only) as a
pre-flight for any stop/target we place; the research-status legend
(STOP/DONE/CONTINUE/GAP). **Avoid:** MACD/RSI as a signal — its own author could
not make it beat buy-and-hold.

**(g)** 82,815 LOC (AutoGen-heavy). `src/autogen_agents/`, `src/backtesting/`,
`scripts/research/*.py` (18 experiments), `config_defaults/*.yaml`,
`docs/08_research/`.

## 3. AI Invest Arena / 1rok (achaljhawar) — the one with a real scoreboard

**Leaderboard, frozen at close 22 May 2026, start 20 Jan 2026 ($100,000 each,
Alpaca paper, ~4 months):**

| # | Model | Return | NAV |
|---|---|---|---|
| 1 | GPT-5.5 | **+26.35%** | $126,348.66 |
| 2 | MiniMax M2.7 | +18.56% | $118,561.38 |
| — | NASDAQ 100 | +17.00% | $117,003.23 |
| 3 | Grok 4.3 | +16.88% | $116,883.58 |
| 4 | Kimi K2.6 | +16.68% | $116,682.26 |
| 5 | Gemini 3.1 Pro | +10.67% | $110,667.59 |
| — | S&P 500 | +8.98% | $108,978.46 |
| 6 | GLM-5.1 | +7.31% | $107,314.37 |
| 7 | DeepSeek V4 Pro | +6.92% | $106,920.90 |
| — | Dow | +3.47% | $103,473.10 |

Only **two of seven** beat NDX; five beat SPY. Spread top-to-bottom 19.4pp over
4 months with identical tools/prompts/data. No Sharpe, drawdown, turnover or
cash% published anywhere (site, README, dev.to).

**Cadence:** cron **every Monday 09:45 ET**; `run` writes a JSON artifact,
`execute` places orders (paper by default, `--live` for real).

**Tools (32, eight groups, identical per model):** market (indices, sectors,
rates, commodities, econ calendar, correlation), stock (quote, profile,
financials, peers, screener, ETF screener), technicals (indicators, momentum,
S/R, short interest), options (chain, IV, skew, term structure, P/C, signals),
earnings, portfolio (`get_portfolio_state`, `calculate_portfolio_allocation`,
`calculate_trade_orders`), Tavily web search. Sources: Alpaca, Yahoo, FRED, Tavily.

**Pipeline (10 agents):** Macro → Screener (4-10 screener queries; mcap ≥$1B,
ADV ≥$5M, NYSE/NASDAQ; 25-30 names) → six analysts score 0-100 in parallel →
Orchestrator composite → Constructor → Alpaca.
Composite: fundamental 20%, valuation 20%, risk 15% (inverted), technical 15%,
catalyst 15%, sentiment 10%, macro gate 5% (`src/harness/prompts/orchestrator_agent.xml`).
Score ≥85 → HIGH (max 40%), 75-84 MEDIUM (25%), 65-74 LOW (15%), ≤64 pass.
Cluster caps tech 50 / cyclical 40 / defensive 50 / financial 40; risk_score >85
rejected; macro can cap score at 64 (no new buys) or forbid HIGH.

**Position sizing — where the models actually differed.** The Constructor is
*forbidden* from doing arithmetic ("NEVER calculate portfolio weights internally")
and must call `calculate_portfolio_allocation`
(`src/data/services/calculations/portfolio-allocation.ts`): weight = conviction
label → **HIGH 30 / MEDIUM 18 / LOW 12**, top 8 by score, cap 40%/name, then
scaled UP to ≥85% invested (or to a macro-set cash target). So the *only*
degrees of freedom a model has are (i) which ≤8 names, (ii) the HIGH/MEDIUM/LOW
label it assigns, (iii) the macro agent's cash %. Two models holding the same
names with different labels get very different books: three HIGHs = 90% in three
names; eight LOWs = 96% spread evenly. That is the mechanism behind "picks were
similar, sizing differed". Final holdings on the site: GPT-5.5 7 names (TSM, V,
KO, TTE, TNK…), Kimi **15 names** (GOOGL, KO, MSFT, LRCX, NVDA… — exceeds the
8-cap, so Kimi's constructor over-rode or accumulated), DeepSeek 6 (AMZN, GOOGL,
TSM, TRV, TTE). KO appears in 6 of 7 books; TSM in 4. The models converge on
the same large-cap names; rank came from concentration and from TSM/semis beta.

**Execution** (`src/harness/core/order-executor.ts`): every order `type: market`,
`time_in_force: day`; SELLs by qty (full-close if qty ≥ available) first, 2 s
sleep, then BUYs by **notional** (fractional). No stops, no brackets, no limits.
Trades placed at 09:45 Monday — after the open auction, into the first-15-min spread.

**Skeptic:** one 4-month window in a +17% NDX tape; a weekly-rebalanced 7-name
long-only book with 30-40% names is a beta+concentration bet, and the winner's
edge (+9pp over NDX) is well within one-name variance (a 30% TSM sleeve alone
moved ±10pp in that period). No repeat, no drawdown, no benchmark on the same
buy dates. Also the DeepSeek V4 last place is relevant to us: DeepSeek is our
only provider.

**Copy:** the tool-not-LLM allocation kernel and the run/execute split with an
artifact in between (audit trail for the judges' "explainability" criterion).
**Avoid:** Monday-only, market-at-09:45, no stops.

**(g)** 23,323 LOC TS (Bun). `src/harness/agents/*.ts` + `prompts/*.xml`,
`src/data/services/**` (32 tool handlers), `src/harness/core/order-executor.ts`.

## 4. TradingAgents (TauricResearch)

**(a)** Per-ticker, per-date: 4 analysts → bull/bear (1 round default) → research
manager → trader (structured `TraderProposal`: action, entry, stop_loss,
position_size) → 3 risk debators → Portfolio Manager emits one of
Buy/Overweight/Hold/Underweight/Sell. **No universe, no sizing math, no broker.**
`propagate("NVDA","2026-01-15")` returns a rating; what you do with it is yours.

**(b)** yfinance/Alpha Vantage/FRED/Polymarket/Reddit/StockTwits; any provider,
default `gpt-5.5` deep / `gpt-5.4-mini` quick. LLM reasons over a given ticker only.

**(c) Returns (paper, arXiv 2412.20138 §experiments):** AAPL/GOOGL/AMZN (+NVDA,
MSFT, META), **1 Jan–29 Mar 2024** only, o1-preview + gpt-4o: CR 26.62 / 24.36 /
23.21%, Sharpe **8.21 / 6.39 / 5.60**, MDD 0.91 / 1.69 / 2.11%; best baseline
2.05 (KDJ&RSI) / 7.78 (B&H) / 17.1 (B&H). Authors: "benchmarked over 3 months
due to intensive LLM and tool use (11 LLM calls & 20+ tool calls/prediction)";
the Sharpe "resulted from few pullbacks". Transaction costs not stated. The
README now says "Backtest results are not guaranteed to match any published
figure". Treat as unreplicated.

**(d)** The reflection memory grades each decision on realised **alpha vs SPY** at
the next run and injects same-ticker lessons into the PM prompt
(`tradingagents/agents/utils/memory.py`); v0.3.1 added Alpha Vantage look-ahead
filtering after a leak — even the reference framework had a lookahead bug in
its news feed for a year.

**(e)** None. It is a rating engine.

**(f) Copy:** structured-output schemas (`agents/schemas.py`), the SPY-alpha
memory tag format. **Avoid:** building the debate. The parent project measured
personas as correlated forecasters; three forks here (AlpacaTradingAgent,
swarm-trader, quant-agent) added Alpaca and none produced a return series.

## 5. AlpacaTradingAgent (huygiatrng, 253★)

TradingAgents + Alpaca + WebUI. **No ticker selection at all** (zero hits for
screener/universe). Flat `trade_amount` $1,000 default, then optional haircuts:
corr >0.6 → ×0.5, inverse-vol to 2%/day, regime ×0.5-0.85; half-Kelly/ATR engine
exists but `risk_sizing_enabled: False`. Brackets `OrderClass.BRACKET`, GTC,
equities only; `_calc_qty` = `int(amount/price)` → **a $1,000 order on a $1,500
stock places nothing**. Bracket rejection falls back to an **unprotected** market
order. Signal parser fallback substring-scans the last 100 chars for
BUY/SELL/HOLD/SHORT ("SHORT-term" matches). Guardrails worth lifting:
`tradingagents/safety/guardrails.py` (kill-switch file, $25k/order, 25%/symbol,
−10% daily, −15% from HWM, 5-rejection halt). Backtester fills at next open and
*logs* margin rejections instead of dropping them (`backtest/engine.py:5-8,128-138`).
**Returns: none** — one screenshot with −$0.80 day P&L.

## 6. renee-jia/trading-bot (92★)

Score = technical 35 / trend 30 / alpha 20 / sentiment 15 (Haiku); top-10 by
score, weights 95% momentum-rank + 5% score², ≤25%/name, cash 0-20% from a
50/50 quant+Haiku macro; enter top-10, exit only on falling out of top-15; 80%
blend toward target; market DAY, whole shares, **no stops**. `core/` (scorer,
strategy, 157-name universe) is **gitignored** — the repo does not run.
**Claimed paper:** 2026-03-12→07-09 **+39.8% vs SPY +13.5% / QQQ +21.4%**, peak
$165,578 (23 Jun) → $139,829, MDD **−20.7%**, 35 positions, cash **−$1,165**
(unintended margin). `scripts/fetch_paper_performance.py` pulls
`portfolio/history` and computes same-window SPY/QQQ (honest), but never checks
deposits. **Its own backtest** (`docs/BACKTEST_RESULTS.md`, 12 mega-cap tech
names, 5 bps/side, T+1 close fills): strategy−basket by year 2022 **−4.1**, 2023
**−11.1**, 2024 +8.6, 2025 +1.8, 2026 +9.9; Sharpe 2.05 vs equal-weight 2.13.
Author: "a beta amplifier on a hand-picked winner basket". The 2022 row is
omitted from the README. Lesson (`alpaca_trader.py:203-207`): blending an *exit*
toward zero with integer rounding strands 1-share remnants forever — exits must
be full-qty, and sub-1% positions must not hold a rank slot. Also: sell proceeds
don't settle in time to fund same-batch buys; buys are scaled to buying_power×0.99.

## 7. swarm-trader (zhound420, 54★)

ai-hedge-fund fork; 7 default personas → one PM LLM call picks action+qty from a
**pre-computed allowed set** (`compute_allowed_actions`); risk sizing 20% NLV ×
vol band × correlation multiplier; second code gate `validate_trade()` (11 rules:
8%/name swing, 20% min cash, −2%/−5% breakers, leveraged-ETF blocklist). Swing
buys = market GTC **bracket**, stop 7%, target 3× stop distance; day mode has
**no broker stop**, stops checked only when a cron fires (3×/day). Bracket legs
priced off a *pre-trade reference*, not the fill. 19 of 121 journal orders
failed `403 held_for_orders` — selling into its own bracket children.
**Evidenced:** `data/performance.json` 2026-03-08→03-17: swing **151,435 →
152,670 (+0.82%)** vs SPY **−0.20%**, intra-window DD −4.0%; day book +2.4% over 3
days. Auto-research kept an experiment with **Sharpe 12.38, MDD 0.00%, 25 trades,
10 days** after its own `program.md` said ">4.0 is suspicious" — the constraint
was prose, not in `_compute_fitness()`. Backtest uses Alpaca **IEX** feed (2-4%
of volume) for every volume threshold.

## 8. quant-agent (yebof)

97-name hardcoded universe; 6 ET sessions/day via systemd timers; buys only in
the morning session, limit DAY; deterministic prefilter (RSI<35/>65, Bollinger
touch, MACD flat, vol Δ>50%) before any LLM; PM emits `target_weight_pct` only,
Python sizes with a 0.5%-of-equity risk budget: `cap = risk$ × entry/(entry−stop)`.
Stop = entry − 2×ATR14 as a **post-fill GTC stop-limit** (limit 3% under);
auto-trim 15% at +30%; −3% daily-loss liquidates all; idle cash swept to SGOV.
All 9 agents `gpt-5.5`, `max_tokens 128000`, no caching. **No backtest, no
track record**, 874 tests. **The lesson** (`src/execution/broker.py:1064-1081`):
an Alpaca OTO/bracket child stop inherits the **parent's TIF**; parent must be
DAY (unfilled entries must die), so every stop expired at 16:00 and positions
"sat NAKED overnight — precisely when gap risk is the reason the stop exists".
Fix: place the stop *after* the entry is terminal, GTC, sized to the actual fill.
Also `str(enum)` → `'OrderStatus.REJECTED'`, so a naive `'rejected' in status`
check passes real rejections (`broker.py:1108-1115`).

## 9. tradefarm (packetloss404)

"100 agents" = `universe[i % 40]` × `strategy[i % 7]` (mom 12-1, LSTM, LSTM+LLM,
BB mean-rev, RSI2, Donchian, pairs z). LSTM slots silently fall back to momentum
without `models/*.pt`. Long-only, 20% of book cash per entry, exits by rule (SL
3%, TP 5%, trail 2%, 10-day time stop) because the LSTM "rarely flips down".
Market DAY only; stops client-side on a 5-min tick over **daily** bars.
Optimistic fills at last close, reconciler patches later; `check_daily_loss`
defined, never called. 100 books on one account attributed by
`client_order_id=agent{id}-{tag}`; no self-cross/wash handling. **No returns**;
only "LSTM val accuracy 55-60% vs 51% flat baseline". Lesson
(`scheduler.py:516-523`): a pending exit re-fired on the next tick "is how a
position flips short under alpaca_paper while the original exit is in flight".

---

## Cross-cutting: what actually made money

1. **Nobody in this set has evidenced alpha.** The only benchmark-relative
   forward records are 1rok (4 months, 2/7 beat NDX, no risk stats), renee-jia
   (+26pp over SPY in 4 months on 25%-name semis concentration with −20.7% DD and
   margin), and swarm-trader (+1pp over 9 days). Every one is concentration ×
   a rising tape. AutoTrader is the only project that *tested* and it published
   negatives.
2. **The LLM is never the sizer in the projects that survived contact with a
   broker.** 1rok, shark, quant-agent, swarm-trader all moved arithmetic into
   code and left the model a label (HIGH/MED/LOW, conviction 0-100, allowed
   actions). The ones that let the model emit qty/price (AlpacaTradingAgent
   fallback parser) documented misfires.
3. **Every Alpaca-specific loss was an order-lifecycle bug, not a forecast:**
   OTO stop inheriting DAY TIF (quant-agent), selling into own bracket children
   (swarm-trader 19×), fractional cannot co-rest two exits (shark, live MRVL),
   `int(qty)`→0 (three repos), double-submit on async fills (tradefarm), bracket
   timeout → duplicate entry (shark), bracket legs priced off pre-fill reference
   (swarm-trader), sell proceeds unsettled for same-batch buys (renee-jia).
4. **Stops tested on closes are a lower bound** (AutoTrader #528 = our agent 7).

## Ten things Aegis does not have and could build in a day (ranked by EV for a 5-session P&L)

Aegis today (`alpha/broker/alpaca.py`, `alpha/exits.py`, `alpha/admission.py`):
no `order_class`, no broker-side stop/target, exits evaluated per pass in code,
no daily-loss halt, no equity/benchmark snapshot script, no journal-with-alpha,
no candidate prefilter outside `scripts/candidates.py`.

1. **Broker-side GTC stop placed after fill, sized to filled qty** (quant-agent
   `place_entry_protection`; shark fallback path). Our share legs carry a 3% stop
   that exists only when a pass runs. One overnight gap without it is the
   competition. ~80 lines. Do NOT use OTO/bracket with a DAY parent.
2. **Daily-loss latch** (shark `session_pnl.py` + `DAILY_LOSS_HALT_PCT`; quant-agent
   `intra_check`): −3% of day-start equity → no new entries, auto-reset next day.
   30-min stateless tick, no LLM. Directly answers the judges' "risk gates".
3. **Same-timestamp SPY/QQQ snapshot + portfolio/history pull**
   (renee-jia `scripts/fetch_paper_performance.py`, swarm-trader
   `performance_tracker_v2.py`). A P&L number without the benchmark on the same
   stamps is the thing we keep warning ourselves about. Add a deposit check.
4. **Path-dependent stop simulator** on our candidate legs before placing them
   (AutoTrader `path_dependent_simulation.py`, 150 lines). Agent 7 already showed
   77-91% of PEAD legs die on intraday highs; run every stop/target pair through
   O→L→H→C worst-case before it is admitted.
5. **Pending-order / pending-exit guard** (renee-jia `alpaca_trader.py:387-398`,
   tradefarm `_pending_exits` TTL): abort a pass if any order is open for the
   symbol; never re-fire a full-qty exit while one is in flight. 20 lines; the
   most common way a paper book flips short by accident.
6. **Cancel-open-orders-then-sell** (swarm-trader's 19 `held_for_orders` 403s).
   If we add item 1, we need this the same day.
7. **Allowed-action pre-computation** (swarm-trader `compute_allowed_actions`):
   compute the legal {buy/sell/hold, max qty} set from cash, buying power,
   admission caps, and hand the LLM only that. Cuts tokens and the whole
   hallucinated-qty class.
8. **Per-trade self-grade with alpha vs SPY written to a journal and injected
   into the next decision** (shark `reflection/`, TradingAgents `memory.py`).
   We have `daily_autopsy`; we do not have per-position R and alpha at exit.
   Cheap, and it is the "explainability/learning" criterion made visible.
9. **Idle-cash sweep to SGOV / BIL** (quant-agent `cash_sweep.py`). Free carry
   on the 60-90% of equity our admission controller keeps free; hidden from
   sizing. Tiny P&L, zero risk, reads as discipline.
10. **Deterministic prefilter before any LLM call** (quant-agent
    `_has_actionable_signal_fn`, 40 lines) — for us: |day-0| ≥3.5%, ETB, spread
    ≤10% — so DeepSeek is only asked about names that can be traded. DeepSeek V4
    came last in 1rok; give it fewer, better questions.

Not on the list, deliberately: multi-persona debate, weekly rebalance, momentum
top-k, LSTM overlays, auto-research fitness loops. Three forks and one paper
produced no return series from the first; AutoTrader's own log kills the third.

## Claims to distrust

- **TradingAgents Sharpe 5.6-8.2**: 3 months, 2024 Q1, o1-preview, no costs
  stated, the README itself now disclaims replication.
- **1rok "GPT-5.5 beats NDX by 9pp"**: one 4-month window; 5/7 models lost to
  NDX; no drawdown/turnover; KO in 6 of 7 books means the models converged and
  the spread is the HIGH/MEDIUM/LOW label × the 30/18/12 kernel, not stock
  selection.
- **renee-jia +39.8% paper**: cash −$1,165 (margin), MDD −20.7%, 12-name
  survivorship-biased backtest with 2022 omitted from the README, strategy code
  not in the repo.
- **AutoTrader "0.856 Sharpe / Outperformed SPY"**: same doc shows +36.6% vs
  buy-hold +90.6% and OOS QQQ Sharpe 0.468.
- **swarm-trader auto-research Sharpe 12.38 / MDD 0.00%**: 25 trades, 10 days,
  IEX volume feed, no holdout, kept despite its own ">4 is suspicious" rule.
- **tradefarm "100 AI agents"**: 40 tickers × 7 rules, LSTM silently absent,
  daily-loss check never called, fills at yesterday's close.
- **quant-agent "live since 2026-04"**: 874 tests, zero P&L numbers; README says
  Anthropic default, config says gpt-5.5.
- **Any "win rate" in any of these READMEs**: none of the journals carry a
  per-trade P&L field (swarm-trader), or the journal is not shipped.
- **shark's badge "it actually trades"**: true, and it is the only project honest
  enough to say "the point isn't alpha".
