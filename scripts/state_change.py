"""Shadow-only loser triage and state-change scoring (review P4/P5).

    python -m scripts.state_change triage --evidence state/psychohistory_evidence/DKS_2026-08-26.json --day0-move -0.367
    python -m scripts.state_change sco    --evidence state/state_change_evidence/SLDP.json --graph hardware --price 2.34 --resolve-by 2027-02-26
    python -m scripts.state_change show
    python -m scripts.state_change grade  --id SC:TRIAGE:...  --move 0.05      # realised move from day-0 close

`triage` reuses the Psychohistory evidence files (facts with sources). The
ticker is hidden from the compiler. Nothing here orders.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from alpha import config, state_change as sc


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("triage")
    t.add_argument("--evidence", required=True)
    t.add_argument("--day0-move", type=float, required=True, help="signed log move across day 0")
    t.add_argument("--sessions", type=int, default=21)
    s = sub.add_parser("sco")
    s.add_argument("--evidence", required=True)
    s.add_argument("--graph", required=True, choices=sorted(sc.STATE_GRAPHS))
    s.add_argument("--price", type=float, required=True)
    s.add_argument("--resolve-by", required=True)
    sub.add_parser("show")
    g = sub.add_parser("grade")
    g.add_argument("--id", required=True)
    g.add_argument("--move", type=float, required=True, help="realised log move from the record's price/day-0 close")
    args = p.parse_args()
    config.load_env()

    if args.cmd in ("triage", "sco"):
        bundle = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
        symbol = bundle["trigger"]["symbol"] if "trigger" in bundle else bundle["symbol"]
        facts = bundle["evidence"]
        if args.cmd == "triage":
            row = sc.triage_loser(symbol, facts, day0_move=args.day0_move,
                                  day0_date=bundle.get("horizon", {}).get("day0") or bundle.get("day0"),
                                  market_context=bundle.get("market_expectation") or {}, resolve_sessions=args.sessions)
            c = row["compiled"]
            print(f"{row['id']}  {c['classification']}  p_overreaction {c['p_overreaction']}  damage {c.get('fundamental_damage_pct')}  "
                  f"reaction_ratio {c.get('reaction_ratio')}  conf {c.get('confidence')}  ${row['llm']['cost_usd']}")
            print(f"   why: {c.get('reasoning')}")
            print(f"   falsifier: {c.get('falsifier_21_sessions')}")
        else:
            row = sc.score_state_change(symbol, facts, graph_key=args.graph, current_price=args.price, resolve_by=args.resolve_by)
            c, k = row["compiled"], row["components"]
            print(f"{row['id']}  {c['current_state']} -> {c['next_state']}  p12m {c.get('p_transition_12m')} (prior {c.get('p_transition_base_rate_used')})  "
                  f"up {c.get('value_if_transition')} / dn {c.get('value_if_fail')}  months {c.get('time_to_resolution_months')}  "
                  f"dilution {c.get('p_dilution_before_resolution')}  priced_in {c.get('already_priced_in')}")
            print(f"   SCO {k.get('sco')}  edge {k.get('edge_vs_price')}  convexity_yield {k.get('convexity_yield')}  ({k.get('reason','')})")
            print(f"   falsifier: {c.get('falsifier')}")
        return 0
    if args.cmd == "show":
        for r in sc.read_all():
            c = r["compiled"]
            head = c.get("classification") or f"{c.get('current_state')}->{c.get('next_state')}"
            print(f"{r['id']:48s} {head:22s} resolved={bool(r.get('resolved'))}")
        return 0
    rows = sc.read_all()
    hit = [r for r in rows if r["id"] == args.id]
    if not hit:
        print("no such id")
        return 1
    r = hit[0]
    c = r["compiled"]
    if r["kind"] == "loser_triage":
        # PRICE_OVERREACTION predicts a move back UP; THESIS_BROKEN predicts further DOWN
        pred_up = c["p_overreaction"]
        realised_up = 1.0 if args.move > 0 else 0.0
        brier = (pred_up - realised_up) ** 2
        verdict = {"realised_move": args.move, "brier_vs_direction": round(brier, 4),
                   "classification_right": (c["classification"] == "PRICE_OVERREACTION") == (args.move > 0)}
    else:
        verdict = {"realised_move": args.move}
    r["resolved"] = verdict
    sc.STORE.write_text("\n".join(json.dumps(x) for x in rows) + "\n", encoding="utf-8")
    print(json.dumps(verdict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
