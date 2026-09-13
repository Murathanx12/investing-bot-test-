"""THE THIRD ARTERY: Book F's monthly engine file must reach a loop WITHOUT a redeploy.

`tests_smoke_seal_delivery.py` exists because a sync nothing called was green
for a trading morning; `tests_smoke_allocator_artery.py` gave the second
artefact the same shape of proof. This is the third, and the claim it has to
defend is a sentence that was deleted from `docs/DEPLOY_PLAN_2026-09-14.md` 3:

    "THIS BOOK NEEDS A REDEPLOY EVERY CALENDAR MONTH."

Two separate things made that true, and a test that checks only one of them
would let hack3 sit empty through October with a green suite:

  1. the FILE arrived only inside an image  -> the authority now serves it;
  2. the LIST of symbols was baked into `AAT_LOOP_ARGS` at deploy time -> the
     loop now re-derives it from the installed file every cycle.

So:

  1. the authority's `/engines/` whitelist: two shapes admitted, everything else
     refused, `latest` resolved to the newest VERIFIED month, volume beating
     image, and an unverified file served by NEITHER side;
  2. the consumer: no base URL -> exact no-op; wrong month, wrong engine, empty
     selection and a broken hash all refused AT THE DOOR, never installed;
  3. the brain still fails CLOSED on every one of its four refusals, and a
     fetched file is checked by exactly the same code as a seeded one;
  4. reachability -- `agent_loop._cycle` calls the sync, `seasonality_f.engine`
     calls it too, and the entry pass uses `cycle_universe`, not `args.universe`;
  5. the calendar: a NEW month needs no redeploy, and the one case that still
     does is named in the caveat and in the deploy plan rather than implied.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import tempfile
from pathlib import Path

_fails: list[str] = []
ROOT = Path(__file__).resolve().parent


def check(name: str, ok: bool, note: str = "") -> None:
    # `ok` with two trailing spaces is what run_tests.py's _OK regex counts.
    print(f"  {'ok ' if ok else 'FAIL'}  {name}" + (f"  ({note})" if note else ""))
    if not ok:
        _fails.append(name)


def _sha(body: dict) -> str:
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _engine(month: str, *, names: int = 3, engine: str = "seasonality_11_20_v0",
            selected: list[str] | None = None) -> dict:
    body = {
        "engine": engine,
        "engine_key": "F",
        "registration": "TRIAL-DRAFT-F-calendar-seasonality-v0 (UNSIGNED)",
        "licence": "PRODUCT_EXPERIMENT",
        "month": month,
        "as_of": f"{month}-01T00:00:00+00:00",
        "construction": {"k": 30},
        "coverage": {"n": names},
        "selected": selected if selected is not None else [f"S{i}" for i in range(names)],
    }
    return {**body, "content_sha256": _sha(body)}


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return path


for _v in ("AAT_ENGINE_BASE_URL", "AAT_ALLOCATOR_BASE_URL", "AAT_PREDICTION_BOOK_BASE_URL"):
    os.environ.pop(_v, None)

_tmp_ledger = tempfile.mkdtemp()
os.environ["AAT_LEDGER_DIR"] = _tmp_ledger

import importlib                                                    # noqa: E402
from scripts import engine_sync as S                                # noqa: E402
from scripts import seal_authority as SA                            # noqa: E402

SA = importlib.reload(SA)


# ---- 1: the authority's whitelist -------------------------------------------
print("\n-- 1: /engines/ admits two shapes, verifies every byte, and volume beats image")
_seed = Path(tempfile.mkdtemp())
SA.SEED_ENGINES = _seed
SA.ENGINES.mkdir(parents=True, exist_ok=True)

_write(_seed / "F_seasonality_2026-09.json", _engine("2026-09", names=3))
_write(_seed / "F_seasonality_2026-10.json", _engine("2026-10", names=4))

check("both seeded months are seen, and nothing else is invented",
      SA.engine_months() == ["2026-09", "2026-10"], str(SA.engine_months()))
check("a month with no file resolves to nothing rather than a neighbour",
      SA.engine_file("2026-11") is None)
check("the image copy is served when the volume has none",
      SA.engine_file("2026-09") == _seed / "F_seasonality_2026-09.json")

# The correction path `cp -rn` never had: a VERIFIED file on the volume wins.
_vol_sep = _write(SA.ENGINES / "F_seasonality_2026-09.json",
                  _engine("2026-09", selected=["CORRECTED", "NAMES"]))
check("a verified volume copy WINS over the image -- the correction `cp -rn` refuses",
      SA.engine_file("2026-09") == _vol_sep)
check("...and it is the corrected content that would be served",
      json.loads(SA.engine_file("2026-09").read_text(encoding="utf-8"))["selected"]
      == ["CORRECTED", "NAMES"])

# A corrupted push must not take the book down: fall back to the image.
_vol_sep.write_text(json.dumps({**_engine("2026-09"), "content_sha256": "0" * 64}),
                    encoding="utf-8")
check("a volume copy that fails its own hash is SKIPPED, not served",
      SA.engine_file("2026-09") == _seed / "F_seasonality_2026-09.json")
check("...and it does not vanish from the month list either (the image still has it)",
      "2026-09" in SA.engine_months())
_vol_sep.unlink()

# A month whose ONLY copy is broken is served by nobody.
_write(SA.ENGINES / "F_seasonality_2026-12.json",
       {**_engine("2026-12"), "content_sha256": "f" * 64})
check("a month with no VERIFIED copy anywhere is refused, not served unverified",
      SA.engine_file("2026-12") is None and "2026-12" not in SA.engine_months())
check("and the route resolves it to a path that cannot exist",
      not Path(SA._engine_served_path("/engines/F_seasonality_2026-12.json")).exists())

# A file whose hashed content names another month is a lie about itself.
_write(SA.ENGINES / "F_seasonality_2027-01.json", _engine("2026-09"))
check("a file whose hashed month disagrees with its NAME is refused",
      SA.engine_file("2027-01") is None, "the name is not part of the hash")
(SA.ENGINES / "F_seasonality_2027-01.json").unlink()
(SA.ENGINES / "F_seasonality_2026-12.json").unlink()

print("\n-- 1b: latest, and everything the whitelist must refuse")
check("/engines/latest/F_seasonality.json resolves to the NEWEST verified month",
      Path(SA._engine_served_path("/engines/latest/F_seasonality.json")).name
      == "F_seasonality_2026-10.json",
      Path(SA._engine_served_path("/engines/latest/F_seasonality.json")).name)
check("a dated request is served by name",
      Path(SA._engine_served_path("/engines/F_seasonality_2026-09.json")).name
      == "F_seasonality_2026-09.json")
for attack in ("/engines/../../.env", "/engines/..%2f..%2fdecisions.jsonl",
               "/engines/seals.jsonl", "/engines/anchor.json",
               "/engines/F_seasonality_2026-09.json.bak", "/engines/",
               "/engines/F_seasonality_2026-9.json", "/engines/F_seasonality_.json",
               "/engines/../allocator/2026-09-11.json"):
    resolved = Path(SA._engine_served_path(attack))
    check(f"refused: {attack}",
          resolved.name.startswith("__") or (
              resolved.name.startswith("F_seasonality_")
              and attack.endswith(f"/{resolved.name}")),
          resolved.name)
check("no refusal can name a path outside the engines directory",
      all(not any(c in Path(SA._engine_served_path(a)).name for c in "/\\")
          for a in ("/engines/../x", "/engines/../../y")))

print("\n-- 1c: the ROUTE, not only the name function")
_h = SA.QuietHandler.__new__(SA.QuietHandler)
_h.directory = str(SA.BOOKS)
check("GET /engines/F_seasonality_2026-09.json resolves to the real file",
      Path(_h.translate_path("/engines/F_seasonality_2026-09.json"))
      == _seed / "F_seasonality_2026-09.json",
      _h.translate_path("/engines/F_seasonality_2026-09.json"))
check("GET /engines/latest/F_seasonality.json resolves through the route too",
      Path(_h.translate_path("/engines/latest/F_seasonality.json")).name
      == "F_seasonality_2026-10.json")
check("a query string does not smuggle a path past the whitelist",
      Path(_h.translate_path("/engines/F_seasonality_2026-09.json?x=../../.env")).name
      == "F_seasonality_2026-09.json")
check("a traversal attempt lands inside the engines dir on a name that cannot exist",
      Path(_h.translate_path("/engines/../../.env")).parent == SA.ENGINES
      and not Path(_h.translate_path("/engines/../../.env")).exists())
check("the allocator route is untouched by the new one",
      Path(_h.translate_path("/allocator/2026-09-11.json")).parent == SA.ALLOC)
check("every other path still goes to the books directory",
      Path(_h.translate_path("/2026-09-11.json")).parent == SA.BOOKS)
check("still no write method anywhere in the handler chain",
      not hasattr(SA.QuietHandler, "do_POST") and not hasattr(SA.QuietHandler, "do_PUT"))
check("the authority's hash is prediction_book._sha, the one the consumer verifies",
      SA._engine_verifies(_seed / "F_seasonality_2026-09.json")
      and S._canonical_sha(json.loads(
          (_seed / "F_seasonality_2026-09.json").read_text(encoding="utf-8")))
      == _engine("2026-09", names=3)["content_sha256"])


# ---- 2: the consumer, and what it refuses at the door -----------------------
print("\n-- 2: the sync is a no-op unconfigured, and refuses four kinds of wrong file")
check("no base url at all -> base_url() is empty", S.base_url() == "")
check("and sync_once is an exact no-op that reports the LOCAL truth",
      S.sync_once("2026-09") is False, "nothing installed, nothing fetched")
os.environ["AAT_PREDICTION_BOOK_BASE_URL"] = "http://seal-authority.railway.internal:8080/"
check("the seal's base url is inherited -- a loop needs no new variable",
      S.base_url() == "http://seal-authority.railway.internal:8080", S.base_url())
os.environ["AAT_ALLOCATOR_BASE_URL"] = "http://alloc:8/"
check("the allocator's variable is the second fallback", S.base_url() == "http://alloc:8")
os.environ["AAT_ENGINE_BASE_URL"] = "http://explicit:9/"
check("an explicit AAT_ENGINE_BASE_URL wins", S.base_url() == "http://explicit:9")
for _v in ("AAT_ENGINE_BASE_URL", "AAT_ALLOCATOR_BASE_URL", "AAT_PREDICTION_BOOK_BASE_URL"):
    os.environ.pop(_v, None)
from alpha import fleet                                             # noqa: E402
check("COMMON_ENV names it, so no book is the one the artery silently misses",
      "AAT_ENGINE_BASE_URL" in fleet.COMMON_ENV)

check("a well-formed file validates and returns the exporter's own sha",
      S._validate(_engine("2026-09"), want_month="2026-09")
      == _engine("2026-09")["content_sha256"])

for label, payload, want, fragment in [
    ("a file for ANOTHER month is never renamed into this one",
     _engine("2026-08"), "2026-09", "not '2026-09'"),
    ("a file naming another ENGINE is refused",
     _engine("2026-09", engine="momentum_12_1"), "2026-09", "Book F's ranking"),
    ("an EMPTY selection is a coverage refusal, not a book",
     _engine("2026-09", selected=[]), "2026-09", "selected no names"),
    ("a TAMPERED file is refused on the hash",
     {**_engine("2026-09"), "selected": ["EVIL"]}, "2026-09", "hash mismatch"),
]:
    try:
        S._validate(payload, want_month=want)
        check(label, False, "it was accepted")
    except ValueError as exc:
        check(label, fragment in str(exc), str(exc)[:110])

print("\n-- 2b: month_wanted is DERIVED, and installed() reads no network")
check("month_wanted slices the repo's one ET trading day",
      S.month_wanted() == __import__("alpha.exits", fromlist=["x"]).session_day()[:7])
check("month_wanted honours an explicit day (a fixture never hardcodes a month)",
      S.month_wanted("2027-03-19") == "2027-03")
_root = Path(_tmp_ledger) / "engines"
check("installed() is None for a month with no file", S.installed("2026-09") is None)
_write(_root / "F_seasonality_2026-09.json", _engine("2026-09"))
check("installed() finds a verified local copy", S.installed("2026-09") is not None)
check("and sync_once short-circuits on it without a base url",
      S.sync_once("2026-09") is True)
(_root / "F_seasonality_2026-09.json").write_text(
    json.dumps({**_engine("2026-09"), "content_sha256": "0" * 64}), encoding="utf-8")
check("installed() REJECTS a local copy that fails its own hash",
      S.installed("2026-09") is None, "a corrupt volume copy is re-fetched, not trusted")
(_root / "F_seasonality_2026-09.json").unlink()


# ---- 3: the brain still fails CLOSED ----------------------------------------
print("\n-- 3: the brain's four refusals survive the new delivery path")
from alpha.brains import seasonality_f as F                         # noqa: E402

F = importlib.reload(F)
F.ENGINES = _root
F.SEED_ENGINES = Path(tempfile.mkdtemp())

try:
    F.engine(month="2026-11")
    check("no engine file for the month -> DECLINED", False)
except F.EngineDeclined as exc:
    check("no engine file for the month -> DECLINED", True, str(exc)[:70])
    check("...and the refusal names the authority route that would have served it",
          "/engines/F_seasonality_2026-11.json" in str(exc))

_write(_root / "F_seasonality_2026-11.json",
       {**_engine("2026-11"), "content_sha256": "0" * 64})
try:
    F.engine(month="2026-11")
    check("a hash mismatch -> DECLINED, in the ORDER path", False)
except F.EngineDeclined as exc:
    check("a hash mismatch -> DECLINED, in the ORDER path",
          "content_sha256" in str(exc), str(exc)[:70])

_write(_root / "F_seasonality_2026-11.json", _engine("2026-09"))
try:
    F.engine(month="2026-11")
    check("a file declaring another month -> DECLINED", False)
except F.EngineDeclined as exc:
    check("a file declaring another month -> DECLINED", "month" in str(exc), str(exc)[:70])

_write(_root / "F_seasonality_2026-11.json", _engine("2026-11", engine="momentum_12_1"))
try:
    F.engine(month="2026-11")
    check("a file declaring another engine -> DECLINED", False)
except F.EngineDeclined as exc:
    check("a file declaring another engine -> DECLINED", "engine" in str(exc), str(exc)[:70])

_write(_root / "F_seasonality_2026-11.json", _engine("2026-11", names=5))
payload = F.engine(month="2026-11")
check("a VERIFIED file is accepted, and only then", payload["month"] == "2026-11")
check("the brain checks the FETCHED bytes with the same code as a seeded file",
      F._sha_of(payload) == payload["content_sha256"])
(_root / "F_seasonality_2026-11.json").unlink()


# ---- 4: the fetch happens BEFORE the order path, and cannot raise into it ----
print("\n-- 4: reachability -- the gap the first artery's test exists for")
_calls: list[str] = []
_orig_ensure = S.ensure_month


def _fake_ensure(month=None):
    _calls.append(month)
    _write(_root / f"F_seasonality_{month}.json", _engine(month, names=2))
    return True


S.ensure_month = _fake_ensure
try:
    F._fetch_from_authority.__globals__  # noqa: B018  (the lazy import is inside)
    payload = F.engine(month="2026-11")
    check("engine() asks the authority when the volume lacks the month",
          _calls == ["2026-11"], str(_calls))
    check("...and then trades the file that arrived", payload["month"] == "2026-11")
finally:
    S.ensure_month = _orig_ensure
    (_root / "F_seasonality_2026-11.json").unlink(missing_ok=True)


def _raising(month=None):
    raise RuntimeError("the authority is on fire")


S.ensure_month = _raising
try:
    F.engine(month="2026-11")
    check("a fetch that RAISES cannot raise into the order path", False)
except F.EngineDeclined:
    check("a fetch that RAISES cannot raise into the order path", True,
          "it becomes an ordinary EngineDeclined")
except Exception as exc:  # noqa: BLE001
    check("a fetch that RAISES cannot raise into the order path", False,
          f"{type(exc).__name__} escaped")
finally:
    S.ensure_month = _orig_ensure

loop_src = (ROOT / "scripts" / "agent_loop.py").read_text(encoding="utf-8")
cycle = loop_src.split("def _cycle(", 1)[-1]
check("agent_loop._cycle calls engine_sync.sync_once",
      "engine_sync" in cycle and "sync_once()" in cycle)
check("the entry pass uses cycle_universe, NOT args.universe",
      "cycle_universe(args)" in cycle and "*args.universe" not in cycle)


# ---- 5: the calendar item is actually gone ----------------------------------
print("\n-- 5: a NEW month needs no redeploy; the one case that does is NAMED")
# Section 3 pointed the brain at throwaway directories on purpose. Put the REAL
# ones back before asking the fleet for hack3's arguments: `loop_args` resolves
# `engine_f` through the brain, so a test that left the fixture in place would
# be asserting against a book that cannot find its own engine file.
F.ENGINES = Path(os.getenv("AAT_LEDGER_DIR") or (F.ROOT / "state")) / "engines"
F.SEED_ENGINES = F.ROOT / "docs" / "seed" / "engines"
m = fleet.FLEET["hack3"]
args = fleet.loop_args(m)
check("hack3's loop args tell it to re-derive the universe",
      "--engine-universe" in args)
check("the flag cannot break the AAT_LOOP_ARGS split on '--universe'",
      "--universe" not in "--engine-universe")

from scripts import agent_loop as AL                                # noqa: E402


class _Args:
    universe = ["OLD1", "OLD2"]
    engine_universe = False


check("a book without the flag gets exactly the baked list",
      AL.cycle_universe(_Args()) == ["OLD1", "OLD2"])
_Args.engine_universe = True
_orig_syms = fleet.engine_f_symbols
fleet.engine_f_symbols = lambda day=None: ["NEW1", "NEW2", "NEW3"]
try:
    check("with the flag, the INSTALLED file's ranking wins over the baked list",
          AL.cycle_universe(_Args()) == ["NEW1", "NEW2", "NEW3"])
    fleet.engine_f_symbols = lambda day=None: (_ for _ in ()).throw(
        F.EngineDeclined("no file"))
    check("and a file that cannot be read falls back LOUDLY to the baked list",
          AL.cycle_universe(_Args()) == ["OLD1", "OLD2"],
          "the brain still refuses every name outside the month it verified")
finally:
    fleet.engine_f_symbols = _orig_syms

plan = (ROOT / "docs" / "DEPLOY_PLAN_2026-09-14.md").read_text(encoding="utf-8")
check("the deploy plan no longer INSTRUCTS a monthly redeploy",
      "python -m scripts.fleet --deploy hack3 --up\n\n## 8" not in plan)
check("the deploy plan names the route that replaced it",
      "/engines/F_seasonality_<YYYY-MM>.json" in plan and "engine_sync.py" in plan)
check("the deploy plan names the one case still manual",
      "correction" in plan.lower() and "delete the volume copy" in plan)
check("...and gives a command to VERIFY the rollover rather than assume it",
      "verified months" in plan and "ENGINE SYNC" in plan)

# The brain must not have grown an order path on the way.
brain_src = (ROOT / "alpha" / "brains" / "seasonality_f.py").read_text(encoding="utf-8")
tree = ast.parse(brain_src)
strings = [n.value for n in ast.walk(tree)
           if isinstance(n, ast.Constant) and isinstance(n.value, str)]
docstrings = set()
for node in ast.walk(tree):
    if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
        body = list(getattr(node, "body", []))
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            docstrings.add(id(body[0].value))
code_strings = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and id(n) not in docstrings]
check("the brain still names no order endpoint in its EXECUTABLE code",
      not any("/v2/orders" in s for s in code_strings),
      "read the AST and skip docstrings -- a grep here would match the "
      "sentence that explains the ban")
check("and engine_sync has no broker import at all",
      "alpha.broker" not in (ROOT / "scripts" / "engine_sync.py").read_text(encoding="utf-8"))
check("engine_sync's hash is byte-identical to the brain's",
      S._canonical_sha(_engine("2026-09")) == F._sha_of(_engine("2026-09")))
check("...and to the authority's", S._canonical_sha(_engine("2026-09"))
      == __import__("scripts.prediction_book", fromlist=["x"])._sha(
          {k: v for k, v in _engine("2026-09").items() if k != "content_sha256"}))
check("the new fetch hook is DOCUMENTED as relaxing nothing, and the doc survives",
      any("IT RELAXES NOTHING" in s for s in strings)
      and not any("IT RELAXES NOTHING" in s for s in code_strings),
      "the sentence lives in a docstring, which is where a reader looks and where "
      "an AST-reading guard must not")

os.environ.pop("AAT_LEDGER_DIR", None)

fails = len(_fails)
print(f"\n{'ALL PASS' if not fails else str(fails) + ' FAIL'}")
if fails:
    for f in _fails:
        print(f"  FAILED: {f}")
raise SystemExit(1 if fails else 0)
