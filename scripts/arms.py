"""ARMS -- what each paper account is FOR, what blocks it, and whether the live
ones are actually independent.

    python -m scripts.arms                 # the board: every arm, status, blocker
    python -m scripts.arms --independence  # measure effective N across LIVE arms
    python -m scripts.arms --json

Answers the question "should we open more paper accounts?" with a measurement
rather than a yes. More accounts are more data only when they disagree; this
prints whether ours do, and refuses to guess when the record is too short.
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request

from alpha import arms as arms_mod
from alpha import config


def _portfolio_returns(role: str, days: int = 60) -> tuple[list[float], str]:
    """Daily NAV returns for one role. Returns (returns, why_not) -- never a bare [].

    The empty list and the reason travel together on purpose. An arm that could
    not be read and an arm that has not traded produce the same `[]`, and a
    correlation computed over the arms that happened to answer is a correlation
    over a self-selected sample. "We could not look" must not be recorded as
    "there is nothing there".
    """
    try:
        creds = config.credentials(role)
    except config.CredentialRefusal as exc:
        return [], f"credentials refused: {str(exc).splitlines()[0][:90]}"
    url = (config.base_url() + "/v2/account/portfolio/history"
           f"?period={days}D&timeframe=1D&intraday_reporting=market_hours")
    req = urllib.request.Request(url, headers={**creds.headers, "accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        return [], f"HTTP {exc.code} from the broker"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return [], f"transport: {type(exc).__name__}"
    eq = [e for e in (data.get("equity") or []) if e]
    rets = [eq[i] / eq[i - 1] - 1.0 for i in range(1, len(eq)) if eq[i - 1]]
    return rets, "" if rets else "broker returned no non-zero equity points"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--independence", action="store_true",
                   help="measure effective N by NAV correlation across live arms")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    config.load_env()

    rows = arms_mod.readiness()

    if args.json and not args.independence:
        print(json.dumps(rows, indent=1))
        return 0

    print(f"{'role':14} {'status':10} {'alpha source':34} {'creds':6} blocked by")
    print("-" * 108)
    for r in rows:
        blk = r["blocked_by"]
        first = blk[0] if blk else ""
        print(f"{r['role']:14} {r['status']:10} {r['alpha_source']:34} "
              f"{'yes' if r['credentials_present'] else 'NO':6} {first[:44]}")
        for extra in blk[1:]:
            print(" " * 66 + extra[:44])
    print("-" * 108)
    live = [r for r in rows if r["status"] == "live"]
    seedable = [r for r in rows if r["can_seed"] and r["status"] == "proposed"]
    print(f"{len(live)} live, {len(seedable)} ready to seed, "
          f"{len(rows) - len(live) - len(seedable)} blocked.")
    if seedable:
        print("  ready to seed (ATTENDED -- see .claude/skills or the seed-a-lane discipline): "
              + ", ".join(r["role"] for r in seedable))
    need_creds = [r["role"] for r in rows if not r["credentials_present"]]
    if need_creds:
        print("\nTO ADD AN ACCOUNT (the Trading API cannot create one -- this is manual):")
        print("  1. Alpaca dashboard -> new PAPER account")
        print("  2. .env:  AAT_<ROLE>_KEY_ID=...   AAT_<ROLE>_SECRET_KEY=...")
        print("  3. re-run this command; the arm moves off 'no credentials'")
        print("  needed for: " + ", ".join(need_creds))

    if args.independence:
        print("\nINDEPENDENCE -- do the live arms actually disagree?")
        read = {r["role"]: _portfolio_returns(r["role"]) for r in live}
        unread = {k: why for k, (s, why) in read.items() if not s}
        for role, (s, why) in read.items():
            print(f"  {role:14} {len(s):>3} daily NAV observations" + (f"   [{why}]" if why else ""))
        if unread:
            print(f"  {len(unread)} of {len(read)} live arms could not be read. The independence "
                  "figure below, if any, covers only the ones that answered -- which is a "
                  "self-selected sample, not the book.")
            print("  NOTE: AAT_ACCOUNT_ROLE is set in .env and pins this process to ONE role by "
                  "design -- it is what every ledger stamp, book match and recovery score reads, "
                  "so credentials() refuses to hand out another role's keys rather than choose. "
                  "Reading every arm at once needs a read-only path that never touches the "
                  "ledger; until that exists this command reports one arm and says so.")
        verdict = arms_mod.effective_n({k: s for k, (s, _) in read.items()})
        if verdict.get("effective_n") is None:
            print(f"  CANNOT DETERMINE: {verdict['why']}")
        else:
            print(f"  effective N by NAV correlation: {verdict['effective_n']} "
                  f"across {verdict['arms']} arms over {verdict['n_obs']} sessions")
            print(f"  average pairwise rho {verdict['avg_rho']}   {verdict['pairwise_rho']}")
            print(f"  reference: {verdict['reference']}")
        if args.json:
            print(json.dumps(verdict, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
