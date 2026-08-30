"""T13 -- replay an era in a fantasy world and see whether the model is reading.

    python -m scripts.era_replay --windows                     # build them, free
    python -m scripts.era_replay --map                         # freeze the entity map
    python -m scripts.era_replay --rewrite --arm fantasy --limit 30
    python -m scripts.era_replay --decide  --arm fantasy --limit 30
    python -m scripts.era_replay --parity  --limit 30           # BEFORE the full grid
    python -m scripts.era_replay --grade

THE ORDER IS NOT OPTIONAL. `--parity` runs on a small slice before the full
grid, because if the rewriter is supplying the variation then every number the
full grid produces is a number about the rewriter and the money spent
collecting it is wasted.

WHAT EACH ARM COSTS. A window is one (company, month) with that month's new
dated facts. Rewriting is one call per window per rewritten arm; deciding is
one call per window per arm. On `deepseek-chat` a window costs about $0.0004,
so a 600-window era across four arms is roughly $1.50. `--max-usd` binds.

NOTHING HERE PLACES AN ORDER.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from alpha import config, transpose as TP  # noqa: E402
from alpha.council import providers  # noqa: E402
from alpha.sources import corpus  # noqa: E402

STORE = ROOT / "state" / "era_replay"
PANEL = corpus.CORPUS / "features"
RELEVANCE = corpus.CORPUS / "relevance"

REWRITER = "openai"          # gpt-5-mini
DECIDER = "deepseek"         # a DIFFERENT family, so it is not reading its own prose
HORIZON_SESSIONS = 21
BENCH = "SPY"

WHY_REWRITE = ("Builds the fantasy arm of T13, which decides whether the LLB adds "
               "anything over the rule and therefore whether we build a council into "
               "the live book at all.")
WHY_DECIDE = ("Produces the graded forecasts that select the top-k basket in the T13 "
              "replay, which decides whether an LLM reading news earns a place in the "
              "live selection chain.")

REWRITE_SYSTEM = (
    "You rewrite a bundle of financial news into a FICTIONAL world, preserving its "
    "causal shape exactly. "
    "You will be given a mapping from real entities to fictional ones and a year offset. "
    "Apply the mapping consistently. Replace every company, person, place, country, "
    "index, regulator and product name with a fictional equivalent; move every date by "
    "the year offset. "
    "PRESERVE EVERY NUMBER EXACTLY as written -- percentages, dollar amounts, counts, "
    "ratios, multiples, ratings. Do not round, convert, add or remove a single figure. "
    "Preserve the ORDER of events, the causal links between them, whether each outcome "
    "beat or missed an expectation, and the tone. "
    "Do not add analysis, do not add a conclusion, and never say what happened next. "
    "Answer ONLY with one JSON object: {\"rewritten\": \"...\"}. English only."
)

ANON_SYSTEM = (
    "You rewrite a bundle of financial news so that no company, person or product can "
    "be identified, while leaving the YEAR and the INDUSTRY intact. "
    "Replace each named entity with the neutral label given in the mapping. "
    "PRESERVE EVERY NUMBER EXACTLY, and the order, causality and tone of events. "
    "Do not add analysis and never say what happened next. "
    "Answer ONLY with one JSON object: {\"rewritten\": \"...\"}. English only."
)

DECIDE_SYSTEM = (
    "You are a portfolio analyst reading one company's recent news. "
    "You must return a forecast for EVERY company you are shown. Refusing, abstaining "
    "or answering 'I don't know' is not available: uncertainty is expressed as "
    "p_up_21d near 0.5 with a low confidence, never as a missing answer. "
    "p_up_21d: probability this company's shares are higher in 21 trading sessions than "
    "now, RELATIVE to the broad market. "
    "exp_return: your expected relative return over those 21 sessions, as a decimal. "
    "downside_5pct: the relative loss you would put at the 5th percentile, as a NEGATIVE "
    "decimal. confidence: 0 to 1, how much you trust your own read. "
    "reason: one sentence naming the specific fact you used. "
    "Answer ONLY with one JSON object with keys p_up_21d, exp_return, downside_5pct, "
    "confidence, horizon, reason. English only."
)


def _p(*parts) -> Path:
    return STORE.joinpath(*parts)


def load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


# --------------------------------------------------------------- the windows

def sessions_for(symbol: str) -> list[dict]:
    f = PANEL / f"bars_{symbol}.json"
    if not f.exists():
        return []
    try:
        return json.load(f.open(encoding="utf-8")).get("bars") or []
    except (OSError, ValueError):
        return []


def build_windows(era_start: str, era_end: str, limit: int | None) -> int:
    """One window per (company, month) that has at least one NEW DATED FACT.

    A window with no new fact is not a window: every arm would be shown an empty
    page and would return the same prior, and the run would measure the prior.
    """
    STORE.mkdir(parents=True, exist_ok=True)
    labels: list[dict] = []
    for shard in sorted(RELEVANCE.glob("*.jsonl")):
        if shard.stem < era_start[:7] or shard.stem > era_end[:7]:
            continue
        labels += load_jsonl(shard)
    facts = [r for r in labels if r.get("role") == "subject" and r.get("is_new_fact")]
    print(f"relevance labels in the era: {len(labels):,}  new dated facts: {len(facts):,}")

    uids = {r["uid"] for r in facts if r.get("uid")}
    body = {r["uid"]: r for r in corpus.read(since=era_start, until=era_end)
            if r.get("uid") in uids}
    print(f"corpus items matched to those labels: {len(body):,}")

    bench = sessions_for(BENCH)
    if not bench:
        raise SystemExit(f"REFUSED: no {BENCH} bars in the panel; there is no benchmark "
                         f"to measure a RELATIVE return against.")
    bench_days = [b["t"][:10] for b in bench]

    def fwd(symbol: str, after: str) -> tuple[str | None, float | None]:
        """SPY-relative return from the first session strictly after `after`."""
        bs = sessions_for(symbol)
        if not bs:
            return None, None
        days = [b["t"][:10] for b in bs]
        i = next((j for j, d in enumerate(days) if d > after), None)
        if i is None or i + HORIZON_SESSIONS >= len(bs):
            return None, None
        bi = next((j for j, d in enumerate(bench_days) if d >= days[i]), None)
        if bi is None or bi + HORIZON_SESSIONS >= len(bench):
            return None, None
        a, b = bs[i]["c"], bs[i + HORIZON_SESSIONS]["c"]
        sa, sb = bench[bi]["c"], bench[bi + HORIZON_SESSIONS]["c"]
        if not all((a, b, sa, sb)):
            return None, None
        return days[i], (b / a - 1.0) - (sb / sa - 1.0)

    by: dict[tuple[str, str], list[dict]] = {}
    for r in facts:
        sym, eff = r.get("symbol"), str(r.get("effective_at") or "")[:10]
        if not sym or not eff:
            continue
        by.setdefault((sym, eff[:7]), []).append(r)

    def month_end(month: str) -> str:
        y, m = int(month[:4]), int(month[5:7])
        y2, m2 = (y + 1, 1) if m == 12 else (y, m + 1)
        return f"{y2:04d}-{m2:02d}-01"

    out, skipped = [], {"no_outcome": 0, "no_body": 0}
    for (sym, month), rows in sorted(by.items()):
        rows.sort(key=lambda r: str(r.get("effective_at")))
        last = str(rows[-1]["effective_at"])[:10]
        # ENTER ON A SHARED REBALANCE DATE, not on each name's own last-news day.
        #
        # The first version entered at the first session after that name's last
        # fact, which gave 1.1 names per decision date -- so "the top 5" was
        # every name, the ranking was never exercised, and the shuffled null
        # could not fail because shuffling outcomes inside a one-name basket
        # returns the same product. A null that cannot go red is worth as much
        # as a gate that cannot go green.
        #
        # Every name in a month now enters at the same month boundary. That is
        # also what makes the arms comparable: they hold the same names on the
        # same dates and differ only in how the news was written.
        d0, ret = fwd(sym, month_end(month))
        if d0 is None:
            skipped["no_outcome"] += 1
            continue
        items = []
        for r in rows:
            b = body.get(r.get("uid"))
            if not b:
                continue
            items.append({"uid": r["uid"], "date": str(r.get("effective_at"))[:10],
                          "event_type": r.get("event_type"),
                          "expectation": r.get("expectation"),
                          "title": (b.get("title") or "")[:300],
                          "text": (b.get("summary") or b.get("body") or "")[:1200]})
        if not items:
            skipped["no_body"] += 1
            continue
        out.append({"key": f"{sym}|{month}", "symbol": sym, "month": month,
                    "decision_date": d0, "rebalance": month, "last_fact": last,
                    "horizon_sessions": HORIZON_SESSIONS,
                    "fwd_rel_21d": round(ret, 6), "n_items": len(items),
                    "items": items})

    if limit:
        out = out[:limit]
    path = _p("windows.jsonl")
    with path.open("w", encoding="utf-8") as fh:
        for w in out:
            fh.write(json.dumps(w) + "\n")
    syms = sorted({w["symbol"] for w in out})
    per_reb: dict[str, int] = {}
    for w in out:
        per_reb[w["rebalance"]] = per_reb.get(w["rebalance"], 0) + 1
    mean_per = sum(per_reb.values()) / len(per_reb) if per_reb else 0
    print(f"windows: {len(out)} over {len(syms)} names, {len(per_reb)} rebalances, "
          f"{mean_per:.0f} names per rebalance")
    if mean_per <= 5:
        print("  WARNING: fewer than 6 names per rebalance means a top-5 basket is "
              "every name and the ranking is never exercised.")
    print(f"  skipped: {skipped}")
    print(f"  -> {path}")
    print("  OUTCOMES ARE ALREADY ON THE WINDOWS and no arm ever sees them: they are "
          "written here so the grader needs no second fetch, and every prompt is built "
          "from `items` alone.")
    return 0


# ------------------------------------------------------------- the entity map

def freeze_map(era: str) -> int:
    ws = load_jsonl(_p("windows.jsonl"))
    if not ws:
        print("REFUSED: no windows. Run --windows first.")
        return 1
    from scripts import tracker as tracker_cli
    from alpha import tracker as T
    sectors = {}
    day = tracker_cli.latest_day()
    if day:
        for r in T.build_rows(tracker_cli.load_day(day)):
            sectors[r["symbol"]] = r.get("sector")
    syms = sorted({w["symbol"] for w in ws})
    m = TP.build_entity_map(syms, [sectors.get(s) or "unknown" for s in syms],
                            era=era)
    m["sector_of"] = {s: (sectors.get(s) or "unknown") for s in syms}
    STORE.mkdir(parents=True, exist_ok=True)
    _p("entity_map.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    print(f"entity map frozen: {len(syms)} companies, {len(m['industries'])} industries, "
          f"year offset {m['year_offset']:+d}")
    print(f"  sha256 {m['sha256'][:16]}  -> {_p('entity_map.json')}")
    print("  GRADER ONLY. Nothing in the decide path reads this file.")
    return 0


def load_map() -> dict:
    p = _p("entity_map.json")
    if not p.exists():
        raise SystemExit("REFUSED: no entity map. Run --map first.")
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- the rewrite

def window_text(w: dict) -> str:
    lines = []
    for it in w["items"]:
        lines.append(f"[{it['date']}] ({it.get('event_type')}, "
                     f"expectation={it.get('expectation')}) {it['title']}")
        if it.get("text"):
            lines.append(f"    {it['text']}")
    return "\n".join(lines)


def rewrite(arm: str, limit: int | None, max_usd: float, tag: str = "",
            rewriter: str | None = None) -> int:
    config.load_env()
    # THE SECOND REWRITE MUST NOT COME FROM THE SAME MODEL AT THE SAME
    # TEMPERATURE. Two calls to one model at temperature 0.1 produce nearly the
    # same prose, so a parity check run that way passes by construction and
    # proves nothing. `--rewriter` is how the B arm gets a different family.
    rewriter = rewriter or REWRITER
    if arm not in ("fantasy", "real_anon"):
        print(f"REFUSED: --arm {arm} needs no rewrite.")
        return 2
    ws = load_jsonl(_p("windows.jsonl"))
    if not ws:
        print("REFUSED: no windows. Run --windows first.")
        return 1
    m = load_map()
    out_path = _p(f"rewritten_{arm}{tag}.jsonl")
    done = {r["key"] for r in load_jsonl(out_path)}
    todo = [w for w in ws if w["key"] not in done][:(limit or len(ws))]
    if not todo:
        print(f"nothing to do ({len(done)} already rewritten for {arm}{tag})")
        return 0
    print(f"rewriting {len(todo)} windows into `{arm}{tag}` with {rewriter}")

    spent, kept, failed = 0.0, 0, {"magnitudes": 0, "leak": 0, "refused": 0}
    fh = out_path.open("a", encoding="utf-8")
    try:
        for i, w in enumerate(todo, 1):
            if spent >= max_usd:
                print(f"STOPPED at the ${max_usd:.2f} budget after {i - 1} windows.")
                break
            src = window_text(w)
            if arm == "fantasy":
                company = m["companies"].get(w["symbol"], "Redacted Company")
                industry = m["industries"].get(m["sector_of"].get(w["symbol"], "unknown"),
                                               "an unnamed industry")
                user = (f"MAPPING (apply consistently):\n"
                        f"  the company this bundle is about -> \"{company}\"\n"
                        f"  its industry -> \"{industry}\"\n"
                        f"  every other company, index, bank, regulator, country or "
                        f"person -> invent a fictional name and reuse it within this "
                        f"bundle\n"
                        f"  every place name -> one of {', '.join(m['places'][:5])}\n"
                        f"  YEAR OFFSET: add {m['year_offset']:+d} years to every date\n\n"
                        f"NEWS BUNDLE:\n{src}")
                system = REWRITE_SYSTEM
            else:
                user = (f"MAPPING: the company this bundle is about -> \"Company A\"; "
                        f"every other named company -> \"Company B\", \"Company C\", ...; "
                        f"every named person -> \"an executive\" / \"an analyst\". "
                        f"KEEP all dates and the industry exactly as they are.\n\n"
                        f"NEWS BUNDLE:\n{src}")
                system = ANON_SYSTEM
            try:
                # `reasoning_effort="minimal"` is not cosmetic on the gpt-5
                # family. Rewriting is TRANSCRIPTION, not judgement, and left to
                # reason the model spends its whole budget thinking and returns
                # an empty string with finish_reason=length -- 3 of the first 6
                # windows here, and the drop correlates with how long the bundle
                # was, i.e. with how much information it carried. The token
                # ceiling is generous for the same reason: a truncated rewrite
                # is a DROPPED window, and dropped windows are not random.
                ans, meta = providers.chat_json(rewriter, system, user,
                                                caller="era_replay.rewrite",
                                                why=WHY_REWRITE, max_tokens=6000,
                                                reasoning_effort="minimal")
            except Exception as e:                                      # noqa: BLE001
                failed["refused"] += 1
                print(f"  {w['key']:22s} REFUSED {type(e).__name__}: {str(e)[:80]}")
                continue
            spent += _cost(meta, rewriter)
            text = str(ans.get("rewritten") or "")
            mag = TP.magnitudes_preserved(src, text)
            leak = (TP.leak_check(text, real_symbols=[w["symbol"]],
                                  real_years=TP.years_in(src))
                    if arm == "fantasy" else {"clean": True})
            # A FAILED REWRITE IS DROPPED, NEVER REPAIRED. Repairing it would
            # mean deciding by hand which magnitude the model meant, and that
            # judgement is exactly the information the arm is trying to isolate.
            if not mag["ok"]:
                failed["magnitudes"] += 1
            if not leak["clean"]:
                failed["leak"] += 1
            row = {"key": w["key"], "arm": arm, "symbol": w["symbol"],
                   "month": w["month"], "rewritten": text,
                   "magnitudes": mag, "leak": leak,
                   "usable": bool(mag["ok"] and leak["clean"] and text),
                   "rewriter": rewriter, "model": (meta or {}).get("model"),
                   "written_at": datetime.now(timezone.utc).isoformat()}
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            kept += 1 if row["usable"] else 0
            if i % 10 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}  usable {kept}  ${spent:.3f}")
    finally:
        fh.close()
    print(f"\n{arm}{tag}: {kept} usable of {min(len(todo), i)} attempted, "
          f"dropped {failed}")
    print(f"cost ${spent:.3f} of the ${max_usd:.2f} budget  -> {out_path}")
    if failed["magnitudes"]:
        print("  DROPPED FOR MAGNITUDES: the rewriter changed a number. Those windows "
              "are excluded rather than fixed -- fixing one by hand would put our "
              "judgement into the arm that is meant to isolate the model's.")
    return 0


#: per 1M tokens
PRICES = {"deepseek": (0.27, 1.10), "openai": (0.25, 2.00)}


def _cost(meta: dict, provider: str) -> float:
    pin, pout = PRICES.get(provider, (0.5, 2.0))
    a, b = (meta or {}).get("prompt_tokens"), (meta or {}).get("completion_tokens")
    if a is None and b is None:
        return (2000 / 1e6 * pin) + (600 / 1e6 * pout)
    return ((a or 0) / 1e6 * pin) + ((b or 0) / 1e6 * pout)


# ----------------------------------------------------------------- the decide

def decide(arm: str, limit: int | None, max_usd: float, tag: str = "") -> int:
    config.load_env()
    if arm not in TP.ARMS:
        print(f"REFUSED: unknown arm {arm!r}. One of {TP.ARMS}.")
        return 2
    ws = {w["key"]: w for w in load_jsonl(_p("windows.jsonl"))}
    if not ws:
        print("REFUSED: no windows. Run --windows first.")
        return 1
    texts: dict[str, str] = {}
    if arm in ("fantasy", "real_anon"):
        rw = load_jsonl(_p(f"rewritten_{arm}{tag}.jsonl"))
        texts = {r["key"]: r["rewritten"] for r in rw if r.get("usable")}
        if not texts:
            print(f"REFUSED: no usable rewrites for {arm}{tag}. Run --rewrite first.")
            return 1
    elif arm == "real":
        texts = {k: window_text(w) for k, w in ws.items()}
    else:                                   # numbers_only
        # The NULL that can end the exercise cheaply: the magnitudes and the
        # event types, with every sentence deleted. If this scores like the
        # fantasy arm, the prose was carrying nothing.
        for k, w in ws.items():
            bits = []
            for it in w["items"]:
                nums = TP.numbers_in(f"{it['title']} {it.get('text') or ''}")
                bits.append(f"[{it['date']}] type={it.get('event_type')} "
                            f"expectation={it.get('expectation')} "
                            f"numbers={', '.join(nums) if nums else 'none'}")
            texts[k] = "\n".join(bits)

    out_path = _p(f"decisions_{arm}{tag}.jsonl")
    done = {r["key"] for r in load_jsonl(out_path)}
    todo = [k for k in sorted(texts) if k not in done][:(limit or len(texts))]
    if not todo:
        print(f"nothing to do ({len(done)} already decided for {arm}{tag})")
        return 0
    print(f"deciding {len(todo)} windows on arm `{arm}{tag}` with {DECIDER}")

    spent, ok = 0.0, 0
    fh = out_path.open("a", encoding="utf-8")
    try:
        for i, key in enumerate(todo, 1):
            if spent >= max_usd:
                print(f"STOPPED at the ${max_usd:.2f} budget after {i - 1} windows.")
                break
            user = (f"COMPANY NEWS BUNDLE:\n{texts[key]}\n\n"
                    f"Give your forecast for this company over the next "
                    f"{HORIZON_SESSIONS} trading sessions, relative to the market.")
            try:
                ans, meta = providers.chat_json(DECIDER, DECIDE_SYSTEM, user,
                                                caller="era_replay.decide",
                                                why=WHY_DECIDE, max_tokens=400)
            except Exception as e:                                      # noqa: BLE001
                print(f"  {key:22s} REFUSED {type(e).__name__}: {str(e)[:80]}")
                continue
            spent += _cost(meta, DECIDER)
            row = {"key": key, "arm": arm + tag, "decider": DECIDER,
                   "model": (meta or {}).get("model"),
                   "decided_at": datetime.now(timezone.utc).isoformat()}
            for k in TP.DECIDER_KEYS:
                row[k] = ans.get(k)
            row["p_up_21d"] = _f(row.get("p_up_21d"))
            row["exp_return"] = _f(row.get("exp_return"))
            row["downside_5pct"] = _f(row.get("downside_5pct"))
            row["confidence"] = _f(row.get("confidence"))
            # NO ABSTAIN. A row that came back without a probability is an
            # error to COUNT, not a refusal to honour -- the schema has no
            # "I don't know" and neither does the grader.
            row["complete"] = row["p_up_21d"] is not None
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            ok += 1 if row["complete"] else 0
            if i % 20 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}  complete {ok}  ${spent:.3f}")
    finally:
        fh.close()
    print(f"\n{arm}{tag}: {ok} complete of {min(len(todo), i)}  ${spent:.3f}")
    return 0


def _f(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip().rstrip("%"))
        except ValueError:
            return None
    return None


# ------------------------------------------------------------------ the grade

def parity_check(limit: int) -> int:
    """Rewrite the same windows twice and see whether the decider notices."""
    a = [r for r in load_jsonl(_p("decisions_fantasy.jsonl")) if r.get("complete")]
    b = [r for r in load_jsonl(_p("decisions_fantasy_b.jsonl")) if r.get("complete")]
    if not b:
        print("REFUSED: the second rewrite does not exist yet. Run:\n"
              f"  python -m scripts.era_replay --rewrite --arm fantasy --tag _b "
              f"--limit {limit}\n"
              f"  python -m scripts.era_replay --decide  --arm fantasy --tag _b "
              f"--limit {limit}")
        return 1
    r = TP.parity(a, b)
    print("REWRITER-PARITY")
    for k, v in r.items():
        print(f"  {k:36s} {v}")
    if r.get("verdict") == "REWRITER_LEAK":
        print("\n  STOP. The rewriter is supplying the variation, so every number the "
              "full grid would produce is a number about the rewriter. Fix the "
              "rewrite prompt before spending on the grid.")
        return 1
    return 0


def grade(k: int, personality: str) -> int:
    ws = {w["key"]: w for w in load_jsonl(_p("windows.jsonl"))}
    if not ws:
        print("REFUSED: no windows.")
        return 1
    outcomes = {key: w["fwd_rel_21d"] for key, w in ws.items()}
    report = {"schema": TP.SCHEMA, "graded_utc": datetime.now(timezone.utc).isoformat(),
              "horizon_sessions": HORIZON_SESSIONS, "k": k,
              "personality": personality, "n_windows": len(ws), "arms": {}}

    # NULL 2, and it is the benchmark every arm is measured against: hold every
    # name in the era, equally, on every date. "Better than WHAT."
    by_date: dict[str, list[str]] = {}
    for key, w in ws.items():
        by_date.setdefault(w.get("rebalance") or w["decision_date"], []).append(key)
    basket = TP.wealth({d: [{"key": key} for key in keys] for d, keys in by_date.items()},
                       outcomes)
    report["null_basket"] = basket

    print(f"T13 ERA REPLAY -- {len(ws)} windows, top {k}, {personality}\n")
    print(f"  NULL basket (every name, equally weighted): wealth "
          f"{basket.get('terminal_wealth')}  t {basket.get('t_stat')}  "
          f"{basket.get('n_dates')} dates")

    for arm in TP.ARMS:
        ds = [d for d in load_jsonl(_p(f"decisions_{arm}.jsonl")) if d.get("complete")]
        if not ds:
            continue
        picks: dict[str, list[dict]] = {}
        for d in ds:
            w = ws.get(d["key"])
            if w:
                picks.setdefault(w.get("rebalance") or w["decision_date"], []).append(d)
        top = {dt: TP.rank(v, personality=personality, k=k) for dt, v in picks.items()}
        w_real = TP.wealth(top, outcomes)
        cal = TP.calibration(ds, outcomes)
        # NULL 1: the same picks against somebody else's outcome.
        shuffled = TP.shuffled_null(ds, outcomes)
        w_null = TP.wealth(top, shuffled)
        # ...AND WHETHER THAT NULL COULD HAVE FAILED AT ALL.
        #
        # The shuffled null tests SELECTION: it asks whether the ranking knew
        # something about THIS name rather than about that month. If a date
        # offers k names or fewer, the top-k IS every name, there is no
        # selection to break, and shuffling outcomes within the same set
        # returns the identical product -- the null then reports the arm's own
        # number back to it and reads as a pass. That happened on the first
        # partial run and it is the reverse of a gate that cannot go green: a
        # null that cannot go red.
        per_date = [len(v) for v in picks.values()]
        mean_per_date = sum(per_date) / len(per_date) if per_date else 0.0
        dates_with_choice = sum(1 for n in per_date if n > k)
        null_informative = dates_with_choice > 0
        report["arms"][arm] = {
            "n_decisions": len(ds), "wealth": w_real, "calibration": cal,
            "null_shuffled_wealth": w_null,
            "null_shuffled_informative": null_informative,
            "mean_candidates_per_date": round(mean_per_date, 2),
            "dates_where_top_k_was_a_choice": dates_with_choice,
            "n_dates": len(per_date),
            "mean_p_up": round(sum(d["p_up_21d"] for d in ds) / len(ds), 4),
            "mean_confidence": round(
                sum(d["confidence"] for d in ds if d.get("confidence") is not None)
                / max(1, sum(1 for d in ds if d.get("confidence") is not None)), 4),
        }
        print(f"\n  {arm.upper():14s} n={len(ds)}")
        print(f"    wealth {w_real.get('terminal_wealth')}  t {w_real.get('t_stat')}  "
              f"hit {w_real.get('hit_rate')}")
        if null_informative:
            wn, wr = w_null.get("terminal_wealth"), w_real.get("terminal_wealth")
            # SAY IT OUT LOUD. 1.73 beside 1.47 is two numbers a reader compares
            # the wrong way round at 2am; "the null BEAT the arm" is not.
            verdict = ("  <-- the NULL BEAT the arm: this ranking is not selecting"
                       if wn is not None and wr is not None and wn > wr else "")
            print(f"    NULL shuffled outcomes: wealth {wn}  t {w_null.get('t_stat')}  "
                  f"({dates_with_choice} of {len(per_date)} dates offered a choice)"
                  f"{verdict}")
        else:
            print(f"    NULL shuffled outcomes: UNINFORMATIVE -- {mean_per_date:.1f} "
                  f"names per date against k={k}, so the top-k is every name and there "
                  f"is no selection for a shuffle to break.")
        print(f"    Brier {cal.get('brier')} vs climatology {cal.get('brier_climatology')}"
              f"  skill {cal.get('skill_vs_climatology')}")
        print(f"    mean p_up {report['arms'][arm]['mean_p_up']}  "
              f"mean confidence {report['arms'][arm]['mean_confidence']}")

    have = set(report["arms"])
    if {"real", "fantasy"} <= have:
        gap = (report["arms"]["real"]["wealth"].get("terminal_wealth", 0)
               - report["arms"]["fantasy"]["wealth"].get("terminal_wealth", 0))
        report["real_minus_fantasy_wealth"] = round(gap, 4)
        print(f"\n  real - fantasy = {gap:+.4f} terminal wealth. Positive means the "
              f"model was using memory or a sector prior, not the shape of the news.")
    if {"numbers_only", "fantasy"} <= have:
        gap2 = (report["arms"]["fantasy"]["wealth"].get("terminal_wealth", 0)
                - report["arms"]["numbers_only"]["wealth"].get("terminal_wealth", 0))
        report["fantasy_minus_numbers_only_wealth"] = round(gap2, 4)
        print(f"  fantasy - numbers_only = {gap2:+.4f}. At or below zero, the PROSE "
              f"added nothing and the numbers were the whole signal.")
    if not have:
        print("\n  no arm has decisions yet.")
    # ARM SIZES SIDE BY SIDE. Two terminal wealths computed on different numbers
    # of windows are not comparable, and `real - fantasy` printed above is
    # meaningless while the arms are still filling at different rates.
    sizes = {a: report["arms"][a]["n_decisions"] for a in have}
    if len(set(sizes.values())) > 1:
        print(f"\n  ARMS ARE NOT THE SAME SIZE: {sizes}. Every gap printed above is "
              f"between baskets built from different numbers of windows and is NOT a "
              f"result. Finish the grid before reading it.")

    out = _p("grade.json")
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"\nreceipt -> {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--windows", action="store_true")
    p.add_argument("--map", action="store_true")
    p.add_argument("--rewrite", action="store_true")
    p.add_argument("--decide", action="store_true")
    p.add_argument("--parity", action="store_true")
    p.add_argument("--grade", action="store_true")
    p.add_argument("--arm", default="fantasy")
    p.add_argument("--tag", default="", help="a suffix, for the second rewrite (_b)")
    p.add_argument("--rewriter", default=None,
                   help="override the rewriting provider. The B arm of the parity "
                        "check MUST use a different family, or two near-identical "
                        "rewrites make the check pass by construction.")
    p.add_argument("--era-start", default="2025-06-01")
    p.add_argument("--era-end", default="2026-07-31")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--personality", default="balanced",
                   choices=sorted(TP.PERSONALITY_LAMBDA))
    p.add_argument("--max-usd", type=float, default=5.00)
    a = p.parse_args(argv)
    if a.max_usd <= 0:
        print("REFUSED: --max-usd must be positive; a run with no budget has no "
              "stopping rule.")
        return 2
    STORE.mkdir(parents=True, exist_ok=True)
    if a.windows:
        return build_windows(a.era_start, a.era_end, a.limit)
    if a.map:
        return freeze_map(a.era_start[:7])
    if a.rewrite:
        return rewrite(a.arm, a.limit, a.max_usd, a.tag, a.rewriter)
    if a.decide:
        return decide(a.arm, a.limit, a.max_usd, a.tag)
    if a.parity:
        return parity_check(a.limit or 30)
    if a.grade:
        return grade(a.k, a.personality)
    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
