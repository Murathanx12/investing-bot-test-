"""Smoke checks for OBSERVATION_CORPUS_v1 and the two collectors. No keys, no network.

Run: python run_tests.py -k corpus

What these pin, in order of how much a regression would cost:

1. **the point-in-time filter** -- `read(as_of=)` must bound `observed_at`, not
   `effective_at`. A forward catalyst is observed today and effective in
   November; filtering it by its effective date would let a backtest read the
   future, improve every number, and announce nothing;
2. **the truncation split** -- Finnhub caps a calendar window at 1500 rows and
   returns the TAIL. The first live run hit that cap three times across
   earnings season. A version that accepted a capped window would silently
   lose the busiest weeks of the horizon;
3. **the reconciliation** -- the first live digest returned a PAST event as a
   forward catalyst and passed Murat's condition (d) with zero forward rows in
   the corpus. Code checks the claim; the prompt asking nicely was not enough;
4. **dedupe by content** -- a re-run of a year-long backfill must append
   nothing;
5. **the reasoning-model truncation** -- `finish_reason == "length"` with a
   clipped body must refuse as a BUDGET problem, because reporting it as a
   dead provider gets a live model struck off the rotation.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


# Point the store at a scratch dir BEFORE importing it -- the module resolves
# its paths at import time, and a test that wrote into the real corpus would
# poison the very record it is meant to protect.
_TMP = tempfile.mkdtemp(prefix="aat_corpus_test_")
os.environ["AAT_STATE_DIR"] = _TMP

from alpha.sources import corpus                                        # noqa: E402

TODAY = date.today().isoformat()
SOON = (date.today() + timedelta(days=40)).isoformat()
BACK = (date.today() - timedelta(days=40)).isoformat()

print("\n-- schema refuses what cannot be filtered later")
try:
    corpus.Observation(kind="news", tense="past", title="x", source="s", source_type="media",
                       observed_at="", effective_at=TODAY)
    check("missing observed_at refused", False)
except corpus.CorpusRefusal:
    check("missing observed_at refused", True)
try:
    corpus.Observation(kind="rumour", tense="past", title="x", source="s", source_type="media",
                       observed_at=TODAY, effective_at=TODAY)
    check("unknown kind refused", False)
except corpus.CorpusRefusal:
    check("unknown kind refused", True)
try:
    corpus.Observation(kind="news", tense="past", title="   ", source="s", source_type="media",
                       observed_at=TODAY, effective_at=TODAY)
    check("empty title refused", False)
except corpus.CorpusRefusal:
    check("empty title refused", True)

print("\n-- append is deduped by CONTENT, so a re-run costs nothing")
past = corpus.Observation(kind="news", tense="past", title="Aardvark Q2 beats", source="finnhub:bz",
                          source_type="media", observed_at=f"{BACK}T12:00:00+00:00",
                          effective_at=BACK, symbols=("AARD",))
future = corpus.Observation(kind="clinical", tense="future", title="AARD HERO primary completion",
                            source="clinicaltrials.gov", source_type="government",
                            observed_at=f"{TODAY}T00:00:00+00:00", effective_at=SOON,
                            symbols=("AARD",), source_verified=False)
new, dup = corpus.append_many([past, future])
check("two new rows stored", (new, dup) == (2, 0), f"{new} new, {dup} dup")
new2, dup2 = corpus.append_many([past, future])
check("re-running the same backfill appends nothing", (new2, dup2) == (0, 2), f"{new2} new, {dup2} dup")
check("a body edit does not re-admit the same story",
      corpus.Observation(**{**{k: v for k, v in vars(past).items()}, "body": "edited"}).uid == past.uid)

print("\n-- POINT IN TIME: as_of bounds observed_at, never effective_at")
seen_today = corpus.read(as_of=TODAY)
check("today sees both rows", len(seen_today) == 2, str(len(seen_today)))
seen_before = corpus.read(as_of=(date.today() - timedelta(days=1)).isoformat())
check("yesterday cannot see a row observed today", [r["title"] for r in seen_before] == ["Aardvark Q2 beats"],
      str([r["title"] for r in seen_before]))
check("the future row is NOT hidden by its effective date",
      any(r["tense"] == "future" for r in corpus.read(as_of=TODAY)))
check("tense filter separates diary from history",
      len(corpus.read(tense="future")) == 1 and len(corpus.read(tense="past")) == 1)
check("symbol filter is case-insensitive", len(corpus.read(symbols=["aard"])) == 2)
check("effective window excludes the forward row", len(corpus.read(until=TODAY)) == 1)

print("\n-- coverage gap is reported as a NUMBER, not as silence")
cov = corpus.symbols_covered()
check("AARD counted twice", cov.get("AARD") == 2, str(cov))
st = corpus.stats()
check("stats separates future from past", st["n_future"] == 1 and st["n_observations"] == 2, str(st))
check("unverified forward row is not counted as verified", st["n_verified"] == 0)

print("\n-- iter_months pages a year without skipping a December")
months = list(corpus.iter_months("2025-11-01", "2026-02-15"))
check("Nov Dec Jan Feb, year rolls over", [m[0] for m in months] ==
      ["2025-11-01", "2025-12-01", "2026-01-01", "2026-02-01"], str([m[0] for m in months]))

print("\n-- reconcile() downgrades a claim the corpus cannot support")
from scripts.corpus_digest import reconcile                             # noqa: E402

view = {"catalysts": [{"date": BACK, "what": "Q2 results"}, {"date": SOON, "what": "HERO readout"}],
        "murat_rule": {"dated_catalyst": "pass"}}
fixes = reconcile(view, [], today=TODAY)
check("a PAST event is not a catalyst", [c["date"] for c in view["catalysts"]] == [SOON],
      str(view["catalysts"]))
check("the drop is recorded, not silent", len(view["catalysts_dropped"]) == 1 and len(fixes) >= 1)
empty = {"catalysts": [{"date": BACK, "what": "old news"}], "murat_rule": {"dated_catalyst": "pass"}}
reconcile(empty, [], today=TODAY)
check("condition (d) with no forward evidence -> unknown",
      empty["murat_rule"]["dated_catalyst"] == "unknown")
kept = {"catalysts": [], "murat_rule": {"dated_catalyst": "pass"}}
reconcile(kept, [{"effective_at": SOON}], today=TODAY)
check("condition (d) stands when the CORPUS holds a forward row",
      kept["murat_rule"]["dated_catalyst"] == "pass")
far = {"catalysts": [{"date": "2031-01-01", "what": "invented"}], "murat_rule": {"dated_catalyst": "pass"}}
fx = reconcile(far, [], today=TODAY)
check("a model-invented future date (2031) cannot sustain (d) and is dropped as outside 12 months",
      far["murat_rule"]["dated_catalyst"] == "unknown" and far["catalysts"] == [] and len(fx) >= 2)
ann = {"catalysts": [{"date": SOON, "what": "print"}], "murat_rule": {"dated_catalyst": "pass"}}
reconcile(ann, [{"effective_at": SOON}], today=TODAY)
check("a surviving catalyst is annotated in_corpus", ann["catalysts"][0].get("in_corpus") is True)

print("\n-- a capped calendar window is SPLIT, never accepted")
import scripts.catalyst_horizon as ch                                   # noqa: E402

calls = []


def fake_calendar(*, start, end):
    calls.append((start, end))
    span = (date.fromisoformat(end) - date.fromisoformat(start)).days
    # Mimic the real endpoint: a wide window returns the CAP, and returns the
    # tail of the range rather than the near end.
    if span > 7:
        return [{"symbol": "X", "date": end, "hour": "", "quarter": 1, "year": 2026}] * ch.FINNHUB_ROW_CAP
    return [{"symbol": "X", "date": start, "hour": "bmo", "quarter": 1, "year": 2026}]


_real_cal, _real_sleep = ch.finnhub.earnings_calendar, ch.time.sleep
ch.finnhub.earnings_calendar, ch.time.sleep = fake_calendar, lambda *_: None
try:
    rows, notes = ch.earnings_window("2026-09-01", "2026-09-29", step_days=14)
    check("the cap triggers a split", any("cap hit" in n for n in notes), str(notes[:2]))
    check("splitting recovers rows under the cap", all(r["date"] < "2026-09-29" or r["hour"] for r in rows))
    check("narrow windows were actually issued",
          any((date.fromisoformat(e) - date.fromisoformat(s)).days <= 7 for s, e in calls))
    quiet = ch.earnings_window("2026-09-05", "2026-09-12", step_days=7)[1]
    check("a weekend gap does not cry wolf", not quiet, str(quiet))
finally:
    ch.finnhub.earnings_calendar, ch.time.sleep = _real_cal, _real_sleep

print("\n-- a TRUNCATED episode chunk splits and retries, it does not vanish")
import scripts.corpus_digest as cd                                      # noqa: E402
from alpha.council import providers                                     # noqa: E402

seen_sizes = []
_real_chat = providers.chat_json


def fake_chat(provider, system, user, *, caller, why, max_tokens=1200, temperature=0.1):
    n = int(user.split(" headlines ")[0].split(". ")[-1])
    seen_sizes.append(n)
    if n > 8:                       # anything wide overflows, like the real one did
        raise providers.ProviderRefusal(
            f"featherless: TRUNCATED at max_tokens={max_tokens} (finish_reason=length)")
    return {"episodes": [{"date": TODAY, "event": f"chunk of {n}"}]}, {"provider": provider}


providers.chat_json = fake_chat
try:
    rows16 = [{"effective_at": TODAY, "source": "s", "title": f"h{i}", "body": ""} for i in range(16)]
    eps, refs = cd._episode_call("X", rows16, provider="featherless")
    check("a truncated chunk is split, not lost", len(eps) == 2, f"{len(eps)} episodes, {refs}")
    check("the split is halving", sorted(seen_sizes) == [8, 8, 16], str(seen_sizes))
    check("the split is recorded as a refusal line", any("split" in r for r in refs), str(refs))

    seen_sizes.clear()
    tiny = [{"effective_at": TODAY, "source": "s", "title": "h", "body": ""} for _ in range(9)]
    eps2, refs2 = cd._episode_call("X", tiny, provider="featherless")
    check("splitting bottoms out instead of recursing forever",
          len(eps2) == 2 and len(seen_sizes) == 3, f"{seen_sizes}")
finally:
    providers.chat_json = _real_chat

print("\n-- the PAID adjudicator is reached only on disagreement, and only within budget")
import scripts.corpus_digest as _cd                                     # noqa: E402

check("bulk order spends prepaid capacity first, metered last",
      _cd.BULK_ORDER[0] == "featherless" and _cd.BULK_ORDER[-1] == "deepseek", str(_cd.BULK_ORDER))
check("the free skeptics never include the metered provider",
      _cd.ADJUDICATOR not in _cd.SKEPTIC_ORDER, str(_cd.SKEPTIC_ORDER))
check("there IS a hard ceiling on paid calls",
      isinstance(_cd.ADJUDICATOR_MAX_CALLS, int) and _cd.ADJUDICATOR_MAX_CALLS > 0)
check("the adjudicator is a different family from the bulk provider",
      providers.PROVIDERS[_cd.ADJUDICATOR].family != providers.PROVIDERS[_cd.BULK_ORDER[0]].family)

print("\n-- the paid budget survives a CAPPED name (the parameter was shadowed by the sampler)")
import inspect                                                          # noqa: E402

_src = inspect.getsource(_cd.digest_one)
check("the sampler does not reassign the `budget` parameter",
      "\n        budget = " not in _src and "quota = max_headlines" in _src)
check("the adjudicator still reads budget as a mapping", 'budget["paid"]' in _src)
# The crash needed a name that was BOTH capped AND had the families disagree,
# so assert the two code paths cannot collide on a shared name again.
_names = {n for n in ("quota", "budget") if f"{n} = max_headlines" in _src}
check("headline quota and paid budget are different names", _names == {"quota"}, str(_names))

print("\n-- a capped history is SAMPLED across months, not truncated to the last one")
big = []
for mon in range(1, 13):
    for k in range(100):
        big.append({"effective_at": f"2026-{mon:02d}-15", "observed_at": f"2026-{mon:02d}-15",
                    "source": "s", "title": f"m{mon} h{k}", "body": ""})
by = {}
budget, chosen = 240, []
for r in big:
    by.setdefault(r["effective_at"][:7], []).append(r)
months_present = sorted(by)
for i, m in enumerate(sorted(months_present, key=lambda m: len(by[m]))):
    share = max(1, budget // (len(months_present) - i))
    take = by[m][-share:] if len(by[m]) > share else by[m]
    chosen += take
    budget -= len(take)
kept_months = {r["effective_at"][:7] for r in chosen}
check("every month survives the cap", len(kept_months) == 12, f"{len(kept_months)} months")
check("the budget is respected", len(chosen) == 240, str(len(chosen)))
check("the oldest month is not dropped", "2026-01" in kept_months)
# a quiet month hands its surplus back rather than losing it
by2 = {"2026-01": big[:2], "2026-02": big[:100], "2026-03": big[:100]}
budget2, chosen2 = 102, []
for i, m in enumerate(sorted(by2, key=lambda m: len(by2[m]))):
    share = max(1, budget2 // (len(by2) - i))
    take = by2[m][-share:] if len(by2[m]) > share else by2[m]
    chosen2 += take
    budget2 -= len(take)
check("a quiet month's unused share flows to the busy ones", len(chosen2) == 102, str(len(chosen2)))

print("\n-- a purge leaves a receipt and rebuilds the index")
junk = corpus.Observation(kind="macro", tense="future", title="FOMC Press Release",
                          source="fred:releases/dates", source_type="government",
                          observed_at=f"{TODAY}T00:00:00+00:00", effective_at=SOON)
corpus.append_many([junk])
check("junk row stored", len(corpus.read(kinds=["macro"])) == 1)
dry = corpus.purge_source("fred", reason="test", dry_run=True)
check("dry run removes nothing", dry["removed"] == 1 and len(corpus.read(kinds=["macro"])) == 1)
wet = corpus.purge_source("fred", reason="test: endpoint slip", dry_run=False)
check("purge removes the bad source only", wet["removed"] == 1 and len(corpus.read(kinds=["macro"])) == 0)
check("purge keeps everything else", len(corpus.read()) == 2, str(len(corpus.read())))
check("purge is recorded, never silent", (corpus.CORPUS / "purges.jsonl").exists())
check("the index is rebuilt so a fixed collector can re-add",
      corpus.append_many([junk]) == (1, 0))
corpus.purge_source("fred", reason="test cleanup", dry_run=False)

print("\n-- a RATE LIMIT is retried, never recorded as 'this company had no news'")
import scripts.news_backfill as nb                                      # noqa: E402

_real_news, _real_nb_sleep = nb.finnhub.company_news, nb.time.sleep
nb.time.sleep = lambda *_: None
attempts = {"n": 0}


def flaky_news(symbol, *, start, end):
    attempts["n"] += 1
    if attempts["n"] < 3:
        raise nb.SourceRefusal("GET https://finnhub.io/api/v1/company-news -> HTTP 429")
    return [{"datetime": 1787000000, "headline": "late but real", "summary": "", "source": "X"}]


try:
    nb.finnhub.company_news = flaky_news
    obs, refs = nb.finnhub_history("SRRK", "2026-01-01", "2026-02-01")
    check("a 429 is retried, not surrendered to", len(obs) == 1 and not refs, f"{len(obs)} obs, {refs}")
    check("the retry happened more than once", attempts["n"] == 3, str(attempts["n"]))

    attempts["n"] = 0

    def always_429(symbol, *, start, end):
        attempts["n"] += 1
        raise nb.SourceRefusal("GET ... -> HTTP 429")

    nb.finnhub.company_news = always_429
    obs2, refs2 = nb.finnhub_history("SRRK", "2026-01-01", "2026-02-01")
    check("a persistent 429 REFUSES rather than returning silence",
          obs2 == [] and len(refs2) == 1 and "429" in refs2[0], str(refs2))
    check("it gave up only after 4 tries", attempts["n"] == 4, str(attempts["n"]))

    def not_429(symbol, *, start, end):
        raise nb.SourceRefusal("GET ... -> HTTP 403")

    nb.finnhub.company_news = not_429
    check("a non-429 error is not retried into a rate limit",
          nb.finnhub_history("X", "2026-01-01", "2026-02-01")[1][0].endswith("HTTP 403"))
finally:
    nb.finnhub.company_news, nb.time.sleep = _real_news, _real_nb_sleep

print("\n-- the dedupe index can always be re-derived from the shards")
before = len(corpus.read())
corpus._INDEX = set()                       # simulate a lost / clobbered index
check("rebuild recovers every uid", corpus.rebuild_index() == before, f"{before} rows")
check("rebuilding does not change the rows", len(corpus.read()) == before)

print("\n-- FRED cadence: a release padded to daily is dropped, measured not asserted")
check("the daily fed-funds series is excluded by name",
      bool(ch.MACRO_EXCLUDE.search("FOMC Press Release")))
check("a real event release is not excluded",
      not ch.MACRO_EXCLUDE.search("Employment Situation")
      and bool(ch.MACRO_PATTERNS.search("Employment Situation")))
check("regional cuts are excluded", bool(ch.MACRO_EXCLUDE.search("Gross Domestic Product by County")))
check("the calendar declares what it knows it lacks",
      any("FOMC" in g for g in ch.KNOWN_GAPS) and any("PDUFA" in g for g in ch.KNOWN_GAPS))

print("\n-- a REASONING model that ran out of budget is a budget refusal, not a dead model")
from alpha.council import providers                                     # noqa: E402


def fake_post(url, body, *, headers, caller, why, timeout):
    return ({"choices": [{"finish_reason": "length",
                          "message": {"content": '{"ok": true, "n": 3',
                                      "reasoning_content": "The user wants JSON. Need"}}],
             "usage": {}}, 0.1)


_real_post, _real_key = providers.llm_post, providers.PROVIDERS["nvidia_kimi"].key
providers.llm_post = fake_post
providers.PROVIDERS["nvidia_kimi"].__class__.key = lambda self: "test-key"
try:
    providers.chat_json("nvidia_kimi", "s", "u", caller="t",
                        why="Decides whether this provider is selected for the digest pass.",
                        max_tokens=64)
    check("truncated reply refused", False)
except providers.ProviderRefusal as exc:
    check("truncated reply refused", True)
    check("the refusal names the BUDGET, not a broken model",
          "TRUNCATED" in str(exc) and "max_tokens" in str(exc), str(exc)[:90])
    check("it does not claim the provider is dead", "non-JSON" not in str(exc))
finally:
    providers.llm_post = _real_post
    providers.PROVIDERS["nvidia_kimi"].__class__.key = _real_key

print(f"\n{len(fails)} failure(s)" + (": " + ", ".join(fails) if fails else ""))
raise SystemExit(1 if fails else 0)
