"""Are the paper loops actually running? -- LOOP_LIVENESS_v1

    python -m scripts.liveness                      # dev + exp1, exit 1 if any is not HEALTHY
    python -m scripts.liveness --expect dev         # only this one
    python -m scripts.liveness --quiet              # exit code only

Read this before believing a quiet log. On 26 Aug both loops died at 09:19 ET
and nothing said so until someone counted processes at 09:36 -- the log simply
stopped, which is what a slow market looks like. Session 9 lost loops the same
way and the cause went untraced for days.

This command is deliberately something a HUMAN or the day session runs, not a
daemon. A watchdog process on this machine can die of the same transient that
kills the loop, and then its silence means nothing either.

EXIT CODES
    0   every expected role is HEALTHY
    1   any role is DEAD, STALE, DEGRADED or UNKNOWN

UNKNOWN is a failure, not a pass. A probe that could not determine whether a
process exists has not established that it does.
"""

from __future__ import annotations

import argparse
import sys

from alpha import escalation, liveness


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--expect", nargs="*", default=["dev", "exp1"],
                   help="roles that SHOULD be running (default: dev exp1)")
    p.add_argument("--stale-after", type=float, default=liveness.STALE_AFTER_S,
                   help="seconds without a completed cycle before STALE")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    ok, lines = liveness.report(tuple(args.expect))
    # Repetition is evidence. A loop DEAD for one check and one DEAD for ten
    # print the same line otherwise, and the second is a standing defect.
    esc = escalation.observe(
        "loop_liveness", ok,
        "; ".join(l for l in lines if liveness.HEALTHY not in l)[:200])
    if not args.quiet:
        print("LOOP LIVENESS")
        for line in lines:
            print("  " + line)
        if ok:
            states = {l.split()[1] for l in lines
                      if len(l.split()) > 1 and l.split()[0] in args.expect}
            if states == {liveness.PRE_HEARTBEAT}:
                print("\nloops are RUNNING, but NOT confirmed by role -- they predate the "
                      "heartbeat.\nRestart to make this authoritative.")
            else:
                print("\nall expected loops HEALTHY")
        else:
            print(f"\n{esc.line()}")
            print("\nNOT HEALTHY -- see above. A stopped loop reads exactly like a quiet market,\n"
                  "so this is the only thing standing between an outage and a silent gap in the\n"
                  "forward record. Restart with the SAME --expiry the book was opened against.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
