"""PSYCHOHISTORY -- the Aegis Causal World Model, shadow-only, v0.

WHAT THIS IS
============
Aegis is good at "does this measured signal survive?" and weak at "what
mechanism is forming in the world before it is a stock signal?". This module
is the hypothesis-generation layer UPSTREAM of the verification machinery. It
holds no trading authority: every record it writes is `action: SHADOW_ONLY`,
and its whole output is a timestamped, falsifiable scenario distribution that
reality later grades.

THE ONE RULE: NEVER NEWS -> TICKER
==================================
    EVENT -> ECONOMIC SHOCK -> BOTTLENECK -> EXPOSURE -> FUNDAMENTAL CHANGE
          -> SURPRISE VS EXPECTATIONS -> MARKET MISPRICING -> INSTRUMENT

"AI demand is enormous" is not a forecast for a print that consensus already
puts at +97% y/y. The compiler must say what the evidence implies RELATIVE to
what the market already expects, and it must say what would prove it wrong.

THE LLM IS A COMPILER, NOT A PICKER
===================================
DeepSeek reads an EVIDENCE BUNDLE (measured facts with sources, the market's
own expectations: consensus, guide, option-implied move, the crowd's ladder,
our brains' widths) and emits STRUCTURE: a causal chain with a confidence and
a lag per edge, a scenario tree whose probabilities sum to one, each scenario's
INTERMEDIATE OBSERVATIONS and the bucket it predicts for the event, a
priced-in estimate, the reasoning templates it used, the falsifiers. It never
emits a trade. Its scenario probabilities are then converted into a
distribution over the same five |move| buckets the option chain implies one
for, so the record can say -- before the outcome -- where the model and the
market disagree, and -- after it -- which of them was better calibrated
(Brier and log score, both stored).

WHAT IS LEARNED
===============
Not the LLM. Every record names the REASONING TEMPLATES it leaned on
(bottleneck-rent, pull-forward-cliff, capex-echo, ...). Over many resolved
records the calibration of each template is a number, and future scenario
probabilities can be weighted by it. That dataset -- timestamped predictions
about the causal structure of the economy, including the ones that never
became trades -- is the asset; the first row is the NVDA print of 26 Aug 2026.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alpha.sources.http import SourceRefusal
from alpha.spend import llm_post

SCHEMA = "PSYCHOHISTORY_v0.1"
STORE = Path(__file__).resolve().parent.parent / "state" / "psychohistory.jsonl"
#: Append-only causal graph: one row per (edge, record). Edges keep their id across records.
GRAPH = Path(__file__).resolve().parent.parent / "state" / "causal_graph.jsonl"

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
PRICE_IN, PRICE_OUT = 0.27, 1.10

#: The event-move buckets a scenario must commit to. The inner edges are the
#: PEAD brain's own terciles (3.5% / 8.2%), so a resolved record grades the
#: same cut the trading rule uses.
BUCKETS: tuple[str, ...] = ("<-8.2%", "-8.2..-3.5%", "-3.5..+3.5%", "+3.5..+8.2%", ">+8.2%")
_EDGES = (-0.082, -0.035, 0.035, 0.082)

#: Reusable causal archetypes the compiler may name. Calibration is tracked PER TEMPLATE.
TEMPLATES: tuple[str, ...] = (
    "bottleneck_rent_migration", "capacity_substitution", "pull_forward_then_cliff",
    "cost_pass_through_chain", "capex_echo", "geopolitical_substitution",
    "infrastructure_shadow_demand", "reflexive_feedback", "cross_country_leading_indicator",
    "contradiction_trading",
)

SYSTEM = (
    "You are the causal compiler of an investment research system. You do NOT recommend trades "
    "and you do NOT output a direction for a stock. You convert an evidence bundle about ONE "
    "scheduled event into STRUCTURE: a causal chain, a scenario tree with probabilities that sum "
    "to 1, what each scenario predicts for the event and for intermediate observations, what is "
    "already priced, and what would falsify each scenario. The central discipline: never go from "
    "news to ticker. Ask what must physically happen if a fact is true, who captures or loses the "
    "economic value as it propagates, and what the market ALREADY expects -- a strong absolute "
    "number that is weaker than expected is a negative surprise. Answer ONLY with one JSON object, "
    "in English, no prose, no markdown fences."
)


@dataclass
class Record:
    schema: str
    id: str
    asof_utc: str
    trigger: dict[str, Any]
    horizon: dict[str, Any]
    evidence: list[dict[str, Any]]
    market_expectation: dict[str, Any]
    compiled: dict[str, Any]
    model_buckets: dict[str, float]
    market_buckets: dict[str, float]
    disagreement: dict[str, Any]
    action: str = "SHADOW_ONLY"
    refusal: str = "PSYCHOHISTORY v0 holds no trading authority; the record exists to be graded."
    llm: dict[str, Any] = field(default_factory=dict)
    outcome: dict[str, Any] | None = None

    def as_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


# ------------------------------------------------------------ provenance (v0.1)
#: Where a fact ultimately comes from. Five articles copying one press release are
#: ONE piece of evidence; a filing, a customs release and a supplier's monthly
#: revenue are three. The origin root is a coarse label the author or collector
#: sets; when absent it is inferred from the source string.
ORIGIN_ROOTS = ("company_filing", "company_statement", "customs", "supplier_report", "price_index",
                "exchange_data", "prediction_market", "analyst_consensus", "newswire", "our_measurement", "other")
_ORIGIN_HINTS = (
    ("sec.gov", "company_filing"), ("8-k", "company_filing"), ("10-q", "company_filing"), ("filing", "company_filing"),
    ("customs", "customs"), ("exports", "customs"), ("census", "customs"),
    ("monthly revenue", "supplier_report"), ("foxconn", "supplier_report"), ("tsmc", "supplier_report"),
    ("polymarket", "prediction_market"), ("kalshi", "prediction_market"),
    ("consensus", "analyst_consensus"), ("preview", "analyst_consensus"), ("tipranks", "analyst_consensus"),
    ("option chain", "exchange_data"), ("alpaca", "exchange_data"), ("bars", "exchange_data"),
    ("state/", "our_measurement"), ("docs/", "our_measurement"), ("our ", "our_measurement"),
    ("reuters", "newswire"), ("bloomberg", "newswire"), ("kiplinger", "newswire"), ("moomoo", "newswire"),
)


def evidence_id(fact: str, source: str) -> str:
    return "E" + hashlib.sha256(f"{source}|{fact}".encode()).hexdigest()[:10]


def origin_root(item: dict) -> str:
    if item.get("origin") in ORIGIN_ROOTS:
        return item["origin"]
    text = f"{item.get('source', '')} {item.get('fact', '')}".lower()
    kind = item.get("kind")
    if kind == "brain" or kind == "chain":
        return "our_measurement" if kind == "brain" else "exchange_data"
    if kind == "crowd":
        return "prediction_market"
    for hint, root in _ORIGIN_HINTS:
        if hint in text:
            return root
    return "other"


def stamp_evidence(evidence: list[dict]) -> list[dict]:
    """Give every item an id and an origin root; drop exact duplicates."""
    seen = set()
    out = []
    for e in evidence:
        eid = evidence_id(str(e.get("fact", "")), str(e.get("source", "")))
        if eid in seen:
            continue
        seen.add(eid)
        out.append({**e, "id": eid, "origin": origin_root(e)})
    return out


def independence(evidence: list[dict]) -> dict:
    roots: dict[str, int] = {}
    for e in evidence:
        roots[e.get("origin", "other")] = roots.get(e.get("origin", "other"), 0) + 1
    newswire = roots.get("newswire", 0)
    return {"items": len(evidence), "origin_roots": roots, "independent_roots": len(roots),
            "newswire_share": round(newswire / max(1, len(evidence)), 3),
            "note": "evidence weight is by ORIGIN ROOT, not by item count; newswire items are rewrites until traced"}


def edge_id(frm: str, to: str, edge: str) -> str:
    key = f"{frm.strip().lower()}|{edge.strip().upper()}|{to.strip().lower()}"
    return "X" + hashlib.sha256(key.encode()).hexdigest()[:10]


def stamp_edges(chain: list[dict]) -> list[dict]:
    out = []
    for e in chain:
        e = dict(e)
        e["edge_id"] = edge_id(str(e.get("from", "")), str(e.get("to", "")), str(e.get("edge", "")))
        out.append(e)
    return out


def upsert_graph(rec_id: str, asof: str, chain: list[dict], graph: Path | None = None) -> int:
    """Append one row per edge to the causal graph. Never rewrites; the graph is its history."""
    path = graph or GRAPH
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a", encoding="utf-8") as fh:
        for e in chain:
            fh.write(json.dumps({"edge_id": e["edge_id"], "from": e.get("from"), "to": e.get("to"), "edge": e.get("edge"),
                                 "confidence": e.get("confidence"), "lag_days": e.get("lag_days"),
                                 "shape": e.get("shape"), "record_id": rec_id, "asof_utc": asof,
                                 "evidence_ids": e.get("evidence_ids") or []}, sort_keys=True) + "\n")
            n += 1
    return n


def graph_summary(graph: Path | None = None) -> dict[str, dict]:
    """Per edge: how many records asserted it, mean confidence, the records, first/last seen."""
    path = graph or GRAPH
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        g = out.setdefault(r["edge_id"], {"from": r["from"], "to": r["to"], "edge": r["edge"], "n_records": 0,
                                          "confidences": [], "records": [], "first_seen": r["asof_utc"], "last_seen": r["asof_utc"]})
        g["n_records"] += 1
        if r.get("confidence") is not None:
            g["confidences"].append(float(r["confidence"]))
        g["records"].append(r["record_id"])
        g["first_seen"] = min(g["first_seen"], r["asof_utc"])
        g["last_seen"] = max(g["last_seen"], r["asof_utc"])
    for g in out.values():
        g["mean_confidence"] = round(sum(g["confidences"]) / len(g["confidences"]), 3) if g["confidences"] else None
        del g["confidences"]
    return out


def checkpoints_due(rec: dict, *, today: str) -> list[dict]:
    """Every intermediate checkpoint whose deadline has passed and which has no grade yet."""
    out = []
    graded = {(c.get("scenario"), c.get("observation")) for c in ((rec.get("outcome") or {}).get("checkpoints") or [])}
    for sc in rec["compiled"]["scenarios"]:
        for c in sc.get("checkpoints") or []:
            if c.get("due") and c["due"] <= today and (sc.get("name"), c.get("observation")) not in graded:
                out.append({"scenario": sc.get("name"), **c})
    return out


# --------------------------------------------------------------------- buckets
def bucket_of(move: float) -> str:
    for edge, name in zip(_EDGES, BUCKETS):
        if move < edge:
            return name
    return BUCKETS[-1]


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def market_buckets(implied_move: float) -> dict[str, float]:
    """The option chain's own probability of each bucket: symmetric normal with
    sigma = implied_move * sqrt(pi/2), the same conversion the sizer uses."""
    if implied_move <= 0:
        return {b: 0.0 for b in BUCKETS}
    sigma = implied_move * math.sqrt(math.pi / 2.0)
    cdfs = [_cdf(e / sigma) for e in _EDGES]
    probs = [cdfs[0], cdfs[1] - cdfs[0], cdfs[2] - cdfs[1], cdfs[3] - cdfs[2], 1.0 - cdfs[3]]
    return {b: round(p, 4) for b, p in zip(BUCKETS, probs)}


def model_buckets(scenarios: list[dict[str, Any]]) -> dict[str, float]:
    """Scenario probabilities folded onto the buckets each scenario commits to.
    A scenario may spread itself over several buckets with weights."""
    out = {b: 0.0 for b in BUCKETS}
    for sc in scenarios:
        p = float(sc.get("p") or 0.0)
        pred = sc.get("predicts") or {}
        spread = pred.get("day0_move_buckets")
        if isinstance(spread, dict) and spread:
            tot = sum(float(v) for v in spread.values()) or 1.0
            for b, w in spread.items():
                if b in out:
                    out[b] += p * float(w) / tot
        else:
            b = pred.get("day0_move_bucket")
            if b in out:
                out[b] += p
    tot = sum(out.values())
    if tot > 0:
        out = {b: round(v / tot, 4) for b, v in out.items()}
    return out


def brier(dist: dict[str, float], realised: str) -> float:
    return round(sum((dist.get(b, 0.0) - (1.0 if b == realised else 0.0)) ** 2 for b in BUCKETS), 4)


def log_score(dist: dict[str, float], realised: str, floor: float = 1e-3) -> float:
    return round(math.log(max(dist.get(realised, 0.0), floor)), 4)


def disagreement(model: dict[str, float], market: dict[str, float]) -> dict[str, Any]:
    diffs = {b: round(model.get(b, 0.0) - market.get(b, 0.0), 4) for b in BUCKETS}
    big = max(diffs.items(), key=lambda kv: abs(kv[1]))
    tail_model = model.get(BUCKETS[0], 0.0) + model.get(BUCKETS[-1], 0.0)
    tail_market = market.get(BUCKETS[0], 0.0) + market.get(BUCKETS[-1], 0.0)
    return {
        "per_bucket": diffs, "largest": {"bucket": big[0], "model_minus_market": big[1]},
        "tail_mass_model": round(tail_model, 4), "tail_mass_market": round(tail_market, 4),
        "up_mass_model": round(model.get(BUCKETS[3], 0.0) + model.get(BUCKETS[4], 0.0), 4),
        "down_mass_model": round(model.get(BUCKETS[0], 0.0) + model.get(BUCKETS[1], 0.0), 4),
        "total_variation": round(0.5 * sum(abs(v) for v in diffs.values()), 4),
    }


# --------------------------------------------------------------------- compile
def build_prompt(trigger: dict, horizon: dict, evidence: list[dict], market: dict) -> str:
    ev_lines = "\n".join(
        f"  - [{e.get('kind', '?')}] {e.get('fact', '')}  (source: {e.get('source', '?')}, {e.get('date', '?')})"
        for e in evidence[:40])
    return (
        f"EVENT: {trigger.get('symbol')} -- {trigger.get('event')} on {trigger.get('event_date')} "
        f"({trigger.get('type')}). Resolve by {horizon.get('resolve_by')}; the day-0 move is the first "
        f"close that reflects the event.\n\n"
        f"WHAT THE MARKET ALREADY EXPECTS (do not restate these as insight):\n"
        f"{json.dumps(market, indent=1)[:3000]}\n\n"
        f"EVIDENCE BUNDLE (measured facts; 'kind' says whether measured, reported, crowd, chain or one of our own brains):\n"
        f"{ev_lines}\n\n"
        f"Reasoning templates you may name (use only the ones you actually relied on): {', '.join(TEMPLATES)}.\n"
        f"Day-0 move buckets you MUST use verbatim: {list(BUCKETS)}.\n\n"
        "Be COMPACT: at most 10 causal edges, 3-5 scenarios, at most 3 falsifiers and 3 intermediate "
        "observations per scenario, one sentence each. The JSON must be complete and parseable.\n"
        "Return a JSON object with EXACTLY these keys:\n"
        '  "causal_chain": list of {"from": str, "to": str, "edge": one of SUPPLIES|CONSUMES|SUBSTITUTES_FOR|COMPETES_WITH|'
        'DEPENDS_ON|EXPORTS_TO|CAPACITY_CONSTRAINED_BY|PRICED_IN|REGULATED_BY|PASSES_COST_TO, "confidence": 0-1, "lag_days": number, '
        '"shape": one of STEP|GRADIENT|CONVEX|CLIFF|LINEAR (how B responds to A), "evidence_ids": list of int (indices into the bundle, 0-based)}\n'
        '  "scenarios": list of 3-5 {"name": str, "p": 0-1 (all p sum to 1), "description": one sentence, '
        '"predicts": {"day0_move_bucket": one bucket string, "day0_move_buckets": optional {bucket: weight}, '
        '"revenue_vs_consensus": below|inline|above, "guide_vs_consensus": below|inline|above, "intermediate_observations": list of str}, '
        '"checkpoints": list of 1-3 {"observation": a specific measurable thing, "expected": what this scenario predicts for it, '
        '"due": YYYY-MM-DD by which it can be checked, "source": where to check} -- intermediate predictions BEFORE the horizon, '
        '"falsifiers": list of str (observable things that would make this scenario much less likely)}\n'
        '  "priced_in": 0-1 -- how much of the evidence the market expectation already reflects\n'
        '  "surprise_axis": one sentence naming the single quantity the event turns on relative to expectations\n'
        '  "second_order": list of 2-5 {"who": entity or sector, "effect": str, "direction": up|down|mixed, "lag_days": number, "confidence": 0-1} -- who captures or loses value as the consequences propagate\n'
        '  "templates_used": list of template names\n'
        '  "candidate_expression": one sentence on the CHEAPEST instrument that would express the largest disagreement, stated as a hypothesis, or "none"\n'
        '  "what_would_change_my_mind": list of str\n'
    )


def compile_with_deepseek(trigger: dict, horizon: dict, evidence: list[dict], market: dict,
                          *, temperature: float = 0.2) -> tuple[dict, dict]:
    key = os.getenv("AAT_DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise SourceRefusal("AAT_DEEPSEEK_API_KEY is not set")
    prompt = build_prompt(trigger, horizon, evidence, market)
    body = {
        "model": MODEL, "temperature": temperature, "max_tokens": 6000,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
    }
    data, dt = llm_post(
        DEEPSEEK_URL, body, headers={"Authorization": f"Bearer {key}"}, timeout=180.0,
        caller="psychohistory.compile",
        why=("Decides whether this event gets a scenario distribution to grade at all, and "
             "which bucket the model disagrees with the chain on -- the disagreement is what "
             "later decides whether a structure is built or refused."))
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    non_latin = sum(1 for ch in text if ord(ch) > 0x24F and ch.isalpha()) / max(1, sum(1 for ch in text if ch.isalpha()))
    if non_latin > 0.10:
        raise SourceRefusal("compiler replied in non-Latin script; refused, not repaired")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceRefusal(f"compiler returned non-JSON: {text[:160]!r}") from exc
    compiled = validate_compiled(raw)
    llm = {"model": MODEL, "prompt_hash": hashlib.sha256((SYSTEM + prompt).encode()).hexdigest()[:12],
           "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
           "cost_usd": round((usage.get("prompt_tokens", 0) * PRICE_IN + usage.get("completion_tokens", 0) * PRICE_OUT) / 1e6, 6),
           "latency_s": round(dt, 2), "temperature": temperature}
    return compiled, llm


def validate_compiled(raw: dict) -> dict:
    """Shape and arithmetic only. The content is the LLM's; the schema is ours."""
    scenarios = raw.get("scenarios")
    if not isinstance(scenarios, list) or not 2 <= len(scenarios) <= 6:
        raise SourceRefusal(f"compiler returned {len(scenarios) if isinstance(scenarios, list) else 'no'} scenarios; need 2-6")
    tot = 0.0
    for sc in scenarios:
        p = float(sc.get("p") or 0.0)
        if not 0.0 <= p <= 1.0:
            raise SourceRefusal(f"scenario {sc.get('name')!r} has p={p}")
        tot += p
        pred = sc.get("predicts") or {}
        b = pred.get("day0_move_bucket")
        spread = pred.get("day0_move_buckets")
        if b not in BUCKETS and not (isinstance(spread, dict) and any(k in BUCKETS for k in spread)):
            raise SourceRefusal(f"scenario {sc.get('name')!r} commits to no known bucket ({b!r})")
        if not sc.get("falsifiers"):
            raise SourceRefusal(f"scenario {sc.get('name')!r} states no falsifier -- a scenario that cannot be wrong is not one")
    if abs(tot - 1.0) > 0.03:
        raise SourceRefusal(f"scenario probabilities sum to {tot:.2f}, not 1")
    # Renormalise the small drift we do accept, so the buckets below sum to one.
    for sc in scenarios:
        sc["p"] = round(float(sc.get("p") or 0.0) / tot, 4)
    chain = raw.get("causal_chain")
    if not isinstance(chain, list) or not chain:
        raise SourceRefusal("compiler returned no causal chain")
    chain = stamp_edges(chain)
    for sc in scenarios:
        cps = []
        for c in sc.get("checkpoints") or []:
            due = str(c.get("due") or "")
            try:
                datetime.fromisoformat(due)
            except ValueError:
                continue                     # a checkpoint with no date cannot come due
            cps.append({"observation": str(c.get("observation", ""))[:200], "expected": str(c.get("expected", ""))[:200],
                        "due": due[:10], "source": str(c.get("source", ""))[:120]})
        sc["checkpoints"] = cps
    used = [t for t in (raw.get("templates_used") or []) if t in TEMPLATES]
    pi = raw.get("priced_in")
    try:
        pi = min(1.0, max(0.0, float(pi)))
    except (TypeError, ValueError):
        raise SourceRefusal("priced_in is not a number")
    return {
        "causal_chain": chain, "scenarios": scenarios, "priced_in": pi,
        "surprise_axis": str(raw.get("surprise_axis") or "")[:400],
        "second_order": raw.get("second_order") or [],
        "templates_used": used,
        "candidate_expression": str(raw.get("candidate_expression") or "none")[:400],
        "what_would_change_my_mind": raw.get("what_would_change_my_mind") or [],
    }


# ---------------------------------------------------------------------- record
def new_id(symbol: str, event_date: str, asof: str) -> str:
    return f"PH:{symbol}:{event_date}:{hashlib.sha256(asof.encode()).hexdigest()[:8]}"


def make_record(trigger: dict, horizon: dict, evidence: list[dict], market: dict,
                compiled: dict, llm: dict, *, asof: str | None = None) -> Record:
    asof = asof or datetime.now(timezone.utc).isoformat()
    evidence = stamp_evidence(evidence)
    mb = model_buckets(compiled["scenarios"])
    kb = market_buckets(float(market.get("implied_move_to_expiry") or 0.0))
    compiled = dict(compiled, causal_chain=stamp_edges(compiled.get("causal_chain") or []),
                    evidence_independence=independence(evidence))
    rec = Record(
        schema=SCHEMA, id=new_id(trigger["symbol"], trigger["event_date"], asof), asof_utc=asof,
        trigger=trigger, horizon=horizon, evidence=evidence, market_expectation=market,
        compiled=compiled, model_buckets=mb, market_buckets=kb, disagreement=disagreement(mb, kb),
        llm=llm,
    )
    return rec


def append(rec: Record, store: Path | None = None, graph: Path | None = None) -> Path:
    path = store or STORE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(rec.as_json() + "\n")
    if rec.outcome is None:
        # A NEW record asserts its edges into the graph; a resolved copy does not re-assert them.
        upsert_graph(rec.id, rec.asof_utc, rec.compiled.get("causal_chain") or [], graph)
    return path


def read_all(store: Path | None = None) -> list[dict]:
    path = store or STORE
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def resolve(rec: dict, *, day0_move: float, reported: dict[str, Any] | None = None,
            pead_3d: float | None = None, notes: str = "") -> dict:
    """Grade a record against what happened. Returns the OUTCOME block (the record is
    appended again with it filled; the original row is never rewritten)."""
    realised = bucket_of(day0_move)
    mb, kb = rec["model_buckets"], rec["market_buckets"]
    scen = rec["compiled"]["scenarios"]
    winner = max(scen, key=lambda s: float(s.get("p") or 0.0)
                 * (1.0 if (s.get("predicts") or {}).get("day0_move_bucket") == realised else 0.0))
    rev_vs = None
    if reported and reported.get("revenue_usd_bn") and rec["market_expectation"].get("consensus_revenue_usd_bn"):
        r, c = float(reported["revenue_usd_bn"]), float(rec["market_expectation"]["consensus_revenue_usd_bn"])
        rev_vs = "above" if r > c * 1.01 else "below" if r < c * 0.99 else "inline"
    per_template = {t: {"brier_model": brier(mb, realised)} for t in rec["compiled"].get("templates_used", [])}
    return {
        "resolved_utc": datetime.now(timezone.utc).isoformat(),
        "day0_move": round(day0_move, 5), "realised_bucket": realised,
        "reported": reported or {}, "revenue_vs_consensus_realised": rev_vs,
        "pead_3d": pead_3d,
        "brier_model": brier(mb, realised), "brier_market": brier(kb, realised),
        "log_model": log_score(mb, realised), "log_market": log_score(kb, realised),
        "model_beat_market": brier(mb, realised) < brier(kb, realised),
        "scenario_realised": (winner.get("name") if (winner.get("predicts") or {}).get("day0_move_bucket") == realised else None),
        "per_template": per_template, "notes": notes,
    }
