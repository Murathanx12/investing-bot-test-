# The ledger chain break of 25 Aug — CONCURRENT_WRITE, confirmed, and there were six of them

**2026-08-26, day session 13.** `state/decisions.jsonl`, 5,896 lines, 11.4 MB.
Investigated read-only. **Nothing in the ledger was modified.**

## Verdict

**`CONCURRENT_WRITE`. Confirmed from evidence, not inferred from a comment.**
Two agent loops (`dev` and `exp1`) appended to one hash chain with no lock, in a
**36-second window on 2026-08-25 between 15:39:55.943 and 15:40:31.519 UTC**.

The cause is already fixed: `alpha.ledger._Lock` (O_EXCL cross-process lock,
30-second stale rule) was added after the incident, and **no break has occurred
since** — 4,516 subsequent rows are self-consistent.

## The evidence

### It is six breaks, not one

Every warning printed for two days named line 1203, because `verify_chain`
**returned at the first break**. Walking to the end finds:

| line | kind | what |
|---|---|---|
| 1203 | stale `_prev` | `20260825T1539:narrative_dispersion:QQQ:alt0` |
| 1370 | **not JSON** | write physically spliced |
| 1372 | stale `_prev` | `20260825T1540:vol_gap:AMD:alt1` |
| 1374 | **not JSON** | write physically spliced |
| 1376 | stale `_prev` | `20260825T1540:vol_gap:AMD:alt3` |
| 1380 | stale `_prev` | `20260825T1540:options_attention:AVGO` |

> **A tamper-evident check that stops at the first sign of tampering
> under-states the damage by design.** Two days of red lines reported one
> damaged row. There were six, and two of them are decisions partly **lost**,
> not merely unverifiable.

### The interleave, at millisecond resolution

| line | role | written (UTC) | decision |
|---|---|---|---|
| 1201 | dev | 15:39:56.252 | `vol_gap:QQQ` |
| 1202 | **dev** | 15:39:59.**208** | `vol_gap:IWM:alt0` |
| 1203 | **exp1** | 15:39:59.**209** | `narrative_dispersion:QQQ:alt0` |

Line 1203's recorded `_prev` is **the hash of line 1201**. So `exp1` read the
head while 1201 was the tail, `dev` appended 1202, and `exp1` appended one
millisecond later carrying a `_prev` that was already stale. Classic
read-modify-write race between two processes.

### Two rows were physically spliced

Lines 1370 and 1374 begin **mid-JSON**:

```
line 1370: isk_fraction":0.0,"signal_shape":"tail","symbol":"AVGO",...
line 1374: e","spot_ts":"2026-08-25T15:40:30.576257+00:00","underlying":"AVGO"},...
```

`isk_fraction` is the tail of `"risk_fraction"`. A single `write()` was split by
the other process's write landing inside it. That proves the appends were not
atomic — which is the same fact as the lock's absence, seen from the filesystem.

### Blast radius

- first break at line 1203; **4,693 lines downstream — 79.6% of the file — can never verify back to genesis**
- rows by account: `dev` 2,130 · `exp1` 2,608 · unstamped (pre-stamp) 1,151

## What was done, and what was deliberately not

**Not repaired.** Rewriting `_prev` on line 1203 would make the file verify and
would destroy the only evidence that anything happened. Repairing a
tamper-evident chain is indistinguishable from the tampering it exists to
detect.

**Declared as an epoch instead** (`alpha/epoch.py`,
`state/ledger_epochs.json`):

```
epoch 1: lines 1..1202     verifies to genesis
BOUNDARY: 6 breaks, CONCURRENT_WRITE, cause known and fixed
epoch 2: lines 1381..EOF   self-consistent
```

`verify_chain` now accepts **exactly** the six enumerated breaks and fails on any
other. The accepted list is covered by a manifest hash, so an epoch cannot be
quietly widened later to swallow a new break — an anchor whose hash does not
match its contents is **refused**, not honoured.

The check now reads:

```
chain intact within epochs, head=05c23c4d (6 declared historical break(s), see state/ledger_epochs.json)
```

## Why the epoch, rather than living with the red line

`verify_chain` had been printing the same failure on **every pass of every loop,
53+ times over two days**, and nobody investigated it — including me, twice.

That is not inattention, it is the documented failure mode from CLAUDE.md:
**a gate that cannot go green is a broken gate.** No action available to anyone
could clear that line, so it stopped carrying information and started training
its readers to skim red lines. An epoch restores the property that the check is
*actionable*: green means "no new damage", and red means something happened
today.

The damage is not laundered. It is dated, enumerated, attributed, and left in
the file.

## The diagnostic that generalises

**The shape of a break says what caused it.**

- A **post-hoc edit** breaks the edited row *and its successor* — the next row's
  `_prev` was the hash of the original bytes. Consecutive breaks.
- A **concurrent-write incident re-syncs**: each writer recomputes `_prev` from
  the bytes actually on disk, so the chain repairs itself on the next append.
  Isolated breaks with clean runs between them.

The 25 Aug damage is the second pattern — 1203, then clean to 1370, then 1372,
1376, 1380, then 4,516 clean rows. **That pattern is inconsistent with anyone
having edited the file** and consistent only with racing appenders. Pinned in
`tests_smoke_epoch.py`.

## What is still owed

1. **`REPEATED_INVARIANT_ESCALATION`** — an integrity warning may not print 53
   times unread. First occurrence warns, repeats escalate, N consecutive fails
   the health check. Not built yet; the epoch removes the immediate noise but
   not the class of failure.
2. The two spliced rows are **lost decisions**. They are not recoverable and are
   not counted in any grading run. `MALFORMED` already surfaces them.
