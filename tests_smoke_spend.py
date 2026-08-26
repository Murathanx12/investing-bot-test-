"""A paid call must name the decision it can change, or it does not happen."""
import sys

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha.sources.http import SourceRefusal
from alpha.spend import SpendRefusal, justify, llm_post, record, summary

GOOD = ("Decides whether the condor is built or refused at tonight's print, and at "
        "what size if built.")

print("\n-- the gate")

check("a real justification passes", justify(GOOD).startswith("Decides"))

for bad, why in [("", "absent"), ("research", "too short"), ("context", "too short"),
                 ("analysis of the NVDA earnings print and its supply chain implications",
                  "long enough but names NO DECISION")]:
    try:
        justify(bad, caller="t")
        check(f"refused: {why}", False, repr(bad[:40]))
    except SpendRefusal as exc:
        check(f"refused: {why}", True, str(exc)[:58])

try:
    justify("", caller="psychohistory.compile")
    check("the refusal names the caller so the site is findable", False)
except SpendRefusal as exc:
    check("the refusal names the caller so the site is findable",
          "(psychohistory.compile)" in str(exc), str(exc)[:52])

print("\n-- it must not turn a refusal into a crash")

check("SpendRefusal IS a SourceRefusal, so every existing handler already covers it",
      issubclass(SpendRefusal, SourceRefusal))
try:
    raise SpendRefusal("x")
except SourceRefusal:
    check("catching SourceRefusal catches it", True)
except Exception:
    check("catching SourceRefusal catches it", False)

print("\n-- the gate runs BEFORE the request, so a refused call costs nothing")

called = []


def _boom(*a, **k):
    called.append(1)
    raise AssertionError("the network must not be reached on a refused call")


import alpha.spend as spend_mod

spend_mod.post_json = _boom
try:
    llm_post("https://example.invalid", {"model": "m"}, why="nope", caller="t")
    check("a bad justification never reaches the network", False)
except SpendRefusal:
    check("a bad justification never reaches the network", not called)

spend_mod.post_json = lambda url, body, headers=None, timeout=90.0: (
    {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}, 1.25)
data, dt = llm_post("https://example.invalid", {"model": "deepseek-chat"},
                    why=GOOD, caller="tests.smoke")
check("a justified call goes through and returns the payload", data["usage"]["prompt_tokens"] == 10)

s = summary()
check("the ledger records the call", s["calls"] >= 1 and "tests.smoke" in s["by_caller"],
      f"calls={s['calls']}")
check("the ledger keeps the REASON, not just the cost",
      GOOD in s["by_caller"]["tests.smoke"]["reasons"])
check("the ledger says our telemetry is not the economic truth",
      "provider's balance" in s["note"])

print("\n-- every live call site carries one")

import inspect

import alpha.narrative.extract as nx
import alpha.psychohistory as ph
import alpha.state_change as sc
import scripts.daily_autopsy as da

for mod in (ph, sc, nx, da):
    src = inspect.getsource(mod)
    name = mod.__name__
    check(f"{name} routes through llm_post", "llm_post(" in src)
    check(f"{name} no longer calls post_json directly", "post_json(" not in src)
    # and the justification it carries must itself pass the gate
    import re
    m = re.search(r'why=\((.*?)\)\)', src, re.S)
    if m:
        text = " ".join(re.findall(r'"([^"]*)"', m.group(1)))
        try:
            justify(text, caller=name)
            check(f"{name}'s own justification passes the gate", True, text[:46])
        except SpendRefusal as exc:
            check(f"{name}'s own justification passes the gate", False, str(exc)[:60])

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("ALL PASS")
