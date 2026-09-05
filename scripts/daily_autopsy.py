"""DAILY AUTOPSY -- what won, what lost, and why; graded against what the engine held.

    python -m scripts.daily_autopsy [--top 25] [--no-llm]

Every session, across the WHOLE universe (HIGH_DISPERSION_US_v1, SIP closes):

  1. the best and worst movers over 1 and 5 sessions, with dollar volume,
     cap bucket and industry (Finnhub profile, movers only);
  2. WHY, from what can be measured: had a print in the last 2 sessions
     (market-wide earnings calendar), the top headlines (Alpaca/Benzinga),
     the industry cluster (three movers from one industry is a theme, not
     three stories);
  3. WHY, compiled: DeepSeek reads the measured facts per mover and names the
     reasoning TEMPLATE, one sentence, whether it was KNOWABLE BEFOREHAND and
     from which precursor -- the Micron test -- and one lesson. Never a trade.
     Templates are tallied across days in `state/autopsy_templates.jsonl`,
     which is the table the engine learns from: not "buy what went up" but
     "which kinds of reason explain the winners, and which were visible before";
  4. GRADE the engine: were the movers in today's candidate report (and which
     way), in the old fifteen, in the control holdings? A lane that never
     holds the day's winners is a lane looking under the streetlamp.

Output: `state/autopsy/<date>.json`, a table, and the rolling template tally.
Nothing here places an order or changes a weight; the improvement is that
tomorrow's candidate report is read beside yesterday's autopsy.

A RECEIPT EVERY NIGHT (B3, 2026-09-05)
======================================
This script used to print a one-line complaint, return 1 and write NOTHING,
and it dated its receipt from the last bar it happened to receive -- so a night
with no bars wrote `state/autopsy/None.json`. Both are the same failure: after
the fact, a night that refused and a night that never ran are indistinguishable
on disk, and this script's value is entirely in the count across days.

So: the session day is DERIVED (`alpha.exits.session_day`, the repo's one clock
convention) rather than read off a bar that may not exist, and every exit path
writes `state/autopsy/<day>.json` with a `status` -- `ok`, `EMPTY`, or
`REFUSED` with the reason. An empty night writes a receipt saying it was empty.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpha import config, exits, universe
from alpha.broker.alpaca import AlpacaPaper
from alpha.sources import attention, finnhub
from alpha.sources.http import SourceRefusal
from alpha.spend import llm_post

logger = logging.getLogger(__name__)
OUT = Path("state") / "autopsy"
TALLY = Path("state") / "autopsy_templates.jsonl"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
PRICE_IN, PRICE_OUT = 0.27, 1.10
TEMPLATES = ("earnings_surprise", "guidance_change", "clinical_readout", "regulatory_decision", "m_and_a",
             "bottleneck_rent_migration", "capacity_substitution", "pull_forward_then_cliff", "cost_pass_through_chain",
             "capex_echo", "geopolitical_substitution", "infrastructure_shadow_demand", "reflexive_feedback",
             "cross_country_leading_indicator", "contradiction_trading", "sector_rotation", "index_or_flow",
             "short_squeeze", "dilution_or_financing", "unknown")

SYSTEM = (
    "You are the daily autopsy analyst of an investment research system. You explain, for each of the day's "
    "largest movers, WHY it moved, using ONLY the facts supplied (return, whether it just reported, the "
    "headlines, industry, size). You never recommend a trade. For every mover you must say whether the move was "
    "KNOWABLE BEFOREHAND from an observable precursor -- a scheduled event, a supplier's number, a sector move "
    "the day before -- or not. Prefer 'unknown' over invention. Answer ONLY with one JSON object, in English."
)


def write_receipt(day: str, payload: dict) -> Path:
    """The one writer. Every exit path goes through it, including the refusals."""
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{day}.json"
    path.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return path


def _returns(bars: dict[str, list[dict]], n: int) -> dict[str, float]:
    out = {}
    for s, b in bars.items():
        if len(b) > n:
            c0, c1 = float(b[-1 - n]["c"]), float(b[-1]["c"])
            if c0 > 0:
                out[s] = c1 / c0 - 1.0
    return out


def _headlines(client, symbols: list[str], *, days: int = 3) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    for s in symbols:
        try:
            items = attention.alpaca_news(client, [s], limit=4, start=start)
        except Exception:                                                # noqa: BLE001
            items = []
        out[s] = [str(i.get("headline") or "")[:140] for i in items][:3]
    return out


def compile_why(movers: list[dict], *, session_date: str) -> tuple[dict, dict]:
    key = os.getenv("AAT_DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise SourceRefusal("AAT_DEEPSEEK_API_KEY is not set")
    lines = []
    for m in movers:
        lines.append(f"- {m['symbol']} ({m['side']}): 1d {m['ret_1d']:+.1%}, 5d {m['ret_5d']:+.1%}; ${m['median_dollar_volume'] / 1e6:.0f}M/day; "
                     f"cap {m.get('cap_bucket') or '?'}; industry {m.get('industry') or '?'}; printed_last_2_sessions={m['had_print']}; "
                     f"headlines: {' | '.join(m['headlines']) or 'none'}")
    prompt = (
        f"Session: {session_date}. The day's largest movers in a ~3,000-name US universe, with measured facts:\n"
        + "\n".join(lines) +
        f"\n\nTemplates you may use, verbatim: {list(TEMPLATES)}.\n"
        "Return a JSON object with EXACTLY these keys:\n"
        '  "movers": list of {"symbol": str, "template": one template, "why": one sentence grounded in the supplied facts, '
        '"knowable_before": yes|partly|no, "precursor": the observable thing that existed BEFORE the move, or "none", '
        '"lesson": one short sentence for the engine}\n'
        '  "themes": list of {"theme": str, "symbols": list of str, "template": one template} -- movers that share ONE cause\n'
        '  "day_lesson": one paragraph: what kind of reasoning would have found today\'s winners and avoided the losers, and what would not have\n'
    )
    body = {"model": MODEL, "temperature": 0.2, "max_tokens": 4000, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}
    data, dt = llm_post(
        DEEPSEEK_URL, body, headers={"Authorization": f"Bearer {key}"}, timeout=180.0,
        caller="daily_autopsy.compile",
        why=("Decides which reasoning TEMPLATE is credited for a day's movers and whether a "
             "precursor was knowable before the move -- the tally across days decides which "
             "templates get built into a candidate lane and which are dropped."))
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    raw = json.loads(text)
    by_sym = {}
    for m in raw.get("movers") or []:
        t = m.get("template") if m.get("template") in TEMPLATES else "unknown"
        by_sym[str(m.get("symbol", "")).upper()] = {"template": t, "why": str(m.get("why", ""))[:300],
                                                    "knowable_before": str(m.get("knowable_before", "no")),
                                                    "precursor": str(m.get("precursor", "none"))[:200],
                                                    "lesson": str(m.get("lesson", ""))[:200]}
    llm = {"model": MODEL, "prompt_hash": hashlib.sha256((SYSTEM + prompt).encode()).hexdigest()[:12],
           "cost_usd": round((usage.get("prompt_tokens", 0) * PRICE_IN + usage.get("completion_tokens", 0) * PRICE_OUT) / 1e6, 6),
           "latency_s": round(dt, 2)}
    return {"movers": by_sym, "themes": raw.get("themes") or [], "day_lesson": str(raw.get("day_lesson", ""))[:1500]}, llm


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--no-llm", action="store_true")
    p.add_argument("--day", default=None, help="ET session day (default: derived)")
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING)
    config.load_env()
    # DERIVED, never read off whichever bar arrived. `session_day` is the repo's
    # one ET convention; the bars only CONFIRM it below.
    day = args.day or exits.session_day()
    members = [m for m in universe.load() if not m.etf_like]
    by_sym = {m.symbol: m for m in members}
    if not members:
        path = write_receipt(day, {
            "session": day, "status": "REFUSED", "universe_n": 0, "movers": [],
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "why": ("no universe on disk (`alpha.universe.load()` returned nothing). "
                    "This is a refusal, not a night with no movers -- run "
                    "`python -m scripts.universe --build` and re-run.")})
        print(f"DAILY AUTOPSY {day}: REFUSED -- no universe on disk")
        print(f"  receipt -> {path}")
        return 1
    try:
        client = AlpacaPaper()
        start = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
        bars = client.stock_bars_multi([m.symbol for m in members], start=start)
    except Exception as exc:                                             # noqa: BLE001
        path = write_receipt(day, {
            "session": day, "status": "REFUSED", "universe_n": len(members),
            "movers": [], "generated_utc": datetime.now(timezone.utc).isoformat(),
            "why": f"{type(exc).__name__}: {str(exc)[:300]}",
            "note": "the venue would not answer for bars; nothing about the tape follows"})
        print(f"DAILY AUTOPSY {day}: REFUSED -- {type(exc).__name__}: {str(exc)[:200]}")
        print(f"  receipt -> {path}")
        return 1
    session = max((b[-1]["t"][:10] for b in bars.values() if b), default=None)
    if session is None:
        path = write_receipt(day, {
            "session": day, "status": "EMPTY", "universe_n": len(members), "movers": [],
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "why": (f"the venue returned no usable bar for any of {len(members)} names. "
                    f"An EMPTY night, recorded as one -- and dated {day} from the clock, "
                    f"not from a bar that does not exist.")})
        print(f"DAILY AUTOPSY {day}: EMPTY -- no bars for any name")
        print(f"  receipt -> {path}")
        return 0
    if session != day:
        # Not an error: run after a weekend and the newest session is Friday.
        # Recorded so nobody reads Friday's autopsy as Sunday's.
        print(f"  note: newest venue session is {session}, clock day is {day}; "
              f"the receipt is filed under {session}")
    day = session
    r1, r5 = _returns(bars, 1), _returns(bars, 5)
    # Only names whose last bar IS the session (a stale name is not a mover).
    r1 = {s: v for s, v in r1.items() if bars[s][-1]["t"][:10] == session}
    ranked = sorted(r1.items(), key=lambda kv: kv[1])
    losers, winners = ranked[:args.top], ranked[-args.top:][::-1]
    picks = [(s, r, "WIN") for s, r in winners] + [(s, r, "LOSS") for s, r in losers]
    syms = [s for s, _, _ in picks]

    # measured why
    today = datetime.now(timezone.utc).date()
    # A REFUSAL IS NOT A ZERO. This used to fall back to `printed = set()`, which
    # turned "the calendar would not answer" into "no mover had an earnings
    # print" -- a measurement. Measured 2026-08-31: six roles run in sequence
    # rate-limited Finnhub, and hack1 and hack4 recorded
    # `winners_with_print: 0` while hack2/3/5/6 recorded 3 ON THE SAME DAY. The
    # zero was the refusal, and nothing in the receipt said so.
    #
    # `printed = None` propagates as `had_print: None` -- unknown, not false --
    # and the grade reports CANNOT_DETERMINE instead of a count.
    printed: set[str] | None
    try:
        cal = finnhub.earnings_calendar(start=(today - timedelta(days=4)).isoformat(), end=today.isoformat())
        printed = {(r.get("symbol") or "").upper() for r in cal}
        print_lookup = "ok"
    except SourceRefusal as exc:
        printed, print_lookup = None, f"REFUSED: {exc}"
        print(f"  earnings calendar REFUSED -- had_print is UNKNOWN for every mover, "
              f"not False: {exc}")
    heads = _headlines(client, syms)
    universe.enrich([by_sym[s] for s in syms], max_calls=2 * args.top)

    # what the engine held
    cand_files = sorted((Path("state") / "candidates").glob("*.json"))
    cands = {}
    if cand_files:
        for c in json.loads(cand_files[-1].read_text(encoding="utf-8")).get("candidates", []):
            cands[c["symbol"]] = c.get("direction")

    movers = []
    for s, r, side in picks:
        m = by_sym[s]
        movers.append({"symbol": s, "side": side, "ret_1d": round(r, 4), "ret_5d": round(r5.get(s, 0.0), 4),
                       "median_dollar_volume": m.median_dollar_volume, "dv_bucket": m.dv_bucket,
                       "market_cap_usd": m.market_cap_usd, "cap_bucket": universe.cap_bucket(m.market_cap_usd),
                       "industry": m.industry, "had_print": (s in printed) if printed is not None else None, "headlines": heads.get(s, []),
                       "engine": {"candidate": cands.get(s), "candidate_right_way": (cands.get(s) == ("UP" if side == "WIN" else "DOWN")) if s in cands else None,
                                  "old_universe": s in universe.OLD_UNIVERSE, "control_holding": s in universe.CONTROL_HOLDINGS}})
    # industry clusters among the movers
    clusters: dict[str, list[str]] = {}
    for m in movers:
        if m["industry"]:
            clusters.setdefault(f"{m['side']}:{m['industry']}", []).append(m["symbol"])
    clusters = {k: v for k, v in clusters.items() if len(v) >= 2}

    compiled, llm = None, None
    if not args.no_llm:
        try:
            compiled, llm = compile_why(movers, session_date=session)
        except Exception as exc:                                         # noqa: BLE001
            logger.warning("autopsy compile failed: %s", exc)
            compiled = {"error": f"{type(exc).__name__}: {exc}"}
    for m in movers:
        m["compiled"] = (compiled or {}).get("movers", {}).get(m["symbol"]) if compiled and "movers" in compiled else None

    # CANNOT DETERMINE rather than 0 when the calendar refused -- a guard
    # derives its input or refuses, and a count is a claim that it looked.
    if printed is None:
        n_win_print = n_loss_print = "CANNOT_DETERMINE"
    else:
        n_win_print = sum(1 for m in movers if m["side"] == "WIN" and m["had_print"])
        n_loss_print = sum(1 for m in movers if m["side"] == "LOSS" and m["had_print"])
    grade = {"winners_with_print": n_win_print, "losers_with_print": n_loss_print,
             "print_lookup": print_lookup,
             "winners_in_candidates": sum(1 for m in movers if m["side"] == "WIN" and m["engine"]["candidate"]),
             "losers_in_candidates": sum(1 for m in movers if m["side"] == "LOSS" and m["engine"]["candidate"]),
             "candidates_right_way": sum(1 for m in movers if m["engine"]["candidate_right_way"]),
             "candidates_wrong_way": sum(1 for m in movers if m["engine"]["candidate_right_way"] is False),
             "movers_in_old_universe": sum(1 for m in movers if m["engine"]["old_universe"]),
             "movers_in_control_holdings": [m["symbol"] for m in movers if m["engine"]["control_holding"]],
             "knowable_before": {k: sum(1 for m in movers if (m.get("compiled") or {}).get("knowable_before") == k) for k in ("yes", "partly", "no")}}
    report = {"session": session, "status": "ok" if movers else "EMPTY",
              "generated_utc": datetime.now(timezone.utc).isoformat(), "universe_n": len(members),
              "median_1d_return": round(statistics.median(r1.values()), 4) if r1 else None,
              "movers": movers, "industry_clusters": clusters, "compiled": compiled, "llm": llm, "grade": grade}
    path = write_receipt(session, report)
    if compiled and "movers" in compiled:
        with TALLY.open("a", encoding="utf-8") as fh:
            for m in movers:
                c = m.get("compiled") or {}
                fh.write(json.dumps({"session": session, "symbol": m["symbol"], "side": m["side"], "ret_1d": m["ret_1d"],
                                     "template": c.get("template", "unknown"), "knowable_before": c.get("knowable_before"),
                                     "had_print": m["had_print"], "candidate": m["engine"]["candidate"]}) + "\n")

    print(f"\nDAILY AUTOPSY {session} -- {len(members)} names, median 1d {report['median_1d_return']:+.2%}")
    for side in ("WIN", "LOSS"):
        print(f"  {side}S")
        for m in [x for x in movers if x["side"] == side]:
            c = m.get("compiled") or {}
            cap = f"{m['market_cap_usd'] / 1e9:.1f}B" if m["market_cap_usd"] else "?"
            eng = ("cand:" + str(m["engine"]["candidate"])) if m["engine"]["candidate"] else ("CONTROL" if m["engine"]["control_holding"] else "")
            print(f"    {m['symbol']:6s} {m['ret_1d']:+7.1%} 5d {m['ret_5d']:+7.1%} {cap:>7s} {(m['industry'] or '')[:18]:18s} "
                  f"{'PRINT' if m['had_print'] else '     '} {c.get('template', '-'):26s} knowable:{c.get('knowable_before', '-'):6s} {eng}")
            if c.get("why"):
                print(f"           why: {c['why'][:150]}")
    if clusters:
        print("  industry clusters:", clusters)
    if compiled and compiled.get("themes"):
        for t in compiled["themes"][:6]:
            print(f"  theme: {t.get('theme')} -> {t.get('symbols')} [{t.get('template')}]")
    if compiled and compiled.get("day_lesson"):
        print(f"\n  DAY LESSON: {compiled['day_lesson'][:900]}")
    print(f"\n  GRADE: {grade}")
    tally = {}
    if TALLY.exists():
        for line in TALLY.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            k = (r["side"], r["template"])
            tally[k] = tally.get(k, 0) + 1
    if tally:
        print("  rolling template tally (side, template) -> n:", {f"{k[0]}:{k[1]}": v for k, v in sorted(tally.items(), key=lambda kv: -kv[1])[:12]})
    print(f"  receipt -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
