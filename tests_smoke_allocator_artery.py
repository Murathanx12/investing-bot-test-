"""THE SECOND ARTERY: the allocator's daily cut must actually reach a loop.

`tests_smoke_seal_delivery.py` exists because `prediction_book_sync.py` was
written, tested and launched by NOTHING for a trading morning -- reachability,
not stage correctness, was the failure, and 2,769 green checks could not see it.
This chunk adds a second artefact over the same artery, so it gets the same
shape of proof rather than a promise in a docstring.

  1. the sync is an exact no-op with no base URL, and its base URL falls back to
     the seal's -- a loop that never carried a new variable still reads the cut;
  2. FRESH / STALE / MISSING / HASH-MISMATCH / WRONG-DAY, each named, and none
     of them a silent 1.00;
  3. a missing or stale record can only KEEP or REDUCE a book, never raise it;
  4. `agent_loop._cycle` actually calls the sync AND forwards its answer -- the
     gap this file exists for, and the one a docstring cannot close;
  5. the authority's allocator step is gated on weekday + out-of-session + the
     declared ET hour, computes a `content_sha256` the consumer can verify, and
     only ever serves `state/allocator/` under `/allocator/`;
  6. the deploy wiring emits key REFERENCES and never a value, and gives the
     authority no volume and no loop variables.
"""
from __future__ import annotations

import ast
import json
import os
import re
import tempfile
from datetime import datetime, time as dtime, timezone
from pathlib import Path

_fails: list[str] = []
ROOT = Path(__file__).resolve().parent


def check(name: str, ok: bool, note: str = "") -> None:
    # `ok` with two trailing spaces is what run_tests.py's _OK regex counts.
    print(f"  {'ok ' if ok else 'FAIL'}  {name}" + (f"  ({note})" if note else ""))
    if not ok:
        _fails.append(name)


def function_node(path: Path, name: str) -> ast.FunctionDef:
    """The AST of one function. A GREP CANNOT TELL AN EXPLANATION FROM AN INSTANCE.

    Three tests in the sibling repo failed on their first run by matching the
    docstring that EXPLAINS the banned pattern, and the cheapest way to make
    them green is to delete the rationale. So the guards below read the tree and
    drop the docstring instead of searching the text (CLAUDE.md, session
    protocol 10).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {path.name}")


def body_without_docstring(fn) -> list:
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return body


def string_constants(nodes: list) -> list:
    out: list = []
    for node in nodes:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                out.append(sub.value)
    return out


def getenv_arguments(nodes: list) -> list:
    out: list = []
    for node in nodes:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) \
                    and sub.func.attr == "getenv" and sub.args:
                out.append(sub.args[0])
    return out


def method_calls(nodes: list) -> set:
    return {sub.func.attr for node in nodes for sub in ast.walk(node)
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)}


#: `AAT_HACK1_KEY_ID` matches; the bare suffix `_KEY_ID` used by an `endswith`
#: guard does not, which is the whole difference between an instance and the
#: code that refuses one.
KEYPAIR = re.compile(r"^AAT_[A-Z0-9]+_(KEY_ID|SECRET_KEY)$")


def _sha(body: dict) -> str:
    import hashlib

    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _record(day: str, scales: dict) -> dict:
    body = {
        "day": day,
        "contract_hash": "deadbeefdeadbeef",
        "licence": "PRODUCT_EXPERIMENT",
        "trial": "TRIAL-DRAFT-ALLOCATOR-v0",
        "per_book": {r: {"gross_budget_scale": s, "kill_state": "ACTIVE",
                         "binding_constraint": "test"} for r, s in scales.items()},
    }
    return {**body, "content_sha256": _sha(body)}


for _v in ("AAT_ALLOCATOR_BASE_URL", "AAT_PREDICTION_BOOK_BASE_URL"):
    os.environ.pop(_v, None)

from scripts import allocator_sync as S           # noqa: E402
from alpha import allocator as A                  # noqa: E402


# ---- 1: the no-op, and where the base URL comes from ------------------------
print("\n-- 1: an unconfigured loop does nothing, and a configured one needs no new variable")
check("no base url at all -> exact no-op True", S.sync_once("2026-09-14") is True)
check("and base_url() is empty", S.base_url() == "")
os.environ["AAT_PREDICTION_BOOK_BASE_URL"] = "http://seal-authority.railway.internal:8080/"
check("the seal's base url is inherited, so hack3/4/6 need no new variable",
      S.base_url() == "http://seal-authority.railway.internal:8080", S.base_url())
os.environ["AAT_ALLOCATOR_BASE_URL"] = "http://explicit:9/"
check("an explicit AAT_ALLOCATOR_BASE_URL wins", S.base_url() == "http://explicit:9")
for _v in ("AAT_ALLOCATOR_BASE_URL", "AAT_PREDICTION_BOOK_BASE_URL"):
    os.environ.pop(_v, None)
check("COMMON_ENV names it, so hack1 and hack5 are not the two books nobody checks",
      "AAT_ALLOCATOR_BASE_URL" in __import__("alpha.fleet", fromlist=["x"]).COMMON_ENV)


# ---- 2: the cadence, which is the thing a naive freshness rule gets wrong ----
print("\n-- 2: freshness is measured against the last CLOSED session, not against today")
fri_after = datetime(2026, 9, 11, 21, 30, tzinfo=timezone.utc)    # 17:30 ET Friday
fri_intra = datetime(2026, 9, 11, 14, 0, tzinfo=timezone.utc)     # 10:00 ET Friday
mon_intra = datetime(2026, 9, 14, 14, 0, tzinfo=timezone.utc)     # 10:00 ET Monday
sun = datetime(2026, 9, 13, 14, 0, tzinfo=timezone.utc)
check("after 16:30 ET on a weekday the day itself has closed",
      S.expected_day(fri_after) == "2026-09-11", S.expected_day(fri_after))
check("DURING a session the last close is the PREVIOUS session",
      S.expected_day(fri_intra) == "2026-09-10", S.expected_day(fri_intra))
check("Monday morning's last close is Friday -- NOT stale, which is the whole point",
      S.expected_day(mon_intra) == "2026-09-11", S.expected_day(mon_intra))
check("a weekend walks back to Friday", S.expected_day(sun) == "2026-09-11")
check("the authority's cut hour and the consumer's are the same number",
      S.CLOSE_MARKED_AFTER_ET == dtime(16, 30))


# ---- 3: what is refused at the door ----------------------------------------
print("\n-- 3: hash mismatch, wrong day, no budget, and leverage are all refused")
good = _record("2026-09-14", {r: 1.0 for r in A.ROLES})
sha, fresh = S._validate(good, want_day="2026-09-14")
check("a well-formed record for the last close is CURRENT", fresh == "CURRENT")
check("and its hash is the one the authority stamped", sha == good["content_sha256"])
_, stale = S._validate(_record("2026-09-10", {r: 0.5 for r in A.ROLES}),
                       want_day="2026-09-14")
check("an older record is STALE, not refused", stale == "STALE")

tampered = dict(good)
tampered["per_book"] = {**good["per_book"]}
tampered["per_book"]["hack1"] = {"gross_budget_scale": 1.0, "kill_state": "ACTIVE"}
try:
    S._validate(tampered, want_day="2026-09-14")
    check("a tampered record is REFUSED on the hash", False)
except ValueError as exc:
    check("a tampered record is REFUSED on the hash", "hash mismatch" in str(exc), str(exc)[:90])

try:
    S._validate(_record("2026-09-15", {r: 1.0 for r in A.ROLES}), want_day="2026-09-14")
    check("a record from a day that has not CLOSED is refused", False)
except ValueError as exc:
    check("a record from a day that has not CLOSED is refused",
          "has not finished" in str(exc), str(exc)[:110])

lever = _record("2026-09-14", {**{r: 1.0 for r in A.ROLES}, "hack1": 1.5})
try:
    S._validate(lever, want_day="2026-09-14")
    check("a record that hands a book LEVERAGE is refused, not clamped quietly", False)
except ValueError as exc:
    check("a record that hands a book LEVERAGE is refused, not clamped quietly",
          "outside [0,1]" in str(exc), str(exc)[:110])

noboo = {"day": "2026-09-14", "per_book": {}}
noboo["content_sha256"] = _sha({k: v for k, v in noboo.items()})
try:
    S._validate(noboo, want_day="2026-09-14")
    check("a record with no per_book block is refused", False)
except ValueError as exc:
    check("a record with no per_book block is refused", "per_book" in str(exc), str(exc)[:90])


# ---- 4: the budget a pass actually runs at ---------------------------------
print("\n-- 4: a missing or stale record can KEEP or REDUCE a book, never raise it")
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    old_state, old_seed = A.STATE, A.SEED_STATE
    A.STATE, A.SEED_STATE = root / "allocator", root / "seed"
    try:
        A.STATE.mkdir(parents=True)
        scale, why = S.effective_gross_scale("hack1", deployed=0.5, day="2026-09-14")
        check("NO RECORD anywhere -> the deployed flag stands, and says so",
              scale == 0.5 and "NO ALLOCATOR RECORD" in why, why[:110])
        check("...and it is never a silent 1.00", scale != 1.0)

        (A.STATE / "2026-09-14.json").write_text(
            json.dumps(_record("2026-09-14", {r: 0.25 for r in A.ROLES})), encoding="utf-8")
        scale, why = S.effective_gross_scale("hack1", deployed=1.0, day="2026-09-14")
        check("a CURRENT record binds even when the deployed flag was larger",
              scale == 0.25 and why.startswith("CURRENT"), why[:90])

        (A.STATE / "2026-09-14.json").write_text(
            json.dumps(_record("2026-09-14", {r: 1.0 for r in A.ROLES})), encoding="utf-8")
        scale, why = S.effective_gross_scale("hack1", deployed=0.5, day="2026-09-14")
        check("a CURRENT record MAY restore a book above the deployed flag -- that IS "
              "the promotion path", scale == 1.0 and why.startswith("CURRENT"), why[:90])

        scale, why = S.effective_gross_scale("hack1", deployed=0.5, day="2026-09-18")
        check("a STALE record is floored at the deployed flag: keep or reduce, never raise",
              scale == 0.5 and why.startswith("STALE"), why[:120])
        check("and the staleness names BOTH days",
              "2026-09-14" in why and "2026-09-18" in why, why[:140])

        (A.STATE / "2026-09-14.json").write_text(
            json.dumps(_record("2026-09-14", {r: 0.02 for r in A.ROLES})), encoding="utf-8")
        scale, why = S.effective_gross_scale("hack1", deployed=1.0, day="2026-09-18")
        check("a STALE record that CUT a book keeps the cut -- a stale allocator never "
              "re-arms", scale == 0.02, why[:120])

        scale, why = S.effective_gross_scale("hack2", deployed=0.7, day="2026-09-14")
        check("hack2 (lane D) gets the deployed flag and a reason, not a guess",
              scale == 0.7 and "not an allocated role" in why, why[:100])
    finally:
        A.STATE, A.SEED_STATE = old_state, old_seed


# ---- 5: the loop launches it AND uses the answer -----------------------------
print("\n-- 5: reachability -- the gap this file exists for")
loop_src = (ROOT / "scripts" / "agent_loop.py").read_text(encoding="utf-8")
cycle = loop_src.split("def _cycle(", 1)[-1]
check("agent_loop._cycle calls allocator_sync.sync_once",
      "allocator_sync" in cycle and "sync_once" in cycle)
check("and asks for the EFFECTIVE budget, not the flag baked in at deploy time",
      "effective_gross_scale" in cycle)
check("both --gross-scale forwarding sites use it",
      cycle.count('extra += ["--gross-scale", str(gross_scale)]') == 2,
      str(cycle.count('extra += ["--gross-scale", str(gross_scale)]')))
check("and args.gross_scale no longer reaches a pass directly",
      'str(args.gross_scale)' not in cycle)


# ---- 6: the authority's gate, hash and served surface ------------------------
print("\n-- 6: the authority computes a CLOSE, stamps it, and serves only allocator files")
os.environ["AAT_LEDGER_DIR"] = tempfile.mkdtemp()
import importlib                                                    # noqa: E402
from scripts import seal_authority as SA                            # noqa: E402
SA = importlib.reload(SA)

et = SA.ET
check("a weekend owes no record",
      SA.allocator_due(datetime(2026, 9, 13, 18, 0, tzinfo=et))[0] is None)
check("an in-session minute owes no record and says a mark is a CLOSE",
      SA.allocator_due(datetime(2026, 9, 14, 11, 4, tzinfo=et))[0] is None
      and "CLOSE" in SA.allocator_due(datetime(2026, 9, 14, 11, 4, tzinfo=et))[1])
check("16:12 ET is after the session but BEFORE the declared hour -- still not owed",
      SA.allocator_due(datetime(2026, 9, 14, 16, 12, tzinfo=et))[0] is None)
day, why = SA.allocator_due(datetime(2026, 9, 14, 16, 31, tzinfo=et))
check("16:31 ET on a weekday owes 2026-09-14", day == "2026-09-14", why)
check("the authority's hour is the consumer's hour",
      SA.ALLOCATOR_AFTER_ET == S.CLOSE_MARKED_AFTER_ET)
check("and it is outside the sealing blackout too",
      SA._in_session(SA.ALLOCATOR_AFTER_ET) is False)

stamped = SA._stamp({"day": "2026-09-14", "per_book": {"hack1": {"gross_budget_scale": 1.0}}})
check("the authority's stamp is the one the consumer verifies",
      S._canonical_sha(stamped) == stamped["content_sha256"])
check("re-stamping is idempotent (a served record is not double-hashed)",
      SA._stamp(stamped)["content_sha256"] == stamped["content_sha256"])

SA.ALLOC.mkdir(parents=True, exist_ok=True)
(SA.ALLOC / "2026-09-11.json").write_text("{}", encoding="utf-8")
(SA.ALLOC / "2026-09-14.json").write_text("{}", encoding="utf-8")
check("/allocator/latest.json resolves to the NEWEST record, not a second copy",
      SA._allocator_name("/allocator/latest.json") == "2026-09-14.json",
      SA._allocator_name("/allocator/latest.json"))
check("a dated record is served by name",
      SA._allocator_name("/allocator/2026-09-11.json") == "2026-09-11.json")
for attack in ("/allocator/../../.env", "/allocator/..%2f..%2fdecisions.jsonl",
               "/allocator/seals.jsonl", "/allocator/anchor.json",
               "/allocator/2026-09-11.json.bak", "/allocator/"):
    name = SA._allocator_name(attack)
    check(f"refused: {attack}", name in ("__refused__", "__no_allocator_record__")
          or name.endswith(".json") and name[0].isdigit() and len(name) == 15
          and attack.endswith(f"/{name}"), name)
check("the whitelist admits exactly two shapes and nothing above the allocator dir",
      not any(ch in SA._allocator_name("/allocator/../x") for ch in "/\\"))
# The ROUTE itself, not only the name function: the one line of glue between
# them is exactly the kind of thing a stage test leaves untested.
# `__new__`, not `__init__`: BaseHTTPRequestHandler's constructor serves a whole
# request. This is the real class, so the `super()` fall-through is the real one.
_h = SA.QuietHandler.__new__(SA.QuietHandler)
_h.directory = str(SA.BOOKS)
check("GET /allocator/latest.json resolves INTO state/allocator/",
      Path(_h.translate_path("/allocator/latest.json")).parent == SA.ALLOC,
      _h.translate_path("/allocator/latest.json"))
check("GET /allocator/2026-09-11.json resolves to that exact file",
      Path(_h.translate_path("/allocator/2026-09-11.json")) == SA.ALLOC / "2026-09-11.json")
check("a query string does not smuggle a path past the whitelist",
      Path(_h.translate_path("/allocator/2026-09-11.json?x=../../.env")).parent == SA.ALLOC)
check("a traversal attempt lands on a name that cannot exist, inside the allocator dir",
      Path(_h.translate_path("/allocator/../../.env")).parent == SA.ALLOC
      and not Path(_h.translate_path("/allocator/../../.env")).exists())
check("every other path still goes to the books directory, unchanged",
      Path(_h.translate_path("/2026-09-11.json")).parent == SA.BOOKS,
      _h.translate_path("/2026-09-11.json"))
check("the served root for books is unchanged", SA.BOOKS == SA.STATE / "predictions")
check("and the allocator dir sits beside it", SA.ALLOC == SA.STATE / "allocator")
check("no do_POST anywhere in the handler chain: every write method is still 501",
      not hasattr(SA.QuietHandler, "do_POST") and not hasattr(SA.QuietHandler, "do_PUT"))
os.environ.pop("AAT_LEDGER_DIR", None)


# ---- 7: the deploy wiring emits references, never values ---------------------
print("\n-- 7: the keys reach the authority as REFERENCES, and no value is printed")
from alpha import fleet                                             # noqa: E402

refs = fleet.seal_authority_key_references()
check("four roles, eight variables -- the authority's own pair is NOT touched",
      len(refs) == 8 and not any("HACK3" in k for k in refs), sorted(refs))
check("every value is a Railway cross-service reference and nothing else",
      all(v == "${{aat-loop-%s.%s}}" % (k.split("_")[1].lower(), k) for k, v in refs.items()),
      json.dumps(refs))
env = fleet.seal_authority_env()
check("the authority gets NO loop variables (the runbook's stale-mandate lesson)",
      not any(k.startswith("AAT_LOOP_") for k in env) and "AAT_MANDATE_END_UTC" not in env,
      sorted(env))
check("and it declares the role it seals under", env["AAT_ACCOUNT_ROLE"] == "hack3")
cmds = fleet.seal_authority_commands()
check("no `railway volume add` -- the authority has no volume by design",
      "volume add" not in cmds.replace("# NO `railway volume add`", ""))
fleet_path = ROOT / "scripts" / "fleet.py"
fleet_src = fleet_path.read_text(encoding="utf-8")
dsa = body_without_docstring(function_node(fleet_path, "deploy_seal_authority"))
check("deploy_seal_authority names NO key-pair variable in its EXECUTABLE code",
      not any(KEYPAIR.match(c) for c in string_constants(dsa)),
      "read the AST, not the text -- the docstring is allowed to explain what the "
      "code must not do")
check("and every os.getenv it makes takes a NAME, never a key-pair literal",
      all(not isinstance(a, ast.Constant) or not KEYPAIR.match(str(a.value))
          for a in getenv_arguments(dsa)))
check("the only environment it reads is fleet.SECRETS",
      any(isinstance(n, ast.For) and isinstance(n.iter, ast.Attribute)
          and n.iter.attr == "SECRETS"
          for n in ast.walk(ast.Module(body=dsa, type_ignores=[]))))
check("its read-back skips the references, or it would re-set them for ever",
      {"_KEY_ID", "_SECRET_KEY"} <= set(string_constants(dsa)))
check("seal-authority is NOT swept up by --deploy all",
      'roles = list(fleet.FLEET) if args.deploy == "all"' in fleet_src
      and "if args.deploy == fleet.SEAL_AUTHORITY_SERVICE:" in fleet_src)


# ---- 8: still no order path in the allocator --------------------------------
print("\n-- 8: the venue reader reads, and the allocator still has no order path")
venue_path = ROOT / "scripts" / "allocator_venue.py"
venue_src = venue_path.read_text(encoding="utf-8")
venue_tree = ast.parse(venue_src)
venue_code = []
for node in venue_tree.body:
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
        continue                                    # the module docstring
    venue_code += body_without_docstring(node) if isinstance(node, ast.FunctionDef) else [node]
venue_strings = string_constants(venue_code)
venue_calls = method_calls(venue_code)
check("allocator_venue names no order endpoint in its EXECUTABLE code",
      not any("/v2/orders" in c for c in venue_strings)
      and not ({"submit_order", "close_position", "cancel", "submit"} & venue_calls),
      "a read-only client must not be able to place one")
check("and it calls exactly the two read methods it declares",
      "portfolio_history" in venue_calls and "account" in venue_calls,
      str(sorted(venue_calls)))
check("scripts/allocator.py is still free of alpha.broker (the existing pin)",
      "alpha.broker" not in (ROOT / "scripts" / "allocator.py").read_text(encoding="utf-8"))
check("AAT_ACCOUNT_ROLE is never mutated by the venue reader",
      'os.environ["AAT_ACCOUNT_ROLE"]' not in venue_src
      and "environ.setdefault" not in venue_src)


# ---- 9: END TO END, with the venue faked and no socket opened ---------------
# The stages all pass above; that is exactly the state tests_smoke_seal_delivery
# was written about, where every stage was correct and the artery had a gap. So
# this drives the real authority function against a stubbed venue read and then
# verifies the byte it wrote with the real consumer.
print("\n-- 9: the authority writes a record the consumer actually accepts")
import importlib                                                    # noqa: E402

with tempfile.TemporaryDirectory() as td:
    os.environ["AAT_LEDGER_DIR"] = td
    SA = importlib.reload(__import__("scripts.seal_authority", fromlist=["x"]))
    AA = importlib.reload(__import__("alpha.allocator", fromlist=["x"]))
    from scripts import allocator_venue                             # noqa: E402

    anchor = {
        "anchor_day": "2026-09-11", "contract_hash": AA.contract_sha256(),
        "trial": AA.TRIAL, "licence": AA.LICENCE,
        "books": {r: {"anchor_equity": 100_000.0, "anchor_day": "2026-09-11",
                      "account": f"PA{r.upper()}"} for r in AA.ROLES},
    }
    AA.STATE.mkdir(parents=True, exist_ok=True)
    (AA.STATE / AA.ANCHOR).write_text(json.dumps(anchor), encoding="utf-8")

    # hack1 is DOWN 8% from its anchor: the drawdown rule must be what fires,
    # on the first close, with no return evidence anywhere.
    equities = {"hack1": 92_000.0, "hack3": 100_000.0, "hack4": 100_000.0,
                "hack5": 100_000.0, "hack6": 100_000.0}
    fake = {r: {"role": r, "account": f"PA{r.upper()}", "equity": e, "door": "stub",
                "source": "stub",
                "curve": [{"day": "2026-09-11", "equity": 100_000.0},
                          {"day": "2026-09-14", "equity": e}]}
            for r, e in equities.items()}
    _real = allocator_venue.read_fleet
    allocator_venue.read_fleet = lambda roles=AA.ROLES, *, anchor=None: fake
    try:
        ok = SA.ensure_allocator("2026-09-14")
    finally:
        allocator_venue.read_fleet = _real
    check("the authority writes the day's record", ok is True)

    written = SA.allocator_record_path("2026-09-14")
    check("beside the seal, under state/allocator/", written.is_file(), str(written))
    payload = json.loads(written.read_text(encoding="utf-8"))
    sha, freshness = S._validate(payload, want_day="2026-09-14")
    check("and the CONSUMER verifies the byte the AUTHORITY wrote",
          sha == payload["content_sha256"] and freshness == "CURRENT")
    check("the record carries the contract hash, the licence and the trial",
          payload["contract_hash"] == AA.contract_sha256()
          and payload["licence"] == "PRODUCT_EXPERIMENT"
          and payload["trial"] == "TRIAL-DRAFT-ALLOCATOR-v0")
    check("it says where it was produced, so a reader can tell it from a laptop run",
          payload.get("produced_by") == "seal_authority")
    check("and that the curves were RE-DERIVED, not accumulated",
          any("RE-DERIVED" in n for n in payload["notes"]), str(payload["notes"])[:160])

    cut = payload["per_book"]["hack1"]
    check("a book 8% below its own peak is FLOORED on the FIRST close, with no "
          "return evidence at all",
          cut["kill_state_base"] == "FLOOR"
          and cut["gross_budget_scale"] == AA.FLOOR_WEIGHT,
          json.dumps({k: cut[k] for k in ("kill_state_base", "kill_state",
                                          "gross_budget_scale")}))
    check("and it is floored, never ZEROED -- a zeroed book stops marking and both "
          "twins stop being exact", cut["gross_budget_scale"] > 0.0)
    check("the cooldown is armed on the same row", "COOLDOWN" in str(cut["kill_state"]))
    check("and the books that did not draw down keep their full size",
          all(payload["per_book"][r]["gross_budget_scale"] == 1.0
              for r in AA.ROLES if r != "hack1"))
    check("the rule that fired is named in numbers",
          any("hack1" in line for line in (payload["rule_fired"] or [])),
          str(payload["rule_fired"]))

    check("/allocator/latest.json now resolves to it",
          SA._allocator_name("/allocator/latest.json") == "2026-09-14.json")
    check("a second call is idempotent and does not re-mark the day",
          SA.ensure_allocator("2026-09-14") is True
          and json.loads(written.read_text(encoding="utf-8"))["content_sha256"]
          == payload["content_sha256"])

    # the loop side, end to end, over the same bytes and with no socket
    root = Path(td) / "allocator"
    scale, why = S.effective_gross_scale("hack1", deployed=1.0, day="2026-09-14")
    check("and a LOOP asking for its budget gets the cut, not the deployed 1.00",
          scale <= AA.FLOOR_WEIGHT and why.startswith("CURRENT"), why[:110])

    # every read failing must REFUSE rather than allocate out of five holes
    allocator_venue.read_fleet = lambda roles=AA.ROLES, *, anchor=None: {
        r: {"role": r, "equity": None, "curve": [], "why": "stubbed refusal"}
        for r in AA.ROLES}
    try:
        refused = SA.ensure_allocator("2026-09-15")
    finally:
        allocator_venue.read_fleet = _real
    check("five unreadable accounts REFUSE the day rather than allocate out of holes",
          refused is False and not SA.allocator_record_path("2026-09-15").exists())
    check("...and the previous record is left standing, so a loop keeps its budget",
          SA._allocator_name("/allocator/latest.json") == "2026-09-14.json")

os.environ.pop("AAT_LEDGER_DIR", None)

maintainer_src = ast.get_source_segment(
    (ROOT / "scripts" / "seal_authority.py").read_text(encoding="utf-8"),
    function_node(ROOT / "scripts" / "seal_authority.py", "maintainer")) or ""
check("the maintainer thread actually CALLS it -- reachability, not correctness, "
      "is how the first artery failed", "ensure_allocator()" in maintainer_src)
check("and it runs AFTER the seal, so a venue read cannot delay the book",
      maintainer_src.index("ensure_today()") < maintainer_src.index("ensure_allocator()"))


print()
if _fails:
    print(f"FAILED: {len(_fails)} -> {_fails}")
    raise SystemExit(1)
print("ALL PASS tests_smoke_allocator_artery")
