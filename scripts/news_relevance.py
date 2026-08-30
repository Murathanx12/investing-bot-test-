"""Turn each corpus news item into a few honest NUMBERS, with an LLM as the reader.

WHAT THIS IS, AND WHAT IT IS NOT
================================
It is a CLASSIFIER, not a forecaster. It is shown one news item and one ticker
and asked three things a careful human could answer from the text alone:

    role          is this company the SUBJECT, merely MENTIONED, or ABSENT?
    is_new_fact   a new dated company fact, or a recap/listicle/opinion?
    event_type    which of eleven declared kinds
    expectation   was an expectation named, and was it beaten or missed?

It is never asked what the stock will do. That is deliberate and it is the
difference between an encoder and an oracle: the model converts text to
features, the backtest decides whether those features carry.

BECAUSE IT NEVER SEES THE FUTURE, THIS IS PIT-SAFE BY CONSTRUCTION
=================================================================
The only input is the item's own title and body. No price, no outcome, no later
item. So a label computed today may be joined to a 2025 date without lookahead
-- which is NOT true of anything that reads a chart. `classified_at` is recorded
anyway, because a claim of PIT-safety that cannot be audited is a promise.

WHY IT EXISTS (measured 2026-08-30, 250-row random sample)
==========================================================
Only **18.4%** of corpus news rows are a new dated fact ABOUT the tagged company.
82.8% have the right subject, but **78.4% are recaps, listicles, aggregates or
opinion**. So `n_items_20d` -- the feature whose IC was +0.023 [-0.004,+0.046] on
152 names -- was counting roughly five noise items for every real event. A count
filtered to (subject AND new fact) is a DIFFERENT feature and has never been
tested. Tetlock (RFS 2011) is the prior: stale news moves prices less, and the
day-of return on stale news REVERSES over the following week.

MODEL CHOICE (measured, same day, on real corpus items)
=======================================================
    gpt-5-nano  reasoning_effort=minimal   6/6 parsed  1.8s  $0.03 / 1k items
    gpt-5-nano  (no flag, the default)     4/6 parsed  5.5s  $0.39 / 1k items
    gpt-5-mini  (no flag)                  6/6 parsed  5.5s  $0.96 / 1k items

The gpt-5 family REASON by default and on a trivial classification will spend
the entire completion budget thinking and return an empty string with
`finish_reason=length`. That reads as "the small model is too weak" and is the
opposite of the truth. Two further quirks are hard 400s, not warnings:
`temperature` must be omitted (only the default 1 is accepted) and the field is
`max_completion_tokens`, never `max_tokens`.

NOTHING HERE PLACES AN ORDER.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from alpha import config  # noqa: E402
from alpha.sources import corpus  # noqa: E402

OBS = corpus.CORPUS / "observations"
OUT = corpus.CORPUS / "relevance"

MODEL = "gpt-5-nano"
#: Per 1M tokens, read from OpenAI's price page 2026-08-30.
PRICE_IN, PRICE_OUT = 0.05, 0.40
#: A hard ceiling. The whole corpus costs ~$2.20 at nano prices; anything that
#: wants more than this has gone wrong, and a runaway loop against a metered
#: provider is the one bug that bills while you sleep.
DEFAULT_MAX_USD = 5.00

EVENT_TYPES = ["earnings", "guidance", "analyst_rating", "m_and_a", "clinical",
               "regulatory", "contract", "product", "legal", "macro", "insider", "none"]
ROLES = ["subject", "mentioned", "absent"]
EXPECTATIONS = ["beat", "miss", "inline", "no_expectation_stated"]

SYSTEM = (
    "You classify a financial news item with respect to ONE named company. "
    "You never predict prices, returns or direction; you only describe the text you are given. "
    "role: 'subject' if the item is substantially about this company, 'mentioned' if it is named "
    "in passing or as one of several, 'absent' if this company does not appear. "
    "is_new_fact: true only for a NEW dated company development; false for recaps, listicles, "
    "'stocks moving' aggregates, opinion, previews and reprints of older news. "
    "expectation: 'beat'/'miss'/'inline' only if the text itself names an expectation or estimate "
    "and says how the outcome compared; otherwise 'no_expectation_stated'."
)

#: A STRICT schema, not a prose request. Asked in prose, the model returned
#: `none_of_above`, `financing|m_and_a`, `milestone` and `corporate` -- values
#: outside the declared enum -- which would have silently become new feature
#: columns downstream. The schema makes an out-of-enum answer impossible.
SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "news_relevance",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["role", "is_new_fact", "event_type", "expectation"],
            "properties": {
                "role": {"type": "string", "enum": ROLES},
                "is_new_fact": {"type": "boolean"},
                "event_type": {"type": "string", "enum": EVENT_TYPES},
                "expectation": {"type": "string", "enum": EXPECTATIONS},
            },
        },
    },
}


class RelevanceRefusal(RuntimeError):
    pass


def _key() -> str:
    """The full key, under either name Murat has used for it.

    `GTP_TOKEN` is what he pasted into the Aegis `.env`; `AAT_OPENAI_API_KEY` is
    what this repo's provider row reads. Accepting both is one line and stops a
    working key reading as a missing one -- which is exactly what happened on
    2026-08-30, when a truncated 109-character paste under the second name
    returned 401 while the full 164-character key sat under the first.
    """
    for name in ("AAT_OPENAI_API_KEY", "GTP_TOKEN", "OPENAI_API_KEY"):
        v = (os.getenv(name) or "").strip()
        if v:
            return v
    raise RelevanceRefusal("no OpenAI key: set AAT_OPENAI_API_KEY or GTP_TOKEN")


def out_path(month: str) -> Path:
    return OUT / f"{month}.jsonl"


def load_labels() -> dict[str, dict]:
    """Every label written so far, keyed `uid|SYMBOL`. Later rows win."""
    out: dict[str, dict] = {}
    if not OUT.exists():
        return out
    for p in sorted(OUT.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            out[f"{r['uid']}|{r['symbol']}"] = r
    return out


def pending(labels: dict[str, dict], *, since: str | None = None) -> list[tuple[dict, str]]:
    """(observation, symbol) pairs with no label yet.

    One row can carry several tickers and the answer differs per ticker -- an
    item is the SUBJECT of one company and a passing MENTION of the other four
    -- so the unit is the PAIR, never the row.
    """
    todo: list[tuple[dict, str]] = []
    for p in sorted(OBS.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("kind") != "news" or not o.get("uid"):
                continue
            if since and str(o.get("effective_at") or "") < since:
                continue
            for sym in (o.get("symbols") or []):
                if f"{o['uid']}|{sym}" not in labels:
                    todo.append((o, sym))
    return todo


def classify(obs: dict, symbol: str, *, model: str = MODEL, timeout: float = 60.0) -> tuple[dict, dict]:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Company ticker: {symbol}\n"
                                        f"Title: {obs.get('title', '')}\n"
                                        f"Body: {(obs.get('body') or '')[:700]}"},
        ],
        "max_completion_tokens": 300,
        "reasoning_effort": "minimal",
        "response_format": SCHEMA,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"})
    last = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
            choice = data["choices"][0]
            if choice.get("finish_reason") == "length":
                raise RelevanceRefusal("truncated at max_completion_tokens")
            return json.loads(choice["message"]["content"]), data.get("usage") or {}
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
            if exc.code in (400, 401, 403):          # not transient: fail loudly
                raise RelevanceRefusal(f"{last} {exc.read().decode()[:200]}") from exc
            time.sleep(1.5 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, KeyError) as exc:
            last = f"{type(exc).__name__}: {exc}"
            time.sleep(1.5 * (attempt + 1))
    raise RelevanceRefusal(f"3 attempts failed: {last}")


def run(*, limit: int | None, max_usd: float, workers: int, model: str,
        since: str | None, dry: bool) -> int:
    labels = load_labels()
    todo = pending(labels, since=since)
    print(f"  labelled already : {len(labels):,}")
    print(f"  pending pairs    : {len(todo):,}")
    if limit:
        todo = todo[:limit]
    # ~180 prompt + ~28 completion tokens per pair, measured on the 250-row sample.
    est = len(todo) * (180 / 1e6 * PRICE_IN + 28 / 1e6 * PRICE_OUT)
    print(f"  this run         : {len(todo):,} pairs, estimated ${est:.2f} (cap ${max_usd:.2f})")
    if est > max_usd:
        print(f"  REFUSED: estimate ${est:.2f} exceeds --max-usd ${max_usd:.2f}. Raise the cap or use --limit.")
        return 2
    if dry or not todo:
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tin = tout = 0
    ok = fail = 0
    t0 = time.time()

    def one(pair):
        obs, sym = pair
        try:
            j, usage = classify(obs, sym, model=model)
        except RelevanceRefusal as exc:
            return None, str(exc), obs, sym, {}
        return j, None, obs, sym, usage

    # FLUSHED EVERY `FLUSH_EVERY` LABELS, NOT AT THE END.
    #
    # The first draft buffered all 64,525 labels in memory and wrote once, after
    # ~45 minutes. That makes `--resume`-by-cache a promise the code does not
    # keep: any crash, Ctrl-C or laptop sleep throws away the whole run AND the
    # money spent on it, and the next run starts from zero because nothing was
    # ever on disk. Appending in batches costs nothing and makes the restart
    # real -- `load_labels()` picks up exactly where the last flush landed.
    FLUSH_EVERY = 500
    buckets: dict[str, list[str]] = {}

    def flush() -> None:
        for month, lines in buckets.items():
            if lines:
                with out_path(month).open("a", encoding="utf-8") as fh:
                    fh.write("\n".join(lines) + "\n")
        buckets.clear()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, (j, err, obs, sym, usage) in enumerate(ex.map(one, todo), 1):
            if err:
                fail += 1
                if fail <= 5:
                    print(f"    refusal: {err[:130]}")
                if fail > 50 and fail > ok:
                    print("  ABORTING: more refusals than successes. Check the key and the model.")
                    break
                continue
            ok += 1
            tin += usage.get("prompt_tokens", 0)
            tout += usage.get("completion_tokens", 0)
            month = str(obs.get("effective_at") or obs.get("observed_at") or "")[:7] or "unknown"
            buckets.setdefault(month, []).append(json.dumps({
                "uid": obs["uid"], "symbol": sym,
                "effective_at": obs.get("effective_at"), "observed_at": obs.get("observed_at"),
                "source": obs.get("source"), "role": j["role"], "is_new_fact": j["is_new_fact"],
                "event_type": j["event_type"], "expectation": j["expectation"],
                "model": model, "classified_at": stamp,
            }, sort_keys=True))
            if ok % FLUSH_EVERY == 0:
                flush()
            if i % 2000 == 0:
                print(f"    {i:,}/{len(todo):,}  ${tin / 1e6 * PRICE_IN + tout / 1e6 * PRICE_OUT:.2f}  "
                      f"{i / max(time.time() - t0, 1e-9):.0f}/s", flush=True)

    flush()
    cost = tin / 1e6 * PRICE_IN + tout / 1e6 * PRICE_OUT
    print(f"\n  {ok:,} labelled, {fail:,} refused, {time.time() - t0:.0f}s, "
          f"{tin:,} in / {tout:,} out tokens, ${cost:.3f}")
    return 0


def summarise() -> int:
    import collections
    labels = load_labels()
    if not labels:
        print("  no labels yet")
        return 1
    role = collections.Counter(r["role"] for r in labels.values())
    newf = collections.Counter(bool(r["is_new_fact"]) for r in labels.values())
    real = [r for r in labels.values() if r["role"] == "subject" and r["is_new_fact"]]
    n = len(labels)
    print(f"\n  {n:,} labelled (uid x symbol pairs)")
    print("  role of the tagged symbol:")
    for k, v in role.most_common():
        print(f"    {k:10s} {v:7,}  {v / n:6.1%}")
    print("  is a new dated company fact:")
    for k, v in newf.most_common():
        print(f"    {str(k):10s} {v:7,}  {v / n:6.1%}")
    print(f"\n  SUBJECT and NEW FACT: {len(real):,} / {n:,} = {len(real) / n:.1%}"
          f"   <- what an event count should count")
    print("  event_type among those:")
    for k, v in collections.Counter(r["event_type"] for r in real).most_common():
        print(f"    {k:16s} {v:6,}")
    bysrc: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    for r in labels.values():
        b = bysrc[r.get("source") or "?"]
        b[1] += 1
        if r["role"] == "subject" and r["is_new_fact"]:
            b[0] += 1
    print("\n  subject+new rate by source (the sensor's signal-to-noise):")
    for s, (k, tot) in sorted(bysrc.items(), key=lambda x: -x[1][1])[:10]:
        print(f"    {s:32s} {k:6,}/{tot:6,} = {k / tot:5.1%}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=None, help="classify at most N pairs this run")
    ap.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--since", default=None, help="only items effective on/after this date")
    ap.add_argument("--dry-run", action="store_true", help="count and price the run, call nothing")
    ap.add_argument("--summary", action="store_true", help="report the labels already written")
    a = ap.parse_args(argv)
    config.load_env()
    if a.summary:
        return summarise()
    rc = run(limit=a.limit, max_usd=a.max_usd, workers=a.workers, model=a.model,
             since=a.since, dry=a.dry_run)
    if rc == 0 and not a.dry_run:
        summarise()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
