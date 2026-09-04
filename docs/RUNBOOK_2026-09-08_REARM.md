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
