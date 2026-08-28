"""AEGIS_RESEARCH_COUNCIL_v1 -- specialists with non-overlapping jobs. Places nothing.

    AAT_ACCOUNT_ROLE=staging python -m scripts.council --probe
    AAT_ACCOUNT_ROLE=staging python -m scripts.council --symbols S WDAY MRVL
    AAT_ACCOUNT_ROLE=staging python -m scripts.council --symbols S --role skeptic=nvidia_minimax

Output: `state/council/<date>/<SYM>.json` and a table. Read `alpha/council/roles.py`
for what each role may and may not do; the SURPRISE CUBE is code, not a model.
"""

from __future__ import annotations

import argparse
import json

from alpha import config
from alpha.broker.alpaca import AlpacaPaper
from alpha.council import providers, run


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=[])
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--role", action="append", default=[], help="role=provider override, e.g. skeptic=nvidia_minimax")
    ap.add_argument("--implied-move", type=float, default=None, help="option-implied move for the print, if known")
    args = ap.parse_args()
    config.load_env()

    live = providers.probe()
    print(f"{'provider':<16}{'state':<7}{'s':>6}  family/model")
    for k, v in live.items():
        print(f"{k:<16}{v.get('state'):<7}{v.get('latency_s', ''):>6}  {providers.PROVIDERS[k].family}/{providers.PROVIDERS[k].model}"
              + (f"  ({v.get('why', '')[:60]})" if v.get("state") != "live" else ""))
    overrides = dict(x.split("=", 1) for x in args.role)
    who = run.assign(live, overrides)
    print("\nroles:", json.dumps(who))
    if args.probe or not args.symbols:
        return 0

    client = AlpacaPaper()
    print(f"\n{'sym':<6}{'AH':>8}{'cells':>6}{'incomp':>7}  {'dir':<5}{'mag':>6}{'p_priced':>9}  families  falsifier")
    for s in args.symbols:
        pk = run.council(client, s, live=live, overrides=overrides, implied_move=args.implied_move)
        path = run.write(pk)
        cube = pk["steps"].get("surprise_cube", {})
        syn = pk["steps"].get("synthesis", {})
        sk = pk["steps"].get("skeptic", {})
        ah = pk["steps"].get("scout", {}).get("ah_move")
        print(f"{pk['symbol']:<6}{('n/a' if ah is None else f'{ah:+.1%}'):>8}{cube.get('n_cells', 0):>6}{cube.get('n_incomparable', 0):>7}  "
              f"{str(syn.get('direction', pk.get('verdict')))[:4]:<5}{float(syn.get('magnitude') or 0):>6.1%}"
              f"{float(sk.get('p_already_priced') or 0):>9.2f}  {','.join(pk.get('families_used', []))}"
              f"{'' if pk.get('skeptic_independent') else ' [skeptic NOT independent]'}  {str(syn.get('falsifier', ''))[:70]}")
        for c in cube.get("cells", [])[:8]:
            print(f"        {c['axis']:<22}{c['metric']:<22}{c['period']:<8}{c['relative'] if c['relative'] is not None else '?':>8}  {c['fact_quote'][:60]}")
        for inc in cube.get("incomparable", [])[:4]:
            print(f"        INCOMPARABLE {inc['axis']:<22}{str(inc['metric']):<40} {inc['why'][:60]}")
        for r in pk.get("refusals", []):
            print(f"        refused {r['step']}: {r['why'][:90]}")
        print(f"        -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
