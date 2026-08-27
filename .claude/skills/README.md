# Skills installed here, and the two things the upstream ones do not know

`alpaca-paper-trading` and `alpaca-backtest` are vendored verbatim from
[`alpacahq/alpaca-skills`](https://github.com/alpacahq/alpaca-skills) at commit
`62891ec` (2026-08-25), Apache-2.0 (`ALPACA_SKILLS_LICENSE`). Do not edit them in
place — re-vendor from upstream and re-apply this file's deltas, so the diff
against upstream stays readable.

They are good skills. They are also written for a **fresh** workspace, and this
one is not fresh. Two things will be wrong if they are followed literally.

## 1 — the credentials are NOT `APCA_API_KEY_ID`

The skills say to read `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY`. Nothing in this
repo sets those. Credentials are **per account role**, in `.env`:

| role | key id | secret |
|---|---|---|
| `dev` | `AAT_DEV_KEY_ID` | `AAT_DEV_SECRET_KEY` |
| `exp1` | `AAT_EXP1_KEY_ID` | `AAT_EXP1_SECRET_KEY` |
| `competition` | `AAT_COMPETITION_KEY_ID` | `AAT_COMPETITION_SECRET_KEY` |

Resolve them with `alpha.config.credentials(role)` — never by reading `.env`
directly, and never by falling back to ambient environment variables.
`config.credentials` **refuses** inherited parent-process keys on purpose
(`tests_smoke.py`: "does not inherit parent keys"), because a key that arrives
from the environment is a key nobody chose.

`AAT_TRADING_BASE` is `https://paper-api.alpaca.markets`. The upstream hard block
on live credentials stands and is correct — keep it.

## 2 — an order that skips the ledger did not happen

The upstream skill's flow is *preview → confirm → submit via any SDK*. In this
repo that last step is wrong. Every order must go through the existing path:

```
alpha/runner.py      decide, size, and refuse
alpha/fills.py       submit, then audit the fill against the decision quote
alpha/ledger.py      append a hash-chained row
```

A raw REST submission produces a position with **no decision row, no forecast,
no refusal reason, and no fill audit** — so `scripts/pnl_attribution`,
`scripts/counterfactual` and `scripts/daily_autopsy` cannot see it, and the
chain hash silently stops covering the book. Use the upstream skill for its
**preview, confirmation and reporting discipline**; use this repo's code for the
verb.

Before any order on a competition account, `python -m scripts.preflight
--require-clean` and `alpha/book_limits.py` are the local equivalent of the
skill's "risk controls" row — and note they currently **report** rather than
refuse.

## 3 — what the backtest skill should be pointed at

`alpaca-backtest` writes its own workspace scripts. That is fine for a one-off,
but this repo already has a replay harness with costs, delisting and next-open
fills (`scripts/*_backtest.py`, and the parent project's
`backend/services/portfolio_farm/`). Prefer extending those; a second backtester
with different cost assumptions is how two numbers that disagree both become
quotable.

Its required-disclosure block is not boilerplate to skip — a backtest reported
without it is exactly the "explaining a winner afterwards" failure the strategic
invariants name.
