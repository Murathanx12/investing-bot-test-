# FINDING 2026-08-26 — a sweep of what others built, and six mechanisms tested on our own prints

**Licence:** `PRODUCT_EXPERIMENT`. Receipts in `state/`. Sample for every test: the 117 SEC-dated prints of `state/event_straddle_backtest.json` (12 names, 2024-02 → 2026-08), real expired-option daily bars.

## 0. RESULTS SCOREBOARD

**RESULT IMPROVEMENT: no P&L (market closed). Four new mechanisms tested; two refuted outright, two with a direction. One exit rule found for the live book.**

| mechanism | verdict | number | receipt |
|---|---|---|---|
| PRE_PRINT_IV_RAMP_v1 (long straddle T-5/T-3 → last close before the print) | **REFUTED, hard** | T-5: mean −19.5%, hit 11%, **t −12.9**; T-3: −10.1%, hit 20%, t −7.4; every name negative | `state/pre_print_iv_ramp.json` |
| PRE_PRINT_OPTION_FLOW_v1 (unsigned call−put volume, 3 sessions, 5 strikes) | dead in the coarse form | sign hit 44%, corr 0.00; Johnson-So O/S vs \|move\| corr −0.07 | `state/pre_print_option_flow.json` |
| EVENT_EXIT_TIMING_v1 (sell the pre-print straddle at the day-0 open vs close) | direction: **sell at the open** | 89% of the day-0 \|move\| is in the gap; holding the session −4.5% mean / −8.9% median (t −1.35); open beats close on 62% (+3.8%, t 1.06) | `state/event_exit_timing.json` |
| EVENT_CALENDAR_v1 (short front straddle through the print, long the back ≥21d, same strike) | direction, not significance | n=76, mean +5.5% of debit, median −7.4%, hit 49%, t 0.77; **steep-term-structure tercile +14.3% vs flat −8.9%**; NVDA **+35%/6** | `state/event_calendar.json` |

## 1. What the wild had (six repos cloned and read, scratchpad only)

| repo | what it is | what it taught |
|---|---|---|
| `IgorGanapolsky/trading` (772 py files) | "paper-first SPY options validation lab": trade gateway, kill switch, broker-backed ledger, 69 closed iron condors | **23.2% win rate, −$57/trade, 39 conditional cells, zero survive Bonferroni.** Their diagnosis: 53/69 closed inside 24h (collected no theta), avg win $70 < avg loss $98 (break-even win rate 58%), and the ledger never recorded VIX/IV-rank/regime at entry so the audit was blind. Their fix is a written hypothesis change before any resumption — the same rule as our recovery mode, arrived at from the other side. It is the most honest repo in the sweep and it has no edge. |
| `ProgramComputer/earnings-trade-automation` | the "Predicting Alpha" earnings calendar in production on Alpaca paper: ATM calendar, back month +30d, 10% Kelly | the screen is **front/45d term-structure slope negative + IV30/RV30 high + 30d volume**. No results published. We tested the trade (§EVENT_CALENDAR); the steep-slope tercile is where its mean lives. Its order code chases the mid with idempotent client ids and cancels-and-confirms — worth copying if we ever run multi-leg orders that do not fill at the limit. |
| `thunderscarf/SPX_0DTE_Options_Selling_Public` | 0DTE SPX credit spreads outside ½·VIX1D expected move, ADX/market-structure regime | the whole "edge" is the regime filter; nothing measured we can use pre-kickoff. |
| `brigoraoul/spy0dte-simulator` | 0DTE credit-spread backtester with MLflow | infrastructure, no mechanism. |
| `TauricResearch/TradingAgents`, `virattt/ai-hedge-fund` | LLM multi-agent debate frameworks (analyst/researcher/trader/risk personas) | **neither touches options**; both are narrative generators over price+news. Our `narrative_dispersion` already is one and it marks −4.2% of risk live. Copying their persona debate adds explanation, not edge, and the judge who marked Falcon down for "plausible narratives after the fact" would mark it down again. |

Competitor pitches on lablab (AgentTrade AI, LS101, AgentAlpha, Stormers) all read "autonomous agent analyses data, evaluates risk, explains, executes paper options". None names a mechanism. Ours names eight refusals.

## 2. What the literature had, and what our prints said back

- **Straddles around earnings** (Gao/Xing/Zhang: +3.34% T-3→T+1 in 1996-2013; BSIC 2011-2021: +1.17% gross, **−9.07% net**; "arbitrageurs have found this"). Our 117 prints: −0.3% mean, 43% clear break-even. Consistent: gone net.
- **Concave IV curves before prints predict negative straddle returns** (Review of Finance 2025). `alpha/surface.py` has the concavity measure; the earlier session found it reproduces the direction weakly.
- **Skew premiums are elevated around prints; risk reversals earn less on negative-skew names** (Financial Review 2026). Not tested — needs OTM bars per print; queued behind SURFACE_MOMENT_SHOCK.
- **Option volume before prints carries private information** (Johnson & So 2012; Ge, Lin & Pearson 2016). Tested in the only form daily bars allow — unsigned volume — and it carries nothing (hit 44%). The papers' signal is *signed* (buyer-initiated puts vs calls) and needs the tape or open-interest changes; the coarse null does not kill the fine version.
- **Day/night option-return asymmetry** (close-to-open option returns positive, open-to-close negative; the variance premium is a reward for overnight risk). Our prints agree in their own way: the gap carries 89% of the move and the session after it costs the long straddle 4.5%. **Rule for the book: an event structure is marked and, if long premium, exited at the first pass after the open — not at 10:45, not at the close.**
- **IV ramp before earnings** (retail canon: "buy 4-5 days before, sell before the print, profit from vega alone"). On mega-caps it is a theta donation — the implied is loaded in a week ahead, and the last three sessions cost 10% on average with an 80% loss rate. The strongest negative t this project has produced (−12.9).

## 3. What changes

1. `alpha/exits.py` / arbiter: a long-premium event structure's exit is the day-0 OPEN. (Rule recorded; the arbiter is still advise-only, so tomorrow it is a logged verdict, not an order.)
2. EVENT_CALENDAR earns a shadow candidate for NVDA: short the 28 Aug ATM straddle, long the Sep monthly at the same strike, entered the last close before the print — **not tonight** (the book is above every ceiling and calendars carry assignment risk the engine does not model).
3. IV ramp, unsigned option flow: `RETIRED_FROM_CURRENT_SEARCH`.

## 4. Rules carried forward

- **The wild's honest repos have no edge and say so; the dishonest ones have no numbers.** A cloned strategy is a hypothesis, and the 117 prints are the test.
- **Test the folk trade before the clever one.** The IV ramp cost nothing to test and produced the largest t of the week, negative.
- **Every straddle test must state its exit time.** Open and close are different trades.
