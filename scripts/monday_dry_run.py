"""MONDAY DRY RUN -- what the tracker books would admit, and what stops the rest.

    python -m scripts.monday_dry_run                     # hygiene-only (decision B.1 4a)
    python -m scripts.monday_dry_run --compare           # both band modes, side by side
    python -m scripts.monday_dry_run --day 2026-09-02    # a named vintage

WHAT THIS IS FOR (B3, 2026-09-05)
=================================
Monday morning has to hold no surprises. This prints, for hack3 / hack4 / hack6:

  * the names ADMITTED per book;
  * the BINDING constraint per book -- `fails_only`, not the first-fired reason.
    The chain short-circuits, so `excluded_by_reason` names the earliest rule a
    name failed and NOT the rule whose removal would buy anything. On the
    2026-09-01 seal the first-fired report said "hack6: 541 names above the 20%
    downside cap"; dropping that rule alone yields 23 names, and dropping the
    coherence floor alone yields 151. A reason count from a short-circuiting
    chain is an ORDER, not a ranking of what binds;
  * the CONTRACT FIELDS on every holding, from `alpha/contract.py` -- horizon,
    minimum hold, thesis expiry, falsifiers, risk budget, emergency reasons;
  * ARMED / DISARMED per book with its binding disarm, from the same
    `scripts.utilization.entry_authority` the daily report uses, so the two
    pages cannot disagree.

IT IS A REPLAY, AND IT SAYS SO
==============================
It seals NOTHING to `state/predictions/`: `--out` defaults to a temporary
directory, so no artefact this produces can be picked up by a loop, a sync or
`--publish`. And it evaluates the vintage's freshness AS OF THE VINTAGE'S OWN
DAY (`tracker_rows(day, asof=day)`), because the question a replay asks is "was
this file fresh when it was written", not "is it fresh now". A LIVE seal passes
no `asof` and is still measured against today -- pricing Monday's book on
Friday's closes remains a refusal.

Places nothing. Submits nothing. Writes only under `--out`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: The books this prints. hack1/2/5 do not trade the sealed tracker portfolio.
BOOKS = ("hack3", "hack4", "hack6")


def _rows_for(day: str) -> tuple[list[dict], dict, list[dict]]:
    from scripts.prediction_book import tracker_rows
    return tracker_rows(day, asof=day)


def build_books(day: str) -> dict:
    """Every book's portfolio for `day`, through the SAME functions the seal
    uses -- `murat_rule.score` for the numbers, `tracker.build_portfolio` for
    the selection. A dry run that re-implemented either would be measuring a
    different book."""
    from alpha import drivers, murat_rule
    from alpha import tracker as _tracker
    from scripts.prediction_book import rule_predictions, rule_prior

    rows, prov, cands = _rows_for(day)
    prior = rule_prior()
    driver_of, _note = drivers.resolve([r["symbol"] for r in rows])
    preds = rule_predictions(rows, prior, driver_of)
    by_sym = {p["symbol"]: p for p in preds}
    # The personalities rank on the RULE's numbers, exactly as `_build_from_tracker`
    # carries them back before building the books. Without this every ratio
    # ranking sees None and the book is empty through a code path that looks full.
    for c in cands:
        p = by_sym.get(c["symbol"])
        if not p:
            continue
        for k in ("exp_return", "downside_5pct", "confidence", "p_up_21d",
                  "hygiene_ok", "hygiene_fails", "hygiene_unreadable", "band_mode",
                  "upside_band"):
            if k in p:
                c[k] = p.get(k)
    out = {}
    for pers in _tracker.PERSONALITIES:
        out[pers.book] = {"personality": pers, "port": _tracker.build_portfolio(cands, pers)}
    return {"day": day, "provenance": prov, "n_candidates": len(cands),
            "band_mode": murat_rule.band_mode(), "books": out,
            "n_hygiene_fail": sum(1 for c in cands if c.get("hygiene_ok") is False)}


def binding(port: dict) -> list[tuple[str, int, int]]:
    """`[(rule, fails, fails_only)]` sorted by what dropping the rule ALONE buys.

    `fails_only` is the number of names that fail ONLY this rule -- i.e. the
    names that become eligible if it alone is relaxed, every other rule kept.
    That is the price of the rule in opportunities. A rule with a large `fails`
    and a zero `fails_only` is REDUNDANT, not binding.
    """
    m = port.get("excluded_marginal") or {}
    fails, only = m.get("fails") or {}, m.get("fails_only") or {}
    keys = sorted(set(fails) | set(only))
    return sorted(((k, int(fails.get(k, 0)), int(only.get(k, 0))) for k in keys),
                  key=lambda t: (-t[2], -t[1]))


#: The equity every dollar figure below is computed at. FROZEN, and stated: the
#: genesis file's `starting_equity` for all six accounts is $100,000, and using a
#: live balance would make a printout nobody could reproduce tomorrow.
ASSUMED_EQUITY_USD = 100_000.0


def profile_for(book: str) -> str | None:
    """The RISK PROFILE the fleet declares for this role -- which is where the
    stop width comes from. `Personality` has no profile field: the book decides
    selection, the mandate decides risk, and reading the stop off the wrong one
    is how `exits.py` charged a flat 3% while `protect.py` placed 8%."""
    from alpha import fleet
    m = fleet.FLEET.get(book)
    return m.profile if m else None


def contract_for(book: str, day: str, notional_frac: float | None,
                 stop_frac: float, *, profile: str | None = None) -> dict:
    """The contract a holding of this book would carry.

    `notional_frac` is a FRACTION OF EQUITY (`Personality.max_notional`), not
    dollars -- `build_portfolio` writes 0.10, meaning 10% of the book. Treating
    it as $0.10 is how the risk budget printed as $1.00 in the first draft of
    this script, which is the units error this repo keeps paying for.
    """
    from alpha import contract as _contract
    risk = round(float(notional_frac or 0.0) * ASSUMED_EQUITY_USD * stop_frac, 2)
    return _contract.for_book(book, day=day, profile=profile,
                              risk_budget_usd=risk if risk > 0 else 1.0).as_dict()


def render(built: dict, *, day: str) -> str:
    from alpha import contract as _contract
    from alpha.engine import equity as _equity

    L: list[str] = []
    L.append("=" * 78)
    L.append(f"MONDAY DRY RUN -- tracker vintage {built['day']}   band mode: "
             f"{built['band_mode'].upper()}")
    L.append(f"generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}Z  "
             f"REPLAY: nothing sealed, nothing ordered, nothing published")
    L.append("=" * 78)
    prov = built["provenance"]
    L.append(f"universe: {prov.get('tracker_names_total')} names screened -> "
             f"{built['n_candidates']} candidates"
             + (f"   ({built['n_hygiene_fail']} fail hygiene: >= $2, >= 2 analysts, "
                f"target window readable)" if built["band_mode"] == "hygiene_only" else ""))
    gaps = prov.get("data_gaps") or {}
    L.append(f"data gaps on the vintage: rec_status not ok "
             f"{gaps.get('rows_rec_status_not_ok')}, target_status not ok "
             f"{gaps.get('rows_target_status_not_ok')}")

    for book in BOOKS:
        b = built["books"].get(book)
        if b is None:
            L.append(f"\n{book}: NOT A TRACKER BOOK in alpha/tracker.PERSONALITIES")
            continue
        pers, port = b["personality"], b["port"]
        holdings = port.get("holdings") or []
        L.append("")
        L.append("-" * 78)
        L.append(f"{book.upper()}   personality={pers.book}  k={pers.k}  rank={pers.rank}  "
                 f"exclude_past_winners={pers.exclude_past_winners}")
        L.append(f"  pool {port.get('candidate_pool')} -> eligible {port.get('eligible')} "
                 f"-> ADMITTED {len(holdings)}")
        if holdings:
            L.append("  names: " + ", ".join(str(h.get("symbol")) for h in holdings))
        else:
            L.append("  names: NONE")

        rows = binding(port)
        if not rows:
            L.append("  BINDING: no eligibility rule fired (nothing to attribute)")
        else:
            top = rows[0]
            if top[2] == 0:
                L.append("  BINDING: NO SINGLE RULE. Every excluded name fails at least two "
                         "rules, so relaxing any ONE of them admits nobody. This is a "
                         "CONJUNCTION, and reading the largest `fails` as 'the' constraint "
                         "would be the short-circuit error one level up.")
            else:
                L.append(f"  BINDING: {top[0]}  -- dropping it ALONE admits {top[2]} name(s)")
            L.append(f"    {'rule':<62}{'fails':>7}{'only':>7}")
            for k, f, o in rows[:8]:
                L.append(f"    {k[:61]:<62}{f:>7}{o:>7}")
            L.append("    (`fails` counts names failing the rule at all; `only` counts names "
                     "failing NOTHING ELSE -- the ones a relaxation would actually buy)")

        # ---- the contract every holding would carry -----------------------
        prof = profile_for(book)
        stop = _equity.stop_fraction(prof)
        notional_frac = pers.max_notional
        c = contract_for(book, day, notional_frac, stop, profile=prof)
        gross = min(len(holdings) * notional_frac, 1.0e9)
        L.append(f"  SIZE: {notional_frac:.0%} of equity per name x {len(holdings)} name(s) "
                 f"= {gross:.0%} gross;  stop {stop:.1%} (profile '{prof}')")
        L.append(f"    worst case if every name gaps to its stop the same day: "
                 f"{gross * stop:.2%} of equity = "
                 f"${gross * stop * ASSUMED_EQUITY_USD:,.0f} on ${ASSUMED_EQUITY_USD:,.0f}")
        L.append("  CONTRACT on every holding (alpha/contract.py):")
        for f in _contract.REQUIRED_FIELDS:
            v = c.get(f)
            if isinstance(v, (list, tuple)):
                L.append(f"    {f:<28}{len(v)} item(s)")
                for item in v:
                    L.append(f"      - {item}")
            else:
                L.append(f"    {f:<28}{v}")
        L.append(f"    {'profit_target_frac':<28}{c.get('profit_target_frac')}"
                 f"   (None = no profit target; a +2.5% target on a 21-session thesis "
                 f"collects a day of noise)")
        L.append(f"    {'stop_fraction (profile)':<28}{stop:.1%}")
        L.append(f"    {'min_edge_over_stop':<28}{c.get('min_edge_over_stop')}"
                 f"   (None = MEASURED AND RECORDED, NOT ENFORCED)")
        missing = [h.get("symbol") for h in holdings
                   if any(h.get(f) is None for f in _contract.REQUIRED_FIELDS)]
        L.append(f"    stamped on all {len(holdings)} holding(s) at seal time: "
                 + ("no -- the seal REFUSES a book whose holdings are unstamped; "
                    f"this replay did not stamp {len(missing)}" if missing
                    else "yes"))
    return "\n".join(L)


def authority_block() -> str:
    from scripts.utilization import entry_authority

    L = ["", "-" * 78, "ENTRY AUTHORITY -- may each book OPEN a position, and what stops it"]
    for role in ("hack1", "hack2", "hack3", "hack4", "hack5", "hack6"):
        try:
            ea = entry_authority(role)
        except Exception as exc:                                    # noqa: BLE001
            L.append(f"  {role:<7}CANNOT DETERMINE: {str(exc)[:80]}")
            continue
        state = ("ARMED" if ea.get("armed") else
                 "DISARMED" if ea.get("armed") is False else "CANNOT DETERMINE")
        L.append(f"  {role:<7}{state:<10}{ea.get('binding') or 'nothing -- this book may enter'}")
    L.append("  TWO of the four possible disarms are RAILWAY VARIABLES and are invisible from")
    L.append("  here: `railway variables --service aat-loop-<role>`. This block reports what a")
    L.append("  local process can see and refuses to guess the rest.")
    L.append("")
    L.append("  hack2 IS ARMED AND IS NOT A TRACKER BOOK -- print this before Monday.")
    L.append("  `contract.defaults_for` branches on TRACKER_BOOKS = (hack3, hack4, hack6), so")
    L.append("  hack2 falls through to the EVENT defaults: horizon 3 sessions, min hold 0,")
    L.append("  profit_target_frac 0.025. Its fleet profile is 'aggressive' = a 3% stop. So the")
    L.append("  one armed book with NO minimum hold and a +2.5% target is the book the whole")
    L.append("  minimum-hold build was written to stop churning. Not fixed here -- which")
    L.append("  defaults hack2 gets is Murat's call, not a session's.")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=None, help="tracker vintage (default: newest on disk)")
    ap.add_argument("--mode", default="hygiene_only",
                    choices=("hygiene_only", "returns"),
                    help="band mode for the run (default: decision B.1 4a)")
    ap.add_argument("--compare", action="store_true",
                    help="run BOTH band modes and print the admitted-set difference")
    ap.add_argument("--out", default=None,
                    help="directory for the replay's artefacts (default: a temp dir; "
                         "never state/predictions)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                            # noqa: BLE001
            pass

    from alpha import config
    config.load_env()
    # NEVER state/predictions. A replay that can be mistaken for a seal is worse
    # than no replay: `tracker_portfolio` reads the newest file for the day.
    out = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="aat-dry-run-"))
    out.mkdir(parents=True, exist_ok=True)

    from scripts import tracker as tracker_cli
    day = args.day or tracker_cli.latest_day()
    if not day:
        print("REFUSED: no tracker vintage on disk. `python -m scripts.tracker --refresh`.")
        return 2

    modes = ("returns", "hygiene_only") if args.compare else (args.mode,)
    results: dict[str, dict] = {}
    pages: list[str] = []
    for m in modes:
        os.environ["AAT_BAND_MODE"] = m
        built = build_books(day)
        results[m] = built
        pages.append(render(built, day=day))
    os.environ.pop("AAT_BAND_MODE", None)

    page = "\n\n".join(pages) + "\n" + authority_block()

    if args.compare:
        page += "\n\n" + "-" * 78 + "\nBAND MODE DIFFERENCE (returns -> hygiene_only)\n"
        for book in BOOKS:
            a = {str(h.get("symbol")) for h in
                 ((results["returns"]["books"].get(book) or {}).get("port") or {}).get("holdings") or []}
            b = {str(h.get("symbol")) for h in
                 ((results["hygiene_only"]["books"].get(book) or {}).get("port") or {}).get("holdings") or []}
            page += (f"  {book:<7}{len(a)} -> {len(b)}   added: {sorted(b - a) or '-'}   "
                     f"dropped: {sorted(a - b) or '-'}\n")

    print(page)
    receipt = {
        "artefact": "MONDAY_DRY_RUN",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tracker_vintage": day,
        "modes": list(modes),
        "sealed": False, "ordered": False, "published": False,
        "books": {m: {b: {
            "admitted": [str(h.get("symbol")) for h in
                         ((r["books"].get(b) or {}).get("port") or {}).get("holdings") or []],
            "pool": ((r["books"].get(b) or {}).get("port") or {}).get("candidate_pool"),
            "eligible": ((r["books"].get(b) or {}).get("port") or {}).get("eligible"),
            "binding": binding(((r["books"].get(b) or {}).get("port") or {})),
        } for b in BOOKS} for m, r in results.items()},
        "page": page,
    }
    path = out / f"monday_dry_run_{day}.json"
    path.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    if args.json:
        print(json.dumps(receipt, indent=1, default=str))
    print(f"\nreplay receipt: {path}   (NOT a seal; nothing under state/predictions was written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
