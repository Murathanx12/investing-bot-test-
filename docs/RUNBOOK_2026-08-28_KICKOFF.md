# RUNBOOK — competition kickoff, 28 Aug 2026, 11:00 ET

Kickoff **2026-08-28 15:00 UTC = 11:00 ET**. Deadline **2026-09-04 15:00 UTC =
11:00 ET**, ninety minutes after the bell and not at a close.

Run these in order. Every step either passes or **refuses and says which rule** —
none of them is advisory, and none is a judgement call made on the morning.

---

## ⚠️ −2. REGISTER. BEFORE 11:00 ET. NOTHING ELSE MATTERS IF THIS IS MISSED.

Pulled from the live dashboard on 27 Aug (`docs/RULES_SNAPSHOT_2026-08-27_REPULL.md`):

> **Fri, Aug 28 · 15:00 UTC · Kickoff · Registration closes · All participants**
> *"Registration closes the moment the event starts."*

**There is no entry after kickoff.** This was not in the 25 Aug snapshot. It is a
hard, irreversible gate that no amount of engineering recovers from, and every
other step in this document is worthless if it is missed.

Sign-up: `https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon?enroll=true`

Also new from that pull: prize pool **$6,000**; the track is called
**"Options Alpha Agents"** — the options requirement is in the name of the track,
not just a rules line; **727 teams** forming, against 555 at the last count.

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

A re-pull was already done on 27 Aug — `docs/RULES_SNAPSHOT_2026-08-27_REPULL.md`.
Kickoff, deadline and the Trading-API/MCP/CLI line are all **confirmed unchanged**.
But the judging-criteria card and the fresh-$100k line **did not render** to our
fetcher, so they are UNCONFIRMED rather than absent, and the 25 Aug capture stays
the authority on them. Diff the morning pull against the 27 Aug one.

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

A new paper account, **options enabled**, **$100,000**.

**Options permission is checked, not assumed.** A fresh Alpaca paper account is
not guaranteed to have it, and an account that cannot buy a call fails the
"Options Alpha Agents" track on day one — *silently*, as a stream of broker
rejections that read like ordinary refusals. `genesis --freeze` refuses below
level 2 and warns below level 3 (spreads and condors need 3). It also refuses
`trading_blocked`. The level is frozen into the record, so a later dispute about
whether options were tradeable has an answer from before the first order.

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

## 8. POINT IT AT NAMES THAT HAVE AN EVENT — this is not optional

**The default universe produces ZERO forecasts.** `scripts/run_pass.UNIVERSE` is
fifteen hardcoded mega-caps and they all report in the last week of *July*, so
by late August every one is 19–25 sessions past its print against a drift window
of +1..+3. A dry pass on 27 Aug returned `NotApplicable` on every single line.

A book that refuses everything scores zero, and **P&L is criterion #1.**

```
python -m scripts.window_universe --json     # re-run each morning
```

95 names have an event whose drift window reaches inside the contest:

| reacts | names | note |
|---|---|---|
| **Fri 28 Aug** | MRVL WDAY ADSK AFRM ESTC RBRK S | **day one**, plus NVDA/CRM/CRWD/VEEV/OKTA/SNPS at +1 |
| Mon 31 Aug | SAIC FRO | thin |
| Tue 1 Sep | NIO MDT ASO AEO | |
| Wed 2 Sep | DLTR M PANW MDB CRDO GTLB | |
| **Thu 3 Sep** | **AVGO** HPE LULU NTAP SNOW CIEN | truncated: 2 sessions left |
| Fri 4 Sep | **DELL** ZS DOCU GWRE PATH IOT | truncated: 1 session, deadline morning |

`AVGO` on 2 Sep amc is the marquee event and it is `TRUNCATED_BY_DEADLINE` — the
+3 session never arrives. That is priced in at selection, not discovered on the
last morning.

### AND THE HARD LIMIT: THE WHOLE CONTEST IS THREE EVENTS

`post_event_drift` is two-sided on ELEVEN names only (`MEGA_MEASURED`). Outside
them an UP print has no edge and a DOWN print needs a pair structure the engine
does not have. Intersect that with the window and you get:

| name | reacts | usable |
|---|---|---|
| **NVDA** | Thu 27 Aug | **day one only** — 28 Aug, then spent |
| **PANW** | Wed 2 Sep | full window |
| **AVGO** | Thu 3 Sep | truncated, 2 sessions |

Each still needs its day-0 move to clear the flat-tercile floor, so **three is a
ceiling, not a forecast.**

**So this brain alone contributes near-zero P&L in either direction, and the
human thesis arm (step 7) is the PRIMARY decision source, not a supplement.**
Plus NFP at 08:30 ET on 4 Sep, for which `EVENT_RESERVE` already holds 10% of
the cap. Full reasoning: `docs/FINDING_2026-08-27_THREE_EVENTS.md`.

Hundreds of `NotApplicable` lines in the log mean *the universe is barren for
this brain*, not *the engine is broken*. Every refusal names its measurement.

## 9. FIRST LIVE PASS

```
AAT_ACCOUNT_ROLE=competition python -m scripts.run_pass --role competition \
    --profile conservative --expiry 2026-09-04 \
    --brains post_event_drift --shadow "" --window-universe       # DRY
```

Read the refusal decomposition before sending anything. Under the `competition`
role, `--live` verifies genesis first and exits 2 if it does not match, and
`--expiry` is refused if it outlives the deadline.

Then, and only then, `--live`.

### What it will actually pick

Measured 27 Aug against **live chains**, with the brain's own +0.72% directional
forecast:

| name | chosen | EV/max-loss | P(profit) | median |
|---|---|---|---|---|
| NVDA | `long_call` | +38% | 33% | −$137 |
| CRM | `bull_call_spread` | +16% | 29% | −$104 |
| DG | `long_shares` | +11% | 56% | +$1 |
| SNPS | `long_shares` | +9% | 54% | +$3 |

Straddles and condors were **refused before pricing** by the claim matrix.
Options win where the edge pays for the spread; shares win where it doesn't — so
the options requirement is satisfied without forcing an instrument.

### ONE DECISION IS YOURS, AND IT IS NOT MADE

The champion is ranked on **expected value**, which picks the NVDA `long_call`
at 33% hit rate over `long_shares` at 56%. Over a long series the mean is right;
over **five sessions** terminal wealth follows the median path.

Full argument both ways: `docs/FINDING_2026-08-27_THE_RANKER_OPTIMISES_THE_MEAN.md`.

1. **Leave it** — option-heavy, choppy curve, real upside. No code change.
2. **Rank on median** — one line in `runner._ev_ratio`. Shares-and-spreads book,
   smoother curve, lower ceiling.
3. **Cap the risk budget in sub-50% structures** — most code, least tested.

The runner now logs `MEAN-RANKED` whenever it takes a champion with P(profit)
below 50%, naming the majority-win alternative it passed over. So you can watch
the trade-off live and change it mid-contest if the curve looks wrong.

## 9b. THE NFP TRADE — Thu 3 Sep after 15:45 ET. Put it in the calendar.

The jobs report at **08:30 ET on Fri 4 Sep** is the one scheduled macro event
inside the window, it lands 2.5 hours before judging, and `EVENT_RESERVE`
already holds **10% of the aggregate cap** for `2026-09-04` so ordinary passes
cannot spend it first.

It is the best-evidenced opportunity in the contest: **28 releases, SPY 0DTE ATM
straddle, prior close → 10:45 ET, mean +16.8%, median +6.8%, hit 57%, 9 of the
last 12 positive.** A TAIL payoff, bounded by construction. The direction channel
is dead (corr 0.03) — this is a WIDTH trade with centre zero.

```
AAT_ACCOUNT_ROLE=competition python -m scripts.nfp_trade          # dry, any time
AAT_ACCOUNT_ROLE=competition python -m scripts.nfp_trade --live   # Thu 3 Sep, after 15:45 ET
```

Two gates it evaluates itself, at the close on 3 Sep:

1. the 0DTE straddle costs no more than 0.77% × 1.10 — **we do not pay up for a tail**;
2. the Kalshi payrolls ladder puts ≥25% of its mass in the two outer buckets —
   **the crowd itself expects a tail**.

Dry-run on 27 Aug: gate 1 **false** (implied 1.28% vs 0.847% max — correct, there
is no NFP today), gate 2 **true** (tail mass 29%), `in_entry_window: false`. The
contract works and refuses honestly.

**Note the interaction, which nearly went wrong.** The index-straddle refusal
added on 27 Aug would have blocked this trade — it refused every SPY straddle
while its scope string claimed to cover only weekly-held-to-expiry ones.
`INDEX_STRADDLE_MIN_DTE = 2.0` fixes it: a 0DTE structure is admissible, a
3-day one (the 25 Aug losers) is not.

## 10. WHAT DOES **NOT** GET CAPITAL

- **`vol_gap`** — quarantined. It opened 5 of the 6 losing structures and cost
  **−$14,335 realised**. Reopens only when re-scored on corrected arithmetic.
- **Long straddles on SPY / QQQ / IWM** — refused. 381 weekly ATM straddles,
  buyer −19.8%/wk pooled, and this book's own SPY+QQQ straddles cost **−$14,711**.
- **Long straddles into NVDA's own print, or a peer's** — refused, 0-for-8 and
  290 relay legs.
- **`narrative_dispersion` / `options_attention`** — shadow. Measured 1.16–1.17×
  sigma inflation, and a 16% inflation alone flips a straddle's sign.

Still fully admissible: calls, puts, debit and credit verticals, condors on
anything with a directional or width claim behind it, and shares.

**And the sentinels now enforce most of that automatically.**

```
python -m scripts.sentinels                    # whole ledger
python -m scripts.sentinels --since 2026-08-27 # after the arithmetic fix
```

A brain one-sided against the chain on >90% of at least 50 decisions loses
**new-position authority** — it still forecasts, enumerates and gets graded, but
it cannot open. On the whole ledger that is **four of five**: relay 99.0%,
narrative_dispersion 96.1%, options_attention 95.4%, vol_gap 93.1%. Only
`event_move`, which has never executed, reads balanced at 28.6%.

**Since the 27 Aug fix it reports `CANNOT_DETERMINE` on 32–35 decisions against a
floor of 50 — so the arithmetic fix is not yet verified.** Expect the judged
account's early passes to be `post_event_drift` and the human arm only, and
expect `SENTINEL:` lines in the log naming each withdrawal.

---

## 11. THE ONE-LINE MORNING ROUTINE, once the account exists

```
python -m scripts.window_universe --json
AAT_ACCOUNT_ROLE=competition python -m scripts.preflight
AAT_ACCOUNT_ROLE=competition python -m scripts.run_pass --role competition     --expiry 2026-09-04 --brains post_event_drift --shadow ""     --window-universe --profile conservative --live
AAT_ACCOUNT_ROLE=competition python -m scripts.pnl_forensics --role competition
```

Then start the loop for the day:

```
AAT_ACCOUNT_ROLE=competition python -m scripts.agent_loop --expiry 2026-09-04     --window-universe --brains post_event_drift --shadow ""     --profile conservative --live
```

**`--window-universe` is not optional.** Without it the loop uses the fifteen
hardcoded mega-caps and produces zero forecasts, which is the exact bug the flag
exists to fix — and it would look like a quiet market. The loop regenerates
`state/window_universe.json` every six hours, because a name that reacts tomorrow
is not in today's receipt.

`scripts/manage` runs inside it and liquidates at **10:45 ET on 4 Sep** — that
verdict outranks a winning thesis.

**Watch for `MEAN-RANKED` and for `DEGRADED` in the logs.** The first says the
ranker took a sub-50%-hit-rate champion over a majority-win alternative; the
second says a sub-step has been exiting non-zero and the loop is cycling while
doing nothing.

## WHICH OF THESE STEPS HAVE ACTUALLY BEEN RUN

A runbook that has not been executed is a hypothesis. Every step below was
exercised on 27 Aug against the **live venue** unless marked otherwise.

| step | status on 27 Aug |
|---|---|
| −2 register | **NOT verifiable** — manual, and the deadline is real |
| 0 re-pull rules | **run** (`docs/RULES_SNAPSHOT_2026-08-27_REPULL.md`); criteria card did not render |
| 1 create account | **NOT verifiable** — manual, Alpaca dashboard |
| 2 `scripts.accounts` | **run** — produced the role→account table |
| 3 `genesis --freeze` | **refusal path run LIVE**: `AAT_COMPETITION_*` pointed at dev's real keys → `GENESIS REFUSED … DENYLISTED`. Success path covered by 38 tests against a fake venue |
| — clean-account state | **run on `pead`**: real $100,000.00, 0 positions, 0 orders of any status, `PA` prefix — every state rule passes; the only failure is the denylist, which is deliberate. Tomorrow's account looks exactly like this minus that entry |
| 4 `preflight` | **run** on dev and pead |
| 5 `tooling_probe` | **run** — 8/8 PASS, `trading` toolset withheld |
| 6 `benchmark_state` | **run** — reads `EXPIRED_UNFILLED` |
| 7 `scripts.thesis` | **run** — recorded, listed, deleted |
| 8 `window_universe` | **run** — 95 names, receipt written |
| 9 `run_pass` dry | **run** on dev and pead, with `--window-universe` |
| 9b `nfp_trade` | **run** — gate 1 false, gate 2 true, `in_entry_window` false |
| 10 `pnl_forensics` | **run** on all four accounts, reconciles with the venue |
| 11 `agent_loop` | **NOT run with the new flags** — dev and exp1 are on the old command line and must not be restarted tonight |

**The two unverified steps are both manual and both yours.** Everything the
machine does has been exercised.

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
