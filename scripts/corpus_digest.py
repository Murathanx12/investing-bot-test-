"""CORPUS_DIGEST -- turn a year of stored observations into what the engine can act on.

    python -m scripts.corpus_digest --murat                     # Murat's twenty names
    python -m scripts.corpus_digest --symbols AARD KYTX --months 12
    python -m scripts.corpus_digest --symbols NVDA --skeptic    # + an independent family
    python -m scripts.corpus_digest --show AARD                 # read a stored digest

WHY THIS IS A SEPARATE SCRIPT
=============================
`news_backfill` and `catalyst_horizon` FETCH. This one REASONS, and the split
is deliberate: a module that fetched and interpreted is how `explain_move.py`
shipped a language bug that every caller inherited for months. A collector
that is wrong gives no rows; an interpreter that is wrong gives confident
rows, which is far worse and far quieter.

THE JOB
=======
Per name, compress everything the corpus knows into ONE record the engine can
condition on:

  narrative   what the last N months actually did to this company, in dated
              episodes -- not a summary of headlines, a causal chain
  state       where the story stands TODAY (thesis intact / impaired / resolved)
  catalysts   the dated forward events, each with what it would prove
  falsifier   the observation that would kill the thesis -- required, because
              a thesis with no falsifier is a mood
  murat_rule  the five conditions of roadmap §3 evaluated explicitly, each
              with the evidence that decided it and `unknown` where the
              corpus cannot say. **`unknown` is a verdict, not a gap to fill.**

MODEL TIERING, AND WHY IT IS NOT ONE MODEL (measured 2026-08-29)
================================================================
    featherless  Qwen2.5-72B    2.7 s   family `alibaba`
    nvidia_kimi  kimi-k3       13-17 s  family `moonshot`, REASONING model

Featherless is the workhorse: five times faster, and the episode pass is many
calls over many chunks. NVIDIA is the SKEPTIC, and the argument for it is
independence, not quality -- `providers.distinct_families` exists because a
skeptic drawn from the same weights as the synthesiser is the synthesiser
agreeing with itself. `--skeptic` is opt-in because it roughly doubles the
cost of a name and its value is highest on names about to be sized.

kimi-k3 spends `max_tokens` on reasoning BEFORE answering, so every call here
carries a budget large enough for both; `providers.chat_json` now names a
truncation as a truncation rather than reporting a live model as broken.

COST DISCIPLINE
===============
Every call names the decision it can change (`alpha.spend` refuses otherwise).
The episode pass is chunked so that a name with 700 headlines does not become
one 200k-token call, and headlines are DEDUPED on title before the chunking --
the same Benzinga item reaches us from two sources, and paying twice to read
the same sentence is the cheapest waste to remove.

SHADOW
======
Writes `state/corpus/digests/<SYMBOL>.json`. Places nothing, sizes nothing.
Its consumer is the pre-open prediction book and a human reading a table.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from alpha import config
from alpha.council import providers
from alpha.sources import corpus

from scripts.news_backfill import MURAT_NAMES

DIGESTS = corpus.CORPUS / "digests"

#: Bulk work runs on PREPAID capacity. DeepSeek is deliberately last here: it
#: is the only metered provider in the list, and the episode pass is ~90% of
#: all calls.
BULK_ORDER = ("featherless", "hf_glm", "nvidia_kimi", "deepseek")

#: The skeptic wants a DIFFERENT FAMILY, and it wants the FREE ones first.
#:
#: Measured 2026-08-29: NVIDIA rate-limited, the fallback reached straight past
#: the free tiers to DeepSeek, and every routine name started spending metered
#: tokens to be told "yes, I agree". That inverts the economics -- a skeptic
#: that agrees is the cheapest output in the system and should cost the least.
#: So free families are exhausted first, and DeepSeek is reserved (below) for
#: the rows where a second opinion actually changes a decision.
SKEPTIC_ORDER = ("nvidia_kimi", "hf_glm", "featherless")

#: The paid adjudicator, and what it is FOR. Reached only when the free
#: skeptics DISAGREE with the analyst -- the ABSI case, where Featherless read
#: `thesis_intact` and the other family read `thesis_impaired`. A disagreement
#: is the one row a human cannot resolve from the table, so a few cents of
#: independent reasoning is worth it there and nowhere else.
ADJUDICATOR = "deepseek"

#: Hard ceiling on paid adjudications per run. A budget that is not enforced is
#: a preference, and the failure mode here is silent: a rate-limited free tier
#: would quietly route the WHOLE universe to the metered provider.
ADJUDICATOR_MAX_CALLS = 6

#: Headlines per episode call, and it is a TWO-SIDED constraint -- both sides
#: measured 2026-08-29.
#:
#: Too small and the pass is slow for the wrong reason: Featherless latency on
#: the shared tier was 6.7 s / 18.8 s / 64.9 s on three consecutive IDENTICAL
#: calls. That is queueing, not throughput, so the cost of a pass is set by the
#: NUMBER of calls and barely at all by their size. CHUNK=40 made a 20-name run
#: ~200 calls and put it on course for two hours.
#:
#: Too large and the ANSWER overflows: at CHUNK=120 the model wrote one episode
#: per headline, produced 9,217 characters, blew the token budget, and the whole
#: chunk was thrown away -- one name's history collapsed to a single episode and
#: read `unknown`. Widening the input silently narrowed the output.
#:
#: 60 sits between them, and `_episode_call` splits on truncation so the upper
#: bound is enforced by measurement rather than by this constant being right.
CHUNK = 60

SYSTEM = ("You are a buy-side analyst building a durable file on one company. "
          "Answer ONLY with one JSON object, in English. Never invent a fact, a date or a number: "
          "every claim must trace to a supplied headline. Where the material does not say, write "
          "\"unknown\" -- an honest unknown is worth more than a plausible guess.")


def _pick(live: dict, order: tuple[str, ...]) -> str | None:
    return next((p for p in order if live.get(p, {}).get("state") == "live"), None)


def chat_retry(*args, **kw):
    """`providers.chat_json` with backoff on a RATE LIMIT only.

    Measured 2026-08-29: NVIDIA answered `HTTP 429 Too Many Requests` on the
    skeptic call for AMD, so that name silently ended with **no second
    opinion** -- `agree_on_state: None`. The skeptic is the highest-value part
    of the pass (it is the only thing that can disagree), and losing it to a
    burst limit degrades the output without failing the run. Same family as the
    Finnhub 429 in `news_backfill`: a rate limit that reads as an absence.

    The retry lives HERE and not in `providers.chat_json`, deliberately. That
    function is on the live council path, where a stalled retry inside a
    trading pass is worse than a refusal that the caller can skip. A batch
    research job has the opposite trade-off, so it opts in.
    """
    for attempt in range(4):
        try:
            return providers.chat_json(*args, **kw)
        except providers.ProviderRefusal as exc:
            if "429" not in str(exc) or attempt == 3:
                raise
            time.sleep(5.0 * (2 ** attempt))       # 5s, 10s, 20s
    raise providers.ProviderRefusal("unreachable")


def _dedupe(rows: list[dict]) -> list[dict]:
    """Same story from two wires is one story. Key on a normalised title."""
    seen, out = set(), []
    for r in rows:
        k = re.sub(r"[^a-z0-9]+", " ", str(r.get("title", "")).lower()).strip()[:90]
        if k and k not in seen:
            seen.add(k)
            out.append(r)
    return out


def _episode_call(symbol: str, chunk: list[dict], *, provider: str, depth: int = 0
                  ) -> tuple[list[dict], list[str]]:
    """One chunk -> episodes. SPLITS AND RETRIES when the answer is truncated.

    Measured 2026-08-29, and it cost a whole name: at CHUNK=120 the model wrote
    one episode PER HEADLINE, produced **9,217 characters**, blew
    `max_tokens=2400` and the entire chunk was discarded -- so AARD's narrative
    was built from **1 episode out of 121 headlines** and read `unknown`. The
    provider was fine; the ask was.

    Two fixes, because either alone is fragile:
    - the prompt now says this is COMPRESSION and caps the episode count, since
      the real error was the model treating a digest as a transcription;
    - a truncation SPLITS the chunk and retries, so a budget miss costs one
      extra call instead of the whole slice. Same shape as the Finnhub
      earnings cap: never accept a bounded answer as a complete one.
    """
    span = f"{str(chunk[0].get('effective_at'))[:10]}..{str(chunk[-1].get('effective_at'))[:10]}"
    text = "\n".join(f"- {str(r.get('effective_at'))[:10]} [{r.get('source')}] "
                     f"{r.get('title')} :: {str(r.get('body') or '')[:160]}" for r in chunk)
    user = (f"Company: {symbol}. {len(chunk)} headlines {span}, oldest first:\n{text}\n\n"
            'Return {"episodes": [{"date": "YYYY-MM-DD", "event": str, "kind": '
            '"clinical"|"earnings"|"guidance"|"financing"|"legal"|"product"|"analyst"|"macro"|"other", '
            '"direction": "positive"|"negative"|"neutral", "why_it_mattered": str, '
            '"still_open": bool}]}. '
            "THIS IS COMPRESSION, NOT TRANSCRIPTION. Return **at most 10 episodes** however "
            "many headlines are supplied, and prefer far fewer: a quarter of coverage is "
            "usually three or four things that actually happened. Merge every duplicate "
            "and follow-up report of one event into ONE episode. Drop price-move recaps, "
            "listicles, 'what analysts think' round-ups and generic market wraps entirely. "
            "Keep `why_it_mattered` to one short sentence. "
            "`still_open` is true when the event created an obligation or a question that a "
            "later dated event will answer (a trial ongoing, a guidance to be met, a case pending).")
    try:
        obj, meta = chat_retry(
            provider, SYSTEM, user, caller="corpus_digest.episodes",
            why=("Builds the dated causal history the pre-open prediction book reads to DECIDE "
                 "whether a name's drawdown is transitory or thesis-impaired, which selects "
                 "whether it is entered at all and at what size."),
            max_tokens=4000)
        eps = []
        for e in obj.get("episodes") or []:
            e["provider"] = meta.get("provider")
            eps.append(e)
        return eps, []
    except providers.ProviderRefusal as exc:
        if "TRUNCATED" in str(exc) and len(chunk) > 8 and depth < 2:
            mid = len(chunk) // 2
            a, ra = _episode_call(symbol, chunk[:mid], provider=provider, depth=depth + 1)
            b, rb = _episode_call(symbol, chunk[mid:], provider=provider, depth=depth + 1)
            return a + b, ra + rb + [f"episodes {span}: truncated at {len(chunk)} headlines -> split"]
        return [], [f"episodes {span}: {str(exc)[:120]}"]


def episodes(symbol: str, rows: list[dict], *, provider: str) -> tuple[list[dict], list[str]]:
    """Compress dated headlines into causal episodes, oldest chunk first."""
    out, refusals = [], []
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i + CHUNK]
        eps, refs = _episode_call(symbol, chunk, provider=provider)
        out += eps
        refusals += refs
        # Progress, because a pass whose per-call latency ranges over an order
        # of magnitude is otherwise indistinguishable from a hung one.
        print(f"      {symbol} chunk {i // CHUNK + 1}/{-(-len(rows) // CHUNK)} "
              f"  {len(out)} episodes so far", flush=True)
    return out, refusals


def synthesise(symbol: str, eps: list[dict], future: list[dict], *,
               provider: str, role: str = "analyst") -> tuple[dict, list[str]]:
    """One record: state, thesis, catalysts, falsifier, Murat's five conditions."""
    ep_text = "\n".join(f"- {e.get('date')} ({e.get('kind')}, {e.get('direction')}"
                        + (", OPEN" if e.get("still_open") else "") + f") {e.get('event')}"
                        f" :: {str(e.get('why_it_mattered'))[:140]}" for e in eps[-70:])
    fu_text = "\n".join(f"- {str(f.get('effective_at'))[:10]} [{f.get('kind')}"
                        + ("" if f.get("source_verified") else ", DATE UNCONFIRMED")
                        + f"] {f.get('title')}" for f in future[:40]) or "(none stored)"
    stance = ("" if role == "analyst" else
              "\n\nYou are the SKEPTIC. Another analyst has built this file. Your job is to find the "
              "reading under which this is a VALUE TRAP or a dead thesis, and to say plainly which "
              "single observation would settle it. Do not be contrarian for its own sake; if the "
              "bull case is sound, say so and name its weakest load-bearing assumption.")
    user = (f"Company: {symbol}.\n\nDATED HISTORY (what happened, oldest first):\n{ep_text}\n\n"
            f"SCHEDULED AHEAD (from calendars; DATE UNCONFIRMED means the date is an estimate):\n{fu_text}\n\n"
            'Return {"one_line": str, "state": "thesis_intact"|"thesis_impaired"|"thesis_resolved"|"unknown", '
            '"narrative": str (<=120 words, the causal chain, not a list), '
            '"drawdown_reading": "transitory"|"thesis_impaired"|"unknown", '
            '"open_questions": [str], '
            '"catalysts": [{"date": str, "what": str, "what_it_would_prove": str, "date_confirmed": bool}], '
            '"falsifier": str (one observation that would kill the thesis), '
            '"murat_rule": {"upside_ratio": "pass"|"fail"|"unknown", "rating": "pass"|"fail"|"unknown", '
            '"sector_fit": "pass"|"fail"|"unknown", "dated_catalyst": "pass"|"fail"|"unknown", '
            '"already_down": "pass"|"fail"|"unknown", "evidence": str}, '
            '"confidence": float 0-1}.\n'
            "The five murat_rule conditions are: (a) analyst target/price >= 1.5, (b) consensus rating "
            ">= 4.1/5, (c) biotech/medtech or technology the next decade needs, (d) a NAMED catalyst "
            "dated inside 12 months, (e) price already down from a recent level. Mark a condition "
            '"unknown" unless the supplied material actually decides it -- do not infer (a) or (b) '
            "from tone." + stance)
    try:
        obj, meta = chat_retry(
            provider, SYSTEM, user, caller=f"corpus_digest.{role}",
            why=("Produces the per-name state and falsifier that DECIDE whether the name enters the "
                 "sealed pre-open prediction book, which book acts on it, and whether its drawdown is "
                 "read as an entry or as an impaired thesis to skip."),
            max_tokens=2600)
        obj["provider"] = meta.get("provider")
        obj["family"] = meta.get("family")
        return obj, []
    except providers.ProviderRefusal as exc:
        return {}, [f"{role}: {str(exc)[:140]}"]


def reconcile(view: dict, future: list[dict], *, today: str) -> list[str]:
    """Check the model's claims against the corpus, and DOWNGRADE what it cannot support.

    Measured on the first AARD run: the analyst returned
    `dated_catalyst: "pass"` and listed a **2026-08-11 event that had already
    happened** as its forward catalyst, while the corpus held ZERO future rows
    for the name. The prompt asked for an honest "unknown" and did not get one.

    So the check lives in code. A catalyst is a FUTURE dated event; a claim of
    one is verifiable against `corpus.read(tense="future")` and is verified
    here rather than trusted. The correction is recorded on the record --
    silently rewriting a model's answer would hide exactly the calibration
    signal that says how much to trust the next one.
    """
    fixes: list[str] = []
    horizon = (date.fromisoformat(today) + timedelta(days=365)).isoformat()
    corpus_dates = sorted({str(f.get("effective_at"))[:10] for f in future
                           if today <= str(f.get("effective_at"))[:10] <= horizon})

    def _backed(when: str) -> bool:
        # A claim is corpus-backed when a future row for this name sits within
        # three days of the claimed date. The corpus is the diary; the model
        # is not allowed to write in it.
        d = date.fromisoformat(when)
        return any(abs((date.fromisoformat(x) - d).days) <= 3 for x in corpus_dates)

    cats = view.get("catalysts")
    if isinstance(cats, list):
        kept, dropped = [], []
        for c in cats:
            when = str((c or {}).get("date") or "")[:10]
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", when) and today <= when <= horizon:
                c = dict(c or {})
                c["in_corpus"] = _backed(when)
                kept.append(c)
            else:
                dropped.append(f"{when or 'undated'}: {str((c or {}).get('what'))[:50]}")
        if dropped:
            fixes.append(f"dropped {len(dropped)} catalyst(s) outside [today, +12m]: " + "; ".join(dropped[:3]))
        view["catalysts"] = kept
        view["catalysts_dropped"] = dropped

    mr = view.get("murat_rule")
    if isinstance(mr, dict) and mr.get("dated_catalyst") == "pass":
        # (d) is "a NAMED catalyst inside 12 months". It passes only on a
        # claim the CORPUS can see (2026-08-29 review: a bare future date the
        # model invented -- 2031, or a date no source ever recorded -- kept
        # `pass` alive).
        # The CORPUS decides (d), not the model: a forward-dated row for this
        # name inside 12 months is what "a dated catalyst exists" means. The
        # model's own list is annotated `in_corpus` and cannot sustain a pass.
        if not corpus_dates:
            mr["dated_catalyst"] = "unknown"
            fixes.append("murat_rule.dated_catalyst pass -> unknown "
                         "(no future-dated corpus row inside 12 months; model-claimed dates cannot sustain a pass)")
    return fixes


def digest_one(symbol: str, *, months: int, live: dict, skeptic: bool,
               max_headlines: int = 400, budget: dict | None = None) -> dict:
    since = (date.today() - timedelta(days=31 * months)).replace(day=1).isoformat()
    past = _dedupe(corpus.read(since=since, until=date.today().isoformat(),
                               tense="past", symbols=[symbol]))
    # A CAP THAT DOES NOT ANNOUNCE ITSELF READS AS FULL COVERAGE, AND A CAP ON
    # RECENCY ANSWERS A DIFFERENT QUESTION THAN THE ONE ASKED.
    #
    # AMD carries 4,117 headlines in twelve months. Keeping the most recent 400
    # -- the first design -- gave a "12-month" digest whose history started
    # 2026-07-29: ONE MONTH, four weeks, and the Murat rule scored on it. The
    # cap was reported honestly and was still the wrong cap, because the whole
    # point of the corpus is the ARC (the guidance cut that made the drawdown,
    # the clinical hold in March), and an arc is exactly what recency
    # truncation deletes.
    #
    # So the sample is STRATIFIED BY MONTH: every month in the window gets a
    # share of the budget, and months with fewer headlines than their share
    # hand the remainder back to the rest. Measured on AMD: 400 drawn across
    # all 13 months, ~31 each, history starting 2025-08-22 instead of
    # 2026-07-29.
    #
    # Note what this deliberately gives up. The result is near-UNIFORM per
    # month, not proportional -- a month with 400 headlines and a month with
    # 178 both contribute ~31. So the sample under-weights busy months, and a
    # busy month is usually busy for a reason. That is the right trade here
    # because the job is to recover the ARC, and a proportional sample of a
    # mega-cap collapses back toward the loudest quarter; but it means the
    # episode counts are NOT evidence of where activity concentrated.
    n_all = len(past)
    truncated_from = None
    if n_all > max_headlines:
        truncated_from = str(past[0].get("effective_at"))[:10]
        by_month: dict[str, list[dict]] = {}
        for r in past:
            by_month.setdefault(str(r.get("effective_at"))[:7], []).append(r)
        months_present = sorted(by_month)
        # NOT `budget` -- that is the PAID-CALL budget parameter, and naming the
        # sampler's headline quota the same thing overwrote it with an int. The
        # adjudicator then did `budget["paid"]` on an int and died, but only for
        # a name that was BOTH capped AND had the two families disagree, which
        # is why a short run never saw it.
        quota = max_headlines
        chosen: list[dict] = []
        # Smallest months first, so a quiet month's unused share flows to the
        # busy ones rather than being lost.
        for i, m in enumerate(sorted(months_present, key=lambda m: len(by_month[m]))):
            share = max(1, quota // (len(months_present) - i))
            take = by_month[m][-share:] if len(by_month[m]) > share else by_month[m]
            chosen += take
            quota -= len(take)
        past = sorted(chosen, key=lambda r: (str(r.get("effective_at")), str(r.get("observed_at"))))
    future = corpus.read(since=date.today().isoformat(), tense="future", symbols=[symbol])
    rec: dict = {"symbol": symbol, "generated_utc": corpus.utcnow(), "months": months,
                 "n_past": len(past), "n_past_available": n_all, "n_future": len(future),
                 "history_covers_from": str(past[0].get("effective_at"))[:10] if past else None,
                 "truncated_from": truncated_from,
                 "sources": sorted({str(r.get("source", "")).split(":")[0] for r in past}),
                 "refusals": []}
    if truncated_from:
        months_kept = len({str(r.get("effective_at"))[:7] for r in past})
        rec["months_represented"] = months_kept
        rec["refusals"].append(
            f"sampled {len(past)} of {n_all} headlines, stratified across {months_kept} months "
            f"from {rec['history_covers_from']} -- each month is a SAMPLE, not its full coverage")
    if not past and not future:
        # AN EMPTY DIGEST IS A FINDING. It says the corpus is blind to this
        # name, which is the coverage gap -- not that the name is quiet.
        rec["state"] = "no_coverage"
        rec["one_line"] = f"{symbol}: the corpus holds nothing. Backfill before reading anything into silence."
        return rec

    bulk = _pick(live, BULK_ORDER)
    if not bulk:
        rec["refusals"].append("no live provider")
        return rec
    eps, refs = episodes(symbol, past, provider=bulk)
    rec["episodes"] = eps
    rec["refusals"] += refs
    n_chunks = max(1, -(-len(past) // CHUNK))
    rec["n_chunks"] = n_chunks
    rec["n_chunks_refused"] = len(refs)
    if len(refs) * 2 > n_chunks:
        # More than half the history failed to compress: a verdict on the
        # surviving half would score like a complete one (2026-08-29 review).
        rec["refusals"].append(f"synthesis refused: {len(refs)} of {n_chunks} chunks failed")
        rec["analyst"] = {}
        return rec
    view, refs = synthesise(symbol, eps, future, provider=bulk)
    rec["refusals"] += refs
    today = date.today().isoformat()
    rec["corrections"] = reconcile(view, future, today=today) if view else []
    rec["analyst"] = view
    if skeptic:
        # TRY EVERY OTHER FAMILY, NOT JUST THE PREFERRED ONE.
        #
        # `_pick` chose one provider up front, so when NVIDIA answered HTTP 429
        # the skeptic was simply lost -- both ABSI and AMD ended with no second
        # opinion while the summary table looked complete. The skeptic is the
        # only component that can DISAGREE, so losing it silently removes the
        # single most informative field on the sheet.
        #
        # What matters is that the skeptic comes from a different FAMILY than
        # the synthesis (`providers.distinct_families`): a skeptic drawn from
        # the same weights is the synthesiser agreeing with itself. Any other
        # family will do, so exhaust them before giving up.
        others = [p for p in SKEPTIC_ORDER
                  if live.get(p, {}).get("state") == "live"
                  and providers.PROVIDERS[p].family != providers.PROVIDERS[bulk].family]
        tried: list[str] = []
        for sk in others:
            alt, refs = synthesise(symbol, eps, future, provider=sk, role="skeptic")
            tried.append(sk)
            if alt.get("state"):
                rec["corrections"] += [f"skeptic: {f}" for f in reconcile(alt, future, today=today)]
                rec["skeptic"] = alt
                rec["skeptic_provider"] = sk
                if view.get("state"):
                    # Disagreement is the useful part and must survive to the receipt.
                    rec["agree_on_state"] = alt["state"] == view["state"]
                break
            rec["refusals"] += refs
        else:
            rec["refusals"].append(
                f"skeptic UNAVAILABLE after trying {tried or 'no second family'}; "
                "this name has ONE opinion and must be weighted as such")

        # ESCALATE ONLY A DISAGREEMENT, AND ONLY WITHIN BUDGET.
        #
        # Two independent families splitting on the same episodes is the one
        # row a human cannot settle from the table, and it is worth paying a
        # metered provider to break. Agreement is not: paying to be told "yes"
        # on eighteen routine names is how a research budget disappears without
        # a decision changing. The escalation is COUNTED and written onto the
        # record, so the spend is visible per run rather than discovered on a
        # monthly bill.
        if (rec.get("agree_on_state") is False
                and budget is not None and budget["paid"] < ADJUDICATOR_MAX_CALLS
                and live.get(ADJUDICATOR, {}).get("state") == "live"
                and providers.PROVIDERS[ADJUDICATOR].family != providers.PROVIDERS[bulk].family):
            adj, refs = synthesise(symbol, eps, future, provider=ADJUDICATOR, role="skeptic")
            rec["refusals"] += refs
            if adj.get("state"):
                budget["paid"] += 1
                rec["adjudicator"] = adj
                rec["adjudicator_provider"] = ADJUDICATOR
                rec["adjudicator_reason"] = (
                    f"escalated: {rec.get('skeptic_provider')} said {rec['skeptic'].get('state')!r}, "
                    f"{bulk} said {view.get('state')!r}")
                # Two of three states agreeing is the readable summary; the
                # three raw verdicts stay on the record so a majority is never
                # mistaken for a consensus.
                votes = [view.get("state"), rec["skeptic"].get("state"), adj.get("state")]
                rec["state_votes"] = votes
                rec["state_majority"] = max(set(votes), key=votes.count) if votes else None
    return rec


def brief(symbol: str) -> dict | None:
    """The stored record for one name, or None. THE consumer entry point.

    `scripts.thesis`, the pre-open prediction book and `dislocation_scan` read
    this rather than re-reading raw headlines, so that what a human sees and
    what a book conditions on are the same object.
    """
    p = DIGESTS / f"{symbol.upper()}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def screen(*, within_days: int = 45) -> list[dict]:
    """Every digested name, ranked for the prediction book.

    Rank is Murat's five conditions PASSED, then whether a dated catalyst
    lands inside `within_days`, then the weight of history behind the call.
    Names where the two model families DISAGREED are surfaced rather than
    hidden -- a split verdict is the most informative row on the sheet and the
    one a human should read first.
    """
    horizon = (date.today() + timedelta(days=within_days)).isoformat()
    today = date.today().isoformat()
    out = []
    for p in sorted(DIGESTS.glob("*.json")):
        if p.name.endswith(".failed.json"):
            continue
        rec = json.loads(p.read_text(encoding="utf-8"))
        a = rec.get("analyst") or {}
        mr = a.get("murat_rule") or {}
        passes = sum(1 for k in ("upside_ratio", "rating", "sector_fit",
                                 "dated_catalyst", "already_down") if mr.get(k) == "pass")
        unknowns = sum(1 for k in ("upside_ratio", "rating", "sector_fit",
                                   "dated_catalyst", "already_down") if mr.get(k) == "unknown")
        soon = [c for c in (a.get("catalysts") or [])
                if today <= str(c.get("date", ""))[:10] <= horizon]
        corpus_soon = [r for r in corpus.read(since=today, until=horizon, tense="future",
                                              symbols=[rec["symbol"]])]
        out.append({
            "symbol": rec["symbol"], "state": a.get("state") or rec.get("state"),
            "rule_passes": passes, "rule_unknowns": unknowns,
            "drawdown_reading": a.get("drawdown_reading"),
            "one_line": a.get("one_line") or rec.get("one_line"),
            "falsifier": a.get("falsifier"),
            "n_catalysts_soon": len(soon) + len(corpus_soon),
            "next_catalyst": min([str(c.get("date"))[:10] for c in soon]
                                 + [str(r["effective_at"])[:10] for r in corpus_soon], default=None),
            "families_disagree": rec.get("agree_on_state") is False,
            "skeptic_state": (rec.get("skeptic") or {}).get("state"),
            # `is None` was wrong: a FAILED skeptic call returns {} from
            # `synthesise`, not None, so AMD -- whose skeptic died on HTTP 429 --
            # showed as having a second opinion it did not have. A falsy check
            # covers both "never attempted" and "attempted and refused".
            "no_skeptic": not (rec.get("skeptic") or {}).get("state"),
            "n_past": rec.get("n_past", 0),
            # HOW MUCH HISTORY THE VERDICT IS ACTUALLY BUILT ON. AMD scored
            # 5/5 on 400 of 4,117 headlines -- one month, not twelve. The
            # refusal line said so inside the JSON while the summary table
            # looked clean, and the table is what gets read.
            "covers_from": rec.get("history_covers_from"),
            "capped": bool(rec.get("truncated_from")),
            "n_past_available": rec.get("n_past_available", rec.get("n_past", 0)),
            "corrections": rec.get("corrections") or [],
        })
    return sorted(out, key=lambda r: (-r["rule_passes"], -r["n_catalysts_soon"], -r["n_past"]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--murat", action="store_true")
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--skeptic", action="store_true", help="second opinion from another model FAMILY")
    ap.add_argument("--show", default=None, help="print a stored digest and exit")
    ap.add_argument("--screen", action="store_true", help="rank every stored digest and exit")
    ap.add_argument("--max-headlines", type=int, default=400,
                    help="cap per name (most recent kept); the drop is reported, never silent")
    args = ap.parse_args()
    config.load_env()

    if args.screen:
        rows = screen()
        print(f"{'sym':<6}{'rule':>5}{'unk':>4}  {'state':<17}{'next cat':<12}"
              f"{'hist':<9}{'from':<12}one line")
        for r in rows:
            hist = f"{r['n_past']}/{r['n_past_available']}" if r["capped"] else str(r["n_past"])
            print(f"{r['symbol']:<6}{r['rule_passes']:>4}/5{r['rule_unknowns']:>4}  "
                  f"{str(r['state'] or '-'):<17}{str(r['next_catalyst'] or '-'):<12}"
                  f"{hist:<9}{str(r['covers_from'] or '-'):<12}{str(r['one_line'] or '')[:52]}"
                  + ("  [DISAGREE]" if r["families_disagree"] else "")
                  + ("  [NO SKEPTIC]" if r["no_skeptic"] else ""))
        print("\n`rule n/5` counts Murat's five conditions PASSED; `unk` counts those the corpus "
              "could not decide.\n`hist` shown as read/available means the verdict rests on the "
              "MOST RECENT slice only -- check `from`.")
        split = [r["symbol"] for r in rows if r["families_disagree"]]
        if split:
            print(f"\nread these first, the two model families disagree: {' '.join(split)}")
        capped = [r["symbol"] for r in rows if r["capped"]]
        if capped:
            print(f"history TRUNCATED (rule scored on a partial window): {' '.join(capped)}")
        lonely = [r["symbol"] for r in rows if r["no_skeptic"]]
        if lonely:
            print(f"NO SECOND OPINION (one family only, treat with less weight): {' '.join(lonely)}")
        bad = [(r["symbol"], c) for r in rows for c in r["corrections"]]
        if bad:
            print(f"\nclaims the corpus could not support ({len(bad)}):")
            for sym, c in bad[:8]:
                print(f"  {sym:<6}{c[:96]}")
        print(f"\n{len(rows)} digested names. SHADOW: nothing is sized or ordered from this. "
              "No backtest has run.")
        return 0

    if args.show:
        p = DIGESTS / f"{args.show.upper()}.json"
        if not p.exists():
            print(f"no digest for {args.show.upper()}; run without --show first")
            return 1
        print(json.dumps(json.loads(p.read_text(encoding="utf-8")), indent=1, ensure_ascii=False))
        return 0

    syms = [s.upper() for s in (args.symbols or [])]
    if args.murat or not syms:
        syms = sorted(set(syms) | set(MURAT_NAMES))

    live = providers.probe(list(dict.fromkeys(BULK_ORDER + SKEPTIC_ORDER + (ADJUDICATOR,))))
    #: Shared across the run, so the paid ceiling is per RUN and not per name.
    paid_budget = {"paid": 0}
    print("providers " + str({k: v.get("state") for k, v in live.items()}))
    DIGESTS.mkdir(parents=True, exist_ok=True)

    table = []
    for sym in syms:
        rec = digest_one(sym, months=args.months, live=live, skeptic=args.skeptic,
                         max_headlines=args.max_headlines, budget=paid_budget)
        target = DIGESTS / f"{sym}.json"
        if not rec.get("analyst") and target.exists():
            # A provider outage must not erase yesterday's good digest: the
            # failed run is written beside it, and screen() keeps reading the
            # last record that carried a verdict (2026-08-29 review).
            (DIGESTS / f"{sym}.failed.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False),
                                                        encoding="utf-8")
            print(f"  {sym}: no verdict this run; prior digest kept, failure written to {sym}.failed.json")
        else:
            target.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        a = rec.get("analyst") or {}
        mr = a.get("murat_rule") or {}
        passes = sum(1 for k in ("upside_ratio", "rating", "sector_fit", "dated_catalyst", "already_down")
                     if mr.get(k) == "pass")
        table.append((sym, rec.get("n_past", 0), rec.get("n_future", 0),
                      a.get("state") or rec.get("state") or "-", passes,
                      (a.get("one_line") or rec.get("one_line") or "")[:78],
                      len(rec.get("refusals") or [])))
        print(f"  {sym:<6} past {rec.get('n_past', 0):>4}  fwd {rec.get('n_future', 0):>3}  "
              f"{str(a.get('state') or rec.get('state') or '-'):<17} rule {passes}/5  "
              f"{(a.get('one_line') or rec.get('one_line') or '')[:70]}")

    print(f"\n{'sym':<6}{'past':>6}{'fwd':>5}  {'state':<17}{'rule':>5}  one line")
    for sym, npast, nfut, state, passes, line, nref in sorted(table, key=lambda t: (-t[4], -t[1])):
        print(f"{sym:<6}{npast:>6}{nfut:>5}  {state:<17}{passes:>4}/5  {line}"
              + (f"   [{nref} refusals]" if nref else ""))
    print(f"\ndigests: {DIGESTS}  (shadow: nothing is sized or ordered from this)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
