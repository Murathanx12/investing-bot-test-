"""The council's roles: each answers ONE question, none is asked "should we buy".

ORDER, AND WHAT EACH ONE IS FORBIDDEN TO DO
===========================================
    FACT_ACCOUNTANT   exact numbers from the company's OWN text, with metric name,
                      basis and period. FORBIDDEN: any view on direction.
    EXPECTATIONS      what the Street/company/chain expected BEFORE the release,
                      from the prior release, headlines and the implied move.
                      FORBIDDEN: reading this release's numbers as expectations.
    SURPRISE_CUBE     deterministic code: facts minus expectations, ONLY where
                      metric, basis and period match. Never an LLM.
    CAUSAL_EXPANSION  who else wins/loses, with SIGN and LAG per edge.
    SKEPTIC           a DIFFERENT family, given the cube WITHOUT the synthesis,
                      asked why the market reaction is rational and what is
                      already priced.
    HISTORICAL_ANALOG deterministic lookup in the measured response curves.
    MARKET_PRICING    deterministic: after-hours move, implied move, band.
    SYNTHESIS         a thesis VECTOR (direction, magnitude, vol, timing,
                      causal confidence, P(already priced), falsifier) -- not
                      an order, not a size, not an instrument.

WHY THE CUBE IS CODE
====================
On 28 Aug the one-shot digest read SentinelOne as "guide lowered -> down" when
the release RAISED revenue and operating-income guidance and LOWERED EPS; and
read a Benzinga line as a Workday revenue cut when it compared prior TOTAL
revenue to new SUBSCRIPTION revenue. A model asked for a direction will find
one. Code that refuses to subtract unlike quantities will not.
"""

from __future__ import annotations

import json
import re
from typing import Any

# --------------------------------------------------------------------------- FACTS

FACT_SYSTEM = (
    "You are a FACT ACCOUNTANT. You extract numbers from a company's own earnings "
    "press release. You have NO opinion on the stock and you never state a direction. "
    "Every number carries: metric (short canonical name), basis (GAAP|non-GAAP|"
    "adjusted|unknown), period (e.g. Q2 FY27, FY27, Q3 FY27), value_low, value_high "
    "(equal if a point), unit (USD|USD_millions|USD_billions|percent|per_share|count), "
    "kind (actual|guide_new|guide_prior|kpi), and an exact short quote from the text."
)

FACT_KEYS = ["metric", "basis", "period", "value_low", "value_high", "unit", "kind", "quote"]


def fact_prompt(symbol: str, text: str, *, prior_text: str | None, max_chars: int = 30000) -> str:
    prior = ("\n\nPRIOR QUARTER RELEASE (for the company's PRIOR guidance only; label those rows "
             f"kind=guide_prior):\n{prior_text[:12000]}") if prior_text else ""
    return (
        f"Company: {symbol}\n\nCURRENT RELEASE:\n{text[:max_chars]}{prior}\n\n"
        "Return {\"rows\": [...], \"share_count_note\": str, \"fx_or_one_off_note\": str} where each "
        "row has exactly the keys: " + ", ".join(FACT_KEYS) + ". Include: reported revenue, "
        "reported EPS (each basis you find), operating income/margin, free cash flow, ARR/RPO/"
        "backlog/bookings/customers if given, capex, buyback/dilution, and EVERY forward guidance "
        "line for the next quarter and the fiscal year (revenue, subscription revenue if separate, "
        "operating income or margin, EPS, share count). If the prior release is given, extract its "
        "guidance lines as kind=guide_prior with the SAME metric names. Numbers only from the text."
    )


def normalise_rows(raw: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for r in raw.get("rows") or []:
        if not isinstance(r, dict):
            continue
        try:
            lo = float(r.get("value_low")); hi = float(r.get("value_high", lo))
        except (TypeError, ValueError):
            continue
        basis = str(r.get("basis", "unknown")).lower().replace("non gaap", "non-gaap").replace("nongaap", "non-gaap")
        metric = _canon_metric(str(r.get("metric", "")))
        if metric == "eps_gaap" and basis.startswith(("non-gaap", "adjusted")):
            metric = "eps_non_gaap"          # the basis field is authoritative over the name
        out.append({
            "metric": metric,
            "basis": basis,
            "period": str(r.get("period", "")).upper().replace("FISCAL ", "FY").replace(" ", ""),
            "value_low": min(lo, hi), "value_high": max(lo, hi),
            "unit": str(r.get("unit", "")), "kind": str(r.get("kind", "")).lower(),
            "quote": str(r.get("quote", ""))[:200],
        })
    return out


_METRIC_MAP = [
    # Margins BEFORE the nouns they qualify: "subscription ARR contribution
    # margin" is a margin, not ARR (RBRK, 28 Aug: it collided with the ARR row).
    (r"contribution margin", "contribution_margin"),
    (r"subscription.*rev", "subscription_revenue"),
    (r"total.*rev|^revenue|net sales|^sales", "revenue"),
    (r"non.?gaap.*eps|adj.*eps|eps.*non.?gaap|diluted.*per share.*non|non.?gaap.*per share", "eps_non_gaap"),
    (r"gaap.*eps|eps|per share", "eps_gaap"),
    (r"operating margin", "operating_margin"),
    (r"operating income", "operating_income"),
    (r"gross margin", "gross_margin"),
    (r"free cash", "free_cash_flow"),
    (r"\barr\b|annual recurring", "arr"),
    (r"rpo|remaining performance|backlog|bookings", "backlog"),
    (r"capex|capital expend", "capex"),
    (r"share count|diluted shares|weighted.*shares", "share_count"),
    (r"customer", "customers"),
]


def _canon_metric(name: str) -> str:
    n = name.lower().strip()
    for pat, canon in _METRIC_MAP:
        if re.search(pat, n):
            return canon
    return re.sub(r"[^a-z0-9]+", "_", n).strip("_") or "unknown"


# --------------------------------------------------------------------- EXPECTATIONS

EXPECT_SYSTEM = (
    "You are an EXPECTATIONS reconstructor. Your ONLY job is to state what the market "
    "expected BEFORE a company's earnings release: consensus estimates quoted in the "
    "headlines, the company's own prior guidance, and what the option-implied move says "
    "the market was braced for. You must NOT use the released actuals as expectations. "
    "Where a number is not present in the material, write null -- never invent consensus."
)


def expect_prompt(symbol: str, headlines: list[str], prior_release: str | None,
                  implied_move: float | None, pre_event_5d_move: float | None) -> str:
    hl = "\n".join(f"- {h}" for h in headlines[:25]) or "- (none)"
    return (
        f"Company: {symbol}\n"
        f"Option-implied move for the print (fraction of spot): {implied_move if implied_move is not None else 'unknown'}\n"
        f"Price move over the 5 sessions before the print: {pre_event_5d_move if pre_event_5d_move is not None else 'unknown'}\n\n"
        f"HEADLINES around the release (consensus figures appear as 'vs $X Est'):\n{hl}\n\n"
        + (f"PRIOR QUARTER RELEASE (the company's prior guidance):\n{prior_release[:10000]}\n\n" if prior_release else "")
        + "Return {\"consensus\": [ {metric, basis, period, value_low, value_high, unit, source_quote} ... ], "
          "\"prior_guidance\": [ same shape ... ], \"what_the_market_was_braced_for\": str, "
          "\"latent_kpi_guess\": str -- the ONE metric investors most likely keyed on for this name, "
          "\"expectations_confidence\": number in [0,1] }. Use canonical metric names: revenue, "
          "subscription_revenue, eps_non_gaap, eps_gaap, operating_margin, operating_income, arr, backlog."
    )


# ------------------------------------------------------------------------- SURPRISE

def surprise_cube(facts: list[dict[str, Any]], expectations: dict[str, Any]) -> dict[str, Any]:
    """Facts minus expectations, per (metric, basis, period). Deterministic.

    A cell exists ONLY where the metric name AND basis AND period agree between
    the two sides. Anything else is listed under `incomparable` with the reason,
    so a total-revenue prior never gets subtracted from a subscription-revenue
    guide again. Values are midpoints; the relative surprise is mid/expected-1.
    """
    def key(r):
        return (r.get("metric"), (r.get("basis") or "unknown"), r.get("period"))

    def mid(r):
        return (float(r["value_low"]) + float(r["value_high"])) / 2.0

    # Both sides go through the SAME canonicalisation: "Q2 FY27" and "Q2FY27",
    # "Non-GAAP EPS" and "eps_non_gaap" must key identically or nothing matches.
    def norm(r):
        try:
            lo = float(r.get("value_low")); hi = float(r.get("value_high", lo))
        except (TypeError, ValueError):
            return None
        return {"metric": _canon_metric(str(r.get("metric", ""))),
                "basis": str(r.get("basis") or "unknown").lower().replace("non gaap", "non-gaap").replace("nongaap", "non-gaap"),
                "period": str(r.get("period", "")).upper().replace("FISCAL ", "FY").replace(" ", ""),
                "value_low": min(lo, hi), "value_high": max(lo, hi),
                "quote": str(r.get("quote") or r.get("source_quote") or "")[:200]}

    cons = {key(x): x for x in (norm(r) for r in (expectations.get("consensus") or [])) if x}
    prior = {key(x): x for x in (norm(r) for r in (expectations.get("prior_guidance") or [])) if x}
    facts = [{**f, "basis": str(f.get("basis") or "unknown").lower()} for f in facts]
    for r in facts:
        if r.get("kind") == "guide_prior":
            prior.setdefault(key(r), r)

    # A reference whose basis is UNKNOWN (a headline's "vs $X Est" says nothing
    # about GAAP vs non-GAAP) may match a fact of any basis on the same metric
    # and period -- but it is flagged `basis_assumed` on the cell, never silent.
    def lookup(table, k):
        if k in table:
            return table[k], False
        for kk, v in table.items():
            if kk[0] == k[0] and kk[2] == k[2] and (kk[1] in ("unknown", "", None) or k[1] in ("unknown", "", None)):
                return v, True
        return None, False

    cells, incomparable = [], []
    for r in facts:
        k = key(r)
        if r.get("kind") == "actual":
            ref, assumed = lookup(cons, k)
            if ref is not None:
                cells.append({**_cell("actual_vs_consensus", r, ref, mid), "basis_assumed": assumed})
            else:
                loose = _loose_match(k, cons)
                incomparable.append({"axis": "actual_vs_consensus", "metric": k, "why":
                                     f"no consensus with same basis/period{'; nearest ' + str(loose) if loose else ''}"})
        elif r.get("kind") == "guide_new":
            ref, assumed = lookup(prior, k)
            if ref is not None:
                cells.append({**_cell("guide_vs_prior_guide", r, ref, mid), "basis_assumed": assumed})
            else:
                loose = _loose_match(k, prior)
                incomparable.append({"axis": "guide_vs_prior_guide", "metric": k, "why":
                                     f"no prior guide with same metric/basis/period{'; nearest ' + str(loose) + ' NOT subtracted' if loose else ''}"})
            ref, assumed = lookup(cons, k)
            if ref is not None:
                cells.append({**_cell("guide_vs_consensus", r, ref, mid), "basis_assumed": assumed})
    return {"cells": cells, "incomparable": incomparable,
            "n_cells": len(cells), "n_incomparable": len(incomparable)}


def _numeric(r) -> bool:
    try:
        float(r.get("value_low")); float(r.get("value_high", r.get("value_low")))
        return True
    except (TypeError, ValueError, AttributeError):
        return False


def _cell(axis, fact, ref, mid):
    f, e = mid(fact), mid(ref)
    rel = (f / e - 1.0) if e else None
    return {"axis": axis, "metric": fact.get("metric"), "basis": fact.get("basis"), "period": fact.get("period"),
            "fact_mid": f, "reference_mid": e, "relative": None if rel is None else round(rel, 4),
            "sign": (0 if rel is None or abs(rel) < 1e-4 else (1 if rel > 0 else -1)),
            "unit": fact.get("unit"), "fact_quote": fact.get("quote", "")[:120],
            "reference_quote": str(ref.get("quote") or ref.get("source_quote") or "")[:120]}


def _loose_match(k, table):
    for kk in table:
        if kk[0] == k[0]:
            return kk
    return None


# ------------------------------------------------------------------------- CAUSAL

CAUSAL_SYSTEM = (
    "You are a CAUSAL EXPANSION analyst. Given the FACTS and the SURPRISE CUBE of one "
    "company's release, name the other listed companies whose economics are moved by it: "
    "suppliers, customers, competitors, bottleneck owners. For EACH edge give economic_sign "
    "(+1/-1), price_sign_expected (+1/-1/0), lag ('same_session'|'days'|'quarters'), "
    "reliability in [0,1] and one sentence of mechanism. Do not recommend trades."
)


def causal_prompt(symbol: str, facts: list[dict], cube: dict, transcript_snips: list[str]) -> str:
    return (f"Company: {symbol}\nFACTS (json): {json.dumps(facts)[:6000]}\nCUBE (json): {json.dumps(cube['cells'])[:3000]}\n"
            f"Named suppliers/customers/bottlenecks in the text:\n" + "\n".join(f"- {s}" for s in transcript_snips[:12]) +
            "\n\nReturn {\"edges\": [ {target_ticker, relation, economic_sign, price_sign_expected, lag, reliability, mechanism} ... ], "
            "\"bottleneck\": str, \"world_state_implied\": str }")


# ------------------------------------------------------------------------- SKEPTIC

SKEPTIC_SYSTEM = (
    "You are the SKEPTIC. You are given the facts, the surprise cube and the observed price "
    "reaction of one company's release, and NOTHING else -- no thesis, no desired answer. "
    "Your job is to explain why the market's reaction is RATIONAL and what is already priced: "
    "which positive-looking cell is low quality (one-offs, FX, share count, comparable "
    "basis), which guide is really below the Street, what the latent KPI was, and what "
    "would have to be true for a contrarian to be right. Rate P(already_priced) in [0,1]."
)


def skeptic_prompt(symbol: str, facts: list[dict], cube: dict, ah_move: float | None, implied_move: float | None) -> str:
    return (f"Company: {symbol}\nObserved after-hours move: {ah_move if ah_move is not None else 'unobservable'}; "
            f"option-implied move: {implied_move if implied_move is not None else 'unknown'}\n"
            f"FACTS: {json.dumps(facts)[:6000]}\nCUBE: {json.dumps(cube)[:4000]}\n\n"
            "Return {\"why_reaction_is_rational\": str, \"low_quality_positives\": [str], "
            "\"latent_kpi\": str, \"p_already_priced\": number in [0,1], "
            "\"contrarian_requires\": str, \"strongest_bear_case\": str, \"strongest_bull_case\": str }")


# ---------------------------------------------------------------- HISTORICAL ANALOG

def historical_analog(symbol: str, ah_move: float | None, *, mega_names: frozenset[str],
                      wide: dict[str, Any] | None, mega: dict[str, Any] | None) -> dict[str, Any]:
    """Deterministic lookup in the measured response curves. No model."""
    if ah_move is None:
        return {"available": False, "why": "no observable day-0 reaction yet"}
    a = abs(ah_move)
    band = "<3.5%" if a < 0.035 else ("3.5-8.2%" if a < 0.082 else ">8.2%")
    sign = "up" if ah_move > 0 else "down"
    if symbol.upper() in mega_names and mega:
        return {"available": True, "population": "MEGA_11 two-sided, excess over beta*QQQ, +1 open -> +3 close",
                "band": band, "sign": sign, "stats": (mega.get("by_arrival") or {}).get("day+1 OPEN  -> +3 close  (a book that woke up late)"),
                "mid_band": (mega.get("mid_band") or {}).get("day+1 OPEN -> +3 close")}
    if wide:
        stats = (wide.get("by_band") or {}).get(band)
        by_sign = (wide.get("by_sign_mid_band") or {}).get(sign) if band == "3.5-8.2%" else None
        return {"available": True, "population": f"wide universe ({wide.get('names_covered_by_sec')} names, {wide.get('legs')} prints), "
                                                 f"excess over {wide.get('benchmark')}, 3 sessions",
                "band": band, "sign": sign, "stats": stats, "by_sign_mid_band": by_sign,
                "note": ("UP prints outside the mega-11 carry no excess (t -1.99 mid band); DOWN prints drift "
                         "further (t 4.29 mid band) and are paid only as a pair vs IWM in simple returns")}
    return {"available": False, "why": "no response curve on disk"}


# ------------------------------------------------------------------------ SYNTHESIS

SYNTH_SYSTEM = (
    "You are the THESIS SYNTHESISER. You receive the outputs of specialists that did not see "
    "each other: facts, expectations, the surprise cube (code), causal edges, a skeptic, a "
    "historical analog and the market's own pricing. Produce a THESIS VECTOR, not a trade: "
    "direction in {up, down, none}; magnitude (fraction of spot over the horizon); "
    "volatility_view in {wider, narrower, unknown} versus the implied move; timing in "
    "{now, days, quarters}; causal_confidence [0,1]; p_already_priced [0,1]; a falsifier "
    "observable within the horizon; and which specialist you weighted most and why. If the "
    "cube has zero comparable cells, direction MUST be none."
)


def synth_prompt(symbol: str, bundle: dict[str, Any]) -> str:
    return (f"Company: {symbol}\nBUNDLE (json): {json.dumps(bundle, default=str)[:14000]}\n\n"
            "Return {\"direction\": str, \"magnitude\": number, \"volatility_view\": str, \"timing\": str, "
            "\"horizon_sessions\": number, \"causal_confidence\": number, \"p_already_priced\": number, "
            "\"falsifier\": str, \"weighted_most\": str, \"one_paragraph\": str }")
