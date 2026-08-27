# RUNBOOK — competition kickoff, 28 Aug 2026, 11:00 ET

Kickoff **2026-08-28 15:00 UTC = 11:00 ET**. Deadline **2026-09-04 15:00 UTC =
11:00 ET**, ninety minutes after the bell and not at a close.

Run these in order. Every step either passes or **refuses and says which rule** —
none of them is advisory, and none is a judgement call made on the morning.

---

## −1. TONIGHT (27 Aug, after 16:00 ET) — the only time-gated item

This cannot be moved earlier and cannot be parallelised: it needs a session that
has not happened yet. Everything else in this document can be done at any time.

```
python -m scripts.contagion        --event 2026-08-27    # MDE ~1.4%; read the SPY/QQQ rows
python -m scripts.anchor_to_torque --event 2026-08-27    # shadow; expect nothing to clear its MDE
python -m scripts.event_grade      --event 2026-08-27
```

Grade the condors against `FINDING_2026-08-26_WHAT_THE_CONDORS_ARE_BETTING.md`,
which was written **before** the outcome: profit zone ≈ −4.9% to +5.8/+7.0%,
mean +$2,349, worst −$17,739.

**Record a null as a null and a low-power outcome as UNRESOLVED.** The sealed
NVDA vector's `event_date` is 2026-08-27, so this is the graded session — the
26 Aug after-hours tape was unmeasurable from our feed and is on record as such,
not as flat.

---

## 0. RE-PULL THE RULES. They are a fact about a web page on one day.

`docs/RULES_SNAPSHOT_2026-08-25.md` says so in its own text.

```
# save the live page, then:
git add docs/RULES_SNAPSHOT_2026-08-28.md
```

Diff it against the 25 Aug snapshot and **stop** if any of these four moved:

| requirement | 25 Aug value |
|---|---|
| judged account | brand new, **$100,000** |
| technology | Trading API **+ MCP server or CLI** |
| strategy | **must incorporate options** |
| criterion #1 | **P&L**, styled `--primary` on the page |

`alpha/config.COMPETITION` holds `kickoff_utc`, `deadline_utc` and
`required_starting_equity` so a script asserts against them rather than a
paragraph. If the page moved, change that dict **before** freezing genesis — the
snapshot's hash goes into the genesis record.

---

## 1. CREATE THE JUDGED ACCOUNT (manual, Alpaca dashboard)

A new paper account, options enabled, **$100,000**.

Then put its keys in `.env` as:

```
AAT_COMPETITION_KEY_ID=...
AAT_COMPETITION_SECRET_KEY=...
```

**Do not reuse an existing account.** These four are denylisted in
`alpha/genesis.DENIED_ACCOUNTS` and `preflight`/`run_pass` will refuse them:

| account | role | why it can never be judged |
|---|---|---|
| `PA32Q5IW7TAS` | dev | the book the UI labels "hackathon". −15% on 27 Aug, 27 orders, 8 positions, opened under the pre-units-fix arithmetic |
| `PA3AOJPJTSBW` | exp1 | −4%, latched, 16 orders |
| `PA3I7VTCC0BM` | market | the passive-beta benchmark |
| `PA3LY4QK3A6A` | pead | clean $100k, but a *declared arm* — reusing it collapses the independence measurement |

The denylist keys on the **account number the venue returns**, not on the role
name, because every other guard in this repo is role-keyed and a role pointed at
the wrong account passes all of them.

---

## 2. VERIFY THE MAPPING FROM THE VENUE, NOT FROM LABELS

```
python -m scripts.accounts
```

`competition` must appear, be a new `PA…` number, read **exactly $100,000.00**,
**0 positions**, **0 orders**, and print `clean`.

If it prints `HAS TRADED`, the account is already legacy. Make another one.

---

## 3. FREEZE GENESIS — before the first order, and only once

```
AAT_ACCOUNT_ROLE=competition python -m scripts.genesis --freeze \
    --rules docs/RULES_SNAPSHOT_2026-08-28.md
```

Writes `state/genesis_competition.json`: account number, timestamp, starting
equity, position and order counts at genesis, the rules snapshot's SHA-256, the
code commit, and a hash over all of it.

It refuses on a denylisted number, on anything but exactly $100,000, on any
position, and on **any order of any status** — `status=open` would call an
account holding one expired OPG order clean, which is the exact state `market`
is in.

Then commit the record. A birth certificate that only exists on one laptop is
not evidence.

---

## 4. PREFLIGHT — it now refuses instead of reporting

```
AAT_ACCOUNT_ROLE=competition python -m scripts.preflight --require-clean
```

Exit 0 is required. Under the `competition` role this returns 1 on a denylisted
account or a genesis that does not verify, before it prints anything about the
book.

---

## 5. PROVE THE TOOLING REQUIREMENT (criterion 2)

```
AAT_ACCOUNT_ROLE=competition python -m scripts.tooling_probe
```

All eight lines must PASS. This is the demo screen as well as the requirement:
the MCP server runs with the `trading` toolset **withheld**, so the LLM connected
to it has no order verb to call — canon expressed as a capability boundary rather
than a prompt.

- Trading API → `alpha/broker/alpaca.py`, the only writer.
- CLI → the audit path a judge can reproduce with two exports and one command.
- MCP → the read/explain surface.

**One authoritative writer. Neither of the other two may ever place an order.**

---

## 6. SEED THE BENCHMARK PROPERLY, or leave it unseeded and say so

The `market` account is $100,000.00 with 0 positions and 1 SPY order whose venue
status is literally `expired`: an OPG order is eligible only for the opening
auction. Nine days of "our arms versus the market" had no market in them.

```
AAT_ACCOUNT_ROLE=market python -m scripts.benchmark_state          # expect EXPIRED_UNFILLED
AAT_ACCOUNT_ROLE=market python -m scripts.seed_market --convention post_open        # dry
AAT_ACCOUNT_ROLE=market python -m scripts.seed_market --convention post_open --live # after 09:30 ET
AAT_ACCOUNT_ROLE=market python -m scripts.benchmark_state          # must read ACTIVE
```

`seed_market` now exits **2** unless a position exists. Until the state reads
`ACTIVE`, **no benchmark number may be quoted anywhere** — not in the handoff,
not in the scoreboard, not to a judge.

---

## 7. THE HUMAN THESIS WIRE — use it before the first pass

This is the channel that did not exist on 26 Aug, when the view existed, the
sealed research agreed, NVDA rose ~6.8% against a ~5.4% implied move, and the
books held index straddles and a peer straddle on AMD.

```
python -m scripts.thesis --symbol XXXX --direction up --expected-move 0.06 \
    --catalyst "..." --catalyst-at 2026-09-02T20:20Z --horizon 3 \
    --conviction 0.8 --reason "..." --falsifier "..."
python -m scripts.thesis --list
```

It refuses a direction with no expected move, a sign disagreement, a missing
falsifier, and a thesis stated at or after its own catalyst. `--magnitude
wider|narrower` adds a claim about the chain's price for the move; leave it
`unknown` if the view is purely directional.

**It is a forecast source, never an order path.** The thesis goes through the
identical gate as every brain: the claim matrix, the chain's own width, the
sizer, the refuted routes, admission, the book limits, the daily latch.

---

## 8. FIRST LIVE PASS

```
AAT_ACCOUNT_ROLE=competition python -m scripts.run_pass --role competition \
    --profile conservative                       # DRY. No --live.
```

Read the refusal decomposition before sending anything. `run_pass --live` under
the `competition` role verifies genesis first and exits 2 if it does not match.

Then, and only then, `--live`.

---

## WHAT IS DIFFERENT FROM THE 25 AUG BOOK

| | 25 Aug | now |
|---|---|---|
| chain width | `0.85 × straddle/spot`, calendar days, one-sided horizon rescale | identity, trading sessions, symmetric |
| book limits | computed, enforced by nothing | enforced; ceiling 40% → 35% |
| refuted routes | in documents | in code, **scoped to their own samples** |
| a direction claim | could be handed an iron condor | structurally inadmissible |
| a human view | a chat message | a typed, falsifiable, timestamped forecast |
| `vol_gap` | spending capital | quarantined pending recalibration |
| the benchmark | "SUBMITTED" read as seeded | a state machine that refuses to lie |
| the judged account | did not exist | a birth certificate, or nothing trades |

**`vol_gap` does not get capital in the judged account until its recalibration
clears.** Two brains inflate sigma by 16–17% (`options_attention`,
`narrative_dispersion`) and a 16% inflation alone flips a straddle's sign; that
is a one-day measurement and it needs more than one day.
