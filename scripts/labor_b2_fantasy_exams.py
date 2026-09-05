"""LABOR DAY LAB — lane B, item B2. FANTASY STRESS EXAMS: does the decider move
the economically correct way when ONE causal fact changes?

    python -m scripts.labor_b2_fantasy_exams --dry-run        # $0.00, stubbed
    python -m scripts.labor_b2_fantasy_exams --cap 5.00       # the paid run

THE QUESTION, AND WHY IT IS NOT THE USUAL ONE
=============================================
Every previous LLM exam in this repo graded the decider against RETURNS. That is
the right question for a book and the wrong one for a reasoning test, because a
return grade confounds two things: does the model reason correctly, and does the
world happen to reward that reasoning over that window. T13 measured the second
and had to spend a lot of tape to say anything about the first.

This exam removes the world. Forty FICTIONAL company situations, each written in
**two versions that differ by exactly ONE causal fact**:

    FDA rejection      vs approval
    sanction imposed   vs sanction lifted
    funding withdrawn  vs funding extended
    supply shock       vs supply relief
    guidance cut       vs guidance raise
    customer loss      vs customer win

Both versions go to the decider as separate calls, in a shuffled order, with no
memory of each other. There is no return label and none is invented. The grade is
**MONOTONICITY**: `p_up_21d` (and `exp_return`, and `downside_5pct`) must move the
economically correct way between the two legs. A model that cannot do that is not
reading the brief, whatever its hit rate on a book.

WHY FICTIONAL, AND WHERE THE NAMES COME FROM
============================================
The entities are drawn from `alpha.transpose.build_entity_map` — the same sealed,
code-built, deterministic era map T13 uses, hashed and never shown to the model.
Nothing here is a real company, so there is nothing to remember: the only thing
the decider can use is the shape of the situation.

THE CANARY, AND WHAT IT MEASURES HERE
=====================================
`blind_tournament`'s canary detects a model that reacts to a fabricated headline.
This exam needs the mirror image: a model that reacts to NOTHING. So eight extra
pairs differ by a causally IRRELEVANT fact (an office relocation, a logo refresh,
a new auditor's home city). The forecast should barely move. The **canary rate**
is the share of those pairs where |Δp_up| exceeds `CANARY_TOLERANCE` — the rate at
which the decider manufactures a view out of noise. High is bad, and it is the
number that says whether a high monotonicity share means anything.

WHAT IS DELIBERATELY ABSENT FROM THE PROMPT
===========================================
No numeric bound of any kind. S28 measured it: "move p_up by at most ±0.10" made
**11 of 13** answers come back at exactly 0.100, while the same guard applied in
CODE gave a mean move of 0.024. A bound the model can see is an anchor. The units
are named ("a probability", "a decimal return") because a unit is not a bound;
nothing tells the model how big a move is allowed.

SPEND
=====
Every paid call goes through `alpha.council.providers.chat_json`, which is the
central path: the English language pin, the non-Latin refusal, the
`alpha.spend` justification gate and the spend ledger all live there. DeepSeek is
the only provider used. The run tracks cost after every call and STOPS at the
cap; the DeepSeek balance is read before and after, because the provider's
balance is the economic truth and our telemetry has been wrong before.

LICENCE: PRODUCT_EXPERIMENT. Rank-only, no return labels, nothing sealed.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from alpha import config as CONFIG                               # noqa: E402
from alpha import transpose as TP                                # noqa: E402
from alpha.council import providers as PROV                      # noqa: E402

# `alpha.config.load_env` is how every other script in this repo gets a key --
# there is no dotenv dependency. It is called inside `run()` rather than at
# import time so that IMPORTING this module for a test does not pull keys into
# the process. It never overwrites an explicit export.

OUT_DIR = REPO / "state" / "labor_day_lab_2026-09-07"
RECEIPT = OUT_DIR / "B2_fantasy_exams.json"

PROVIDER = "deepseek"
ERA = "2051-01"
SEED = 20260907

#: DeepSeek per-million-token prices, DERIVED from the provider's own balance on
#: 2026-09-05 and pinned in the finance repo at `backend/config.LLM_PRICE_PER_MTOK`
#: (receipt: backend/data/optimus/continuation_2026-09-06b/
#: C3_deepseek_price_derivation_run01.json). Copied rather than imported: the two
#: repos do not share a path, and a cross-repo import that silently fails would
#: leave this script pricing at zero.
PRICE_IN_PER_MTOK = 0.169413
PRICE_OUT_PER_MTOK = 1.284835

#: A canary pair whose forecast moves more than this has manufactured a view out
#: of a fact that cannot matter.
CANARY_TOLERANCE = 0.05

N_PAIRS = 40
N_CANARIES = 8

WHY_THIS_CALL_CAN_CHANGE_A_DECISION = (
    "Decides whether the LLM decider may be given any role in ranking names at "
    "all: if its p_up does not move the economically correct way when one causal "
    "fact flips in an otherwise identical fictional brief, we refuse to let it "
    "rank or size anything and the ranking stays numerical. A high monotonicity "
    "share with a low canary rate promotes it to a scored arm in the entry "
    "tournament; a low share kills that lane this week."
)

_SYSTEM = (
    "You are a securities analyst. You are given a brief about one company and "
    "you must state a short-horizon view. Think about the mechanism: what the "
    "described fact does to revenue, costs, financing and risk over the next "
    "month. Answer with one JSON object and nothing else, with these keys: "
    "p_up_21d (a probability that the stock is higher in 21 trading sessions), "
    "exp_return (the expected return over those 21 sessions, as a decimal "
    "fraction, negative for a loss), downside_5pct (the return at the 5th "
    "percentile of your outcome distribution, as a decimal fraction), "
    "confidence (how much you trust your own estimate, as a fraction), and "
    "reason (one sentence)."
)


# ───────────────────────────────────────────────────────── the exam material


#: Each family: (name, the fact in its GOOD version, the fact in its BAD version,
#: which way p_up must move: +1 means GOOD > BAD).
FAMILIES: tuple[tuple[str, str, str], ...] = (
    ("fda",
     "the regulator APPROVED the company's lead product for marketing, with no "
     "restrictions beyond the label the company had requested",
     "the regulator REJECTED the company's lead product and asked for a new "
     "trial before it will look at the file again"),
    ("sanction",
     "the export sanctions that had covered the company's largest end market "
     "were LIFTED this week and shipments may resume immediately",
     "new export sanctions were IMPOSED this week covering the company's "
     "largest end market and shipments must stop immediately"),
    ("funding",
     "the company's lead lender EXTENDED the revolving facility by three years "
     "on unchanged terms",
     "the company's lead lender WITHDREW the revolving facility and it must be "
     "repaid within ninety days"),
    ("supply",
     "the single-source component that had been rationed is now in FULL SUPPLY "
     "and the supplier has doubled the company's allocation",
     "the single-source component the company depends on has been CUT OFF and "
     "the supplier has halved the company's allocation"),
    ("guidance",
     "management RAISED full-year guidance at this week's update",
     "management CUT full-year guidance at this week's update"),
    ("customer",
     "the company WON the renewal of its largest customer contract on improved "
     "terms",
     "the company LOST its largest customer contract to a competitor"),
)

#: Facts that cannot move a share price a month out. The canary asks whether the
#: decider moves anyway.
IRRELEVANT: tuple[tuple[str, str], ...] = (
    ("the company moved its twelve-person investor-relations office to a "
     "different floor of the same building",
     "the company kept its twelve-person investor-relations office on the "
     "floor it has always occupied"),
    ("the company refreshed its corporate logo and its typeface",
     "the company left its corporate logo and its typeface unchanged"),
    ("the company's auditor opened a second office in a different city, "
     "unrelated to this engagement",
     "the company's auditor kept its single office, unrelated to this "
     "engagement"),
    ("the company renamed its internal engineering intranet",
     "the company left the name of its internal engineering intranet alone"),
)


def _fmt(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}"


def build_exam(n_pairs: int = N_PAIRS, n_canaries: int = N_CANARIES,
               seed: int = SEED) -> tuple[list[dict], dict]:
    """Build the pairs in CODE from a sealed entity map. No LLM is used to write
    a brief: the rewriter's job here is naming, and a model that writes its own
    exam can write an easy one."""
    rng = random.Random(seed)
    symbols = [f"X{i:03d}" for i in range(n_pairs + n_canaries)]
    sectors = [f"SEC{i % 9}" for i in range(n_pairs + n_canaries)]
    emap = TP.build_entity_map(symbols, sectors, era=ERA, seed="aegis-labor-b2")
    names = emap["companies"]
    inds = emap["industries"]

    items: list[dict] = []
    for i in range(n_pairs + n_canaries):
        sym = symbols[i]
        is_canary = i >= n_pairs
        company = names[sym]
        industry = inds[sectors[i]]
        rev = round(rng.uniform(180.0, 4200.0), 1)
        growth = round(rng.uniform(-14.0, 31.0), 1)
        margin = round(rng.uniform(-9.0, 34.0), 1)
        cash = round(rng.uniform(20.0, 1800.0), 1)
        debt = round(rng.uniform(0.0, 2600.0), 1)
        cover = rng.randint(2, 19)
        upside = round(rng.uniform(-12.0, 68.0), 1)
        vol = round(rng.uniform(26.0, 88.0), 1)
        dd = round(rng.uniform(-62.0, -4.0), 1)
        base = (
            f"{company} is a listed company in the {industry} industry. "
            f"Trailing twelve-month revenue is ${_fmt(rev)}m, growing "
            f"{_fmt(growth)}% year on year, at a {_fmt(margin)}% operating "
            f"margin. It holds ${_fmt(cash)}m of cash against ${_fmt(debt)}m of "
            f"debt. {cover} analysts cover it and the consensus price target "
            f"implies {_fmt(upside)}% upside. Realised volatility is "
            f"{_fmt(vol)}% annualised and the shares are {_fmt(dd)}% below "
            f"their fifty-two-week high."
        )
        if is_canary:
            fam, good, bad = ("canary_irrelevant",
                              *IRRELEVANT[(i - n_pairs) % len(IRRELEVANT)])
        else:
            fam, good, bad = FAMILIES[i % len(FAMILIES)]
        items.append({
            "pair_id": f"{'CANARY' if is_canary else 'PAIR'}-{i:03d}",
            "family": fam, "is_canary": is_canary,
            "company": company, "industry": industry, "symbol_key": sym,
            "brief_good": base + " This week, " + good + ".",
            "brief_bad": base + " This week, " + bad + ".",
            # Which leg is asked FIRST, so leg order cannot confound the sign.
            "good_first": bool(rng.random() < 0.5),
        })
    meta = {
        "entity_map_sha256": emap["sha256"], "era": ERA,
        "n_pairs": n_pairs, "n_canaries": n_canaries, "seed": seed,
        "map_note": ("names come from alpha.transpose.build_entity_map — sealed, "
                     "deterministic, never shown to the model"),
        "brief_note": ("briefs are written in CODE from a template. A model that "
                       "writes its own exam writes an easy one."),
    }
    return items, meta


# ─────────────────────────────────────────────────────────────── the decider


def _num(obj: dict, key: str) -> float | None:
    v = obj.get(key)
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def stub_decider(brief: str) -> tuple[dict, dict]:
    """A $0 decider used by --dry-run and by the smoke test. It reads ONE word
    out of the brief, which is enough to prove the grading arithmetic — and not
    enough to be mistaken for a model."""
    good_words = ("APPROVED", "LIFTED", "EXTENDED", "FULL SUPPLY", "RAISED",
                  "WON")
    bad_words = ("REJECTED", "IMPOSED", "WITHDREW", "CUT OFF", "CUT ", "LOST")
    p = 0.50
    if any(w in brief for w in good_words):
        p = 0.68
    elif any(w in brief for w in bad_words):
        p = 0.31
    return ({"p_up_21d": p, "exp_return": (p - 0.5) * 0.2,
             "downside_5pct": -0.20 + (p - 0.5) * 0.1,
             "confidence": 0.5, "reason": "stub"},
            {"provider": "stub", "model": "stub", "prompt_tokens": 0,
             "completion_tokens": 0, "latency_s": 0.0})


def ask(brief: str, caller: str) -> tuple[dict, dict]:
    return PROV.chat_json(PROVIDER, _SYSTEM, brief, caller=caller,
                          why=WHY_THIS_CALL_CAN_CHANGE_A_DECISION,
                          max_tokens=400, temperature=0.1)


def call_cost_usd(meta: dict) -> float:
    pt = float(meta.get("prompt_tokens") or 0)
    ct = float(meta.get("completion_tokens") or 0)
    return (pt * PRICE_IN_PER_MTOK + ct * PRICE_OUT_PER_MTOK) / 1_000_000.0


# ─────────────────────────────────────────────────────────────── the grading


def grade_pair(item: dict, good: dict, bad: dict) -> dict:
    """Did the forecast move the economically correct way? GOOD must sit above
    BAD on p_up and exp_return, and its downside must be no worse."""
    g_p, b_p = _num(good, "p_up_21d"), _num(bad, "p_up_21d")
    g_r, b_r = _num(good, "exp_return"), _num(bad, "exp_return")
    g_d, b_d = _num(good, "downside_5pct"), _num(bad, "downside_5pct")
    out = {
        "pair_id": item["pair_id"], "family": item["family"],
        "is_canary": item["is_canary"],
        "p_up_good": g_p, "p_up_bad": b_p,
        "d_p_up": (round(g_p - b_p, 6) if g_p is not None and b_p is not None
                   else None),
        "d_exp_return": (round(g_r - b_r, 6) if g_r is not None and b_r is not None
                         else None),
        "d_downside": (round(g_d - b_d, 6) if g_d is not None and b_d is not None
                       else None),
    }
    out["p_up_moves_correctly"] = (None if out["d_p_up"] is None
                                   else bool(out["d_p_up"] > 0))
    out["exp_return_moves_correctly"] = (None if out["d_exp_return"] is None
                                         else bool(out["d_exp_return"] > 0))
    out["downside_moves_correctly"] = (None if out["d_downside"] is None
                                       else bool(out["d_downside"] >= 0))
    out["all_three_agree"] = bool(
        out["p_up_moves_correctly"] and out["exp_return_moves_correctly"]
        and out["downside_moves_correctly"])
    if item["is_canary"]:
        out["canary_moved"] = (None if out["d_p_up"] is None
                               else bool(abs(out["d_p_up"]) > CANARY_TOLERANCE))
    return out


def summarise(rows: list[dict]) -> dict:
    real = [r for r in rows if not r["is_canary"] and r["d_p_up"] is not None]
    can = [r for r in rows if r["is_canary"] and r["d_p_up"] is not None]

    def _share(xs, key):
        v = [r[key] for r in xs if r[key] is not None]
        return (round(sum(1 for x in v if x) / len(v), 4), len(v)) if v else (None, 0)

    p_share, p_n = _share(real, "p_up_moves_correctly")
    r_share, r_n = _share(real, "exp_return_moves_correctly")
    d_share, d_n = _share(real, "downside_moves_correctly")
    a_share, a_n = _share(real, "all_three_agree")
    mags = [abs(r["d_p_up"]) for r in real]
    signed = [r["d_p_up"] for r in real]
    rmags = [abs(r["d_exp_return"]) for r in real
             if r["d_exp_return"] is not None]
    canary_moved = [r["canary_moved"] for r in can if r.get("canary_moved") is not None]
    by_family: dict[str, dict] = {}
    for r in real:
        b = by_family.setdefault(r["family"], {"n": 0, "correct": 0,
                                               "mean_abs_d_p_up": 0.0})
        b["n"] += 1
        b["correct"] += 1 if r["p_up_moves_correctly"] else 0
        b["mean_abs_d_p_up"] += abs(r["d_p_up"])
    for b in by_family.values():
        b["share_correct"] = round(b["correct"] / b["n"], 4)
        b["mean_abs_d_p_up"] = round(b["mean_abs_d_p_up"] / b["n"], 4)
    return {
        "pairs_graded": len(real),
        "monotonicity_share_p_up": p_share,
        "monotonicity_share_exp_return": r_share,
        "monotonicity_share_downside": d_share,
        "share_all_three_agree": a_share,
        "mean_abs_move_p_up": round(sum(mags) / len(mags), 4) if mags else None,
        "mean_signed_move_p_up": (round(sum(signed) / len(signed), 4)
                                  if signed else None),
        "mean_abs_move_exp_return": (round(sum(rmags) / len(rmags), 4)
                                     if rmags else None),
        "canaries_graded": len(canary_moved),
        "canary_rate": (round(sum(1 for x in canary_moved if x) / len(canary_moved), 4)
                        if canary_moved else None),
        "canary_tolerance": CANARY_TOLERANCE,
        "canary_reading": (
            "the share of causally IRRELEVANT pairs on which the forecast still "
            f"moved more than {CANARY_TOLERANCE} of probability. It is the rate "
            "at which the decider manufactures a view out of nothing, and it is "
            "what says whether a high monotonicity share means anything."),
        "by_family": by_family,
        "counts_note": {"p_up": p_n, "exp_return": r_n, "downside": d_n,
                        "all_three": a_n},
    }


# ────────────────────────────────────────────────────────────────── the run


def deepseek_balance() -> dict | None:
    """The provider's own balance — the economic truth. Read-only, unpaid."""
    key = os.getenv("AAT_DEEPSEEK_API_KEY", "").strip()
    if not key:
        return None
    try:
        req = urllib.request.Request(
            "https://api.deepseek.com/user/balance",
            headers={"Authorization": f"Bearer {key}",
                     "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:                                     # noqa: BLE001
        return {"error": f"{type(e).__name__}: {str(e)[:160]}"}


def _balance_usd(b: dict | None) -> float | None:
    if not isinstance(b, dict):
        return None
    infos = b.get("balance_infos") or []
    for i in infos:
        if str(i.get("currency", "")).upper() == "USD":
            try:
                return float(i.get("total_balance"))
            except (TypeError, ValueError):
                return None
    return None


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                              capture_output=True, text=True,
                              timeout=20).stdout.strip() or None
    except Exception:                                          # noqa: BLE001
        return None


def run(n_pairs: int, n_canaries: int, cap_usd: float, dry_run: bool,
        seed: int = SEED) -> dict:
    if not dry_run:
        CONFIG.load_env()
    items, meta = build_exam(n_pairs, n_canaries, seed)
    bal_before = None if dry_run else deepseek_balance()
    rows, calls, spend, refusals = [], [], 0.0, []
    stopped_at = None

    for it in items:
        legs = [("good", it["brief_good"]), ("bad", it["brief_bad"])]
        if not it["good_first"]:
            legs.reverse()
        answers: dict[str, dict] = {}
        aborted = False
        for leg, brief in legs:
            if not dry_run and spend >= cap_usd:
                stopped_at = it["pair_id"]
                aborted = True
                break
            t0 = time.time()
            try:
                if dry_run:
                    obj, m = stub_decider(brief)
                else:
                    obj, m = ask(brief, caller="labor_b2.fantasy_exam")
            except Exception as e:                             # noqa: BLE001
                refusals.append({"pair_id": it["pair_id"], "leg": leg,
                                 "error": f"{type(e).__name__}: {str(e)[:200]}"})
                aborted = True
                break
            c = 0.0 if dry_run else call_cost_usd(m)
            spend += c
            calls.append({"pair_id": it["pair_id"], "leg": leg,
                          "prompt_tokens": m.get("prompt_tokens"),
                          "completion_tokens": m.get("completion_tokens"),
                          "latency_s": round(time.time() - t0, 2),
                          "usd": round(c, 6), "model": m.get("model")})
            answers[leg] = obj
        if stopped_at:
            break
        if aborted or "good" not in answers or "bad" not in answers:
            continue
        g = grade_pair(it, answers["good"], answers["bad"])
        g["reason_good"] = str(answers["good"].get("reason", ""))[:220]
        g["reason_bad"] = str(answers["bad"].get("reason", ""))[:220]
        rows.append(g)

    bal_after = None if dry_run else deepseek_balance()
    b0, b1 = _balance_usd(bal_before), _balance_usd(bal_after)
    summary = summarise(rows)
    return {
        "item": "LABOR_DAY_LAB_2026-09-07 / lane B / B2",
        "title": "fantasy stress exams — monotonicity under one flipped fact",
        "licence": "PRODUCT_EXPERIMENT",
        "mode": "RANK_ONLY — no return labels exist for this exam",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "argv": list(sys.argv), "git_commit": _git_commit(),
        "python": sys.version.split()[0],
        "dry_run": dry_run,
        "config": {"provider": PROVIDER,
                   "model": PROV.PROVIDERS[PROVIDER].model,
                   "n_pairs": n_pairs, "n_canaries": n_canaries,
                   "cap_usd": cap_usd, "seed": seed,
                   "max_tokens": 400, "temperature": 0.1,
                   "canary_tolerance": CANARY_TOLERANCE},
        "exam": meta,
        "why_this_call_can_change_a_decision": WHY_THIS_CALL_CAN_CHANGE_A_DECISION,
        "prompt_carries_no_numeric_bound": (
            "S28: a bound stated IN THE PROMPT is an anchor — 11 of 13 answers "
            "came back at exactly the bound. The system prompt names units and "
            "no limits."),
        "system_prompt": _SYSTEM,
        "summary": summary,
        "pairs": rows,
        "refusals": refusals,
        "stopped_at_pair": stopped_at,
        "spend": {
            "calls": len(calls),
            "usd_from_tokens": round(spend, 6),
            # Rounded UP, and named so. "$0.01" for a run that cost $0.0148
            # understates it, and a spend figure that rounds a run down is the
            # wrong direction for a cap to be wrong in.
            "usd_rounded_up_to_the_cent": (math.ceil(spend * 100.0) / 100.0
                                           if spend else 0.00),
            "cap_usd": cap_usd,
            "price_per_mtok": {"in": PRICE_IN_PER_MTOK,
                               "out": PRICE_OUT_PER_MTOK,
                               "source": ("aegis-finance backend/config."
                                          "LLM_PRICE_PER_MTOK, derived from the "
                                          "provider balance 2026-09-05")},
            "prompt_tokens": sum(int(c["prompt_tokens"] or 0) for c in calls),
            "completion_tokens": sum(int(c["completion_tokens"] or 0) for c in calls),
            "balance_usd_before": b0, "balance_usd_after": b1,
            "balance_delta_usd": (round(b0 - b1, 4)
                                  if b0 is not None and b1 is not None else None),
            "balance_note": ("the provider's balance is the economic truth; the "
                             "token figure is OUR telemetry and has disagreed "
                             "before"),
        },
        "calls": calls,
    }


def write_receipt(receipt: dict, path: Path = RECEIPT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="labor_b2_fantasy_exams")
    ap.add_argument("--dry-run", action="store_true",
                    help="$0.00: a stubbed decider, to check the arithmetic")
    ap.add_argument("--pairs", type=int, default=N_PAIRS)
    ap.add_argument("--canaries", type=int, default=N_CANARIES)
    ap.add_argument("--cap", type=float, default=5.00)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    path = Path(a.out) if a.out else (
        RECEIPT.with_name("B2_fantasy_exams_dryrun.json") if a.dry_run
        else RECEIPT)
    try:
        rec = run(a.pairs, a.canaries, a.cap, a.dry_run)
    except BaseException as e:                                 # noqa: BLE001
        import traceback
        write_receipt({"item": "LABOR_DAY_LAB_2026-09-07 / lane B / B2",
                       "status": "FAILED", "dry_run": a.dry_run,
                       "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                       "argv": list(sys.argv), "git_commit": _git_commit(),
                       "error": f"{type(e).__name__}: {e}",
                       "traceback": traceback.format_exc(),
                       "note": "a traceback is a receipt"}, path)
        print(f"FAILED — receipt written to {path}")
        raise
    write_receipt(rec, path)
    s = rec["summary"]
    print(f"\npairs graded          {s['pairs_graded']}")
    print(f"monotonicity (p_up)   {s['monotonicity_share_p_up']}")
    print(f"monotonicity (exp_r)  {s['monotonicity_share_exp_return']}")
    print(f"all three agree       {s['share_all_three_agree']}")
    print(f"mean |d p_up|         {s['mean_abs_move_p_up']}")
    print(f"canary rate           {s['canary_rate']} of {s['canaries_graded']}")
    print(f"spend                 ${rec['spend']['usd_from_tokens']:.6f} "
          f"({rec['spend']['calls']} calls, cap ${rec['spend']['cap_usd']:.2f})")
    print(f"[receipt] -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
