"""D3 -- WHAT THE TUESDAY RE-ARM WOULD ACTUALLY DO. Re-runnable, offline, read-only.

    python -m scripts.labor_d3_rearm_audit          # rewrite the receipt
    python -m scripts.labor_d3_rearm_audit --print  # show it, write nothing

WHY THIS EXISTS AS A SCRIPT (X10, 2026-09-07)
=============================================
`state/labor_day_lab_2026-09-07/D3_tuesday_rearm_audit.json` was produced by
hand on 2026-09-05 and then went stale in the way a hand-made receipt always
does: on 2026-09-06 hack2 was declared manage-only (`alpha/fleet.py`, commit
5875483), and the receipt still said

    hack2  ENTRY_STATE_AFTER_DEPLOY: ARMED   declared_manage_only: false

A receipt that disagrees with the code is worse than no receipt, because it is
the artefact a Tuesday morning reads to decide whether a book may enter. So the
half of the audit that is DERIVABLE is now derived, every time, from
`alpha.fleet.env_for()` -- the same function `scripts.fleet --deploy` uses to
set the variables, so this cannot drift from the deploy by construction.

THE HALF THAT IS NOT DERIVABLE SAYS SO
--------------------------------------
Two of the four possible disarms are Railway variables and are invisible to a
local process. This script does NOT shell out to `railway`: it carries the
previous receipt's live column forward VERBATIM, stamped with the timestamp it
was actually read at, and marks it `LIVE_NOT_RE_READ`. A carried-forward value
presented as fresh is exactly the failure this file was written to close.

WHAT IT REFUSES TO GUESS
------------------------
`ENTRY_STATE_TODAY` is a property of the running Railway services. It is copied
forward or reported CANNOT_DETERMINE. The column that is authoritative here is
`ENTRY_STATE_AFTER_DEPLOY`: what the next `scripts.fleet --deploy` WOULD set.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from alpha import fleet

REPO = Path(__file__).resolve().parent.parent
RECEIPT = REPO / "state" / "labor_day_lab_2026-09-07" / "D3_tuesday_rearm_audit.json"

#: The env var the runbook told an operator to set. Its whole story is that it
#: reads nothing -- so the audit DERIVES that rather than asserting it, and would
#: report the opposite the day somebody wires it up.
MANAGE_ONLY_ENV = "AAT_MANAGE_ONLY"


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                              text=True, timeout=30).stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def manage_only_env_readers() -> dict:
    """Every place `AAT_MANAGE_ONLY` is READ, as opposed to merely mentioned.

    A mention in a comment, a docstring or a caveat string is not a reader. A
    reader is `os.getenv("AAT_MANAGE_ONLY")` / `os.environ[...]` / `.get(...)`.
    Derived by scanning the tree, so this row changes the day the variable is
    actually wired up -- and a guard that can only ever print one answer is not
    a guard (`monday_gate_check`, weeks of `0/9 stamped [FAIL]`)."""
    read_rx = re.compile(
        r"(?:getenv|environ\.get|environ\[|os\.environ\.get)\s*\(?\s*['\"]" + MANAGE_ONLY_ENV)
    readers, mentions = [], []
    _self = Path(__file__).resolve()
    for path in sorted(REPO.rglob("*.py")):
        if any(part in (".git", "__pycache__", "node_modules") for part in path.parts):
            continue
        # THE SCANNER IS NOT EVIDENCE. Its own `read_rx` source line matches
        # `read_rx`, so the first run reported "READ by 1 site(s); it is no
        # longer inert" -- an audit that had found itself and would have told a
        # Tuesday operator the variable now works.
        if path.resolve() == _self:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if MANAGE_ONLY_ENV not in text:
            continue
        rel = path.relative_to(REPO).as_posix()
        for i, line in enumerate(text.splitlines(), 1):
            if MANAGE_ONLY_ENV not in line:
                continue
            (readers if read_rx.search(line) else mentions).append(f"{rel}:{i}")
    return {
        "env_var": MANAGE_ONLY_ENV,
        "readers": readers,
        "mentions_only": mentions,
        "verdict": ("INERT -- nothing reads it; setting it disarms nothing"
                    if not readers else
                    f"READ by {len(readers)} site(s); it is no longer inert"),
        "the_only_switch": ("alpha.fleet.Mandate.manage_only -> loop_args() -> "
                            "'--manage-only' in AAT_LOOP_ARGS -> scripts.agent_loop's "
                            "args.manage_only, which gates the ENTRY branch only"),
    }


def declared_rows() -> list[dict]:
    """What the next `scripts.fleet --deploy` would set, per role. Derived."""
    rows = []
    for role, m in fleet.FLEET.items():
        env = fleet.env_for(m)
        args = env.get("AAT_LOOP_ARGS", "")
        disarmed = "--manage-only" in args
        rows.append({
            "role": role,
            "service": f"aat-loop-{role}",
            "declared_manage_only": bool(m.manage_only),
            "post_deploy_has_manage_only_flag": disarmed,
            "ENTRY_STATE_AFTER_DEPLOY": "DISARMED" if disarmed else "ARMED",
            "deploy_sets_mandate_end_utc": env.get("AAT_MANDATE_END_UTC"),
            "deploy_sets_loop_expiry": env.get("AAT_LOOP_EXPIRY"),
            "deploy_sets_entry_style": env.get("AAT_ENTRY_STYLE"),
            "deploy_sets_loop_args": args,
            "declared_allow_short": bool(fleet.may_short(role)),
        })
    return rows


def build(previous: dict | None) -> dict:
    prev_roles = {r.get("role"): r for r in (previous or {}).get("roles", [])}
    prev_at = (previous or {}).get("at")
    rows = []
    changed = []
    for row in declared_rows():
        old = prev_roles.get(row["role"], {})
        # THE LIVE COLUMN IS CARRIED, NEVER RE-DERIVED. Copying it silently would
        # be the whole defect this script exists to close, so it is renamed on the
        # way in and every one of them carries the date it was really read.
        # READ FROM BOTH SCHEMAS. The first generation of this script read the
        # hand-made receipt's FLAT keys and wrote them NESTED under
        # LIVE_NOT_RE_READ -- so its own second run found nothing at the flat
        # names and quietly replaced a real 2026-09-05 reading with
        # CANNOT_DETERMINE. A migration that loses the column it was written to
        # preserve is worse than no migration; `carried` looks in the nested
        # place first, then the flat one, and only then gives up.
        carried = old.get("LIVE_NOT_RE_READ") or {}

        def _live(key: str):
            for src in (carried, old):
                if key in src and src[key] not in (None, ""):
                    return src[key]
            return "CANNOT_DETERMINE"

        row["LIVE_NOT_RE_READ"] = {
            "read_at": carried.get("read_at") or prev_at or "never",
            "ENTRY_STATE_TODAY": _live("ENTRY_STATE_TODAY"),
            "live_has_manage_only_flag": _live("live_has_manage_only_flag"),
            "live_mandate_end_utc": _live("live_mandate_end_utc"),
            "note": ("copied from the previous receipt; a local process cannot see a "
                     "Railway variable and this script deliberately does not shell out "
                     "to `railway`. Re-read with "
                     "`railway variables --service aat-loop-<role>` when it matters."),
        }
        was = old.get("ENTRY_STATE_AFTER_DEPLOY")
        if was and was != row["ENTRY_STATE_AFTER_DEPLOY"]:
            changed.append(f"{row['role']}: {was} -> {row['ENTRY_STATE_AFTER_DEPLOY']}")
        rows.append(row)

    armed = [r["role"] for r in rows if r["ENTRY_STATE_AFTER_DEPLOY"] == "ARMED"]
    disarmed = [r["role"] for r in rows if r["ENTRY_STATE_AFTER_DEPLOY"] == "DISARMED"]
    return {
        "receipt": "LABOR-D3-TUESDAY-REARM-AUDIT",
        "at": datetime.now(timezone.utc).isoformat(),
        "git_commit": _commit(),
        "producer": "scripts/labor_d3_rearm_audit.py (re-runnable; the 2026-09-05 "
                    "receipt was made by hand and went stale within a day)",
        "method": ("OFFLINE AND READ-ONLY. The ARMED/DISARMED column is DERIVED from "
                   "alpha.fleet.env_for() -- the same function `scripts.fleet --deploy` "
                   "uses -- so it cannot drift from the deploy. No network call, no "
                   "`railway` invocation, no venue. The live column is carried forward "
                   "from the previous receipt and labelled LIVE_NOT_RE_READ."),
        "headline": {
            "roles_armed_by_the_deploy": armed,
            "roles_disarmed_by_the_deploy": disarmed,
            "changed_since_previous_receipt": changed or ["(none)"],
            "previous_receipt_at": prev_at or "none on disk",
        },
        "manage_only_env": manage_only_env_readers(),
        "railway_project": (previous or {}).get("railway_project", "loving-elegance"),
        "non_fleet_services": (previous or {}).get("non_fleet_services", {}),
        "roles": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true", dest="show",
                    help="print the audit and write nothing")
    args = ap.parse_args()
    previous = None
    if RECEIPT.exists():
        try:
            previous = json.loads(RECEIPT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"previous receipt unreadable ({exc}); the live column will be "
                  f"CANNOT_DETERMINE rather than guessed")
    out = build(previous)
    for r in out["roles"]:
        print(f"  {r['role']}  {r['ENTRY_STATE_AFTER_DEPLOY']:<9}"
              f"declared_manage_only={str(r['declared_manage_only']):<5} "
              f"live(read {r['LIVE_NOT_RE_READ']['read_at'][:10]})="
              f"{r['LIVE_NOT_RE_READ']['ENTRY_STATE_TODAY']}")
    print(f"  changed since the previous receipt: "
          f"{out['headline']['changed_since_previous_receipt']}")
    print(f"  {MANAGE_ONLY_ENV}: {out['manage_only_env']['verdict']}")
    if args.show:
        return 0
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
    print(f"receipt: {RECEIPT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
