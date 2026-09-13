# DEPLOY PLAN — Monday 2026-09-14, chunk 13b

**Written by the Opus build agent, 2026-09-13. Fable checks it; Murat runs the
lines.** Nothing in chunk 13b has been deployed and nothing has been pushed.
Every number below was printed by the code named beside it, on this machine,
today — not copied from an earlier document.

Two things change on Monday and one thing does not:

1. **hack3's ENGINE becomes Book F** (calendar seasonality). Its sizing, stop,
   horizon and worst case are untouched.
2. **The allocator begins.** From Monday every allocated book carries a
   `--gross-scale` it did not carry before. On day one every scale is **1.00**,
   so the fleet's exposure is exactly what it is today.
3. **hack2 is not touched.** Its loop is already down and its account went to
   lane D on Murat's 2026-09-13 12:05 HKT decision. No command below names it.

---

## 0. THE STATE BEFORE, READ FROM THE VENUE

`railway run --service aat-loop-<role> -- python -m scripts.fleet --check --json`,
2026-09-13, read-only — it places nothing. Markets were closed, so these are
Friday's closing marks and they agree with the 12:10 HKT read to the cent.

| role | account | equity | positions | orders (any status) |
|---|---|---|---|---|
| hack1 | PA3WXDS3MJ53 | $93,863.45 | 3 | 30 |
| hack3 | PA3JYEG4DF9G | $83,342.42 | 10 | 98 |
| hack4 | PA3R9XHMCVDA | $92,941.33 | 4 | 62 |
| hack5 | PA3T8OTGULCD | $95,094.68 | 1 | 12 |
| hack6 | PA3I816FLXE9 | $87,590.50 | 15 | 130 |

hack2: $98,820.50, loop DOWN, reassigned to lane D. Allocated fleet
**$452,832.38**.

**The accounts are NOT reset.** Alpaca's dashboard "reset" is
delete-and-recreate and rotates the API keys; every allocator curve therefore
starts from the equity above, recorded in `state/allocator/anchor.json` with the
account number beside it (`alpha/genesis.py`'s warning: every other piece of
state here is keyed by ROLE, so a role pointed at a new account would carry the
old one's history forward under the same label).

## 1. THE MANDATE AFTER THIS CHUNK, PER ROLE

| role | brains | shadow | universe | changed? |
|---|---|---|---|---|
| hack1 | `theme_basket` | `post_event_drift, murat_rule` | themes (40) | **only the allocator flag** |
| hack2 | — | — | — | **untouched; loop stays down** |
| hack3 | **`seasonality_f`** | **`tracker_portfolio`**, `theme_basket`, `murat_rule` | **`engine_f`** — the month's 30 selected names | **ENGINE SWITCH** |
| hack4 | `tracker_portfolio` | `post_event_drift` | window | **only the allocator flag** |
| hack5 | `theme_basket, post_event_drift` | — | themes with options | **only the allocator flag** |
| hack6 | `tracker_portfolio` | `council_vector, post_event_drift, theme_basket` | window + themes | **only the allocator flag** |

**hack4 does NOT get the G3 lineage.** The one DSR-surviving lineage
(32f752af234f0d3d, Sharpe 6.2735 vs an expected-maximum bar of 3.1528 at 595
trials) was frozen as a static rule in the research repo, and the probe that
asks whether this repo can compute its inputs came back **NOT EXECUTABLE**: six
of its fourteen features have no source here at all (`log_market_cap`,
`disagreement`, `dispersion`, `net_rev_4w`, `target_rev_1m`,
`consensus_rev_1m`), two more exist only as another vendor's near-substitute,
and every feature is a within-month cross-sectional z over ~2,000 names against
a decision-time universe of 98. hack4 keeps its current mandate and is governed
by the allocator's drawdown cut. Receipt:
`../aegis-finance/backend/data/optimus/engines/G3_lineage_32f752af234f0d3d.json`.

## 2. WORST CASE, PRINTED FRESH FROM `alpha.contract.worst_case`

Session-protocol rule 4. Computed 2026-09-13 on the equities in §0, at the
budgets the allocator's first record sets (all 1.00):

| role | n × notional | gross | stop | worst case | in dollars |
|---|---|---|---|---|---|
| hack1 | 8 × 12.50% | 1.00 | 10% | −10.00% | **−$9,386** |
| hack3 | 10 × 10.00% | 1.00 | 12% | −12.00% | **−$10,001** |
| hack4 | 5 × 20.00% | 1.00 | 12% | −12.00% | **−$11,153** |
| hack5 | 6 × 3.00% | 0.18 | 50% of premium | −9.00% | **−$8,559** (absolute premium bound −18.00% = −$17,117) |
| hack6 | 15 × 6.67% | 1.00 | 10% | −10.00% | **−$8,759** |
| **allocated fleet** | | | | **−10.57%** | **−$47,858 of $452,832** |

hack2, not deployed: 8 × 12.5% at an 8% stop = −8.00% = −$7,906. Including it
the six-book number is **−$55,764 of $551,653 = −10.11%**.

**hack3 before the switch: n 10, notional 10.00%, gross 1.00, stop 12.00%,
worst case 12.00%. hack3 after the switch: identical, field for field.** The
mandate changed its ranking and its universe; `worst_case` reads
`BOOK_SIZING × HORIZON_REMAP` and neither mentions a brain.
`tests_smoke_engine_seasonality.py` asserts the five fields rather than
promising it in prose.

## 3. WHAT SHIPS, AND HOW

**The Book F engine file ships IN THE IMAGE, not through the seal authority.**

- `docs/seed/engines/F_seasonality_2026-09.json` (sha `141b01cd6344b43d`) and
  `F_seasonality_2026-10.json` (sha `dae6f7db5aa2ff48`).
- The Dockerfile does `COPY docs/seed/ /app/seed/` and the container start does
  `cp -rn /app/seed/. /app/state/`, so the file lands on the volume at
  `/app/state/engines/` where `alpha/brains/seasonality_f.py` looks first, and
  the repo copy at `/app/docs/seed/engines/` is the fallback.
- It does **not** go through `scripts/seal_authority.py`. That service serves
  `state/predictions/` over HTTP and nothing else
  (`scripts/prediction_book_sync.py` is its only consumer), so **no
  seal-authority redeploy is required by this chunk.** Redeploying it would be
  harmless and would change nothing.
- **`cp -rn` NEVER OVERWRITES.** A *new* month's file is a new name and arrives
  normally. A *corrected* file for a month already on the volume does **not**
  arrive, and the stale copy keeps winning silently because it verifies against
  its own hash perfectly. If an engine file for a month already seeded is ever
  re-exported, the volume copy must be removed by hand.

**The allocator's record ships the same way:**
`docs/seed/allocator/anchor.json` and `docs/seed/allocator/2026-09-11.json`.

## 4. THE ALLOCATOR'S FIRST RUN — ALREADY DONE, ON DISK, NO VENUE WRITE

    python -m scripts.allocator --anchor --day 2026-09-11 \
      --equity "hack1=93863.45:PA3WXDS3MJ53,hack3=83342.42:PA3JYEG4DF9G,\
    hack4=92941.33:PA3R9XHMCVDA,hack5=95094.68:PA3T8OTGULCD,hack6=87590.50:PA3I816FLXE9"
    python -m scripts.allocator --run --day 2026-09-11 --equity "<the same>"

Result (`state/allocator/2026-09-11.json`, contract `25aadd395acf688d`):

| role | drawdown | state | posterior mean | blocks | weight | EW twin | random twin | **gross** |
|---|---|---|---|---|---|---|---|---|
| hack1 | +0.00% | ACTIVE | +0.3297%/d | 0 | 0.172 | 0.200 | 0.350 | **1.00** |
| hack3 | +0.00% | ACTIVE | +0.0206%/d | 0 | 0.350 | 0.200 | 0.106 | **1.00** |
| hack4 | +0.00% | ACTIVE | +0.0000%/d | 0 | 0.117 | 0.200 | 0.071 | **1.00** |
| hack5 | +0.00% | ACTIVE | +0.4529%/d | 0 | 0.245 | 0.200 | 0.350 | **1.00** |
| hack6 | +0.00% | ACTIVE | +0.0000%/d | 0 | 0.116 | 0.200 | 0.124 | **1.00** |

No kill rule fired. hack3 takes the 35% pool ceiling on Book F's replay prior
(419 blocks, t 3.1178) — it is the only book with a prior that rests on more
than one date block. **No book's GROSS moves**, because no book has three
complete date blocks yet and the return signal may not move a live book's size
before it does (`TRIAL-DRAFT-ALLOCATOR-v0` §6.2). Twins both at 0 over 0
sessions; verdict clock **TOO EARLY, 60 sessions to the decision**.

**The daily run from Monday** (not registered — registering a scheduled task is
an attended act; and the machine's clock is UTC+8 while the venue closes 16:00
ET, so compute ET before trusting the hour):

    schtasks /Create /TN "aegis-allocator" /SC WEEKLY /D MON,TUE,WED,THU,FRI ^
      /ST 17:15 /TR "cmd /c cd /d C:\Users\mrthn\aegis-alpha-terminal && ^
      python -m scripts.allocator --run >> state\allocator\run.log 2>&1"

It runs **here**, not on Railway: reading six accounts needs six key pairs, and
`--deploy` gives each service exactly one role's keys and its own volume, so no
Railway service could read the fleet or write into the loops' state.

## 5. THE DEPLOY LINES, IN ORDER

Run from `C:\Users\mrthn\aegis-alpha-terminal` with the repo **pushed** (the
deploy stamps `AAT_BUILD_COMMIT` and marks a dirty tree as `+dirty`).

    # 0. the gate, first — a red suite is not a deploy
    python run_tests.py                      # expect: 87 suites, ALL PASS

    # 1. the book whose ENGINE changed, alone, so its logs can be read on their own
    python -m scripts.fleet --deploy hack3 --up

    # 2. the four that change only by the allocator flag
    python -m scripts.fleet --deploy hack1 --up
    python -m scripts.fleet --deploy hack4 --up
    python -m scripts.fleet --deploy hack5 --up
    python -m scripts.fleet --deploy hack6 --up

    # 3. hack2 is NOT deployed. Its loop stays down; its account is lane D's.

hack3 goes first and alone on purpose: it is the only behavioural change, and a
five-service deploy that goes wrong is five logs to read instead of one.

The variable set each line writes (printed by
`python -m scripts.fleet --railway hack3`, no deploy):

    AAT_LOOP_BRAINS=seasonality_f
    AAT_LOOP_SHADOW=tracker_portfolio,theme_basket,murat_rule
    AAT_RISK_PROFILE=basket   AAT_RANK_OBJECTIVE=median
    AAT_STRUCTURE_KINDS=long_shares   AAT_ALLOW_MAXIMUM=1
    AAT_LOOP_ARGS=--profile basket --gross-scale 1.000000 --universe THO AEHR ALGN
      NKE EVR RDN SNDK SFNC RMBS OXM IPAR EXTR NXST PAR NEOG AEO CBRL HURN AXON
      AMZN TCBK AZZ STAA QDEL MGM MANH GIII MNST EVC EEFT
    AAT_LOOP_EXPIRY=2027-12-31   AAT_MANDATE_END_UTC=2027-12-31T15:00:00Z

`--deploy` already reads every variable back after the bulk `--set` and re-sets
any that did not take (the 28 Aug lesson: a variable that was not verified was
not set).

## 6. VERIFY, AFTER

    python -m scripts.fleet --check-all
    python -m scripts.fleet_health
    railway logs --service aat-loop-hack3 | findstr /C:"seasonality" /C:"engine" /C:"REFUS"

What a healthy hack3 log looks like on Monday: the entry pass asks about the
thirty names in `AAT_LOOP_ARGS`, `seasonality_f` speaks for the first **ten** and
declines the other twenty by name with *"does not re-rank at decision time"*.
`tracker_portfolio` appears in the SHADOW rows and places nothing.

**The one failure to expect and to recognise:** if the engine file did not reach
the container, every symbol is declined with *"no seasonality engine file for
2026-09 … it does not re-derive a twenty-year seasonality average at the open"*
and hack3 holds what it has. That is the designed failure, not a bug — but it
means the deploy did not ship `docs/seed/engines/`, so check the image, not the
brain.

## 7. THE CALENDAR ITEM THIS CREATES

**hack3 needs a redeploy every calendar month.** The engine file is per month
and the brain refuses a month it has no file for. `F_seasonality_2026-10.json`
is already installed, so the October redeploy only refreshes
`AAT_LOOP_ARGS`' universe — but it is not optional: without it the October
universe would still be September's thirty names while the brain declined every
one of them.

    # first business day of each month, in the research repo:
    python -m scripts.night_factory_jobs F_seasonality_export
    # then copy the new month's file into aegis-alpha-terminal/docs/seed/engines/,
    # commit, push, and:
    python -m scripts.fleet --deploy hack3 --up

## 8. WHAT THIS PLAN DOES NOT DO

- It does not reset any account.
- It does not deploy hack2, touch lane D, or change any key.
- It does not change any `k`, `notional%`, `stop` or `profile` — the only reason
  §2's table can be identical to last week's.
- It does not promote anything on return: every gross budget is 1.00 and the
  first budget that can move on return is 3 complete date blocks away (hack5
  at 2 sessions a block, hack1 at 5, hack3 and hack6 at 21, hack4 at 42).
- It claims nothing about Book F. F is **CONDITIONAL** — its falsifiers passed
  and its primary did not clear its declared effect size. It is deployed under
  `PRODUCT_EXPERIMENT` to find out what it does on real fills.
