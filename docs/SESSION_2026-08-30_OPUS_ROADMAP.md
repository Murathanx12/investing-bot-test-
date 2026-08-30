# SESSION 2026-08-30 (Opus) — THE ROADMAP TESTS, AND A RESULT THAT DID NOT SURVIVE ITS UNIVERSE

**Suite:** 51 → **54 suites, 2,277 checks, all green.**
**Commits:** `46b595e`, `b7a0319`, `85e6271`, `961c69a` (+ this handoff).
**Nothing was deployed** — everything here is research and offline tooling; the
six loops still run `42d5b4c+dirty`, which is Friday's Monday-safety build.

---

## 0. SCOREBOARD

**RESULT IMPROVEMENT: NONE.** No trade, no promotion. What changed is that one
result was withdrawn, two tests that could not previously be *asked* were asked
and answered negative, and the pre-open book now claims nothing on purpose.

| | before | after |
|---|---|---|
| features panel | 23 symbols / 5,678 symbol-days | **152 / 37,601** |
| features clearing a 95% CI | **7 of 29** (on 23 names) | **0 of 29** (on 152) |
| T3 sector-lead | **could not be asked** | 269 events, six real drivers, negative |
| T6 rule cells | not run | run; condition (b) UNAVAILABLE and said so |
| refusal NAV | one pooled number | **13 classes, three kinds, nulls named** |
| sealed pre-open book | did not exist | exists, hashed, **0 claims by derivation** |
| tradable universe | 98 names | **94** — four were delisted/bankrupt |

---

## 1. THE ONE THAT MATTERS: "EVENT COUNTS CARRY INFORMATION" WAS 23 NAMES

Full receipt: `docs/FINDING_2026-08-30_THE_EVENT_COUNTS_WERE_TWENTY_THREE_NAMES.md`.

Rank IC vs the 21-session SPY-relative return, block bootstrap, **11 date blocks
in both runs**, same harness, same period:

| feature | 23 symbols | 152 symbols | 95% CI (wide) |
|---|---:|---:|---|
| `ev_insider_20d` | **+0.148** | +0.023 | [−0.004, +0.046] |
| `ev_earnings_20d` | **+0.155** | +0.005 | [−0.052, +0.059] |
| `ev_macro_20d` | +0.118 | +0.040 | [−0.011, +0.085] |
| `ev_contract_20d` | +0.103 | −0.000 | [−0.041, +0.036] |
| `ev_analyst_rating_20d` | +0.098 | +0.020 | [−0.032, +0.072] |

Seven features cleared zero on the narrow panel. **Zero of 29 clear it on the
wide one.**

**It is the universe, not the harness.** Re-running the *same 23 symbols*
through the *wide build's own files* reproduces +0.139 / +0.145 / +0.086. The 23
were Murat's own names plus the benchmarks — chosen because they were
interesting, over a window in which MU ran +702.7%, MRVL +197.5%, AMD +185.0%.

**Coverage is ruled out, not assumed.** It was the first suspect (Benzinga files
1,566 items on NVDA and 3–4 on AARD). `coverage_baseline_90d` alone has a
per-day cross-sectional IC of **+0.0004**, and normalising each count by the
name's own 90-day baseline moves the ICs by under 0.005. The counts are not a
coverage proxy; they are just weak.

**What this is not:** it is not evidence that events don't matter. It is
evidence that *a count of event headlines in a 20-day window, ranked
cross-sectionally* does not predict 21 sessions on a broad universe. Surprise,
direction and magnitude are untested encodings.

---

## 2. THE SEALED PRE-OPEN BOOK (T7) — AND WHY IT CLAIMS NOTHING

`scripts/prediction_book.py`. One file per ET trading day, sha256 of its own
content inside it and in an append-only `seals.jsonl`. A reseal writes **beside**
the original and logs both hashes — a book cannot be replaced silently. PIT
twice over: corpus rows cut at the seal **instant**, price context at the last
**closed** session.

`CLAIMING` is **derived from the CIs**, not asserted, so it turns itself on when
a signal earns it and off when one stops. Today: **151 considered, 0 claims.**
A no-claim book is still worth sealing — it is the control the named digest is
measured against, and every sealed day is a vintage.

**To run it Monday, before 09:15 ET:**

```
python -m scripts.prediction_book --seal      # local: it needs state/corpus
python -m scripts.prediction_book --verify    # re-hash every sealed book
```

It cannot run on Railway: the panel and corpus live in `state/`, which is
gitignored and local.

---

## 3. T2 — REFUSAL-LEDGER NAV, BY CLASS

`scripts/refusal_nav.py` + `alpha/refusal_classes.py`. 7,599 refused rows,
13 classes, **three kinds that are never pooled**: *merit* (was the idea good),
*book state* (should the book have had room — a positive number there means the
book was full, which is what a limit does), and *tournament* (the ranker
preferred a sibling structure, so the idea was usually taken in another
instrument and counting it as discarded edge double-counts one forecast).

Pooling those three is how 2026-08-29 printed *"the gate is discarding edge —
loosen it."*

A classifier bug the test caught: `"8 structures enumerated…, none cleared the
gates. aggregate convex risk is already 61%"` is a **forecast-level** refusal
that *quotes* the gate which stopped its best structure. Matching the tail first
put **473** of those into `AGGREGATE_RISK` (2,823 → 2,350).

**Tonight's table, and what it does not say.** Every scored class is negative:
MDE −$14,399 / 123 worlds, AGGREGATE_RISK −$68,002 / 66, EDGE_BELOW_BAR
−$21,765 / 57. **But the null is empty** — none of the 23 taken decisions can be
marked, because their legs have expired and today's quotes cannot price a
contract that no longer trades. So the table says what the *refused* ideas would
be worth now; it does **not** say refusing beat trading. That sentence prints
above the table.

`ALREADY_HELD` (903) and `DAILY_LOSS_LATCH` (538) carry no legs at all and read
CANNOT DETERMINE, never zero.

---

## 4. T6 AND T3 (`scripts/rule_cells.py`)

**T6 — condition (b) cannot be tested and is not.** `rating_counts_mean` is
non-null on **135 of 37,601** symbol-days: `analyst_panel` records *forward*
from 2026-08-26, and using today's rating on a 2025 date is exactly the
lookahead that panel exists to prevent. So the tested rule is (a) × (e):

| cell | 21d mean | median | terminal wealth | MDE |
|---|---:|---:|---:|---:|
| a AND e | +4.47% | +0.51% | **1.49×** | 23.29% |
| a only | +2.70% | +1.01% | 1.10× | 21.73% |
| e only | −0.73% | −3.14% | **0.92×** | 17.76% |
| neither | +0.65% | −1.09% | 1.08× | 15.26% |

Every cell **below its own MDE**. The readable part: **"already down" on its own
loses money**, agreeing with the CRSP knife-basket adjudication already on file
(−0.31%/5d, t −2.35). At 63 days there are 3 blocks and nothing can be read.

**T3 — no support for buying the driver's laggard.** 269 events, six real
drivers, shock = `attention_z ≥ 1.0` on ≥3 names in one driver on one day:

| arm | mean | median | terminal wealth |
|---|---:|---:|---:|
| laggard | +6.74% | **−4.09%** | 1.43× |
| leader | +3.92% | −3.62% | 1.28× |
| **the middle** | +6.56% | **+0.71%** | **1.50×** |

All below MDE. The laggard beats the leader but **loses to the middle on all
three measures**, and on the median it is the worst of the three.

T3 could not be asked before this session: on 23 names the only drivers with
three members were `murat_book`, `UNCLASSIFIED` and `index_beta`.

---

## 5. HOUSEKEEPING THAT WAS NOT HOUSEKEEPING

**Four names in the trading universe cannot be traded.** GES, GMS, SNBR and TPIC
were missing from the SEC ticker file — because they are no longer listed
registrants. Verified at the venue: GES and GMS are `inactive, tradable=False`;
SNBR and TPIC return **HTTP 404** (their SEC tickers are SNBRQ and TPICQ, and the
Q is the bankruptcy suffix; TPIC's newest filing is a `15-12G`, which *is*
deregistration). All four sat in the 98-name `window_universe.json` that
hack2/hack4/hack6 trade from, because that list is built from the earnings
calendar and **never asked the venue**. Now 94, with the drops named in the
receipt. Nothing could have filled, so it cost no money — it cost a count that
did not mean what it said.

**A four-hour clock hole.** `tests_smoke_fleet` wrote its council packet under
the **UTC** date while the writer and reader both key on the **ET trading day**,
so the suite passed 20 hours a day and failed for 4 — and failed at 00:5x UTC
last night. `exits.session_day()` is now the single definition. The same trap
appeared a third time in `corpus_features --until`, which defaulted to
`date.today() - 1` — the *machine's* date on a UTC+8 box — and asked SIP for a
session that had not closed (HTTP 403, which reads like a plan problem).

**Recorded and deliberately not fixed:** `ET_OFFSET` is a fixed −4h, so it is
EDT and will be an hour wrong from the first Sunday in November for anything
dated near midnight ET. Changing the repo's clock convention is not a change to
make the night before an open.

**`numpy` declared** (ten modules import it; it was in the image by accident of
another dependency).

---

## 6. T1's SECOND-FAMILY CONTROL — BLOCKED ON CAPACITY

`--provider` now pins the family (roadmap §6 asked for it); a pinned provider
that is down **refuses rather than falling back**, because a run that silently
changes model answers a different question.

**A defect caught before it was paid for.** `derive_aliases` strips capitalised
tokens specific to a symbol's own titles. For SPY those are `U.S`, `Iran`,
`Bessent`, `Hormuz`, `Warsh` — the blinder was deleting the macro story and
producing *"the company.-Israel Agreement On Trade"*. The SPY control would have
measured whether a model can read shredded text. Index instruments now keep only
their declared aliases; the resulting asymmetry is stated on the receipt.

```
featherless   live   alibaba    <- the ORIGINAL run's family: useless as a control
nvidia_kimi   down   moonshot   HTTP 429
hf_glm        down   zhipu      HTTP 402 monthly included credits depleted
```

**For Murat:** hf_glm needs credits (402 is a budget wall, not a blip). Then:

```
python -m scripts.blind_tournament --provider hf_glm --max-calls 120 \
    --run-id 20260830T_glm120
```

---

## 7. OPEN, IN PRIORITY ORDER

1. **Seal Monday's book before 09:15 ET** (local; §2).
2. **T1's control** — needs hf_glm credits or nvidia_kimi's 429 to clear.
3. **T5 (catalyst approach/aftermath)** is the next untried test; T9/T10 need a
   week of sealed books first.
4. **Condition (b) becomes testable in weeks** — `analyst_panel` captures ~60
   names a day, and at ~30 vintages T6 becomes the three-condition test.
5. **Eleven blocks is the binding constraint** on every cell in §4, and it is a
   calendar fact. Only time fixes it.
6. **ET_OFFSET DST**, before November.

## 8. WHAT NOT TO DO

- Do not restore the narrow-panel weights because they look better. That is the
  finding.
- Do not read T6's `a AND e` +4.47% as an edge: its MDE is 23.29%.
- Do not run T1 on `featherless` and call it a second family.
- Do not let the sealed book claim while `CLAIMING` is False — it is derived, so
  the way to make it claim is to earn it on a universe nobody chose.
