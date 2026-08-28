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

---

## 10. ADDENDUM 01:45 ET — sources, models, and the mega-cap question, measured

### 10.1 The Bigdata.com replacement is already paid for: Alpaca's news feed

Measured on the staging key, `GET /v1beta1/news?include_content=true`:

| name | item | chars | lag after the call |
|---|---|---|---|
| MRVL | "Transcript: Marvell Tech Q2 2027 Earnings Conference Call" | 58,149 | ~90 min |
| ESTC / RBRK | "…Full Earnings Call Transcript" | 61,243 / 53,368 | same night |
| S / WDAY | guidance bullets ("Lowers FY2027 Adj EPS Guidance from … to …", "Sees Q3 Sales $2.515B vs $2.697B Est") | — | minutes |

Small caps included; it is Benzinga's wire, free on the paper data key. Polygon
adds Zacks/Motley Fool items with a sentiment tag; Finnhub's free tier gives
recommendation trends and the earnings calendar but **403s** on price targets
and upgrades; FMP is **402** (paid) on grades/estimates; SEC full-text search
403s without a proper User-Agent and is not needed for this.

**`scripts/transcript_digest.py` (TRANSCRIPT_DIGEST_v1)** reads the transcript
or the guidance bullets, asks DeepSeek for DECLARED fields (guide vs prior,
headline vs estimates, tone, direction claim, expected move, key numbers with
comparators, supplier/bottleneck mentions, what is observable in 3 sessions,
a falsifier, and a forced comparison with the after-hours move), and writes
`state/expectations/<date>/<SYM>.json` with sources, model, prompt hash and
cost. First run, nine printers, **9 calls / 65k prompt tokens / ~$0.02**:

| sym | AH move | text | guide | dir | move | conf |
|---|---|---|---|---|---|---|
| MRVL | −0.96% | transcript | raised | up | 10% | 0.90 |
| **S** | **−6.17%** | headlines | **lowered** | **down** | 6% | 0.70 |
| **WDAY** | n/a on feed | headlines | **lowered** (FY27 sales $10.64B→$9.94B) | **down** | 15% | 0.70 |
| ESTC / RBRK / ADSK / ULTA / GAP | n/a / +11.6% (GAP) | transcript | raised | up | 5% | 0.7–0.8 |
| AFRM | n/a | transcript | none | up | 5% | 0.70 |

It is expectation data. It places nothing. Its job is to let a human state a
thesis with a falsifier before the open instead of from a headline.

### 10.2 The NVIDIA key and the Hugging Face token — what they actually reach

- **NVIDIA Build (`NVIDIA_API_KEY`, Aegis `.env`)** is live: `/v1/models` lists
  ~40 models including `deepseek-ai/deepseek-v4-pro-0813`, `-v4-flash-0731`,
  `moonshotai/kimi-k3`, `google/gemma-4-31b-it`, `minimaxai/minimax-m3`.
  `kimi-k3` answered in **2.3 s**; the two DeepSeek-V4 models **timed out at
  90 s** (queued free tier). Several names from the doc (`llama-3.3-70b`,
  `nemotron-ultra`) are **410/404 — gone**.
- **HF Inference Providers (`HF_TOKEN`)**: live, account is free/prepaid
  (`canPay: false`). `deepseek-ai/DeepSeek-V4-Flash` answered in **1.5 s**;
  `openai/gpt-oss-20b` is 403 (provider not enabled); `Qwen3.6-35B-A3B`
  returned an empty choice.
- **The HF *model* the project runs is FinBERT** (`ProsusAI/finbert`, local
  transformers, CPU) inside `backend/services/sentiment_analyzer.py` — headline
  sentiment for the website, keyword fallback if it fails to load. It has no
  role in the competition engine.
- `backend/services/model_provider.py` already wraps all three behind ONE
  OpenAI-compatible contract; its `status()` reads `absent` unless
  `backend.config` has loaded `.env` first — a probe artefact, not a bug.

**So the NVIDIA key helps as a second, cheaper/faster reader** for the digest
(kimi-k3 at 2 s vs DeepSeek's 4 s and a different training set — a genuinely
independent second opinion on the same transcript, which is what
`DISAGREEMENT` needs). It is not a data source, and none of these models gets
trading authority. `--provider nvidia` is the next flag on the digest.

### 10.3 The mega-cap fixation is structural, and here is the number

`scripts.candidates --sessions 3` over the 4,634-name universe:

    CANDIDATES (1) -- post_event_drift; 75 printers declined
    UNIVERSE AUDIT: UNIVERSE_COLLAPSE  old-universe share 100%, mega share 100%

One name — NVDA. The only brain with authority is two-sided on eleven
mega-caps because that is where it was measured; outside them an UP print has
no edge (2,532 names) and a DOWN print is only paid as a **pair** (short the
loser / long IWM: +0.35% / +0.26% per 3 sessions, t 2.2 / 2.0 in simple
returns; the unhedged short is +0.04%, nothing). The engine has no pair
structure, so the wide DOWN side is refused by design. That is the whole reason
the book keeps ending up in mega-caps: not preference, absence of an
instrument.

**Two routes out, ranked:**

1. **Now (no code on the write path):** the digest → `scripts.thesis` →
   engine. A human thesis "S down 6% over 3 sessions, falsifier: closes above
   the pre-print close" enters the runner under the same claim matrix and
   enumerates `short_shares` / bear put spread; the sizer, the −3% latch and
   the node cap still bind. S and WDAY are the day-one candidates, and both
   are outside the eleven.
2. **After day one (touches the write path — not at 01:45 ET before a live
   open):** `PAIR_SHORT_VS_IWM` as a first-class structure. Touchpoints, so the
   next session does not rediscover them: `alpha/engine/equity.py` (new kind,
   two legs, stress charge on the spread not the leg), `runner.build_order`
   (two equity orders per structure, one decision id, legs recorded),
   `alpha/book.py` (reconstruct a pair from two `us_equity` positions),
   `alpha/exits.py` (close both legs, never one), `post_event_drift`
   (`WIDE_UNHEDGED_SHORT_ENABLED` stays False; a new `WIDE_PAIR_ENABLED`
   quotes `WIDE_HEDGED_IWM_SIMPLE`), and tests in `tests_smoke_equity` /
   `tests_smoke_pead` / `tests_smoke_book`.

### 10.4 The investing strategy, in one paragraph, for the week and after

For the five sessions: **beta is the floor, not the plan** — SPY/QQQ/IWM shares
entered MOC with a call-debit sleeve to satisfy the options requirement, sized
by the tournament mode. On top of it, every dollar of max-loss budget is
auctioned to **dated, non-consensus, falsifiable** opportunities: the
post-print drift where it is measured (mega-11, +1 open, now reachable), the
**wide-universe DOWN prints as pairs** once the structure exists, and **human
theses stated before their catalyst** with a falsifier — fed by the firm's own
words (the digest) rather than by headlines. Rank on the median in BASE, on EV
in ATTACK. Direction disagreement → shares or debit spread; magnitude
disagreement → premium; never a sign-blind structure for a directional view.

After the week, the same machine is the research programme's front end: the
digest packets are the first non-price, non-mega-cap information source the
project has had that arrives *before* the drift window opens, and grading
`direction_claim` against realised 3-session moves over a few hundred prints
is a real, cheap, cross-sectional test of whether management's words carry
information the price has not yet absorbed — on the whole market, not eleven
names.

---

## 11. ADDENDUM 03:45 ET — the council, the pair, and what the guards cost

### 11.1 Built in this window (all read-only unless stated)

| lane | status | receipt |
|---|---|---|
| **SURPRISE_CUBE_v1** | built, code not model; 17 checks | `alpha/council/roles.py`, `tests_smoke_council.py` |
| **RESEARCH_COUNCIL_v1** | built; 5 roles across **4 model families** (deepseek / moonshot / minimax / zhipu); skeptic never shares weights with the synthesiser; per-role fallback across live rows | `alpha/council/`, `scripts/council.py` |
| primary source | **EDGAR full-submission `.txt` → Exhibit 99.1** (the folder index did not list the exhibit for S or WDAY) | `alpha/sources/sec.press_releases` |
| **PAIR_SHORT_VS_IWM** | built on the WRITE PATH (worktree, merged): one decision id, two equity legs, joint stress, leg-2 failure flattens leg 1, book/exits/protect handle both legs; **38 checks** | `alpha/engine/equity.py`, `tests_smoke_pair.py` |
| no-chain pairs | a wide printer with no listed options (LUCK, P, DY, HQY) no longer errors: the chain is optional for a pair | `runner.evaluate` |
| **GUARD_CLASS_v1** | registry of 28 guards: HARD / EMPIRICAL / TOURNAMENT / RETEST_DUE, each with scope and `reopens_when` | `alpha/guards.py` |
| **REFUSAL_REGRET_v1** | prices every refused world in the counterfactual ledger by guard (1,062,527 rows → 6,667 distinct refusals) | `scripts/refusal_regret.py`, `state/refusal_regret.json` |
| **EARNINGS_DISLOCATION_v1** | shadow scan: light council on recent printers, four quadrants of cube-vs-reaction | `scripts/dislocation_scan.py` |
| ATTENTION_ROUTER | `council(light=True)` = facts + expectations + cube; `--deep N` runs the full council on the most dislocated | same |

### 11.2 What the council said, versus what the digest said

| name | one-shot digest (01:30) | council cube (03:20) |
|---|---|---|
| **S** | "guide lowered → down" | revenue guide **+0.4%**, operating income **+5%**, EPS **−11.4%**, share count **+3.1%**; direction `down`, p_priced 0.72 |
| **WDAY** | "$10.64B → $9.94B cut" | subscription revenue FY27 **+0.08%** (maintained), operating margin **+1.6%** (raised); the total-vs-subscription pair listed **INCOMPARABLE** |
| MRVL | up, 10% | 0 comparable cells (no consensus with matching basis) → synthesis forced `none` |

The cube refuses to subtract unlike quantities; that is the whole fix. The
`basis_assumed` flag marks cells where a headline's "vs $X Est" carried no
GAAP/non-GAAP basis.

### 11.3 The pair: built, reachable, and correctly refused — for now

Recomputed from the 25,856-leg receipt in SIMPLE returns as the structure is
actually paid (short leg −(e^r−1), hedge leg e^r−1), DOWN prints:

| band | n | hedged mean / 3 sessions | sd | t |
|---|---|---|---|---|
| 5–8.2% | 2,133 | **+0.21%** | 7.19% | **1.34** |
| >8.2% | 3,790 | +0.10% | 8.22% | 0.79 |

Weaker than the +0.35% / t 2.2 constant the brain carried (a different cut).
Either way a +0.2% centre on a 7% sd is a **breadth claim** — it pays over
hundreds of legs, never on one — and the per-name MDM gate refuses it
correctly (BURL, ZM tonight: "+1.4–2.4% of probability mass below the 5pp
floor"). The pair stays **enabled** so every refusal is marked by the
counterfactual ledger; basket sizing is the research item. Nothing was forced
through at 3 a.m.

### 11.4 What the guards cost — the first measurement

`scripts.refusal_regret`, parallel worlds at $5,000 risk, last mark per decision:

| class | n | saved $ | cost $ | net $ |
|---|---|---|---|---|
| TOURNAMENT (book limits, latch, one-per-underlying) | 3,055 | 4,740,466 | 2,506,705 | **+2,233,761** |
| EMPIRICAL (the MDM floor) | 2,676 | 1,842,628 | 2,688,877 | **−846,249** |

The EMPIRICAL line is the one Murat is worried about, and it looked damning:
64% of what the floor refused would have won. Then by *how far below 5pp*:

| edge bucket | n | win% | net $ |
|---|---|---|---|
| 0–1pp | 85 | 29% | +88,873 |
| 1–2pp | 185 | 33% | +125,603 |
| 2–3pp | 176 | 30% | +31,456 |
| 3–4pp | 190 | 27% | −121,943 |
| 4–5pp | 155 | 26% | −67,308 |

Win rate is 26–33% *everywhere*; the positive net is **long_call +$685k (72%
hit) against long_put −$563k (5% hit)**, all marked on 28 Aug after CRM +22%,
SNPS +13%, CRWD +20%, NVDA +9%. That is the tape's sign, not the gate's. Not
evidence to lower the floor; recorded on the guard as its `reopens_when`
(win% rising toward the floor on ≥ 2 regimes). **The doctrine held under the
pressure to relax it, and it held because the number was computed.**

### 11.5 Agents: what each has earned the authority to do (as of 03:45 ET)

| role | provider (family) | measured | authority |
|---|---|---|---|
| FACT ACCOUNTANT | deepseek (deepseek) → hf DeepSeek-V4 fallback | S: 5 comparable cells from the 8-K; WDAY: 2 | write facts; **no direction** |
| EXPECTATIONS | nvidia kimi-k3 (moonshot) | consensus rows from headlines; timed out once on a 10k prior release → fallback | write reference rows |
| SURPRISE CUBE | code | 17 checks incl. the S and WDAY regressions | the only thing allowed to subtract |
| CAUSAL | nvidia minimax-m3 (minimax) | 3.9 s; edges with sign+lag | candidate names for the scout, ungraded |
| SKEPTIC | hf GLM-5.3-Flash (zhipu) | p_priced 0.72–0.75 on S/WDAY | can lower a thesis vector's weight; ungraded |
| SYNTHESIS | deepseek | forced `none` when the cube is empty (MRVL) | a thesis VECTOR for a human; **no order path** |
| HISTORICAL / MARKET | code | band-keyed lookups | reference only |

No LLM has broker authority (pinned: `tests_smoke_council` asserts the council
package imports no broker code). Track records per role start accruing today;
none has one yet, and the roadmap will not pretend otherwise.

### 11.6 What can trade at kickoff, what stays shadow

- **Trades (attended / loop):** beta core (`competition_book`, human sends);
  `post_event_drift` on the mega-11 at the +1 open (NVDA today, `long_shares`
  under the median ranker); human theses via `scripts.thesis` → seed → loop.
- **Enabled, expected to be refused, regret-marked:** the wide-universe DOWN
  pair.
- **Shadow only:** council packets, dislocation quadrants, causal edges, the
  four sentinel-quarantined brains.
- **Tournament risk mode:** BASE (need 0.40%/session to a +2% target).

Freeze of write-path code: **after the 09:30 ET staging fill is reconciled**,
and before the judged account is created.

### 11.7 The bakeoff, and the first dislocation table (05:10 ET)

`scripts.role_bakeoff --role fact` — five guidance rows per release from the
EX-99.1 answer key, ranges compared low-to-low and high-to-high:

| provider | family | S | WDAY | latency | note |
|---|---|---|---|---|---|
| hf DeepSeek-V4-Flash | deepseek | **5/5** | 4/5 | ~30 s | missed Q2 non-GAAP EPS once |
| deepseek-chat | deepseek | — | 5/5 | ~10 s | intermittently DOWN tonight (connection resets) |
| GLM-5.3-Flash | zhipu | 0/5 (truncated JSON) | 4/5 | ~14 s | fine on short text, not on a 30k prompt |
| minimax-m3 | minimax | 0/5 | 0/5 | 60 s timeout | not a reader |
| kimi-k3 | moonshot | refused | refused | — | not a reader; fine for EXPECTATIONS (short prompts) |

`ROLE_PREFERENCES["fact"]` now follows the table. This is the pattern for every
role: an answer key, a score, then an assignment — never the reverse.

`scripts.dislocation_scan` on four printers (light council, ~$0.01):

| sym | cube net | cells | reaction | quadrant |
|---|---|---|---|---|
| **S** | −0.029 | 5 | −6.2% | CONTINUATION_VS_OVERREACTION |
| RBRK | +0.25 (capped; EPS guide $0.30→$0.50, FCF +10%, rev +2.8%) | 6 | n/a | NO_REACTION_YET |
| ESTC | +0.065 | 6 | n/a | NO_REACTION_YET |
| WDAY | +0.017 | 2 | n/a | NO_REACTION_YET |

The reaction column fills at 09:30. **RBRK** is the name to watch at the open:
the strongest across-the-board raise of the night, outside the eleven, with no
observable after-hours print on our feed. If it opens flat, that is the
UNDER_REACTION quadrant and a human thesis candidate; if it gaps, it is
CONTINUATION_VS_PRICED and the historical analog says UP prints outside the
eleven carry no excess. Either way the packet, not a headline, is the reason.

### 11.8 Not done, honestly

- **Tournament risk frontier** (review item 9): not simulated. `mode_for`'s
  1.5%/session ATTACK threshold and the 30%/6%/3-entry caps are inherited
  policy. The regret report shows the caps SAVED +$2.2M net in the parallel
  worlds, which argues for keeping them through day one and simulating after.
- **Agent track records**: the scaffolding exists (every packet carries the
  provider per role); zero graded outcomes yet. First grades after +3 sessions.
- **Basket sizing for the pair**: research item; the pair is enabled and
  refused per name.
- **Staging fill / reconcile / restart** at 09:30 ET; freeze of write-path
  code after that and before the judged account exists.

---

## 12. ADDENDUM 06:10 ET — validation by backtest: two ideas die, one survives, one is bounded

### 12.1 Overnight-only ETF core — REFUTED as a 5-session strategy (2022–2026)

The 32-year finding says close→open is the segment that pays. Tested as the
thing it would have to be in this contest — hold overnight, flat intraday, 1bp
round trip, every 5-session window since 2022 (Alpaca daily bars):

| | overnight-only vs buy&hold, per 5 sessions | hit | t |
|---|---|---|---|
| SPY, n=1,161 | **−0.16%** | 43% | **−3.05** |
| QQQ | −0.17% | 45% | −2.36 |
| IWM | −0.08% | 49% | −1.10 |
| SPY, last 60 windows only | +0.36% | 65% | +2.13 |

Intraday was **positive** in 2025 and 2026 YTD on all three (SPY +7.9% / +4.3%);
only the last three months invert it. A 60-session window is one regime. The
tilt stays what it was — **enter MOC, hold** — and flattening at the open is
not deployed. (Both OPG order shapes were probed and accepted on staging, so
the refusal is on evidence, not on plumbing.)

### 12.2 SUE × reaction quadrants on CRSP 2013–2024 — the dislocation hypothesis REFUTED, continuation survives

`scripts/sue_dislocation_backtest.py` (Aegis repo): 116,231 announcements with
a pre-announcement IBES consensus (≥3 estimates), SUE = (actual − last median
estimate)/price, reaction = print session + next (excess vs EW market),
forward = the next 3 sessions excess. Receipt
`backend/data/optimus/sue_dislocation_2013_2024.json`.

| SUE quintile × reaction | n | mean fwd | median | hit | t (pooled) | t (week blocks) |
|---|---|---|---|---|---|---|
| best × **down** ("under-reaction") | 6,048 | −0.02% | −0.20% | 48% | −0.16 | −1.74 |
| worst × **up** ("delayed downside") | 5,470 | **+0.38%** | +0.03% | 50% | 3.47 | 2.40 |
| best × up (continuation) | 12,324 | **+0.41%** | +0.11% | 51% | **6.14** | **2.49** |
| worst × down (continuation) | 12,784 | −0.13% | −0.29% | 48% | −1.82 | −0.55 |
| best SUE alone | 23,246 | +0.24% | — | 50% | 4.90 | **0.01** |

Three readings, all of which change the plan:

1. **The disagreement quadrants do not pay.** "Good surprise, bad reaction"
   is flat-to-negative; "bad surprise, good reaction" continues *up*. The
   price reaction carries the information, not the disagreement. The
   `EARNINGS_DISLOCATION_v1` ranking, as hypothesised, is **refuted on 12
   years** and stays shadow; its quadrant labels are renamed in the next pass.
2. **Continuation is real and it is a right tail.** Best-SUE-and-up: +0.41%
   mean, +0.11% median, t 2.49 on week blocks. By size the MEDIAN is +0.31%
   with 54% hit in **large** caps, +0.03% in small caps (whose +0.56% mean is
   a tail). Under the terminal-wealth rule the large-cap cell is the
   tradeable one — which is the mega-11 finding, reproduced on 1,813 events.
3. **Pooled t lies here.** SUE-alone t 4.90 pooled becomes **0.01** on week
   blocks: earnings cluster, and same-week prints share a market. Every
   number this project quotes on prints must be blocked by week.

### 12.3 The risk frontier — small sleeve, not a big one

`scripts/risk_frontier.py`: beta core bootstrapped from 1,162 real SPY
five-session windows; call-debit-spread sleeve **parametric on the
OptionMetrics receipt's moments** (n=884, mean +3.3%, sd 47.6%, hit 51%),
drawn on the same market path. Target +2%, floor −5%:

| option budget | P(≥ +2%) | P(≤ −5%) | median |
|---|---|---|---|
| 0% (core only, 100%) | 18.7% | 2.1% | +0.41% |
| **5% + 60% core** | **42.8%** | **2.1%** | −0.03% |
| 10% + 60% core | 48.6% | 21.7% | −0.89% |
| 20% + 60% core | 49.4% | 47.6% | −2.33% |
| 30% + 60% core | 49.5% | 49.6% | −3.52% |

P(target) saturates near 49% by a 10% budget; every dollar above buys only the
left tail. **The 30% defined-risk cap is far above the frontier; 5–10% is
where the sleeve earns its place.** Read the ordering, not the decimals — the
sleeve is parametric.

### 12.4 What the field looks like (Exa, 28 Aug)

- This hackathon: LinkedIn post says **$5,000, 3 winners + 2 social-engagement
  awards; judging "P&L and creativity or engagement"; submission = dedicated
  $100k account + one-page write-up (AI logic, risk gates, Alpaca infra) +
  options in the strategy.** The write-up is a deliverable; `docs/WRITEUP.md`
  must be regenerated from tonight's receipts.
- Most-starred: TradingAgents (~100k ★, LLM roles + bull/bear debate + a
  decision log with reflection injected into the next run), ai-hedge-fund
  (~63k ★, 14 investor personas; does not trade), FinRL-X (weight-centric
  pipeline, Alpaca execution). An Alpaca-published multi-agent build uses
  five isolated lenses → critic → **human gate** → deterministic risk guard.
  None of them price their own refusals, seal an account's birth, or run a
  real-quote replay against their own design. That is the differentiator, and
  it should be the first paragraph of the write-up.

### 12.5 What this changes for kickoff

- Beta core stays; the options sleeve is sized **5–10%** of equity, not 30%.
- `post_event_drift` on the mega-11 at the +1 open is corroborated by an
  independent 12-year, 1,813-event large-cap cell (median +0.31%, 54%).
- No overnight flattening. No dislocation capital. Small-cap continuation is
  a tail, not a median — a research lane, not a contest lane.
