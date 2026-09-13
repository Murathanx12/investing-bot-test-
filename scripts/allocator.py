"""Run the allocator once a day: mark the six curves, apply the rules, write the receipt.

    python -m scripts.allocator --anchor              # ONCE, on deploy day
    python -m scripts.allocator --run                 # daily, after the close
    python -m scripts.allocator --show                # print today's record, write nothing
    python -m scripts.allocator --run --equity hack1=93863,hack3=83342,...   # no venue

WHERE THIS RUNS, AND WHY IT IS NOT A RAILWAY CRON
=================================================
Reading six accounts' equity needs SIX key pairs. No Railway service has them:
`scripts/fleet.py --deploy` sets exactly one role's keys per service, on purpose
(`alpha/crossbook.py` explains why), and each service's volume is its own -- a
seventh service could read nothing and could write into nobody's `/app/state`.

So the allocator runs **where all six key pairs already live: the machine that
runs `python -m scripts.fleet --check-all`**, once a day after the close, and
its receipt reaches the loops the same way every other frozen artefact does --
committed under `docs/seed/allocator/` and shipped in the image on the next
deploy. The daily receipt names which books' budgets CHANGED, so only those need
a redeploy; on a day when nothing changed, nothing is deployed.

Windows Task Scheduler line for the daily run (NOT registered by this file --
registering a scheduled task is an attended act):

    schtasks /Create /TN "aegis-allocator" /SC WEEKLY /D MON,TUE,WED,THU,FRI ^
      /ST 17:15 /TR "cmd /c cd /d C:\\Users\\mrthn\\aegis-alpha-terminal && ^
      python -m scripts.allocator --run >> state\\allocator\\run.log 2>&1"

17:15 is local time on a machine whose clock is UTC+8; the venue closes 16:00
ET. **Compute ET before trusting that number** -- this repository has two clocks
and has been bitten by exactly this (`MEMORY.md`: machine UTC+8, scheduler
US/Eastern). The `--run` step refuses to write a record for a day the venue has
not finished, so a mistimed schedule produces a refusal rather than a half-day
mark.

THE ORDER OF THE DAY
====================
1. read each role's equity from the venue (`scripts.fleet.check`, read-only --
   it places nothing and this file imports no order path);
2. append it to `state/allocator/curves/<role>.jsonl`;
3. apply yesterday's record + today's curves to `alpha.allocator.allocate`;
4. print the WORST CASE IN DOLLARS, per book and fleet, BEFORE writing;
5. write `state/allocator/<day>.json`.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from alpha import allocator as A, contract as _contract, exits as _exits

ROOT = Path(__file__).resolve().parent.parent


def _dir() -> Path:
    A.STATE.mkdir(parents=True, exist_ok=True)
    (A.STATE / "curves").mkdir(parents=True, exist_ok=True)
    return A.STATE


def read_equities(roles=A.ROLES, *, supplied: dict | None = None) -> dict:
    """{role: {equity, account, orders, positions}} or the reason it is absent.

    `supplied` short-circuits the venue entirely and is how the first dry run
    was done before any deploy -- with the numbers read by hand and pasted in,
    so the run is reproducible from its own command line.
    """
    if supplied:
        return {r: {"equity": float(v["equity"]), "account": v.get("account"),
                    "source": "supplied on the command line"}
                for r, v in supplied.items() if r in roles}
    from scripts.fleet import check
    out = {}
    for r in roles:
        try:
            row = check(r)
        except Exception as exc:                                    # noqa: BLE001
            out[r] = {"equity": None, "why": f"{type(exc).__name__}: {str(exc)[:160]}"}
            continue
        if row.get("state") == "NO_KEYS" or row.get("equity") is None:
            out[r] = {"equity": None, "why": row.get("why") or "no equity on the account row"}
            continue
        out[r] = {"equity": float(row["equity"]), "account": row.get("account"),
                  "orders": row.get("orders_any_status"), "positions": row.get("positions"),
                  "source": "venue read, scripts.fleet.check"}
    return out


def curve_path(role: str) -> Path:
    return _dir() / "curves" / f"{role}.jsonl"


def load_curve(role: str) -> list[dict]:
    p = curve_path(role)
    if not p.is_file():
        return []
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    # ONE MARK PER DAY, the LAST one written. A second read on the same day is a
    # correction, not a second observation -- counting it twice would inflate
    # every block count downstream.
    by_day = {}
    for r in rows:
        by_day[str(r["day"])] = r
    return [by_day[d] for d in sorted(by_day)]


def append_mark(role: str, day: str, equity: float, **extra) -> None:
    row = {"day": str(day), "equity": float(equity),
           "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), **extra}
    with curve_path(role).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def anchor_path() -> Path:
    return _dir() / A.ANCHOR


def write_anchor(equities: dict, day: str) -> dict:
    """The deploy-time equity every allocator curve starts from.

    THE ACCOUNTS ARE NOT RESET. Deleting and recreating an Alpaca paper account
    rotates its API keys, so the six roles keep the equity they have and every
    curve in this trial starts from the number recorded here -- which is why the
    anchor has to be written down before the first weight, not reconstructed
    afterwards from whatever the account happened to be worth.
    """
    if anchor_path().is_file():
        raise SystemExit(
            f"REFUSED: {anchor_path()} already exists. An anchor is the start of "
            f"a measured series; rewriting it silently re-bases every drawdown "
            f"and every cumulative excess computed since. Move the old one aside "
            f"by hand, on purpose, if a re-anchor is really intended.")
    missing = [r for r in A.ROLES if (equities.get(r) or {}).get("equity") is None]
    if missing:
        raise SystemExit(
            f"REFUSED: no equity for {missing}. An anchor with a hole in it is an "
            f"anchor that silently excludes a book from the fleet's worst case.")
    rec = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "anchor_day": str(day),
        "trial": A.TRIAL, "licence": A.LICENCE,
        "contract_hash": A.contract_sha256(),
        "accounts_were_reset": False,
        "why_not_reset": ("Alpaca's dashboard reset is delete-and-recreate and "
                          "rotates the API keys; the six roles keep their "
                          "equity and every curve here starts from it"),
        "books": {r: {"anchor_equity": equities[r]["equity"], "anchor_day": str(day),
                      "account": equities[r].get("account"),
                      "source": equities[r].get("source")} for r in A.ROLES},
    }
    anchor_path().write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rec


def load_anchor() -> dict:
    for p in (anchor_path(), A.SEED_STATE / A.ANCHOR):
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    raise SystemExit(
        f"REFUSED: no anchor at {anchor_path()}. Run `--anchor` first: a "
        f"drawdown measured from an unstated starting point is not a drawdown.")


def print_worst_case(rec: dict) -> None:
    """Rule 4 of the session protocol: the worst case in dollars, BEFORE the change."""
    print("\n  WORST CASE IN DOLLARS, at the budgets this record sets")
    print(f"  {'role':<8}{'equity':>12}{'scale':>8}{'stop%':>8}{'worst $':>12}  state")
    for r in A.ROLES:
        b = rec["per_book"][r]
        print(f"  {r:<8}{(b['current_equity'] or 0):>12,.0f}"
              f"{b['gross_budget_scale']:>8.2f}"
              f"{(b['declared_worst_case_frac'] or 0):>8.1%}"
              f"{b['worst_case_usd']:>12,.0f}  {b['kill_state']}"
              f" [{b['binding_constraint']}]")
    print(f"  {'FLEET':<8}{'':>12}{'':>8}{'':>8}{rec['worst_case_usd_fleet']:>12,.0f}"
          f"  = {(rec['worst_case_pct_equity_fleet'] or 0):.2%} of fleet equity")
    print("  (per book: declared worst_case_frac x gross_budget_scale x equity; "
          "alpha/contract.worst_case is the source of the fraction)")


def build(day: str, *, supplied: dict | None = None, mark: bool = True) -> dict:
    anchor = load_anchor()
    eq = read_equities(supplied=supplied)
    notes = []
    for r in A.ROLES:
        v = (eq.get(r) or {}).get("equity")
        if v is None:
            notes.append(f"{r}: NO MARK TODAY -- {(eq.get(r) or {}).get('why')}")
            continue
        if mark:
            append_mark(r, day, v, account=(eq[r].get("account")),
                        source=eq[r].get("source"))
    curves = {r: load_curve(r) for r in A.ROLES}
    if mark:
        for r in A.ROLES:
            v = (eq.get(r) or {}).get("equity")
            if v is not None and (not curves[r] or curves[r][-1]["day"] != str(day)):
                curves[r] = curves[r] + [{"day": str(day), "equity": v}]
    yesterday, _ = A.latest_record(day=_prev_day(day))
    rec = A.allocate(day, curves=curves, anchor=anchor, yesterday=yesterday)
    rec["notes"] = list(rec.get("notes") or []) + notes
    rec["anchor_hash"] = anchor.get("contract_hash")
    if anchor.get("contract_hash") != rec["contract_hash"]:
        # A CONTRACT THAT MOVED MID-TRIAL IS THE ONE THING THIS RECEIPT CANNOT
        # HIDE. It is reported, loudly, on the row, rather than silently
        # re-hashed: a tamper-evident record whose evidence of tampering is
        # repaired is not tamper-evident.
        rec["notes"].append(
            f"CONTRACT CHANGED SINCE THE ANCHOR: anchor "
            f"{str(anchor.get('contract_hash'))[:16]} vs today "
            f"{rec['contract_hash'][:16]}. Every number before today was "
            f"produced under a different rule.")
    return rec


def _prev_day(day: str) -> str:
    from datetime import date, timedelta
    y, m, d = (int(x) for x in str(day).split("-"))
    return (date(y, m, d) - timedelta(days=1)).isoformat()


def write_record(rec: dict) -> Path:
    p = _dir() / f"{rec['day']}.json"
    p.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return p


def changed_books(rec: dict, yesterday: dict | None) -> list[str]:
    """Whose gross budget moved, so the deploy plan names only those."""
    prev = ((yesterday or {}).get("per_book") or {})
    out = []
    for r in A.ROLES:
        a = prev.get(r, {}).get("gross_budget_scale")
        b = rec["per_book"][r]["gross_budget_scale"]
        if a is None or abs(float(a) - float(b)) > 1e-9:
            out.append(r)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--anchor", action="store_true",
                    help="write the deploy-time anchor. Once, and it refuses to overwrite.")
    ap.add_argument("--run", action="store_true", help="mark the curves and write today's record")
    ap.add_argument("--show", action="store_true", help="compute and print; write nothing")
    ap.add_argument("--day", default=None)
    ap.add_argument("--equity", default=None,
                    help="role=value[:account],role=value -- skip the venue entirely. The "
                         "optional :account is the venue ACCOUNT NUMBER and belongs on the "
                         "anchor: every other piece of state here is keyed by ROLE, and a role "
                         "pointed at a different account would carry the old one's history "
                         "forward under the same label (alpha/genesis.py's own warning).")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    day = a.day or _exits.session_day()
    supplied = None
    if a.equity:
        supplied = {}
        for part in a.equity.split(","):
            k, _, v = part.partition("=")
            eq, _, acct = v.partition(":")
            supplied[k.strip().lower()] = {"equity": float(eq),
                                           "account": acct.strip() or None}

    if a.anchor:
        eq = read_equities(supplied=supplied)
        rec = write_anchor(eq, day)
        print(json.dumps(rec, indent=1))
        return 0

    if not (a.run or a.show):
        ap.error("one of --anchor, --run, --show is required")

    rec = build(day, supplied=supplied, mark=bool(a.run))
    yesterday, _ = A.latest_record(day=_prev_day(day))

    if a.json:
        print(json.dumps(rec, indent=1))
    else:
        print(f"\nALLOCATOR {rec['day']}  contract {rec['contract_hash'][:16]}  "
              f"{rec['licence']} / {rec['trial']}")
        print(f"  {'role':<8}{'dd':>9}{'state':>10}{'post mean':>12}{'blocks':>8}"
              f"{'weight':>9}{'EW':>8}{'rand':>8}{'gross':>8}")
        for r in A.ROLES:
            b = rec["per_book"][r]
            dd = b["drawdown_from_peak_pct"]
            pm = b["posterior_mean_daily_excess_vs_twin"]
            print(f"  {r:<8}{(f'{dd:+.2%}' if dd is not None else 'n/a'):>9}"
                  f"{b['kill_state_base']:>10}"
                  f"{(f'{pm:+.4%}' if pm is not None else 'n/a'):>12}"
                  f"{b['n_effective_date_blocks']:>8}"
                  f"{b['allocator_weight']:>9.3f}{b['equal_weight_twin_weight']:>8.3f}"
                  f"{b['random_twin_weight']:>8.3f}{b['gross_budget_scale']:>8.2f}")
        for line in rec["rule_fired"] or ["  (no kill or restore rule fired today)"]:
            print(f"  RULE FIRED: {line}" if rec["rule_fired"] else line)
        print_worst_case(rec)
        vc = rec["verdict_clock"]
        print(f"\n  TWINS: allocator - equal weight = "
              f"{rec['allocator_vs_equal_weight_twin_cum_excess']:+.6f}; "
              f"allocator - random = {rec['allocator_vs_random_twin_cum_excess']:+.6f} "
              f"over {vc['sessions_elapsed']} session(s)")
        print(f"  VERDICT CLOCK: {vc['status']}"
              + (f", {vc['sessions_to_decision']} session(s) to the decision"
                 if vc.get("sessions_to_decision") else ""))
        for n in rec["notes"]:
            print(f"  note: {n}")

    if a.run:
        p = write_record(rec)
        moved = changed_books(rec, yesterday)
        print(f"\n  -> {p}")
        print(f"  budgets that MOVED today: {moved or 'none'}"
              + ("  (redeploy only these: "
                 + "; ".join(f"python -m scripts.fleet --deploy {r} --up" for r in moved)
                 + ")" if moved else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
