# NEXT SESSION FOR OPUS — 2026-08-30 (written by Fable after validating session 3)

**Read first:** `../aegis-finance/docs/ROADMAP_2026-08-29_WEEKEND_TO_MONDAY.md` §10 (status
table below is the truth), `docs/SESSION_2026-08-30_OPUS_ROADMAP.md` (your own receipt),
`docs/FINDING_2026-08-30_THE_EVENT_COUNTS_WERE_TWENTY_THREE_NAMES.md`.

## 0. Validation of session 3 (Fable, 30 Aug 10:40 SGT)

Checked against the repo and the venue, not the prose: commits `46b595e`…`cabdb06` present;
`python run_tests.py` = **54 suites / 2,277 checks, ALL PASS**; `prediction_book --verify` re-hashes
`2026-08-30.json` (c24e247b…) and matches; `ic_narrow23_from_wide_build.json` reproduces the
narrow ICs (+0.132 / +0.120 / +0.075 on 21d raw) — the withdrawal is correctly reasoned; the 94-name
universe, the `session_day()` clock fix and `numpy` are in. Nothing to reverse.

One reading to correct, not a fact: **"0 of 29 clear on 152" is a GLOBAL negative, and CLAUDE.md's
standing rule is that a global negative does not answer a conditional question that was never
asked.** The narrow panel was Murat's names — high realised vol, thesis-driven, under-covered
biotech/tech. The next test is not to restore the weights; it is to ask, on the 152, *for which
kind of name does the event count carry*, with the conditioning variable chosen BEFORE looking
(realised-vol tercile, coverage tercile, sector). If it carries in the high-vol tercile and not
elsewhere, that is a conditional positive with a mechanism (events move names that can move), and
the sealed book can claim on that cell only. If it carries nowhere, the withdrawal stands.

## 1. Roadmap — done / left (the honest split)

| item | status |
|---|---|
| §4 Monday-safety P0.0–P0.5 | **DONE, deployed** (`42d5b4c+dirty` running) |
| §5 information layer: corpus, calendar, EDGAR/IR/fleet news, features panel | **DONE** (80,212 obs; 152-name panel) |
| §10 T1 blind tournament | **DONE — negative** (no information; second family blocked on capacity) |
| §10 T2 refusal NAV | **DONE — table only** (null empty; says what refused ideas are worth, not that refusing won) |
| §10 T3 sector-lead | **DONE — negative on the laggard**; see §2 below for what it did show |
| §10 T6 rule cells | **DONE — (a)×(e) 1.49× but below MDE; (b) untestable for weeks** |
| §10 T7 sealed pre-open book | **DONE — seals, claims nothing by derivation**; must be sealed LOCALLY before 09:15 ET |
| §10 T4 coverage shock, T5 catalyst windows, T8 instrument A/B grade, T9 timing, T10 Asia lead | **LEFT** |
| §5 generators 1/4/5/7 as separate candidate files; edge table v0 | **LEFT** |
| §5 discovery autopsy → research queue → next digest | **LEFT** (receipt is written nightly, nobody reads it) |
| §6 local-model lifecycle | DONE by policy (nothing resident); HF is OFF by Murat's instruction |
| NN progression stages 0–3 | **NOT STARTED, correctly** — no sealed vintages yet |

Roughly: **guards and sensors 100%, tests 5 of 10 asked (4 negative, 1 control), discovery
generators 0%, learning 0%.** Zero of it has moved P&L; that is expected before the first sealed
week.

## 2. Find what works — Murat's instruction, and it is a fair one

Every test since Friday returned a negative. Some of that is the market; some is how the
questions were posed (global, cross-sectional, 21-day, one encoding). The record already holds
positives; the next session's job is to put them in the books' path and to pose the conditional
questions. On record, with receipts:

- **Overnight vs intraday**, CRSP 1993-2024 EW top-200: overnight 164.6× (t +7.92), intraday 0.09×.
  Consequence already partly taken (no 09:30–09:45 entries). Not yet taken: **enter at MOC, exit
  at the open** as the default share expression → T9 decides it this week.
- **The measured drift exit** worked live (DKNG +2.5% target hit, 28 Aug).
- **Source-PEAD pair** (short loser / long IWM) +0.35%/+0.26%, t≈2 — the one event lane with a
  positive paired receipt.
- **SUE × reaction**: the REACTION carries the information (commit 7db0126) — encode the day-1
  reaction to an event, not the count of events.
- **profit_roe** cross-section ic_t 4.18, monotone 0.90 over 32 years — a STEP, build it WIDE;
  **mom_12_1** k=20 $971k; **liquid** t 2.55 at low te.
- **T3's own table**: every arm after a driver-wide attention shock is positive on the mean
  (+3.9 to +6.7%) — the laggard lost to the middle, but the SHOCK itself is untested against
  random dates. Test it (null = same drivers, shuffled dates).
- **T6's (a)×(e) cell** is 1.49× on the mean and positive on the median while every other cell
  is ≤1.10× — below MDE, so not a claim, but the direction is the one Murat's own 2025 list
  showed (9 of 14 up). Pre-register it and let the vintages accrue.
- **Murat's rule, live**: MU passes (a) at 1.61 with a dated catalyst 21 Sep and HBM sold out.

Rule for the session: **every negative must name the conditional question it did not ask**, and
**every test must be paired with its mirror** (T1 blinded → T1 with names as the treatment; T3
laggard → the shock itself; T6 global → by sector/vol tercile). A harness that can only say "no"
is as broken as one that can only say "yes"; the shuffled null is the check on the first, the
mirror test is the check on the second.

## 3. Next items, in order (gates, not dates)

1. **Conditional IC on the 152** (`corpus_features --ic --by realised_vol_20d,coverage_baseline_90d,sector`):
   pre-declare the cut (terciles), report each cell with n and CI, BH-FDR across cells. If a cell
   clears, `prediction_book` may claim on that cell only (`CLAIMING` derived per cell).
2. **Encode SURPRISE, not count**: for each corpus event, day-0 abnormal return and abnormal
   volume (vs SPY and the name's own 60-day sigma) → `ev_<type>_surprise_20d` features. The
   SUE×reaction finding says this is where the information is.
3. **T5 catalyst windows** now that the calendar accrues daily vintages (start with the 8,480
   earnings dates: pre-10 / post-10 sessions by coverage tercile; null = ±30-day shifted dates).
4. **T3 mirror**: driver-wide attention shock vs shuffled dates; if positive, a SHADOW lane on
   hack6 that buys the driver's MIDDLE name (not the laggard) at MOC, 21-session hold, 3%/name.
5. **T9 timing** on the taken decisions since kickoff: shadow fills at 09:45 / 10:30 / MOC from
   minute bars; the winner becomes the default `entry_timing`.
6. **Discovery autopsy → research queue → digest `--symbols`** (close the loop that writes a
   receipt nobody reads).
7. **Generators as separate files** (event, analyst-dislocation, undercoverage, Asia lead) feeding
   the sealed book; T4 on the 152.
8. **T1 second family** when `hf_glm` has credits or NVIDIA stops 429-ing — until then, do not
   spend Featherless on it again.
9. **Bias-state panel (T11, new — §5)**.

## 4. Providers — Murat's ruling, applied

- **HF is OFF** (402, and off by instruction). Do not probe it; do not route to it.
- Order for bulk work: **DeepSeek (default, and the fallback) → Featherless → NVIDIA**. NVIDIA is
  free but rate-limited (kimi 429, minimax/gemma timeouts at 10:40 SGT) — treat it as the skeptic
  when it answers, never as the bulk path. NVIDIA **embeddings** (`nemotron-3-embed-1b`) stay the
  novelty/independence model.
- **OpenAI**: the key Murat pasted returns HTTP 401 "Incorrect API key" — it is truncated in the
  paste (a `sk-proj-` key is ~160 chars; this one is 100). It sits in `.env` as
  `AAT_OPENAI_API_KEY`; Murat re-pastes the full key and rotates it afterwards (it is in a chat
  transcript). Provider `openai` in `providers.py` is wired to `gpt-5-mini`; change to
  `gpt-5-nano` for bulk.
- **Price per 1M tokens (in / out), read 30 Aug:** DeepSeek V4-Flash **$0.22 / $0.66** (half
  off-peak; cache hits $0.007); OpenAI gpt-5-nano **$0.05 / $0.40**, gpt-5.6-luna $0.20 / $1.20,
  Batch API −50%, web-search tool $10 per 1k calls; Featherless is a subscription — the $25 Chat
  plan **forbids API/background automation** (the Developer plan, $50 credits/mo, is the legal
  one for our use); NVIDIA hosted endpoints free with rate limits. **For web scraping the answer
  is $0: fetching is Python** (EDGAR JSON, Alpaca news, Finnhub, RSS, GDELT) and the LLM is spent
  only on classification/extraction of the fetched text — gpt-5-nano in batch or DeepSeek Flash
  off-peak for that, DeepSeek for Chinese/Japanese/Korean.

## 5. NVIDIA lane (Murat's links, logged with gates — nothing here before the sealed week exists)

| what | it is | use for us | setup / gate |
|---|---|---|---|
| **Quantitative Signal Discovery Agent** (`github.com/NVIDIA-AI-Blueprints/quantitative-signal-discovery-agent`) | 3 agents (Signal → Code → Eval) over yfinance S&P-500 OHLCV; Eval = Rank IC with p-value/IR/positive-IC ratio, accept at |IC| ≥ 0.02 & p ≤ 0.05; runs CPU-only against hosted NIM | **Point it at OUR panel** (corpus features + CRSP farm) instead of price-volume operators: the Eval agent's `signal_evaluator.py` is reusable as-is; the Signal agent becomes generator #11 ("LLM proposes a formula over declared features, code tests it, nothing trades") | `uv sync`, `NVIDIA_API_KEY`, `download_data`; gate: every accepted signal goes through OUR MDE + BH-FDR before it is called a signal (their 0.02 bar is not ours) |
| **NeMo Agent Toolkit** (`pip install nvidia-nat`; `aiq` command is now `nat`) | framework-agnostic agent wiring; web search via Tavily (needs `TAVILY_API_KEY`) | a governed harness for the research agents; Tavily for the "whole-internet" pass Murat asked for | install in a venv on the laptop; gate: every fetched page becomes a corpus Observation with observed_at, or it is not evidence |
| **NemoClaw** (Hermes agent / LangChain Deep Agents Code + Nemotron 3 Ultra + OpenShell sandbox) | self-improving agent runtime with sandboxed tools | overnight research agent that reads the corpus and writes typed hypotheses (never orders) | Nemotron 3 Ultra needs 48 GB+ VRAM locally → hosted only; **after 4 Sep** |
| Featured models (screenshot): kimi-k3, deepseek-v4-pro, nemotron-3.5-lightning-30b, nemotron-3-ultra | hosted, free, rate-limited | council voices; `nemotron-3.5-lightning-30b` is worth probing as a cheap fast skeptic | add to `providers.py` behind the 429-aware probe |

## 6. Bias-state panel (T11) — the part Murat thinks is novel, made testable

The literature (2026: multi-dimensional sentiment — relevance/polarity/intensity/uncertainty/
forwardness; event-conditional sentiment; dissemination-aware signals; look-ahead detection for
LLM forecasts) says two things we already found: polarity alone is weak, and the information sits
in *what kind* of event, *how fast it spreads*, and *what was expected*. What nobody in that
literature does is **encode the psychological state of the holders as a number and condition the
event response on it.** That is the novel claim, and it is cheap to build from data we already
hold:

| bias | numeric state (PIT, from bars + corpus) | hypothesis to test |
|---|---|---|
| anchoring | distance from 52-week high / from the last round number; days since the high | good news lands harder near an anchor (resistance) — response by anchor-distance tercile |
| disposition effect | capital-gains overhang: volume-weighted share of the last 120 sessions' turnover ABOVE the current price | names with most holders under water UNDER-react to good news (sellers into strength) |
| attention | abnormal volume + `attention_z` + Google Trends (`trends_sentiment.py` exists in Aegis) | high attention → over-reaction and reversal; low attention → drift (the normalisation thesis, as a state not a bonus) |
| narrative concentration | entropy of embedding clusters over the last 20 days' titles | one-story names move more on a contradiction; many-story names shrug |
| expectation | implied move from the chain vs realised; analyst dispersion | surprise = realised − expected; **this is SUE×reaction generalised to every event type** |
| herding | analyst revision clustering (n revisions in 5 days / 90-day rate) | late-cluster revisions after a move carry nothing; early ones do |
| diffusion speed | hours from first report to 5 independent sources | slow diffusion + low coverage → drift (FinGPT's dissemination result) |

Test design: features at t, response = 21-session SPY-relative return AFTER a dated event,
conditioned on bias state tercile × event type; null = shuffled states within event type; BH-FDR
across cells; pre-register in `docs/TRIALS/` before the first look. Pass = a cell that survives
on the 152 AND on the CRSP farm's characteristic panel (the farm can run the anchoring and
disposition states over 32 years today — `characteristics.py` joins PIT; overhang is one join on
`crsp.dsf`).

## 7. For Murat, in one paragraph

Monday: seal the book locally before 09:15 ET (`python -m scripts.prediction_book --seal`); close
hack5's BE calls if you agree; MU is the only shortlist name that passes your own rule. Re-paste the
full OpenAI key. The blueprint that is actually useful to us this week is the Signal-Discovery
agent's evaluator pointed at our panel; NemoClaw is after 4 Sep. HF stays off.
