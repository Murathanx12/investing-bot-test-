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
import pathlib
import subprocess
import os
import sys

from alpha import config, fleet


ROOT = pathlib.Path(__file__).resolve().parent.parent

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
    # WHICH CODE IS UP THERE. `agent_loop._commit()` shells out to `git rev-parse`
    # and its docstring says a heartbeat that cannot name its build "explains an
    # outage as a mystery rather than as a deploy" -- but `railway up` TARS THE
    # WORKING DIRECTORY and .git is gitignored, so in the container that call has
    # always returned None. The deploy is the only process that knows the answer,
    # so it states it here, as a variable, next to every other variable it sets.
    # A dirty tree is stamped as such: deploying uncommitted code is allowed and
    # pretending it was the commit is not.
    try:
        sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                      cwd=str(ROOT), text=True, timeout=10).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"],
                                        cwd=str(ROOT), text=True, timeout=20).strip()
        env["AAT_BUILD_COMMIT"] = sha + ("+dirty" if dirty else "")
    except (OSError, subprocess.SubprocessError):
        env["AAT_BUILD_COMMIT"] = "UNKNOWN"

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
    # READ BACK. On 28 Aug a bulk --set returned 0 and left AAT_LOOP_ARGS at its
    # old value (hack6 ran without --council for two deploys); a single --set
    # then took. A variable that was not verified was not set.
    r = run("variables", "--service", svc, "--json", ok_fail=True)
    try:
        live_vars = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        live_vars = {}
    stale = [k for k, v in env.items() if not k.endswith("_KEY_ID") and not k.endswith("_SECRET_KEY")
             and k not in fleet.SECRETS and str(live_vars.get(k)) != str(v)]
    for k in stale:
        run("variables", "--service", svc, "--skip-deploys", "--set", f"{k}={env[k]}")
    if stale:
        print(f"  re-set {len(stale)} variable(s) that did not take on the bulk call: {stale}")
    if up:
        run("up", "--service", svc, "-d")


def overlap() -> None:
    """Which names is the fleet holding in more than one account, and how?

    28 Aug the basket book held twelve theme names in shares while the convex
    book held 5-DTE calls on the same names, and both were reported as
    independent selectors. `alpha/crossbook.py` refuses that going forward, but
    only from a process that can read the peers -- which on Railway is none of
    them. This is where the number lives, and it is a MEASUREMENT, not a gate:
    it changes nothing and refuses nothing.
    """
    from alpha import concentration, crossbook

    config.load_env()
    books: dict[str, dict[str, str]] = {}
    blind: list[str] = []
    for role in sorted(fleet.FLEET):
        peer = crossbook.open_peer(role)
        if peer is None:
            blind.append(role)
            continue
        try:
            rows = peer.positions()
        except Exception as exc:                                        # noqa: BLE001
            blind.append(f"{role} ({type(exc).__name__})")
            continue
        held: dict[str, str] = {}
        for pos in rows:
            sym = str(pos.get("symbol") or "").upper()
            under = concentration.underlying_of(sym)
            if not under:
                continue
            kind = "option" if (pos.get("asset_class") == "us_option" or sym != under) else "shares"
            held[under] = "both" if held.get(under, kind) != kind else kind
        books[role] = held

    by_name: dict[str, dict[str, str]] = {}
    for role, held in books.items():
        for sym, kind in held.items():
            by_name.setdefault(sym, {})[role] = kind

    shared = {s: v for s, v in by_name.items() if len(v) > 1}
    print("")
    print(f"FLEET CROSS-BOOK OVERLAP -- {len(books)} book(s) read"
          + (f", BLIND to {len(blind)}: {', '.join(blind)}" if blind else ""))
    print(f"{len(by_name)} distinct name(s) held; {len(shared)} held by more than one book")
    print("")
    if not by_name:
        print("  every readable book is flat.")
    for sym, who in sorted(shared.items(), key=lambda kv: -len(kv[1])):
        instruments = sorted(set(who.values()))
        flag = "  <-- ONE BET, TWO INSTRUMENTS" if len(instruments) > 1 else ""
        print(f"  {sym:<6} {len(who)} book(s): "
              + ", ".join(f"{r}={k}" for r, k in sorted(who.items())) + flag)
    solo = {s: v for s, v in by_name.items() if len(v) == 1}
    if solo:
        print("")
        print(f"  held by exactly one book ({len(solo)}): " + ", ".join(sorted(solo))[:200])
    if blind:
        print("")
        print("  NOTE: a blind book is not a flat book. The names above are the overlap")
        print("        among the books this process could read, and are a LOWER BOUND.")


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
    ap.add_argument("--overlap", action="store_true",
                    help="the FLEET's real cross-book overlap: which names more than one account holds, "
                         "and in which instruments. Runs where the keys are (locally); the loops on "
                         "Railway carry only their own pair and record CANNOT DETERMINE instead.")
    args = ap.parse_args()
    if args.overlap:
        overlap()
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
        # FAIL CLOSED. A NO_KEYS row, a blocked account or an options level
        # below 3 used to print and exit 0 -- a validator that cannot go red is
        # a broken gate. The last check before kickoff must be able to fail.
        bad = [r for r in rows if r["state"] in ("ERROR", "NO_KEYS") or r.get("trading_blocked")
               or (r.get("options_level") is not None and int(r["options_level"]) < 3)]
        for r in bad:
            print(f"FAIL {r['role']}: {r.get('why') or r}", file=sys.stderr)
        return 1 if bad else 0
    if not any([args.plan, args.env_template, args.railway, args.check, args.check_all,
                args.deploy, args.overlap]):
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
