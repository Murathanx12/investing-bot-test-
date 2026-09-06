"""Labor Day Lab lane D — `scripts/connection_check.py`, OFFLINE.

Run only through `python run_tests.py`, which sets the venue guard and blocks
the socket in this process and every child. Nothing here opens one: the HTTP
layer is stubbed and the classification logic is exercised directly.

This file deliberately does NOT name the guard variable and does NOT set it:
`tests_smoke_test_isolation.py` fails the build if any other suite mentions
it, precisely so no suite can quietly re-enable the network. It asks
`alpha.config.test_mode()` instead, and REFUSES to run when the answer is no.

What is pinned, and why each line was earned:

- **A key never leaves the process.** The fingerprint is one-way and the URL is
  redacted before it can enter a receipt.
- **A 403 beside a 200 from the same credential is ENTITLEMENT.** Alpaca's
  `opra` options feed 403s on a plan whose bars answer 200; reading that as a
  dead key sends someone to re-mint six working accounts.
- **A blocked account is not a healthy one.** `/v2/account` answering 200 with
  `trading_blocked: true` is exactly what a book with nothing to buy looks
  like, and the two must never share a row.
- **The private seal URL failing from a laptop is not an outage.**
  `seal-authority.railway.internal` resolves only inside the Railway project.
- **Featherless is not in `alpha/fleet.SECRETS`.** It reaches the services
  because `scripts/fleet.py::deploy` appends the name by hand. A declaration
  that lives in one call site is not a declaration, and this test states the
  fact so a change to either side is visible.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from alpha import config as _cfg                # noqa: E402
from scripts import connection_check as cc      # noqa: E402
from alpha import fleet                         # noqa: E402

CHECKS = 0
FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"  ok   {name}")
    else:
        FAILED.append(f"{name}: {detail}")
        print(f"  FAIL {name}  {detail}")


def stub_http(table: dict[str, int | None]):
    """Replace the HTTP layer with a lookup. NO SOCKET IS OPENED."""
    def fake(url, **kw):
        for needle, code in table.items():
            if needle in url:
                break
        else:
            raise AssertionError(f"unstubbed url: {url}")
        if code is None:
            return {"ok": False, "code": None, "ms": 1.0, "body": "",
                    "class": cc.NETWORK, "why": "TimeoutError: stub",
                    "url": cc._redact_url(url)}
        if 200 <= code < 300:
            body = table.get(needle + "|body", "{}")
            return {"ok": True, "code": code, "ms": 1.0, "body": body,
                    "class": None, "url": cc._redact_url(url)}
        return {"ok": False, "code": code, "ms": 1.0, "body": "",
                "class": cc._classify(code, ""), "why": str(code),
                "url": cc._redact_url(url)}
    return fake


# ── 1. credentials never leave the process ───────────────────────────────────

def suite_no_key_ever_printed() -> None:
    print("suite: no key ever printed")
    # A fixture that cannot be mistaken for a credential by a
    # key-shape grep over the repo. It is 26 chars so the length
    # arithmetic still matches a real Alpaca key id.
    secret = "NOT-A-KEY-fixture-value-01"
    fp = cc.key_fp(secret)
    check("fingerprint excludes the value", secret not in fp, fp)
    for n in (4, 6, 8):
        check(f"fingerprint excludes first {n}", secret[:n] not in fp)
        check(f"fingerprint excludes last {n}", secret[-n:] not in fp)
    check("fingerprint keeps the length", fp.endswith(f"/len{len(secret)}"), fp)
    check("absent key -> None", cc.key_fp(None) is None)
    check("empty key -> None", cc.key_fp("") is None)
    check("equal-length distinct keys differ",
          cc.key_fp("A" * 40) != cc.key_fp("B" * 40))

    for param in ("token", "api_key", "apikey", "secret"):
        url = f"https://v.example/x?symbol=SPY&{param}=SECRET123"
        out = cc._redact_url(url)
        check(f"{param} redacted from url", "SECRET123" not in out, out)
        check(f"{param}: symbol survives", "symbol=SPY" in out, out)

    md = cc.to_markdown({
        "rows": [{"provider": "X", "status": "ok", "latency_ms": 1.0,
                  "entitlement": "granted", "failure_class": None,
                  "key_fingerprint": "sha256:cafebabe/len26"}],
        "counts": {"ok": 1, "fail": 0, "cannot_determine": 0, "total": 1}})
    check("markdown table carries no fingerprint", "cafebabe" not in md, md)


# ── 2. the classifier ────────────────────────────────────────────────────────

def suite_failure_classes() -> None:
    print("suite: failure classes")
    for code, want in ((401, cc.AUTH), (403, cc.ENTITLEMENT), (429, cc.QUOTA),
                       (402, cc.QUOTA), (500, cc.NETWORK), (503, cc.NETWORK),
                       (404, cc.CANNOT)):
        check(f"{code} -> {want}", cc._classify(code, "") == want,
              cc._classify(code, ""))
    check("403 with an invalid-key body is auth",
          cc._classify(403, '{"message":"invalid api key"}') == cc.AUTH)


def suite_alpaca_data_entitlement_vs_dead_key() -> None:
    print("suite: alpaca data — entitlement is not a dead key")
    os.environ["AAT_HACK3_KEY_ID"] = "NOT-A-KEY-fixture-value-h3"
    os.environ["AAT_HACK3_SECRET_KEY"] = "s" * 44
    real = cc.http
    try:
        # Bars and news answer; the options feed 403s. That is a FEED
        # entitlement, and the probe must stay ok while naming it.
        cc.http = stub_http({"/v2/stocks/bars": 200, "/v1beta1/news": 200,
                             "/v1beta1/options/snapshots": 403,
                             "/v1beta1/screener": 200})
        p = cc.probe_alpaca_data()
        check("mixed 200/403 stays ok", p.status == cc.OK, p.detail)
        check("the 403 surface is named NOT entitled",
              "NOT entitled" in p.entitlement and "options" in p.entitlement,
              p.entitlement)
        check("no failure class on an ok row", p.failure_class is None)

        # Every surface refuses the credential -> dead key, not entitlement.
        cc.http = stub_http({"/v2/stocks/bars": 401, "/v1beta1/news": 401,
                             "/v1beta1/options/snapshots": 403,
                             "/v1beta1/screener": 401})
        p = cc.probe_alpaca_data()
        check("all refused -> dead_key", p.failure_class == cc.DEAD_KEY, p.detail)

        # Nothing reachable -> network. Never "no data".
        cc.http = stub_http({"/v2/stocks/bars": None, "/v1beta1/news": None,
                             "/v1beta1/options/snapshots": None,
                             "/v1beta1/screener": None})
        p = cc.probe_alpaca_data()
        check("all timed out -> network", p.failure_class == cc.NETWORK, p.detail)
    finally:
        cc.http = real


def suite_a_blocked_account_is_not_a_healthy_one() -> None:
    print("suite: a blocked account is not a healthy one")
    os.environ["AAT_HACK4_KEY_ID"] = "NOT-A-KEY-fixture-value-h4"
    os.environ["AAT_HACK4_SECRET_KEY"] = "s" * 44
    real = cc.http
    try:
        acct = json.dumps({"status": "ACTIVE", "trading_blocked": True,
                           "account_blocked": False, "equity": "100000",
                           "last_equity": "100000", "cash": "100000"})
        cc.http = stub_http({"/v2/account": 200, "/v2/account|body": acct,
                             "/v2/clock": 200, "/v2/clock|body": '{"is_open":false}',
                             "/v2/positions": 200, "/v2/positions|body": "[]"})
        p = cc.probe_alpaca_role("hack4")
        check("trading_blocked is a FAIL", p.status == "FAIL", p.detail)
        check("and its class is entitlement", p.failure_class == cc.ENTITLEMENT,
              str(p.failure_class))

        acct = json.dumps({"status": "ACTIVE", "trading_blocked": False,
                           "account_blocked": False, "equity": "100000",
                           "last_equity": "100000", "cash": "100000"})
        cc.http = stub_http({"/v2/account": 200, "/v2/account|body": acct,
                             "/v2/clock": 200, "/v2/clock|body": '{"is_open":false}',
                             "/v2/positions": 200, "/v2/positions|body": "[]"})
        p = cc.probe_alpaca_role("hack4")
        check("an unblocked account is ok", p.status == cc.OK, p.detail)
        check("positions are counted, not assumed",
              "positions=0" in p.detail, p.detail)

        # Account ok, positions refused: holdings are UNKNOWN. A book whose
        # holdings cannot be read must not be reported as flat.
        cc.http = stub_http({"/v2/account": 200, "/v2/account|body": acct,
                             "/v2/clock": 200, "/v2/clock|body": '{"is_open":false}',
                             "/v2/positions": 500})
        p = cc.probe_alpaca_role("hack4")
        check("unreadable positions -> CANNOT_DETERMINE",
              p.status == "CANNOT_DETERMINE", p.detail)
    finally:
        cc.http = real


def suite_never_probes_a_live_trading_host() -> None:
    print("suite: never probes a non-paper host")
    os.environ["AAT_HACK1_KEY_ID"] = "NOT-A-KEY-fixture-value-h1"
    os.environ["AAT_HACK1_SECRET_KEY"] = "s" * 44
    prev = os.environ.get("AAT_TRADING_BASE")
    real = cc.http
    try:
        os.environ["AAT_TRADING_BASE"] = "https://api.alpaca.markets"
        cc.http = stub_http({"": 200})     # would answer anything
        p = cc.probe_alpaca_role("hack1")
        check("a live host is refused, not probed",
              p.status == "CANNOT_DETERMINE" and not p.endpoints,
              f"{p.status} endpoints={len(p.endpoints)}")
    finally:
        cc.http = real
        if prev is None:
            os.environ.pop("AAT_TRADING_BASE", None)
        else:
            os.environ["AAT_TRADING_BASE"] = prev


def suite_seal_authority_private_url_is_not_an_outage() -> None:
    print("suite: seal authority")
    real = cc.http
    try:
        # No book for today, but the service answers: a SEAL state.
        # `.json` FIRST: the stub matches by substring and "/" is in every URL.
        cc.http = stub_http({".json": 404, "/": 200})
        p = cc.probe_seal_authority()
        check("no book today is not a connection failure", p.status == cc.OK,
              p.detail)
        check("and it says so in words", "seal state" in p.detail.lower(), p.detail)

        # Nothing answers at all: that IS a connection failure.
        cc.http = stub_http({".json": None, "/": None})
        p = cc.probe_seal_authority()
        check("an unreachable authority fails", p.status == "FAIL", p.detail)
        check("classified network", p.failure_class == cc.NETWORK,
              str(p.failure_class))

        # The private URL is never probed from here.
        check("SEAL_PUBLIC is the public host",
              "railway.internal" not in cc.SEAL_PUBLIC, cc.SEAL_PUBLIC)
    finally:
        cc.http = real


def suite_model_list_shapes() -> None:
    print("suite: model list counting")
    check("openai shape", cc._count_models('{"data":[{"id":"a"},{"id":"b"}]}') == 2)
    check("bare list shape", cc._count_models('[{"id":"a"}]') == 1)
    check("unknown shape is -1, not 0", cc._count_models('{"models":3}') == -1)
    check("unparseable is -1", cc._count_models("<html>") == -1)
    check("-1 renders as words, not as a number",
          "uncountable" in cc._n_str(-1), cc._n_str(-1))


# ── 3. facts about the fleet this probe asserts ──────────────────────────────

def suite_featherless_is_not_in_fleet_secrets() -> None:
    print("suite: featherless declaration gap")
    check("AAT_FEATHERLESS_API_KEY is NOT in alpha/fleet.SECRETS",
          "AAT_FEATHERLESS_API_KEY" not in fleet.SECRETS,
          "if this now passes BY BEING IN SECRETS, delete this test and the "
          "note in probe_featherless — the gap was closed")
    deploy_src = (ROOT / "scripts" / "fleet.py").read_text(encoding="utf-8")
    check("but scripts/fleet.py::deploy pushes it anyway",
          "AAT_FEATHERLESS_API_KEY" in deploy_src,
          "neither SECRETS nor the deploy carries it: the services would have "
          "no Featherless key at all")
    for k in ("AAT_DEEPSEEK_API_KEY", "AAT_FINNHUB_API_KEY", "AAT_FRED_API_KEY",
              "AAT_NVIDIA_API_KEY", "AAT_HF_TOKEN"):
        check(f"{k} is declared in SECRETS", k in fleet.SECRETS)


def suite_registry_is_coherent() -> None:
    print("suite: registry")
    for r in cc.ROLES:
        check(f"alpaca_{r} is registered", f"alpaca_{r}" in cc.PROBES)
    for n in cc.LLM_PROBES:
        check(f"{n} is registered", n in cc.PROBES)
        check(f"{n} can be switched off with --no-llm",
              "llm" in cc.PROBES[n].__code__.co_varnames)
    check("exactly one paid probe lives here", len(cc.LLM_PROBES) == 1,
          str(cc.LLM_PROBES))
    check("the paid probe names a decision",
          len(cc.LLM_WHY) >= 60 and any(v in cc.LLM_WHY.lower()
                                        for v in ("decide", "keep", "drop",
                                                  "refuse", "reconfigure")))
    check("every probe is callable", all(callable(f) for f in cc.PROBES.values()))
    p = cc.Probe("never ran", group="?", why="?")
    check("a probe that never ran is CANNOT_DETERMINE, not ok",
          p.status == "CANNOT_DETERMINE" and p.status != cc.OK, p.status)


def suite_read_only_by_construction() -> None:
    """The read-only claim is checked against EXECUTABLE code, not against the
    file's text. The module docstring says the words "railway up" in order to
    promise it never runs one, and a substring scan over the whole file failed
    on its own promise. Prose is stripped; only statements are read."""
    print("suite: read-only by construction")
    import ast
    path = ROOT / "scripts" / "connection_check.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    # Collect the docstring/bare-expression string nodes BY IDENTITY first.
    # `ast.walk` still visits the Constant inside an Expr after the Expr is
    # skipped, so skipping the parent is not enough — that is exactly how this
    # suite failed its own promise on the first run.
    prose = {id(n.value) for n in ast.walk(tree)
             if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
             and isinstance(n.value.value, str)}
    strings, calls = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str)                 and id(node) not in prose:
            strings.append(node.value)
        if isinstance(node, ast.Call):
            calls.append(node)
    joined = " ".join(strings)
    check("no railway variable is ever set", "--set" not in joined, joined[:120])
    check("no `railway up`", "up" not in [s.strip() for s in strings
                                          if s.strip() in ("up", "redeploy", "down")])
    check("no order path", "/v2/orders" not in joined)
    check("no cancel path", "/v2/positions/" not in joined
          and "DELETE" not in joined)
    subprocess_calls = [c for c in calls
                        if isinstance(c.func, ast.Attribute)
                        and c.func.attr == "run"
                        and isinstance(c.func.value, ast.Name)
                        and c.func.value.id == "subprocess"]
    check("exactly one subprocess call", len(subprocess_calls) == 1,
          str(len(subprocess_calls)))
    if subprocess_calls:
        args = subprocess_calls[0].args[0]
        literal = [a.value for a in getattr(args, "elts", [])
                   if isinstance(a, ast.Constant)]
        check("and it is `railway status`", literal == ["status"], str(literal))


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                            # noqa: BLE001
            pass
    print("tests_smoke_labor_connections")
    if not _cfg.test_mode():
        # A suite that silently runs without the venue block is worse than a
        # suite that does not run: it looks green while the socket is open.
        print("  REFUSED: the venue guard is not set. Run `python run_tests.py`.")
        return 2
    suite_no_key_ever_printed()
    suite_failure_classes()
    suite_alpaca_data_entitlement_vs_dead_key()
    suite_a_blocked_account_is_not_a_healthy_one()
    suite_never_probes_a_live_trading_host()
    suite_seal_authority_private_url_is_not_an_outage()
    suite_model_list_shapes()
    suite_featherless_is_not_in_fleet_secrets()
    suite_registry_is_coherent()
    suite_read_only_by_construction()
    if FAILED:
        print(f"\n{len(FAILED)} FAILED of {CHECKS} checks")
        for f in FAILED:
            print("  -", f)
        return 1
    print(f"\nALL PASS ({CHECKS} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
