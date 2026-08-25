"""LLM extraction of NARRATIVE_SHOCK_v1 records. DeepSeek is the provider.

THE CONTRACT
============
The model is asked for NUMBERS on declared axes, never for a trade. Its output
is validated against `schema.AXES`, and the model, prompt hash, tokens and cost
travel on the record so the spend is attributed to a decision. A reply that is
not valid JSON with every axis present is REFUSED (not repaired, not retried in
a loop) and counted -- a silently repaired reply is a number nobody produced.

The system prompt pins the output language because `deepseek-chat` code-switches
to Chinese when it is not told (parent project, measured). It also states the
one thing the parent project learned about narrative: explaining a move after
the fact is trivial; the axes are about what is knowable NOW.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from alpha.narrative import schema
from alpha.sources.http import SourceRefusal, post_json

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
#: USD per 1M tokens, DeepSeek published pricing (cache-miss input / output).
PRICE_IN, PRICE_OUT = 0.27, 1.10

SYSTEM = (
    "You are an information analyst for an options trading engine. You do NOT recommend "
    "trades. You estimate, for ONE news/social item about ONE listed company, a set of "
    "numeric axes describing the item as knowable RIGHT NOW, before any outcome. "
    "Truth and market impact are DIFFERENT variables: a false rumour can move a stock; a "
    "true fact can be ignored. Be willing to say 'probably false, highly market-moving'. "
    "Answer ONLY with a single JSON object, in English, no prose, no markdown fences."
)


def _axes_spec() -> str:
    return "\n".join(f'  "{k}": number in [{lo}, {hi}] -- {desc}' for k, (lo, hi, desc) in schema.AXES.items())


def build_prompt(symbol: str, headline: str, body: str, sources: list[dict[str, Any]],
                 *, context: str = "") -> str:
    src_lines = "\n".join(f"  - {s.get('source', '?')} @ {s.get('created_at', '?')}: {s.get('headline', '')[:160]}"
                          for s in sources[:12])
    return (
        f"Company: {symbol}\nPrimary item headline: {headline}\nItem text: {body[:2500]}\n\n"
        f"Other recent items about {symbol} (for repetition / social proof / disagreement):\n{src_lines}\n\n"
        f"{('Context: ' + context) if context else ''}\n\n"
        "Return a JSON object with EXACTLY these keys:\n"
        f"{_axes_spec()}\n"
        '  "affected_entities": list of tickers plausibly affected (include the company)\n'
        '  "affected_sectors": list of short sector names\n'
        '  "event_type": one of rumour|leak|product|policy|geopolitical|macro|earnings|legal|other\n'
        '  "summary": one sentence, what happened and what is uncertain about it\n'
    )


def extract(symbol: str, headline: str, body: str, sources: list[dict[str, Any]], *,
            context: str = "", observed_at: str | None = None) -> schema.NarrativeShock:
    key = os.getenv("AAT_DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise SourceRefusal("AAT_DEEPSEEK_API_KEY is not set")
    at = observed_at or datetime.now(timezone.utc).isoformat()
    prompt = build_prompt(symbol, headline, body, sources, context=context)
    body_req = {
        "model": MODEL, "temperature": 0.2, "max_tokens": 700,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
    }
    data, dt = post_json(DEEPSEEK_URL, body_req, headers={"Authorization": f"Bearer {key}"})
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    cost = (usage.get("prompt_tokens", 0) * PRICE_IN + usage.get("completion_tokens", 0) * PRICE_OUT) / 1e6

    if _non_latin_share(text) > 0.10:
        raise SourceRefusal("extractor replied in non-Latin script; refused, not repaired")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceRefusal(f"extractor returned non-JSON: {text[:120]!r}") from exc
    axes = schema.validate_axes(raw)

    return schema.NarrativeShock(
        schema=schema.SCHEMA_VERSION,
        event_id=schema.event_id(symbol, headline, at),
        symbol=symbol, headline=headline, summary=str(raw.get("summary", ""))[:400],
        observed_at_utc=at,
        sources=[{k: s.get(k) for k in ("source", "created_at", "headline", "url")} for s in sources[:12]],
        axes=axes,
        affected_entities=[str(x).upper() for x in (raw.get("affected_entities") or [])][:12],
        affected_sectors=[str(x) for x in (raw.get("affected_sectors") or [])][:8],
        event_type=str(raw.get("event_type", "other")),
        llm={"model": MODEL, "prompt_hash": schema.prompt_hash(SYSTEM + prompt),
             "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
             "cost_usd": round(cost, 6), "latency_s": round(dt, 2)},
    )


def _non_latin_share(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for ch in letters if ord(ch) > 0x024F) / len(letters)
