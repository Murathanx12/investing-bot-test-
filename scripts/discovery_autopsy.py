"""DISCOVERY_AUTOPSY -- did AEGIS even GENERATE today's biggest movers?

    python -m scripts.discovery_autopsy                # after the close
    python -m scripts.discovery_autopsy --top 30

WHY (Murat, 28 Aug; vision file §4.3 in Aegis-Finance)
========================================================
The old autopsy asked one question: did our trades win? This asks the second,
more important one: **what were today's largest idiosyncratic winners and
losers across the WHOLE market, what evidence existed before they moved, and
did AEGIS ever put the name on a list?** A stock that rises 18% on something
reported overnight in Korean industry press, that no AEGIS list contained, is
not a forecast error -- it is an OPPORTUNITY-DISCOVERY FAILURE, and it becomes
tonight's research task. "Find Micron before it was Micron" is only testable
if every day counts the Microns we never looked at.

WHAT IT DOES
============
1. venue movers: Alpaca screener top gainers/losers (US equities).
2. for each mover, WHERE was it in our pipeline today:
     digest_bet       -- premarket_digest wrote a bet for it
     digest_universe  -- in the 141-name digest universe, no bet
     window_universe  -- on the earnings-window list
     theme_seed       -- one of Murat's theme names
     candidate        -- scripts.candidates produced it
     NOT_GENERATED    -- nowhere. The failure class this script exists for.
3. pre-move evidence: how many Alpaca news items in the prior 24h (a number a
   code path could have seen), and whether the name has options (tradeable).
4. receipt: state/autopsy/discovery_<day>.json with the per-class counts, so a
   week of them says whether the generator is widening or not.

5. THE OPPORTUNITY-RECALL LEDGER (B3, 2026-09-05): the same movers, typed by
   WHICH STAGE OF OURS lost them -- `NOT_OBSERVED` / `GENERATED_NOT_RANKED` /
   `RANKED_NOT_BOUGHT` / `BOUGHT_SOLD_EARLY`, or `CAPTURED`. A location says
   where the name was; a type says what to repair, and the four repairs are
   completely different (coverage / the model / execution / the exit rule).
   Written to `state/opportunity_recall/<day>.jsonl`, one row per mover, both
   sides of the tape, so a week of them is a `group by`.

A RECEIPT EVERY NIGHT, INCLUDING AN EMPTY ONE. An empty night writes a receipt
that says it was empty and why; it does not write nothing. A missing file and a
night on which nothing happened are indistinguishable afterwards, and this
script's whole value is the count across days.

Shadow. Places nothing. A NOT_GENERATED mover with pre-move evidence is a row
for the overnight research queue, not a trade.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpha import config, contract, exits, fleet, recall
from alpha.broker.alpaca import AlpacaPaper

STATE = Path(__file__).resolve().parent.parent / "state"


def _state_dir() -> Path:
    """The ledger directory, so this script reads the SAME state the loop wrote
    on Railway (a mounted volume shadows the image's `state/`)."""
    import os
    return Path(os.getenv("AAT_LEDGER_DIR") or STATE)


def _day() -> str:
    """The ET trading day, from the repo's ONE clock convention.

    It used to be `now_utc - 4h` inline, which is the same arithmetic written a
    second time. Two definitions of "today" is how a writer and a reader
    disagree for the four hours a day when the UTC date has rolled and the ET
    date has not."""
    return exits.session_day()


# ---------------------------------------------------------------------------
# The pipeline state a recall row is classified against
# ---------------------------------------------------------------------------

def ranked_symbols(day: str) -> tuple[set[str], str]:
    """Names the day's SEALED book actually admitted, across every role.

    Ranked means "our own book named it", not "it was in the universe". Returns
    the set and a provenance string; an absent seal is reported, never silently
    treated as an empty ranking -- with no seal, every observed name would type
    as GENERATED_NOT_RANKED and the ledger would blame the model for a night the
    seal never ran.
    """
    from scripts.utilization import sealed_book
    payload = sealed_book(day)
    if payload is None:
        return set(), f"NO SEAL for {day} -- `ranked` is UNKNOWN, not empty"
    syms = {str(h.get("symbol") or "").upper()
            for p in (payload.get("portfolios") or {}).values()
            for h in ((p or {}).get("holdings") or [])}
    return {s for s in syms if s}, f"seal {str(payload.get('content_sha256'))[:12]}"


def positions_from_ledger(day: str) -> tuple[set[str], dict[str, bool], str]:
    """`(held_on_or_before_day, sold_early_on_day, provenance)` from the ledger.

    * held: a `submitted` entry row on or before `day`.
    * sold early: an exit row dated `day` whose typed reason is an EMERGENCY one
      -- which under `alpha/contract.py` is precisely "closed before the minimum
      hold, for a reason the contract names" -- or an entry and exit in the SAME
      session, which is the churn the fleet was measured at 60% on.

    An UNTYPED exit row (written before 2026-09-05) is not counted as sold-early:
    absence of a code is not evidence of a code, and inventing one would put a
    number on the exact thing the enum exists to measure.
    """
    path = _state_dir() / "decisions.jsonl"
    if not path.exists():
        return set(), {}, f"NO LEDGER at {path} -- `bought` is UNKNOWN, not empty"
    entered: dict[str, str] = {}
    sold_early: dict[str, bool] = {}
    n = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            n += 1
            sym = str(r.get("symbol") or "").upper()
            if not sym:
                continue
            d = str(r.get("ts_utc") or "")[:10]
            if r.get("action") == "submitted":
                entered.setdefault(sym, d)
            if r.get("brain") == "exit" and r.get("action") == "closed" and d == day:
                code = ((r.get("outcome") or {}).get("exit_reason") or "").strip()
                if code in contract.EMERGENCY_EXIT_REASONS or entered.get(sym) == day:
                    sold_early[sym] = True
    held = {s for s, d in entered.items() if d <= day}
    return held, sold_early, f"{n} ledger rows from {path}"


def movers(client, top: int) -> list[dict]:
    d = client._request("GET", "/v1beta1/screener/stocks/movers", base=config.data_url(), params={"top": top}) or {}
    rows = []
    for kind in ("gainers", "losers"):
        for m in d.get(kind) or []:
            rows.append({"symbol": m.get("symbol"), "kind": kind, "pct": float(m.get("percent_change") or 0.0),
                         "price": float(m.get("price") or 0.0)})
    return rows


def universe_movers(day: str) -> list[dict]:
    """The day's movers as `scripts.daily_autopsy` measured them, if it ran.

    WHY BOTH SOURCES. The venue's `/screener/stocks/movers` returns a handful of
    names and applies its own opaque filter -- on 2026-09-04 it gave SEVEN names
    at or above $3, while `daily_autopsy` ranked the SAME session across the
    3,056-name tradable universe on SIP closes and named NX +22.2%, GWRE -19.9%,
    LULU -17.4% and a five-name Technology cluster, none of which the screener
    listed. "The biggest idiosyncratic winners and losers across the WHOLE
    market" is the second question's own wording, and seven screener rows are
    not the whole market.

    So the recall ledger takes the union, and every row records `mover_source`.
    The scheduler runs `daily_autopsy` immediately before this script, so the
    file is normally there; when it is not, this returns nothing and the ledger
    is the screener's alone, which the receipt states.
    """
    path = STATE / "autopsy" / f"{day}.json"
    if not path.exists():
        return []
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for m in d.get("movers") or []:
        sym = str(m.get("symbol") or "").upper()
        if not sym:
            continue
        out.append({"symbol": sym,
                    "kind": "gainers" if m.get("side") == "WIN" else "losers",
                    "pct": round(100.0 * float(m.get("ret_1d") or 0.0), 2),
                    "price": None,
                    "mover_source": "daily_autopsy universe",
                    "industry": m.get("industry"),
                    "market_cap_usd": m.get("market_cap_usd"),
                    "had_print": m.get("had_print")})
    return out


def our_lists(day: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {"digest_bet": set(), "digest_universe": set(), "window_universe": set(),
                                "theme_seed": set(), "candidate": set()}
    p = STATE / "premarket" / f"{day}.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        out["digest_bet"] = {b["symbol"] for b in d.get("bets") or []}
        out["digest_universe"] = set(d.get("universe") or [])
    p = STATE / "window_universe.json"
    if p.exists():
        out["window_universe"] = {str(r["symbol"]).upper() for r in json.loads(p.read_text(encoding="utf-8")).get("rows") or []}
    try:
        out["theme_seed"] = set(fleet.theme_symbols())
    except Exception:                                                   # noqa: BLE001
        pass
    p = STATE / "candidates" / f"{day}.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        out["candidate"] = {str(r.get("symbol") or r.get("sym")).upper() for r in (d.get("candidates") or d.get("rows") or [])}
    return out


def classify(symbol: str, lists: dict[str, set[str]]) -> str:
    for k in ("digest_bet", "candidate", "digest_universe", "window_universe", "theme_seed"):
        if symbol in lists[k]:
            return k
    return "NOT_GENERATED"


def pre_move_evidence(client, symbol: str) -> dict:
    start = (datetime.now(timezone.utc) - timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = (datetime.now(timezone.utc) - timedelta(hours=4)).replace(hour=13, minute=30, second=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        d = client._request("GET", "/v1beta1/news", base=config.data_url(),
                            params={"symbols": symbol, "start": start, "end": end, "limit": 20, "sort": "desc"})
        news = (d or {}).get("news") or []
    except Exception:                                                   # noqa: BLE001
        news = []
    try:
        a = client._request("GET", f"/v2/assets/{symbol}") or {}
        options = "has_options" in (a.get("attributes") or [])
    except Exception:                                                   # noqa: BLE001
        options = None
    return {"news_before_open": len(news), "first_headline": (news[-1].get("headline") if news else None), "has_options": options}


def _write_receipt(day: str, payload: dict) -> Path:
    out = STATE / "autopsy"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"discovery_{day}.json"
    path.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--min-price", type=float, default=3.0)
    ap.add_argument("--day", default=None, help="ET session day (default: today)")
    args = ap.parse_args()
    config.load_env()
    day = args.day or _day()
    try:
        client = AlpacaPaper()
        rows = [m for m in movers(client, args.top) if m["price"] >= args.min_price]
    except Exception as exc:                                            # noqa: BLE001
        # A RECEIPT EVEN WHEN THE VENUE REFUSES. Silence and "no movers today"
        # are the same file on disk otherwise, and the count across days is the
        # whole point of this script.
        path = _write_receipt(day, {
            "date": day, "status": "REFUSED", "counts": {}, "movers": [],
            "research_queue": [],
            "why": f"{type(exc).__name__}: {str(exc)[:300]}",
            "note": ("the venue would not answer for the mover screen. This is a "
                     "refusal, not a night with no movers -- do not read it as "
                     "evidence about the tape.")})
        print(f"DISCOVERY AUTOPSY {day}: REFUSED -- {type(exc).__name__}: {str(exc)[:200]}")
        print(f"receipt: {path}")
        return 1
    for m in rows:
        m.setdefault("mover_source", "venue screener")
    # The whole-market movers from daily_autopsy, if it ran first (it does on the
    # after-close block). Screener rows win on a symbol clash -- they carry the
    # price the min-price filter was applied to.
    seen = {m["symbol"] for m in rows}
    extra = [m for m in universe_movers(day) if m["symbol"] not in seen]
    rows = rows + extra
    lists = our_lists(day)
    counts: dict[str, int] = {}
    if not rows:
        path = _write_receipt(day, {
            "date": day, "status": "EMPTY", "counts": {}, "movers": [],
            "research_queue": [],
            "why": (f"the venue's screener returned no mover at or above "
                    f"${args.min_price:.0f}. An EMPTY night, recorded as one."),
            "recall": recall.summarise([])})
        print(f"DISCOVERY AUTOPSY {day}: EMPTY -- no movers >= ${args.min_price:.0f}")
        print(f"receipt: {path}")
        return 0
    n_screen = sum(1 for m in rows if m.get("mover_source") == "venue screener")
    print(f"DISCOVERY AUTOPSY {day}: {len(rows)} movers -- {n_screen} from the venue "
          f"screener (>= ${args.min_price:.0f}), {len(rows) - n_screen} from the "
          f"whole-market daily_autopsy universe\n")
    print(f"{'sym':<6}{'kind':<8}{'move':>7}  {'where in our pipeline':<17}{'news<open':>10}  {'opts':<5} first headline")
    for m in rows:
        where = classify(m["symbol"], lists)
        counts[where] = counts.get(where, 0) + 1
        ev = pre_move_evidence(client, m["symbol"])
        m.update({"where": where, **ev})
        print(f"{m['symbol']:<6}{m['kind']:<8}{m['pct']:>+6.1f}%  {where:<17}{ev['news_before_open']:>10}  "
              f"{str(ev['has_options']):<5} {str(ev['first_headline'] or '')[:60]}")
    missed = [m for m in rows if m["where"] == "NOT_GENERATED" and m["news_before_open"] > 0]
    print(f"\nby class: {counts}")
    print(f"NOT_GENERATED with pre-open evidence (research queue): {[m['symbol'] for m in missed]}")

    # ---- THE OPPORTUNITY-RECALL LEDGER -----------------------------------
    # `observed` is the union of every AEGIS list including the whole tracker
    # watchlist -- the widest thing we can honestly claim to have looked at.
    observed = set().union(*lists.values()) if lists else set()
    tracker_file = _state_dir() / "tracker" / f"{day}.jsonl"
    tracker_n = 0
    if tracker_file.exists():
        with tracker_file.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    observed.add(str(json.loads(line)["symbol"]).upper())
                    tracker_n += 1
                except (ValueError, KeyError):
                    continue
    ranked, ranked_why = ranked_symbols(day)
    bought, sold_early, bought_why = positions_from_ledger(day)
    inputs = {
        "observed_n": len(observed), "observed_sources": sorted(lists),
        "tracker_rows": tracker_n,
        "ranked_n": len(ranked), "ranked_source": ranked_why,
        "bought_n": len(bought), "bought_source": bought_why,
        "sold_early_n": len(sold_early),
    }
    # A GUARD DERIVES ITS INPUTS OR REFUSES. With no seal, every observed name
    # would type GENERATED_NOT_RANKED and the ledger would blame the model for a
    # night the seal never ran. With no ledger, everything ranked would type
    # RANKED_NOT_BOUGHT and blame execution. Both are recorded and the ledger is
    # written UNCLASSIFIED rather than confidently wrong.
    unreadable = [w for w in (ranked_why, bought_why) if w.startswith("NO ")]
    for m in rows:
        m["side"] = "WIN" if m["kind"] == "gainers" else "LOSS"
    if unreadable:
        recall_rows = [dict(m, miss_type=None, recall_kind=None,
                            cannot_determine="; ".join(unreadable)) for m in rows]
        summary = {"status": "CANNOT DETERMINE", "why": "; ".join(unreadable),
                   "inputs": inputs,
                   "note": ("classified nothing rather than blaming a stage for a job "
                            "that did not run")}
    else:
        recall_rows = recall.classify_day(rows, observed=observed, ranked=ranked,
                                          bought=bought, sold_early=sold_early)
        summary = dict(recall.summarise(recall_rows), status="ok", inputs=inputs)

    led = _state_dir() / "opportunity_recall"
    led.mkdir(parents=True, exist_ok=True)
    led_path = led / f"{day}.jsonl"
    with led_path.open("w", encoding="utf-8") as fh:
        for r in recall_rows:
            fh.write(json.dumps({"day": day, **r}, default=str) + "\n")

    print("\nOPPORTUNITY RECALL -- which stage of OURS lost each mover")
    if summary.get("status") == "ok":
        print(f"  by miss type: {summary['by_miss_type']}")
        print(f"  winners {summary['n_winners']} recall {summary['winner_recall']}   "
              f"losers {summary['n_losers']} avoidance {summary['loser_avoidance']}")
        print(f"  {summary['reading']}")
    else:
        print(f"  CANNOT DETERMINE: {summary['why']}")
    print(f"  ledger: {led_path}")

    path = _write_receipt(day, {"date": day, "status": "ok", "counts": counts,
                                "movers": recall_rows,
                                "research_queue": [m["symbol"] for m in missed],
                                "recall": summary,
                                "recall_ledger": str(led_path),
                                "mover_sources": {
                                    "venue_screener": n_screen,
                                    "daily_autopsy_universe": len(rows) - n_screen}})
    print(f"receipt: {path}   (shadow; a missed name is a research task, not a trade)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
