"""ANALYST_PANEL -- start the point-in-time clock today, because we cannot start it yesterday.

    python -m scripts.analyst_panel --n 500          # capture today's slice
    python -m scripts.analyst_panel --n 20 --dry     # shape check, few calls

WHY THIS EXISTS
===============
`ANALYST_DISLOCATION_FUNNEL_v1` is blocked, and it is blocked on the one thing
no amount of compute can produce: **point-in-time analyst vintages we did not
record.** A target gap read today against a target revised three months ago is
not a signal, it is a lookahead dressed as one, and the parent project has
already paid for that mistake once (`public_date` and `searchsorted(side=...)`).

The lane has been "blocked" for weeks on that basis. But the reason it stays
blocked forever is that nobody starts the recording, because on day one the
panel is worth nothing. It is worth nothing on day two as well. In three months
it is the only PIT analyst panel this project has, and it is un-buyable.

**Every day this is not running is a day permanently missing from the panel.**

WHAT IS AND IS NOT AVAILABLE
============================
Finnhub's free tier refuses `stock/price-target` (HTTP 403), so the literal
">50% analyst upside" screen from Murat's own process **cannot be reproduced**.
Stated plainly rather than approximated: a consensus target is not derivable
from recommendation counts, and pretending otherwise would put a fabricated
number in a PIT panel, which is worse than a missing column.

What IS available, and recorded:

    stock/recommendation   strongBuy/buy/hold/sell/strongSell BY PERIOD
                           -> net breadth, and its CHANGE across periods, which
                              is the revision-direction leg of the funnel
    stock/profile2         market cap, industry, shares outstanding
                           -> the universe's missing cap screen and the sector
                              bucket that cross-sectional normalisation needs
    (bars, from Alpaca)    drawdown, momentum, vol, dollar volume -- fetched in
                           BULK because per-name calls are the scarce resource

THE STAMP IS THE POINT
======================
Every row carries `captured_utc` and the vendor's own `period`. A value may be
used strictly AFTER its capture stamp. That is the whole discipline, and it is
the only reason a panel built forward is worth more than one scraped backward.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics as st
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from alpha import config, universe
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal

PANEL = Path(__file__).resolve().parent.parent / "state" / "research" / "analyst_panel"
BASE = "https://finnhub.io/api/v1"
#: MEASURED 2026-08-26: 30 back-to-back `profile2` calls with NO sleep at all
#: returned 30x HTTP 200 in 39.7s -- network latency alone paces this at ~45
#: calls/minute, already under the free tier's limit. The original 1.15s sleep
#: was therefore delay bought against a 429 that does not happen, and it roughly
#: doubled the job. 0.4s keeps a margin without paying for one twice.
SLEEP_S = 0.4


from alpha import analyst_targets

def _get(path: str, key: str, **kw):
    kw["token"] = key
    url = f"{BASE}/{path}?" + urllib.parse.urlencode(kw)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=25) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:                     # rate limited: back off, do not drop the name
                time.sleep(3 + 3 * attempt)
                continue
            if e.code == 403:
                return {"_forbidden": True}
            return {"_error": f"HTTP {e.code}"}
        except Exception as e:                    # noqa: BLE001
            return {"_error": type(e).__name__}
    return {"_error": "rate limited after retries"}


def net_breadth(rec: dict) -> float | None:
    """(bullish - bearish) / total. None when there is no coverage AT ALL.

    Zero coverage and balanced coverage are different facts and must not collapse
    to the same 0.0 -- that is the `rev_breadth` lesson from the parent project,
    where a bound asserted from a formula silently filtered the informative tail.
    """
    tot = sum(int(rec.get(k) or 0) for k in
              ("strongBuy", "buy", "hold", "sell", "strongSell"))
    if tot <= 0:
        return None
    bull = int(rec.get("strongBuy") or 0) + int(rec.get("buy") or 0)
    bear = int(rec.get("sell") or 0) + int(rec.get("strongSell") or 0)
    return (bull - bear) / tot


def price_features(bars: list[dict]) -> dict:
    c = [float(b["c"]) for b in bars if b.get("c")]
    dv = [float(b.get("v") or 0) * float(b["c"]) for b in bars if b.get("c")]
    if len(c) < 60:
        return {}
    out = {"price": c[-1], "r5": c[-1] / c[-6] - 1 if len(c) > 6 else None,
           "dollar_volume_median_60": st.median(dv[-60:]) if dv else None}
    if len(c) >= 252:
        out["mom_12_1"] = c[-21] / c[-252] - 1
        out["drawdown_52w"] = c[-1] / max(c[-252:]) - 1
    if len(c) >= 200:
        out["dist_200d"] = c[-1] / (sum(c[-200:]) / 200) - 1
    r = [math.log(c[i] / c[i - 1]) for i in range(len(c) - 60, len(c))]
    out["vol_60d_ann"] = st.pstdev(r) * math.sqrt(252)
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=500, help="names to capture")
    p.add_argument("--dry", action="store_true")
    args = p.parse_args()
    config.load_env()
    key = os.getenv("AAT_FINNHUB_API_KEY", "").strip()
    if not key:
        print("REFUSED: AAT_FINNHUB_API_KEY is not set. A panel with a missing day is "
              "better than a panel with an invented one.")
        return 1

    members = universe.load()
    if not members:
        print("REFUSED: no universe snapshot. Run the universe build first.")
        return 1
    tradable = [m for m in members if not m.etf_like]
    # Stratify by dollar-volume bucket so the panel is not another mega-cap list.
    # The whole complaint this project keeps answering is that every candidate
    # set collapses to the famous names; a panel built that way inherits it.
    buckets: dict[str, list] = {}
    for m in tradable:
        buckets.setdefault(m.dv_bucket, []).append(m)
    order = ["mega", "large", "mid", "small", "micro"]
    per = max(1, args.n // len([b for b in order if buckets.get(b)]))
    picked = []
    for b in order:
        got = sorted(buckets.get(b, []), key=lambda m: -m.median_dollar_volume)[:per]
        picked.extend(got)
    picked = picked[:args.n]
    print(f"universe {len(tradable)} tradable -> capturing {len(picked)} "
          f"({', '.join(f'{b}:{sum(1 for m in picked if m.dv_bucket==b)}' for b in order)})")
    if args.dry:
        picked = picked[:5]

    client = AlpacaPaper()
    syms = [m.symbol for m in picked]
    print("fetching bars in bulk ...")
    bars = {}
    for i in range(0, len(syms), 200):
        try:
            bars.update(client.stock_bars_multi(syms[i:i + 200], start="2025-06-01",
                                                timeframe="1Day"))
        except BrokerRefusal as exc:
            print(f"  bar batch failed: {exc}")
    print(f"  bars for {len(bars)} names")

    captured = datetime.now(timezone.utc).isoformat()
    # WRITE AS WE GO. The first version buffered every row and wrote once at the
    # end, so killing a 40-minute job at minute 38 destroyed 225 completed
    # captures -- which is exactly what happened on the first run. A long capture
    # that writes once has no partial credit, and a panel row is worth having
    # whether or not the run that produced it finished.
    PANEL.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).date().isoformat()
    path = PANEL / f"{day}.jsonl"
    fh = path.open("w", encoding="utf-8")
    rows, forbidden, errors = [], 0, 0
    for i, m in enumerate(picked, 1):
        rec = _get("stock/recommendation", key, symbol=m.symbol)
        time.sleep(SLEEP_S)
        prof = _get("stock/profile2", key, symbol=m.symbol)
        time.sleep(SLEEP_S)
        if isinstance(rec, dict) and rec.get("_forbidden"):
            forbidden += 1
            rec = []
        if isinstance(rec, dict) and rec.get("_error"):
            errors += 1
            rec = []
        periods = sorted(rec, key=lambda r: r.get("period", ""), reverse=True)[:4] if rec else []
        nb = [net_breadth(r) for r in periods]
        row = {
            "symbol": m.symbol, "captured_utc": captured,
            "dv_bucket": m.dv_bucket, "exchange": m.exchange,
            "market_cap_usd": (float(prof.get("marketCapitalization")) * 1e6
                               if isinstance(prof, dict) and prof.get("marketCapitalization") else None),
            "industry": (prof.get("finnhubIndustry") if isinstance(prof, dict) else None),
            "ipo": (prof.get("ipo") if isinstance(prof, dict) else None),
            "rec_periods": [{"period": r.get("period"), "strongBuy": r.get("strongBuy"),
                             "buy": r.get("buy"), "hold": r.get("hold"),
                             "sell": r.get("sell"), "strongSell": r.get("strongSell"),
                             "net_breadth": net_breadth(r)} for r in periods],
            "net_breadth": nb[0] if nb else None,
            "net_breadth_delta_1m": (nb[0] - nb[1]) if len(nb) > 1 and None not in nb[:2] else None,
            "coverage": (sum(int(periods[0].get(k) or 0) for k in
                             ("strongBuy", "buy", "hold", "sell", "strongSell"))
                         if periods else 0),
            # The VENDOR consensus is still 403 on this tier and is still never
            # guessed. What changed on 2026-08-29 is that a second, independent
            # source exists: the corpus carries 2,368 broker notes in Benzinga's
            # regular form, each with the firm, the figure and the timestamp it
            # became knowable. `alpha/analyst_targets.py` reads them; this column
            # records the reconstruction, labelled by source so the two are never
            # confused. A THIN panel (fewer than MIN_FIRMS) stays absent.
            "price_target": None,
            "price_target_status": "UNAVAILABLE_FREE_TIER",
        }
        try:
            _pan = analyst_targets.panel(m.symbol, as_of=row["captured_utc"])
            if _pan.n_firms >= analyst_targets.MIN_FIRMS:
                row["price_target"] = _pan.median_target
                row["price_target_status"] = "CORPUS_BROKER_NOTES"
                row["price_target_n_firms"] = _pan.n_firms
                row["price_target_firms"] = _pan.firms[:12]
                row["price_target_newest_age_days"] = (
                    round(_pan.newest_age_days, 1) if _pan.newest_age_days is not None else None)
                row["price_target_dispersion"] = (
                    round(_pan.dispersion, 3) if _pan.dispersion is not None else None)
                row["price_target_split_suspect"] = _pan.split_suspect
            elif _pan.targets:
                row["price_target_status"] = f"THIN_{_pan.n_firms}_FIRMS"
        except Exception as exc:                                        # noqa: BLE001
            # A corpus read must never take the panel down: the panel's whole
            # value is that TODAY's slice gets recorded, and a missing column is
            # recoverable where a missing day is not.
            row["price_target_status"] = f"CORPUS_ERROR: {type(exc).__name__}"
        _rating = analyst_targets.consensus_rating(periods[0]) if periods else None
        row["consensus_rating"] = round(_rating[0], 3) if _rating else None
        row["consensus_rating_scale"] = "1-5, FIVE IS BEST (Murat's bar: >= 4.1)"
        row.update(price_features(bars.get(m.symbol, [])))
        rows.append(row)
        fh.write(json.dumps(row) + "\n")
        fh.flush()
        if i % 25 == 0 or i == len(picked):
            print(f"  [{i}/{len(picked)}] {m.symbol:6s} cov={row['coverage']:3d} "
                  f"nb={row['net_breadth']}", flush=True)

    fh.close()
    covered = sum(1 for r in rows if (r.get("coverage") or 0) > 0)
    print(f"\n{len(rows)} rows -> {path}")
    print(f"  with analyst coverage: {covered} ({100*covered/max(1,len(rows)):.0f}%)")
    print(f"  price-target forbidden: {forbidden}, errors: {errors}")
    _from_corpus = sum(1 for r in rows if r.get("price_target_status") == "CORPUS_BROKER_NOTES")
    _rated = sum(1 for r in rows if r.get("consensus_rating") is not None)
    print(f"  price target reconstructed from broker notes: {_from_corpus} "
          f"({100*_from_corpus/max(1,len(rows)):.0f}%)")
    print(f"  consensus rating from recommendation counts: {_rated} "
          f"({100*_rated/max(1,len(rows)):.0f}%)")
    print("  NOTE: the VENDOR consensus target is still 403 on this tier and is still never")
    print("        approximated. `price_target` is reconstructed from dated broker notes in")
    print("        the corpus and is labelled CORPUS_BROKER_NOTES -- a different source with")
    print("        a different bias, recorded as such rather than merged into one column.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
