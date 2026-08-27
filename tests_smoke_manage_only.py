"""Smoke checks for MANAGE-ONLY -- the legacy-book mode that may exit but never enter.
No keys, no network.  Run: python tests_smoke_manage_only.py

dev and exp1 are being wound down as PRE_UNITS_FIX books: they carry positions
opened under the pricing bug fixed on 27 Aug, so their exits and marks are still
wanted and their ENTRIES are not. A flag that quietly stopped prohibiting new
risk would put capital back to work in a book nobody is underwriting any more,
so the prohibition is asserted here rather than trusted.
"""
from __future__ import annotations

import sys
import types

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


import scripts.agent_loop as loop  # noqa: E402


class _Clock:
    """A broker that is always open, so nothing is skipped for the wrong reason."""
    def clock(self):
        return {"is_open": True}


def _args(**kw):
    base = dict(expiry="2026-09-04", live=True, entry_minutes=0, exit_minutes=0,
                once=False, brains=None, shadow=None, profile=None, universe=None,
                manage_only=False)
    base.update(kw)
    return types.SimpleNamespace(**base)


def _run_cycle(args):
    """Run one cycle with every outward call stubbed; return the modules invoked.

    `_cycle` reaches the outside world TWO ways -- `_run` for most modules and a
    bare `subprocess.call` for `belief_vs_chain`. Stubbing only the first is not
    enough: the first draft of this file did exactly that, and the test hit the
    live venue and appended 338 rows to state/belief_series.jsonl. A unit test
    that writes real state is a defect in the test, so both doors are shut here
    and `subprocess` is asserted absent from the recorded calls.
    """
    called: list[str] = []
    real_run = loop._run
    real_open = getattr(loop, "_market_open", None)
    real_call = loop.subprocess.call
    loop._run = lambda mod, *a, **k: called.append(mod)
    def _fake_call(argv, *a, **k):
        # Record the MODULE, not the tail of argv: `-m mod sym --expiry X` puts the
        # module fourth from the end and the first draft's argv[-3:] sliced it off,
        # so the recorded name could not be checked against anything.
        argv = [str(x) for x in argv]
        mod = argv[argv.index("-m") + 1] if "-m" in argv else argv[0]
        called.append("subprocess:" + mod)
        return 0
    loop.subprocess.call = _fake_call
    if real_open is not None:
        loop._market_open = lambda *a, **k: True
    try:
        last = {k: 0.0 for k in
                ("exit", "entry", "cf", "fill", "belief", "candidates", "autopsy")}
        loop._cycle(_Clock(), args, last)
    finally:
        loop._run = real_run
        loop.subprocess.call = real_call
        if real_open is not None:
            loop._market_open = real_open
    return called


SRC = open(loop.__file__, encoding="utf-8").read()

print("\n-- the flag exists and is off by default")
check("--manage-only is a declared flag", '"--manage-only"' in SRC)
check("default is False (a book keeps trading unless told otherwise)",
      _args().manage_only is False)

print("\n-- manage-only never reaches the entry pass")
normal = _run_cycle(_args(manage_only=False))
legacy = _run_cycle(_args(manage_only=True))
check("a normal cycle DOES run the entry pass", "scripts.run_pass" in normal,
      f"invoked: {normal}")
check("a manage-only cycle does NOT run the entry pass", "scripts.run_pass" not in legacy,
      f"invoked: {legacy}")

print("\n-- but it still manages what is already open")
check("exits still run", "scripts.manage" in legacy, f"invoked: {legacy}")
check("marking still runs", "scripts.counterfactual" in legacy, f"invoked: {legacy}")
_SAFE_SUBPROCESS = {"scripts.belief_vs_chain", "scripts.belief_vs_chain_grade",
                    "scripts.belief_recorder"}
_subs = {c.split(":", 1)[1] for c in normal + legacy if c.startswith("subprocess:")}
# WAS: `_subs and _subs <= _SAFE_SUBPROCESS` -- "if anything bypasses _run it
# must be one of these three research recorders". The three now go THROUGH _run,
# so nothing bypasses it and the set is empty. That is the stronger invariant and
# the test asserts it directly: their exit codes used to reach no counter, no
# heartbeat and no log, and belief_vs_chain_grade had been crashing on every
# cycle since its first success without anyone hearing about it.
check("NOTHING bypasses _run any more -- every step's exit code is counted",
      not _subs, f"bypassing _run: {sorted(_subs)}")
check("and the three research recorders are still invoked, via _run",
      _SAFE_SUBPROCESS <= set(normal),
      f"missing: {sorted(_SAFE_SUBPROCESS - set(normal))}")
check("no ENTRY-side subprocess exists in manage-only",
      not any("run_pass" in c for c in legacy), f"invoked: {legacy}")
check("manage-only is a strict SUBSET of a normal cycle",
      set(legacy) <= set(normal) | {"scripts.manage"},
      f"legacy-only extras: {set(legacy) - set(normal)}")

print("\n-- the prohibition is announced, not silent")

check("skipping an entry pass emits a log line",
      "MANAGE-ONLY" in SRC and "log.info" in SRC.split("MANAGE-ONLY")[0][-200:],
      "an absence that is never printed reads as a decision nobody made")

print("\nALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
