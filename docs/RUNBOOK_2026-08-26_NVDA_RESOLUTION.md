# Tonight's runbook — resolve NVDA, in this order, without exception

**Release expected ~16:20 ET 2026-08-26.** The sealed vector is
`state/event_state/NVDA_2026-08-27_vector.json`, sealed 11:50 UTC, `seal_valid=True`,
13 fields, `resolved_at: null`.

## The order is the experiment

`StateVector.reaction()` refuses until every field is resolved, and the refusal
was rehearsed today on a copy. But the tooling can only enforce the machine
half. **The human half is not fetching a quote before the fields are filled** —
a move you have already seen cannot be un-seen while reading the facts that
caused it, and the resulting story is always coherent, which is exactly what
makes it worthless.

So: **do not look at the after-hours price, and do not read market commentary,
until step 3 is complete.**

## Steps

**1. Get the release itself.** `investor.nvidia.com` press release + the CFO
commentary PDF. The release, not a wire summary of it — every field's
`resolution_rule` refers to what the company said.

**2. Fill the template from the release only.**
```
python -m scripts.nvda_resolve --status        # the 13 rules, in rank order
# edit state/event_state/NVDA_2026-08-27_answers.json
```
A field the release did not address is the string `"UNAVAILABLE"`. That is a
finding about the release and must never be indistinguishable from a field we
forgot.

The four that decide it, in the sealed order:
1. `q3_guide_surprise` — guidance midpoint minus **104.2** ($bn)
2. `gross_margin_surprise` — reported non-GAAP GM minus **75.0**; a Q3 GM guide
   below 74% is the bear trigger *regardless of the revenue line*
3. `HBM_cost_pressure` — `{absorbed, passed_through, partially_passed, not_addressed}`
4. `Rubin_timing_change` — `{ahead, on_schedule, slipped, not_addressed}`, and
   record the exact phrasing: "production" / "sampling" / "volume" are different claims

`revenue_surprise` is **rank 13 of 13**. The headline is the least important
field and was sealed that way before the print.

**3. Resolve.**
```
python -m scripts.nvda_resolve --answers state/event_state/NVDA_2026-08-27_answers.json
```
Must print `ALL FIELDS RESOLVED`. Until it does, step 4 is refused by code.

**4. Only now, read the price.**
```
python -m scripts.nvda_resolve --answers ... --read-move
```

**5. Tomorrow, after the 27 Aug session closes** — the contagion decomposition.
The baseline was fitted today at 15:55 UTC, *before* the print, and the event
path refuses a baseline stamped after the release.
```
python -m scripts.contagion --event 2026-08-27
```
Read the **SPY and QQQ rows** — their one-event MDE is ~1.4%, so "did the index
move beyond NVDA's ~7.8% mechanical share" is answerable on a single print.
Per-node MDE runs 3.9%–20.8%; those rows **accumulate**, they do not conclude.

**6. Grade the book.** The two iron condors carry $25,270 of max loss (25.9% of
equity) into this print, and `docs/FINDING_2026-08-26_WHAT_THE_CONDORS_ARE_BETTING.md`
records what they were betting *before* the outcome was known. Compare against
that, not against a fresh rationalisation.

## What not to do

- **Do not edit a prior or reorder the hierarchy.** `resolve()` refuses a broken
  seal, and that refusal is the only thing separating this from a post-hoc story.
- **Do not turn one event into a strategy.** Per-node MDE says a single print
  cannot resolve a per-node effect. Tonight is calibration.
- **Do not restart the loops to "fix" anything mid-event** without deciding that
  separately. They are running pre-heartbeat code; that is known, logged, and
  not urgent enough to change during the event they are trading.
