# RUNBOOK — Monday 2026-09-08 — re-arm the fleet under contracts

**For Murat, before the open. Fifteen minutes, seven steps, one decision.**
Everything below is attended: no session flips a live flag on its own.

Written 2026-09-05 by Opus 5 with the B2 build (branch
`lab/night-2026-09-05`, terminal repo). What changed and why:
`docs/BUILD_B2_2026-09-05.md`.

---

## 0. What you are re-arming, in one paragraph

The books have been flat since judging day: the expiry guard liquidated
everything at 10:45 ET on 09-04, and entries were then disarmed by hand so the
−3%/+2.5% churn could not restart. Tonight's build gives every book a
**strategy contract** — a horizon, a minimum hold, falsifiers and a risk budget
— and makes `alpha/exits.py` obey it. A position may now only be closed early
for a typed reason (a stop, a deadline, a data error, a broken thesis); "the
price moved 3%" is no longer one. The daily 10:45 liquidation is keyed to the
mandate end date (2027-12-31), so it cannot fire every morning.

**Expected outcome:** the tracker books (hack3, hack4, hack6) take positions on
Monday's 10:01 ET pass and still hold them on Tuesday, Wednesday and the
Monday after. If they are flat again on Tuesday morning, something in this
runbook did not take, and §6 says how to tell which.

---

## 1. Merge and push (laptop, any time before the open)

```bash
cd ~/aegis-alpha-terminal
git checkout main
git merge --no-ff lab/night-2026-09-05        # the B2 build
python run_tests.py                            # expect: 74 suites, ALL PASS
git push origin main

cd ~/aegis-finance
git push origin main                           # B1 + tonight's lab commits
```

`run_tests.py` is the ONLY supported way to run the terminal suite — it sets
the venue guard for every child process. A green suite here is necessary and
not sufficient; §5 is the live check.

## 2. Deploy each role (this also re-arms entries — read §3 first)

```bash
python -m scripts.fleet --deploy hack3 --up
python -m scripts.fleet --deploy hack4 --up
python -m scripts.fleet --deploy hack6 --up
```

`--deploy` writes **every** variable from `alpha/fleet.py` and reads them back,
so it will:

- set `AAT_MANDATE_END_UTC=2027-12-31T15:00:00Z` (the new liquidation date);
- set `AAT_LOOP_EXPIRY=2027-12-31` for the share books (their horizon now comes
  from their contract, not from this flag);
- **overwrite `AAT_LOOP_ARGS`, removing the manual `--manage-only`** — this is
  the step that re-arms entries;
- restore `AAT_ENTRY_STYLE=staggered` on hack6, which the mandate declares.

hack1 stays manage-only **by declaration** (`Mandate.manage_only=True`); hack2
and hack5 are left as they are for now — hack2 can originate a short and its
expression is the one the 09-05 finding refuted.

## 3. The one decision before you run §2

**Do you want hack4 and hack6 entering at the open, or on the 10:01 pass?**
hack6 declares `staggered` (half into the auction, the rest at 10:01); hack4
declares nothing and takes the whole weight at 10:01. Leaving both as declared
is the default and needs no action. To hold a book back one more session,
deploy it without `--up` and start it when you want it.

## 4. Verify the deploy took (before 09:30 ET)

```bash
railway variables --service aat-loop-hack4 | grep -E "LOOP_ARGS|MANDATE_END|EXPIRY|ENTRY_STYLE"
railway logs --service aat-loop-hack4 | tail -40
python -m scripts.utilization                  # ENTRY AUTHORITY section
```

`scripts/utilization` now prints, per role, **ARMED / DISARMED and the binding
constraint**. Two of the four possible disarms live in Railway variables and it
says so rather than guessing. What you want to see:

- `AAT_LOOP_ARGS` with **no** `--manage-only` for hack3/4/6;
- `AAT_MANDATE_END_UTC=2027-12-31T15:00:00Z`;
- the log line `horizon from the strategy contract for role hack4: 21 trading
  sessions` (NOT "horizon derived from expiry").

## 5. The seal, and the first book under hygiene-only

The first seal after this build is the first one under the hygiene-only band
prior (Murat's decision B.1: the ratio is a displayed indicator and a model
feature, never a gate).

```bash
python -m scripts.prediction_book --seal --universe tracker
python -m scripts.prediction_book --publish
python -m alpha.brains.tracker_portfolio      # or: scripts/utilization --why-idle
```

**The seal now REFUSES a book whose portfolios carry no contract.** If it
refuses, it prints every problem at once — that is the guard working, not an
outage. Each holding carries `expected_horizon_sessions`, `min_normal_hold_sessions`,
`thesis_expiry`, `hard_falsifiers`, `risk_budget_usd` and `emergency_exit_reasons`
inside `content_sha256`.

## 6. After the open — the three things that say it worked

**10:05 ET.** `railway logs --service aat-loop-hack4 | grep -i submitted` —
names went on.

**11:00 ET.** No `CLOSED` lines for those names. If you see one, read its
reason: it now begins with a typed code. `HARD_RISK_LIMIT` on the first morning
means the stop is inside the noise for that name and is a finding worth
keeping; `HELD under contract` is the line you want to see repeated.

**Tuesday 09:45 ET.** The positions are still there. This is the actual test:
the old rule round-tripped 60% of positions inside their opening session.

```bash
python -m scripts.daily_learning_report        # section (c2) HOLDING DISCIPLINE
```

(c2) prints the exit-reason census and the same-session round-trip percentage.
A morning with zero exits and armed entries is a book holding a thesis.

## 6b. One thing that will look like a bug and is not

A **local** dry pass with the fleet's new expiry refuses:

```
REFUSED: expiry 2027-12-31 is after the mandate end 2026-09-04 ...
```

That is correct. The mandate end is the variable `AAT_MANDATE_END_UTC`, which
`fleet --deploy` sets on every Railway service (2027-12-31) and which a bare
local shell does not have — so the local default falls back to the old contest
deadline. To reproduce the live configuration locally:

```bash
AAT_MANDATE_END_UTC=2027-12-31T15:00:00Z python -m scripts.run_pass --expiry 2027-12-31 --dry-run ...
```

## 7. If something is wrong — how to stop, cleanly

```bash
railway variables --service aat-loop-hack4 --set "AAT_LOOP_ARGS=<old args> --manage-only"
# or, to stop the service entirely:
railway down --service aat-loop-hack4
```

`--manage-only` keeps exits, stops, fills and marking running while forbidding
new positions: the book can only get smaller. That is the correct emergency
brake and it is instantly reversible.

---

## What this build does NOT do, and you should know before Monday

1. **The 3:1 edge-vs-stop floor is measured on every order and BINDS only on
   naked shorts.** Applied to every book it refuses 100% of what the tracker
   books select — their own sealed `exp_return` is 1–3% against a 6–8% stop,
   which is 0.2–0.4:1. That is a finding about the books, and binding it
   tonight would have emptied the accounts this build exists to fill. The ratio
   is recorded on every admission so the decision can be made on a census.
2. **No book may open a naked short.** `Mandate.allow_short` is False for all
   six; the hedged pair-vs-IWM expression is untouched. Declaring it is one
   line, attended.
3. **Nothing was pushed, deployed or sealed by the session that wrote this.**
   Railway variables are exactly as you left them until you run §2.

---

# APPENDIX A — THE MONDAY DRY RUN (added 2026-09-05 by the B3 agent)

**Read this before §2.** It is the printout of what the three tracker books
would admit, what actually stops the rest, and the two things that will bite on
Monday if nobody looks. Nothing below was sealed, ordered, deployed or pushed.

Reproduce it in ten seconds, any time:

```bash
AAT_ACCOUNT_ROLE=hack1 python -m scripts.monday_dry_run --compare
```

It is a **REPLAY**, and it says so on every page: it writes to a temp directory,
never `state/predictions`, and it evaluates the vintage's freshness *as of the
vintage's own day* (`tracker_rows(day, asof=day)`). A LIVE seal passes no `asof`
and is still measured against today — pricing Monday's book on Friday's closes
is still a refusal.

Vintage used: **2026-09-02**, the newest tracker file on disk. 3,056 names
screened. `rec_status` not ok on 3 rows, `target_status` not ok on 101.

## A.1 The two things that will bite on Monday

**(1) The 10:01 pass declines, fail-closed, on all three books — right now.**
Run this morning against the live venue, dry (no `--live`):

```
hack3  EXIT=2  tracker_portfolio is enabled but its sealed portfolio could not be read:
               no sealed book for 2026-09-05 ... Declining rather than re-deriving.
hack4  EXIT=2  (identical)
hack6  EXIT=2  (identical)
```

That is the artery working exactly as designed, and it is also the whole
Monday risk in one line: **no seal, no trade.** The nightly tracker refresh has
not run since **2026-09-02**, so the ordered chain in §5 is not optional and it
must finish before 10:01 ET:

```bash
python -m scripts.tracker --refresh          # THIS is the step that is currently dead
python -m scripts.tracker --backfill-prices  # realised_vol_20d; without it hack3/6 seal EMPTY
python -m scripts.prediction_book --seal --universe tracker
python -m scripts.prediction_book --publish
```

**(2) `--dry-run` is not a flag.** §6b of this runbook tells you to run
`python -m scripts.run_pass --expiry 2027-12-31 --dry-run ...`. That is
`error: unrecognized arguments: --dry-run` — verified 2026-09-05. A pass is dry
by *default*; `--live` is what makes it send orders. The correct line is:

```bash
AAT_MANDATE_END_UTC=2027-12-31T15:00:00Z AAT_ACCOUNT_ROLE=hack4 \
  python -m scripts.run_pass --expiry 2027-12-31 --profile maximum \
  --brains tracker_portfolio          # no --live == dry
```

## A.2 What each book admits, and what actually binds

`BINDING` below is **`fails_only`** — the count of names that fail *only* that
rule, i.e. what relaxing it alone would buy. It is **not** the first-fired
reason. The chain short-circuits, so `excluded_by_reason` names the earliest
rule a name failed; on the 2026-09-01 seal it said "hack6: 541 names above the
20% downside cap", and dropping that rule alone yields 23. A reason count from a
short-circuiting chain is an ORDER.

### Under today's live setting (`AAT_BAND_MODE` unset = `returns`)

| book | pool → eligible → **admitted** | names | BINDING (drop it alone → admits) |
|---|---|---|---|
| hack3 | 806 → 416 → **10** | IVA TNXP IMRX LENZ ASPI DAKT INVA CRUS VST NPKI | downside above the 30% cap → **151** |
| hack4 | 806 → 31 → **5** | NB LAES ALMU ABAT FPS | catalyst beyond 30 calendar days → **607** |
| hack6 | 806 → 185 → **15** | MAZE NKTR RARE NAMS AMSC RUSHA INVA MLYS BUR TREE HLMN HDB GRAB CALX VST | downside above the 20% cap → **375** |

Sizes and the worst case, at the frozen $100,000 genesis equity:

| book | per name | gross | stop (profile) | worst case if every name gaps to its stop the same day |
|---|---|---|---|---|
| hack3 | 8.3% x 10 | 83% | 8.0% (`basket`) | **-6.64% = -$6,640** |
| hack4 | 10% x 5 | 50% | 6.0% (`maximum`) | **-3.00% = -$3,000** |
| hack6 | 6% x 15 | 90% | 3.0% (`aggressive`) | **-2.70% = -$2,700** |

### Under decision B.1 §4a (`AAT_BAND_MODE=hygiene_only`) — **NOT ENABLED**

| book | pool → eligible → **admitted** | names | BINDING (drop it alone → admits) |
|---|---|---|---|
| hack3 | 810 → 5 → **5** | LOVE RZLT RFIL LAES AVAV | exp_return not positive → **413** |
| hack4 | 810 → 11 → **5** | NB LAES ALMU ABAT FPS | exp_return not positive → **20** |
| hack6 | 810 → 0 → **0** | **NONE** | exp_return not positive → **185** |

Difference, `returns` → `hygiene_only`:

```
  hack3  10 -> 5   added: AVAV, LAES, LOVE, RFIL, RZLT
                   dropped: ASPI, CRUS, DAKT, IMRX, INVA, IVA, LENZ, NPKI, TNXP, VST
  hack4   5 -> 5   added: -   dropped: -
  hack6  15 -> 0   added: -   dropped: all 15
```

## A.3 THE FINDING: hygiene-only as written would EMPTY hack6

Retiring the four band-return constants does not just stop excluding names — it
removes the number the **coherence floor** reads.

`murat_rule.score` computes `exp_return = (2·p_up − 1) × claimed_abs_move`. The
panel's unconditional base rate is **p_up = 0.4615**, so every name the rule does
not fire on gets a **negative** `exp_return`; only the rule-firing cell
(**p_up = 0.5082**) is positive. Until now the band prior *overwrote* that number
with its own eleven-year constant, which was positive for all three bands below
5.0. Take the constants away and the fallback is the panel, and:

> **799 of 810 candidates fail `exp_return not positive`.**

The coherence floor — a long-only book may not hold a name its own calibration
says loses — then becomes the *sole* gate. hack6 goes to zero. hack3 keeps five
names it never held before and loses ten it did.

**This is not an argument against decision B.1 §4a.** The decision is right: the
constants came off a corrupted tape and the ratio should be a guide. It is that
4a needs a companion decision, and it is Murat's:

- **(i)** what feeds `exp_return` once the band constants are gone — the panel
  base rate (which empties the books), the learner, or a flat prior; **or**
- **(ii)** whether the coherence floor still applies when `exp_return` is a
  transferred 152-name base rate rather than a measured band.

Until one of those is answered, **do not set `AAT_BAND_MODE=hygiene_only` on a
live service.** The flag exists, is off by default, is exercised by the suite in
both modes, and the live fleet is byte-identical without it. When Murat wants it:

```bash
railway variables --service aat-loop-<role> --set "AAT_BAND_MODE=hygiene_only"
```

What the flag changes, all three at once and in opposite directions:
1. `UPSIDE_IMPLAUSIBLE_AT` (ratio ≥ 4.0) stops **barring** candidacy and becomes a
   reported indicator — this ADMITS names;
2. the hard price floor rises **$1 → $2** — this EXCLUDES names, and it is the
   condition every EXP-RETURN-XS-1 cell was measured under;
3. a target window whose high/low exceeds **5×** is UNREADABLE and is barred —
   the split / share-basis case that produced the toxic band in the first place,
   now named as a data defect instead of priced as a forecast.

On the 09-02 vintage, hygiene excluded **33 of 810** candidates and was
`fails_only = 0` in every book: nothing was admitted or refused *because of*
hygiene alone. Hygiene is not what changes the books — the missing `exp_return`
constant is.

## A.4 The contract every holding carries

Identical across hack3 / hack4 / hack6 (they share `contract.TRACKER_BOOKS`):

```
expected_horizon_sessions   21
min_normal_hold_sessions    10          <-- the minimum hold, as approved
thesis_expiry               2026-10-01  (21 weekday sessions from the vintage)
hard_falsifiers             3
  - the sealed ranking value for this name is no longer in the book's admitted set
  - the analyst target that ranked it is withdrawn or cut below the entry price
  - a delisting, halt or split makes the sealed price basis unreadable
risk_budget_usd             hack3 $664  hack4 $600  hack6 $180
                            (= per-name notional x $100,000 x the profile stop)
emergency_exit_reasons      DEADLINE, EXECUTION_CORRECTION, HARD_RISK_LIMIT,
                            DATA_ERROR, THESIS_INVALIDATED,
                            EXPLICIT_EVENT_STRATEGY_EXIT
profit_target_frac          None        (no +2.5% target on a 21-session thesis)
min_edge_over_stop          None        (MEASURED AND RECORDED, NOT ENFORCED)
```

Before the 10th session a close needs one of the six typed emergency reasons.
"The price moved 3%" is not one of them any more.

## A.5 Armed / disarmed, as of 2026-09-05

```
  hack1  DISARMED  Mandate.manage_only=True (declared in alpha/fleet.py)
  hack2  ARMED     nothing -- this book may enter
  hack3  ARMED     nothing -- this book may enter
  hack4  ARMED     nothing -- this book may enter
  hack5  ARMED     nothing -- this book may enter
  hack6  ARMED     nothing -- this book may enter
```

Two of the four possible disarms are **Railway variables** and are invisible to
a local process. It reports that rather than guessing:
`railway variables --service aat-loop-<role>`.

### hack2 is armed and is NOT a tracker book — print this before Monday

`contract.defaults_for` branches on `TRACKER_BOOKS = (hack3, hack4, hack6)`, so
**hack2 falls through to the EVENT defaults**: `expected_horizon_sessions 3`,
`min_normal_hold_sessions 0`, `profit_target_frac 0.025`. Its fleet profile is
`aggressive`, i.e. a **3% stop**. So the one armed book with **no minimum hold
and a +2.5% profit target** is precisely the churn the whole minimum-hold build
exists to stop, and it is the book that opened five 1:8 shorts on 2026-09-04.

Not fixed here. Which defaults hack2 gets is your call, not a session's.

## A.6 What this dry run could NOT do, and why

- **It could not seal a book dated today.** The newest tracker vintage is
  2026-09-02 and `MAX_TRACKER_AGE_SESSIONS = 2`, so a seal today is correctly
  refused. Running `--refresh` to manufacture one was declined deliberately: a
  half-finished refresh leaves a *fresh-looking* partial vintage that Monday's
  seal would then price a book on, which is a worse failure than an absent one.
- **It therefore reports the vintage it actually has**, and the 10:01 pass result
  above is the true current state, not a simulated success.

---

# APPENDIX B — THE TWO DECISIONS AS PROPOSALS (added 2026-09-05, CONTINUATION b item 7)

Read-only. **Nothing was sealed, ordered, deployed, or changed on Railway.** The
full three-mode printout this appendix summarises is
`aegis-finance/backend/data/optimus/continuation_2026-09-06b/C7_monday_dry_run_printout.txt`
and its replay JSON is `C7_monday_dry_run_replay_2026-09-02.json`. Tracker
vintage 2026-09-02, the newest on disk; a seal today is still correctly refused
by `MAX_TRACKER_AGE_SESSIONS = 2`.

## B.1 Proposal (a): a third band mode, `indicator`

**The problem A.3 found.** Decision B.1 4a implemented literally — retire the
band's four return constants, keep hygiene — **empties hack6** (15 names to 0)
and replaces hack3's ten with a different five. That is not a coincidence and
it is not a bug in the coherence floor: the band's constants were the *source*
of `exp_return` for exactly those names, so retiring them sends every row back
to the panel base rate and **799 of 810 then fail the long-book coherence
floor**, against 35 of 806 today. The floor is doing its job. There is nothing
left for it to read.

**The proposal.** `AAT_BAND_MODE=indicator`, a third mode, **OFF by default**:

| | `returns` (live today) | `hygiene_only` (B.1 4a) | **`indicator` (proposed)** |
|---|---|---|---|
| ratio is an admission rule | **yes** (≥ 4.0 bars candidacy) | no | **no** |
| hygiene gates admission | no | yes | **yes** |
| hard price floor | $1 | $2 | **$2** |
| band constant populates `exp_return` | yes | **no** | **yes** |
| that constant is labelled | no | n/a | **`UNVALIDATED_INDICATOR`** |

**Measured on the 2026-09-02 vintage:**

```
BAND MODE DIFFERENCE (returns -> hygiene_only)
  hack3  10 -> 5    hack4  5 -> 5    hack6  15 -> 0
BAND MODE DIFFERENCE (returns -> indicator)
  hack3  10 -> 10   hack4  5 -> 5    hack6  15 -> 15
```

So the proposal **costs nothing in admissions and buys the label**: the admitted
sets are identical to today's, the ratio stops being an admission rule, hygiene
starts being one, and every `exp_return` that came off an eleven-year band
constant now says so — on the row, in the book, and **inside the seal's
`content_sha256`** (`band_mode` in the provenance block,
`exp_return_validation` on every holding).

**Two things this proposal does NOT claim.** It does not say the constants are
right — they came off a tape whose defects are documented and they sit below
their own t 2 bar, which is precisely why the label reads UNVALIDATED. And the
identical admitted set is a fact about *this vintage*: the hygiene gate does
fire (33 names fail it, visible in the printout's `fails` column for every
book), it simply removes names that were already failing something else.

**What is genuinely different, and is a real change:** under `indicator` the
candidate pool is 810 rather than 806, the price floor is $2 rather than $1, and
a ratio ≥ 4.0 no longer bars a name from candidacy. Those are the same three
movements `hygiene_only` makes, pulling in opposite directions, and they are
pinned by `tests_smoke_band_mode.py`.

**How to try it, when you want to (not tonight, not by a session):**

```bash
# research side, read-only, no seal:
python -m scripts.monday_dry_run --compare        # all three modes, side by side
python -m scripts.monday_dry_run --mode indicator

# live fleet — YOUR call, and it is a Railway variable per role:
railway variables --service aat-loop-<role> --set "AAT_BAND_MODE=indicator"
```

An unrecognised value resolves to `returns`. A typo in a Railway variable must
not half-apply a mode to a live book, and that is pinned by a test.

## B.2 Proposal (b): hack2 is manage-only until its defaults are decided

**Restating A.5's finding, because it is the sharpest edge going into Monday.**
`contract.defaults_for` branches on `TRACKER_BOOKS = (hack3, hack4, hack6)`, so
**hack2 falls through to the EVENT defaults**: `expected_horizon_sessions 3`,
`min_normal_hold_sessions 0`, `profit_target_frac 0.025`. Its fleet profile is
`aggressive`, i.e. a **3% stop**. The one armed book with **no minimum hold and
a +2.5% profit target** is the exact churn pattern the whole minimum-hold build
was written to stop — and it is the book that opened five 1:8 shorts on
2026-09-04.

**Proposed for Monday: mark hack2 MANAGE-ONLY before §2's deploy re-arms
entries**, and leave it there until you have decided which contract defaults it
should get. This is a runbook instruction, not a code change: nothing in this
session set `manage_only` on hack2, because which defaults hack2 gets is your
call.

Add this to §3, before running §2:

```bash
railway variables --service aat-loop-hack2 --set "AAT_MANAGE_ONLY=1"
railway variables --service aat-loop-hack2            # confirm it took
```

Then §5's ENTRY AUTHORITY block should read `hack2  DISARMED` rather than
`hack2  ARMED  nothing -- this book may enter`. If it still says ARMED after the
deploy, the variable did not take, and **two of the four possible disarms are
Railway variables that a local process cannot see** — so verify at the service,
not from the laptop.

**The alternative, if you would rather it trade:** give hack2 tracker defaults
(21/10, no profit target). That is a one-line change to `TRACKER_BOOKS` or an
explicit branch in `contract.defaults_for`, and it should be made deliberately
rather than by a book falling through a tuple membership test.

## B.3 What Appendix B changed in code, and what it did not

Changed (all behind the flag; the live default is byte-identical, and the
terminal suite is **76 suites / 3,503 checks / ALL PASS**, up from 3,483):

- `alpha/murat_rule.py` — `BAND_MODE_INDICATOR`, `BAND_MODES`, the `indicator`
  branch of `band_overlay` (which *reuses* the returns path verbatim rather than
  re-expressing its four silences), and `exp_return_validation` on every scored
  row in **every** mode. The live default's constant was never validated either;
  until now nothing said so.
- `alpha/tracker.py` — `hygiene_gate_on()` beside the narrower `hygiene_only()`.
  The eligibility chain, the $2 floor and the ratio bar now ask the gate
  question, not the mode-name question. Gating on `hygiene_only()` alone would
  have silently dropped the hygiene exclusion the moment a third mode was
  switched on.
- `scripts/prediction_book.py` — `band_mode` in the seal's provenance block and
  `exp_return_validation` on every sealed holding, both **inside**
  `content_sha256`.
- `scripts/monday_dry_run.py` — `--mode indicator`, `--compare` over all three,
  and the hygiene count printed for every mode that runs the gate.

Not changed: no Railway variable, no `manage_only` flag, no seal, no order, no
deploy. `AAT_BAND_MODE` is unset locally and the live fleet is untouched.
