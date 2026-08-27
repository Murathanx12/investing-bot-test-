# START HERE — environment, tooling, and state as of 2026-08-27 evening

Read this before `docs/HANDOFF.md`. That file is the trading record; this one is
the machine you will be running it on. Session 15's findings are in
`docs/HANDOFF_SESSION_15.md`.

---

## 0 — THE ONE-LINE STATE

> **RESULT IMPROVEMENT: NONE this session.** Guardrails, tooling and providers
> only. No strategy tested, no candidate promoted, no P&L moved. The competition
> opens 28 Aug and the judged account **does not exist yet**.

---

## 1 — TOOLING THAT IS INSTALLED AND WORKING

### Claude Code plugins (`~/.claude/plugins/installed_plugins.json` is the truth)

| plugin | version | note |
|---|---|---|
| `agent-skills@addy-agent-skills` | 0.6.7 | spec/plan/build/review/ship/test + 4 subagents |
| `huggingface-skills@claude-plugins-official` | 1.0.25 | `hf-cli`, `huggingface-local-models`, `hf-mem` |
| `superpowers`, `code-review`, `plugin-dev`, `skill-creator`, `claude-code-setup`, `claude-md-management`, `context7`, `playwright`, `supabase`, `github`, `security-guidance`, `frontend-design`, `vercel`, `explanatory-output-style` | — | official marketplace |

**FOUR PLUGINS NOT INSTALLED.** None of their marketplaces are registered either
— `known_marketplaces.json` holds only `claude-plugins-official` and
`addy-agent-skills`. Run these ONE AT A TIME, smallest first, and read the
"marketplace add is SLOW" section below before retrying anything:

```
/plugin marketplace add nextlevelbuilder/ui-ux-pro-max-skill   # ~1 min
/plugin install ui-ux-pro-max@ui-ux-pro-max-skill
/plugin marketplace add affaan-m/ECC                           # ~5 min
/plugin install ecc@ecc
/plugin marketplace add headroomlabs-ai/headroom               # ~8 min
/plugin install headroom@headroom-marketplace
/plugin marketplace add thedotmack/claude-mem                  # ~48 min
/plugin install claude-mem@thedotmack

cat ~/.claude/plugins/known_marketplaces.json   # the add must land HERE first
cat ~/.claude/plugins/installed_plugins.json    # then the plugin appears HERE
```

Install `claude-mem`, **never `claude-mem-cowork`** — its own manifest says its
hooks stream tool output off-machine.

`farion1231/cc-switch` (Tauri desktop app) and `NousResearch/hermes-agent`
(standalone Python agent) have **no plugin manifest**. There is no install
command for either; they are separate downloads.

### MCP servers (`.mcp.json`, present in BOTH repos)

| server | what |
|---|---|
| `optimus` | the brain: canon, postmortems, verified state, skills across 3 roots |
| `exa` | free whole-web semantic search — `web_search_exa`, `web_fetch_exa`, no key |

The terminal repo had **no `.mcp.json` at all** until 27 Aug, so optimus was
never reachable from a session started there. It is now.

### CLI tools

- **`graphify` 0.9.50** — codebase → queryable knowledge graph. `/graphify .`
  builds one (not built yet; it is an LLM-cost operation, do it deliberately).
- **`agent-reach` 1.5.0** — 4/15 channels work with NO credentials: RSS/Atom,
  V2EX, any webpage via Jina Reader, Bilibili search. `agent-reach doctor`.
  Twitter / Reddit / Xueqiu / LinkedIn need **browser session cookies** and are
  deliberately NOT configured on a machine holding broker credentials. Xueqiu
  (stock quotes + community) is the one most worth the trade-off.
- **`mcporter`** — how Exa was registered.

### Plugin `marketplace add` is SLOW, not broken (2026-08-27)

`EBUSY: resource busy or locked` on `~/.claude/plugins/marketplaces/<dir>` does
NOT mean a permissions problem. It means **a git clone from a previous attempt is
still running** and holding `.git/objects/pack/tmp_pack_*` and
`.git/shallow.lock`. Retrying kills nothing and starts a second clone competing
for the same bandwidth.

The installer clones with `--depth 1 --recurse-submodules`, and this machine
manages roughly **9 MB/min** to GitHub:

| repo | size | ~clone |
|---|---|---|
| `nextlevelbuilder/ui-ux-pro-max-skill` | 7.8 MB | 1 min |
| `affaan-m/ECC` | 46.7 MB | 5 min |
| `headroomlabs-ai/headroom` | 74.8 MB | 8 min |
| `thedotmack/claude-mem` | **432 MB** | **48 min** |

**"Just wait for the clone" does NOT work** — advice given earlier in the same
session and disproved within the hour. The installer TIMES OUT, reports failure
and abandons the result, while the orphaned git process keeps downloading for
nothing. `headroom` finished its clone, its directory was cleaned up, and it
STILL never registered. The only variable that predicts success is clone time vs
the installer's timeout:

| repo | clone | registered? |
|---|---|---|
| ui-ux-pro-max (7.8 MB) | ~1 min | **YES** |
| ECC (46.7 MB) | ~5 min | no |
| headroom (74.8 MB) | ~8 min | no |

**THE WORKAROUND — pre-clone locally, then add from disk.** Nothing times out on
a plain `git clone`, and these manifests declare `"source": "./"`, so the plugin
installs from the marketplace directory itself and does NOT re-clone:

    git clone --depth 1 https://github.com/OWNER/REPO.git  <SRC>\NAME
    /plugin marketplace add <SRC>\NAME
    /plugin install PLUGIN@MARKETPLACE-NAME

where `<SRC>` is `C:\Users\mrthn\cc-plugin-src`. Deliberately NOT a path under
`~/.claude/plugins/` — the installer manages that directory and will try to
delete anything it finds there.

**If it is genuinely wedged:** kill the clone processes
(`Get-CimInstance Win32_Process -Filter "Name='git.exe'"`), then `rm -rf` the
directory, then ONE clean add. **Filter the kill on the FULL path**: a filter on
`marketplaces` also matches a working directory named `claude-marketplaces`,
which is how a healthy clone got killed on 2026-08-27.

**ECC IS DEPRIORITISED — DO NOT INSTALL WITHOUT RE-DECIDING (2026-08-27).**
Measured from the clone, not guessed: **898 skills, 367 agents, 424 commands**,
and its skill descriptions alone are **~35,000 tokens injected into EVERY turn**
— more than CLAUDE.md (18.6k) + MEMORY.md (7.6k) + all 113 existing skills (10k)
combined, three times over. Skill listings are budget-trimmed past ~1% of
context, so beyond a point they crowd each other out and dilute which skill
actually triggers. It also declares HOOKS, which fire on tool events on a machine
holding live broker credentials. The clone is kept at
`C:\Users\mrthn\cc-plugin-src\ECC` if the decision is revisited; `agent-skills`
already covers spec/plan/build/review/ship at a fraction of the cost.

**claude-mem (432 MB) will not clone inside the timeout on this link.**
Pre-clone it locally or skip it.

**Measuring progress:** `Get-ChildItem -Recurse` reports **0 MB** on these
directories because it cannot stat the locked files and `-ErrorAction
SilentlyContinue` turns that into a zero -- it read "STALLED" on a clone that was
downloading 4.5 MB per 30s. Open the `tmp_pack_*` file with
`FileShare.ReadWrite` and read its `.Length` instead.

---

## 2 — MODEL PROVIDERS

`backend/services/model_provider.py` (aegis-finance). ONE OpenAI-compatible
contract; a provider is a ROW, not a class.

```
python -m backend.services.model_provider           # environment only
python -m backend.services.model_provider --probe   # actually call them
```

| provider | state | model |
|---|---|---|
| deepseek | **live** | `deepseek-chat` |
| nvidia | **live** | `openai/gpt-oss-20b` |
| huggingface | **live** | `meta-llama/Llama-3.3-70B-Instruct`, ~1.9s |

**`status()` reports absent / configured / live and never collapses them.**
`--probe` is what turns the second into the third, and three things it caught
that reading config never would:

1. the first NVIDIA default returned **HTTP 410 END OF LIFE dated 2026-08-26** —
   the day before it was written. NIM retires models on a date;
2. **being LISTED by `/v1/models` is not being callable.** Six candidates: two
   410, one 404 not-available-to-this-account, three timed out, one answered;
3. `gpt-oss-20b` is a REASONING model. At `max_tokens=16` `content` came back
   EMPTY with only `reasoning_content` populated; at 300 it answered in 120
   tokens. **A small budget on a reasoning model reads exactly like a dead
   model.**

It is deliberately **NOT a router** and has **no trading authority**.

**The HF token is over-scoped.** It is a fine-grained token with `repo.write`,
`job.write`, `inference.endpoints.write` (the last two can incur GPU charges),
`post.write` and `user.billing.read`. This system uses exactly two of those:
`inference.serverless.write` and `repo.content.read`. Narrowing it costs two
minutes and is worth doing on a machine that also holds live broker credentials
and has already leaked two keys into transcripts. Murat's call; flagged once.

**Local inference is now less urgent than it looked.** HF serverless answers from
a 70B in ~1.9s for free, which is far beyond what 8 GB of VRAM can hold. The case
for local was never capability — it is removing per-call cost on the high-volume
extraction jobs. That case still holds; it is no longer blocking.

---

## 3 — LOCAL INFERENCE (IN PROGRESS, NOT FINISHED)

**Hardware:** RTX 5060 Laptop, **8 GB VRAM**, 20 CPU cores, 111 GB free.
**`torch` is `2.11.0+cpu`** — the CPU-only wheel, so `cuda available: False`.
Nothing torch-based can use the GPU today.

Path chosen is **llama.cpp / GGUF**, not torch: purpose-built for inference,
native quantization, ships an OpenAI-compatible `llama-server`, no torch needed.

**State at handoff:**

- `C:\Users\mrthn\llama\bin\` — llama.cpp **b10645, CUDA 13.3** build EXTRACTED.
  `llama-server.exe`, `llama-cli.exe`, `ggml-cuda.dll` all present.
- `cudart-llama-bin-win-cuda-13.3-x64.zip` — **STILL DOWNLOADING** (~93 of
  372 MB, very slow link).
- **`llama-server.exe --list-devices` currently prints `(none)`** because the
  CUDA runtime DLLs are not there yet. That is expected, not a failure.

**Remaining steps:**

1. finish the cudart download, extract it into `C:\Users\mrthn\llama\bin\`;
2. `llama-server.exe --list-devices` must name the RTX 5060. **If it still says
   `(none)`, stop** — do not fall back to CPU silently and call it working;
3. pull a **Q4 7–8B GGUF** (~4.5 GB) — that is the size class 8 GB VRAM fits;
4. `llama-server.exe -m <model> --port 8080 --n-gpu-layers 99`;
5. add a `local` row to `PROVIDERS` pointing at `http://localhost:8080/v1`, then
   `--probe` it. Configuration is not capability.

**CUDA 13.3 and not 12.4 on purpose:** the RTX 5060 is Blackwell (sm_120) and
needs CUDA 12.8+. The 12.4 build has no kernels for it and would silently run on
CPU — fast enough to look like it worked, ten times slower than it should be.

**Expectation setting:** a local 8B is genuinely good for the high-volume jobs —
extraction, classification, routing, parsing filings into structured evidence —
and removes the ~$3.68/day DeepSeek bill for those. It is **not** a substitute
for a frontier model on generating causal hypotheses and falsifiers.

---

## 4 — CODE STATE (session 15, all pushed)

- **aegis-alpha-terminal** `c4c9890+` — 25 suites, **917 checks**, all green.
  **Run the suite with `python run_tests.py` and NOTHING else** — it sets
  `AAT_TEST_MODE=1`, which blocks outbound sockets AND DNS in the suite and in
  every child it spawns. Running a `tests_smoke_*.py` file directly leaves the
  venue reachable.
- **aegis-finance** `1a7a0bf` — **6037 passed**, 1 pre-existing failure fixed.
  `AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow"`.

Session 15 shipped: venue-blocked test isolation · intent-before-POST +
`scripts/reconcile` (0 lost rows on market/dev/exp1) · **book-wide limits
ENFORCED** with a warm-up so a fresh account is not deadlocked · the effective
book ceiling moved **40% → 35%**.

---

## 5 — TRAPS THAT COST TIME TODAY

- **`piping pytest into `tail` throws away its verdict.`** An "exit code 0" was
  `tail`'s, not pytest's; the suite had actually failed. Capture
  `PYTEST_EXIT=$?` from pytest itself.
- **A literal pinned to a DERIVED value re-breaks whenever the derivation gains
  data.** `test_iif1_readiness_is_free` asserted `10:04Z`; a new night's receipt
  moved it to `10:03Z`. Bumping the number resets the timer; assert the property
  with a bound instead.
- **`pip install <name>` from a GitHub link installs whatever owns that name on
  PyPI.** `agent-reach` resolved to a different author's project (repo 1.5.0 vs
  PyPI 0.1.0). Check `project_urls` on the PyPI JSON API first.
- **Plugin installs failed twice for two different reasons**, and neither said so
  clearly: first a transient network failure that printed `(no content)`; then
  `No ED25519 host key is known for github.com`. Fixed by (a) adding GitHub's
  host keys **after verifying them against GitHub's published set over HTTPS** —
  blindly appending `ssh-keyscan` output defeats the check that was failing — and
  (b) `git config --global url."https://github.com/".insteadOf "git@github.com:"`,
  since both repos already push over HTTPS and no SSH key is registered.
- **`EBUSY: resource busy or locked`** on a marketplace directory means a handle
  is open (antivirus, or a shell sitting inside it). The directory is gone now,
  so a retry works.
- The network on this machine is **intermittently DNS-flaky** — it killed a pip
  install, a DeepSeek call and two downloads today. Retry before diagnosing.

---

## 6 — WHAT IS BLOCKED, AND ON WHOM

| blocker | who clears it |
|---|---|
| `competition` Alpaca account does not exist | Murat, at kickoff |
| `HF_TOKEN` empty | Murat — huggingface.co/settings/tokens |
| NVIDIA key exposed twice in transcript | Murat — rotate |
| Railway plan tier unreadable from CLI | Murat — dashboard |
| four plugins not installed | Murat — the commands in §1 |
| cudart download unfinished | time |

---

## 7 — NEXT DISCRIMINATING TESTS (in order)

1. **Grade the 27-Aug session** — `scripts.contagion --event 2026-08-27`,
   `scripts.anchor_to_torque --event 2026-08-27`, condors vs the pre-outcome
   receipt. Outstanding since yesterday.
2. **Exercise admission live** — the book-limit wiring is suite-verified only; a
   dry pass timed out in chain fetches before reaching it.
3. **Re-pull the hackathon rules at kickoff** as `RULES_SNAPSHOT_2026-08-28` and
   fail preflight if a requirement changed.
4. **Price real option wings** off expired OPRA bars — the one measurement
   between `FAILED_VARIANT` and a defined-risk premium arm.
5. **Find the 0.36 vCPU** Railway burns for 13 requests/12h. Confirmed cause:
   `backend/main.py::_warm_endpoint_caches_loop` (80-ticker screener on a 15-min
   TTL, 10k-path MC hourly). **Do not touch it before 4 Sep** — the site is a
   submission surface.
