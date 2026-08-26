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
import subprocess
import sys
import time
from datetime import datetime, timezone

from alpha import config
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal

log = logging.getLogger("loop")


#: A pass that runs longer than this is killed and logged. The loop is
#: sequential, so a 40-minute entry pass would starve the five-minute EXIT pass
#: -- and exits are the one job that must never wait on an LLM call.
TIMEOUTS_S = {"scripts.run_pass": 1500, "scripts.manage": 300, "scripts.counterfactual": 600, "scripts.candidates": 900, "scripts.daily_autopsy": 900,
              "scripts.fill_audit": 300}


def _run(mod: str, *args: str, live: bool) -> int:
    cmd = [sys.executable, "-m", mod, *args] + (["--live"] if live else [])
    log.info("run %s", " ".join(cmd[2:]))
    try:
        return subprocess.call(cmd, timeout=TIMEOUTS_S.get(mod, 900))
    except subprocess.TimeoutExpired:
        log.error("%s exceeded %ss and was killed; the next cycle re-reads the venue", mod, TIMEOUTS_S.get(mod, 900))
        return 124


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
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    config.load_env()
    client = AlpacaPaper()

    last = {"exit": 0.0, "entry": 0.0, "cf": 0.0, "fill": 0.0, "belief": 0.0, "candidates": 0.0, "autopsy": 0.0}
    consecutive_errors = 0
    while True:
        try:
            consecutive_errors = _cycle(client, args, last)
        except Exception:
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
            time.sleep(min(300, 30 * consecutive_errors))
        if args.once:
            return 0
        time.sleep(60)


def _cycle(client, args, last: dict) -> int:
    """One pass of the schedule. Returns the consecutive-error count (0 = fine)."""
    if True:
        now = time.time()
        try:
            clock = client.clock()
            is_open = bool(clock.get("is_open"))
        except BrokerRefusal as exc:
            log.warning("clock unavailable: %s -- treating as closed", exc)
            is_open = False

        if is_open and now - last["exit"] >= args.exit_minutes * 60:
            _run("scripts.manage", live=args.live); last["exit"] = now
        et_hour = (datetime.now(timezone.utc).hour - 4) % 24
        if not is_open and 16 <= et_hour < 20 and now - last["autopsy"] >= 20 * 3600:
            # After the close: what won, what lost, why, and did the engine hold it.
            _run("scripts.daily_autopsy", live=False); last["autopsy"] = now
        if now - last["candidates"] >= 6 * 3600:
            # The WHOLE market's recent printers through the one positive-t brain,
            # so an entry pass can see a $2B name that printed, not just the old fifteen.
            _run("scripts.candidates", "--sessions", "3", live=False); last["candidates"] = now
        if is_open and now - last["entry"] >= args.entry_minutes * 60:
            extra: list[str] = ["--candidates"]
            if args.brains is not None:
                extra += ["--brains", args.brains]
            if args.shadow is not None:
                extra += ["--shadow", args.shadow]
            if args.profile:
                extra += ["--profile", args.profile]
            if args.universe:
                extra += ["--universe", *args.universe]
            _run("scripts.run_pass", "--expiry", args.expiry, *extra, live=args.live); last["entry"] = now
        if now - last["cf"] >= 3600:
            _run("scripts.counterfactual", "--record", live=False); last["cf"] = now
        if is_open and now - last["belief"] >= 3600:
            # Crowd vs chain, recorded hourly and graded once resolved -- the
            # belief-gap idea earns a trade from these grades, not from a prior.
            for sym in ("NVDA", "TSLA", "SPY"):
                subprocess.call([sys.executable, "-m", "scripts.belief_vs_chain", sym, "--expiry", args.expiry])
            subprocess.call([sys.executable, "-m", "scripts.belief_vs_chain_grade"])
            subprocess.call([sys.executable, "-m", "scripts.belief_recorder"])   # the velocity series
            last["belief"] = now
        if is_open and now - last["fill"] >= 900:
            _run("scripts.fill_audit", "--record", live=False); last["fill"] = now

        return 0


if __name__ == "__main__":
    sys.exit(main())
