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

`scripts/corpus_features --ic` asked the same question of the COUNTS, with a
block bootstrap over 11-12 date blocks. Rank IC against the 21-session
SPY-relative return, CI at 95%:

    ev_insider_20d          +0.148   [ 0.092,  0.213]   <- insider / stake / activist
    ev_earnings_20d         +0.155   [ 0.035,  0.274]
    ev_analyst_rating_20d   +0.098   [ 0.018,  0.205]
    ev_contract_20d         +0.103   [ 0.002,  0.189]   <- marginal, kept and flagged
    ev_macro_20d            +0.118   [ 0.002,  0.222]   <- EXCLUDED, see below
    attention / sentiment / novelty        ~0 or negative

`ev_macro_20d` is excluded despite clearing zero: macro news is market-wide, so
as a CROSS-SECTIONAL score it mostly ranks how much macro coverage a name
attracts, which is a size proxy wearing an event's name. A feature that cannot
state a per-name mechanism does not enter a per-name book.

**The honest n is 11 DATE BLOCKS, not 4,451 symbol-days**, and 29 features were
screened, so these are SCREENING results and the marginal ones would not survive
a multiplicity correction. That is why this book carries ZERO SIZE: it is T7 in
the roadmap, a prediction book beside the named digest, and the difference
between them is what the NAME adds. It gets order authority when it beats its
own null out of sample, and not before.

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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from alpha import config, drivers
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

#: feature -> (weight, measured 21d SPY-relative rank IC, 95% CI). The weights
#: ARE the ICs, normalised: a reader can check the weighting against the receipt
#: rather than take a hand-tuned number on trust.
SIGNALS: dict[str, tuple[float, tuple[float, float]]] = {
    "ev_insider_20d": (0.148, (0.092, 0.213)),
    "ev_earnings_20d": (0.155, (0.035, 0.274)),
    "ev_contract_20d": (0.103, (0.002, 0.189)),
    "ev_analyst_rating_20d": (0.098, (0.018, 0.205)),
}
IC_RECEIPT = "state/corpus/features/ic_2026-08-29.json"

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


# ------------------------------------------------------------------- the build


def build(*, now: datetime | None = None, universe: list[str] | None = None) -> dict:
    """Today's sealed book, as a dict. Pure over the corpus and the panel."""
    now = now or datetime.now(timezone.utc)
    seal_utc = now.isoformat()
    day = _exits.session_day(now)

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
        f = features.daily_features(sym, as_of_bar or day, crows, bars=bars.get(sym))
        counts = f.get("event_type_counts_20d") or {}
        rows.append({
            "symbol": sym,
            "features": {k: float(counts.get(k.replace("ev_", "").replace("_20d", ""), 0) or 0)
                         for k in SIGNALS},
            "realised_vol_20d": f.get("realised_vol_20d"),
            "n_items_20d": f.get("n_items_20d"),
            "drawdown_from_60d_high": f.get("drawdown_from_60d_high"),
            "days_to_next_catalyst": f.get("days_to_next_catalyst"),
        })

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
    n_claim = int(len(rows) * CLAIM_FRACTION) if not universe_note else 0
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

    payload = {
        "schema": "prediction-book-1",
        "day": day,
        "sealed_at_utc": seal_utc,
        "generator": "event_counts_v1",
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
        "claims_made": n_claim,
        "claim_fraction": CLAIM_FRACTION,
        "skipped": skipped,
        "driver_taxonomy": driver_note,
        "authority": "ZERO SIZE. Nothing in this file may size, order or influence an order.",
        "evidence_caveat": (
            "The weights are SCREENING ICs over 11 date blocks with 29 features screened; the "
            "marginal ones would not survive a multiplicity correction. The blinded-narrative "
            "tournament was NEGATIVE (hit 45% vs a 47% null, IC -0.18), which is why no model "
            "prose enters this book."),
        "universe_note": universe_note,
        "predictions": predictions,
    }
    payload["content_sha256"] = _sha(payload)
    return payload


def seal(book: dict) -> Path:
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seal", action="store_true", help="build and seal today's book")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--grade", action="store_true")
    ap.add_argument("--verify", action="store_true", help="re-hash every sealed book")
    ap.add_argument("--day", default=None, help="ET trading day (default: today)")
    ap.add_argument("--horizon", type=int, default=HORIZON_SESSIONS)
    args = ap.parse_args(argv)
    config.load_env()
    day = args.day or _exits.session_day()

    if args.verify:
        return 1 if verify() else 0

    if args.seal:
        book = build()
        path = seal(book)
        print(f"sealed {path}")
        print(f"  day {book['day']}  sha256 {book['content_sha256'][:16]}")
        print(f"  considered {book['universe_considered']}, claims {book['claims_made']}"
              + (f", skipped {book['skipped']}" if book["skipped"] else ""))
        if book["universe_note"]:
            print(f"  {book['universe_note']}")
        args.show = True

    if args.show:
        path = BOOKS / f"{day}.json"
        if not path.exists():
            print(f"no sealed book for {day}")
            return 1
        book = json.loads(path.read_text(encoding="utf-8"))
        print(f"\nSEALED BOOK {book['day']}  (sealed {book['sealed_at_utc']}, "
              f"sha {book['content_sha256'][:16]})")
        print(f"  price context through {book['pit']['price_context_through']}; "
              f"{book['universe_considered']} considered, {book['claims_made']} claims")
        print(f"  {book['authority']}")
        print(f"\n  {'rank':>4} {'sym':<6} {'score':>7} {'move':>7}  driver")
        for p in book["predictions"]:
            if not p["claims"]:
                continue
            print(f"  {p['rank']:>4} {p['symbol']:<6} {p['score']:>7.4f} "
                  f"{(p['expected_abs_move_21d'] or 0) * 100:>6.1f}%  {p['driver']}")

    if args.grade:
        rep = grade(day, horizon=args.horizon)
        print(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
