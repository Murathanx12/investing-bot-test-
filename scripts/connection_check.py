"""CONNECTION CHECK (terminal) — one READ-ONLY probe per venue and provider.

    python -m scripts.connection_check                 # table to stdout
    python -m scripts.connection_check --json OUT.json # receipt JSON
    python -m scripts.connection_check --no-llm        # skip the one paid call
    python -m scripts.connection_check --only alpaca_hack4,railway

The finance repo has a twin (`aegis-finance/scripts/connection_check.py`) that
owns the DATA vendors and the research warehouse. This one owns what only this
repo can reach: the six paper accounts, the Alpaca data surfaces the books
trade on, the seal artery, the Railway fleet, and the LLM council's key
inventory.

READ-ONLY, AND THAT IS ENFORCED BY WHAT IS ABSENT
=================================================
Every venue call here is a GET. There is no order path, no cancel path, no
`railway variables --set`, no `railway up`. `alpha.guards` is not needed to
make that true; nothing in this file can construct an order.

NEVER PRINTS A KEY
==================
`key_fp()` is `sha256:<8 hex>/len<N>`. A one-way fingerprint cannot leak from a
committed receipt, and it still answers the question that matters most often —
**is the key in this repo the same object as the key in the other repo** — by
comparison rather than by inspection.

THE ONE PAID CALL
=================
Featherless, five output tokens, through `alpha.spend.llm_post` so it carries a
justification and lands in `state/llm_spend.jsonl`. DeepSeek is probed at
`GET /user/balance` (free, and the balance is the economic truth). NVIDIA, the
HF router and OpenAI are probed with their **model list** only — their paid
5-token probe was spent once from the finance twin, and this script proves it
was the same credential by fingerprint instead of paying twice.

CLASSES, NOT ADJECTIVES
=======================
A failing row names one of: auth · quota · network · entitlement · dead_key ·
absent · cannot_determine. A probe that cannot answer says CANNOT_DETERMINE and
why. A timeout is `network`, never "no data"; a 403 beside a 200 from the same
credential is `entitlement`, never a dead key.

CALLABLE ENTRY POINT
====================
`run_checks()` returns the receipt dict, so `scripts/fleet_health.py` can adopt
it. This file schedules nothing and deploys nothing.
"""

from __future__ import annotations

import argparse
import concurrent.futures as _cf
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
ROLES = ("hack1", "hack2", "hack3", "hack4", "hack5", "hack6")

AUTH, QUOTA, NETWORK = "auth", "quota", "network"
ENTITLEMENT, DEAD_KEY, ABSENT = "entitlement", "dead_key", "absent"
CANNOT, OK = "cannot_determine", "ok"

_TIMEOUT = 25.0
_UA = "Aegis Alpha Terminal connection-check (mrthnabdullaev@gmail.com)"

#: The public seal authority. The services reach it on the Railway private
#: network (`http://seal-authority.railway.internal:8080`), which resolves
#: ONLY inside the project — a laptop probe of that host is EXPECTED to fail
#: and must not be reported as an outage.
SEAL_PUBLIC = "https://seal-authority-production.up.railway.app"

#: The justification the one paid probe carries. `alpha.spend.justify` refuses
#: a reason without a decision verb, on purpose.
LLM_WHY = ("Decides whether to KEEP Featherless in the council's provider order "
           "or DROP it: the skeptic role is required to use a family the "
           "synthesis did not, and if this key no longer buys a completion the "
           "council must be reconfigured rather than silently falling back to "
           "the family it was meant to disagree with.")


def key_fp(value: str | None) -> str | None:
    v = (value or "").strip()
    if not v:
        return None
    return f"sha256:{hashlib.sha256(v.encode('utf-8')).hexdigest()[:8]}/len{len(v)}"


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


class Probe:
    def __init__(self, name: str, *, group: str, why: str) -> None:
        self.name, self.group, self.why = name, group, why
        self.status, self.failure_class = "CANNOT_DETERMINE", CANNOT
        self.latency_ms: float | None = None
        self.entitlement, self.quota_hint = "unknown", None
        self.detail, self.key_fp = "probe did not run", None
        self.endpoints: list[dict[str, Any]] = []

    def as_dict(self) -> dict[str, Any]:
        return {"provider": self.name, "group": self.group, "why": self.why,
                "status": self.status, "failure_class": self.failure_class,
                "latency_ms": (round(self.latency_ms, 1)
                               if self.latency_ms is not None else None),
                "entitlement": self.entitlement, "quota_hint": self.quota_hint,
                "detail": self.detail[:500], "key_fingerprint": self.key_fp,
                "endpoints": self.endpoints}

    def ok(self, detail: str, *, entitlement: str = "granted",
           quota_hint: str | None = None) -> "Probe":
        self.status, self.failure_class = OK, None
        self.detail, self.entitlement, self.quota_hint = detail, entitlement, quota_hint
        return self

    def fail(self, klass: str, detail: str, *, entitlement: str = "unknown") -> "Probe":
        self.status, self.failure_class = "FAIL", klass
        self.detail, self.entitlement = detail, entitlement
        return self

    def cannot(self, detail: str) -> "Probe":
        self.status, self.failure_class = "CANNOT_DETERMINE", CANNOT
        self.detail = detail
        return self


def _redact_url(url: str) -> str:
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return "<unparseable url>"
    if not parts.query:
        return f"{parts.scheme}://{parts.netloc}{parts.path}"
    secretish = ("key", "token", "apikey", "api_key", "secret", "password")
    kept = [(k, "<redacted>" if any(s in k.lower() for s in secretish) else v)
            for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)]
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path,
                                    urllib.parse.urlencode(kept), ""))


def _classify(code: int, body: str) -> str:
    low = (body or "")[:400].lower()
    if code == 401:
        return AUTH
    if code == 403:
        return AUTH if ("invalid" in low and "key" in low) else ENTITLEMENT
    if code in (402, 429):
        return QUOTA
    if 500 <= code < 600:
        return NETWORK
    return CANNOT


def http(url: str, *, headers: dict[str, str] | None = None,
         timeout: float = _TIMEOUT) -> dict[str, Any]:
    h = {"User-Agent": _UA, "Accept": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {"ok": True, "code": r.status,
                    "ms": (time.perf_counter() - t0) * 1000,
                    "body": r.read(256 * 1024).decode("utf-8", "replace"),
                    "class": None, "url": _redact_url(url)}
    except urllib.error.HTTPError as e:
        try:
            body = e.read(16 * 1024).decode("utf-8", "replace")
        except Exception:                                            # noqa: BLE001
            body = ""
        return {"ok": False, "code": e.code, "ms": (time.perf_counter() - t0) * 1000,
                "body": body, "class": _classify(e.code, body),
                "why": str(e.code), "url": _redact_url(url)}
    except Exception as e:                                           # noqa: BLE001
        return {"ok": False, "code": None, "ms": (time.perf_counter() - t0) * 1000,
                "body": "", "class": NETWORK,
                "why": f"{type(e).__name__}: {str(e)[:160]}", "url": _redact_url(url)}


def _rec(p: Probe, label: str, r: dict[str, Any]) -> dict[str, Any]:
    p.endpoints.append({"endpoint": label, "url": r.get("url"), "code": r.get("code"),
                        "ms": round(r.get("ms") or 0, 1), "class": r.get("class"),
                        "why": r.get("why")})
    return r


# ── Alpaca: six accounts, three endpoints each ───────────────────────────────

def _alpaca_headers(role: str) -> tuple[dict[str, str] | None, str | None]:
    k, s = _env(f"AAT_{role.upper()}_KEY_ID"), _env(f"AAT_{role.upper()}_SECRET_KEY")
    if not (k and s):
        return None, None
    return {"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s}, key_fp(k)


def probe_alpaca_role(role: str) -> Probe:
    """`/v2/account`, `/v2/clock`, `/v2/positions` for one paper account.

    The account's `status`, `trading_blocked` and `account_blocked` fields are
    reported because a reachable account is not the same fact as a tradeable
    one, and a book that is blocked at the venue looks exactly like a book with
    nothing to buy.
    """
    p = Probe(f"Alpaca {role}", group="venue", why=f"the {role} paper book")
    h, fp = _alpaca_headers(role)
    p.key_fp = fp
    if not h:
        return p.fail(ABSENT, f"AAT_{role.upper()}_KEY_ID / _SECRET_KEY not set "
                              f"in this process")
    base = _env("AAT_TRADING_BASE") or "https://paper-api.alpaca.markets"
    if not base.startswith("https://paper-api."):
        return p.cannot(f"AAT_TRADING_BASE is not a paper host; refusing to probe it")
    ra = _rec(p, "/v2/account", http(base + "/v2/account", headers=h))
    rc = _rec(p, "/v2/clock", http(base + "/v2/clock", headers=h))
    rp = _rec(p, "/v2/positions", http(base + "/v2/positions", headers=h))
    p.latency_ms = min([x["ms"] for x in (ra, rc, rp) if x.get("ms")] or [0]) or None
    if not ra["ok"]:
        return p.fail(ra["class"] or CANNOT, f"/v2/account {ra.get('code')}: "
                                             f"{str(ra.get('why'))[:120]}")
    try:
        acc = json.loads(ra["body"])
        pos = json.loads(rp["body"]) if rp["ok"] else None
        clk = json.loads(rc["body"]) if rc["ok"] else {}
    except Exception:                                                # noqa: BLE001
        return p.cannot("/v2/account answered 200 with an unparseable body")
    npos = len(pos) if isinstance(pos, list) else None
    summary = {"status": acc.get("status"),
               "trading_blocked": acc.get("trading_blocked"),
               "account_blocked": acc.get("account_blocked"),
               "equity": acc.get("equity"), "last_equity": acc.get("last_equity"),
               "cash": acc.get("cash"), "positions": npos,
               "clock_is_open": clk.get("is_open"),
               "clock_next_open": clk.get("next_open")}
    p.endpoints.append({"endpoint": "summary", "account": summary})
    blocked = bool(acc.get("trading_blocked") or acc.get("account_blocked"))
    if blocked:
        return p.fail(ENTITLEMENT, f"account reachable but BLOCKED at the venue: "
                                   f"{json.dumps(summary)}", entitlement="blocked")
    if npos is None:
        return p.cannot(f"/v2/account ok but /v2/positions returned "
                        f"{rp.get('code')} — holdings CANNOT be determined")
    return p.ok(f"status={summary['status']} equity={summary['equity']} "
                f"positions={npos} market_open={summary['clock_is_open']}",
                entitlement="paper venue")


def probe_alpaca_data() -> Probe:
    """The four data surfaces the books actually read: bars, news, an option
    chain and the screener. One credential, four entitlements — an options
    snapshot 403 while bars answer 200 is a FEED entitlement (`opra` needs Algo
    Trader Plus; `indicative` does not), which is why the row names the feed."""
    p = Probe("Alpaca data", group="venue",
              why="bars, news, options chain, screener")
    h, fp = _alpaca_headers("hack3")
    if not h:
        for r in ROLES:
            h, fp = _alpaca_headers(r)
            if h:
                break
    p.key_fp = fp
    if not h:
        return p.fail(ABSENT, "no role key pair in this process to read data with")
    base = _env("AAT_DATA_BASE") or "https://data.alpaca.markets"
    feed = _env("AAT_STOCK_FEED") or "iex"
    ofeed = _env("AAT_OPTIONS_FEED") or "indicative"
    calls = [
        (f"stocks bars (feed={feed})",
         f"{base}/v2/stocks/bars?symbols=SPY&timeframe=1Day&limit=1&feed={feed}"),
        ("news (v1beta1)", f"{base}/v1beta1/news?symbols=SPY&limit=1"),
        (f"options snapshots (feed={ofeed})",
         f"{base}/v1beta1/options/snapshots/SPY?limit=1&feed={ofeed}"),
        ("screener most-actives",
         f"{base}/v1beta1/screener/stocks/most-actives?top=1"),
    ]
    got, ms = [], []
    for label, url in calls:
        r = _rec(p, label, http(url, headers=h))
        if r["ok"]:
            got.append(label)
            ms.append(r["ms"])
    p.latency_ms = min(ms) if ms else None
    gated = [e["endpoint"] for e in p.endpoints if e["code"] in (401, 402, 403)]
    limited = [e["endpoint"] for e in p.endpoints if e["code"] == 429]
    if not got:
        codes = {e["code"] for e in p.endpoints}
        if codes <= {401, 403}:
            return p.fail(DEAD_KEY, "every data surface refused the credential")
        if None in codes:
            return p.fail(NETWORK, "no data surface reachable")
        return p.cannot(f"no 200 from any data surface: {sorted(codes)}")
    return p.ok(f"{len(got)}/{len(calls)} data surfaces answered",
                entitlement=("granted: " + ",".join(got)
                             + (" | NOT entitled: " + ",".join(gated) if gated else "")),
                quota_hint=("429 on " + ",".join(limited)) if limited else None)


# ── the seal artery ──────────────────────────────────────────────────────────

def probe_seal_authority() -> Probe:
    """Public GET only. The PRIVATE URL the services use
    (`http://seal-authority.railway.internal:8080`) resolves only inside the
    Railway project, so a laptop probe of it is EXPECTED to fail — reporting
    that as an outage is the reason this note exists."""
    p = Probe("seal-authority", group="ours", why="the artery the tracker books read")
    day = date.today().isoformat()
    r_root = _rec(p, "GET / (public)", http(SEAL_PUBLIC + "/", timeout=45))
    r_day = _rec(p, f"GET /{day}.json (public)", http(f"{SEAL_PUBLIC}/{day}.json",
                                                     timeout=45))
    p.latency_ms = min(x["ms"] for x in (r_root, r_day))
    configured = _env("AAT_PREDICTION_BOOK_BASE_URL")
    if configured and "railway.internal" in configured:
        p.endpoints.append({
            "endpoint": "configured base (services)",
            "note": "private Railway DNS; NOT resolvable from a laptop by design"})
    if r_day["ok"]:
        try:
            d = json.loads(r_day["body"])
            return p.ok(f"today's book served: day={d.get('day')!r} "
                        f"portfolios={len(d.get('portfolios') or {})}",
                        entitlement="ours, public read")
        except Exception:                                            # noqa: BLE001
            return p.cannot(f"/{day}.json 200 with an unparseable body")
    if r_root["ok"] or r_root.get("code") in (403, 404):
        return p.ok(f"authority reachable (root {r_root.get('code')}); no book for "
                    f"{day} — a SEAL state, not a connection failure",
                    entitlement="ours, public read")
    return p.fail(r_root["class"] or CANNOT,
                  f"root {r_root.get('code')}: {str(r_root.get('why'))[:140]}")


# ── LLM council ──────────────────────────────────────────────────────────────

def _count_models(body: str) -> int:
    """How many models a `/models` response lists, across the two shapes.

    Featherless answers a bare JSON LIST where OpenAI answers `{"data": [...]}`;
    a parser that only knew the second shape reported "-1 models visible" for a
    provider that had just served a completion. A count that cannot be derived
    returns -1 and the caller must say so rather than print it as a number.
    """
    try:
        d = json.loads(body)
    except Exception:                                                # noqa: BLE001
        return -1
    if isinstance(d, list):
        return len(d)
    if isinstance(d, dict) and isinstance(d.get("data"), list):
        return len(d["data"])
    return -1


def _n_str(n: int) -> str:
    return f"{n} models" if n >= 0 else "an uncountable model list"


def _models_only(p: Probe, url: str, key: str, note: str) -> Probe:
    r = _rec(p, "GET /models", http(url, headers={"Authorization": f"Bearer {key}"}))
    p.latency_ms = r["ms"]
    if not r["ok"]:
        return p.fail(r["class"] or CANNOT, f"{r.get('code')} {str(r.get('why'))[:140]}")
    n = _count_models(r["body"])
    shown = f"{n} models" if n >= 0 else "an uncountable model list"
    return p.ok(f"credential authenticated; {shown} listed. {note}",
                entitlement=f"{shown} VISIBLE — visibility is not a grant")


def probe_deepseek() -> Probe:
    p = Probe("DeepSeek", group="llm", why="first in the council probe order")
    k = _env("AAT_DEEPSEEK_API_KEY")
    p.key_fp = key_fp(k)
    if not k:
        return p.fail(ABSENT, "AAT_DEEPSEEK_API_KEY not set (a BLANK value is how "
                              "a process is routed to Featherless on purpose)")
    r = _rec(p, "GET /user/balance", http("https://api.deepseek.com/user/balance",
                                          headers={"Authorization": f"Bearer {k}"}))
    p.latency_ms = r["ms"]
    if not r["ok"]:
        return p.fail(r["class"] or CANNOT, str(r.get("why")))
    try:
        d = json.loads(r["body"])
        infos = d.get("balance_infos") or []
        bal = ", ".join(f"{i.get('total_balance')} {i.get('currency')}" for i in infos)
    except Exception:                                                # noqa: BLE001
        return p.cannot("200 with an unparseable balance body")
    return p.ok(f"balance endpoint answered; is_available={d.get('is_available')}",
                entitlement="pay-as-you-go", quota_hint=f"balance {bal}")


def probe_nvidia() -> Probe:
    p = Probe("NVIDIA NIM", group="llm", why="council families kimi / minimax / gemma")
    k = _env("AAT_NVIDIA_API_KEY")
    p.key_fp = key_fp(k)
    if not k:
        return p.fail(ABSENT, "AAT_NVIDIA_API_KEY not set")
    base = _env("AAT_NVIDIA_BASE_URL") or "https://integrate.api.nvidia.com/v1"
    return _models_only(p, base.rstrip("/") + "/models", k,
                        "Completion NOT issued here: the paid 5-token probe was "
                        "spent once from the finance twin on the same key "
                        "fingerprint.")


def probe_hf() -> Probe:
    p = Probe("HF router", group="llm", why="council families hf_deepseek_v4 / hf_glm")
    k = _env("AAT_HF_TOKEN")
    p.key_fp = key_fp(k)
    if not k:
        return p.fail(ABSENT, "AAT_HF_TOKEN not set")
    return _models_only(p, "https://router.huggingface.co/v1/models", k,
                        "Completion NOT issued here: spent once from the finance twin.")


def probe_openai() -> Probe:
    p = Probe("OpenAI", group="llm", why="gpt-5-nano extraction, gpt-5-mini judge")
    k = _env("AAT_OPENAI_API_KEY") or _env("GTP_TOKEN") or _env("OPENAI_API_KEY")
    p.key_fp = key_fp(k)
    if not k:
        return p.fail(ABSENT, "none of AAT_OPENAI_API_KEY / GTP_TOKEN / "
                              "OPENAI_API_KEY is set")
    return _models_only(p, "https://api.openai.com/v1/models", k,
                        "Completion NOT issued here: spent once from the finance twin.")


def probe_featherless(*, llm: bool) -> Probe:
    """The one paid call, and the one question about the fleet's secret set.

    `alpha.fleet.SECRETS` does NOT contain `AAT_FEATHERLESS_API_KEY`. That is a
    real gap and it is currently papered over: `scripts/fleet.py::deploy`
    appends the name by hand at line 74. So the key IS on every `aat-loop-*`
    service today, and it is there because ONE call site remembers it rather
    than because the fleet declares it. Anything that reads `SECRETS` — a new
    deploy path, a rotation script, an audit — will miss it.
    """
    p = Probe("Featherless", group="llm", why="fifth family (alibaba/qwen); the skeptic role")
    k = _env("AAT_FEATHERLESS_API_KEY")
    p.key_fp = key_fp(k)
    try:
        from alpha import fleet
        in_secrets = "AAT_FEATHERLESS_API_KEY" in fleet.SECRETS
    except Exception:                                                # noqa: BLE001
        in_secrets = None
    p.endpoints.append({
        "endpoint": "alpha/fleet.py::SECRETS membership",
        "AAT_FEATHERLESS_API_KEY_in_SECRETS": in_secrets,
        "note": ("NOT in SECRETS; scripts/fleet.py::deploy appends it explicitly, "
                 "so it reaches every service anyway. A declaration that lives in "
                 "one call site is not a declaration."
                 if in_secrets is False else "")})
    if not k:
        return p.fail(ABSENT, "AAT_FEATHERLESS_API_KEY not set in this process")
    base = _env("AAT_FEATHERLESS_BASE_URL") or "https://api.featherless.ai/v1"
    model = _env("AAT_FEATHERLESS_MODEL") or "Qwen/Qwen2.5-72B-Instruct"
    r = _rec(p, "GET /models", http(base.rstrip("/") + "/models",
                                    headers={"Authorization": f"Bearer {k}"}))
    p.latency_ms = r["ms"]
    if not r["ok"]:
        return p.fail(r["class"] or CANNOT, f"{r.get('code')} {str(r.get('why'))[:140]}")
    n = _count_models(r["body"])
    if not llm:
        return p.ok(f"credential authenticated; {_n_str(n)} listed "
                    f"(completion skipped: --no-llm)",
                    entitlement=f"{_n_str(n)} visible; in_SECRETS={in_secrets}")
    # THE PAID CALL. Through the spend gate, so it carries a justification and
    # lands in the ledger like every other paid call in this repo.
    try:
        from alpha import spend
        body = {"model": model,
                "messages": [{"role": "system",
                              "content": "Answer in English. One word."},
                             {"role": "user", "content": "Reply with the word: up"}],
                "max_tokens": 5}
        t0 = time.perf_counter()
        data, _dt = spend.llm_post(base.rstrip("/") + "/chat/completions", body,
                                   why=LLM_WHY, caller="scripts.connection_check",
                                   headers={"Authorization": f"Bearer {k}"},
                                   timeout=60.0)
        p.latency_ms = (time.perf_counter() - t0) * 1000
        txt = (data["choices"][0]["message"].get("content") or "").strip()
        usage = data.get("usage") or {}
        p.endpoints.append({"endpoint": f"chat/completions {model}",
                            "usage": usage, "via": "alpha.spend.llm_post"})
        return p.ok(f"5-token completion returned {txt[:24]!r}",
                    entitlement=f"{_n_str(n)} visible; {model} served; "
                                f"in_SECRETS={in_secrets}",
                    quota_hint=f"usage={usage.get('prompt_tokens')}p/"
                               f"{usage.get('completion_tokens')}c")
    except Exception as e:                                           # noqa: BLE001
        msg = str(e)[:220]
        low = msg.lower()
        klass = (QUOTA if "429" in low or "quota" in low or "credit" in low else
                 AUTH if "401" in low else
                 ENTITLEMENT if "403" in low else
                 NETWORK if "timed out" in low or "urlerror" in low else CANNOT)
        return p.fail(klass, f"model list answered ({n} models) but the completion "
                             f"failed: {msg}",
                      entitlement=f"{_n_str(n)} visible; in_SECRETS={in_secrets}")


# ── data vendors this repo carries its OWN copy of the key for ───────────────

def probe_finnhub() -> Probe:
    p = Probe("Finnhub (AAT key)", group="data", why="quotes and the analyst count")
    k = _env("AAT_FINNHUB_API_KEY")
    p.key_fp = key_fp(k)
    if not k:
        return p.fail(ABSENT, "AAT_FINNHUB_API_KEY not set")
    b = "https://finnhub.io/api/v1"
    free = _rec(p, "quote (free)", http(f"{b}/quote?symbol=AAPL&token={k}"))
    prem = _rec(p, "stock/price-target (PREMIUM)",
                http(f"{b}/stock/price-target?symbol=AAPL&token={k}"))
    p.latency_ms = free["ms"]
    if free["ok"]:
        return p.ok("free tier answered",
                    entitlement=("granted: quote"
                                 + ("; NOT entitled: price-target (403)"
                                    if prem.get("code") == 403 else
                                    "; price-target also granted"
                                    if prem["ok"] else
                                    f"; price-target {prem.get('code')}")))
    if free.get("code") in (401, 403):
        return p.fail(DEAD_KEY, f"the FREE endpoint refused the key "
                                f"({free.get('code')})")
    return p.fail(free["class"] or CANNOT, str(free.get("why")))


def probe_fred() -> Probe:
    p = Probe("FRED (AAT key)", group="data", why="macro series the loop reads")
    k = _env("AAT_FRED_API_KEY")
    p.key_fp = key_fp(k)
    if not k:
        return p.fail(ABSENT, "AAT_FRED_API_KEY not set")
    r = _rec(p, "series/VIXCLS", http(
        f"https://api.stlouisfed.org/fred/series?series_id=VIXCLS"
        f"&api_key={k}&file_type=json"))
    p.latency_ms = r["ms"]
    if r["ok"]:
        return p.ok("series endpoint answered", entitlement="public API key")
    return p.fail(r["class"] or CANNOT, f"{r.get('code')} {str(r.get('why'))[:140]}")


# ── Railway ──────────────────────────────────────────────────────────────────

def probe_railway() -> Probe:
    """`railway status` only. No variable is read here and none is written —
    the Tuesday variable audit is `D3`, and it is a separate, attended read."""
    p = Probe("Railway (loving-elegance)", group="ours",
              why="is every fleet service Online / Failed / Sleeping")
    rail = (shutil.which("railway") or shutil.which("railway.cmd")
            or shutil.which("railway.exe"))
    if not rail:
        return p.cannot("railway CLI not on PATH")
    t0 = time.perf_counter()
    try:
        # BYTES: Railway prints status glyphs, and a cp1252 decode raises inside
        # subprocess's reader THREAD — which surfaces as empty stdout, i.e. as
        # "no services", i.e. as a green nothing.
        r = subprocess.run([rail, "status"], cwd=str(ROOT), capture_output=True,
                           timeout=180)
        stdout = r.stdout.decode("utf-8", "replace")
        stderr = r.stderr.decode("utf-8", "replace")
    except Exception as e:                                           # noqa: BLE001
        return p.cannot(f"railway status did not run: {type(e).__name__}: {e}")
    p.latency_ms = (time.perf_counter() - t0) * 1000
    if r.returncode != 0:
        return p.fail(NETWORK, (stderr or stdout).strip()[:200])
    services: dict[str, str] = {}
    for line in stdout.splitlines():
        s = line.strip()
        if not s.startswith("- "):
            continue
        name, low = s[2:].split(":", 1)[0].strip(), s.lower()
        services[name] = ("Online" if "online" in low else
                          "Failed" if "failed" in low else
                          "Sleeping" if "sleep" in low else
                          "Crashed" if "crash" in low else "UNKNOWN")
    p.endpoints.append({"endpoint": "railway status", "services": services})
    if not services:
        return p.cannot("railway status exited 0 and listed no services")
    bad = {k: v for k, v in services.items() if v != "Online"}
    unexpected = {k: v for k, v in bad.items() if k != "aat-loop-staging"}
    if unexpected:
        return p.fail(NETWORK, "not Online: " + "; ".join(
            f"{k}={v}" for k, v in sorted(unexpected.items())), entitlement="ours")
    note = ("aat-loop-staging=Failed, which is EXPECTED and is the only one"
            if services.get("aat-loop-staging") == "Failed" else "all Online")
    return p.ok(f"{len(services)} services; {note}", entitlement="ours")


# ── registry ─────────────────────────────────────────────────────────────────

def _role_probe(role: str) -> Callable[[], Probe]:
    return lambda: probe_alpaca_role(role)


PROBES: dict[str, Callable[..., Probe]] = {
    **{f"alpaca_{r}": _role_probe(r) for r in ROLES},
    "alpaca_data": probe_alpaca_data,
    "seal_authority": probe_seal_authority,
    "deepseek": probe_deepseek,
    "nvidia": probe_nvidia,
    "hf_router": probe_hf,
    "openai": probe_openai,
    "featherless": probe_featherless,
    "finnhub": probe_finnhub,
    "fred": probe_fred,
    "railway": probe_railway,
}

LLM_PROBES = ("featherless",)


def run_checks(*, only: list[str] | None = None, llm: bool = True,
               workers: int = 6) -> dict[str, Any]:
    """Run every probe and return the receipt dict. The callable entry point."""
    from alpha import config as _cfg
    loaded = _cfg.load_env()
    names = [n for n in PROBES if not only or n in only]
    started = datetime.now(timezone.utc)

    def _run(n: str) -> tuple[str, Probe]:
        try:
            fn = PROBES[n]
            return n, (fn(llm=llm) if n in LLM_PROBES else fn())
        except Exception as e:                                       # noqa: BLE001
            return n, Probe(n, group="?", why="?").cannot(
                f"probe raised {type(e).__name__}: {str(e)[:200]}")

    results: dict[str, Probe] = {}
    with _cf.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for n, pr in ex.map(_run, names):
            results[n] = pr

    rows = [results[n].as_dict() for n in names]
    by_class: dict[str, list[str]] = {}
    for r in rows:
        if r["failure_class"]:
            by_class.setdefault(r["failure_class"], []).append(r["provider"])
    return {
        "receipt": "LABOR-D1-CONNECTION-CHECK",
        "repo": "aegis-alpha-terminal",
        "argv": sys.argv[1:],
        "env_vars_loaded_from_dotfile": loaded,
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "llm_probes_enabled": llm,
        "llm_probes_issued": [n for n in names if n in LLM_PROBES] if llm else [],
        "why_this_call_can_change_a_decision": LLM_WHY if llm else None,
        "counts": {"total": len(rows),
                   "ok": sum(1 for r in rows if r["status"] == OK),
                   "fail": sum(1 for r in rows if r["status"] == "FAIL"),
                   "cannot_determine": sum(1 for r in rows
                                           if r["status"] == "CANNOT_DETERMINE")},
        "failure_classes": by_class,
        "rows": rows,
    }


def to_markdown(receipt: dict[str, Any]) -> str:
    out = ["| provider | status | latency | entitlement | failure class |",
           "|---|---|---|---|---|"]
    for r in receipt["rows"]:
        ms = "-" if r["latency_ms"] is None else f"{r['latency_ms']:.0f} ms"
        out.append(f"| {r['provider']} | {r['status']} | {ms} | "
                   f"{(r['entitlement'] or 'unknown').replace('|', '/')[:110]} | "
                   f"{r['failure_class'] or '-'} |")
    c = receipt["counts"]
    out += ["", f"{c['ok']} ok · {c['fail']} FAIL · "
                f"{c['cannot_determine']} CANNOT DETERMINE of {c['total']}"]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", nargs="?", const="-", default=None, metavar="PATH")
    ap.add_argument("--markdown", nargs="?", const="-", default=None, metavar="PATH")
    ap.add_argument("--no-llm", action="store_true",
                    help="skip the one PAID completion (model lists still probed)")
    ap.add_argument("--only", default="", help="comma-separated: " + ",".join(PROBES))
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                            # noqa: BLE001
            pass
    only = [x.strip() for x in a.only.split(",") if x.strip()] or None
    if only:
        bad = [x for x in only if x not in PROBES]
        if bad:
            ap.error(f"unknown probe(s): {bad}; known: {sorted(PROBES)}")
    rec = run_checks(only=only, llm=not a.no_llm, workers=a.workers)
    if a.json is None and a.markdown is None:
        print(to_markdown(rec))
        print()
        for r in rec["rows"]:
            if r["status"] != OK:
                print(f"  {r['status']:<17} {r['provider']:<26} "
                      f"[{r['failure_class']}] {r['detail'][:140]}")
    if a.json:
        blob = json.dumps(rec, indent=1, sort_keys=True, default=str)
        if a.json == "-":
            print(blob)
        else:
            Path(a.json).parent.mkdir(parents=True, exist_ok=True)
            Path(a.json).write_text(blob + "\n", encoding="utf-8")
            print(f"receipt -> {a.json}")
    if a.markdown:
        md = to_markdown(rec)
        if a.markdown == "-":
            print(md)
        else:
            Path(a.markdown).parent.mkdir(parents=True, exist_ok=True)
            Path(a.markdown).write_text(md + "\n", encoding="utf-8")
            print(f"table -> {a.markdown}")
    return 1 if rec["counts"]["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
