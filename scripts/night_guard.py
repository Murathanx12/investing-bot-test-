"""NIGHT_CONFLICT_GUARD -- night discovers, day promotes, execution never self-mutates.

    python -m scripts.night_guard            # static: every scripts/night_*.py obeys the boundary
    python -m scripts.night_guard --range d48416a..HEAD   # a night commit range touches only night paths

The running paper loops (`scripts.agent_loop`) import `alpha/` and write the
execution state files. Night research may READ anything and WRITE only
`state/night_shadow/`, `docs/night/`, `scripts/night_*.py`, `tests_smoke_night.py`.
A night script that imports the execution surface, or a night commit that
touches it, FAILS here -- a boundary that lives in a paragraph is not one.
"""
from __future__ import annotations

import argparse, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NIGHT_WRITE_PREFIXES = ("state/night_shadow/", "docs/night/", "scripts/night_", "tests_smoke_night.py", ".gitignore",
                        "docs/HANDOFF.md")
FORBIDDEN_IMPORTS = ("alpha.ledger", "alpha.liveness", "alpha.book", "alpha.runner", "alpha.fills", "alpha.admission", "alpha.arbiter",
                     "alpha.recovery", "alpha.exits", "alpha.engine", "scripts.agent_loop", "scripts.run_pass",
                     "scripts.manage")
#: read-only market data through the broker client is allowed ONLY here
BROKER_ALLOWLIST = {"scripts/night_bars.py"}
EXECUTION_STATE = re.compile(r"state/(decisions|fills|forecasts|ledger|book|positions|orders|candidates|cards|"
                             r"psychohistory\.jsonl|belief_series|autopsy|event_grade|universe|liveness)")


def static_check() -> list[str]:
    errs = []
    for f in sorted(ROOT.glob("scripts/night_*.py")):
        rel = f.relative_to(ROOT).as_posix()
        txt = f.read_text(encoding="utf-8")
        for imp in FORBIDDEN_IMPORTS:
            if re.search(rf"^\s*(from|import)\s+{re.escape(imp)}\b", txt, re.M):
                errs.append(f"{rel}: imports {imp}")
        if rel not in BROKER_ALLOWLIST and re.search(r"^\s*(from|import)\s+alpha\.broker", txt, re.M):
            errs.append(f"{rel}: imports alpha.broker (only night_bars may, read-only)")
        for m in EXECUTION_STATE.finditer(txt):
            line = txt[:m.start()].count("\n") + 1
            # reading is fine; writing is not -- flag any write verb on the same line
            ln = txt.splitlines()[line - 1]
            if re.search(r"write_text|open\([^)]*['\"][wa]|\.dump|to_json|unlink|rename|shutil", ln):
                errs.append(f"{rel}:{line}: writes execution state {m.group(0)}")
    return errs


def range_check(rng: str) -> list[str]:
    out = subprocess.run(["git", "diff", "--name-only", rng], cwd=ROOT, capture_output=True, text=True, check=True)
    return [f"night commit touches {p}" for p in out.stdout.split()
            if not p.startswith(NIGHT_WRITE_PREFIXES) and not p.startswith(("state/night_shadow", "docs/night"))]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--range")
    a = p.parse_args()
    errs = static_check() + (range_check(a.range) if a.range else [])
    for e in errs:
        print("NIGHT_CONFLICT_GUARD FAIL:", e)
    print("NIGHT_CONFLICT_GUARD:", "PASS" if not errs else f"{len(errs)} violation(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
