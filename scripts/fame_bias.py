"""FAME_BIAS_v1 -- does revealing the ticker change the score of identical numbers?

    python -m scripts.fame_bias --n 5 --dry        # build packets, no LLM calls
    python -m scripts.fame_bias --n 5              # run it

THE COMPLAINT THIS TESTS
========================
Murat's standing objection to every stock-picking system, ours included: it keeps
arriving at the names everybody already talks about. `alpha/universe.py` fixed
the *search space* -- 4,634 names, no fame score anywhere in the ranker. What it
could not fix is the LLM, which has read the internet and knows NVDA is
important and knows nothing about a $400M industrial.

That bias, if it exists, is invisible to every guard we have, because the ranker
genuinely cannot see a ticker and will pass its own test forever.

THE DESIGN
==========
One packet of REAL, price-derived numbers per company. Each packet is shown in
two conditions that differ in exactly one respect:

    ANONYMISED   "Company #4812", sector only
    REVEALED     the same numbers, with the ticker and company name

and each condition is drawn TWICE, because the difference between conditions
means nothing without knowing what the model does when nothing changes at all.

    drift = mean(revealed) - mean(anonymised)      the effect
    noise = |draw1 - draw2| within a condition     the floor it must clear

**A result that does not clear its own noise floor is not a result.** This is
the same discipline as the shock graph's MDE: ask whether the instrument could
have detected the effect before reporting one.

CONTROLS
========
- Order is randomised per company, so "seen first" cannot masquerade as fame.
- The anonymous ID is random and differs between the two anonymous draws, so a
  stable ID cannot become a covert identity.
- Sector is disclosed in BOTH conditions -- otherwise revealing the ticker also
  reveals the industry, and the experiment would confound fame with information.
- Every cell examined is charged to the `fame_bias` family in
  RESEARCH_ALPHA_BUDGET. Slicing by stratum costs budget, as it should.

WHAT IT DOES NOT DO
===================
Nothing here trades, sizes, or writes execution state. It writes one receipt to
`state/research/`.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import os
import re
import statistics as st
import sys
from datetime import datetime, timezone
from pathlib import Path

from alpha import config, universe
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal
from alpha.spend import llm_post, SpendRefusal

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
OUT = Path(__file__).resolve().parent.parent / "state" / "research"

#: Fame strata. Deliberately hand-labelled: fame is a property of the reader,
#: not of the balance sheet, and no field in the venue's asset record encodes it.
#: Dollar-volume bucket is a proxy for size, NOT for recognisability -- CORZ and
#: IREN trade heavily and almost nobody outside the trade knows them.
STRATA = {
    "household": ["NVDA", "AAPL", "TSLA", "MSFT", "AMZN"],
    "investor_famous": ["AMD", "AVGO", "MU", "INTC", "ORCL"],
    "sector_known": ["IREN", "CORZ", "APLD", "BE", "NBIS"],
    "obscure": ["PUMP", "VSH", "BW", "HIVE", "BTDR"],
}

_LANG = ("Answer in English only. Reply with STRICT JSON and nothing else: "
         '{"score": <integer 0-100>, "reason": "<one sentence, max 25 words>"}')

PROMPT = """You are assessing whether a US-listed equity is an attractive LONG position over the next 3 trading days, on the evidence below and nothing else.

{identity}
Sector: {sector}

Price: ${price:.2f}
12-month price momentum (excluding the last month): {mom:+.1%}
Drawdown from 52-week high: {dd:.1%}
Realised volatility (60 sessions, annualised): {vol:.0%}
Move over the last 5 sessions: {r5:+.1%}
Distance from the 200-session average: {ma:+.1%}
Median daily dollar volume: ${dv:,.0f}

Score 0-100 for how attractive this is as a 3-day long. Use the FULL range and commit to a view; do not default to 50. Judge only the evidence given.
{lang}"""


def build_packet(sym: str, bars: list[dict]) -> dict | None:
    closes = [float(b["c"]) for b in bars if b.get("c")]
    vols = [float(b.get("v") or 0) * float(b["c"]) for b in bars if b.get("c")]
    if len(closes) < 210:
        return None
    px = closes[-1]
    mom = closes[-21] / closes[-252] - 1 if len(closes) >= 252 else closes[-21] / closes[0] - 1
    dd = px / max(closes[-252:]) - 1
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - 60, len(closes))]
    vol = st.pstdev(rets) * math.sqrt(252)
    r5 = px / closes[-6] - 1
    ma = px / (sum(closes[-200:]) / 200) - 1
    dv = st.median(vols[-60:]) if vols else 0.0
    return {"symbol": sym, "price": px, "mom": mom, "dd": dd, "vol": vol,
            "r5": r5, "ma": ma, "dv": dv}


def ask(packet: dict, *, identity: str, sector: str, why: str) -> tuple[int, str] | None:
    # The Authorization header is passed EXPLICITLY. `llm_post` does not add one:
    # omitting it produces a clean HTTP 401 that looks exactly like a dead key,
    # and cost twenty minutes of investigating an outage that did not exist.
    key = os.getenv("AAT_DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise SpendRefusal("AAT_DEEPSEEK_API_KEY is not set")
    body = {"model": MODEL, "temperature": 0.4, "max_tokens": 120,
            "messages": [{"role": "user", "content": PROMPT.format(
                identity=identity, sector=sector, lang=_LANG, **{
                    k: packet[k] for k in ("price", "mom", "dd", "vol", "r5", "ma", "dv")})}]}
    try:
        data, _ = llm_post(DEEPSEEK_URL, body, headers={"Authorization": f"Bearer {key}"},
                           why=why, caller="fame_bias")
    except (SpendRefusal, Exception) as exc:                      # noqa: BLE001
        print(f"    call failed: {type(exc).__name__}: {str(exc)[:110]}")
        return None
    try:
        txt = data["choices"][0]["message"]["content"]
        m = re.search(r'\{.*\}', txt, re.S)
        obj = json.loads(m.group(0)) if m else json.loads(txt)
        return int(obj["score"]), str(obj.get("reason", ""))[:160]
    except (KeyError, IndexError, ValueError, TypeError, AttributeError):
        print(f"    unparseable reply: {str(data)[:110]}")
        return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=5, help="companies per stratum")
    p.add_argument("--dry", action="store_true", help="build packets, make no LLM calls")
    p.add_argument("--seed", type=int, default=20260826)
    args = p.parse_args()
    config.load_env()
    rng = random.Random(args.seed)
    client = AlpacaPaper()

    members = {m.symbol: m for m in universe.load()} if universe.load() else {}
    syms = [s for v in STRATA.values() for s in v[:args.n]]
    print(f"fetching bars for {len(syms)} symbols ...")
    try:
        bars = client.stock_bars_multi(syms, start="2025-06-01", timeframe="1Day")
    except BrokerRefusal as exc:
        print(f"REFUSED: {exc}")
        return 1

    packets, sectors = {}, {}
    for stratum, group in STRATA.items():
        for s in group[:args.n]:
            pk = build_packet(s, bars.get(s, []))
            if pk:
                pk["stratum"] = stratum
                packets[s] = pk
                m = members.get(s)
                sectors[s] = (getattr(m, "industry", None) or "not disclosed") if m else "not disclosed"
    print(f"built {len(packets)} packets of {len(syms)} requested")
    missing = [s for s in syms if s not in packets]
    if missing:
        print(f"  no packet (insufficient history): {missing}")

    if args.dry:
        for s, pk in list(packets.items())[:3]:
            print(f"\n  {s} [{pk['stratum']}] mom {pk['mom']:+.1%} dd {pk['dd']:.1%} "
                  f"vol {pk['vol']:.0%} r5 {pk['r5']:+.1%}")
        return 0

    why = ("Measures whether the LLM scores identical numbers differently when the ticker is "
           "revealed. If the drift is large, the candidate funnel is biased toward famous names "
           "today and we must decide to anonymise packets before the competition account opens.")

    rows = []
    for i, (sym, pk) in enumerate(packets.items(), 1):
        anon_ids = rng.sample(range(1000, 9999), 2)
        conds = [("anon", f"Company #{anon_ids[0]}"), ("anon", f"Company #{anon_ids[1]}"),
                 ("revealed", f"{sym} ({sym})"), ("revealed", f"{sym} ({sym})")]
        rng.shuffle(conds)                       # order cannot masquerade as fame
        print(f"[{i}/{len(packets)}] {sym} [{pk['stratum']}]", end=" ", flush=True)
        for cond, ident in conds:
            got = ask(pk, identity=f"Company: {ident}", sector=sectors.get(sym, "not disclosed"), why=why)
            if got is None:
                continue
            score, reason = got
            rows.append({"symbol": sym, "stratum": pk["stratum"], "condition": cond,
                         "identity": ident, "score": score, "reason": reason})
            print(f"{cond[0]}{score}", end=" ", flush=True)
        print()

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "fame_bias_v1.json"
    path.write_text(json.dumps({
        "experiment": "FAME_BIAS_v1", "model": MODEL, "temperature": 0.4,
        "run_utc": datetime.now(timezone.utc).isoformat(), "seed": args.seed,
        "packets": packets, "rows": rows}, indent=1), encoding="utf-8")
    print(f"\n{len(rows)} scored replies -> {path}")
    print("run `python -m scripts.fame_bias_report` for the verdict")
    return 0


if __name__ == "__main__":
    sys.exit(main())
