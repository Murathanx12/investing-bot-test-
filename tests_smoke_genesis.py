"""COMPETITION_ACCOUNT_GENESIS_v1 -- replayed against the accounts that exist.

Every account number in here was read from the venue on 2026-08-27 by
`python -m scripts.accounts`. The test is not "does genesis have rules" -- it is
"would the judged role, pointed at the real dev book, be refused".

No network: a fake client returns the states we measured.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

fails: list[str] = []
ran = 0


def check(name: str, cond: bool, why: str = "") -> None:
    global ran
    ran += 1
    if cond:
        print(f"  ok   {name}")
    else:
        fails.append(name)
        print(f"  FAIL {name}  {why}")


print("competition account genesis")

_tmp = tempfile.mkdtemp(prefix="aat_genesis_")
os.environ["AAT_LEDGER_DIR"] = _tmp

from alpha import genesis                                   # noqa: E402  (after env)

genesis.STATE_DIR = Path(_tmp)


class FakeClient:
    def __init__(self, number, equity, positions=0, orders=0, options=3, blocked=False):
        self._n, self._e, self._p, self._o = number, equity, positions, orders
        self._opt, self._blocked = options, blocked
        self.order_status_asked = None

    def account(self):
        a = {"account_number": self._n, "equity": self._e, "status": "ACTIVE",
             "trading_blocked": self._blocked}
        if self._opt is not None:
            a["options_trading_level"] = self._opt
        return a

    def positions(self):
        return [{"symbol": "X"}] * self._p

    def orders(self, status="open", limit=200):
        self.order_status_asked = status
        return [{"id": str(i)} for i in range(self._o)]


RULES = Path(_tmp) / "rules.md"
RULES.write_text("fresh $100,000 account; options required; Trading API + MCP or CLI\n")


def freeze(client, role="competition", **kw):
    return genesis.freeze(client, role=role, rules_snapshot=RULES, **kw)


def refuses(client, role="competition", **kw):
    try:
        freeze(client, role=role, **kw)
        return None
    except genesis.GenesisRefusal as exc:
        return str(exc)


# --- the accounts that actually exist ---------------------------------------
dev = refuses(FakeClient("PA32Q5IW7TAS", 84888.33, positions=8, orders=27))
check("the dev book (PA32Q5IW7TAS, -15.1%) is REFUSED as the judged account",
      dev is not None and "DENYLISTED" in dev, str(dev))
check("and the refusal names WHY it is legacy, not just that it is",
      dev is not None and "dev" in dev and "27 orders" in dev)

exp1 = refuses(FakeClient("PA3AOJPJTSBW", 95879.66, positions=8, orders=16))
check("exp1 is REFUSED", exp1 is not None and "DENYLISTED" in exp1, str(exp1))

# `market` is the load-bearing case: $100,000.00 exactly, ZERO positions, and one
# OPG order that expired unfilled. Under `status=open` it reads as pristine.
mkt = refuses(FakeClient("PA3I7VTCC0BM", 100000.00, positions=0, orders=1))
check("the market benchmark ($100,000.00, 0 positions) is still REFUSED",
      mkt is not None and "DENYLISTED" in mkt, str(mkt))

pead = refuses(FakeClient("PA3LY4QK3A6A", 100000.00, positions=0, orders=0))
check("a CLEAN $100k account that is a declared arm is REFUSED",
      pead is not None and "DENYLISTED" in pead,
      "reusing a declared arm's account collapses the independence measurement")

check("every denied account states its reason",
      all(len(v) > 40 for v in genesis.DENIED_ACCOUNTS.values())
      and len(genesis.DENIED_ACCOUNTS) >= 4)

# --- the state rules --------------------------------------------------------
check("a live (non-PA) account is REFUSED",
      (r := refuses(FakeClient("123456789", 100000.0))) is not None and "paper" in r, str(r))

check("$99,999.99 is REFUSED -- the rule is exact, not approximate",
      (r := refuses(FakeClient("PANEWFRESH01", 99999.99))) is not None
      and "exactly" in r, str(r))

check("a fresh account holding a position is REFUSED",
      (r := refuses(FakeClient("PANEWFRESH02", 100000.0, positions=1))) is not None
      and "Not new" in r, str(r))

check("a fresh account with ONE order of any status is REFUSED",
      (r := refuses(FakeClient("PANEWFRESH03", 100000.0, orders=1))) is not None
      and "any status" in r, str(r))

# The exact false-clean this exists for: `orders(status="open")` would return []
# for an expired OPG order. genesis must ask for ALL.
probe = FakeClient("PANEWFRESH04", 100000.0)
freeze(probe)
check("genesis asks the venue for orders of ANY status, not just open",
      probe.order_status_asked == "all",
      f"asked for status={probe.order_status_asked!r} -- an expired OPG order would read as clean")

# --- OPTIONS PERMISSION: the track is called "Options Alpha Agents" --------
# A fresh Alpaca paper account is not guaranteed to have options enabled, and an
# account that cannot buy a call fails the requirement on day one -- SILENTLY, as
# a stream of broker rejections that read like ordinary refusals.
check("options level 0 is REFUSED",
      (r := refuses(FakeClient("PAOPT000000A", 100000.0, options=0))) is not None
      and "options level 0" in r, str(r))
check("  and the refusal says it would fail SILENTLY",
      r is not None and "SILENTLY" in r and "read like ordinary refusals" in r)
check("level 1 is REFUSED too",
      refuses(FakeClient("PAOPT000001A", 100000.0, options=1)) is not None)
# NOTE: a genesis record already exists by this point in the file, so a valid
# account is refused by the ONE-TIME rule. These assert the refusal is not about
# OPTIONS, which is the thing under test -- asserting `is None` would silently
# pass for the wrong reason the day the one-time rule changes.
_ok2 = refuses(FakeClient("PAOPT000002A", 100000.0, options=2)) or ""
check("level 2 is ACCEPTED -- enough to buy a call",
      "options level" not in _ok2, _ok2[:90])

# The subtle one, and the direction that matters: an account object with NO
# options field tells us nothing. Treating silence as level 0 would refuse a
# perfectly good account on an absence.
_okN = refuses(FakeClient("PAOPT00NONE1", 100000.0, options=None)) or ""
check("a MISSING options field is not read as level 0",
      "options level" not in _okN,
      f"None is not zero; silence is not evidence -- got {_okN[:80]}")
check("  and options_level() returns None rather than 0 for it",
      genesis.options_level({"account_number": "X"}) is None)
check("  while a present level is parsed",
      genesis.options_level({"options_trading_level": "2"}) == 2,
      "the venue returns it as a string in some responses")

check("trading_blocked is REFUSED whatever the options level",
      (r := refuses(FakeClient("PABLOCKED001", 100000.0, options=3, blocked=True))) is not None
      and "trading_blocked" in r, str(r))

check("the floor is 2 and the full level is 3",
      genesis.MIN_OPTIONS_LEVEL == 2 and genesis.FULL_OPTIONS_LEVEL == 3)

# --- the record -------------------------------------------------------------
rec = json.loads(genesis.path("competition").read_text())
for field in ("account_number", "frozen_at_utc", "starting_equity", "rules_snapshot_sha256",
              "code_commit", "genesis_sha256", "competition", "options_level"):
    check(f"the record carries {field}", field in rec and rec[field] not in (None, ""))

check("the record's hash recomputes",
      genesis.load("competition").digest() == rec["genesis_sha256"])

check("re-freezing over an existing record is REFUSED",
      (r := refuses(FakeClient("PANEWFRESH05", 100000.0))) is not None
      and "already frozen" in r, str(r))

check("freezing genesis for a NON-judged role is REFUSED",
      (r := refuses(FakeClient("PANEWFRESH06", 100000.0), role="dev")) is not None
      and "may only be frozen" in r, str(r))

# --- verify catches a role re-pointed at another account --------------------
ok, lines = genesis.verify(FakeClient("PA32Q5IW7TAS", 84888.33, 8, 27), role="competition")
check("verify REFUSES when the judged role resolves to a different account",
      not ok and any("ACCOUNT MISMATCH" in ln for ln in lines), str(lines))
check("and it also names the denylist hit", any("DENYLISTED" in ln for ln in lines))

ok2, lines2 = genesis.verify(FakeClient("PANEWFRESH04", 100000.0), role="competition")
check("verify PASSES on the account it froze", ok2, str(lines2))

genesis.path("competition").unlink()
ok3, lines3 = genesis.verify(FakeClient("PANEWFRESH04", 100000.0), role="competition")
check("a MISSING record is a refusal, not a pass",
      not ok3 and "NO GENESIS RECORD" in lines3[0], str(lines3))

# --- and it must be WIRED, not merely written -------------------------------
import inspect                                              # noqa: E402

src_pre = Path("scripts/preflight.py").read_text(encoding="utf-8")
check("preflight imports genesis", "genesis" in src_pre)
check("preflight REFUSES (returns 1) on a denylisted judged account",
      "DENYLISTED" in src_pre and "return 1" in src_pre)

src_run = Path("scripts/run_pass.py").read_text(encoding="utf-8")
check("run_pass imports genesis", "genesis" in src_run)
check("run_pass refuses a live judged pass without a verified genesis",
      "genesis.verify(" in src_run and "JUDGED_ROLE" in src_run,
      "a gate only in preflight is a gate someone chooses to run")
i_gen = src_run.find("genesis.verify(")
i_pass = src_run.find("runner.")
check("checked BEFORE the pass runs", -1 < i_gen < i_pass, f"{i_gen} vs {i_pass}")

# --- THE JUDGED ARM AND THE JUDGED ACCOUNT ARE ONE OBJECT -------------------
# Until 2026-08-27 the one account that gets judged was the one account with no
# declared hypothesis and no falsifier, so `arms.validate()` could not refuse a
# duplicate alpha source it had never been told about.
from dataclasses import replace as _replace                  # noqa: E402

from alpha import arms                                       # noqa: E402

comp = [a for a in arms.ARMS if a.role == "competition"]
check("the judged account has a declared arm", len(comp) == 1,
      "an undeclared arm cannot collide, and cannot be refused either")
if comp:
    c = comp[0]
    check("it declares a falsifier", len(c.falsifier.strip()) > 40)
    check("it does not inherit a LIVE arm's alpha source",
          c.alpha_source not in {a.alpha_source for a in arms.ARMS
                                 if a.status == "live" and a.role != "competition"},
          "two accounts running one bet is the arena bottleneck, rebuilt")
    check("it names the account, genesis and rules blockers", len(c.depends_on) >= 3)
    check("its instruments include options (the rules require them)",
          any("call" in i or "put" in i or "spread" in i for i in c.instruments))
    check("its notes name the vol_gap quarantine as a hard constraint",
          "quarantined" in c.notes)

    # genesis.path is redirected to the temp dir above and the record was unlinked,
    # so a live competition arm must refuse for want of a birth certificate.
    try:
        arms.validate(tuple(a if a.role != "competition" else _replace(a, status="live",
                                                                      depends_on=())
                            for a in arms.ARMS))
        got = None
    except arms.ArmRefusal as exc:
        got = str(exc)
    check("a LIVE competition arm with no genesis record is REFUSED",
          got is not None and "no genesis record exists" in got, str(got))

check("the registry as declared validates", arms.validate() is None)

print(f"\n{ran} checks")
print("ALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
