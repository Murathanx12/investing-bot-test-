"""Run the logic brain over today's tracker candidates, and grade it later.

    python -m scripts.logic_brain --run                # score today's candidates
    python -m scripts.logic_brain --run --limit 20     # a cheap smoke run
    python -m scripts.logic_brain --show               # what it said and why
    python -m scripts.logic_brain --grade --horizon 5  # did it beat the rule?

WHAT IT COSTS. ~200 names on `deepseek-chat` is about $0.12 a run, measured
against the token counts the provider returns rather than estimated. The run
refuses to start without a budget and stops the moment it is reached, so the
failure mode is a short run rather than a surprise bill.

WHAT IT MAY DO. Move the rule's `p_up_21d` by at most +/-0.10, and only while
naming which supplied fact caused it. Everything else about a name -- whether it
is a candidate at all, how large a position it could take, when it may trade --
is decided elsewhere, by rules, under caps. See `alpha/logic_brain.py` for why.

NOTHING HERE PLACES AN ORDER.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from alpha import config, logic_brain as LB, tracker  # noqa: E402
from alpha.council import providers  # noqa: E402
from alpha.sources import corpus  # noqa: E402

STORE = ROOT / "state" / "logic_brain"
RELEVANCE = corpus.CORPUS / "relevance"
PROVIDER = "deepseek"
CALLER = "logic_brain"

WHY = ("Decides whether each tracker candidate's rule probability is adjusted up or "
       "down before the books rank on it, which changes which names hack3/hack4/hack6 "
       "select and size tomorrow morning.")


def _day() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def path_for(day: str) -> Path:
    return STORE / f"{day}.jsonl"


def load_run(day: str) -> list[dict]:
    p = path_for(day)
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


def load_relevance(since_month: str) -> list[dict]:
    """Relevance labels from the shards that could contain the window.

    Reads by MONTH shard rather than the whole store: the corpus labels are
    hundreds of thousands of rows and a five-session window touches two files.
    """
    if not RELEVANCE.exists():
        return []
    out = []
    for shard in sorted(RELEVANCE.glob("*.jsonl")):
        if shard.stem < since_month:
            continue
        for line in shard.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def _titles_for(uids: set[str], since: str, as_of: str) -> dict[str, str]:
    """Headlines for the labelled facts, so the brain reads text and not an id."""
    out = {}
    for r in corpus.read(since=since, as_of=as_of):
        uid = r.get("uid")
        if uid in uids:
            out[uid] = r.get("title") or ""
    return out


def run(day: str | None, limit: int | None, max_usd: float, provider: str,
        include_factless: bool = False) -> int:
    config.load_env()
    day = day or _day()
    from scripts import tracker as tracker_cli
    from scripts.tracker import merge_book_numbers

    tday = tracker_cli.latest_day()
    if not tday:
        print("REFUSED: no tracker day on disk. Run `python -m scripts.tracker --refresh`.")
        return 1
    rows = tracker.build_rows(tracker_cli.load_day(tday))
    prev = tracker_cli.latest_day(before=tday)
    tracker.apply_status(rows, prev_by_symbol={r["symbol"]: r for r in
                                               tracker_cli.load_day(prev)} if prev else {})
    n_joined, note = merge_book_numbers(rows, tday)
    print(f"tracker {tday}: {len(rows)} rows | book: {note}")
    if not n_joined:
        print("REFUSED: no rule numbers to adjust. The brain ADJUSTS a forecast; with "
              "nothing to adjust it would be inventing one, which is the thing it is "
              "built not to do.\n  Seal a book first: "
              "python -m scripts.prediction_book --seal --universe tracker")
        return 1

    cands = [r for r in tracker.candidates(rows)
             if r.get("p_up_21d") is not None]
    print(f"candidates with a rule number: {len(cands)}")
    done = {r["symbol"] for r in load_run(day)}

    since = (datetime.fromisoformat(day).date().toordinal()
             - LB.FACT_LOOKBACK_SESSIONS * 2)
    since_iso = datetime.fromordinal(since).date().isoformat()
    labels = load_relevance(since_iso[:7])
    print(f"relevance labels in the window: {len(labels):,}")
    facts_by_sym = {r["symbol"]: LB.facts_for(labels, r["symbol"], as_of=day,
                                              lookback_days=LB.FACT_LOOKBACK_SESSIONS * 2)
                    for r in cands}
    with_facts = [r for r in cands if facts_by_sym.get(r["symbol"])]

    # ONLY THE NAMES IT CAN SEE. A candidate with no supplied fact cannot be
    # adjusted -- `LB.bound` reverts it to the rule by construction -- so paying
    # for that call buys a copy of a number we already have. Measured on
    # 2026-08-30: 16 of 749 candidates had a new dated fact in the window, so
    # the top-200-by-upside ordering would have spent 184 calls to return
    # "unchanged" 184 times.
    #
    # THE 733 ARE THE FINDING, NOT THE 16. Our corpus is a 152-name panel and
    # Benzinga files 1,566 items on NVDA against three on a small biotech, so
    # "which names have facts" is very nearly "which names are famous" -- the
    # same asymmetry that made the old book select MU. The brain is therefore a
    # MEGA-CAP-ONLY instrument today, and that is a statement about our news
    # coverage, not about the brain.
    print(f"candidates with at least one new dated fact in the window: "
          f"{len(with_facts)} of {len(cands)}"
          f"  ({len(with_facts) / max(len(cands), 1):.1%})")
    if not with_facts:
        print("REFUSED: not one candidate has a new dated fact in the window. Every call "
              "would return the rule's own number unchanged, which is not worth paying "
              "for. Check that the corpus has been ingested and labelled for this week.")
        return 1

    pool = with_facts if not include_factless else cands
    pool = sorted(pool, key=lambda r: (-len(facts_by_sym.get(r["symbol"]) or []),
                                       -(r.get("upside") or 0)))
    todo = [r for r in pool if r["symbol"] not in done][:(limit or LB.DEFAULT_MAX_NAMES)]
    if not todo:
        print(f"nothing to do ({len(done)} already scored today)")
        return 0
    uids = {f["uid"] for r in todo for f in (facts_by_sym.get(r["symbol"]) or [])
            if f.get("uid")}
    titles = _titles_for(uids, since_iso, day) if uids else {}
    print(f"scoring {len(todo)} names"
          + ("" if not include_factless else " (INCLUDING factless ones, as asked)"))

    STORE.mkdir(parents=True, exist_ok=True)
    spent, t0 = 0.0, time.time()
    written = 0
    fh = path_for(day).open("a", encoding="utf-8")
    try:
        for i, r in enumerate(todo, 1):
            if spent >= max_usd:
                print(f"STOPPED at the ${max_usd:.2f} budget after {i - 1} names. "
                      f"{len(todo) - i + 1} not scored -- rerun to continue.")
                break
            available = facts_by_sym.get(r["symbol"]) or []
            facts = available[:LB.MAX_FACTS_PER_NAME]
            for f in facts:
                f["title"] = titles.get(f.get("uid"), "")
            rule = {k: r.get(k) for k in
                    ("p_up_21d", "exp_return", "downside_5pct", "confidence")}
            user = LB.build_user_prompt(r, rule, facts)
            try:
                ans, meta = providers.chat_json(
                    provider, LB.SYSTEM, user, caller=CALLER, why=WHY,
                    max_tokens=500, temperature=0.1)
            except Exception as e:                                      # noqa: BLE001
                print(f"  {r['symbol']:8s} REFUSED {type(e).__name__}: {str(e)[:90]}")
                continue
            # `chat_json` returns token counts at the TOP level of `meta`, not
            # under a `usage` key. Reading the wrong shape made `_cost` return
            # 0.0 for every call, which is a budget that can never bind -- the
            # one bug class that bills while you sleep.
            spent += _cost(meta or {})
            bounded, notes = LB.bound(ans, rule, facts)
            out = {
                "schema": LB.SCHEMA_NAME, "day": day, "tracker_day": tday,
                "symbol": r["symbol"], "sector": r.get("sector"),
                "status": r.get("status"), "provider": provider,
                "model": (meta or {}).get("model"),
                "usage": {k: (meta or {}).get(k) for k in
                          ("prompt_tokens", "completion_tokens", "latency_s")},
                "n_facts_supplied": len(facts),
                "n_facts_available": len(available),
                "scored_at": datetime.now(timezone.utc).isoformat(),
                "brain_notes": notes,
                # A guard that fires without keeping what it acted on cannot be
                # debugged: on the first run three rows said "p_up unreadable"
                # and nothing on disk could say what had actually come back.
                "raw_answer": (ans if notes else None),
                **bounded,
            }
            fh.write(json.dumps(out) + "\n")
            fh.flush()
            written += 1
            if i % 20 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}  ${spent:.3f}  "
                      f"{i / max(time.time() - t0, 1e-9):.1f}/s")
    finally:
        fh.close()

    rowsw = load_run(day)
    summary = LB.run_summary(rowsw)
    print(f"\nwrote {written} rows -> {path_for(day)}")
    print(f"cost ${spent:.3f} of the ${max_usd:.2f} budget")
    for k, v in summary.items():
        print(f"  {k:26s} {v}")
    if summary["n_adjusted"] == 0 and summary["n_scored"]:
        print("\n  EVERY name came back unchanged. With facts supplied that IS a verdict "
              "-- the brain read them and found nothing that moves a 21-session view. "
              "Without facts supplied it is arithmetic, not a verdict: check the "
              "`candidates with at least one new dated fact` line above.")
    return 0


#: deepseek-chat, per 1M tokens, read from the provider's price page 2026-08-30.
PRICE_IN, PRICE_OUT = 0.27, 1.10


def _cost(meta: dict) -> float:
    """Cost from the counts the PROVIDER returned, never from an estimate.

    Refuses silently-zero: a missing count is charged at a conservative
    placeholder rather than as free, so an API that stops reporting usage
    cannot turn the budget off.
    """
    pin = meta.get("prompt_tokens")
    pout = meta.get("completion_tokens")
    if pin is None and pout is None:
        return (1500 / 1e6 * PRICE_IN) + (300 / 1e6 * PRICE_OUT)
    return ((pin or 0) / 1e6 * PRICE_IN) + ((pout or 0) / 1e6 * PRICE_OUT)


def show(day: str | None, n: int) -> int:
    day = day or _day()
    rows = load_run(day)
    if not rows:
        print(f"no logic-brain run for {day}")
        return 1
    s = LB.run_summary(rows)
    print(f"LOGIC BRAIN {day} -- {s['n_scored']} names, {s['n_adjusted']} adjusted, "
          f"{s['n_clipped']} clipped\n")
    adj = sorted([r for r in rows if r.get("fact_id") != LB.NO_FACT],
                 key=lambda r: -abs(r.get("adjustment") or 0))
    for r in adj[:n]:
        print(f"  {r['symbol']:8s} p_up {r['rule_p_up_21d']:.3f} -> {r['p_up_21d']:.3f} "
              f"({r['adjustment']:+.3f}){'  CLIPPED' if r.get('clipped') else ''}  "
              f"[{r['fact_id']}]")
        print(f"           {r['reason'][:120]}")
        for note in r.get("brain_notes") or []:
            print(f"           GUARD: {note}")
    if not adj:
        print("  no name was adjusted -- every one came back on the rule's numbers")
    print()
    for k, v in s.items():
        print(f"  {k:26s} {v}")
    return 0


def grade(day: str | None, horizon: int) -> int:
    """Did the brain beat the rule? Needs `horizon` sessions to have passed."""
    day = day or _day()
    rows = load_run(day)
    if not rows:
        print(f"no logic-brain run for {day}")
        return 1
    from alpha.broker.alpaca import AlpacaPaper
    from alpha.broker.base import BrokerRefusal
    # ONE SPY close source: the benchmark symbol and its TAPE are named by
    # `alpha.spy`, not by whichever default this helper happens to carry.
    from alpha import spy as _spy
    syms = sorted({r["symbol"] for r in rows} | {_spy.SYMBOL})
    client = AlpacaPaper()
    bars = {}
    for i in range(0, len(syms), 200):
        try:
            bars.update(client.stock_bars_multi(syms[i:i + 200], start=day,
                                                timeframe="1Day", feed=_spy.FEED))
        except BrokerRefusal as exc:
            print(f"  bar batch {i}: {exc}")
    spy = bars.get(_spy.SYMBOL) or []
    if len(spy) <= horizon:
        print(f"REFUSED: only {len(spy)} SPY sessions since {day}; {horizon + 1} are "
              f"needed. A grade computed on a shorter window is a different horizon "
              f"wearing this one's name.")
        return 1

    def rel(sym: str) -> float | None:
        bs = bars.get(sym) or []
        if len(bs) <= horizon:
            return None
        a, b = bs[0].get("c"), bs[horizon].get("c")
        sa, sb = spy[0].get("c"), spy[horizon].get("c")
        if not a or not b or not sa or not sb:
            return None
        return (b / a - 1.0) - (sb / sa - 1.0)

    outcomes = {s: v for s in syms if s != _spy.SYMBOL and (v := rel(s)) is not None}
    g = LB.grade(rows, outcomes)
    print(f"LOGIC BRAIN GRADE  {day}  horizon {horizon} sessions  "
          f"({len(outcomes)} names resolved)")
    for k, v in g.items():
        print(f"  {k:28s} {v}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--run", action="store_true")
    p.add_argument("--show", action="store_true")
    p.add_argument("--grade", action="store_true")
    p.add_argument("--day", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--n", type=int, default=25)
    p.add_argument("--horizon", type=int, default=5)
    p.add_argument("--max-usd", type=float, default=LB.DEFAULT_MAX_USD)
    p.add_argument("--provider", default=PROVIDER)
    p.add_argument("--include-factless", action="store_true",
                   help="also score candidates with no new dated fact. Every one "
                        "of those comes back on the rule's numbers by "
                        "construction, so this buys the null and nothing else.")
    a = p.parse_args(argv)
    if a.max_usd <= 0:
        print("REFUSED: --max-usd must be positive. A run with no budget is a run "
              "with no stopping rule.")
        return 2
    if a.run:
        return run(a.day, a.limit, a.max_usd, a.provider, a.include_factless)
    if a.show:
        return show(a.day, a.n)
    if a.grade:
        return grade(a.day, a.horizon)
    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
