# Session 26 — the book can now claim. Read MU's numbers before Monday.

For Murat and Fable. Written plainly on purpose.
Commit `30180dd` on `main` in `aegis-alpha-terminal`. **Committed, not pushed.**
56 suites, 2,432 checks, all pass. `fleet --check-all` green on all six accounts.

---

## 0. Scoreboard

| | |
|---|---|
| **Result improvement on P&L** | **None yet.** The engine can now decide. It has not yet traded on it. |
| sealed book today | 151 names considered, **1 claim: MU** |
| what MU's claim is worth | `p_up 0.508`, expected return **+0.25%**, downside −25.4%, confidence 0.92 |
| catalyst calendar | filled: 8,973 earnings + 50 macro + 9 clinical rows; 98 touch a watched name |
| T12 | **closed, negative.** 70 cells, nothing survives BH-FDR |
| hack2 | not broken — it is in a gap between two earnings waves |
| tests | 2,418 → **2,432 checks, all pass** |
| LLM spend | $2.01 (the classifier finishing) |

---

## 1. Why the book said nothing, and what I changed

The book looked at 151 names on 30 Aug and claimed nothing. That was not the
names being bad. The switch that decides whether it may claim is computed from
whether any measured signal's confidence interval excludes zero — and on the
152-name panel, none does. So the old generator could look at any number of
names and still claim zero. Forever.

There were two ways to fix that. One was to loosen the test until something
passed. That turns a measurement into a wish, so I did not do it.

The other was to **add a second generator** with its own rules, its own
evidence and its own grade, sitting beside the first. That is what shipped:
`murat_rule_v1`, your rule, frozen in code before the first seal.

    (a) consensus target / price  >= 1.50
    (b) consensus rating          >= 4.1     -- only when a rating can be read today
    (d) a dated catalyst inside 21 sessions
    (e) drawdown from the 60-day high <= -15%

Clause (c), "sector fit", is deliberately not in there. It is a judgement, not
a reading, and a clause nobody can evaluate the same way twice does not belong
in a frozen contract.

**Today it claims exactly one name: MU.** Target/price 1.61, catalyst in 24
days, down 23.1% from its 60-day high, and its rating was readable so all four
clauses were tested.

## 2. The number you should look at before Monday

MU's expected return is **+0.25% over 21 sessions, against a downside of
−25.4%.**

That is not a typo and it is not pessimism. It falls out of the base rate. I
measured how often the rule's testable clauses have been followed by a positive
21-session return, on the 152-name panel:

| | hit rate | sample | date blocks | mean relative return |
|---|---|---|---|---|
| the rule's (a AND e) subset | **50.8%** | 3,894 | 11 | **+4.39%** |
| every name, unconditionally | 46.2% | 34,180 | 11 | +0.91% |

The rule's subset does beat the panel — by 4.7 points of hit rate and 3.5
points of mean return. But 50.8% is very close to a coin, and a near-coin hit
rate sitting beside a large mean means **a few big winners, not a reliable
tendency**. That is the same shape as the attention-shock result I killed
yesterday, and it is why the expected return the book is willing to publish is
small even though the rule fired.

Two honest caveats, both written into the file:
- it is **in-sample** — measured on the same panel the book ranks over. It is a
  base rate for calibration, not proof the rule works. The forward grade is.
- it stands on clauses **(a) and (e) only**. (b) has no rating history and (d)
  had no calendar until today, so the live rule is *stricter* than the
  condition the base rate was measured under.

**Every name now publishes numbers**, as you asked — no more "I don't know".
The 150 names that did not claim each show their probability, expected return,
downside, confidence, and the clause that blocked them. Uncertainty comes out
as "p ≈ 0.46, low confidence", never as a refusal.

## 3. The catalyst clause had never been evaluated. Not once.

Fable said the calendar was empty. It was not — the corpus already held **8,547
forward-dated rows**, 8,539 of them stored on 29 Aug. What was empty was the
*receipt file*, because a later partial re-run overwrote it and the receipt is
named by day.

The real problem was underneath, and it is worth understanding because it made
the clause you lean on hardest do nothing at all, silently:

- Price data is cut at the **last closed session** — 28 Aug — because our free
  data plan refuses recent bars.
- The catalyst calendar is pulled **today** — 29/30 Aug.
- One shared "what did we know by then" filter was applied to both. Every
  calendar row was newer than the cutoff, so every one was thrown away.

MU's 21 September earnings date was sitting in the corpus and was invisible.
`days_to_next_catalyst` was blank for all 151 names.

The fix is two clocks instead of one. Backward news still cannot be seen after
the decision — that is the whole of the discipline. But a *forward* date asks a
different question: not "had it happened yet?" but "did we know the date?", and
at a 09:15 seal we plainly do. The old behaviour stays the default, so no
backtest changes.

## 4. hack2: nothing is broken, and it gets busy on Monday

Fable asked me to find the biggest book-state refusal and fix it if it was a
mis-set input. **There are no book-state refusals at all.** All 40 refusals in
the ledger are about the candidate's merit (34) or the ranker preferring a
different structure (4). The biggest single cause is the direction/dispersion
guard — the one that stops a directional forecast being handed a sign-blind
iron condor. That guard is working as designed.

The counterfactual agrees: **53 saved losses against 8 false refusals.**

The actual reason for 2 orders is the calendar. hack2 trades drift 1–3 sessions
after an earnings print. Of 98 usable prints in its window:

    reaction on or before Fri 28 Aug   51    <- already gone
    Mon 31 Aug                          2
    Tue 1 Sep                           3
    Wed 2 Sep                          10
    Thu 3 Sep                          21
    Fri 4 Sep                          11    <- deadline day, can't complete a drift

It has been sitting in the gap between two earnings waves. **42 of its 47
remaining chances land on 2–4 September.** Per the brief, the class is an
evidence class, so I left it alone and am saying so.

## 5. T12 is closed and the answer is no

The classifier finished: 63,798 of 64,525 labelled, 98.9%, $2.01.

**Only 7.7% of the corpus is a new dated fact about the company it is tagged
with.** (51.6% of rows only *mention* the company; 20.2% do not discuss it at
all.) That is worse than the 18.4% I estimated from a 250-row sample.

Filtering down to just those real events and re-running the whole screen:
**70 scorable cells, nothing survives BH-FDR at q=0.10.** The cleaned counts do
no better than the dirty ones — in fact the raw control was slightly stronger.

So this is a second negative on the *encoding*, and it is a real answer: the
counts were not weak because they were dirty. Counting is the wrong shape. The
next thing to try is **surprise** — the day-0 abnormal move and volume — and
when I do, it has to be tested against plain trailing momentum, not against
zero, or it will just rediscover momentum.

## 6. What I did NOT do, and why

**Market-on-close entry for hack3.** The brief asked for it. `alpha/timing.py`
already has the machinery, and the sealed book is the perfect candidate (it
freezes at 09:15, the venue cutoff is 15:50). But it is not wired into the
order builder, that builder is shared by all six accounts, and switching to MOC
means giving up the limit price that currently protects every fill. Doing that
untested the night before a session is how Monday becomes an incident.

The dangerous half of that instruction is already enforced: **no share entry
between 09:30 and 09:45**, for every account.

## 7. What happens Monday, and the one decision that is yours

Nothing I built trades unless you push. Here is the exact chain:

```
python -m scripts.prediction_book --seal      # before 09:15 ET
python -m scripts.prediction_book --verify
python -m scripts.prediction_book --publish   # -> docs/seed/predictions/<day>.json
git add docs/seed/predictions && git commit && git push
```

`--publish` exists because the Railway loops mount a volume over `/app/state`,
which **hides** anything the repo has at that path. A book sealed on the laptop
and committed under `state/` would be invisible to the running loop, and hack3
would decline every name for a reason that looks like the rule having nothing
to say. `docs/seed/` is not hidden — it is already how the theme list gets in.

**The worst case, computed from the code rather than typed by hand:**

```
gross cap (basket) 1.00x  x  stop 8%  =  -8.00% of equity  =  -$7,289 on hack3's $91,107
```

Inside the −9% bound. The bound is gross × stop; there is no name-count term in
it, so adding a selector cannot raise it. No cap, stop, notional limit or
opening-range rule was touched.

**If the book claims nothing on Monday, hack3 holds cash and says so.** That is
the intended behaviour, not a failure.

---

## What I would do next

1. **Encode surprise, not count** (the T12 result points straight at it), with
   plain momentum as the control.
2. **The fantasy transposition harness** — your design. The anonymiser is the
   first piece and the classifier already proved the pipeline and the price
   (~$2 for 80k rows).
3. Leave hack2 alone until 2 September, then watch it.
