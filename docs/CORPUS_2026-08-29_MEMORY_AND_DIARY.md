# OBSERVATION CORPUS — the memory and the diary (2026-08-29)

**Status:** built, run, shadow. Places nothing, sizes nothing.
**Licence:** `PRODUCT_EXPERIMENT` (collection + shadow synthesis; no claim).
**Roadmap:** closes `ROADMAP_2026-08-29_WEEKEND_TO_MONDAY.md` §5 "EventObservation
schema + source registry", "catalyst calendar with `source_verified` per row",
and the §7 coverage gap.

---

## 0. RESULT

**RESULT IMPROVEMENT: NONE** in P&L terms — nothing traded, nothing was sized.
What changed is what the engine can *see*.

| | before | after |
|---|---|---|
| news window | 48 hours | **2025-06-09 → today** |
| forward events | ~2-day earnings peek | **→ 2027-02-25 (180 days)** |
| Murat's 20 names with any history | **0** | **20** (16–707 headlines each) |
| stored observations | none (no store existed) | **14,794+** |
| macro calendar | none | 67 dated releases, 10 series |
| trial readouts | none | 9 dated milestones |

The §7 finding was *"not one of Murat's twenty names received a bet — none had
a headline in the pipe."* The cause is now measured rather than inferred:

> Over three months Alpaca/Benzinga filed **1,566 items on NVDA and 3–4 each on
> AARD / SLDP / KYTX** — a 390:1 wire ratio. At ~4 items per 90 days, the chance
> a small name has *any* headline in a 48-hour window is ≈9%. The digest was not
> mis-ranking those names. It was never shown them.

Finnhub's per-**symbol** endpoint returned **18 items for KYTX where the
per-wire feed returned 4**. Asking *"what happened to this company"* beats
asking *"what did the wire publish"* exactly when the company is small — which
is the whole population Murat's rule selects from.

---

## 1. WHAT WAS BUILT

| file | job |
|---|---|
| `alpha/sources/corpus.py` | the append-only store: schema, PIT filter, content dedupe, purge-with-receipt |
| `scripts/news_backfill.py` | **backward** — up to 12 months, Alpaca + Finnhub per-symbol |
| `scripts/catalyst_horizon.py` | **forward** — 1 to 6 months: earnings, macro, clinical |
| `scripts/corpus_digest.py` | the LLM tier: episodes → state/thesis/falsifier/Murat-rule → `--screen` |
| `tests_smoke_corpus.py` | 37 checks pinning every trap below |

Fetch and interpretation are **separate scripts on purpose**. A collector that
also interprets is how `explain_move.py` shipped a bug every caller inherited.
A collector that is wrong gives no rows; an interpreter that is wrong gives
confident rows, which is quieter and worse.

### Point-in-time is two timestamps

Every row carries `observed_at` (when it became **knowable**) and
`effective_at` (when it is/was **true**). `read(as_of=…)` filters on
`observed_at` — the only filter that cannot leak. A forward catalyst is
observed today and effective in November; filtering it by its effective date
would let a backtest read the future, improve every number, and announce
nothing.

---

## 2. FIVE TRAPS, ALL PAID FOR IN THIS SESSION

**1. A 1500-row cap that deletes the NEAR term.** Asking Finnhub for the whole
6-month earnings range returns exactly 1500 rows spanning **2027-02-08 →
2027-02-26** — the cap is silent and it returns the *tail*, so one wide call
drops the next five months, the only tradeable part, while looking full. The
fix is not a bigger limit: `earnings_window()` pages narrowly and **splits any
window that comes back at the cap**. It fired three times on the first live run,
across late-October/early-November earnings season, and recovered **8,480 rows**.

**2. Cloudflare 1010 reads as "no credit".** Featherless returned `HTTP 403
error code 1010` to a bare `urllib` request and answered in 2.7 s once a
User-Agent was set. Project code goes through `post_json`, which sets one — but
a hand-rolled probe does not, and would have been reported as a dead provider.

**3. A reasoning model spends `max_tokens` before it answers.** `kimi-k3`
returns thought in `reasoning_content` and the answer in `content`, **both from
the same budget**. At `max_tokens=64` it returned `'{"ok": true, "n": 3'` —
valid JSON truncated mid-object; at 900 the same prompt answered in 45 tokens.
`providers.chat_json` surfaced that as *"non-JSON reply"*, which reads as **the
model is broken** when the true cause is our budget. It now names the
truncation and says to raise the budget. *(This was a latent bug in existing
code, not something the corpus introduced.)*

**4. Two FRED endpoints one letter apart.** `/releases/dates` (plural) is every
release's dates and **ignores `release_id`**; `/release/dates` (singular) is
one release's. Passing `release_id` to the plural one returned **11,000 rows**
that looked like a rich calendar and were the firehose again — with each date
stamped with a *wanted* release's name, so the store held **"FOMC Press Release"
on a Saturday**. The dedupe absorbed most of it, which is what made it hard to
see. Both constants are now named separately.

**5. `include_release_dates_with_no_data` is required, and it pads.** Without
it every *future* window returns zero. With it, most releases are correct (NFP
4, CPI 4, claims 18 over 180 days) but **FRED release 101 returns 125** — because
"FOMC Press Release" in FRED is the **daily fed-funds series**, not the
eight-meetings-a-year event; its measured history is **363 dates/year**. The
guard is a **cadence check that derives its bound**: each release is asked what
it actually did over the trailing year, and a forward count far above its own
history is dropped as padding. A hardcoded "FOMC is monthly" would have broken
on the next renumbering.

**6. A RATE LIMIT IS THE SAME BUG, ONE LEVEL DOWN.** The first 12-month run
finished with 31 refusals, all HTTP 429, and they landed on **SRRK (10 months),
HUBS (8), KYTX (8), PRCH (5)** — precisely the small names whose counts are
thin, where a missing month is a large share of the entire record. A
rate-limited window is **indistinguishable from "this company had no news that
month"**, which is the exact false silence this corpus exists to end.

Cause was my own pacing: 1.1 s between symbols but 0.25 s between months ≈ 4
calls/second against a 60/minute limit. Fixed with backoff retry (2s/4s/8s) and
1.1 s between months. Re-running those four names recovered:

| | before | after | |
|---|---:|---:|---|
| SRRK | 46 | **163** | 3.5× |
| HUBS | 227 | **536** | 2.4× |
| KYTX | 50 | **131** | 2.6× |
| PRCH | 64 | **128** | 2.0× |

So the holes had been deleting **half to three-quarters** of those names'
history. The run now also prints `MONTHS n/12` per symbol: *"0 items over 12/12
months"* is a quiet company, *"0 items over 4/12 months"* is a hole, and the
two must never print the same way.

**7. The cap I added myself.** AMD/MU/MRVL/TSM hold ~9,700 headlines between
them — ~240 LLM calls for four names. `--max-headlines` (default 400, most
recent kept) bounds it, and every truncated record carries
`n_past_available`, `history_covers_from` and `truncated_from` **plus a
refusal line**, so no one reads a "12-month" field that actually covers four.
A bounded run that does not say what it dropped reads as full coverage.

**8. WIDENING AN INPUT SILENTLY NARROWED AN OUTPUT.** Featherless latency on
the shared tier measured **6.7 s / 18.8 s / 64.9 s on three consecutive
identical calls** — queueing, not throughput — so a pass costs by *number of
calls*, not their size. Raising the episode chunk 40 → 120 to cut a 20-name run
from ~200 calls to ~70 then caused the model to treat the digest as
**transcription**: one episode per headline, **9,217 characters**, over
`max_tokens`, and **the entire chunk was discarded**. AARD's file was built from
**1 episode out of 121 headlines** and read `unknown`.

Nothing in the chunk change touched the response budget — the two are coupled
only through the model's behaviour, and that coupling shows up as a *refusal*
only because something checks `finish_reason`. That check had been written for a
different provider entirely (trap 3).

Fixed on both sides, because either alone is fragile: the prompt now says
**"THIS IS COMPRESSION, NOT TRANSCRIPTION — at most 10 episodes however many
headlines are supplied"**, and `_episode_call` **splits the chunk and retries**
on truncation, so a budget miss costs one extra call instead of the slice.
Same shape as the earnings cap (trap 1): *never accept a bounded answer as a
complete one.*

Result on identical data: **15 episodes over 3 chunks, zero truncations**, and
AARD moved `unknown` → **`thesis_impaired`, rule 3/5**. The earlier verdict was
an artefact, not a judgement. **Any AARD reading produced before this fix is
void.**

---

## 3. WHAT THE CALENDAR KNOWS IT LACKS

Recorded on every receipt as `known_gaps`, because a missing source nobody
writes down becomes a missing source nobody remembers — and a reader of a
clean-looking calendar will read the absence of an FOMC row as *no meeting*.

- **FOMC meeting dates** — not available from FRED (see trap 5). Real calendar
  is `federalreserve.gov` HTML. Treat as **UNKNOWN here, never as absent.**
- **FDA PDUFA dates** — no free API. ClinicalTrials.gov primary-completion is a
  proxy for a **readout**, not for an approval decision.
- **Guidance / investor days / lock-up expiries** — not collected.

---

## 4. THE MODEL TIER (measured, this session)

```
featherless  Qwen2.5-72B    2.7 s   family alibaba    -- the workhorse
nvidia_kimi  kimi-k3       13-17 s  family moonshot   -- the SKEPTIC (reasoning)
deepseek     deepseek-chat          family deepseek   -- live
hf_glm       GLM-5.3-Flash          family zhipu      -- live
```

No local model was run and none was resident (GPU 428 MB of 8 GB, idle).

**The skeptic earned its slot on the first name.** On AARD, Featherless returned
`thesis_intact`; NVIDIA returned `unknown` and explained why — a single-asset
bet on ARD-101 Phase 3 HERO data, with a Neutral rating and a **$6** target.
`agree_on_state: False` survives to the receipt, and `--screen` prints
`[FAMILIES DISAGREE]` first. That is the argument for two *families* rather
than two models: a skeptic drawn from the same weights is the synthesiser
agreeing with itself.

---

## 5. THE MODEL WILL CLAIM A CATALYST IT DOES NOT HAVE

On the first live AARD digest the analyst listed a **2026-08-11 event that had
already happened** as a forward catalyst, and passed Murat's condition (d)
— *"a named catalyst inside 12 months"* — while the corpus held **zero** future
rows for the name. The prompt had asked, in words, for an honest `unknown`.

So the check is in code. `reconcile()` drops any "catalyst" that is not
future-dated, and downgrades `dated_catalyst: pass → unknown` when neither a
surviving catalyst nor a corpus row supports it. Every correction is written to
the record rather than applied silently — **the correction rate is the
calibration signal**, and hiding it would destroy the only measure of how much
to trust the next answer.

This is the standing rule in its usual clothes: **a guard derives its inputs or
refuses.** Asking a model to be honest is not a guard.

---

## 6. HOW TO RUN IT

```bash
python -m scripts.news_backfill --months 12 --murat      # backward
python -m scripts.catalyst_horizon --days 180 --murat    # forward
python -m scripts.corpus_digest --murat --skeptic        # digest
python -m scripts.corpus_digest --screen                 # what the book reads
python -m scripts.news_backfill --stats                  # what is stored
python run_tests.py -k corpus                            # 37 checks
```

Re-running any collector is free: dedupe is by content hash, so a second pass
over the same year appends nothing and says so.

---

## 7. WHAT THIS IS NOT

Not evidence of alpha. Not a signal. Nothing here has been backtested, and no
number in it has a t-statistic. It is the **information layer** that the
selection rule needs in order to be *evaluable at all* — the §5 backtest
factory (analyst-upside × drawdown cells on CRSP + IBES) is the thing that
would adjudicate it, and that has not been run.

`corpus_digest --screen` output is a **reading order for a human**, not a
ranking to size from. Paper authority stays where the roadmap put it: drift
(measured), the Murat lane under a gross cap, and the attended human thesis.
