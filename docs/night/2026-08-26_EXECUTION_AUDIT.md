# Execution audit — 2026-08-26 (night, read-only)

Scope: the decision -> order -> fill -> ledger path in `alpha/engine/equity.py`,
`alpha/broker/alpaca.py`, `alpha/runner.py`, `alpha/exits.py`, `alpha/fills.py`,
`alpha/recovery.py`, `alpha/book.py`, `alpha/ledger.py`, `scripts/agent_loop.py`,
`scripts/run_pass.py`, `scripts/manage.py`, `scripts/preflight.py`, checked
against the seven order-lifecycle failure classes in
`docs/night/2026-08-26_EXTERNAL_PROJECTS_DIGEST.md` ("Cross-cutting" §3 and
"Ten build-in-a-day"). No file was modified. Line numbers are as of this commit.

**The one-paragraph reading.** Our surface is SMALLER than the nine rivals':
one order type (limit, DAY, whole units), no bracket/OTO, no broker-side stop,
one exit verb (`DELETE /v2/positions/{symbol}`). That removes four of the
digest's eight bug classes outright (OTO TIF, held_for_orders, fractional
co-rest, `int(qty)`->0 silently). What is left is the mirror image: **there is
no stop at the broker at all**, the client-side stop is sampled at a cadence
that an LLM entry pass can stretch to ~30 minutes, **there is no daily-loss
latch and the sizer scales risk UP after losses late in the window**, and a
resting unfilled entry is invisible to the one-position-per-symbol guard, so a
restart or the next 30-minute pass can stack a second order on the first.

---

## 1. Stop/exit children inheriting DAY TIF (OTO/bracket)

**VERDICT: not applicable — but the underlying exposure is WORSE than the bug.**

Evidence:

- `alpha/runner.py:360-388` `build_order` emits exactly three shapes, all
  `"type": "limit"`, `"time_in_force": "day"`, no `order_class` other than
  `mleg`, no `take_profit`, no `stop_loss`:
  ```
  366  "symbol": symbol, "qty": str(contracts), "side": side,
  367  "type": "limit", "limit_price": f"{abs(structure.entry_cost):.2f}",
  368  "time_in_force": "day",
  ```
- `grep -rn "order_class\|stop_loss\|take_profit\|stop_price"` over `alpha/` and
  `scripts/` returns only the `mleg` line. There is no child order to inherit
  anything.
- The only stop is `alpha/engine/equity.py:201-206` (`stop_hit` /
  `target_hit`), evaluated in `alpha/exits.py:151-165` from
  `position["unrealized_plpc"]`, and only when `scripts/manage.py` runs.
- `scripts/agent_loop.py:90-91` runs `manage` only `if is_open`.

Failure scenario: a long-shares leg filled at 15:58 ET Friday 28 Aug. Between
16:00 Friday and ~09:35 Monday there is nothing at the venue that will sell it.
A -8% gap on Monday's open is booked in full; the "3% stop" the book was
charged for (`STOP_FRACTION + gap`, `equity.py:73`) was never a stop, it was a
charge. quant-agent's positions "sat NAKED overnight" because of a TIF bug;
ours sit naked overnight by construction.

Partial fill of the entry: the DAY limit rests for the remainder and expires at
16:00. The ledger row keeps `order.qty = n` (`runner.py:635-637`). In
`alpha/book.py:216-227` a row whose legs are not ALL held at the full
`contracts` fails to match (`have < need`), so a partially filled share
position becomes a residual: long charged at `MAX_LOSS_FRACTION`
(`book.py:287-292`, acceptable); **short shares residual is UNBOUNDED**
(`book.py:249-254`) and every subsequent entry in the account is refused
(`runner.py:459-469`) until a human intervenes. So a partial fill of a
short-shares entry silently halts the whole book for the rest of the day.
`exits._entry_row_for_shares` (`exits.py:132-148`) matches by symbol only, so
the horizon/stop is still found for the partial — that part is fine.

Minimal fix: after the entry order is terminal (poll `GET /v2/orders/{id}` for
`filled`/`partially_filled`+expired), place a GTC stop (`type: stop`, sized to
`filled_qty`) as a SEPARATE order with its own `client_order_id` derived from
`decision_id + ":stop"`; record its id on the ledger row. Do not use
bracket/OTO. In `book.reconstruct`, treat a share row as matched at
`min(contracts, held)` instead of all-or-nothing, so a partial short is charged
at its stop rather than read as unbounded.

## 2. Selling into our own resting children (`held_for_orders`)

**VERDICT: safe from the digest's bug (no children exist); a related
sequencing gap is CANNOT DETERMINE.**

Evidence:

- The only exit call is `alpha/exits.py:369` `client.close_position(symbol)` ->
  `alpha/broker/alpaca.py:297-301` `DELETE /v2/positions/{symbol}`.
- No code path anywhere reads open orders before acting: `grep -rn "\.orders("`
  hits only `scripts/preflight.py:77` (freshness check). There is no
  cancel-open-orders-then-sell sequence.

What can still happen: the entry limit (DAY) is partially filled and still
resting when `manage` decides to close (stop/target/horizon). `close_position`
closes the held qty; the resting remainder stays open. If it fills afterwards
the position re-opens with no fresh decision; the next `manage` pass finds the
old `submitted` row (`exits.py:132-148`) and evaluates the re-opened lot on the
ORIGINAL entry timestamp, so it is held until stop/target/horizon rather than
flattened as an orphan. Not a short flip (DELETE never over-sells), but a
position that was decided-closed is open again. Whether Alpaca's single-symbol
DELETE refuses while an order rests on that symbol is not asserted anywhere in
our code and I cannot determine it from the repo; either outcome is unhandled
(a refusal is counted as `errors` and retried in 5 min; a success leaves the
resting order).

Option structures: `manage` iterates `client.positions()` in venue order and
DELETEs each LEG separately (`exits.py:346-373`). If the long wing of a
credit spread is closed first, the short leg is naked for one request; a
level-3 paper account may reject that leg close, which lands as
`close_failed` and an error count. Cannot determine from code whether the
venue rejects; the arbiter test (`tests_smoke_arbiter.py:105`) fakes
`close_position` and never exercises ordering.

Minimal fix: before `close_position`, `GET /v2/orders?status=open&symbols=X`
and `DELETE /v2/orders/{id}` each; then close. For multi-leg structures, close
short legs before long legs (or use one `mleg` closing order).

## 3. Fractional shares / notional / `int(qty)` -> 0

**VERDICT: safe.**

Evidence:

- Quantities are whole units: `runner.py:391-401` `contracts_for` returns
  `int(budget // structure.max_loss)` capped by `equity.units_cap`
  (`equity.py:194-198`, `int(... // spot)`); `build_order` sends
  `"qty": str(contracts)`. No `notional` anywhere (`grep -rn notional` hits
  prose only).
- `int(...)->0` is a RECORDED REFUSAL, not a silent no-op: `runner.py:604-612`
  writes `refused ... Rounds to zero contracts`, and `build_order` itself
  raises on `contracts < 1` (`runner.py:362-363`).
- Only one exit verb (full-position DELETE), so two exits cannot co-rest.

Residual note: `contracts_for` divides the risk budget by `max_loss = spot *
charge` (5-8% of spot), so a 3% risk fraction becomes 40-60% notional before
`units_cap` clamps it to 25% (`equity.py:121`). The cap works; the number
recorded as `risk_fraction` on the row is therefore not the notional the trade
carries. Reporting issue only.

## 4. Double-fired exits / duplicate submissions on re-run

**VERDICT: bug (entries); safe (exits).**

Evidence:

- Idempotency = `client_order_id = "aat-" + sha256(decision_id)[:32]`
  (`alpaca.py:304-307`), `decision_id = "%Y%m%dT%H%M:brain:symbol"`
  (`ledger.py:554-563`). Collision is guaranteed only within the SAME MINUTE.
- The cross-minute guard is `held_underlyings` (`runner.py:127-136`), which
  reads `client.positions()` — **positions, not open orders**. An entry limit
  that has not filled is not a position.
- The loop's entry cadence is 30 min (`agent_loop.py:100-110`); the entry limit
  is DAY at the ask/bid of an IEX or synthetic quote (`runner.py:300-357`).

Failure scenario: 10:00 pass sends `buy 120 NVDA limit 212.96 DAY`; price
ticks to 213.10 and the order rests. 10:30 pass: NVDA not in `held`, the
brain re-forecasts, a new decision id (different minute) -> a second
`buy 120 NVDA` rests. A dip to 212.90 fills both: 240 shares, 50% notional
against a 25% cap, two ledger rows, `book.reconstruct` matches both (240
held >= 2x120) and the admission controller was never asked about the second.
Same mechanism on a process restart one minute after a submit, and on two
`agent_loop` processes on the same role (Session 9 found dead/duplicated
loops). renee-jia's pending-order guard and tradefarm's `_pending_exits` are
the digest's fix for exactly this.

Exits: `close_position` is a full-qty DELETE, so a second call on a still-open
position after the first market close is in flight either errors ("insufficient
qty") or closes what remains; it cannot flip the sign. The exit `decision_id`
(`exits.py:361`) is not sent to the venue at all, so there is no idempotency
key on exits — harmless here because the verb is idempotent by nature.

Minimal fix: in `run_pass`, fetch `client.orders(status="open")` once per pass
and add every symbol (and OCC root) with an open order to `held`; refuse with
reason "order in flight". Additionally, on `BrokerRefusal` containing
`client_order_id` duplicate text, record `action="duplicate_collision"` rather
than `rejected` so the ledger distinguishes the guard working from a real
reject.

## 5. -3% day-start-equity latch / kill switch

**VERDICT: bug — none exists, and the sizer does the opposite.**

Evidence:

- `grep -rln "last_equity\|day_start\|daily_loss\|halt"` over `alpha/` and
  `scripts/` hits nothing on the execution path (one prose hit in
  `daily_autopsy.py`).
- Equity is read once per entry pass (`runner.py:107-123` `tournament_state`)
  against a CONSTANT `starting_equity = 100_000` (`config.py:230`), never
  against the day's opening equity (Alpaca's `last_equity` field is not read).
- `alpha/engine/sizing.py:404-432` `_tournament_multiplier`: in LATE/FINAL
  phase (last ~2 sessions), `if state.behind or ret < 0.0: mult = 2.0 if FINAL
  else 1.6` — **a negative return raises risk by 1.6-2.0x**. In MIDDLE phase,
  `behind` raises it 1.4x. There is no branch that reduces size after a loss.
- Nothing survives a restart because nothing is stored: the loop holds only
  `last[...]` timestamps in memory (`agent_loop.py:80`).

Failure scenario: Monday 31 Aug the book opens -3.5% on a gap (item 1). The
09:30 entry pass sees `ret = -0.035`, phase MIDDLE (window remaining ~60%),
sizes at 1.0-1.4x and adds new risk into the drawdown. By Thursday 3 Sep
(FINAL) a -2% book is sized at 2.0x. The digest's shark/quant-agent latch is
the exact opposite policy, and the judges' "risk gates" criterion asks for it.

Minimal fix: a 30-line `alpha/daybreak.py`: at first pass of each ET session
write `{date, equity}` to `state/day_start_<role>.json` (or read Alpaca's
`account.last_equity`, which is the previous close equity and survives
restarts for free); `runner.run_pass` and `admission.admit` refuse every entry
when `equity / day_start - 1 <= -0.03`; `exits.manage` is unaffected. Reset by
date, not by process. Separately cap `_tournament_multiplier` at 1.0 when
`ret < 0` — or delete the "behind -> lean in" branch for the competition role.

## 6. Stops on closes vs intraday

**VERDICT: partial — evaluated on the venue's last-trade mark, but SAMPLED, and
the sampler is starved by the entry pass.**

Evidence:

- `exits.py:192` `plpc = float(position.get("unrealized_plpc"))` — Alpaca's
  positions endpoint marks at the latest trade, so this is an intraday mark,
  not a close. No bar high/low is consulted.
- Sampling: `agent_loop.py:90-91` runs `manage` when `now - last["exit"] >=
  5 min`, but the loop is SEQUENTIAL (`subprocess.call`), and `run_pass` is
  allowed 1500 s (`agent_loop.py:50`) with DeepSeek calls inside it. The file's
  own comment (`agent_loop.py:47-49`) says exits "must never wait on an LLM
  call", and then they do.
- `manage` runs only while `is_open` (`agent_loop.py:90`), so the first stop
  check after an overnight gap is at 09:30 + up to one cycle.

Failure scenario: an entry pass starts 10:00:30 and spends 22 minutes in
brains + chain fetches over 15 names plus candidates. NVDA drops 4% at 10:07.
The stop fires at 10:23 at -5.5%. Agent 7 last night showed 77-91% of PEAD
legs touch the stop intraday; a stop that is checked every 5-30 minutes catches
the touch late, and the digest's AutoTrader #528 says a close-sampled stop is a
lower bound on damage. Ours is a 5-30-minute-sampled stop — between the two.

Minimal fix: item 1 (a GTC stop at the venue) makes sampling irrelevant for the
share legs. Independently, run `manage` in its own thread/process with its own
clock, or call `exits.manage` from inside `run_pass` before the brains start and
after each symbol.

## 7. Everything else on decision -> order -> fill -> ledger

7a. **Key selection — safe, with one silent-disagreement path (bug, low).**
`config.credentials` (`config.py:159-183`) reads only `AAT_<ROLE>_KEY_ID/_SECRET_KEY`,
refuses fallback to `ALPACA_*` by name (`config.py:103-108`), requires an
explicit role (`config.py:136-156`), allowlists the paper host (`config.py:79,186-190`),
and `AlpacaPaper._verify_paper` checks the `PA` prefix server-side
(`alpaca.py:93-113`). Covered by `tests_smoke.py:179-215`. The gap:
`scripts/run_pass.py:195` / `scripts/manage.py:267` build the client from
`--role`, but every ledger stamp and book match read `AAT_ACCOUNT_ROLE` from
the environment (`runner.py:698`, `exits.py:136`, `book.py:321-322`,
`recovery.py`). `AAT_ACCOUNT_ROLE=dev python -m scripts.run_pass --role
competition --live` sends orders to the competition account and stamps the rows
`dev`; `book.reconstruct(account_role="dev")` then matches dev rows against
competition positions, and the competition account's book risk is computed from
another account's rows. Fix: `AlpacaPaper.__post_init__` sets
`os.environ["AAT_ACCOUNT_ROLE"]` from its resolved role, or refuse when the two
disagree.

7b. **Ledger/broker drift on partial and expired fills — bug, low.** A
`submitted` row is never updated with `filled_qty` or terminal status
(`ledger` is append-only by design; `fills.py` audits into a separate
`fills` ledger but reads `qty = order.qty` not `filled_qty`, `fills.py:104`,
so `slippage_usd` is overstated on partials). An unfilled DAY order expires at
16:00 and its row stays `submitted` forever; `recovery.live_scores`
(`recovery.py:491-527`) and the counterfactual then grade a decision that
never became a position as if it had. Money impact: recovery-mode demotion of
a brain on the mark of a trade it never made. Fix: `fill_audit` writes a
`:terminal` row with `filled_qty` and `status`; `recovery` and `book` prefer
it.

7c. **Market orders at the open / extended hours — safe.** Entries are always
limit (`runner.py:360-388`); `extended_hours` is never set and the broker
refuses it for options (`alpaca.py:289-293`). Note that `DELETE /v2/positions`
submits a MARKET order; the deadline liquidation at 10:45 ET (`exits.py:66`) is
deliberate, and on a wide option that market order is the price of certainty.

7d. **Starting equity is a constant — bug, low, competition-neutral.**
`tournament_state` uses `config.COMPETITION["required_starting_equity"]` for
every role (`runner.py:110-111`), so on `dev` (not $100k) `total_return` and
the `behind` multiplier are computed against the wrong base. Correct on the
competition account by coincidence of the rules. Fix: read the first-pass
equity per role from disk (same file as the day-start latch).

7e. **Pass killed mid-loop — safe.** `agent_loop._run` kills `manage` at 300 s
(`agent_loop.py:50-61`); `close_position` precedes `_record_exit`
(`exits.py:369-373`), so the worst case is a closed position with no exit row,
which the next pass reads from the venue. `ledger._Lock` (`ledger.py:452-490`)
survives a dead writer via the 30 s stale rule.

7f. **`--candidates` universe reads `state/candidates` relative to CWD**
(`run_pass.py:202`) while `ledger.LEDGER_DIR` is absolute (`ledger.py:366`).
Started from another directory, the entry pass silently trades the fixed
15-name universe only. Not a money loss; a silent scope change.

7g. **Holidays.** `_sessions_since` (`exits.py:112-129`) ignores holidays; the
window 28 Aug - 4 Sep 2026 contains none (Labor Day is 7 Sep). Correct for
this window and wrong the day after.

---

## Existing smoke tests covering these paths

All are `check(...)`-style scripts, not pytest; run each with `python <file>`.

| File | What it covers on the execution path |
|---|---|
| `tests_smoke_equity.py:151-158` | `contracts_for` (risk -> units, small budget -> 0), `build_order` for long and short shares emits `type: limit`, `time_in_force: day`, `limit_price` at the ask/bid |
| `tests_smoke_equity.py:162` | `held_underlyings` counts a share position |
| `tests_smoke_equity.py:164-168` | synthetic quote substitution when the IEX quote is one-sided or off-trade |
| `tests_smoke_equity.py:210-219` | `exits.evaluate` for shares: hold inside, close at -3%, close at +2.5%, horizon exit after 15:45 on the last session, orphan (no ledger row) flattened, deadline outranks everything |
| `tests_smoke_arbiter.py:93-131` | `exits.manage` end to end with a fake client: advise mode records only, act mode calls `close_position`; `ARBITER_RECORD_EVERY_S` throttling |
| `tests_smoke_book.py:51-90` | `book.reconstruct`: structures matched at max loss, premium-paid view kept beside it, role-stamped rows never matched to another book, residual short at full width, naked residual short = UNBOUNDED, role-less rows explained largest-first |
| `tests_smoke_book.py:195-219` | node cap counts the BOOK; recovery-mode demotion (`res.submitted` counts) |
| `tests_smoke_brains.py:224` | `held_underlyings` decodes the OCC root |
| `tests_smoke.py:91-95` | ledger hash chain verifies and detects tampering |
| `tests_smoke.py:179-215` | child env forced to paper, live host refused, forbidden inherited key names refused, unset role refuses, the LLM tool spec cannot place an order |

**Not covered by any test:** `client_order_id` derivation and cross-minute
non-collision; behaviour with an open (unfilled) order for a held symbol; a
partial fill of a share row in `book.reconstruct`; any daily-loss behaviour;
the `--role` flag vs `AAT_ACCOUNT_ROLE` disagreement; `exits.manage` ordering
of multi-leg closes; the `_tournament_multiplier` sign on negative returns.

---

## Confirmed defects worth a day patch before 28 Aug 15:00 UTC (ranked)

1. **No stop at the venue; positions are naked from 16:00 to the first
   `manage` pass** (`runner.py:360-388`, `agent_loop.py:90`). Patch: post-fill
   GTC `stop` order sized to `filled_qty`, id derived from `decision_id +
   ":stop"`, id recorded on the row. Plus the cancel-then-close in item 2 the
   same day, or the stop will sit under every `close_position` call.
2. **No daily-loss latch, and `_tournament_multiplier` sizes UP on a negative
   return** (`sizing.py:404-432`, nothing reads day-start equity). Patch:
   `account.last_equity` (survives restarts) -> refuse entries at -3%; clamp the
   multiplier to <=1.0 when `ret < 0` for the competition role.
3. **Unfilled entry orders are invisible to the one-position-per-symbol
   guard** (`runner.py:127-136`, `483-498`); the 30-minute cadence and any
   restart past the minute stack a second order. Patch: merge
   `client.orders(status="open")` into `held`.
4. **Exit sampling is starved by the entry pass** (`agent_loop.py:50, 90-110`,
   sequential `subprocess.call`, `run_pass` allowed 1500 s). Patch: run
   `manage` on its own thread or invoke `exits.manage` inside `run_pass` before
   the brains. Largely moot for shares once #1 lands; still binds for options.
5. **Partial fill of a SHORT-shares entry reads as UNBOUNDED and halts every
   entry for the day** (`book.py:216-227, 249-254`). Patch: match share rows
   at `min(contracts, held)`.
6. **`--role` flag and `AAT_ACCOUNT_ROLE` can disagree silently**, stamping
   one account's rows with another's role and mis-reconstructing the book
   (`run_pass.py:195`, `runner.py:698`, `book.py:321`). Patch: refuse on
   disagreement.
7. **Expired/partial orders never reach the ledger as terminal**, so
   `recovery` grades trades that never opened and `fills` overstates slippage
   (`fills.py:104`, `recovery.py:491-527`). Patch: `fill_audit` writes a
   `:terminal` row with `filled_qty`/`status`.

Not defects, confirmed safe: fractional/notional/`int(qty)` silent zero (item
3), bracket-child TIF (item 1, nothing to inherit), selling into own children
(item 2, none exist), key namespace and paper-host guards (7a), extended-hours
and market-at-open entries (7c).
