# Tools — what exists, and what question each one answers

One line per command. If a question below is one you are about to answer by
reading code or eyeballing the venue, there is probably already a tool.

## Is the machine alive and honest?

| command | answers |
|---|---|
| `python -m scripts.liveness` | **Are the loops actually running?** Heartbeat + OS process scan. A stopped loop reads exactly like a quiet market; this is the only thing that separates them. Exit 1 if not healthy. |
| `python -m scripts.night_guard` | Does night research stay off the execution surface? |
| `python -m scripts.preflight [--require-clean]` | **What state is this account in before the first order?** Equity, free capital, true max loss beside the flattering premium-paid view, effective N, largest thesis, latch, liveness. `--require-clean` refuses an account already traded into. |
| `python -m scripts.dashboard` | The one page a judge reads. Liveness first, then accounts, then concentration. |

## What is this book actually doing?

| command | answers |
|---|---|
| `python -m scripts.concentration` | **How many bets is this book making?** Effective N by RISK, weighted by true max loss — and which name costs the most diversification, which is often not the largest one. Calibrated against a real $20bn liquidation (1.43), not a round number. |
| `python -m scripts.reunderwrite` | **Would I open this position today?** Flags STALE (thesis finished, capital idle) separately from EVENT EXPOSED (thesis about to be decided) — and derives event exposure from the earnings calendar, because no brain tags one. |

## Did the idea work?

| command | answers |
|---|---|
| `python -m scripts.contagion --baseline` | Fit NVDA/SMH loadings **before** an event. Refuses to be useful afterwards, which is the point. |
| `python -m scripts.contagion --event YYYY-MM-DD` | Split an index move into mechanical / sector / behavioural. Read the SPY and QQQ rows — one-event MDE ~1.4%. Per-node MDE is 3.9%–20.8% and accumulates rather than concludes. |
| `python -m scripts.nvda_resolve --status \| --template \| --answers F [--read-move]` | Resolve a sealed state vector **from the release**, then read the price. The order is enforced in code. |
| `python -m scripts.fame_bias` / `fame_bias_report` | Does revealing a ticker change the score of identical numbers? Each condition drawn twice, because a difference between conditions is meaningless without the model's own noise floor. |

| `python -m scripts.elasticity --shock 1000` | **If this shock happens, who moves?** Elasticity = shock / revenue, so a $1bn revenue win is 328% for CORZ and 0.4% for NVDA. Ranking by market cap puts NVDA first. Non-USD reporters are excluded and NAMED, never FX-converted. |
| `python -m scripts.anchor_to_torque --event YYYY-MM-DD` | **The mega-cap is the sensor; which name is the expression?** Composes contagion betas x elasticity x coverage x residual. Shadow only, and it prints its own MDE every run. |

## Is the evidence real?

| command | answers |
|---|---|
| `python -m scripts.analyst_panel` | Capture today's PIT slice: recommendation counts by period, net breadth and its delta, market cap, industry, price features. Runs daily at 17:30 ET as `AegisAnalystPanelDaily`. |
| `python -m scripts.analyst_panel_calibrate` | **Run this before trusting the panel.** Coverage rises with size, sell-side optimism present but not saturated, breadth tracks momentum, zero coverage stays None. A failure invalidates everything downstream. |

| `python -m scripts.depreciation_gap` | **Is accounting useful life being stretched?** PP&E / depreciation from SEC XBRL. Flags missing years, and runs Apple as the control that stops a clean AI narrative. |

| `python -m scripts.needs_graph` | **Which layer of the build-out has pricing power?** revenue growth AND margin expansion, jointly. Says out loud when its own binary fails to discriminate. |

## Modules worth knowing

| module | why |
|---|---|
| `alpha/concentration.py` | Effective N by risk + marginal contribution. |
| `alpha/liveness.py` | Heartbeat, and a PID probe that is **measured** — `os.kill(pid,0)` reports a dead process as ALIVE on Windows. |
| `alpha/escalation.py` | A warning may not print 53 times. WARN → ELEVATED → FAIL. No acknowledge verb, deliberately. |
| `alpha/epoch.py` | Ledger damage is **dated**, never repaired. |
| `alpha/alpha_budget.py` | Generation is free; promotion is rationed. Charged per cell LOOKED AT. |
| `alpha/spend.py` | A paid call must say what decision it can change. |

## Things these tools will tell you that are easy to forget

- The forward record in this repo is **two calendar days** old. No brain can be
  ranked against another yet (`FINDING_..._THE_SCOREBOARD_IS_TWO_DAYS`).
- `EVENT_NODE_CAP` counts **tags**, and no brain tags
  (`FINDING_..._THE_EVENT_CAP_COUNTS_TAGS`).
- Implied useful life is rising across big tech — **but Apple is up 85%**, so it
  is not cleanly an AI story (`FINDING_..._DEPRECIATION_IS_RISING_BUT_NOT_ONLY_AI`).
- Both books behave like **1.3–1.5 independent bets**
  (`FINDING_..._EFFECTIVE_N_BY_RISK`).
