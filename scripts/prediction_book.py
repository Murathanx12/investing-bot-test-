"""THE SEALED PRE-OPEN BOOK -- what we expect, written down before the open and
hashed, so that "we called that" is checkable instead of remembered.

    python -m scripts.prediction_book --seal            # build and seal today's book
    python -m scripts.prediction_book --show            # print it
    python -m scripts.prediction_book --grade --day D   # grade a sealed day
    python -m scripts.prediction_book --verify          # re-hash every sealed book

WHY IT IS SEALED, AND WHAT THAT IS WORTH
========================================
The competition write-up, the roadmap and the postmortems all want to say what
the engine expected BEFORE the session. Without a sealed artefact that sentence
is a memory, and a memory that survives a good day and forgets a bad one is not
evidence of anything. So: one file per ET trading day, a sha256 of its own
content stored inside it, and the same hash appended to `seals.jsonl`, which is
append-only. Re-writing a book after the fact is possible -- nothing here can
stop a determined author -- but it cannot be done SILENTLY, which is the whole
of what tamper-evidence buys.

WHAT IT PREDICTS FROM, AND WHY NOT THE NARRATIVE
================================================
`scripts/blind_tournament` asked whether blinded news carries direction:
120 sealed cells, blinding held (0/120 identified), **hit 45% against a 47%
shuffled null, IC -0.18**. No information, and worse when confident. So the
model's prose does not enter this book.

`scripts/corpus_features --ic` asked the same question of the COUNTS. On a
23-symbol panel the answer looked like yes (insider +0.148, earnings +0.155).
**On 152 symbols, over the same period and through the same harness, ZERO of
29 features have a 95% CI excluding zero.** The details and the reproduction
check are in the `SIGNALS` block below; the short version is that the 23 were
Murat's own names and a curated list is not a cross-section.

So this book currently CLAIMS NOTHING. It still ranks, still seals, and is
still worth running: it is T7's control beside the named digest, and every
sealed day is a vintage the next measurement can use. `CLAIMING` is derived
from the CIs, so it turns itself on when a signal earns it.

**The honest n is 11 DATE BLOCKS, not 36,841 symbol-days**, and 29 features
were screened. It gets order authority when it beats its own null out of
sample, and not before.

POINT IN TIME, TWICE OVER
=========================
Corpus rows are cut at the SEAL INSTANT (not the seal day), so a headline
published at 09:20 cannot be in a 09:15 book even when the book is rebuilt
later. Bars are cut at the last CLOSED session, because the free SIP plan
refuses recent data and because a signal needing today's close could not have
traded today's open anyway. Both bounds are written into the receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from alpha import config, drivers, murat_rule
from alpha import contract as contract_mod
from alpha import tracker as _tracker
from alpha import exits as _exits
from alpha.sources import corpus, features

ROOT = Path(__file__).resolve().parent.parent
BOOKS = Path(os.getenv("AAT_LEDGER_DIR") or (ROOT / "state")) / "predictions"
SEALS = BOOKS / "seals.jsonl"
PANEL = corpus.CORPUS / "features"
BENCH = "SPY"

#: Horizon of the claim, in SESSIONS. 21 is where the event counts were measured;
#: 5 is carried as a checkpoint so a book can be looked at before a month passes.
HORIZON_SESSIONS = 21
CHECKPOINT_SESSIONS = 5

#: feature -> (weight, 95% CI) at the WIDE measurement. The weights ARE the ICs,
#: so a reader checks them against the receipt instead of trusting a hand-tuned
#: number.
#:
#: THE NUMBERS BELOW ARE NOT THE ONES THIS BOOK WAS FIRST BUILT ON.
#: On 2026-08-29 the panel covered 23 symbols -- Murat's own names plus the
#: benchmarks, a list curated because those names were interesting -- and the
#: event counts looked strong. Rebuilt on 152 symbols over the SAME period with
#: the SAME harness (`ic_2026-08-30_wide152.json`), every one of them collapses:
#:
#:     feature                 23 symbols    152 symbols   95% CI (wide)
#:     ev_insider_20d              +0.148         +0.023   [-0.004, +0.046]
#:     ev_earnings_20d             +0.155         +0.005   [-0.052, +0.059]
#:     ev_analyst_rating_20d       +0.098         +0.020   [-0.032, +0.072]
#:     ev_contract_20d             +0.103         -0.000   [-0.041, +0.036]
#:     ev_macro_20d                +0.118         +0.040   [-0.011, +0.085]
#:
#: **ZERO of 29 features have a 95% CI excluding zero on the wide panel.** The
#: harness is not the difference: re-running the SAME 23 symbols from the wide
#: build reproduces +0.139 / +0.145 / +0.086, so the collapse is the universe.
#: That is the `feedback-a-hand-picked-universe-is-survivorship-bias` lesson at
#: full strength -- when a curated list and a broad screen disagree, the screen
#: is right.
#:
#: So the book keeps the ranking, keeps sealing, and CLAIMS NOTHING: `CLAIMING`
#: is False until a feature clears zero on a universe nobody chose. A sealed
#: book of no claims is still worth writing -- it is the control T7 needs, and
#: it accrues the vintages that make the next measurement possible.
SIGNALS: dict[str, tuple[float, tuple[float, float]]] = {
    "ev_insider_20d": (0.023, (-0.004, 0.046)),
    "ev_earnings_20d": (0.005, (-0.052, 0.059)),
    "ev_contract_20d": (0.000, (-0.041, 0.036)),
    "ev_analyst_rating_20d": (0.020, (-0.032, 0.072)),
}
IC_RECEIPT = "state/corpus/features/ic_2026-08-30_wide152.json"

#: Does any signal's 95% CI exclude zero on the universe we did not choose?
#: Derived, not asserted, so it flips on its own when a future measurement
#: earns it -- a constant set by hand would still say False after the evidence
#: changed, and would still say True after it went away.
CLAIMING = any(lo > 0 or hi < 0 for _, (lo, hi) in SIGNALS.values())

#: THE SECOND GENERATOR, and why the book stopped being unable to claim.
#:
#: `CLAIMING` above is derived from `SIGNALS`, and on a universe nobody curated
#: no signal clears zero -- so `event_counts_v1` can never claim, whatever it
#: reads. On 2026-08-30 it looked at 151 names and claimed 0, which Murat
#: correctly read as a design fact rather than as a verdict on the names.
#:
#: `murat_rule_v1` is a SEPARATE generator with its own frozen contract, not a
#: loosened gate on this one. Both write rows into the same sealed book, each
#: row stamped with its `generator`, so Friday's autopsy compares a rule that
#: claims against a panel that does not. Widening the CI test until something
#: passed would have converted a measurement into a wish.
RULE_GENERATOR = murat_rule.CONTRACT["generator"]

#: Where the measured base rate is cached. Recomputing it walks the whole panel
#: (~37k symbol-days), which is too slow for a 09:15 seal.
PRIOR_CACHE = PANEL / "murat_rule_prior.json"

#: Fraction of the ranked universe that gets a directional claim. The rest are
#: recorded as CONSIDERED with no claim -- an empty book and a book that looked
#: at nothing must not print alike.
CLAIM_FRACTION = 0.10
#: Below this many scored names the cross-section is not a cross-section and the
#: book claims nothing, loudly.
MIN_UNIVERSE = 20


# --------------------------------------------------------------------- helpers


def _sha(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _panel_symbols() -> list[str]:
    return sorted(p.stem for p in PANEL.glob("*.jsonl") if not p.stem.startswith("bars_"))


def _bars(symbol: str) -> list[dict]:
    p = PANEL / f"bars_{symbol}.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("bars") or []
    except (OSError, ValueError):
        return []


def _last_closed_session(bars: dict[str, list[dict]]) -> str | None:
    """The newest bar date every benchmark agrees on."""
    days = [str((b[-1].get("t") or ""))[:10] for b in bars.values() if b]
    return max(days) if days else None


def _rank_pct(values: list[float]) -> list[float]:
    """Average-rank percentile in [0,1]. Ties share a rank, so a column that is
    mostly zeros -- which every event count is -- does not become an ordering of
    noise among the zeros."""
    n = len(values)
    if n < 2:
        return [0.5] * n
    order = sorted(range(n), key=lambda i: values[i])
    out = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            out[order[k]] = avg / (n - 1)
        i = j + 1
    return out


# ------------------------------------------------- generator 2: the rule's prior


def _spy_relative_forward(bars: dict[str, list[dict]], h: int) -> dict[str, dict[str, float]]:
    """{symbol: {day: SPY-relative return, next open -> close h sessions on}}.

    Entry at the NEXT open, never today's close: a feature computed from today's
    bar cannot trade today's close, because Alpaca refuses `cls` after 15:50 ET.
    """
    def fwd(bs: list[dict]) -> dict[str, float]:
        out: dict[str, float] = {}
        for i, b in enumerate(bs):
            if i + h >= len(bs):
                break
            o = float(bs[i + 1].get("o") or 0.0)
            c = float(bs[i + h].get("c") or 0.0)
            if o > 0 and c > 0:
                out[str(b.get("t") or "")[:10]] = c / o - 1.0
        return out

    bench = fwd(bars.get(BENCH) or [])
    out: dict[str, dict[str, float]] = {}
    for sym, bs in bars.items():
        if sym == BENCH or not bs:
            continue
        out[sym] = {d: r - bench[d] for d, r in fwd(bs).items() if d in bench}
    return out


def rule_prior(*, refresh: bool = False) -> dict:
    """The measured base rate behind every `p_up_21d` this generator publishes.

    Cached: walking 152 panel files is far too slow for a 09:15 seal, and the
    number only moves when the panel is rebuilt. `--refresh-prior` recomputes.
    """
    if PRIOR_CACHE.exists() and not refresh:
        try:
            return json.loads(PRIOR_CACHE.read_text(encoding="utf-8"))
        except ValueError:
            pass
    rows: dict[str, list[dict]] = {}
    for p in sorted(PANEL.glob("*.jsonl")):
        if p.stem.startswith("bars_"):
            continue
        rows[p.stem] = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    bars = {}
    for p in sorted(PANEL.glob("bars_*.json")):
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        bars[blob.get("symbol") or p.stem[5:]] = blob.get("bars") or []
    prior = murat_rule.prior_from_panel(rows, _spy_relative_forward(bars, HORIZON_SESSIONS))
    prior["computed_utc"] = datetime.now(timezone.utc).isoformat()
    prior["panel_symbols"] = len(rows)
    PRIOR_CACHE.parent.mkdir(parents=True, exist_ok=True)
    PRIOR_CACHE.write_text(json.dumps(prior, indent=1), encoding="utf-8")
    return prior


# ------------------------------------------------- ONE rule row, two producers

#: Every field `murat_rule.evaluate`, `murat_rule.score` and
#: `murat_rule.band_overlay` read off a rule row. Both producers must state all
#: of them -- as a value or as an explicit None.
#:
#: WHY THIS LIST EXISTS AT ALL (scenario lab L1-18, repaired 2026-09-02)
#: =====================================================================
#: Two functions in this file build a rule row: `tracker_rows()` for the whole
#: market, `build()` for the corpus panel. On 2026-09-01 a pre-seal replay found
#: that BAND-CONDITIONAL PRIOR v2 could not verify its own sub-$2 condition
#: without `close`, and the fix landed on ONE of the two. From then on v2 APPLIED
#: on every tracker name and was WITHHELD on every corpus name -- the two arms of
#: a live A/B were not running the same scorer, and nothing said so.
#:
#: The repair is not "add the field to the other function", which reopens the
#: moment somebody adds a third field. It is this: one builder, and it REFUSES a
#: producer that leaves a canonical field unstated. `coverage=None` written
#: deliberately is honest data-absence, which v2 already maps to WITHHELD; a
#: `coverage` key that was never in the dict is SCHEMA-absence wearing the same
#: answer, and the two must not print alike.
RULE_ROW_FIELDS: tuple[str, ...] = (
    "symbol",
    "target_ratio",              # clause (a), and the band prior's band
    "close",                     # the band prior's $2 condition
    "coverage",                  # the band prior's >= 2 analyst condition
    "coverage_source",           # WHICH analyst count -- the scales differ by 1.80x
    "rating_counts_mean",        # clause (b)
    "days_to_next_catalyst",     # clause (d)
    "drawdown_from_60d_high",    # clause (e)
    "realised_vol_20d",          # every magnitude the scorer publishes
)

#: The corpus arm has NO calibrated analyst count, and says so instead of
#: guessing. Its only available count is Finnhub's recommendation-panel total,
#: which ran a MEDIAN 1.80x yfinance's `numberOfAnalystOpinions` on a 56-name
#: stratified sample (`alpha/tracker.COVERAGE_SOURCE_CALIBRATED`) -- and
#: `BAND_PRIOR["min_coverage"] = 2` was measured on IBES `numrec`, which is the
#: quantity yfinance's field means. Reading the Finnhub count against that bar
#: is the error that had hack6 admitting 1-2-analyst names while believing it
#: had required four. `alpha/tracker.py` already states the rule: a book whose
#: rule names a bucket must REFUSE the wrong scale rather than read it. So the
#: corpus row carries an explicit None and the band prior WITHHOLDS -- for a
#: stated reason, on a field that is present.
CORPUS_COVERAGE_ABSENT = None


def rule_row(**fields) -> dict:
    """The canonical rule row. Both producers build through here, or neither does.

    Every name in `RULE_ROW_FIELDS` must be passed -- a None is a statement, a
    missing key is a bug -- and anything else passed rides along as the
    producer's own extras. Refusing loudly is the whole mechanism: a third
    producer, or a fourth canonical field, cannot reopen the split silently.
    """
    missing = [k for k in RULE_ROW_FIELDS if k not in fields]
    if missing:
        raise ValueError(
            f"rule_row REFUSES: {missing} unstated. Every field the rule and the band prior "
            f"read must be present on the row, as a value or as an explicit None -- a missing "
            f"key and a null read identically at the scorer and do not mean the same thing. "
            f"This is the L1-18 split: pass `{missing[0]}=None` if it is genuinely unavailable.")
    row = {k: fields.pop(k) for k in RULE_ROW_FIELDS}
    row.update(fields)
    return row


def rule_row_from_tracker(t: dict) -> dict:
    """The TRACKER producer's rule row: whole-market, one row per candidate."""
    up = t.get("upside")
    return rule_row(
        symbol=t["symbol"],
        # target_ratio is target/price; the tracker stores it as target/price - 1.
        target_ratio=(1.0 + up) if up is not None else None,
        # The band prior's $2 silence needs the price it is conditioned on.
        # Discovered in a pre-seal replay (2026-09-01): without this field
        # band_overlay could never verify the sub-$2 condition -- and a guard
        # that cannot read its input must refuse, not pass.
        close=t.get("close"),
        coverage=t.get("coverage"),
        coverage_source=t.get("coverage_source"),
        rating_counts_mean=t.get("consensus"),
        days_to_next_catalyst=t.get("days_to_catalyst"),
        drawdown_from_60d_high=t.get("drawdown_60d"),
        realised_vol_20d=t.get("realised_vol_20d"),
        # -- the tracker producer's own extras ------------------------------
        # Present so downstream shapes match, and NEVER scored: EVENT_COUNTS_V1
        # does not run on this universe (see `tracker_rows`).
        features={k: 0.0 for k in SIGNALS},
        score=None,
        n_items_20d=None,
        tracker_status=t.get("status"),
        coverage_bucket=t.get("coverage_bucket"),
        past_winner=t.get("past_winner"),
        sector=t.get("sector"),
        ret_12m=t.get("ret_12m"),
    )


def rule_row_from_features(symbol: str, f: dict, *, close: float | None) -> dict:
    """The CORPUS producer's rule row, from one `features.daily_features` row.

    `close` comes from `features.last_close` on the SAME bars and the SAME day
    that priced `target_ratio` -- not from a second expression, and not from a
    fresher quote. A ratio and the price it is a ratio TO must come from one
    reading or the band prior is banding a number nobody computed.
    """
    counts = f.get("event_type_counts_20d") or {}
    return rule_row(
        symbol=symbol,
        target_ratio=f.get("target_ratio"),
        close=close,
        # Stated, not omitted. See CORPUS_COVERAGE_ABSENT.
        coverage=CORPUS_COVERAGE_ABSENT,
        coverage_source=None,
        rating_counts_mean=f.get("rating_counts_mean"),
        days_to_next_catalyst=f.get("days_to_next_catalyst"),
        drawdown_from_60d_high=f.get("drawdown_from_60d_high"),
        realised_vol_20d=f.get("realised_vol_20d"),
        # -- the corpus producer's own extras -------------------------------
        features={k: float(counts.get(k.replace("ev_", "").replace("_20d", ""), 0) or 0)
                  for k in SIGNALS},
        score=None,                      # filled by the cross-sectional rank in `build`
        n_items_20d=f.get("n_items_20d"),
        # The Finnhub panel total when it was read, RECORDED AND NOT USED: it is
        # on the uncalibrated scale, so it cannot answer the band prior's
        # >= 2-analyst condition. Recorded so "we had a number and declined to
        # read it" is checkable rather than a claim.
        coverage_uncalibrated=f.get("rating_coverage"),
    )


def _ratings_for(symbols: list[str]) -> dict[str, dict]:
    """Same-day consensus ratings, fetched ONLY for names that already pass the
    price clauses.

    Finnhub allows 60 calls a minute and the panel is 152 names; asking for all
    of them would spend the budget to learn the rating of names the rule has
    already rejected on (a) or (e). A name whose rating cannot be read is not
    rejected -- it runs as `rule_variant: a_d_e` and says so.
    """
    out: dict[str, dict] = {}
    if config.test_mode() or not symbols:
        return out
    from alpha.sources import finnhub
    from alpha.sources.http import SourceRefusal
    for i, s in enumerate(symbols):
        if i:
            time.sleep(1.1)
        try:
            recs = finnhub.recommendation_trends(s)
        except SourceRefusal:
            continue
        if recs:
            out[s] = recs[0]
    return out


def rule_predictions(rows: list[dict], prior: dict, driver_of: dict[str, str]) -> list[dict]:
    """One row per name, ALWAYS with numbers. See `alpha/murat_rule.py`."""
    # Price clauses first, so ratings are fetched for a handful of names rather
    # than for the whole panel.
    pre = {r["symbol"]: murat_rule.evaluate(r) for r in rows}
    need_rating = [r["symbol"] for r in rows
                   if pre[r["symbol"]]["clauses"]["a_target_ratio"] is True
                   and pre[r["symbol"]]["clauses"]["e_drawdown"] is True
                   and r.get("rating_counts_mean") is None]
    ratings = _ratings_for(need_rating)

    out: list[dict] = []
    for r in rows:
        if r["symbol"] in ratings:
            got, _cov = features.rating_from_panel(ratings[r["symbol"]])
            # `_cov` is the Finnhub PANEL total, not an analyst count on the
            # scale the band prior was measured on (1.80x, n=56 stratified). It
            # is recorded and NOT written to `coverage`: a book whose rule names
            # a bucket refuses the wrong scale rather than reading it.
            r = {**r, "rating_counts_mean": got, "coverage_uncalibrated": _cov}
        v = murat_rule.evaluate(r)
        s = murat_rule.score(r, v, prior)
        out.append({
            "symbol": r["symbol"],
            "generator": RULE_GENERATOR,
            "claims": v["fires"],
            "direction": "up" if v["fires"] else None,
            "horizon_sessions": HORIZON_SESSIONS,
            "checkpoint_sessions": CHECKPOINT_SESSIONS,
            "driver": driver_of.get(r["symbol"]),
            "rule_variant": v["rule_variant"],
            "clauses": v["clauses"],
            "clause_inputs": v["inputs"],
            "failed_clauses": v["failed_clauses"],
            "unreadable_clauses": v["unreadable_clauses"],
            **s,
            "falsifier": (
                f"{r['symbol']} fails this claim if its SPY-relative return from the next open "
                f"to the close {HORIZON_SESSIONS} sessions later is <= 0." if v["fires"] else None),
            "which_book_acts": "hack3 (THESIS) as its own selector -- see scripts/fleet.py",
        })
    # Claiming rows first, then everything else by `exp_return - |downside|`.
    #
    # The second group's ordering is LEAST-BAD, not second-best, and it is
    # labelled as such on every row. With p_up below 0.5 for every non-firing
    # name, `exp_return` is negative for all of them, so the ordering among
    # them is driven almost entirely by volatility -- the calmest name sorts
    # highest. Printing that as "rank 2" beside a real claim at rank 1, with
    # nothing to distinguish them, is how a reader comes away believing the
    # book had fourteen ideas when it had one.
    out.sort(key=lambda p: (not p["claims"], -murat_rule.rank_key(p)))
    for i, p in enumerate(out):
        p["rank"] = i + 1
        p["rank_basis"] = ("CLAIMING, ranked by exp_return - |downside_5pct|" if p["claims"]
                           else "NOT CLAIMING: ranked least-bad by the same expression. This is "
                                "an ordering of names the rule declined, not a shortlist.")
    return out


# ------------------------------------------------------------------- the build


def tracker_rows(day: str | None = None, *, asof: str | None = None) -> tuple[list[dict], dict, list[dict]]:
    """Book rows built from the TRACKER instead of the corpus. (rows, provenance).

    WHY THE TRACKER AND NOT THE CORPUS
    ==================================
    The corpus path needs news to exist for a name before it can score it, and
    that requirement is itself a mega-cap filter: Benzinga files 1,566 items on
    NVDA and three or four on AARD. That is how the panel arrived at 151 names,
    nearly all large, and how the book came to claim one mega-cap that had
    already risen 700%.

    The tracker needs no news. Every input Murat's rule actually reads --
    target ratio, consensus rating, drawdown, days to catalyst -- is on the
    tracker row already, from sources that cover a four-analyst biotech as
    readily as they cover Apple. So the rule runs on the whole market here.

    EVENT_COUNTS_V1 DOES NOT RUN ON THIS UNIVERSE, deliberately. Its inputs are
    corpus event counts, which most tracker names do not have; scoring them as
    zero would silently convert "no coverage" into "no events", which is the
    exact collapse `net_breadth` was fixed to avoid. A generator with no inputs
    reports that it did not run. It does not report a zero.
    """
    from scripts import tracker as tracker_cli

    day = day or tracker_cli.latest_day()
    if not day:
        raise SystemExit("REFUSED: no tracker day on disk. Run `python -m scripts.tracker "
                         "--refresh` first -- the book cannot select from a list that does "
                         "not exist.")
    raw = tracker_cli.load_day(day)
    if not raw:
        raise SystemExit(f"REFUSED: tracker file for {day} is empty.")
    # AGE. `latest_day()` returns the newest file on disk however old it is, so
    # without this a dead refresh seals Monday's book on Friday's closes and
    # says nothing. Counted in sessions: Monday on Sunday's file is age 1.
    try:
        # `asof` is for a declared REPLAY only (scripts/monday_dry_run.py): it
        # asks "was this vintage fresh ON ITS OWN DAY", which is the right
        # question for a replay and the WRONG one for a live seal. A live
        # seal passes nothing and is measured against today, unchanged.
        fresh = _tracker.assert_fresh(day, asof=asof,
                                      what=f"tracker file {day} (the seal's price source)")
    except _tracker.StaleTrackerData as exc:
        raise SystemExit(str(exc)) from exc
    trows = _tracker.build_rows(raw)
    prev_day = tracker_cli.latest_day(before=day)
    prev = {r["symbol"]: r for r in tracker_cli.load_day(prev_day)} if prev_day else {}
    hist = _tracker.apply_status(trows, prev_by_symbol=prev)
    cands = _tracker.candidates(trows)

    # ONE builder, both producers (`rule_row_from_tracker` -> `rule_row`). The
    # mapping used to live inline here and the corpus arm had its own copy; that
    # is how `close` reached one producer of two and BAND_PRIOR v2 ran on one arm
    # of a live A/B. See RULE_ROW_FIELDS.
    rows = [rule_row_from_tracker(t) for t in cands]
    prov = {
        "source": "tracker", "tracker_day": day, "previous_day": prev_day,
        "tracker_freshness": fresh,
        "tracker_names_total": len(trows), "tracker_status_histogram": hist,
        "candidates_ranked": len(rows),
        # ABSENT vs REFUSED, distinguishable inside the artifact (2026-08-31,
        # after a Finnhub 503 storm left 75 observed-but-consensus-unreadable
        # rows). A row that could not be read is a recorded refusal on the day
        # file; this count surfaces it in the seal so a reader does not have to
        # diff the universe to discover a data gap -- the daily_autopsy
        # rate-limit lesson (a SourceRefusal that prints as a confident zero).
        "data_gaps": {
            "rows_rec_status_not_ok": sum(1 for r in raw if r.get("rec_status") != "ok"),
            "rows_target_status_not_ok": sum(1 for r in raw if r.get("target_status") != "ok"),
            "note": ("observed names whose vendor reading failed STAY in the day file with "
                     "the failure on the row; they are blocked from candidacy with a reason, "
                     "never silently absent"),
        },
        "clause_f_not_past_winner": (
            "NOT APPLIED TO THIS BOOK, AND THAT IS DELIBERATE. Until 2026-08-30 (e) the tracker "
            "status itself required `past_winner is False`, so the sealed book inherited clause "
            "(f) from its universe. It no longer does: the exclusion measured NEGATIVE on eleven "
            "years of IBES (-2.9pp/yr; the excluded names were the strongest sub-basket in the "
            "study at +18.60%/yr, t 3.31) and it is now a PER-BOOK preference -- ON for hack3, "
            "OFF for hack4 and hack6 -- so that both arms run and the paper books settle it. "
            "A prediction book PREDICTS; it does not hold. Sealing past winners too costs "
            "nothing and buys the one thing that decides the question: graded forecasts on the "
            "names the exclusion would have thrown away. `past_winner` and `past_winner_basis` "
            "are on every prediction row, so the book can be graded either way after the fact. "
            "`murat_rule_v1`'s frozen contract is untouched -- this is a change of UNIVERSE, "
            "never an amendment to the rule."),
        "event_counts_v1": (
            "DID NOT RUN on this universe. Its inputs are corpus event counts and most tracker "
            "names carry no corpus rows; scoring those as zero would read 'not covered' as "
            "'no events happened'. A generator with no inputs says so."),
    }
    # `cands` is returned ALONGSIDE the reshaped rows, not instead of them. The
    # reshaped row is what the rule reads (`target_ratio`, `days_to_next_catalyst`);
    # the tracker row is what the PERSONALITIES read (`upside`, `median_dollar_volume`,
    # `coverage_source`, `status`). Handing `rows` to `build_portfolio` returns an
    # empty book in silence, because every filter reads a key that is not there --
    # which is why the two shapes are now returned together and named apart.
    return rows, prov, cands


def _source_versions() -> dict:
    """Which code sealed this book (§1a, brief g). AAT_BUILD_COMMIT first, for
    the same reason as `agent_loop._commit`: in the deployed container `.git`
    is not shipped and `git rev-parse` has always failed there. A dirty tree is
    stamped `+dirty` -- a seal from uncommitted code should say so."""
    import subprocess
    commit = os.getenv("AAT_BUILD_COMMIT", "").strip() or None
    if not commit:
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(ROOT), text=True, timeout=10).strip()
            if subprocess.check_output(["git", "status", "--porcelain"],
                                       cwd=str(ROOT), text=True, timeout=10).strip():
                commit += "+dirty"
        except (OSError, subprocess.SubprocessError):
            commit = None
    return {
        "code_commit": commit,
        "seal_script": "scripts/prediction_book.py",
        "portfolio_module": "alpha.tracker",
        "selector_brain": "alpha.brains.tracker_portfolio",
        "rule_generator": RULE_GENERATOR,
        "rule_registered": murat_rule.CONTRACT["registered"],
        # WHICH BAND MODE PRODUCED THIS BOOK. Inside content_sha256, because
        # the mode decides whether `exp_return` is an eleven-year band constant,
        # a panel base rate, or nothing -- and a seal that does not say which
        # cannot be graded against the next one.
        "band_mode": murat_rule.band_mode(),
    }


#: E1 -- PRICE THE DISSENT (retro 2026-09-02 §5, motivated by §2 Miss #1).
#:
#: RZLV lost -17.30% on 2026-09-01 at 10% of hack4 while its own row in the very
#: same sealed file read `claims: false`, `rank: 576` of 766, failing `b_rating`
#: by 0.017. On the 09-02 seal the disagreement is the NORM, not the edge case:
#: 25 of 30 hack3+hack6 holdings are names `murat_rule_v1` explicitly declined.
#: The selector ranks on `upside_x_consensus`; the generator answers a different
#: question; nobody was writing down that they disagreed.
#:
#: This is a JOIN, NOT A GATE. Both numbers were already in the same JSON --
#: `predictions[]` carried the verdict, `portfolios[book]["holdings"][]` carried
#: the weight, and no key tied them together. Stamping the verdict onto the
#: holding at seal time costs one dict merge, changes NOTHING about selection
#: (it runs strictly after `build_portfolio` has returned), and makes the four
#: populations -- held+claimed, held+declined, and their unheld complements --
#: fall out of `state/decision_outcomes/` automatically as grades mature.
#:
#: `34f08ca` decided deliberately that the runner expresses a sealed weight and
#: does not re-adjudicate it; dissent is RECORDED, not enforced. This stamp is
#: the recording. Promoting it to a size haircut needs 21 sessions and the
#: pre-registered decision rule in the retro, and is not licensed here.
DISSENT_UNKNOWN = (
    "NO VERDICT: the generator produced no row for this symbol in this seal, so "
    "`generator_claimed` is UNKNOWN and not False. A held name whose verdict was "
    "never computed is a different fact from one the rule declined, and collapsing "
    "the two would put un-adjudicated names into the `dissent` population.")


def generator_stamp(pred: dict | None) -> dict:
    """The generator's verdict on ONE symbol, as sealed onto its holding.

    `pred` is the `murat_rule_v1` prediction row for the symbol, or None when
    the generator never scored it. Pure, and never raises: a stamp that could
    fail would take the whole seal down for a bookkeeping field.

    `generator_score` is the generator's OWN ranking expression
    (`exp_return - |downside_5pct|`, `murat_rule.rank_key`) -- the number the
    rule sorts on, so a reader can see how far down the generator's own order
    the selector reached. `rank_key` returns -inf for a row missing either
    input; that is recorded as None rather than as `-Infinity`, which is not
    JSON and would break every strict reader of a sealed book.
    """
    if not pred:
        return {"generator": RULE_GENERATOR, "generator_claimed": None,
                "generator_score": None, "generator_rank": None,
                "generator_failed_clauses": None, "dissent": None,
                "dissent_basis": DISSENT_UNKNOWN}
    claimed = bool(pred.get("claims"))
    key = murat_rule.rank_key(pred)
    return {
        "generator": pred.get("generator") or RULE_GENERATOR,
        "generator_claimed": claimed,
        "generator_score": round(key, 6) if math.isfinite(key) else None,
        "generator_rank": pred.get("rank"),
        "generator_failed_clauses": list(pred.get("failed_clauses") or []),
        # SELECTED BUT NOT CLAIMED. Recorded, never enforced -- see above.
        "dissent": not claimed,
        "dissent_basis": (
            "the generator CLAIMED this name and the selector held it: agreement"
            if claimed else
            "DISSENT: held by the book's selector, declined by murat_rule_v1"
            + (f" on {', '.join(pred.get('failed_clauses') or []) or 'no failed clause'}"
               f" (rank {pred.get('rank')})")),
    }


def _equity_basis(book: str) -> tuple[float, str]:
    """The dollars a risk budget is expressed against, and where that came from.

    The seal is equity-agnostic by design -- weights are fractions -- but a
    contract's `risk_budget_usd` has to be a number of dollars or it cannot be
    compared with an expected edge in dollars, which is the whole point of the
    2026-09-05 guard. The genesis file is the right basis: it is the frozen
    starting equity of THIS role, it is already tamper-evident, and it does not
    move under the book while the book is being graded.
    """
    from pathlib import Path

    for path in (Path(f"state/genesis_{book}.json"), ROOT / "state" / f"genesis_{book}.json"):
        try:
            eq = float(json.loads(path.read_text(encoding="utf-8")).get("starting_equity") or 0.0)
        except (OSError, ValueError, AttributeError):
            continue
        if eq > 0:
            return eq, f"genesis_{book}.json starting_equity"
    eq = float(config.COMPETITION["required_starting_equity"])
    return eq, ("NO genesis file for this role: fell back to the declared starting equity "
                f"{eq:,.0f}. The budget is a RATIO of that, so a book whose real equity has "
                "drifted carries a proportionally wrong dollar figure -- stated, not hidden.")


def _contract_block(p, port: dict, wc: dict, *, day: str) -> dict:
    """The strategy contract this book seals for today (`alpha/contract.py`).

    WHY IT IS IN THE SEAL AND NOT IN A SIDE FILE
    ============================================
    Because it must be inside `content_sha256`. A contract that can be edited
    after the book traded grades nothing -- the same argument that put the
    holdings here. `alpha/exits.py` reads it back off the ENTRY LEDGER ROW, so
    the terms that govern a live position are the terms that were sealed when
    it opened, and a re-seal cannot re-write the deal on a position already on.
    """
    equity_basis, basis_note = _equity_basis(p.book)
    stop = float(wc.get("stop_fraction") or 0.0) if wc.get("determinable") else 0.0
    per_name = float(port.get("max_notional_each") or 0.0)
    k = contract_mod.for_book(
        p.book, day=day,
        risk_budget_usd=max(0.01, per_name * stop * equity_basis),
        profile=wc.get("profile"))
    out = k.as_dict()
    out["risk_budget_frac_of_equity"] = round(per_name * stop, 6)
    out["risk_budget_basis"] = basis_note
    out["equity_basis_usd"] = equity_basis
    out["stop_fraction"] = stop or None
    return out


def _portfolio_block(port: dict, p, driver_of: dict[str, str],
                     verdicts: dict[str, dict] | None = None,
                     day: str | None = None) -> dict:
    """One book's sealed block from an already-built portfolio (§1a, brief g).

    Three derived fields beyond the holdings, so the seal answers "is this one
    hidden bet?" and "what is the dollar bound?" by itself:

    - `driver_exposure`: Σ|notional| per causal driver, via `drivers`. Twelve
      sectors that are one driver show up here as one number.
    - `derived_gross`: Σ|notional| actually selected -- the gross this book
      REQUESTS, before any runner cap.
    - `worst_case`: from `alpha.tracker.worst_case` with the cap and stop read
      from the modules that ENFORCE them (`scripts.tracker._limits_for`), the
      binding constraint named. When the limits cannot be read the block says
      `determinable: False` WITH THE REASON, never a silently absent bound --
      a guard derives its inputs or refuses (CLAUDE.md, monday_gate lesson).
    """
    verdicts = verdicts or {}
    holdings = [{"symbol": h["symbol"], "notional": h["notional"],
                 "sector": h["sector"], "rank_value": h["rank_value"],
                 "exp_return": h["exp_return"],
                 "exp_return_validation": h.get("exp_return_validation"),
                 "downside_5pct": h["downside_5pct"],
                 "confidence": h["confidence"],
                 "numbers_source": h["numbers_source"],
                 # E1: the generator's verdict, joined at seal time. Stamped
                 # AFTER `build_portfolio` returned, so it cannot influence
                 # which names are here or at what weight.
                 **generator_stamp(verdicts.get(h["symbol"]))}
                for h in port["holdings"]]
    derived_gross = round(sum(abs(float(h["notional"] or 0.0)) for h in holdings), 4)
    try:
        from scripts.tracker import _limits_for
        gross_cap, stop, profile = _limits_for(p.book)
        wc = _tracker.worst_case(n=port["n_selected"], notional_each=p.max_notional,
                                 stop_fraction=stop, gross_cap=gross_cap)
        wc["profile"] = profile
        wc["determinable"] = True
    except (Exception, SystemExit) as exc:  # _limits_for REFUSES via SystemExit
        wc = {"determinable": False, "reason": f"{type(exc).__name__}: {exc}"}
    # THE CONTRACT, and then the same fields ON EVERY HOLDING (2026-09-05).
    #
    # Duplicated deliberately. `exits.py` judges ONE position at a time and gets
    # its contract from that position's own entry row; a reader auditing why a
    # name was held for eleven sessions should not have to join back to a block
    # header to find out what it promised. The stamp is a copy of the block's
    # contract, written after `build_portfolio` returned, and it cannot change
    # which names are here or at what weight.
    contract = _contract_block(p, port, wc, day=day or _exits.session_day())
    _stamp = {k: contract[k] for k in contract_mod.REQUIRED_FIELDS}
    for h in holdings:
        h.update(_stamp)
    return {
        "book": p.book, "personality": p.name, "ranking": p.rank,
        "contract": contract,
        "k_target": port["k_target"], "n_selected": port["n_selected"],
        "max_notional_each": port["max_notional_each"],
        "rank_distinct_values": port["rank_distinct_values"],
        "ranking_is_degenerate": port["ranking_is_degenerate"],
        "constraints": {
            "exclude_past_winners": port["exclude_past_winners"],
            "requires_catalyst": port["requires_catalyst"],
            "min_coverage_bucket": port["min_coverage_bucket"],
            "max_coverage_bucket": port["max_coverage_bucket"],
            "min_dollar_volume": port["min_dollar_volume"],
            "max_sector_share": port["max_sector_share"],
            "max_names_per_sector": port["max_names_per_sector"],
            "max_downside": port["max_downside"],
        },
        # The ONLY thing the runner is allowed to act on. Symbol and weight,
        # decided before the open, frozen by the hash.
        "holdings": holdings,
        "candidate_pool": port["candidate_pool"], "eligible": port["eligible"],
        "excluded_by_reason": port["excluded_by_reason"],
        "sector_notional": port["sector_notional"],
        "driver_exposure": {d: round(v, 4) for d, v in sorted(
            drivers.notional_by_driver(
                {h["symbol"]: float(h["notional"] or 0.0) for h in holdings},
                driver_of).items())},
        "derived_gross": derived_gross,
        "worst_case": wc,
        # E1's census for THIS book, so "how much of what we hold does our own
        # generator decline?" is one field rather than a join a reader has to
        # write. `unknown` is its own bucket and is never folded into either
        # side -- see DISSENT_UNKNOWN.
        "generator_dissent": {
            "held": len(holdings),
            "claimed": sum(1 for h in holdings if h["generator_claimed"] is True),
            "declined": sum(1 for h in holdings if h["generator_claimed"] is False),
            "unknown": sum(1 for h in holdings if h["generator_claimed"] is None),
            "note": ("RECORDED, NOT ENFORCED (34f08ca): the runner expresses a sealed "
                     "weight and does not re-adjudicate the seal. E1 accrues "
                     "held+claimed vs held+declined forward; promotion to a size "
                     "haircut needs 21 sessions and the pre-registered rule."),
        },
    }


def _build_from_tracker(*, now: datetime, seal_utc: str, day: str) -> dict:
    """The sealed book over the tracker's candidate list. One generator, all numbers."""
    rows, prov, cands = tracker_rows()
    prior = rule_prior()
    driver_of, driver_note = drivers.resolve([r["symbol"] for r in rows])
    predictions = rule_predictions(rows, prior, driver_of)
    rule_claims = sum(1 for p in predictions if p["claims"])

    # The personalities rank on the RULE's numbers, so they have to be carried
    # back onto the tracker rows before the books are built -- exactly what
    # `scripts/tracker.py --portfolios` does via `merge_book_numbers`. Without
    # this the ratio rankings see None and every name ranks -inf, which is an
    # empty book that took the same code path as a full one.
    _pred_by_symbol = {p["symbol"]: p for p in predictions}
    for _c in cands:
        _p = _pred_by_symbol.get(_c["symbol"])
        if not _p:
            continue
        for _k in ("exp_return", "downside_5pct", "confidence", "p_up_21d"):
            _c[_k] = _p.get(_k)
        _c["numbers_source"] = "rule"

    # Carry the tracker's own columns onto every prediction so a reader can see
    # WHICH universe rule the name passed as well as which clause the rule read.
    by_sym = {r["symbol"]: r for r in rows}
    for p in predictions:
        t = by_sym.get(p["symbol"]) or {}
        p["tracker"] = {k: t.get(k) for k in
                        ("tracker_status", "coverage", "coverage_bucket",
                         "past_winner", "sector", "ret_12m")}

    # Murat's thin-coverage hypothesis, kept as a QUESTION. The book does not
    # prefer thin names and does not avoid them; it records how the claims fell
    # across coverage so the answer can be measured forward instead of assumed.
    claims_by_coverage: dict[str, dict[str, int]] = {}
    for p in predictions:
        b = (p.get("tracker") or {}).get("coverage_bucket") or "none"
        d = claims_by_coverage.setdefault(b, {"ranked": 0, "claimed": 0})
        d["ranked"] += 1
        d["claimed"] += 1 if p["claims"] else 0

    # THE ARTERY (2026-08-31). Until now the seal carried per-name CLAIMS and
    # nothing else, so `murat_rule` traded claimers -- never hack3/hack4/hack6.
    # The personalities, their rankings, sector caps, coverage bands, liquidity
    # floors and downside limits lived only in a PRINT. Sealing the exact
    # holdings and weights here puts them inside `content_sha256`, which is what
    # makes "the runner traded what I inspected" a checkable statement instead
    # of a hope. Nothing acts on this block unless an account enables the
    # `tracker_portfolio` brain; sealing is not enabling.
    portfolios = {}
    for p in _tracker.PERSONALITIES:
        portfolios[p.book] = _portfolio_block(_tracker.build_portfolio(cands, p),
                                              p, driver_of, _pred_by_symbol, day=day)

    payload = {
        "schema": "prediction-book-3",
        "day": day,
        "sealed_at_utc": seal_utc,
        "generator": RULE_GENERATOR,
        "generators": [RULE_GENERATOR],
        "portfolios": portfolios,
        "portfolios_note": (
            "EXACT holdings and weights per book, sealed inside content_sha256. "
            "The `tracker_portfolio` brain reads THIS and nothing else -- it does "
            "not re-rank, and a tracker refresh after the seal cannot change what "
            "trades today. A book listed here is not thereby live: it trades only "
            "on an account whose AAT_LOOP_BRAINS contains `tracker_portfolio`."),
        "universe_source": prov,
        "source_versions": _source_versions(),
        "murat_rule_contract": murat_rule.CONTRACT,
        "murat_rule_prior": prior,
        "claims_by_generator": {RULE_GENERATOR: rule_claims},
        "claims_by_coverage_bucket": claims_by_coverage,
        "rule_variant_histogram": murat_rule.variant_histogram(predictions),
        "pit": {
            "tracker_observed_at": prov["tracker_day"],
            "note": ("every tracker row carries its own `observed_at` capture stamp and is used "
                     "strictly after it. The analyst target has NO vendor vintage -- we know when "
                     "WE read it, which is the bound a live decision needs and is NOT a bound a "
                     "backtest may use. See `alpha/tracker.py`."),
        },
        "universe_considered": len(rows),
        "claims_made": rule_claims,
        "skipped": {},
        "driver_taxonomy": driver_note,
        "authority": (
            "NOT SELF-EXECUTING. This file sizes and orders NOTHING by itself. It becomes "
            "tradable only on an account whose AAT_LOOP_BRAINS names an enabled selector -- "
            "`murat_rule` for per-name claims, `tracker_portfolio` for `portfolios[book]` -- "
            "and admission may CUT what a selector takes from it, never raise it. The old "
            "text ('nothing may influence an order') was false the moment a selector brain "
            "was built to consume this artifact; an artifact must not deny the authority "
            "an enabled brain explicitly exercises over it."),
        "claiming": True,
        "evidence_caveat": (
            "THE BASE RATE IS TRANSFERRED, NOT MEASURED HERE. `p_up` on every row below comes "
            "from `murat_rule_prior`, measured on the 152-name corpus panel over 11 date blocks. "
            "It is applied to a universe of several thousand names that panel did not contain, "
            "and the tracker is one day old so it cannot yet produce a base rate of its own -- a "
            "forward rate needs forward returns and there are none. Two consequences, both "
            "stated rather than buried: the ranking here is sound (it is an ordering by the "
            "rule's own inputs), and the LEVEL of p_up is an extrapolation whose error is "
            "unmeasured. The honest resolution is the out-of-sample test of these same status "
            "rules on IBES + CRSP 2013-2024, which measures the rate on the whole market over "
            "eleven years instead of on 152 names over eleven blocks."),
        "universe_note": (
            f"selected from the tracker's {prov['candidates_ranked']} candidates out of "
            f"{prov['tracker_names_total']} names screened -- not from the 151-name corpus panel. "
            f"{prov['clause_f_not_past_winner']}"),
        "predictions": predictions,
    }
    payload["content_sha256"] = _sha(payload)
    return payload


def build(*, now: datetime | None = None, universe: list[str] | None = None,
          source: str = "corpus") -> dict:
    """Today's sealed book, as a dict. Pure over the corpus and the panel."""
    now = now or datetime.now(timezone.utc)
    seal_utc = now.isoformat()
    day = _exits.session_day(now)

    if source == "tracker":
        return _build_from_tracker(now=now, seal_utc=seal_utc, day=day)

    syms = sorted(set(universe or _panel_symbols()))
    bars = {s: _bars(s) for s in syms}
    bench_bars = bars.get(BENCH) or _bars(BENCH)
    as_of_bar = _last_closed_session({BENCH: bench_bars} if bench_bars else bars)

    rows: list[dict] = []
    skipped: dict[str, int] = {}
    for sym in syms:
        if sym == BENCH:
            continue
        # PIT TWICE: corpus rows cut at the seal INSTANT, price context at the
        # last closed session. `daily_features` applies its own day bound on top.
        crows = [r for r in corpus.read(symbols=[sym]) if str(r.get("observed_at") or "") <= seal_utc]
        if not crows:
            skipped["no_corpus_rows"] = skipped.get("no_corpus_rows", 0) + 1
            continue
        if not bars.get(sym):
            skipped["no_bars"] = skipped.get("no_bars", 0) + 1
            continue
        # `future_known_by=seal_utc` is what makes clause (d) readable at all.
        # The price context is the last CLOSED session (the free SIP plan
        # refuses newer bars), but the forward catalyst calendar is pulled
        # today -- so one shared bound filtered every catalyst out and
        # `days_to_next_catalyst` was None for every name in the book. See
        # `features.daily_features` for why two clocks need two bounds.
        f_day = as_of_bar or day
        f = features.daily_features(sym, f_day, crows, bars=bars.get(sym),
                                    future_known_by=seal_utc)
        # ONE builder, both producers. `close` is read off the SAME bars and the
        # SAME day `daily_features` priced `target_ratio` against, so the band
        # prior bands a ratio and a price that were read together.
        rows.append(rule_row_from_features(
            sym, f, close=features.last_close(bars.get(sym), f_day)))

    # Cross-sectional score. Ranked per feature, then IC-weighted.
    universe_note = ""
    if len(rows) >= MIN_UNIVERSE:
        total_w = sum(w for w, _ in SIGNALS.values())
        ranked = {k: _rank_pct([r["features"][k] for r in rows]) for k in SIGNALS}
        for i, r in enumerate(rows):
            r["score"] = sum(SIGNALS[k][0] * ranked[k][i] for k in SIGNALS) / total_w
    else:
        universe_note = (f"{len(rows)} scored names is below MIN_UNIVERSE={MIN_UNIVERSE}: a "
                         "cross-sectional rank over a handful of names is an ordering of noise. "
                         "NO CLAIMS MADE.")
        for r in rows:
            r["score"] = None

    rows.sort(key=lambda r: (-(r["score"] or -1), r["symbol"]))
    if not CLAIMING:
        # SCOPED TO THIS GENERATOR. Before `murat_rule_v1` existed this sentence
        # described the whole book and was true of it. Left unscoped it now
        # contradicts the file it is written into -- a book that claims MU while
        # its own header says it "asserts nothing" teaches a reader to stop
        # believing the header.
        universe_note = (universe_note + " " if universe_note else "") + (
            "event_counts_v1 CLAIMS NOTHING: on the 152-symbol panel not one of the 29 "
            "features has a 95% CI excluding zero (ic_2026-08-30_wide152.json). Its ranking "
            "is still computed and still sealed -- it is the control, and it accrues the "
            "vintages -- but it asserts nothing until a signal clears zero on a universe "
            "nobody curated. This says NOTHING about murat_rule_v1, which is a separate "
            "generator with its own contract and its own claims; see claims_by_generator.")
    n_claim = int(len(rows) * CLAIM_FRACTION) if (not universe_note and CLAIMING) else 0
    driver_of, driver_note = drivers.resolve([r["symbol"] for r in rows])

    predictions = []
    for i, r in enumerate(rows):
        claims = i < n_claim
        vol = r.get("realised_vol_20d")
        # Expected magnitude is the name's OWN realised vol scaled to the horizon,
        # not a number we chose. It is a scale, not a forecast: the claim is the
        # DIRECTION, and the magnitude says how big a move would be ordinary.
        mag = (float(vol) * math.sqrt(HORIZON_SESSIONS / 252.0)) if vol else None
        predictions.append({
            "symbol": r["symbol"],
            "claims": claims,
            "direction": "up" if claims else None,
            "expected_abs_move_21d": round(mag, 4) if mag else None,
            "magnitude_basis": "the name's own realised_vol_20d scaled by sqrt(21/252)",
            "horizon_sessions": HORIZON_SESSIONS,
            "checkpoint_sessions": CHECKPOINT_SESSIONS,
            "score": round(r["score"], 5) if r["score"] is not None else None,
            "rank": i + 1,
            "driver": driver_of.get(r["symbol"]),
            "features": r["features"],
            "p_priced": None,
            "p_priced_note": ("not computed: this book does not read an options chain. What the "
                              "market already prices is the runner's question at order time, and "
                              "asserting it here without a chain would be a number nobody measured."),
            "falsifier": (
                f"{r['symbol']} fails this claim if its SPY-relative return from the next open to "
                f"the close {HORIZON_SESSIONS} sessions later is <= 0."
                if claims else None),
            "generator": "event_counts_v1",
            "which_book_acts": "NONE -- zero size; T7 prediction book only",
        })

    # SECOND GENERATOR. It runs over the same rows and writes into the same
    # sealed book, each row stamped with its own `generator`, so the two are
    # graded separately and Friday can compare a rule that claims with a panel
    # that does not.
    prior = rule_prior()
    rule_rows = rule_predictions(rows, prior, driver_of)
    rule_claims = sum(1 for p in rule_rows if p["claims"])
    predictions += rule_rows

    payload = {
        "schema": "prediction-book-2",
        "day": day,
        "sealed_at_utc": seal_utc,
        "generator": "event_counts_v1",
        "generators": ["event_counts_v1", RULE_GENERATOR],
        "murat_rule_contract": murat_rule.CONTRACT,
        "murat_rule_prior": prior,
        "claims_by_generator": {"event_counts_v1": n_claim, RULE_GENERATOR: rule_claims},
        "rule_variant_histogram": murat_rule.variant_histogram(rule_rows),
        "signals": {k: {"weight_ic": w, "ci95": list(ci)} for k, (w, ci) in SIGNALS.items()},
        "ic_receipt": IC_RECEIPT,
        "pit": {
            "corpus_rows_observed_at_max": seal_utc,
            "price_context_through": as_of_bar,
            "note": ("corpus cut at the seal INSTANT so a later rebuild cannot see a headline the "
                     "book could not; bars cut at the last CLOSED session, because the free SIP "
                     "plan refuses recent data and a signal needing today's close could not have "
                     "traded today's open"),
        },
        "universe_considered": len(rows),
        "claims_made": n_claim + rule_claims,
        "claim_fraction": CLAIM_FRACTION,
        "skipped": skipped,
        "driver_taxonomy": driver_note,
        "authority": (
            "NOT SELF-EXECUTING. This file sizes and orders NOTHING by itself. It becomes "
            "tradable only on an account whose AAT_LOOP_BRAINS names an enabled selector -- "
            "`murat_rule` for per-name claims, `tracker_portfolio` for `portfolios[book]` -- "
            "and admission may CUT what a selector takes from it, never raise it. The old "
            "text ('nothing may influence an order') was false the moment a selector brain "
            "was built to consume this artifact; an artifact must not deny the authority "
            "an enabled brain explicitly exercises over it."),
        "claiming": CLAIMING,
        "evidence_caveat": (
            "Measured on 152 symbols over 11 date blocks: ZERO of 29 features have a 95% CI "
            "excluding zero. The stronger numbers this book was first built on came from a "
            "23-symbol panel of hand-picked names; re-running those 23 from the wide build "
            "reproduces them, so the collapse is the universe, not the harness. The "
            "blinded-narrative tournament was separately NEGATIVE (hit 45% vs a 47% null, "
            "IC -0.18), which is why no model prose enters this book either."),
        "universe_note": universe_note,
        "predictions": predictions,
    }
    payload["content_sha256"] = _sha(payload)
    return payload


def check_contracts(book: dict) -> list[str]:
    """Every contract problem in this book, as prose. Empty list = sealable.

    A BOOK WITHOUT A CONTRACT MAY NOT BE SEALED (2026-09-05)
    =======================================================
    The `PRODUCT_EXPERIMENT` licence drops the significance gate, the MDE and
    the preregistration. What it does not drop is a frozen strategy contract
    BEFORE the first decision. Until tonight that was true of the two accounts
    `scripts/contract.py` froze by hand and of nothing else: the tracker books
    sealed holdings with no declared horizon, no minimum hold and no risk
    budget, and `exits.py` filled the gap with a -3%/+2.5% rule nobody chose.

    Checked here, at the seal, because that is the last moment before the book
    becomes tradable and the first moment every number exists.
    """
    bad: list[str] = []
    for name, port in sorted((book.get("portfolios") or {}).items()):
        bad += contract_mod.validate(port.get("contract"), where=f"portfolios[{name}].contract")
        missing = [h.get("symbol") for h in (port.get("holdings") or [])
                   if any(h.get(f) is None for f in contract_mod.REQUIRED_FIELDS)]
        if missing:
            bad.append(f"portfolios[{name}]: {len(missing)} holding(s) carry no contract stamp "
                       f"({', '.join(str(s) for s in missing[:5])}"
                       f"{'...' if len(missing) > 5 else ''}).")
    return bad


def seal(book: dict) -> Path:
    bad = check_contracts(book)
    if bad:
        raise contract_mod.ContractRefusal(
            "REFUSING TO SEAL: this book's portfolios do not carry a usable strategy contract, "
            "and a book that trades without one has no declared horizon, no minimum hold and no "
            "risk budget -- which is how 60% of the fleet's round trips finished in the session "
            "they opened. Problems:\n  - " + "\n  - ".join(bad))
    BOOKS.mkdir(parents=True, exist_ok=True)
    path = BOOKS / f"{book['day']}.json"
    if path.exists():
        prior = json.loads(path.read_text(encoding="utf-8"))
        if prior.get("content_sha256") != book.get("content_sha256"):
            # RESEALING IS NOT SILENT. The new book is written beside the old one
            # and both hashes go to the append-only log; the original file is not
            # touched. A book that can be quietly replaced grades nothing.
            alt = BOOKS / f"{book['day']}.resealed_{book['sealed_at_utc'][11:19].replace(':', '')}.json"
            alt.write_text(json.dumps(book, indent=1, ensure_ascii=False), encoding="utf-8")
            _append_seal(book, path=alt, note=f"RESEAL: {path.name} already sealed with a different hash")
            return alt
        return path
    path.write_text(json.dumps(book, indent=1, ensure_ascii=False), encoding="utf-8")
    _append_seal(book, path=path)
    return path


def _append_seal(book: dict, *, path: Path, note: str = "") -> None:
    SEALS.parent.mkdir(parents=True, exist_ok=True)
    with SEALS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"day": book["day"], "sealed_at_utc": book["sealed_at_utc"],
                             "file": path.name, "content_sha256": book["content_sha256"],
                             "claims": book["claims_made"], "considered": book["universe_considered"],
                             "note": note}) + "\n")


def verify() -> int:
    """Re-hash every sealed book. A book whose content no longer matches its own
    hash has been edited since sealing, and that is the one thing this file
    exists to make visible."""
    bad = 0
    for p in sorted(BOOKS.glob("*.json")):
        book = json.loads(p.read_text(encoding="utf-8"))
        claimed = book.pop("content_sha256", None)
        actual = _sha(book)
        ok = claimed == actual
        print(f"  {'ok ' if ok else 'TAMPERED'} {p.name}  {str(claimed)[:16]}"
              + ("" if ok else f" != {actual[:16]}"))
        bad += 0 if ok else 1
    if not bad:
        print("  every sealed book matches its own hash")
    return bad


# ---------------------------------------------------------------------- grading


def _sessions_after(bars: list[dict], day: str, n: int) -> tuple[float | None, str]:
    """Return from the OPEN of the session after `day` to the CLOSE n sessions on."""
    idx = [i for i, b in enumerate(bars) if str(b.get("t") or "")[:10] > day]
    if not idx:
        return None, "no session after the sealed day yet"
    start = idx[0]
    end = start + n - 1
    if end >= len(bars):
        return None, f"only {len(bars) - start} of {n} sessions elapsed"
    o = float(bars[start].get("o") or 0.0)
    c = float(bars[end].get("c") or 0.0)
    if o <= 0 or c <= 0:
        return None, "bar missing open or close"
    return c / o - 1.0, ""


def grade(day: str, *, horizon: int = HORIZON_SESSIONS) -> dict:
    path = BOOKS / f"{day}.json"
    if not path.exists():
        return {"day": day, "status": "NO SEALED BOOK"}
    book = json.loads(path.read_text(encoding="utf-8"))
    bench, why_b = _sessions_after(_bars(BENCH), day, horizon)
    graded, pending = [], []
    for p in book["predictions"]:
        if not p["claims"]:
            continue
        r, why = _sessions_after(_bars(p["symbol"]), day, horizon)
        if r is None:
            pending.append({"symbol": p["symbol"], "why": why})
            continue
        rel = r - bench if bench is not None else None
        graded.append({"symbol": p["symbol"], "ret": round(r, 4),
                       "rel": round(rel, 4) if rel is not None else None,
                       "hit": (rel > 0) if rel is not None else None})
    hits = [g["hit"] for g in graded if g["hit"] is not None]
    return {
        "day": day, "horizon_sessions": horizon,
        "content_sha256": book.get("content_sha256"),
        "benchmark_return": round(bench, 4) if bench is not None else None,
        "benchmark_note": why_b,
        "n_claims": book["claims_made"], "n_graded": len(graded), "n_pending": len(pending),
        "hit_rate": round(sum(hits) / len(hits), 4) if hits else None,
        "mean_rel": round(sum(g["rel"] for g in graded if g["rel"] is not None) / len(graded), 4)
        if graded else None,
        # A hit rate on three names is not a hit rate. Said here rather than left
        # for the reader to notice.
        "reads_as_evidence": len(hits) >= 20,
        "note": ("fewer than 20 graded claims: this is a receipt, not a result"
                 if len(hits) < 20 else ""),
        "graded": graded, "pending": pending,
    }


# ------------------------------------------------------------------------- CLI


#: A seal with fewer claims than this is not an error -- markets are quiet and
#: a generator that fires on nothing has said something. It IS a thing that has
#: to be explained out loud rather than noticed a week later.
MIN_CLAIMS_PER_GENERATOR = 10


def _report_claims_bar(book: dict) -> None:
    """Print claims per generator against the bar, and DIAGNOSE a shortfall.

    On 2026-08-30 a book sealed ONE claim out of 151 names and the number sat
    in a line of output nobody read as a problem. A low count has three very
    different causes -- a quiet market, a universe too small to contain
    candidates, or a clause that is silently unreadable -- and they need
    different fixes. So the shortfall is named, and the two diagnostics that
    separate those causes are printed beside it.
    """
    by_gen = book.get("claims_by_generator") or {}
    if not by_gen:
        print("  CANNOT DETERMINE claims per generator: the book carries no "
              "`claims_by_generator`.")
        return
    considered = book.get("universe_considered") or 0
    low = {g: n for g, n in by_gen.items() if (n or 0) < MIN_CLAIMS_PER_GENERATOR}
    for g, n in sorted(by_gen.items()):
        mark = "ok " if (n or 0) >= MIN_CLAIMS_PER_GENERATOR else "LOW"
        print(f"  claims {mark} {g}: {n} of {considered} considered "
              f"(bar {MIN_CLAIMS_PER_GENERATOR})")
    if not low:
        return
    print(f"  WHY THE COUNT IS LOW -- {len(low)} generator(s) under the bar. The three "
          f"causes need different fixes and these two numbers separate them:")
    preds = book.get("predictions") or []
    unread: dict[str, int] = {}
    failed: dict[str, int] = {}
    for pr in preds:
        for c in pr.get("unreadable_clauses") or []:
            unread[c] = unread.get(c, 0) + 1
        for c in pr.get("failed_clauses") or []:
            failed[c] = failed.get(c, 0) + 1
    if unread:
        top = sorted(unread.items(), key=lambda kv: -kv[1])[:4]
        print("    UNREADABLE clauses (a data gap, not a market): "
              + ", ".join(f"{c} x{n}" for c, n in top))
    else:
        print("    no clause was unreadable -- this is not a data gap.")
    if failed:
        top = sorted(failed.items(), key=lambda kv: -kv[1])[:4]
        print("    FAILED clauses (the market did not offer it): "
              + ", ".join(f"{c} x{n}" for c, n in top))
    if considered and considered < 200:
        print(f"    and the universe is only {considered} names -- with a strict "
              f"conjunction that is often the binding constraint, not the rule.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seal", action="store_true", help="build and seal today's book")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--grade", action="store_true")
    ap.add_argument("--verify", action="store_true", help="re-hash every sealed book")
    ap.add_argument("--publish", action="store_true",
                    help="copy today's sealed book to docs/seed/predictions/ so the Railway "
                         "loops can read it (the /app/state volume shadows the repo's state/)")
    ap.add_argument("--refresh-prior", action="store_true",
                    help="recompute the measured base rate by walking the whole panel")
    ap.add_argument("--universe", default="corpus", choices=("corpus", "tracker"),
                    help="corpus = the 151-name news panel (the control); tracker = the "
                         "whole-market analyst watchlist, BUY/STRONG_BUY only")
    ap.add_argument("--day", default=None, help="ET trading day (default: today)")
    ap.add_argument("--horizon", type=int, default=HORIZON_SESSIONS)
    args = ap.parse_args(argv)
    config.load_env()
    day = args.day or _exits.session_day()

    if args.verify:
        return 1 if verify() else 0

    if args.refresh_prior:
        p = rule_prior(refresh=True)
        print(json.dumps(p, indent=1))
        if not args.seal:
            return 0

    if args.publish:
        # The Railway loops mount a volume over /app/state, so a book sealed
        # here and committed under state/ is INVISIBLE to them. docs/seed/ is
        # how the theme universe already reaches the container.
        from alpha.brains.murat_rule import SEED_BOOKS
        src = sorted(BOOKS.glob(f"{day}.json")) + sorted(BOOKS.glob(f"{day}.resealed_*.json"))
        if not src:
            print(f"nothing to publish: no sealed book for {day}")
            return 1
        SEED_BOOKS.mkdir(parents=True, exist_ok=True)
        dst = SEED_BOOKS / f"{day}.json"
        dst.write_text(src[-1].read_text(encoding="utf-8"), encoding="utf-8")
        print(f"published {src[-1].name} -> {dst}")
        print("  now: git add docs/seed/predictions && git commit && git push, then redeploy.")
        print("  Until that push lands, the loops decline every symbol with 'no sealed book',")
        print("  which is the SAFE failure and is recorded as a refusal, not as silence.")
        return 0

    if args.seal:
        book = build(source=args.universe)
        path = seal(book)
        print(f"sealed {path}")
        print(f"  day {book['day']}  sha256 {book['content_sha256'][:16]}")
        print(f"  considered {book['universe_considered']}, claims {book['claims_made']}"
              + (f", skipped {book['skipped']}" if book["skipped"] else ""))
        if book["universe_note"]:
            print(f"  {book['universe_note']}")
        _report_claims_bar(book)
        args.show = True

    if args.show:
        # NEWEST FIRST. A reseal writes a NEW file beside the original rather
        # than overwriting it (that is the tamper-evidence), so reading
        # `<day>.json` unconditionally showed the SUPERSEDED book -- it printed
        # "0 claims" minutes after a reseal that made one.
        cands = sorted(BOOKS.glob(f"{day}.json")) + sorted(BOOKS.glob(f"{day}.resealed_*.json"))
        if not cands:
            print(f"no sealed book for {day}")
            return 1
        path = cands[-1]
        book = json.loads(path.read_text(encoding="utf-8"))
        print(f"\nSEALED BOOK {book['day']}  ({path.name}, sealed {book['sealed_at_utc']}, "
              f"sha {book['content_sha256'][:16]})")
        if len(cands) > 1:
            print(f"  {len(cands)} sealed files for this day; showing the NEWEST. "
                  f"The earlier ones are kept, not replaced.")
        # The two universes carry DIFFERENT point-in-time bounds and neither is
        # wrong: the corpus book is bounded by the last closed session it read
        # prices through, the tracker book by the capture stamp on its rows.
        # Printing one key for both crashed the display AFTER a successful
        # seal, which reads exactly like a seal that failed.
        pit = book.get("pit") or {}
        bound = (pit.get("price_context_through")
                 or (f"tracker captured {pit['tracker_observed_at']}"
                     if pit.get("tracker_observed_at") else "NOT STATED"))
        print(f"  PIT bound: {bound}; "
              f"{book['universe_considered']} considered, {book['claims_made']} claims "
              f"{book.get('claims_by_generator') or ''}")
        print(f"  {book['authority']}")

        ev = [p for p in book["predictions"] if p.get("generator") == "event_counts_v1"]
        print(f"\n  -- event_counts_v1 ({sum(1 for p in ev if p['claims'])} claims) --")
        for p in ev:
            if not p["claims"]:
                continue
            print(f"  {p['rank']:>4} {p['symbol']:<6} {p['score']:>7.4f} "
                  f"{(p['expected_abs_move_21d'] or 0) * 100:>6.1f}%  {p['driver']}")

        rr = [p for p in book["predictions"] if p.get("generator") == RULE_GENERATOR]
        if rr:
            claims = [p for p in rr if p["claims"]]
            print(f"\n  -- {RULE_GENERATOR} ({len(claims)} claims of {len(rr)} scored) --")
            print(f"  {'rank':>4} {'sym':<6} {'p_up':>6} {'expR':>8} {'down':>8} {'conf':>5}  "
                  f"{'variant':<8} blocking clause(s)")
            # Claims, then the best few declines -- so a book that claims nothing
            # still SHOWS the numbers it declined on. Murat, 2026-08-30: the
            # engine may not answer "I don't know"; it must publish the number.
            for p in (claims + [p for p in rr if not p["claims"]][:8]):
                print(f"  {p['rank']:>4} {p['symbol']:<6} {p['p_up_21d']:>6.3f} "
                      f"{(p['exp_return'] or 0):>8.4f} {(p['downside_5pct'] or 0):>8.4f} "
                      f"{p['confidence']:>5.2f}  {p['rule_variant']:<8} "
                      f"{', '.join(p['failed_clauses']) or '(none -- CLAIMS)'}")

    if args.grade:
        rep = grade(day, horizon=args.horizon)
        print(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
