# ROADMAP — 28 Aug 2026, session 19: the loop leaves the laptop, the probe goes live, the ranker follows the mode

*Written ~00:30 ET on 28 Aug, eleven hours before kickoff (15:00 UTC / 11:00 ET).
Supersedes the operating parts of `NEXT_SESSION_2026-08-28_EXECUTE.md`; the
evidence table there still stands and is not repeated.*

## RESULTS SCOREBOARD

| item | value |
|---|---|
| competition equity | **no judged account yet** — created at kickoff by Murat |
| staging account (rehearsal) | `PA3HSRGSPXAY`, $100,000.00, level 3, 0 positions, 0 open orders (six probe orders sent and cancelled) |
| best forward paper strategy | none demonstrated; beta + drift on eleven names is what we own |
| independent selector count | 1 with authority (`post_event_drift`); 4 shadow (`vol_gap`, `narrative_dispersion`, `options_attention`, `relay`) |
| trades placed / refused this session | 6 probe orders placed and cancelled; 0 positions; 0 book trades |
| new actionable finding | **the drift brain could never take its best-measured entry** (below) |
| external execution drag | not yet measured on staging (fills need the open) |
| LLM spend | DeepSeek balance **$14.96**; Bigdata.com connector **out of credits** |
| **RESULT IMPROVEMENT** | **P&L capability, not P&L**: the loop now runs from Railway, every order shape is venue-proven, and day one produces a forecast where yesterday it produced zero |

## 1. THE QUESTION ASKED DIRECTLY: does the PC have to be on?

**Until tonight: yes.** Both loops (`dev`, `exp1`) ran under `nohup` on this laptop
and died with it. `railway.toml` and the `Dockerfile` were prepared on 26 Aug and
**never deployed** (`docs/HANDOFF.md` §"Railway (still yours)"). The Aegis backend
on Railway (`selfless-courage` / service `Aegis-Finance`) is the website; it has
never placed an Alpaca order for this repo and is not supposed to.

**From tonight: no.** The loop is a Railway service — project `loving-elegance`,
service **`aat-loop-staging`**, volume `aat-loop-staging-volume` mounted at
`/app/state`, image built from this repo's `Dockerfile`. It cycled within a
minute of deploy, regenerated `window_universe.json` on the volume, and is
running `--live` against the **staging** account with
`--profile conservative --brains post_event_drift --window-universe`,
expiry `2026-09-04`.

One service per ACCOUNT ROLE; the role is a Railway variable, the image is the
same. To bring the judged account up at kickoff:

```
railway add --service aat-loop-competition
railway volume add -m /app/state                    # while linked to that service
railway variables --service aat-loop-competition --skip-deploys \
   --set AAT_ACCOUNT_ROLE=competition \
   --set AAT_COMPETITION_KEY_ID=... --set AAT_COMPETITION_SECRET_KEY=... \
   --set AAT_LEDGER_DIR=/app/state --set AAT_LOOP_EXPIRY=2026-09-04 \
   --set AAT_LOOP_BRAINS=post_event_drift \
   --set "AAT_LOOP_ARGS=--profile conservative --window-universe" \
   --set AAT_TRADING_BASE=https://paper-api.alpaca.markets --set AAT_DATA_BASE=https://data.alpaca.markets \
   --set AAT_OPTIONS_FEED=indicative --set AAT_STOCK_FEED=iex --set AAT_RISK_PROFILE=aggressive \
   --set AAT_DEEPSEEK_API_KEY=... --set AAT_FINNHUB_API_KEY=... --set AAT_FRED_API_KEY=...
git add docs/seed/genesis_competition.json && git commit      # AFTER genesis --freeze on the laptop
railway up --service aat-loop-competition -d
railway logs --service aat-loop-competition
```

Three facts about this hosting that will bite if forgotten:

- **The volume is the ledger; the repo is the seed.** `docs/seed/` is copied
  into `/app/state` with `cp -rn` on every start and never overwrites. The
  genesis record and the whole-market universe travel that way. The laptop's
  1.3 GB `state/` is `.dockerignore`d and must stay so.
- **Never run one role from two hosts.** The laptop `exp1` loop is still running
  (its six option positions expire today at the close and something has to
  manage them). `dev` was STOPPED tonight — its key has returned **401** since
  before this session and the loop cycled HEALTHY against it for 1,073 cycles.
  *A dead credential reads exactly like a quiet market.* Heartbeat retired.
- **Liveness is on the volume, not on the laptop.** `railway logs` is the
  heartbeat until a `/liveness` line is exported; `python -m scripts.liveness`
  on the laptop cannot see the Railway roles.

## 2. VALIDATED TONIGHT (receipts, not claims)

| check | result | receipt |
|---|---|---|
| test suite | 38 suites / **1,228 checks ALL PASS** after fixes | `run_tests.py` |
| `tests_smoke_equity` | was FAILING on 28 Aug: hardcoded an expiry that arrived — dates are now relative | commit |
| execution probe LIVE | **first ever.** equity limit / MOC / LOC, single-leg option, multileg DEBIT and CREDIT spread (level 3) all `accepted`, all cancelled, 0 left | `state/evidence/execution_probe_staging.json` |
| account mapping from the venue | staging clean; exp1 `PA3AOJPJTSBW` 6 pos / 18 orders legacy; pead clean; market legacy (1 expired OPG) | `scripts.accounts` |
| WRDS | connects; **IBES `recddet` has 0 rows since 2026-08-20** — it lags weeks. Historical calibration only, never live reaction | probe |
| DeepSeek | live, $14.96 | `/user/balance` |
| Bigdata.com MCP | **credits exhausted** — no broker research from it until topped up | tool error |
| Railway loop | cycling on the volume; `candidates` needed the universe file → now seeded | `railway logs` |

## 3. TWO CHANGES TO THE ENGINE, BOTH PINNED BY TESTS

### 3.1 The drift brain could never take the +1 open

`post_event_drift.forecast` counted `elapsed` = bars after the event bar and
refused `elapsed == 0` as "still forming". But `elapsed == 0` is precisely
**day-0 closed, +1 open not yet reached** — the arrival the receipt
(`state/source_pead_horizon.json`) scores highest: **+1.08% / t 2.82 / hit 62%**,
three sessions of window. The brain therefore only ever traded a full session
late (+0.72%, t 2.17). Tonight at 00:10 ET the dry pass declined SNPS, VEEV,
CRM, TITN as "still forming" for a session that had closed eight hours earlier,
and produced **zero forecasts**.

Fix: `_bar_is_closed(client, day)` asks the **venue clock**. A bar is closed if
its date is before today's ET date, or it is today and the venue reports closed
after 16:00 ET. Clock unavailable → the old behaviour (closed only if before
today). `ARRIVAL[0] = (0.0108, 0.0448, 3.0)`; the sd floor is the sd of
`sign*(d1+d2+d3)` over the same 108 rows, which reproduces the existing 2- and
1-session floors (0.0353 / 0.0259 vs 0.0345 / 0.0255) by the same arithmetic.
Conviction is full at arrival 0 and 1, haircut at 2. Eight tests.

After the fix the dry pass forecasts **NVDA** (+8.8% on 27 Aug, over-extended
band, conviction 0.6). CRM/SNPS/CRWD/OKTA/VEEV remain refused for the right
reason: UP prints outside the eleven names carry no edge (2,532-name receipt).

### 3.2 The ranker follows the tournament mode

`runner._ev_ratio` ranked on the arithmetic mean, and the 27 Aug finding showed
what that buys: NVDA `long_call` +38% EV / **P(profit) 33% / median −$137** over
`long_shares` +12% / 56% / +$1. The finding declined to change the objective
hours before judging. Tonight it is changed, on the same grounds every refutation
this week rested on — *rank on terminal wealth* — and coupled to the switch that
was already pre-registered:

> `rank_objective(state)`: **BASE → median/max-loss; ATTACK → EV/max-loss.**
> `AAT_RANK_OBJECTIVE=mean|median` overrides and says so. `AAT_TARGET_PCT`
> (default 2) sets the target `mode_for` reasons against.

Same dry pass: `RANKED ON MEDIAN -- BASE: need 0.40%/session` → **NVDA
long_shares ×109, risk 1.44%**. If the book falls behind late, `mode_for` flips
to ATTACK and the same code buys the convexity. Five tests.

## 4. THE ACCOUNT QUESTION

Rules (25 Aug snapshot, §Account requirements): *"Use any paper account you like
during development"* / judged: *"create a brand-new Alpaca paper trading account
dedicated to this hackathon. Projects run on an existing or reused account
[are ineligible]"* / *"Starting balance must be set to $100,000."*

`PA3HSRGSPXAY` was created 28 Aug 03:42 UTC with exactly $100,000, before
kickoff. Whether "brand-new" means *after kickoff* is not stated. What IS stated
is *not reused* — and tonight six probe orders were sent to it and cancelled, so
it has an order history and **is legacy now by our own `genesis` rule** (which
refuses any order of any status). That was the right use of it: it is the
rehearsal account (`staging`), and the judged account is **the one Murat creates
at kickoff**, untouched until `genesis --freeze`. Add `PA3HSRGSPXAY` to
`genesis.DENIED_ACCOUNTS` when the competition role is wired.

## 5. THE FIRST HOUR AT KICKOFF (11:00 ET)

The old runbook's steps 1–6 stand. Changed or added:

1. Murat creates the account, options enabled, $100k. Keys → `.env` as
   `AAT_COMPETITION_*`. `python -m scripts.accounts --role competition` → `clean`.
2. `AAT_ACCOUNT_ROLE=competition python -m scripts.genesis --freeze --rules docs/RULES_SNAPSHOT_2026-08-27_REPULL.md`
   → copy `state/genesis_competition.json` to `docs/seed/`, commit, push.
3. Railway: create `aat-loop-competition` exactly as in §1. **Stop** the
   staging service first if the two would ever share a ledger path — they do
   not (separate volumes), but one writer per book is the rule.
4. `railway logs --service aat-loop-competition` until the first cycle prints
   `verified paper account PA…`. Under the `competition` role `run_pass --live`
   verifies genesis and exits 2 if it does not match.
5. Human theses: `python -m scripts.thesis --symbol … --direction up --expected-move 0.04 --catalyst … --catalyst-at … --horizon 3 --conviction 0.7 --reason … --falsifier …`
   Committed to `state/human_theses.jsonl` ON THE VOLUME, so run it with
   `railway ssh` or add a `railway run`-equivalent; interim: record on the
   laptop, and the entry pass picks it up when the file is synced to the seed.
   *(Open item — see §8.)*
6. The beta core is still **attended**: `AAT_ACCOUNT_ROLE=competition python -m scripts.competition_book`
   prints; a human sends. Enter shares MOC before 15:45 ET; option legs as
   marketable limits 15:30–15:55 ET.

## 6. THE CHATGPT MASTER CONTEXT — what is right and what to change

`~/Downloads/AEGIS_MASTER_CONTEXT_FOR_CLAUDE_2026-08-28.md` is a good synthesis
and most of it is already code. Specific corrections:

- **§1/§21 "do not collapse the two objectives"** — right, and now enforced:
  the ranker switches objective with `mode_for` (§3.2).
- **§20 fresh account genesis** — right; add: the staging account is legacy
  the moment it is probed (§4), so *probe on staging, never on the judged one*.
- **§28 OptionMetrics kill** — right. One nuance the doc drops: the refutation
  is of the *structure as a core*; a short put spread can still win an
  auction increment on a specific name/date if the live chain says so. It is
  not banned, it is not default.
- **§32 MOC for options** — right, and now *proven at the venue*: options
  accept `tif=day` only; `cls` on an option is refused locally before it can
  reach Alpaca.
- **§46 provider platform (NVIDIA NIM, HF, local llama.cpp)** — aspirational.
  Only DeepSeek is wired (`AAT_DEEPSEEK_API_KEY`); Aegis has the same single
  provider. Do not plan the week around models that are not connected.
- **§47 "Agent-Reach + Exa" / Bigdata** — Bigdata.com is out of credits;
  Exa MCP is available. Treat *any* retrieved research as *expectation data*,
  never as a forecast (the doc says this in §42 and it applies here too).
- **§49 "never idle"** — right, with one addition earned tonight: *idle work
  must not touch the objective function of a live loop mid-session.* The
  ranker change was made at 00:30 ET with eleven hours to kickoff and a
  full suite; that is the last moment such a change is allowed this week.
- **What the doc does not say and should:** the hosting (§1 above). A plan
  whose executor is a laptop is a plan with a single point of failure that
  has already failed twice (26 Aug DNS, 28 Aug dead key).

## 7. "DOWNLOAD THE ANALYSIS, NOT ONLY THE DATA" — what is possible this week

Murat asked for WRDS *analysis* (how researchers reviewed and analysed) and
firm research, digested by the built-in LLM. Measured constraints:

| source | live? | use |
|---|---|---|
| WRDS IBES (`recddet`, `statsum`) | **no** — 0 rows since 20 Aug | historical calibration of *how much analyst reaction predicts drift* (a real, unasked question — see §8.3) |
| WRDS OptionMetrics | daily, lags | done: the core refutation |
| Bigdata.com broker reports | **no credits** | top up → `bigdata_search` with `document_type INVESTMENT-RESEARCH` for the window names |
| SEC EDGAR 8-K Item 2.02 | yes, free | already the drift brain's event source |
| Finnhub recommendation trends / news | yes | expectation data for the window names |
| Exa web search | yes (MCP) | sell-side note *summaries* in press; provenance is weak |
| DeepSeek | yes, $14.96 | `alpha/narrative/extract.py` already asks for NUMBERS on declared axes, never a trade |

The lane that fits the week: **`EXPECTATION_DIGEST_v1`** — for each name in
`window_universe.json`, pull (Finnhub trends + recent news + latest 8-K), ask
DeepSeek for the *declared axes only* (what is expected on print, what would
surprise, what the chain implies), store as a `state/expectations/<sym>.json`
packet with source provenance, and mark it against the realised move. It is
expectation data feeding the human-thesis arm and the claim matrix. It does not
place orders, and it does not need Bigdata to start.

## 8. NOVEL, UNTRIED, AND CHEAP ENOUGH FOR THIS WEEK

Each carries the one question every intuition owes: *what observation would
separate this from beta?*

1. **The +1 open is the trade the engine could not take until tonight.**
   Not novel research — a defect — but it is the single largest P&L-capability
   change of the week, and its first live test is 09:30 ET today on NVDA.
   *Separator:* the drift over +1..+3 net of beta×QQQ, on the ledger row.
2. **Pair the wide-universe DOWN prints** (`short loser / long IWM`, +0.35%/3d,
   t≈2, the only wide-universe number that survived session 10). The engine
   has no pair structure; the venue does (two equity orders). ZM −7.4% on
   26 Aug was refused tonight for exactly this reason. *Separator:* the pair's
   return vs the unhedged short's, both on the ledger.
3. **Overnight-only expression of the beta core.** 32 years say close→open is
   the segment that pays (t +7.92); the runbook already says "enter MOC".
   The untried half is *exit at the open and re-enter at the close* for the
   ETF core — refused before on cost grounds (dies above ~1.5 bps round trip)
   but Alpaca paper charges **zero commission**, so the paper book can measure
   the pure overnight/intraday split for five sessions. *Separator:* overnight
   vs intraday P&L attribution per session — a number no judge has seen.
4. **Expectation digest as a pre-print state** (§7) on PANW (2 Sep) and AVGO
   (3 Sep), sealed before the print like NVDA's 13 fields were. *Separator:*
   which sealed field the market repriced on, ranked, as on 27 Aug.
5. **Ranking on the median in BASE and on EV in ATTACK** (done) — the
   counterfactual ledger already marks both; report the *regret of the
   objective* at contest end: what the mean-ranked book would have made.
6. **`credit_ratio` (+0.143/+0.174)** stays in the research programme.

Not this week: anything that adds a brain, a provider, or a data source that
is not already wired. Three events, five sessions, one writer.

## 9. OPEN ITEMS, RANKED

1. **Human theses cannot reach the Railway loop.** `scripts.thesis` writes to
   the ledger dir; on Railway that is the volume. Cheapest fix: a
   `docs/seed/human_theses.jsonl` that `cp -rn` seeds (append-only, no
   overwrite) — or `railway ssh` into the service to run the script. Decide
   before the first thesis.
2. **`exp1` positions expire today at 15:30 ET** and are managed by the
   *laptop* loop. Keep the laptop on through 16:00 ET today, or move `exp1`
   to Railway now (`--manage-only`, same recipe).
3. Fills on staging have not been observed — the probe ran with the market
   closed. The 09:30 pass is the fill test.
4. The ledger hash chain break of 25 Aug: still not to be repaired silently.
5. Bigdata.com credits.
