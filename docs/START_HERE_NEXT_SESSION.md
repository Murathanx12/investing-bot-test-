# START HERE — 2026-08-27, end of session 15

Read this before `docs/HANDOFF.md`. That file is the trading record; this one is
the machine you will run it on. Session 15's findings: `docs/HANDOFF_SESSION_15.md`.

---

## 0 — THE ONE-LINE STATE  (rewritten 2026-08-27 night)

> **THE AGENT COULD NOT HAVE TRADED, AND THAT WAS THE FINDING.** With `vol_gap`
> quarantined, a dry pass over the default universe produced **ZERO forecasts** —
> fifteen hardcoded mega-caps that all report in late July, against a +1..+3
> drift window. The judged account would have sat in cash for five sessions while
> P&L is criterion #1, and **refusing correctly and having nothing to refuse
> print identically**, so no test could see it.
>
> **REGISTER BEFORE 11:00 ET ON 28 AUG. Registration closes at kickoff.** New
> from the 27 Aug re-pull and absent from every earlier snapshot. Nothing else in
> any document matters if this is missed.

**Read in this order:** `docs/RUNBOOK_2026-08-28_KICKOFF.md` (the ordered
sequence for the morning) → `docs/HANDOFF.md` (the trading record) → this file
(the machine).

**RESULT IMPROVEMENT: NONE in P&L.** No strategy tested, no candidate promoted.
What moved is what the machine is allowed and able to do.

---

## 0b — WHAT IS ACTUALLY TRADEABLE, which is less than it looks

`python -m scripts.window_universe --json` → 95 names with an event reaching
inside the contest. But `post_event_drift` is two-sided on **eleven** names only,
and exactly **three** of them print in the window:

| | reacts | usable |
|---|---|---|
| **NVDA** | 27 Aug | day one only |
| **PANW** | 2 Sep | full |
| **AVGO** | 3 Sep | truncated, 2 sessions |

Each still needs its day-0 move to clear the flat-tercile floor, so **three is a
ceiling.** Outside those eleven names an UP print has no edge and a DOWN print
needs a pair structure the engine does not have.

**So the human thesis arm is the PRIMARY decision source**, not a supplement,
plus NFP on 4 Sep. `docs/FINDING_2026-08-27_THREE_EVENTS.md`.

---

## 0c — THE ONE DECISION LEFT OPEN

The champion ranker optimises the arithmetic **mean**. Measured on a live NVDA
chain it takes a `long_call` at **33% hit rate, median −$137** over `long_shares`
at **56%, median +$1**. Over five sessions terminal wealth follows the median
path. Three costed options in
`docs/FINDING_2026-08-27_THE_RANKER_OPTIMISES_THE_MEAN.md`; the runner now logs
`MEAN-RANKED` when it takes a sub-50% champion. **Deliberately not changed** —
editing the objective function of a system hours before judging is how a seventh
instrument defect gets made.

---

## 1 — WHAT IS RUNNING RIGHT NOW

| what | detail | rule |
|---|---|---|
| `agent_loop` **dev** (pid 17200) | `--manage-only`, cycling, 0 errors | **do not kill** |
| `agent_loop` **exp1** (pid 59544) | `--manage-only`, cycling, 0 errors | **do not kill** |
| optimus MCP × 2 | one per repo | expected |
| `llama-server.exe` | 4.9 GB VRAM, port 8080 | dies on reboot |

Both loops manage exits, fills and marking on the PRE_UNITS_FIX legacy books and
never open new risk. Both books hold options expiring **28 Aug**;
`exits.CLOSE_BEFORE_EXPIRY_ET` (15:30 ET) closes them, and that rule finally has
tests (`tests_smoke_expiry.py`) — dev holds a **short NVDA 225 call** whose
assignment would convert a 19-lot premium position into a 1,900-share stock
short overnight.

**A stopped loop reads exactly like a quiet market** — and so does a loop whose
entry pass exits 2 on every cycle, which is why `_run` now counts consecutive
non-zero exits and `liveness` reports DEGRADED with the step named.

**Accounts, read from the venue** (`python -m scripts.accounts`):

| role | account | equity | pos | ord |
|---|---|---|---|---|
| dev | `PA32Q5IW7TAS` | ~$83k | 6 | 29 |
| exp1 | `PA3AOJPJTSBW` | ~$96k | 8 | 16 |
| market | `PA3I7VTCC0BM` | $100,000.00 | 0 | 1 `expired` |
| pead | `PA3LY4QK3A6A` | $100,000.00 | 0 | 0 |
| **competition** | **does not exist** | — | — | — |

All four are denylisted in `alpha/genesis.DENIED_ACCOUNTS`, keyed on the
account number the venue returns.

---

## 2 — MODEL PROVIDERS: ALL FOUR LIVE

`backend/services/model_provider.py` (aegis-finance). One OpenAI-compatible
contract; a provider is a ROW, not a class.

```
python -m backend.services.model_provider           # environment only
python -m backend.services.model_provider --probe   # actually call them
```

| provider | model | measured |
|---|---|---|
| deepseek | `deepseek-chat` | live |
| nvidia | `openai/gpt-oss-20b` | live, ~2.0s |
| huggingface | `meta-llama/Llama-3.3-70B-Instruct` | live, ~1.9s |
| **local** | Qwen2.5-7B-Instruct Q4_K_M | **live, 56.4 tok/s gen, 977 tok/s prompt** |

**Five states, never collapsed:** `absent` · `configured` (a key exists — says
NOTHING about whether it answers) · `unprobed` (keyless, e.g. a local server:
nothing to configure, so a config read carries no information) · `down` · `live`.

**What `--probe` caught that reading config never would:**

1. the first NVIDIA default returned **HTTP 410 END OF LIFE dated 2026-08-26** —
   the day after it was written. NIM retires models on a date;
2. **being LISTED by `/v1/models` is not being callable** — of six candidates:
   two 410, one 404 not-available-to-this-account, three timed out, one answered;
3. `gpt-oss-20b` is a REASONING model. At `max_tokens=16` `content` came back
   EMPTY with only `reasoning_content` set; at 300 it answered in 120 tokens.
   **A small budget on a reasoning model reads exactly like a dead model.**

Deliberately **NOT a router** (that needs benchmark evidence that does not exist
yet) and **no trading authority**, per canon.

**The HF token is over-scoped** — fine-grained with `repo.write`, `job.write`,
`inference.endpoints.write` (the last two can incur GPU charges), `post.write`,
`user.billing.read`. This system uses exactly two: `inference.serverless.write`
and `repo.content.read`. Narrowing it is two minutes and worth doing on a machine
that also holds live broker credentials. Murat's call; flagged once.

---

## 3 — LOCAL INFERENCE: DONE AND VERIFIED

- **`C:\Users\mrthn\llama\bin\`** — llama.cpp b10645, **CUDA 13.3**.
- **`C:\Users\mrthn\llama\models\Qwen2.5-7B-Instruct-Q4_K_M.gguf`** — 4.68 GB.
- Start it:
  ```
  cd C:\Users\mrthn\llama\bin
  .\llama-server.exe -m ..\models\Qwen2.5-7B-Instruct-Q4_K_M.gguf ^
      --port 8080 --host 127.0.0.1 -ngl 99 -c 8192 --no-webui
  ```
- Verified: `CUDA0: NVIDIA GeForce RTX 5060 Laptop GPU (8150 MiB)`, **4934 MiB
  held by llama-server**, 56.4 tok/s.

**CUDA 13.3 and not 12.4 on purpose:** the RTX 5060 is Blackwell (sm_120),
needing CUDA 12.8+. The 12.4 build has no kernels for it and **falls back to CPU
silently** — fast enough to look like it worked.

`torch` here is `2.11.0+cpu`, so nothing torch-based can use the GPU. llama.cpp
does not need torch.

**It does not survive a reboot.** Making it always-on is a scheduled task and a
deliberate decision, not a default.

**Honest framing:** a local 7B is genuinely good for high-volume extraction,
classification, routing and filing-parsing, at zero marginal cost. It is **not**
a substitute for a frontier model on generating causal hypotheses and falsifiers.
And with HF serverless answering from a 70B in ~1.9s for free, local is a **cost**
lever, not a capability one.

---

## 4 — PLUGINS AND MCP

**Installed (17):** `agent-skills@addy-agent-skills` 0.6.7 ·
`ui-ux-pro-max@ui-ux-pro-max-skill` · `huggingface-skills` 1.0.25 · superpowers ·
code-review · plugin-dev · skill-creator · claude-code-setup ·
claude-md-management · context7 · playwright · supabase · github ·
security-guidance · frontend-design · vercel · explanatory-output-style.

`~/.claude/plugins/installed_plugins.json` is the ONLY truth. A marketplace in
`known_marketplaces.json` is NOT evidence its plugin installed.

**MCP (`.mcp.json`, both repos):** `optimus` (canon, postmortems, verified state,
skills across 3 roots) and `exa` (free whole-web semantic search —
`web_search_exa`, `web_fetch_exa`, no key). The terminal repo had no `.mcp.json`
at all until 27 Aug, so optimus was unreachable from sessions started there.

**CLI:** `graphify` 0.9.50 (`/graphify .` — an LLM-cost operation, not yet run) ·
`agent-reach` 1.5.0 (4/15 channels need no credentials: RSS/Atom, V2EX, any page
via Jina Reader, Bilibili; Twitter/Reddit/Xueqiu/LinkedIn need **browser session
cookies** and are deliberately NOT configured) · `mcporter`.

### Plugin installs TIME OUT — pre-clone locally

**"Wait for the clone" does NOT work.** `headroom` finished its clone, its
directory was cleaned up, and it **still never registered**. The installer times
out, reports failure, and abandons the result while the orphaned git process
keeps downloading for nothing. The only variable that predicts success is clone
time vs the timeout:

| repo | clone | registered? |
|---|---|---|
| ui-ux-pro-max (7.8 MB) | ~1 min | **YES** |
| ECC (46.7 MB) | ~5 min | no |
| headroom (74.8 MB) | ~8 min | no |

**Workaround** — nothing times out on a plain clone, and these manifests declare
`"source": "./"` so a local add does NOT re-clone:

    git clone --depth 1 https://github.com/OWNER/REPO.git C:\Users\mrthn\cc-plugin-src\NAME
    /plugin marketplace add C:\Users\mrthn\cc-plugin-src\NAME
    /plugin install PLUGIN@MARKETPLACE-NAME

`cc-plugin-src` is deliberately NOT under `~/.claude/plugins/` — the installer
manages that directory and deletes what it finds there.

**Already cloned and ready:** `cc-plugin-src\ECC`, `cc-plugin-src\headroom`
(clone completed; **footprint not yet measured — measure before installing**).

    /plugin marketplace add C:\Users\mrthn\cc-plugin-src\headroom
    /plugin install headroom@headroom-marketplace

**ECC IS DEPRIORITISED — do not install without re-deciding.** Measured from the
clone: **898 skills, 367 agents, 424 commands**, whose skill descriptions alone
are **~35,000 tokens injected into EVERY turn** — more than CLAUDE.md (18.6k) +
MEMORY.md (7.6k) + all 113 existing skills (10k) combined, three times over.
Skill listings are budget-trimmed past ~1% of context, so beyond a point they
crowd each other out and make triggering worse. It also declares HOOKS, which
fire on tool events on a machine holding live broker credentials.

**claude-mem is 432 MB** and will not clone inside the timeout. Pre-clone or skip.
Install `claude-mem`, **never `claude-mem-cowork`** — its manifest says its hooks
stream tool output off-machine.

**EBUSY** on a marketplace directory = a clone is still running. Kill the git
processes, `rm -rf` the directory, then ONE clean add. **Filter the kill on the
FULL path** — a filter on `marketplaces` also matches a working directory named
`claude-marketplaces`, which is how a healthy clone got killed on 27 Aug.

---

## 5 — CODE STATE (all pushed)

- **aegis-alpha-terminal** — 25 suites, **917 checks**, green.
  **Run the suite with `python run_tests.py` and NOTHING else.** It sets
  `AAT_TEST_MODE=1`, blocking sockets AND DNS in the suite and every child it
  spawns. Running a `tests_smoke_*.py` file directly leaves the venue reachable.
- **aegis-finance** — **6037 passed**.
  `AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow"`.

Session 15 shipped: venue-blocked test isolation (zero egress) · intent-before-POST
+ `scripts/reconcile` (**0 lost rows** on market/dev/exp1) · **book-wide limits
ENFORCED** with a warm-up so a fresh account is not deadlocked · effective book
ceiling moved **40% → 35%** · the reserved-event exemption found to be **dead code
at `aggregate_cap ≥ 45%`**.

> **NOT LIVE-VERIFIED:** the book-limit wiring is covered by the suite only. A dry
> pass timed out in chain fetches before reaching admission. **Exercise it before
> the judged account is writable.**

---

## 6 — MEASUREMENT TRAPS PAID FOR ON 27 AUG

Every one of these looked like a system failure and was a **broken measurement**.

- **Piping pytest into `tail` throws away its verdict.** An "exit code 0" was
  `tail`'s; the suite had failed. Capture `PYTEST_EXIT=$?` from pytest itself.
- **`Get-ChildItem -Recurse` reported 0 MB** on a directory with locked files —
  `-ErrorAction SilentlyContinue` turned "cannot stat" into a zero, reading
  STALLED on a clone downloading 4.5 MB/30s. Open `tmp_pack_*` with
  `FileShare.ReadWrite` and read `.Length`.
- **A 20 MB range request measures TCP slow-start, not bandwidth.** It predicted
  75 minutes for a download that took 8.
- **An `Invoke-WebRequest` poll reported "still loading" for 4 minutes** on a
  server up since second 48. The empty HTTP code was the tell — it was not a 503.
- **A process-kill filtered on `marketplaces` matched `claude-marketplaces`** and
  killed a healthy clone. Filter on the full path.
- **A `git commit` chained after a failed Python edit committed a message
  describing changes that were not in the tree** — a receipt for work that did not
  happen. Amended. Never chain `&& git commit` after an unverified edit.
- **`pip install <name>` from a GitHub link installs whatever owns that name on
  PyPI.** `agent-reach` resolved to a different author's project (repo 1.5.0 vs
  PyPI 0.1.0). Check `project_urls` on the PyPI JSON API first.
- **Heredoc backslash mangling** corrupted Python twice (`C:\Users` in a non-raw
  string, `\n` in a hook payload). Use Write/Edit for anything with backslashes.
- **Git Bash `/tmp` paths handed to Windows Python do not resolve** — it reported
  `NO-MANIFEST` for a repo that had one.
- The network here is **intermittently DNS-flaky**: it killed a pip install, a
  DeepSeek call, two downloads and several clones. Retry before diagnosing.

---

## 7 — BLOCKED, AND ON WHOM

| blocker | who |
|---|---|
| **`competition` Alpaca account does not exist** | **Murat, at kickoff** |
| NVIDIA key exposed twice in transcript | Murat — rotate |
| HF token over-scoped | Murat — narrow to serverless+read |
| Railway plan tier unreadable from CLI | Murat — dashboard |
| headroom / claude-mem not installed | Murat — §4 |

---

## 8 — NEXT DISCRIMINATING TESTS, IN ORDER

1. **Grade the 27-Aug session** — `scripts.contagion --event 2026-08-27`,
   `scripts.anchor_to_torque --event 2026-08-27`, condors vs the pre-outcome
   receipt. **Outstanding since 26 Aug.**
2. **Exercise admission live** so §5's book-limit wiring stops being suite-only.
3. **Re-pull the hackathon rules at kickoff** as `RULES_SNAPSHOT_2026-08-28`;
   fail preflight if a requirement changed. The 25-Aug snapshot says Trading API
   + MCP-or-CLI + options + a fresh $100k judged account.
4. **Price real option wings** off expired OPRA bars — the one measurement
   between `FAILED_VARIANT` and a defined-risk premium arm.
5. **Do NOT rebuild the expression engine.** `structures.py`, `sizing.py`,
   `payoff.py`, `shape.py`, `equity.py` already are one. Prove the chain
   end-to-end instead: forecast → structures → economics → CASH-or-structure →
   book limits → order payload → deterministic client id → intent row → submit →
   reconcile → ledger, with a deliberate crash at each boundary.
6. **`alpha/tooling.py` already satisfies the MCP/CLI rule**, with the better
   idea: the MCP server can start with the `trading` toolset withheld, so a
   connected LLM *has no order-placing verb*. Worth a screen of the demo.
7. **Railway:** the 0.36 vCPU is `backend/main.py::_warm_endpoint_caches_loop`
   (80-ticker screener on a 15-min TTL, 10k-path MC hourly) serving 13 requests
   per 12h. **Do not touch it before 4 Sep** — the site is a submission surface.
