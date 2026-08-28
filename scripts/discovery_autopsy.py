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

Shadow. Places nothing. A NOT_GENERATED mover with pre-move evidence is a row
for the overnight research queue, not a trade.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpha import config, fleet
from alpha.broker.alpaca import AlpacaPaper

STATE = Path(__file__).resolve().parent.parent / "state"


def _day() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=4)).date().isoformat()


def movers(client, top: int) -> list[dict]:
    d = client._request("GET", "/v1beta1/screener/stocks/movers", base=config.data_url(), params={"top": top}) or {}
    rows = []
    for kind in ("gainers", "losers"):
        for m in d.get(kind) or []:
            rows.append({"symbol": m.get("symbol"), "kind": kind, "pct": float(m.get("percent_change") or 0.0),
                         "price": float(m.get("price") or 0.0)})
    return rows


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--min-price", type=float, default=3.0)
    args = ap.parse_args()
    config.load_env()
    client = AlpacaPaper()
    day = _day()
    lists = our_lists(day)
    rows = [m for m in movers(client, args.top) if m["price"] >= args.min_price]
    counts: dict[str, int] = {}
    print(f"DISCOVERY AUTOPSY {day}: {len(rows)} movers >= ${args.min_price:.0f}\n")
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
    out = STATE / "autopsy"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"discovery_{day}.json").write_text(json.dumps({"date": day, "counts": counts, "movers": rows,
                                                            "research_queue": [m["symbol"] for m in missed]}, indent=1),
                                               encoding="utf-8")
    print(f"receipt: {out / ('discovery_' + day + '.json')}   (shadow; a missed name is a research task, not a trade)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
