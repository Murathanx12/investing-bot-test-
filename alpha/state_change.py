"""STATE_CHANGE_OPTIONALITY_v1 and LOSER TRIAGE -- SHADOW ONLY (review P4/P5, 2026-08-26).

Two questions the price-only brains cannot ask, both compiled by the LLM from
facts it is GIVEN (it invents none) with the ticker HIDDEN so familiarity cannot
score:

  triage_loser(facts)   -> THESIS_BROKEN | PRICE_OVERREACTION | CANNOT_DETERMINE
      after a large day-0 drop: did the long-run economics deteriorate by as much
      as the price says? The wide-PEAD rule treats every drop alike; HUBS (-19% on
      a beat, +17% back in three weeks) and DKNG say that throws reversals away.

  score_state_change(facts) -> SCO components
      P(transition) x value_if_transition - current, over time-to-resolution and
      the dilution / insolvency / execution penalties. The state graphs are named
      per sector so the compiler must place the company ON one and say which edge
      it is on and what moves it to the next node.

Nothing here orders. Every call writes a row to `state/state_change.jsonl` with
the prompt hash, the model, the cost, the hidden ticker (for grading), and the
`resolve_by` date; `scripts/state_change.py grade` resolves rows against bars.
Base rates matter more than narratives: the compiler is TOLD the measured base
rates it must beat (biotech phase transitions, small-cap dilution frequency) so
"credible future state" has a number to argue against.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alpha.psychohistory import DEEPSEEK_URL, MODEL, PRICE_IN, PRICE_OUT
from alpha.sources.http import SourceRefusal, post_json

STORE = Path("state") / "state_change.jsonl"
ACTION = "SHADOW_ONLY"
TRIAGE_CLASSES = ("THESIS_BROKEN", "PRICE_OVERREACTION", "CANNOT_DETERMINE")

STATE_GRAPHS = {
    "biotech": ["PRECLINICAL", "CLINICAL", "VALIDATED", "APPROVED", "COMMERCIAL"],
    "hardware": ["R&D", "OEM_TESTING", "QUALIFICATION", "CONTRACT", "PRODUCTION", "SCALE"],
    "distressed_asset": ["BLOCKED", "LEGAL_PROGRESS", "PERMITTED", "RESTART", "PRODUCTION"],
    "software": ["DECELERATING", "STABILIZING", "REACCELERATING"],
    "turnaround": ["LOSS", "BREAKEVEN", "POSITIVE_FCF", "OPERATING_LEVERAGE"],
}
#: Published base rates the narrative has to beat (BIO 2011-2020 clinical success
#: by phase; small-cap dilution from the short seller's brief). Stated to the
#: compiler as PRIORS, not as facts about the company.
BASE_RATES = {
    "biotech_phase1_to_approval": 0.079, "biotech_phase2_to_phase3": 0.29, "biotech_phase3_to_approval": 0.58,
    "smallcap_biotech_raises_equity_within_12m": 0.6,
    "note": "BIO/Informa/QLS 2011-2020 phase transition rates; dilution rate is an order-of-magnitude prior",
}

SYSTEM = ("You are a causal compiler for an investment research system. You are given FACTS about an unnamed "
          "company; you must not guess its identity and must not use anything you believe you know about a "
          "specific company. Reason only from the facts and the stated base rates. Reply with ONE JSON object and "
          "nothing else, in English.")


def _blind(facts: list[dict], symbol: str) -> list[dict]:
    """Strip the ticker and obvious names from the facts before the compiler sees them."""
    out = []
    for f in facts:
        text = str(f.get("fact", ""))
        for tok in (symbol, symbol.lower(), symbol.title()):
            text = text.replace(tok, "the company")
        out.append({**f, "fact": text})
    return out


def _call(prompt: str, *, temperature: float = 0.2) -> tuple[dict, dict]:
    key = os.getenv("AAT_DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise SourceRefusal("AAT_DEEPSEEK_API_KEY is not set")
    body = {"model": MODEL, "temperature": temperature, "max_tokens": 3000,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}
    data, dt = post_json(DEEPSEEK_URL, body, headers={"Authorization": f"Bearer {key}"}, timeout=180.0)
    text = data["choices"][0]["message"]["content"]
    non_latin = sum(1 for ch in text if ord(ch) > 0x24F and ch.isalpha()) / max(1, sum(1 for ch in text if ch.isalpha()))
    if non_latin > 0.10:
        raise SourceRefusal("compiler replied in non-Latin script; refused, not repaired")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceRefusal(f"compiler returned non-JSON: {text[:160]!r}") from exc
    usage = data.get("usage") or {}
    llm = {"model": MODEL, "prompt_hash": hashlib.sha256((SYSTEM + prompt).encode()).hexdigest()[:12],
           "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
           "cost_usd": round((usage.get("prompt_tokens", 0) * PRICE_IN + usage.get("completion_tokens", 0) * PRICE_OUT) / 1e6, 6),
           "latency_s": round(dt, 2)}
    return raw, llm


# ---------------------------------------------------------------- loser triage
def triage_prompt(facts: list[dict], day0_move: float, market_context: dict) -> str:
    return (
        f"A company's stock fell {day0_move:+.1%} on its earnings day. Facts (each with a source and date):\n"
        + json.dumps(facts, indent=1)
        + "\nMarket context: " + json.dumps(market_context)
        + "\n\nClassify the drop. Return JSON:\n"
        '{"classification": "THESIS_BROKEN" | "PRICE_OVERREACTION" | "CANNOT_DETERMINE",\n'
        ' "p_overreaction": 0..1,\n'
        ' "fundamental_damage_pct": your estimate of how much the long-run value fell, as a fraction (e.g. -0.08),\n'
        ' "reaction_ratio": |day0 move| / |fundamental_damage_pct| (compute it),\n'
        ' "broken_signals": [facts that say the economics deteriorated],\n'
        ' "overreaction_signals": [facts that say the price fell more than the economics],\n'
        ' "what_would_change_my_mind": [observable checks with dates],\n'
        ' "falsifier_21_sessions": "the price path over 21 sessions that would prove this classification WRONG",\n'
        ' "confidence": 0..1, "reasoning": "<= 80 words"}\n'
        "Rules: if the facts do not contain the forward guidance, the balance sheet, or the unit economics, answer "
        "CANNOT_DETERMINE -- never fill the gap with what companies like this usually do. Be compact."
    )


def triage_loser(symbol: str, facts: list[dict], *, day0_move: float, day0_date: str,
                 market_context: dict | None = None, resolve_sessions: int = 21) -> dict:
    blind = _blind(facts, symbol)
    prompt = triage_prompt(blind, day0_move, market_context or {})
    raw, llm = _call(prompt)
    cls = raw.get("classification")
    if cls not in TRIAGE_CLASSES:
        raise SourceRefusal(f"compiler returned classification {cls!r}; must be one of {TRIAGE_CLASSES}")
    p = raw.get("p_overreaction")
    if not isinstance(p, (int, float)) or not 0 <= p <= 1:
        raise SourceRefusal("p_overreaction missing or outside [0,1]")
    row = {"id": f"SC:TRIAGE:{symbol}:{day0_date}:{uuid.uuid4().hex[:8]}", "kind": "loser_triage", "action": ACTION,
           "asof_utc": datetime.now(timezone.utc).isoformat(), "symbol_hidden_from_compiler": symbol,
           "day0_date": day0_date, "day0_move": round(day0_move, 5), "resolve_sessions": resolve_sessions,
           "facts_n": len(facts), "compiled": raw, "llm": llm, "resolved": None}
    _append(row)
    return row


# ---------------------------------------------------------- state-change score
def sco_prompt(facts: list[dict], graph_key: str, current_price: float) -> str:
    return (
        "Facts about an unnamed company (with sources and dates):\n" + json.dumps(facts, indent=1)
        + f"\nState graph for its kind of business ({graph_key}): {' -> '.join(STATE_GRAPHS[graph_key])}\n"
        + "Base rates you must beat, stated as priors: " + json.dumps(BASE_RATES)
        + f"\nCurrent price: {current_price}\n\nReturn JSON:\n"
        '{"current_state": one node of the graph, "next_state": the next node,\n'
        ' "p_transition_12m": 0..1 (start from the base rate; move it only for a stated fact),\n'
        ' "p_transition_base_rate_used": the prior you started from,\n'
        ' "value_if_transition": price if the transition happens (state the method: multiple, peer, DCF sketch),\n'
        ' "value_if_fail": price if it fails, "time_to_resolution_months": number,\n'
        ' "p_dilution_before_resolution": 0..1, "p_insolvency_before_resolution": 0..1,\n'
        ' "already_priced_in": 0..1 (how much of the transition the current price already assumes),\n'
        ' "catalysts": [{"what": ..., "expected_date": YYYY-MM-DD or null, "observable": where to check}],\n'
        ' "falsifier": "the observation that would collapse p_transition",\n'
        ' "reasoning": "<= 80 words"}\n'
        "If a required number cannot be supported by the facts, set it to null rather than guessing. Be compact."
    )


def sco_components(raw: dict, current_price: float) -> dict:
    """The formula, in code, from the compiler's components -- nulls propagate to null."""
    need = ("p_transition_12m", "value_if_transition", "value_if_fail", "time_to_resolution_months",
            "p_dilution_before_resolution", "p_insolvency_before_resolution", "already_priced_in")
    if any(not isinstance(raw.get(k), (int, float)) for k in need):
        return {"sco": None, "reason": "a component is null; the compiler could not support it from the facts"}
    p, up, dn = raw["p_transition_12m"], raw["value_if_transition"], raw["value_if_fail"]
    ev = p * up + (1 - p) * dn
    edge = (ev - current_price) / current_price
    t_years = max(raw["time_to_resolution_months"], 1) / 12.0
    survival = (1 - raw["p_dilution_before_resolution"] * 0.5) * (1 - raw["p_insolvency_before_resolution"])
    sco = edge * survival * (1 - raw["already_priced_in"]) / t_years
    return {"sco": round(sco, 4), "expected_value": round(ev, 3), "edge_vs_price": round(edge, 4),
            "survival_factor": round(survival, 3), "annualised": True,
            "convexity_yield": round(((up - current_price) / current_price) * p / t_years, 4)}


def score_state_change(symbol: str, facts: list[dict], *, graph_key: str, current_price: float,
                       resolve_by: str) -> dict:
    if graph_key not in STATE_GRAPHS:
        raise SourceRefusal(f"unknown state graph {graph_key!r}; known: {sorted(STATE_GRAPHS)}")
    blind = _blind(facts, symbol)
    raw, llm = _call(sco_prompt(blind, graph_key, current_price))
    if raw.get("current_state") not in STATE_GRAPHS[graph_key]:
        raise SourceRefusal(f"compiler placed the company at {raw.get('current_state')!r}, not on the {graph_key} graph")
    row = {"id": f"SC:SCO:{symbol}:{datetime.now(timezone.utc).date().isoformat()}:{uuid.uuid4().hex[:8]}",
           "kind": "state_change", "action": ACTION, "asof_utc": datetime.now(timezone.utc).isoformat(),
           "symbol_hidden_from_compiler": symbol, "graph": graph_key, "price_at_record": current_price,
           "resolve_by": resolve_by, "facts_n": len(facts), "compiled": raw,
           "components": sco_components(raw, current_price), "llm": llm, "resolved": None}
    _append(row)
    return row


def _append(row: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    with STORE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def read_all() -> list[dict]:
    if not STORE.exists():
        return []
    return [json.loads(l) for l in STORE.read_text(encoding="utf-8").splitlines() if l.strip()]
