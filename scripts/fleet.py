"""THE FLEET -- plan, env template, Railway commands, freshness check. See `alpha/fleet.py`.

    python -m scripts.fleet --plan
    python -m scripts.fleet --env-template >> .env          # then paste the six key pairs
    python -m scripts.fleet --railway thesis                 # commands for one role
    python -m scripts.fleet --railway all
    AAT_ACCOUNT_ROLE=thesis python -m scripts.fleet --check  # venue: fresh? $100k? 0 orders?
    python -m scripts.fleet --check-all                      # every role whose keys are in .env

`--check` reads the venue and places nothing. An account with ANY order of any
status is reported LEGACY (the rules make it ineligible as the judged account;
for a fleet role it is still usable, but the ledger must know its history did
not start at zero).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from alpha import config, fleet


def plan() -> None:
    print(f"{'role':<10}{'tier':<6}{'profile':<13}{'objective':<10}{'universe':<21}{'brains':<32}label")
    for r, m in fleet.FLEET.items():
        print(f"{r:<10}{m.tier:<6}{m.profile:<13}{(m.rank_objective or 'mode'):<10}{m.universe:<21}{','.join(m.brains):<32}{m.label}")
    print()
    for r, m in fleet.FLEET.items():
        print(f"[{r}] Q: {m.question}")
        if m.structure_kinds:
            print(f"      kinds: {','.join(m.structure_kinds)}")
        if m.caveat:
            print(f"      caveat: {m.caveat}")
    print(f"\nSAFE: {fleet.SAFE}   RISKY: {fleet.RISKY}")


def check(role: str) -> dict:
    from alpha.broker.alpaca import AlpacaPaper
    os.environ["AAT_ACCOUNT_ROLE"] = role
    try:
        creds = config.credentials(role)
    except config.CredentialRefusal as exc:
        return {"role": role, "state": "NO_KEYS", "why": str(exc)[:120]}
    client = AlpacaPaper(creds) if "creds" in AlpacaPaper.__init__.__code__.co_varnames else AlpacaPaper()
    acct = client._request("GET", "/v2/account")
    orders = client._request("GET", "/v2/orders", params={"status": "all", "limit": 500}) or []
    positions = client._request("GET", "/v2/positions") or []
    equity = float(acct.get("equity") or 0)
    fresh = (not orders) and (not positions) and abs(equity - 100_000.0) < 1.0
    return {"role": role, "state": "FRESH" if fresh else "LEGACY", "account": acct.get("account_number"),
            "equity": equity, "orders_any_status": len(orders), "positions": len(positions),
            "options_level": acct.get("options_approved_level"), "trading_blocked": acct.get("trading_blocked")}


def deploy(role: str, *, up: bool) -> None:
    """Create/refresh the Railway service for a role. Secrets come from the
    process environment (config.load_env), never from the command line echo."""
    import shutil
    import subprocess
    railway = shutil.which("railway") or shutil.which("railway.exe") or shutil.which("railway.cmd")
    if not railway:
        raise SystemExit("railway CLI not on PATH")
    m = fleet.FLEET[role]
    svc = f"aat-loop-{role}"
    env = fleet.env_for(m)
    pre = f"AAT_{role.upper()}"
    for k in (f"{pre}_KEY_ID", f"{pre}_SECRET_KEY", *fleet.SECRETS, "AAT_FEATHERLESS_API_KEY"):
        v = os.getenv(k, "")
        if v:
            env[k] = v
    if not env.get(f"{pre}_KEY_ID"):
        print(f"{role}: no {pre}_KEY_ID in the environment; not deploying")
        return

    def run(*cmd, ok_fail=False):
        r = subprocess.run([railway, *cmd], capture_output=True, text=True)
        line = (r.stdout + r.stderr).strip().splitlines()
        print(f"  $ railway {' '.join(c if not c.startswith('AAT_') else c.split('=')[0] + '=...' for c in cmd)[:110]}"
              + (f"  -> {line[-1][:100]}" if line else ""))
        if r.returncode and not ok_fail:
            raise SystemExit(f"railway {cmd[0]} failed for {role}")
        return r

    print(f"[{role}] {m.label}")
    run("add", "--service", svc, ok_fail=True)          # exists -> non-zero, fine
    run("service", svc)
    run("volume", "add", "-m", "/app/state", ok_fail=True)
    sets = []
    for k, v in env.items():
        sets += ["--set", f"{k}={v}"]
    run("variables", "--service", svc, "--skip-deploys", *sets)
    if up:
        run("up", "--service", svc, "-d")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--env-template", action="store_true")
    ap.add_argument("--railway", default=None, help="role or 'all'")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--check-all", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--deploy", default=None, help="role or 'all': create the Railway service, volume and variables (keys read from .env)")
    ap.add_argument("--up", action="store_true", help="with --deploy: also `railway up -d` (starts the LIVE loop)")
    args = ap.parse_args()
    if args.plan:
        plan()
    if args.env_template:
        print(fleet.env_template())
    if args.railway:
        roles = list(fleet.FLEET) if args.railway == "all" else [args.railway]
        for r in roles:
            print(f"# ---- {r} ({fleet.FLEET[r].tier}) ----")
            print(fleet.railway_commands(fleet.FLEET[r]))
            print()
    if args.deploy:
        config.load_env()
        roles = list(fleet.FLEET) if args.deploy == "all" else [args.deploy]
        for r in roles:
            deploy(r, up=args.up)
    if args.check or args.check_all:
        config.load_env()
        roles = list(fleet.FLEET) if args.check_all else [config.role()]
        rows = []
        for r in roles:
            try:
                rows.append(check(r))
            except Exception as exc:                                     # noqa: BLE001
                rows.append({"role": r, "state": "ERROR", "why": f"{type(exc).__name__}: {str(exc)[:120]}"})
        if args.json:
            print(json.dumps(rows, indent=1))
        else:
            for row in rows:
                print(json.dumps(row))
        bad = [r for r in rows if r["state"] == "ERROR"]
        return 1 if bad else 0
    if not any([args.plan, args.env_template, args.railway, args.check, args.check_all, args.deploy]):
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
