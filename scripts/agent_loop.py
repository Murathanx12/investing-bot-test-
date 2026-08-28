"""The unattended loop: exits often, entries on a cadence, counterfactuals hourly.

    AAT_ACCOUNT_ROLE=dev python -m scripts.agent_loop --expiry 2026-08-28            # dry
    AAT_ACCOUNT_ROLE=dev python -m scripts.agent_loop --expiry 2026-08-28 --live

Cadence (all in market time, read from the venue clock, never from the laptop):

    exits            every 5 min while the market is open     (deadline, expiry, targets)
    entries          every 30 min while open, and once at 15:30 ET for the next session
    counterfactual   every 60 min, market open or not          (marks need quotes; stale
                                                                quotes mark as stale)
    belief vs chain  every 60 min while open, graded after resolution
    fill audit       every 15 min while an order is open

TWO ACCOUNTS, TWO CHAMPIONS. The second paper account is not a duplicate risk
profile; it runs the strongest CHALLENGER so the two produce competing fill and
P&L evidence on the same sessions:

    AAT_ACCOUNT_ROLE=dev  python -m scripts.agent_loop --expiry ... --live
        (champion: vol_gap + event_move execute; attention/narrative shadow)
    AAT_ACCOUNT_ROLE=exp1 python -m scripts.agent_loop --expiry ... --live         --brains vol_gap,event_move,options_attention,narrative_dispersion --shadow vol_gap,event_move
        (challenger: the two shadow brains execute; the champion pair is shadowed)

Both write to the same ledgers with the account role on every row, so
`scripts.counterfactual` grades them against each other at equal risk.

A crash mid-cycle is safe: decision ids are minute-derived so a restart inside
the same minute collides at the broker, and every cycle re-reads the venue.
Nothing here holds state between cycles except the ledgers on disk.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from alpha import config, liveness
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal

log = logging.getLogger("loop")


#: A pass that runs longer than this is killed and logged. The loop is
#: sequential, so a long entry pass starves the five-minute EXIT pass -- and
#: exits are the one job that must never wait on an LLM call.
#:
#: run_pass was 1500s, chosen as a safety net rather than from evidence. MEASURED
#: over 10 completed entry passes in `state/loop_exp1.log`: median 368s, p90
#: 439s, max 439s. So the ceiling was 3.4x the worst pass ever observed, and it
#: bought that headroom by letting a hung pass delay exits by 25 minutes.
#:
#: 600s sits ~37% above the worst observed pass and caps the exit delay at
#: roughly 600 + 60 = 11 minutes instead of 26. A pass that exceeds it is not a
#: slow pass, it is a stuck one, and the next cycle re-reads the venue anyway.
#: (Audit defect 4 -- see docs/FINDING_2026-08-26_DEFECT_4_IS_SLIPPAGE_NOT_RUIN.md
#: for why this is the proportionate fix and venue-side structure stops are not.)
TIMEOUTS_S = {"scripts.run_pass": 600, "scripts.dislocation_scan": 1500, "scripts.premarket_digest": 600, "scripts.manage": 300, "scripts.counterfactual": 600, "scripts.candidates": 900, "scripts.daily_autopsy": 900,
              "scripts.fill_audit": 300}


def _market_open(client) -> bool:
    """Venue clock, treating an unreadable clock as CLOSED.

    Closed is the safe default here: this gates an EXTRA exit pass, so a wrong
    False costs one skipped pass that the next cycle picks up, while a wrong
    True spends a `manage` run against a venue we cannot reach.
    """
    try:
        return bool(client.clock().get("is_open"))
    except BrokerRefusal as exc:
        log.warning("clock unavailable after entry pass: %s -- skipping the immediate exit", exc)
        return False


def _commit() -> str | None:
    """Which code is running. A heartbeat that cannot say that explains an
    outage as a mystery rather than as a deploy."""
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=str(Path(__file__).resolve().parent.parent),
                                       text=True, timeout=10).strip()
    except (OSError, subprocess.SubprocessError):
        return None


#: Consecutive non-zero exits from one step before the loop says so LOUDLY.
#: Two, not one: a single failure is usually a transient venue refusal and the
#: next cycle re-reads. Three in a row is a configuration error nobody has seen.
NOISY_AFTER = 2

#: mod -> how many times in a row it has exited non-zero.
_consecutive_failures: dict[str, int] = {}


def _run(mod: str, *args: str, live: bool) -> int:
    """Run one step. A NON-ZERO EXIT IS NOT SILENT.

    Every caller below discards this return value, and for most steps that is
    right -- a failed autopsy should not stop the loop. But the failure it hides
    is the one this repo keeps paying for: `scripts.run_pass` exiting 2 on every
    cycle (a bad --expiry, an unverified genesis, a missing window universe)
    produces a loop that logs "run scripts.run_pass" forever, a heartbeat that
    stays HEALTHY, and a book that never trades.

    **A refusing pass reads exactly like a quiet market.** That is the same shape
    as the dead loops on 26 Aug, which read exactly like a quiet market too.

    So the count lives here, where every step passes through, rather than in each
    caller -- which is how it would be forgotten on the next one added.
    """
    cmd = [sys.executable, "-m", mod, *args] + (["--live"] if live else [])
    log.info("run %s", " ".join(cmd[2:]))
    try:
        rc = subprocess.call(cmd, timeout=TIMEOUTS_S.get(mod, 900))
    except subprocess.TimeoutExpired:
        log.error("%s exceeded %ss and was killed; the next cycle re-reads the venue", mod, TIMEOUTS_S.get(mod, 900))
        _consecutive_failures[mod] = _consecutive_failures.get(mod, 0) + 1
        return 124
    if rc == 0:
        if _consecutive_failures.get(mod):
            log.info("%s recovered after %d consecutive failure(s)", mod, _consecutive_failures[mod])
        _consecutive_failures[mod] = 0
        return rc
    n = _consecutive_failures[mod] = _consecutive_failures.get(mod, 0) + 1
    if n >= NOISY_AFTER:
        log.error("%s HAS EXITED NON-ZERO %d TIMES IN A ROW (last rc=%d). This loop is "
                  "cycling and doing nothing, which looks identical to a quiet market. "
                  "Run it by hand and read the refusal: %s",
                  mod, n, rc, " ".join(cmd[2:]))
    else:
        log.warning("%s exited rc=%d", mod, rc)
    return rc


def failing_steps() -> dict[str, int]:
    """Steps currently failing, and for how many cycles. Read by the heartbeat."""
    return {m: n for m, n in _consecutive_failures.items() if n}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--expiry", required=True)
    p.add_argument("--live", action="store_true")
    p.add_argument("--entry-minutes", type=int, default=30)
    p.add_argument("--exit-minutes", type=int, default=5)
    p.add_argument("--once", action="store_true", help="one cycle, then exit")
    p.add_argument("--brains", default=None, help="comma list passed to run_pass (the account's CHAMPION set)")
    p.add_argument("--shadow", default=None, help="comma list passed to run_pass (recorded, never executed)")
    p.add_argument("--profile", default=None, help="risk profile passed to run_pass")
    p.add_argument("--universe", nargs="*", default=None, help="symbols passed to run_pass")
    p.add_argument("--window-universe", action="store_true",
                   help=("pass --window-universe to every entry pass, so the universe is the "
                         "names with an event inside the contest rather than fifteen hardcoded "
                         "mega-caps that all reported in July. WITHOUT THIS the loop produces "
                         "zero forecasts in late August and looks like a quiet market."))
    p.add_argument("--refresh-window-minutes", type=int, default=360,
                   help="how often to regenerate state/window_universe.json (0 = never)")
    p.add_argument("--council", action="store_true",
                   help="every 6h run scripts.dislocation_scan --deep 3 on the day's printers so "
                        "council_vector has packets on THIS host's volume (the council brain reads "
                        "state/council/<day>/; a scan on the laptop writes to the laptop)")
    p.add_argument("--manage-only", action="store_true",
                   help="LEGACY MODE: run exits, fills, counterfactual and autopsy, but NEVER "
                        "an entry pass. The book can only get smaller. Use for a book that is "
                        "being wound down rather than traded -- it keeps stops, exits and the "
                        "forward record alive while prohibiting new risk.")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    config.load_env()
    client = AlpacaPaper()

    last = {"exit": 0.0, "entry": 0.0, "cf": 0.0, "fill": 0.0, "belief": 0.0, "candidates": 0.0, "council": 0.0,
            "autopsy": 0.0, "window": 0.0}
    consecutive_errors = 0
    # THE HEARTBEAT. A dead process cannot report its own death, so the receipt
    # has to exist before the first cycle and be refreshed by every one that
    # completes. `scripts.liveness` and the dashboard read it; nothing runs in
    # the background to make this work, so nothing in the background can fail
    # silently and take the guarantee with it.
    role = os.getenv("AAT_ACCOUNT_ROLE", "").strip().lower() or "unset"
    beat = liveness.Beat(role=role, pid=os.getpid(), expiry=args.expiry, live=bool(args.live),
                         argv=sys.argv[1:], commit=_commit(),
                         started_utc=datetime.now(timezone.utc).isoformat())
    liveness.write(beat)
    while True:
        beat.started_utc = datetime.now(timezone.utc).isoformat()
        liveness.write(beat)
        try:
            consecutive_errors = _cycle(client, args, last)
            beat.cycle += 1
            beat.completed_utc = datetime.now(timezone.utc).isoformat()
            beat.failing_steps = failing_steps()
            beat.consecutive_errors = 0
            beat.last_error = None
            beat.backoff_until_utc = None
            liveness.write(beat)
        except Exception as exc:
            # THE SUPERVISOR MUST OUTLIVE THE WORK.
            #
            # Every job below already runs as a subprocess and cannot take this
            # process down. The clock call does not, and on 26 Aug a DNS blip
            # ended both loops mid-session. `alpha.broker.alpaca` now converts
            # transport failures into BrokerRefusal, which is the real fix; this
            # is the belt to that pair of braces, because a loop whose whole job
            # is to still be running in nine days may not die of an unforeseen
            # exception either. Silence has been read as health here before.
            consecutive_errors += 1
            log.exception("cycle failed (%d in a row); continuing", consecutive_errors)
            wait = min(300, 30 * consecutive_errors)
            beat.consecutive_errors = consecutive_errors
            beat.last_error = f"{type(exc).__name__}: {exc}"
            beat.backoff_until_utc = datetime.fromtimestamp(
                time.time() + wait, timezone.utc).isoformat()
            liveness.write(beat)
            time.sleep(wait)
        if args.once:
            # A single deliberate cycle is a DIAGNOSTIC, not a loop. Its
            # heartbeat must not outlive it: a `--once` run on `pead` on 27 Aug
            # left a receipt that made the next liveness report say
            # "pead DEAD -- the loop is gone", a false alarm printed beside two
            # real HEALTHY lines. A report with wrong entries is one people
            # learn to skim.
            liveness.retire(role)
            return 0
        time.sleep(60)


def _cycle(client, args, last: dict) -> int:
    """One pass of the schedule. Returns the consecutive-error count (0 = fine)."""
    if True:
        now = time.time()
        try:
            clock = client.clock()
            is_open = bool(clock.get("is_open"))
            try:  # minutes until the next open; the council step must not straddle the bell
                _no = datetime.fromisoformat(str(clock.get("next_open")))
                mins_to_open = (_no - datetime.now(_no.tzinfo)).total_seconds() / 60
            except (TypeError, ValueError):
                mins_to_open = 1e9
        except BrokerRefusal as exc:
            log.warning("clock unavailable: %s -- treating as closed", exc)
            is_open = False

        if is_open and now - last["exit"] >= args.exit_minutes * 60:
            _run("scripts.manage", live=args.live); last["exit"] = now
        et_hour = (datetime.now(timezone.utc).hour - 4) % 24
        if not is_open and 16 <= et_hour < 20 and now - last["autopsy"] >= 20 * 3600:
            # After the close: what won, what lost, why, and did the engine hold it.
            _run("scripts.daily_autopsy", live=False); last["autopsy"] = now
        if (getattr(args, "window_universe", False) and args.refresh_window_minutes
                and now - last.get("window", 0.0) >= args.refresh_window_minutes * 60):
            # The calendar moves: a name that reacts tomorrow is not in today's
            # receipt. Regenerated on a cadence rather than once at startup,
            # because this loop is meant to run for a week.
            _run("scripts.window_universe", "--json", live=False); last["window"] = now
        if now - last["candidates"] >= 6 * 3600:
            # The WHOLE market's recent printers through the one positive-t brain,
            # so an entry pass can see a $2B name that printed, not just the old fifteen.
            _run("scripts.candidates", "--sessions", "3", live=False); last["candidates"] = now
        if getattr(args, "council", False) and not is_open and mins_to_open > 60 and now - last["council"] >= 6 * 3600:
            # The council packets are what `council_vector` trades from. Run
            # after candidates so the printers list is fresh; --deep 2 = full
            # council (fact/expectations/cube/causal/skeptic/synthesis) on the
            # two most dislocated, light pass on the rest. Places nothing.
            # MEASURED 28 Aug: one LIGHT council is ~82s, a full one ~3-4 min,
            # so the first deploy's `--max 15 --deep 3` could never finish
            # inside 900s and was killed every time -- and it BLOCKS this loop
            # while it runs. Sized to ~12 min and gated to CLOSED hours, so an
            # exit never waits behind an LLM call.
            # Whole-universe overnight digest FIRST (East -> West, ~130 names,
            # ~6 LLM calls), so the council's four slots go to the digest's
            # ranking rather than to whoever printed last. Shadow; places nothing.
            _run("scripts.premarket_digest", live=False)
            _run("scripts.dislocation_scan", "--max", "4", "--deep", "2", live=False); last["council"] = now
        if is_open and getattr(args, "manage_only", False) and now - last["entry"] >= 3600:
            # Say it OUT LOUD, hourly. A legacy book that silently stopped
            # entering looks exactly like a book whose entry pass is broken, and
            # this repo has paid twice for an absence that read as a decision.
            log.info("MANAGE-ONLY: entry pass skipped by flag; exits, fills and marking continue. "
                     "This book can only get smaller.")
            last["entry"] = now
        if is_open and not getattr(args, "manage_only", False) \
                and now - last["entry"] >= args.entry_minutes * 60:
            extra: list[str] = ["--candidates"]
            if getattr(args, "window_universe", False):
                extra += ["--window-universe"]
            if args.brains is not None:
                extra += ["--brains", args.brains]
            if args.shadow is not None:
                extra += ["--shadow", args.shadow]
            if args.profile:
                extra += ["--profile", args.profile]
            if args.universe:
                extra += ["--universe", *args.universe]
            _run("scripts.run_pass", "--expiry", args.expiry, *extra, live=args.live); last["entry"] = now
            # EXITS IMMEDIATELY AFTER, not on the next tick. The entry pass has
            # just held this loop for ~6 minutes (measured median 368s), so the
            # five-minute exit cadence is already overdue by the time it returns
            # -- and waiting out the 60s sleep adds a minute to a stop that is
            # late for reasons that have nothing to do with the position.
            #
            # Deliberately sequential rather than concurrent: two processes
            # touching execution state is what broke the ledger hash chain on
            # 25 Aug, in six places. Exits get priority in TIME, never a
            # parallel writer.
            if _market_open(client):
                _run("scripts.manage", live=args.live); last["exit"] = time.time()
        if now - last["cf"] >= 3600:
            _run("scripts.counterfactual", "--record", live=False); last["cf"] = now
        if is_open and now - last["belief"] >= 3600:
            # Crowd vs chain, recorded hourly and graded once resolved -- the
            # belief-gap idea earns a trade from these grades, not from a prior.
            for sym in ("NVDA", "TSLA", "SPY"):
                # THROUGH `_run`, NOT `subprocess.call`.
                #
                # These three were the only steps calling subprocess directly,
                # so their exit codes reached nobody: not the failure counter,
                # not the heartbeat, not the log. `belief_vs_chain_grade` has
                # been crashing on EVERY cycle since its first success -- it
                # writes GRADES.json into the directory it globs and then reads
                # its own output back as an input -- and nothing ever said so.
                _run("scripts.belief_vs_chain", sym, "--expiry", args.expiry, live=False)
            _run("scripts.belief_vs_chain_grade", live=False)
            _run("scripts.belief_recorder", live=False)          # the velocity series
            last["belief"] = now
        if is_open and now - last["fill"] >= 900:
            _run("scripts.fill_audit", "--record", live=False); last["fill"] = now

        return 0


if __name__ == "__main__":
    sys.exit(main())
