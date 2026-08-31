# FEEDBACK — Opus → Fable, 2026-08-31

Written against `NEXT_SESSION_2026-08-31i_FABLE_WBUY_ROOT_CAUSE_AND_ADAPTIVE_DECISIONS.md`
(`2237e7c`). That brief is right about almost everything and I am not restating
it. This is the delta: **two things I built that change its assumptions, one
purchase recommendation it gets wrong, one experiment it should run before
softening a band, and the design for Murat's newest question.**

Murat's governing sentence, which I am treating as the ranking rule for
everything below:

> *"don't generalize, go deeper to the root cause… we make a decision, see
> result, see if it's good or not and we adjust. there is no fixed path."*

---

## 0. RESULT IMPROVEMENT: NONE (yet). Two structural cuts CLOSED.

Nothing traded differently today. Four positions across six books, and three
books ~9% below the other three on *realised* losses. The system is not sizing
badly — **it is barely deciding at all**, and today found out why.

| role | equity | positions |
|---|---|---|
| hack1 | $99,250 | 0 |
| hack2 | $99,239 | 0 |
| hack3 | $90,923 | 1 (BE) |
| hack4 | $99,197 | 1 (NVDA) |
| hack5 | $91,419 | 2 (BE, PLUG calls) |
| hack6 | $90,706 | 0 |

---

## 1. "The engine did not digest the news" is FALSE, and the true answer is worse

The digest **did** digest it. On 08-31 `premarket_digest` ranked **WBUY first**
and wrote a real bet — up, +10%, one session, `p_already_priced 0.70`, with a
falsifier. The stock moved 20%.

No gate rejected it. **Nothing that could place an order ever read the file.**

| reader of `state/premarket/<day>.json` | its own docstring |
|---|---|
| `dislocation_scan.py:108` | *"It places nothing"* (line 24) |
| `discovery_autopsy.py:66` | *"Shadow. Places nothing."* |

`run_pass.py` — the only placer — built its universe from four sources
(`:171-217`): the hardcoded list, `window_universe.json`, `candidates/<date>.json`,
and the seal. The digest was not among them.

**This is the same shape as the artery cut closed hours earlier, one stage
upstream.** There: book → runner. Here: discovery → book. Both components ran,
wrote receipts, and passed their tests; the defect lived *between* files, which
is why 2,687 checks never saw it.

**A pipeline needs a reachability test, not per-stage correctness.** That is the
generalisable lesson and it should go in canon.

### CLOSED — `012a35c`, proof 7, 12 executed checks

`inject_news_universe` mirrors `inject_sealed_portfolio`: off unless asked
(`--news-universe`), adds names in the **digest's own rank order** (re-scoring
here would be a second unrecorded opinion), and **refuses — exit 2 —** when the
digest is missing, stale (>18h) or undateable. *"The digest found nothing"* and
*"the digest never ran"* are the same silence on disk.

Verified on the real day file: universe 15 → 24, **WBUY at rank 0**.

> Widening the universe is not authorising a trade. Admission, sizing, the
> liquidity floor and the sealed-weight ceiling are untouched.

---

## 2. Your §4 is right and is now BUILT — `6ad7232`

One constant did two jobs. `MIN_DOLLAR_VOLUME` decided both *"can we buy this at
our size?"* and *"are we allowed to KNOW about this?"*, and a single `continue`
in `universe.build()` deleted the name.

**We did not decide against WBUY. We arranged never to have an opinion about it.**

Split into `MIN_OBSERVE_DOLLAR_VOLUME` ($20k) and `MIN_EXECUTE_DOLLAR_VOLUME`
($3m, unchanged). `load()` still defaults to execute scope, so **every existing
caller behaves exactly as before**. `execution_authority()` now answers the
question that deletion used to answer:

| median $vol/day | tier | max position |
|---|---|---|
| $25k (WBUY) | `OBSERVE_ONLY` | **$250** (0.25% of a $99k book) |
| $1.2m | `OBSERVE_ONLY` | $12,000 |
| $40m | `FULL` | $400,000 |
| unknown | `UNKNOWN` | **authorises nothing** |

That last row is the one to defend. An absent dollar volume is not zero and not
a million; it reports unknown and authorises nothing.

**NOT YET TRUE, and said in the module rather than implied:** the stored
universe file was *built* at the execute floor, so `load(scope="observe")`
returns the same 4,634 names until `build(scope="observe")` runs against the
venue. **The structure is in place; the data is not.** That rebuild is your
first task — it is a venue call, not a design question.

---

## 3. Before you soften the >400% band, run the experiment that may DELETE it

Murat: *"when we limit stocks by high increase band saying overall bad we are
losing on great winners too."* He is likely right, and I can be more specific
than "make it a warning."

I measured that band at **−26.47%/yr over 11 years**. Your brief proposes
downgrading `REJECT` → `HIGH_UPSIDE_ANOMALY`. **Do not do that first.** Our own
receipts already contain the alternative hypothesis:

> `feedback_a_stale_target_across_a_split_is_not_an_opinion` — the +400% band has
> **median 44×**, and capping it flipped a screen from **−5.5%/yr to +3.9%/yr,
> t 2.16**.

So the live question is not *"should the ban be a warning?"* It is:

**How much of −26.47%/yr survives once stale and split-unadjusted targets are
removed from the band?**

Run that first. Three outcomes, three different next moves:

- **It flips positive** → the band was never bad. It was a *data-integrity*
  bucket wearing a statistical costume, and the correct fix is the integrity
  rule you already classify as hard, not a softened prior. The >400% "finding"
  gets retracted.
- **It stays negative but weakens** → your anomaly taxonomy is right and worth
  the build.
- **It is unchanged** → the band is real and the anomaly book is a corpse
  waiting to happen. Budget accordingly.

Softening the gate before running this risks *learning the contamination*.
Murat's rule — go to root cause, don't generalise — cuts against the softening
as much as against the ban.

---

## 4. Analyst provenance: Murat's newest question, and we ALREADY OWN THE DATA

> *"dissect them into categories based on what company is making the analysis,
> who is making it, is this reliable?"*

This is the best idea in the thread, because it is **measurable rather than a
vibe** — and the answer changes the purchase decision.

`tr_ibes.ptgdetu` — **price-target DETAIL**, entitled, verified today:

```
4,658,468 individual price targets   2013-01-01 .. 2026-05-14
37,343 tickers | 1,348 brokers | 33,043 analysts
2,215,396 targets since 2020 carry a NAMED analyst
```

Per-target columns: `estimid` (broker), `alysnam` (analyst name),
**`amaskcd` (stable analyst ID that follows a person across firm changes)**,
`horizon`, `value`, `anndats` (**the PIT bound — when it became public**).
`recddet` carries the same provenance for ratings via `ireccd` / `emaskcd`.

Busiest brokers since 2020: GOLDMAN 109,364 targets / 5,121 names; JPMORGAN
96,946 / 5,487; MORGAN 91,267 / 5,431 — down a long tail to boutiques covering
a dozen names.

### What to build (in this order)

1. **Per-broker and per-analyst measured skill**, not reputation: hit rate at
   the target's own `horizon`, signed bias (systematic optimism), dispersion,
   and revision velocity — each computed **only from `anndats` forward**.
2. **Coverage breadth as a feature.** A boutique covering 12 names and a
   bulge bracket covering 5,400 are different instruments. Breadth is a proxy
   for both specialisation and for conflict exposure.
3. `amaskcd` is the crown jewel: it lets us ask **"is this person good?"**
   separately from **"is this firm good?"** — an analyst who moves from a
   boutique to Goldman carries their record with them. Nothing on the shopping
   list offers that.
4. **The decisive control, and it must be run before any of this is believed:**
   *does broker/analyst identity add anything over the plain consensus?* Build a
   skill-weighted consensus and an equal-weighted consensus, compare out of
   sample. If skill-weighting does not beat equal-weighting, provenance is a
   story and the whole branch is a corpse. Pre-register that.
5. **`SOURCE_DISAGREEMENT` as a first-class feature.** Your §5 is right that
   sell-side target, consensus, vendor "fair value", algorithmic forecast, our
   valuation, and 52-week range must never collapse into the word "forecast".
   WBUY is the exhibit: MarketBeat shows one Sell with no target, TipRanks has
   nothing, algorithmic sites print $4–5. That spread is **information**, and
   in a nano-cap with an equity line outstanding it is probably the *dominant*
   information.

### Therefore, the purchase recommendation — I disagree with the thread

| service | verdict | why |
|---|---|---|
| **Koyfin ($39/mo, analyst consensus)** | **NO** | We own 4.66m analyst-level targets with names, stable IDs and PIT dates back to 2013. Koyfin sells us a *thinner* version of what we already have. |
| **InvestingPro** | **NO for the engine** | They state they have no public API. Buying it to scrape 70k names is fragile and against their terms. *Possibly* one month purely as a **benchmark** for their fair-value models on a 300-name stratified sample — treat as a model to beat, never as truth. |
| **WSJ** | **NO** | Buy it if you want to read it. One newspaper cannot be infrastructure: it misses small caps, foreign-language sources, filings, FDA, suppliers. |
| **Quiver ($30, one month)** | **ONLY AFTER** the free path exists | Build SEC Form 4 + STOCK Act ingestion first, then use one Quiver month to **check our own entity mapping**. Buying first means buying a dependency instead of a benchmark. |

**The strongest lever we have not pulled costs nothing: `ptgdetu` is sitting in
WRDS, entitled, 4.66 million rows deep.** Spending $39/mo on consensus while
that is unread is the actual error to avoid this month.

---

## 5. Four clocks (your §7) — one correction

Your ordering is right; one thing to make non-negotiable in code rather than in
prose. Every ownership and disclosure source needs **three** timestamps stored
separately:

```
transaction_date   what the filer did, and when
filing_date        when they told the regulator
first_seen_at      when WE could observe it
```

Never backtest from `transaction_date`. The 13F study already paid for this
once: `fdate − rdate` has **median 0, min 0, max 0** — it *equals* `rdate`, so
using it as the knowability bound would have assumed a quarter's holdings were
public 45 days before they were, on 72.7m rows, producing a confident wrong
answer. Politicians have the identical trap with a ~45-day disclosure window.

And the framing that already inverted once today: **13F is a receipt, not an
intention.** Institutions *selling >10%* predicted **+26.00%/yr** against
*buying >10%* at **+8.35%**, monotone, surviving popularity, trailing-return
**and** liquidity-band controls, strongest in `10m–50m` at **+32.54% net**. Do
not let the richer ownership feature set quietly re-import "they are buying, so
should we."

---

## 6. What I think should be done next, ranked

1. **`build(scope="observe")` against the venue.** Everything else in this
   document is blocked on it. The structure exists; the data does not.
2. **Give WBUY a CompanyState row** and grade it at 1/5/21/63d. It is the first
   name that exists in our records *without being buyable* — that is the test of
   §2, not a favour to one stock.
3. **Run the >400% contamination experiment (§3)** before writing the anomaly
   taxonomy. It may retract the finding the taxonomy is built on.
4. **Per-broker/per-analyst skill from `ptgdetu`**, with the equal-weight
   control pre-registered (§4).
5. **The DecisionCard** (your §1). It is the right shape and it is what Murat has
   asked for four times: *"I estimate a 63% chance this pays +45% over six
   months… because liquidity is terrible I would prefer Candidate B unless WBUY
   falls below $0.78."* Not "passed screen." Note that `execution_authority`
   already supplies its `capital authority` field — wire it, don't rebuild it.
6. **Form 4 before politicians.** Insiders disclose in ~2 days; politicians in
   ~45. One is a sensor, the other is structure. `TRIAL-CONGRESS-IC` is already
   a corpse — read it before re-deriving it.

**Not in scope and not to be touched:** hack4 activation still fails condition 1
(203 rows `rec_status: error:HTTP 503`, `latest.json` stale). Murat's approval
in `32178bd` is recorded and does not expire — but it explicitly does not
authorise trading a partial artifact, and it never authorised hack1/2/3/5/6.

---

## 7. The one methodological thing I want you to carry

Murat asked why an engine that found a great stock could not say *"I think by
x% it's a good buy, good because of these, bad because of these, I'd rather get
this than that."*

The reason is not missing intelligence. **Every stage in the chain was written
to return a verdict, and no stage was written to return a decision.** A verdict
composes badly: `REJECT` cannot be traded against `REJECT`. A decision composes:
a probability, a magnitude, a downside, a confidence and an authority can be
ranked against every other name in the book, and — critically — **can be graded
later against what happened.**

That is why the DecisionCard is not cosmetic. A system that only emits verdicts
cannot learn from being wrong, because "rejected" has no outcome to compare
against. Every gate we have argued about today — the $3m floor, the >400% band —
became harmful at exactly the moment it stopped producing a number and started
producing a word.
