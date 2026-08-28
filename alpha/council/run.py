"""Run the council on one printer. Read-only: it writes a packet and nothing else.

    from alpha.council import run
    packet = run.council(client, "S")

ROLE -> PROVIDER ASSIGNMENT
===========================
Preference lists per role, filtered by a liveness probe at the start of the run.
The skeptic must come from a DIFFERENT family than the synthesiser; if the live
rows cannot satisfy that, the packet says `skeptic_independent: false` rather
than pretending. The bundle handed to the synthesiser contains every specialist's
output; the skeptic never sees the synthesis, and the fact accountant never sees
the price.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from alpha import config
from alpha.council import providers, roles
from alpha.council.providers import ProviderRefusal
from alpha.sources import sec
from alpha.sources.http import SourceRefusal

STATE = Path(os.getenv("AAT_LEDGER_DIR") or "state")

#: Preference order per role. Families: deepseek / moonshot / minimax / google / zhipu.
ROLE_PREFERENCES: dict[str, list[str]] = {
    "fact": ["deepseek", "hf_deepseek_v4", "nvidia_minimax"],
    "expectations": ["nvidia_kimi", "hf_glm", "nvidia_minimax", "hf_deepseek_v4"],
    "causal": ["nvidia_minimax", "nvidia_kimi", "hf_glm", "deepseek"],
    "skeptic": ["hf_glm", "nvidia_kimi", "nvidia_minimax", "hf_deepseek_v4"],
    "synthesis": ["deepseek", "hf_deepseek_v4", "nvidia_kimi", "nvidia_minimax"],
}

MEGA_NAMES = frozenset({"AAPL", "AMD", "AMZN", "AVGO", "GOOGL", "META", "MSFT", "MU", "NVDA", "PANW", "TSLA"})


def assign(live: dict[str, dict[str, Any]], overrides: dict[str, str] | None = None) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for role, prefs in ROLE_PREFERENCES.items():
        forced = (overrides or {}).get(role)
        if forced:
            out[role] = forced
            continue
        out[role] = next((p for p in prefs if live.get(p, {}).get("state") == "live"), None)
    # The skeptic must not share weights with the synthesiser.
    if out["skeptic"] and out["synthesis"] and \
            providers.PROVIDERS[out["skeptic"]].family == providers.PROVIDERS[out["synthesis"]].family:
        alt = next((p for p in ROLE_PREFERENCES["skeptic"] if live.get(p, {}).get("state") == "live"
                    and providers.PROVIDERS[p].family != providers.PROVIDERS[out["synthesis"]].family), None)
        out["skeptic"] = alt or out["skeptic"]
    return out


def _ask(role: str, who: dict[str, str | None], live: dict[str, dict[str, Any]], system: str, user: str,
         *, caller: str, why: str, max_tokens: int, packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ask the assigned provider; on refusal (timeout, truncated JSON, non-Latin)
    fall through the role's remaining LIVE providers. Every attempt is recorded
    on the packet so a fallback is visible, and the provider that answered is
    written back into `who[role]` so `skeptic_independent` reflects reality."""
    tried = []
    order = [who.get(role)] + [p for p in ROLE_PREFERENCES[role] if p != who.get(role) and live.get(p, {}).get("state") == "live"]
    last: Exception | None = None
    for prov in [p for p in order if p]:
        try:
            raw, meta = providers.chat_json(prov, system, user, caller=caller, why=why, max_tokens=max_tokens)
            who[role] = prov
            if tried:
                packet.setdefault("fallbacks", []).append({"role": role, "tried": tried, "answered": prov})
            return raw, meta
        except ProviderRefusal as exc:
            tried.append({"provider": prov, "why": str(exc)[:120]})
            last = exc
    raise ProviderRefusal(f"{role}: every live provider refused: {tried}") from last


def _headlines(client, symbol: str, days: int = 4) -> list[dict[str, Any]]:
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        data = client._request("GET", "/v1beta1/news", base=config.data_url(),
                               params={"symbols": symbol, "limit": 50, "sort": "desc", "start": start,
                                       "include_content": "true"})
    except Exception:                                                   # noqa: BLE001
        return []
    return (data or {}).get("news") or []


def _ah_move(client, symbol: str) -> float | None:
    try:
        d = client._request("GET", "/v2/stocks/snapshots", base=config.data_url(),
                            params={"symbols": symbol, "feed": config.stock_feed()})
        x = d[symbol]
        close, last = float(x["dailyBar"]["c"]), float(x["latestTrade"]["p"])
        lt, bt = x["latestTrade"]["t"], x["dailyBar"]["t"]
        if lt[:10] >= bt[:10] and lt[11:16] > "20:02":
            return last / close - 1.0
    except Exception:                                                   # noqa: BLE001
        pass
    return None


def _pre_event_move(client, symbol: str) -> float | None:
    try:
        start = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
        bars = (client.stock_bars(symbol, start=start).get("bars") or {}).get(symbol) or []
        closes = [float(b["c"]) for b in bars]
        if len(closes) >= 6:
            return closes[-1] / closes[-6] - 1.0
    except Exception:                                                   # noqa: BLE001
        pass
    return None


def _load(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _snips(text: str) -> list[str]:
    import re
    out = []
    for s in re.split(r"(?<=[.;])\s", text):
        if re.search(r"supplier|customer|capacity|hyperscaler|partner|foundry|memory|constraint|shortage|backlog", s, re.I) and 40 < len(s) < 260:
            out.append(s.strip())
        if len(out) >= 12:
            break
    return out


def council(client, symbol: str, *, live: dict[str, dict[str, Any]] | None = None,
            overrides: dict[str, str] | None = None, implied_move: float | None = None,
            light: bool = False) -> dict[str, Any]:
    """`light=True` runs SCOUT, FACT, EXPECTATIONS and the CUBE only -- the
    ATTENTION_ROUTER's cheap pass over many printers; the deep roles run on the
    few the cube singles out."""
    symbol = symbol.upper()
    live = live if live is not None else providers.probe()
    who = assign(live, overrides)
    packet: dict[str, Any] = {"schema": "RESEARCH_COUNCIL_v1", "symbol": symbol,
                              "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                              "roles": who, "steps": {}, "refusals": []}

    def refuse(step: str, exc: Exception) -> None:
        packet["refusals"].append({"step": step, "why": str(exc)[:200]})

    # 1. SCOUT: primary text + headlines + market observables (deterministic)
    try:
        rels = sec.press_releases(symbol, limit=2)
    except SourceRefusal as exc:
        rels = []
        refuse("sec_press_release", exc)
    current = rels[0]["text"] if rels else ""
    prior = rels[1]["text"] if len(rels) > 1 else None
    news = _headlines(client, symbol)
    headlines = [n.get("headline", "") for n in news]
    transcript = next((n for n in news if "transcript" in (n.get("headline") or "").lower()
                       and len(n.get("content") or "") > 5000), None)
    if not current and transcript:
        import re, html as _h
        current = _h.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", transcript["content"])))
        packet["refusals"].append({"step": "fact_source", "why": "no 8-K exhibit; facts read from the transcript"})
    ah = _ah_move(client, symbol)
    pre5 = _pre_event_move(client, symbol)
    packet["steps"]["scout"] = {"releases": [{k: r[k] for k in ("date", "accession", "exhibit_type", "chars", "url")} for r in rels],
                                "n_headlines": len(headlines), "has_transcript": bool(transcript),
                                "ah_move": ah, "pre_event_5d_move": pre5, "implied_move": implied_move}
    if not current:
        packet["verdict"] = "NO_PRIMARY_TEXT"
        return packet

    # 2. FACT ACCOUNTANT (never sees the price)
    facts: list[dict[str, Any]] = []
    if who["fact"]:
        try:
            raw, meta = _ask(
                "fact", who, live, roles.FACT_SYSTEM, roles.fact_prompt(symbol, current, prior_text=prior),
                caller="council.fact", max_tokens=4000, packet=packet,
                why="Decides which guidance cells are COMPARABLE; a metric with no exact prior is refused from the cube, not subtracted.")
            facts = roles.normalise_rows(raw)
            packet["steps"]["facts"] = {"rows": facts, "share_count_note": raw.get("share_count_note"),
                                        "fx_or_one_off_note": raw.get("fx_or_one_off_note"), "llm": meta}
        except ProviderRefusal as exc:
            refuse("fact", exc)

    # 3. EXPECTATIONS (never sees the actuals as expectations)
    expectations: dict[str, Any] = {}
    if who["expectations"]:
        try:
            raw, meta = _ask(
                "expectations", who, live, roles.EXPECT_SYSTEM,
                roles.expect_prompt(symbol, headlines, prior, implied_move, pre5),
                caller="council.expectations", max_tokens=2500, packet=packet,
                why="Decides the reference each fact is graded against; without it the cube has no cells and the synthesis must say none.")
            expectations = raw
            packet["steps"]["expectations"] = {**{k: raw.get(k) for k in ("consensus", "prior_guidance", "what_the_market_was_braced_for",
                                                                        "latent_kpi_guess", "expectations_confidence")}, "llm": meta}
        except ProviderRefusal as exc:
            refuse("expectations", exc)

    # 4. SURPRISE CUBE -- code
    cube = roles.surprise_cube(facts, expectations)
    packet["steps"]["surprise_cube"] = cube

    # 5. CAUSAL EXPANSION
    if who["causal"] and facts and not light:
        try:
            raw, meta = _ask(
                "causal", who, live, roles.CAUSAL_SYSTEM, roles.causal_prompt(symbol, facts, cube, _snips(current)),
                caller="council.causal", max_tokens=2000, packet=packet,
                why="Decides which OTHER names enter the candidate list as proxies, with a sign and lag the grader can score.")
            packet["steps"]["causal"] = {**raw, "llm": meta}
        except ProviderRefusal as exc:
            refuse("causal", exc)

    # 6. SKEPTIC -- different family, no synthesis shown
    if who["skeptic"] and facts and not light:
        try:
            raw, meta = _ask(
                "skeptic", who, live, roles.SKEPTIC_SYSTEM, roles.skeptic_prompt(symbol, facts, cube, ah, implied_move),
                caller="council.skeptic", max_tokens=2000, packet=packet,
                why="Decides P(already priced), which can veto a thesis vector before it is sized; a skeptic from the synthesiser's own family is recorded as not independent.")
            packet["steps"]["skeptic"] = {**raw, "llm": meta}
        except ProviderRefusal as exc:
            refuse("skeptic", exc)

    # 7. HISTORICAL ANALOG -- code over the measured response curves
    packet["steps"]["historical_analog"] = roles.historical_analog(
        symbol, ah, mega_names=MEGA_NAMES, wide=_load(STATE / "pead_wide.json"),
        mega=_load(STATE / "source_pead_horizon.json"))

    # 8. MARKET PRICING -- code
    band = None if ah is None else ("<3.5%" if abs(ah) < 0.035 else "3.5-8.2%" if abs(ah) < 0.082 else ">8.2%")
    packet["steps"]["market_pricing"] = {"ah_move": ah, "band": band, "implied_move": implied_move,
                                         "reaction_vs_implied": (None if ah is None or not implied_move else round(abs(ah) / implied_move, 2)),
                                         "pre_event_5d_move": pre5}

    # 9. SYNTHESIS
    if who["synthesis"] and facts and not light:
        bundle = {k: v for k, v in packet["steps"].items()}
        try:
            raw, meta = _ask(
                "synthesis", who, live, roles.SYNTH_SYSTEM, roles.synth_prompt(symbol, bundle),
                caller="council.synthesis", max_tokens=2500, packet=packet,
                why="Decides the thesis VECTOR a human may adopt via scripts.thesis; direction must be none when the cube has no comparable cell.")
            if cube["n_cells"] == 0:
                raw["direction"] = "none"
                raw["forced_none"] = "cube has zero comparable cells"
            packet["steps"]["synthesis"] = {**raw, "llm": meta}
        except ProviderRefusal as exc:
            refuse("synthesis", exc)

    sk, sy = who["skeptic"], who["synthesis"]
    packet["skeptic_independent"] = bool(sk and sy and providers.PROVIDERS[sk].family != providers.PROVIDERS[sy].family)
    packet["families_used"] = sorted({providers.PROVIDERS[p].family for p in who.values() if p})
    packet["light"] = light
    packet["verdict"] = "OK" if "synthesis" in packet["steps"] else ("LIGHT" if light and facts else "PARTIAL")
    return packet


def write(packet: dict[str, Any]) -> Path:
    day = (datetime.now(timezone.utc) - timedelta(hours=4)).date().isoformat()
    outdir = STATE / "council" / day
    outdir.mkdir(parents=True, exist_ok=True)
    p = outdir / f"{packet['symbol']}.json"
    p.write_text(json.dumps(packet, indent=1, default=str), encoding="utf-8")
    return p
