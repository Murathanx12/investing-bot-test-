"""PRE-MARKET PASSES ARE OFF, and the switch is real code rather than a runbook line.

Murat, 2026-09-07: "we dont run premarket runs anymore, the more project
improves the more things we lose and gets missed."

WHY THIS FILE EXISTS AT ALL
===========================
`AAT_MANAGE_ONLY=1` sat in the runbook for days meaning exactly nothing, because
no line of code ever read it (`alpha/fleet.py` Mandate.manage_only docstring).
A switch that is only written down is not a switch. So the assertions below are
about the SCHEDULER's behaviour, not about the presence of a constant:

  1. the default is OFF,
  2. `--premarket` turns it back on,
  3. BOTH pre-open passes are gated on the same decision -- the digest and the
     opening auction, so one cannot be silently left running,
  4. the skip is LOGGED, because an absence that says nothing reads exactly like
     a pass that broke.
"""
import argparse
import inspect
import sys

from scripts import agent_loop

CHECKS = 0


def check(cond, label):
    global CHECKS
    CHECKS += 1
    if not cond:
        print(f"FAIL {label}")
        sys.exit(1)
    print(f"  ok  {label}")


def _args(**kw):
    ns = argparse.Namespace(premarket=False)
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


print("PRE-MARKET OFF")
check(agent_loop.PREMARKET_PASSES_ENABLED is False,
      "PREMARKET_PASSES_ENABLED defaults to False")
check(agent_loop._premarket_on(_args()) is False,
      "the scheduler's own decision is False by default")
check(agent_loop._premarket_on(_args(premarket=True)) is True,
      "--premarket overrides it for one run")
check(agent_loop._premarket_on(argparse.Namespace()) is False,
      "a namespace with no flag at all does not enable it")

src = inspect.getsource(agent_loop)

# The digest and the auction must BOTH be behind the one decision. Counting the
# call sites rather than eyeballing them, because the failure this guards is a
# future edit that adds a third pre-open pass and forgets the gate.
# `def _premarket_on(args)` contains the same substring, so the definition is
# excluded explicitly rather than by an off-by-one constant that would go stale
# the moment the helper is renamed.
call_sites = src.count("_premarket_on(args)") - src.count("def _premarket_on(args)")
check(call_sites == 2,
      f"exactly two pre-open call sites are gated (digest + opening auction); found {call_sites}")
# The CALL, not the first mention: the constant's own comment names the module
# too, and anchoring on that would measure the docstring instead of the code.
digest_at = src.index('_run("scripts.premarket_digest"')
gate_before_digest = src.rindex("_premarket_on(args)", 0, digest_at)
check(digest_at - gate_before_digest < 200,
      "the premarket digest call sits directly under its gate")
check("PRE-MARKET DIGEST SKIPPED" in src and "PRE-OPEN AUCTION SKIPPED" in src,
      "both skips are logged out loud, not silent")

# The flag exists on the parser, so the override is reachable from the command
# line and not only from a Python caller.
parser_src = inspect.getsource(agent_loop)
check('"--premarket"' in parser_src, "--premarket is a real CLI flag")

print(f"\n{CHECKS} checks passed")
