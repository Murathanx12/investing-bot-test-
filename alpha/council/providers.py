"""One wire, several model FAMILIES, no broker authority.

DeepSeek, NVIDIA Build and the Hugging Face router all speak OpenAI's
`/chat/completions`. A provider here is a ROW -- base URL, key variable, default
model, family -- so a council role can be pointed at a different family by
changing one string, and the ledger can say which family produced which field.

WHY FAMILIES, NOT MODELS
========================
The council's value is orthogonality: a skeptic drawn from the same weights as
the synthesiser is the synthesiser arguing with itself. `family` is the unit of
independence, and `distinct_families(roles)` is what a test asserts.

MEASURED 2026-08-28 (`docs/ROADMAP_2026-08-28_EXECUTION_AND_HOSTING.md` §10.2)
=================================================================================
    deepseek   deepseek-chat                      ~4 s    live, $14.96 balance
    nvidia     moonshotai/kimi-k3                 2.3 s   live
    nvidia     deepseek-ai/deepseek-v4-*          90 s+   TIMES OUT on the free tier
    nvidia     meta/llama-3.3-70b, nemotron-*     410/404 GONE
    hf         deepseek-ai/DeepSeek-V4-Flash      1.5 s   live, free prepaid account
    hf         openai/gpt-oss-20b                 403     provider not enabled

A row being listed is not a row being live: `probe()` asks each one.

NOTHING HERE PLACES AN ORDER. The module imports no broker code and is imported
by none.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from alpha.sources.http import SourceRefusal
from alpha.spend import SpendRefusal, llm_post


class ProviderRefusal(RuntimeError):
    pass


@dataclass(frozen=True)
class Provider:
    name: str
    family: str
    base_url: str
    key_env: str
    model: str
    timeout: float = 90.0

    def key(self) -> str:
        return os.getenv(self.key_env, "").strip()


PROVIDERS: dict[str, Provider] = {
    "deepseek": Provider("deepseek", "deepseek", "https://api.deepseek.com", "AAT_DEEPSEEK_API_KEY", "deepseek-chat", 120.0),
    "nvidia_kimi": Provider("nvidia_kimi", "moonshot", os.getenv("AAT_NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
                            "AAT_NVIDIA_API_KEY", "moonshotai/kimi-k3", 60.0),
    "nvidia_minimax": Provider("nvidia_minimax", "minimax", os.getenv("AAT_NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
                               "AAT_NVIDIA_API_KEY", "minimaxai/minimax-m3", 60.0),
    "nvidia_gemma": Provider("nvidia_gemma", "google", os.getenv("AAT_NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
                             "AAT_NVIDIA_API_KEY", "google/gemma-4-31b-it", 60.0),
    "hf_deepseek_v4": Provider("hf_deepseek_v4", "deepseek", "https://router.huggingface.co/v1", "AAT_HF_TOKEN",
                               "deepseek-ai/DeepSeek-V4-Flash", 60.0),
    "hf_glm": Provider("hf_glm", "zhipu", "https://router.huggingface.co/v1", "AAT_HF_TOKEN", "zai-org/GLM-5.3-Flash", 60.0),
    # A fourth FAMILY, dormant until AAT_OPENAI_API_KEY exists (Murat's $25 credit,
    # 28 Aug, if that is where it came from). `probe()` reports it as no-key
    # until then; the skeptic role prefers a family the synthesis did not use.
    "openai": Provider("openai", "openai", "https://api.openai.com/v1", "AAT_OPENAI_API_KEY", "gpt-5-mini", 60.0),
}


def _url(p: Provider) -> str:
    base = p.base_url.rstrip("/")
    return base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions" if "deepseek.com" not in base else "/chat/completions")


def _non_latin_share(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    return (sum(1 for c in letters if ord(c) > 0x024F) / len(letters)) if letters else 0.0


def chat_json(provider: str, system: str, user: str, *, caller: str, why: str,
              max_tokens: int = 1200, temperature: float = 0.1) -> tuple[dict[str, Any], dict[str, Any]]:
    """One JSON-object completion. Returns (parsed_object, meta).

    Refuses (never repairs) a non-Latin reply, a non-JSON reply, and a missing
    key. The spend ledger records the call under `caller` with `why`.
    """
    p = PROVIDERS[provider]
    key = p.key()
    if not key:
        raise ProviderRefusal(f"{provider}: {p.key_env} is not set")
    body = {"model": p.model, "temperature": temperature, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system + " Answer ONLY with one JSON object, in English."},
                         {"role": "user", "content": user}]}
    if p.family in ("deepseek",):
        body["response_format"] = {"type": "json_object"}
    t0 = time.time()
    try:
        data, dt = llm_post(_url(p), body, headers={"Authorization": f"Bearer {key}"},
                            caller=caller, why=why, timeout=p.timeout)
    except (SpendRefusal, SourceRefusal) as exc:
        raise ProviderRefusal(str(exc)[:200]) from exc
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        raise ProviderRefusal(f"{provider} ({p.model}): {exc}") from exc
    try:
        text = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderRefusal(f"{provider}: malformed reply {str(data)[:120]!r}") from exc
    if _non_latin_share(text) > 0.10:
        raise ProviderRefusal(f"{provider}: non-Latin reply refused")
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):text.rfind("}") + 1]
    elif not text.startswith("{"):
        i, j = text.find("{"), text.rfind("}")
        text = text[i:j + 1] if i >= 0 and j > i else text
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderRefusal(f"{provider}: non-JSON reply {text[:100]!r}") from exc
    usage = data.get("usage") or {}
    meta = {"provider": provider, "family": p.family, "model": p.model,
            "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
            "latency_s": round(time.time() - t0, 1)}
    return obj, meta


def probe(names: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Which rows answer, and how fast. A listed row is not a live row."""
    out = {}
    for n in names or list(PROVIDERS):
        try:
            obj, meta = chat_json(n, "You are a probe.", 'Return {"ok": true}.', caller="council.probe",
                                  why=("Decides which model families the council may ASSIGN a role to this session: a "
                                       "row that does not answer is skipped, not retried inside a live pass."),
                                  max_tokens=400)   # thinking models spend tokens before the JSON
            out[n] = {"state": "live" if obj.get("ok") else "odd", **meta}
        except ProviderRefusal as exc:
            out[n] = {"state": "down", "why": str(exc)[:120]}
    return out


def distinct_families(providers: list[str]) -> int:
    return len({PROVIDERS[p].family for p in providers if p in PROVIDERS})
