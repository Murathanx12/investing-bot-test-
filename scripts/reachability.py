"""EXECUTION_REACHABILITY_AUDIT -- prove every guard lies on a real call path.

    python -m scripts.reachability            # report
    python -m scripts.reachability --strict   # exit 1 if any guard is unreachable

WHY THIS EXISTS
===============
`alpha/book_limits.py` described itself in its own docstring as "implemented,
tested, and called by NOTHING" while the book it was written to bound reached
**72.9% of equity in true max loss**. Replaying that book under the limits it
already had would have stopped it at five orders and 32.5%.

Nothing was broken. Every test passed. The module simply had no caller, and a
module with no caller is indistinguishable from a module that works -- from the
outside, from the test suite, and from a handoff.

That failure is **machine-detectable**, and this is the machine.

WHAT IT CHECKS
==============
Two questions, in order:

1. **Module reachability.** Is every module under `alpha/` imported, directly or
   transitively, from one of the ENTRY POINTS? An unimported module cannot
   possibly run.
2. **Guard reachability.** For every top-level function whose NAME implies it
   refuses something -- gate, limit, refuse, admit, verify, check, guard, cap,
   block, kill, quarantine, invariant, policy -- is it called anywhere outside
   its own module and its own tests?

A guard called only by its test is the exact shape of the `book_limits` bug: the
test proves the logic and says nothing about whether the logic runs.

WHAT IT DELIBERATELY DOES NOT DO
================================
It does not resolve dynamic dispatch, `getattr`, registries or string-keyed
lookup. So it can produce FALSE ALARMS on things that are genuinely reached
through a table -- `alpha/brains/__init__.py` maps names to callables, and
`sources/registry.py` does the same.

That direction of error is the right one: a false alarm costs a minute of
reading, and the failure it exists to catch cost a book. Anything intentionally
reached dynamically goes in `DYNAMIC` below **with the mechanism named**, so the
exemption is an argument rather than a silence.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: The processes that actually run. Anything not reachable from one of these is
#: not part of the agent, whatever else it may be.
ENTRY_POINTS = (
    "scripts/agent_loop.py",
    "scripts/run_pass.py",
    "scripts/manage.py",
    "scripts/preflight.py",
    "scripts/reconcile.py",
)

#: Name fragments that mean "this thing refuses something". A function called
#: `admit` or `verify_chain` that nobody calls is a guard that does not guard.
GUARD_WORDS = ("gate", "limit", "refuse", "refusal", "admit", "verify", "guard",
               "block", "kill", "quarantine", "invariant", "policy", "cap",
               "latch", "check", "validate", "enforce", "deny", "reject")

#: Names whose "unreachable" verdict is a false alarm, and the MECHANISM that
#: reaches them. An entry here is an argument; an entry with no mechanism is a
#: silence and should be deleted instead.
DYNAMIC: dict[str, str] = {
    "alpha.brains": "brains/__init__.BRAINS maps names to callables; run_pass --brains selects by string",
    "alpha.sources.registry": "sources are looked up by string key at call time",
}


#: Guards that are uncalled ON PURPOSE, and the argument for it. Same discipline
#: as DYNAMIC: an entry here must carry a REASON, so a reader can tell "we
#: decided this" from "nobody noticed". An entry with no reason is a silence and
#: should be deleted rather than kept.
DELIBERATELY_UNCALLED: dict[str, str] = {
    "alpha.book_limits.would_admit": (
        "a bool convenience. Its own docstring says whether a breach refuses, warns or "
        "resizes is a POLICY decision belonging at an attended call site -- so the module "
        "exposes it and refuses to make that choice on the caller's behalf. book_limits "
        "itself IS enforced: admission.py calls evaluate() and refusing()."),
    "alpha.psychohistory.checkpoints_due": "psychohistory is shadow-only and pre-competition",
    "alpha.psychohistory.validate_compiled": "psychohistory is shadow-only and pre-competition",
}


def _module_name(p: Path) -> str:
    """Dotted name, with `__init__` stripped to the PACKAGE name.

    Without this strip, `alpha/brains/__init__.py` is called
    `alpha.brains.__init__` and `from alpha import brains` never resolves to it,
    so every module a package re-exports reads as an orphan. The first run of
    this audit reported 22 orphans and most of them were this bug -- which is
    the correct order of events: distrust the instrument before the result.
    """
    rel = p.relative_to(ROOT).with_suffix("")
    parts = [x for x in rel.parts if x != "__init__"]
    return ".".join(parts)


def _imports(tree: ast.AST) -> set[str]:
    """Every module this one depends on -- including the ones it SPAWNS.

    `scripts/agent_loop.py` is the process that actually runs, and it reaches
    most of the system through `_run("scripts.fill_audit", ...)` -- a subprocess
    launched by module NAME, as a string literal. An import walker cannot follow
    that, so the first version of this audit reported `alpha.fills` as an orphan
    when it runs every 300 seconds in production.

    A false alarm here is not free. This audit exists because the repo's house
    failure is a guard nobody calls, and a report with wrong entries in it is one
    people learn to skim -- which is how the guard goes unnoticed the next time.
    So a string constant naming a module in this repo counts as an edge.
    """
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value
            if (v.startswith("scripts.") or v.startswith("alpha.")) and " " not in v:
                out.add(v)
    return out


def _called_names(tree: ast.AST) -> set[str]:
    """Every name that appears in a call position, bare or attribute."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                out.add(f.id)
            elif isinstance(f, ast.Attribute):
                out.add(f.attr)
    # A guard passed as a value (a callback, a table entry) counts as reached.
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            out.add(node.attr)
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--strict", action="store_true", help="exit 1 on any unreachable guard")
    args = p.parse_args()

    py = sorted(set(ROOT.glob("alpha/**/*.py")) | set(ROOT.glob("scripts/*.py")))
    trees: dict[str, ast.AST] = {}
    for f in py:
        if f.name == "__pycache__":
            continue
        try:
            trees[_module_name(f)] = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            print(f"UNPARSEABLE {f}: {exc}")
            return 2

    # ---------------------------------------------------------------- modules
    edges = {m: {i for i in _imports(t) if i.startswith(("alpha", "scripts"))}
             for m, t in trees.items()}
    reached: set[str] = set()
    stack = [_module_name(ROOT / e) for e in ENTRY_POINTS]
    while stack:
        cur = stack.pop()
        if cur in reached:
            continue
        reached.add(cur)
        for dep in edges.get(cur, ()):  # `from alpha.x import y` yields both forms
            for cand in (dep, dep.rsplit(".", 1)[0]):
                if cand in trees and cand not in reached:
                    stack.append(cand)

    alpha_mods = sorted(m for m in trees if m.startswith("alpha"))
    orphan_mods = [m for m in alpha_mods if m not in reached and m not in DYNAMIC]

    print("MODULE REACHABILITY -- from " + ", ".join(ENTRY_POINTS))
    print(f"  {len(alpha_mods)} alpha modules, {len(alpha_mods) - len(orphan_mods)} reachable")
    for m in orphan_mods:
        print(f"  ORPHAN  {m}   imported by no entry point")
    if not orphan_mods:
        print("  every alpha module is reachable from a process that runs")

    # ----------------------------------------------------------------- guards
    # Who calls what, excluding each module's own body and the test files.
    external_calls: dict[str, set[str]] = {}
    for m, t in trees.items():
        for name in _called_names(t):
            external_calls.setdefault(name, set()).add(m)
    for f in sorted(ROOT.glob("tests_smoke*.py")):
        t = ast.parse(f.read_text(encoding="utf-8"))
        for name in _called_names(t):
            external_calls.setdefault(name, set()).add(f"TEST:{f.name}")

    findings = []
    for m, t in trees.items():
        if not m.startswith("alpha"):
            continue
        for node in t.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name = node.name
            if name.startswith("_"):
                continue
            if not any(w in name.lower() for w in GUARD_WORDS):
                continue
            callers = external_calls.get(name, set())
            non_self = {c for c in callers if c != m}
            prod = {c for c in non_self if not c.startswith("TEST:")}
            tests = {c for c in non_self if c.startswith("TEST:")}
            # A guard called from INSIDE its own reachable module is reached.
            # `alpha/arms.readiness()` calls `validate()` and `scripts/arms.py`
            # calls `readiness()`, so `validate` runs in production -- but no
            # external module names it, and the first version of this audit
            # reported it UNCALLED. That is a false alarm on a guard that works,
            # printed beside real ones, which is precisely how a report gets
            # skimmed.
            same_module = name in _called_names(t) and m in reached
            if not prod and not same_module and f"{m}.{name}" not in DELIBERATELY_UNCALLED:
                findings.append((m, name, sorted(tests), m in reached))

    print("\nGUARD REACHABILITY -- functions whose NAME implies a refusal")
    if not findings:
        print("  every named guard is called from production code")
    for m, name, tests, mod_reached in findings:
        why = ("called ONLY by its own tests" if tests else "called by NOTHING, anywhere")
        print(f"  UNCALLED  {m}.{name}()  -- {why}")
        if tests:
            print(f"            tests: {', '.join(t[5:] for t in tests)}")
        if not mod_reached:
            print("            (and its module is itself unreachable)")

    bad = len(orphan_mods) + len(findings)
    print(f"\n{len(orphan_mods)} orphan module(s), {len(findings)} uncalled guard(s)")
    if bad and args.strict:
        print("STRICT: a guard that nothing calls is not a strict guard, it is a comment.")
    return 1 if (bad and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
