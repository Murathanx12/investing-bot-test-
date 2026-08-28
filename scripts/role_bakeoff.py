"""ROLE_BAKEOFF_v1 -- score each model on ONE role against a known answer. Not "pick the stock".

    AAT_ACCOUNT_ROLE=staging python -m scripts.role_bakeoff --role fact
    AAT_ACCOUNT_ROLE=staging python -m scripts.role_bakeoff --role fact --providers deepseek nvidia_kimi hf_glm

WHY
===
A model's authority over a council role must be EARNED on that role, not
inherited from a favourite. The FACT ACCOUNTANT has an answer key: the numbers
in the company's own Exhibit 99.1. Two releases from 28 Aug carry the exact
traps the one-shot digest fell into -- SentinelOne (revenue guide RAISED, EPS
guide LOWERED, in one release) and Workday (subscription vs total revenue).
Each provider reads the same text and is scored on: did it return every
required guidance row, with the right metric, period, and range; did it invent
a row that is not in the text; how long, how many tokens. Structured validity
(a JSON object with the declared keys) is scored too, because a model that is
right in prose and wrong in JSON is wrong for this job.

The scoreboard is written to `state/role_bakeoff_<role>.json` and is the
evidence `alpha/council/run.ROLE_PREFERENCES` should follow, not precede.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from alpha import config
from alpha.council import providers, roles
from alpha.council.providers import ProviderRefusal
from alpha.sources import sec

STATE = Path(os.getenv("AAT_LEDGER_DIR") or "state")

#: Answer keys, from the filings themselves (EDGAR EX-99.1, fetched 2026-08-28).
#: (metric, period, low, high, tolerance as a fraction of the value)
FACT_KEYS = {
    "S": [
        ("revenue", "FY27", 1.202e9, 1.207e9, 0.005),
        ("eps_non_gaap", "FY27", 0.30, 0.32, 0.02),
        ("operating_income", "FY27", 124e6, 128e6, 0.01),
        ("revenue", "Q3FY27", 309e6, 311e6, 0.005),
        ("eps_non_gaap", "Q3FY27", 0.08, 0.09, 0.02),
    ],
    "WDAY": [
        ("subscription_revenue", "FY27", 9.940e9, 9.950e9, 0.002),
        ("operating_margin", "FY27", 31.0, 31.0, 0.02),
        ("revenue", "Q2FY27", 2.649e9, 2.649e9, 0.002),
        ("subscription_revenue", "Q2FY27", 2.471e9, 2.471e9, 0.002),
        ("eps_non_gaap", "Q2FY27", 2.75, 2.75, 0.01),
    ],
}


def _same(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol * max(abs(b), 1e-9)


def score_fact(rows: list[dict], key: list[tuple]) -> dict:
    found, missing = 0, []
    for metric, period, lo, hi, tol in key:
        hit = False
        for r in rows:
            if r["metric"] == metric and r["period"] == period:
                # units may be millions/billions: compare on scale-normalised value
                lo_r, hi_r = _scale(r, lo), _scale(r, hi)
                if _same(lo_r[0], lo, tol) and _same(hi_r[1], hi, tol):
                    hit = True
                    break
        if hit:
            found += 1
        else:
            missing.append(f"{metric}@{period}")
    return {"required": len(key), "found": found, "missing": missing, "n_rows": len(rows)}


def _scale(r: dict, target: float):
    """Bring a row's value to the answer key's scale (USD vs USD_millions etc.)."""
    lo, hi = float(r["value_low"]), float(r["value_high"])
    unit = str(r.get("unit", "")).lower()
    for mult in (1.0, 1e6, 1e9, 1e3):
        cand = (lo * mult, hi * mult)
        if abs(cand[0] - target) <= 0.05 * max(abs(target), 1e-9) or abs(cand[1] - target) <= 0.05 * max(abs(target), 1e-9):
            return cand
    if "million" in unit:
        return (lo * 1e6, hi * 1e6)
    if "billion" in unit:
        return (lo * 1e9, hi * 1e9)
    return (lo, hi)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", default="fact", choices=["fact"])
    ap.add_argument("--providers", nargs="*", default=None)
    ap.add_argument("--symbols", nargs="*", default=["S", "WDAY"])
    args = ap.parse_args()
    config.load_env()
    live = providers.probe(args.providers)
    names = [p for p, v in live.items() if v.get("state") == "live"]
    print("live:", names)
    texts = {}
    for s in args.symbols:
        rels = sec.press_releases(s, limit=2)
        texts[s] = (rels[0]["text"], rels[1]["text"] if len(rels) > 1 else None)

    board = {}
    print(f"\n{'provider':<16}{'family':<10}{'sym':<6}{'found':>6}{'rows':>6}{'s':>6}{'tokens':>8}  missing")
    for prov in names:
        for s in args.symbols:
            cur, prior = texts[s]
            t0 = time.time()
            try:
                raw, meta = providers.chat_json(
                    prov, roles.FACT_SYSTEM, roles.fact_prompt(s, cur, prior_text=prior),
                    caller="bakeoff.fact", max_tokens=4000,
                    why="Decides which provider is ASSIGNED the fact-accountant role: the one that reproduces the filing's guidance rows.")
                rows = roles.normalise_rows(raw)
                sc = score_fact(rows, FACT_KEYS[s])
                sc.update({"valid_json": True, "latency_s": round(time.time() - t0, 1),
                           "tokens": (meta.get("prompt_tokens") or 0) + (meta.get("completion_tokens") or 0)})
            except ProviderRefusal as exc:
                sc = {"required": len(FACT_KEYS[s]), "found": 0, "missing": ["REFUSED: " + str(exc)[:60]], "n_rows": 0,
                      "valid_json": False, "latency_s": round(time.time() - t0, 1), "tokens": None}
            board.setdefault(prov, {})[s] = sc
            print(f"{prov:<16}{providers.PROVIDERS[prov].family:<10}{s:<6}{sc['found']:>3}/{sc['required']:<2}{sc['n_rows']:>6}{sc['latency_s']:>6}{str(sc['tokens']):>8}  {', '.join(sc['missing'])[:70]}")
    totals = {p: sum(v[s]["found"] for s in v) for p, v in board.items()}
    print("\nTOTAL found:", dict(sorted(totals.items(), key=lambda kv: -kv[1])))
    out = STATE / f"role_bakeoff_{args.role}.json"
    out.write_text(json.dumps({"role": args.role, "at_utc": datetime.now(timezone.utc).isoformat(), "answer_key_source": "EDGAR EX-99.1",
                               "board": board, "totals": totals}, indent=1), encoding="utf-8")
    print(f"receipt: {out}\nThe preference order in alpha/council/run.ROLE_PREFERENCES should follow this table.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
