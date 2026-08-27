"""Run every smoke suite with the venue BLOCKED, and count the checks.

    python run_tests.py                # the only supported way to run the suite
    python run_tests.py -k chain       # only files whose name contains "chain"
    python run_tests.py --allow-venue  # deliberate, announced, for integration work

WHY A RUNNER AND NOT "just run the files"
=========================================
Every `tests_smoke_*.py` is a standalone script -- there is no pytest, no
conftest, and therefore no place a network guard could have lived. That is not
a stylistic gap: on 2026-08-27 a test spawned a CHILD process that hit the live
venue and wrote 338 rows into `state/belief_series.jsonl`. Once the competition
account is live, that class of accident writes into a judged record.

So the guard is `AAT_TEST_MODE=1`, set HERE, in the one place the suite is
started from. An env var is inherited by child processes; a monkeypatch is not,
and the failure above was precisely a child. `alpha.config.credentials()`
refuses while it is set, and that function is the only door to a venue header.

`--allow-venue` exists because integration checks are legitimate. It prints a
banner naming the account role, so a run that can reach the broker can never be
mistaken in a scrollback for an ordinary green suite.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
#: A check is an `  ok   <name>` line -- that IS the suites' shared convention and
#: the only one. A first cut parsed a trailing "N checks" summary that most files
#: never print, so the headline read 11 when the suite had run several hundred.
#: Counting the assertions themselves cannot drift from what actually ran.
_OK = re.compile(r"^\s*ok\s{2,}", re.M)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("-k", metavar="SUBSTR", help="only files whose name contains this")
    p.add_argument("--allow-venue", action="store_true",
                   help="do NOT block credentials (integration runs only)")
    args = p.parse_args()

    files = sorted(ROOT.glob("tests_smoke*.py"))
    if args.k:
        files = [f for f in files if args.k in f.name]
    if not files:
        print(f"no suites matched {args.k!r}")
        return 2

    env = dict(os.environ)
    if args.allow_venue:
        role = env.get("AAT_ACCOUNT_ROLE", "<unset>")
        print("=" * 72)
        print(f"  VENUE ALLOWED. AAT_ACCOUNT_ROLE={role}. Orders and writes are REAL.")
        print("=" * 72)
        env.pop("AAT_TEST_MODE", None)
    else:
        env["AAT_TEST_MODE"] = "1"

    total, failed, unknown = 0, [], []
    for f in files:
        r = subprocess.run([sys.executable, f.name], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=900)
        out = r.stdout + r.stderr
        n = len(_OK.findall(out))
        if n == 0:
            # Reported no `ok` lines. That can mean it asserts nothing OR that it
            # prints its own wording -- this cannot tell them apart, so it says
            # what it observed rather than diagnosing. tests_smoke_night.py was
            # the second case and a first draft libelled it as the first.
            unknown.append(f.name)
        total += n
        status = "ok  " if r.returncode == 0 else "FAIL"
        if r.returncode != 0:
            failed.append(f.name)
        print(f"{status} {f.name:38} {n:>4} checks")
        if r.returncode != 0:
            print("\n".join("      " + ln for ln in out.strip().splitlines()[-25:]))

    print("\n" + "=" * 72)
    print(f"{len(files)} suites, {total} checks"
          f"{'' if not unknown else f'  -- {len(unknown)} suite(s) reported no `ok` lines: {unknown}'}")
    if not args.allow_venue:
        print("venue BLOCKED for every suite and every child process (AAT_TEST_MODE=1)")
    print("ALL PASS" if not failed else f"{len(failed)} SUITE(S) FAILED: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
