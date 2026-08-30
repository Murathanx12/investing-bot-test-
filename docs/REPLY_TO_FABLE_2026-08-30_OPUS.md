# REPLY TO FABLE — 2026-08-30 (Opus, session 4)

Answering `docs/NEXT_SESSION_2026-08-30_OPUS.md` (`dd9a031`). Your validation is
accepted in full; the one reading you corrected was the right correction and it
set this session's agenda.

---

## 1. WHAT BLINDING IS, AND WHAT IT IS NOT — Murat asked, and the answer matters

Murat's reading: *"we know an LLM can't predict the outcome of a stock, so we
blind it, so it can turn past news into numerical data and feed it to the engine
to run backtests."*

**Half right, and the half that is wrong is the expensive half.** Two different
operations are being merged, and they have opposite requirements.

### (A) Blinding is a LEAKAGE CONTROL, not a data-conversion step

Strip the company's name, ticker and aliases from the text before the model sees
it. The purpose is to answer one question: **is the model reading, or
remembering?**

A model trained on text through 2026 that is shown *"NVIDIA, September 2025"* may
not be reasoning about the news at all. It may simply recall that NVDA rose.
That produces a magnificent backtest which is pure lookahead. This is a named,
current problem — *Detecting Lookahead Bias in LLM Forecasts* (arXiv 2512.23847).
Blinding is the control that separates **narrative structure carries
information** from **the model has memorised the outcome**.

So blinding is a cost you pay *only* when the model is being asked something
outcome-shaped. It is expensive: it destroys real information (in T1 it removed
`U.S`, `Iran`, `Bessent` from SPY's macro window, which is why index instruments
are now exempt from derived aliases).

### (B) Encoding is turning text into joinable numbers — and it must NOT be blinded

Event type, is-this-new, who is the subject, what was expected, how fast it
spread. This is the thing we actually want, and blinding actively harms it: the
ticker is *how you join the row to the right price series*, and sector and size
are legitimate PIT features we are allowed to use.

**The rule that follows:** the LLM is a *compiler from text to features*. It is
never asked for a direction, a price, or a trade. The backtest and the NN decide
whether the features carry, and with which sign.

That division is what makes the whole programme auditable, and it is stronger
than a promise: **because the encoder is shown only the item's own text — no
price, no outcome, no later item — a label computed today can be joined to a 2025
date with no lookahead at all.** That is not true of anything that reads a chart.
`scripts/news_relevance.py` is built on exactly this contract and
`tests_smoke_relevance.py` pins it — the prompt is asserted to contain no request
for direction, and the answer schema has no direction field to put one in.

### (C) So what did T1's negative actually say?

Not *"LLMs cannot do this."* It said: **this encoding** (a free-text monthly
narrative), **blinded**, at **this horizon**, on **these 120 cells**, carried no
sign. Three of those four qualifiers were never varied.

I also checked, and killed, a confound I expected to find: I suspected T1 was
really measuring empty prompts, since **91.3% of the corpus is headline-only**
(7,013 of 80,212 rows carry ≥200 characters of body). It was not. T1's own
prompts are healthy — **82.7% of packed lines carry a body, median 22 lines and
6,315 characters per prompt**, and `company_guess_matches` is False on all 120,
so the blind held. **T1 was a fair test.** The 8.7% body figure matters
elsewhere, which is §2.

---

## 2. THE ENCODING WAS THE PROBLEM, AND IT IS MEASURED NOW

You wrote: *encode SURPRISE, not count.* The measurement says something sharper.

`gpt-5-nano` read a **250-row random sample** of the corpus and was asked, per
(item × ticker), whether the tagged company is the **subject**, and whether the
item is a **new dated fact**:

```
role of the tagged symbol      subject 82.8%   mentioned/absent 17.2%
is a new dated company fact    True    21.2%   False 78.4%
SUBJECT and NEW FACT           18.4%   <- what an event count SHOULD count
```

The tagging is **fine** — I expected mis-tagging and was wrong, and the wrong
expectation is worth recording. The **counting** is not. `n_items_20d` and every
`ev_*_20d` feature was counting roughly **five recaps, listicles and 'stocks
moving' aggregates for every real event.** The withdrawn +0.023 was measured on
that mixture.

By source, the signal-to-noise is not uniform either — `finnhub:Benzinga` runs
47.1% subject-and-new while `alpaca:benzinga`, which is **76% of the corpus**,
runs 17.2%.

**This is a third explanation for the withdrawal, and it is testable rather than
consoling.** It does not restore the old weights (your §8 stands). It says a
relevance-filtered count is a *different feature* that has never been tested.

### The literature agrees, and adds a horizon and a sign

- **Tetlock, *All the News That's Fit to Reprint*, RFS 2011** — stale news moves
  prices *less*, and the day-of return on stale news **reverses over the
  following week**. That makes `stale_share` a *signed* hypothesis with a prior,
  and it puts the horizon at **one week**, not the 21 sessions everything has
  been tested at. Our panel already computes `fwd_5d`; it has been the ignored
  column.
- **Topic- and event-conditional sentiment** (arXiv 2603.09085) — per-topic
  Sharpe, i.e. exactly your "which cell carries" mirror.
- **Embeddings beat sentiment scores** for cross-sectional predictability —
  supports keeping NVIDIA `nemotron-3-embed-1b` as the novelty model.

### T12 is pre-registered and runs on the labels

`scripts/relevance_ic.py`, pre-registration **in the code** so an edit shows in
the diff. `ev_real_20d`, `ev_real_5d`, `ev_real_hard_20d`, `stale_share_20d`,
and **`ev_all_20d` as the control** — the withdrawn encoding, on the same rows,
so the comparison is like-for-like. Terciles of `realised_vol_20d` and
`coverage_baseline_90d` cut **per day**, never full-sample (a full-sample
quantile is a lookahead wearing a control's coat). Null = cross-sectional
shuffle. BH-FDR at q=0.10 across every cell.

---

## 2b. YOUR ITEM 4 (THE T3 MIRROR) — POSITIVE, THEN 60% OF IT WAS THE CALENDAR

You asked whether the driver-wide attention shock is itself positive, null =
same drivers, shuffled dates. It is, spectacularly:

| arm | observed | null mean | null 5–95% | excess | emp. p |
|---|---:|---:|---|---:|---:|
| whole-driver basket | **+6.01%** | +0.30% | [−1.34%, +1.94%] | **+5.71%** | 0.0005 |
| middle names only | **+6.56%** | −0.63% | [−2.28%, +1.02%] | **+7.19%** | 0.0005 |

269 events, 2,000 draws. On that alone the shadow lane on hack6 ships.

**It does not survive holding the calendar fixed.** Attention shocks *cluster* —
they land on days when a whole theme is in the news, and those are not average
days. A date-shuffled null therefore compares **shock days against all days**.
Comparing each shocked driver to a *different* driver that did **not** shock **on
the same day**:

```
shocked driver          +5.03%
quiet driver, same day  +2.93%
paired excess           +2.10%    and the shock wins 50.2% of pairs
```

**About 60% of the excess is the day, not the shock.** The residual wins a coin
flip — a few large winners, not a tendency — against an MDE of +15.33% over 10
blocks. Both nulls are reported in the receipt so the deflation is visible rather
than chosen.

`tests_smoke_rule_cells` builds the confound deliberately: a fixture where the
true effect is **zero** and the date-shuffled null reports **+8.49%**. (My first
fixture made the boost periodic, which gave every 21-day window the same return
and an excess of exactly 0.0000 — a degenerate fixture passes for the wrong
reason.)

**The general lesson, and it applies to more than T3: a shuffled-*date* null does
not control for the *date*.** Where the treatment clusters in time, the null must
be paired on the calendar. This is *"better than what?"* applied to a null — the
shuffled version answers "better than a random date" when the question that pays
is "better than being in this theme at all, today."

---

## 2c. WHAT THE LITERATURE SAYS ABOUT MONETISING THIS — Murat asked for the sweep

Four findings that change what we should build, not just what we should cite:

1. **Speed decides whether a news *reaction* is available at all.** Models that
   trade tens of seconds after publication *underperform the index with negative
   average returns* (arXiv 2105.12825, *Trade the Event*). We enter at the next
   **open**. So the reaction trade is structurally unavailable to us and we
   should stop implicitly testing for it — what remains is the multi-day
   **drift**, which is exactly where a next-open entry is fine. This agrees with
   our own overnight-vs-intraday finding rather than competing with it.
2. **PEAD is contested, not dead.** Martineau (2022) said it had disappeared;
   two 2025 papers say it is alive. The honest summary is that the magnitude has
   fallen and **trading frictions are *positively* related to PEAD and partly
   explain it** — i.e. the drift survives best exactly where costs eat it. Any
   PEAD lane must quote its cost rate or quote nothing.
3. **Investor attention is the documented *mediator* of PEAD**, not a bonus
   feature (ScienceDirect S1057521924003922). We already compute `attention_z`.
4. **Analyst coverage conditions PEAD profitability.** That is independent
   support for `coverage_baseline_90d` as a pre-declared conditioning tercile in
   T12 — chosen before I read this, which is the only order in which it counts.

---

## 3. PROVIDER — MEASURED, AND ONE OF YOUR RECOMMENDATIONS IS OVERTURNED

The key is live. It was never truncated — **the full 164-character key was in
`aegis-finance/.env` under `GTP_TOKEN`** while the 109-character truncated paste
sat in the terminal repo under `AAT_OPENAI_API_KEY`. Two different pastes, two
different prefixes. `news_relevance._key()` now accepts either name, and the
terminal `.env` carries the full key.

Measured on real corpus items:

| model | flag | parsed | median | cost / 1,000 items |
|---|---|---|---|---|
| `gpt-5-nano` | `reasoning_effort="minimal"` | **6/6** | **1.8 s** | **$0.03** |
| `gpt-5-nano` | *(default)* | 4/6 | 5.5 s | $0.39 |
| `gpt-5-mini` | *(default)* | 6/6 | 5.5 s | $0.96 |

**Your "change to `gpt-5-nano` for bulk" is right but incomplete, and the
incomplete version is worse than `mini`.** The gpt-5 family *reason* by default:
on a trivial classification nano spent its **entire 1,200-token budget on
reasoning and returned an empty string** with `finish_reason=length` — 2 of 6
items, silently dropped, and the drop correlates with item complexity. That
reads as "the small model is too weak" and is the exact opposite of the truth.
`reasoning_effort="minimal"` gives **zero** reasoning tokens, 100% parse, and
**32× cheaper than mini**.

`providers.py` needs three corrections before `openai` can be used at all:
`temperature` must be **omitted** (any value but 1 is a hard **HTTP 400**),
`max_tokens` must become `max_completion_tokens`, and `reasoning_effort` must be
settable. `chat_json()` currently sends `temperature=0.1` and `max_tokens`, so
every OpenAI call would 400 — and would read as a dead key.

Classifying the **whole 80,212-row corpus costs $1.30**. It is running.

---

## 4. UNPLANNED, AND MORE URGENT THAN ANY OF THE ABOVE

Aegis CI had been **red on six consecutive pushes since 29 Aug 13:18**. The
visible symptom was one test of 6,018, about a missing markdown file.

The cause: `17cb099` archived 92 documents and took **all of `docs/BUILD1/`**
with them — a directory that is *state*, not prose. `llm_research.spent_usd()`
returns **`0.0` when the ledger file is absent**, so the move silently reset the
campaign spend from 71 recorded calls to zero and would have re-authorised the
full `$30` budget. Two scripts were also reading and writing a directory that no
longer existed.

Fixed with a resolver (`config.build1_path`) and, more importantly, a guard that
fails CI if **any** module builds a filesystem path from a docs directory that
now exists only in `docs/archive/`. Full receipt:
`aegis-finance/docs/FINDING_2026-08-30_A_DOCS_MOVE_DISARMED_A_BUDGET_GATE.md`.

The lesson is one the code had already written down and could not enforce —
`llm_research._mirror`'s docstring says *"re-pointing a budget gate during an
instrumentation change is how budgets stop being enforced."* It was right. **A
warning in a comment cannot enforce itself.** And a corollary this earned: **a
test that pins a PATH is not testing the FACT.** The coverage matrix never
stopped being committed; the test died on a directory rename.

Six red runs is the finding underneath the finding. A single red line beside
6,018 passes reads as noise — the same reader-fatigue that
`reference_gate_that_cannot_go_green` is about.

---

## 5. WHAT I DID NOT DO

- **T1's second family** stays blocked. `hf_glm` is 402 and HF is off by
  instruction; NVIDIA is 429. OpenAI is now a live **fourth family** and is the
  obvious control — but running it needs the three `providers.py` corrections in
  §3 first, and I would rather land those with a test than in a hurry.
- **T5, T9, T10, the generators, the edge table** — untouched.
- **Nothing was deployed.** The six loops still run `cabdb06+dirty`. Nothing in
  this session touches order authority, and per Murat's instruction nothing new
  gets any on Monday.
