"""CONTRACT -- freeze what an account will trade, BEFORE its first decision.

    python -m scripts.contract --freeze pead      # write + hash (refuses if traded)
    python -m scripts.contract --verify pead      # has it changed since?
    python -m scripts.contract --list

WHY A HASH AND NOT JUST A MARKDOWN FILE
=======================================
The `PRODUCT_EXPERIMENT` licence drops the significance gate, the MDE and the
preregistration. What it does NOT drop is a frozen strategy contract before the
first decision. The point is not ceremony: it is that a book which drifted into a
different strategy can otherwise be re-described afterwards as having always
meant to do that, and nobody -- including the person who wrote it -- can tell.

So the declaration is hashed, the hash is stored beside it, and `--verify` says
CHANGED rather than quietly passing. It is deliberately NOT wired into execution:
a guard added before its failure is observed is a guard tuned to a guess, and the
honest first step is to be able to SEE a breach.

WHAT IT REFUSES
===============
Freezing a contract for an account that has already traded. "Before the first
decision" is the whole property being claimed; an account with fills has one
already, and back-dating it would be the exact tampering this file exists to make
visible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from alpha import config

CONTRACT_DIR = Path("state/contracts")

#: Declarations live here, in code, so a contract cannot be created by editing a
#: JSON file that nothing reviews. Prose lives in docs/CONTRACT_*.md; this is the
#: machine-checkable half and the two must agree.
DECLARATIONS: dict[str, dict] = {
    "pead": {
        "name": "SOURCE_PEAD_MID_v1",
        "licence": "PRODUCT_EXPERIMENT",
        "prose": "docs/CONTRACT_2026-08-27_SOURCE_PEAD_MID.md",
        "hypothesis": (
            "A name that has just printed drifts in the SIGN of its own day-0 move over the "
            "following three sessions, as excess over beta*QQQ, and the effect is concentrated "
            "in the MIDDLE of the day-0 move distribution."
        ),
        "qualifying_event": {
            "source": "SEC 8-K Item 2.02, exact filing date and session",
            "day0_bar_must_be_closed": True,
            "abs_r0_min": 0.035,
            "abs_r0_full_conviction_max": 0.082,
            "conviction_multiplier_above_max": 0.5,
            "max_sessions_elapsed": 3,
        },
        "instruments": ["shares", "debit_spread"],
        "forbidden_instruments": ["long_call", "long_put", "long_straddle", "long_strangle"],
        "max_round_trip_cost_frac_of_spot": 0.005,
        "fill_convention": {
            "entry": "day+1 open",
            "exit": "day+3 close, or the declared stop",
            "late_arrival_allowed": True,
            "zero_cost_diagnostic_permitted": False,
        },
        "objective": "terminal wealth, balanced personality",
        "benchmarks": ["market arm PA3I7VTCC0BM (product)", "sign-flipped same events (signal)"],
        "risk": {
            "risk_per_event_frac": 0.02,
            "max_concurrent_events": 5,
            "max_single_thesis_frac_of_book_max_loss": 0.20,
            "min_effective_n_by_risk_before_6th": 2.0,
            "daily_latch_frac": -0.03,
            "down_side_traded_only_as_pair_with_IWM": True,
        },
        "retire_if": [
            "fails to clear the sign-flipped control over 20 qualifying events",
            "realised round-trip cost exceeds 0.50% of spot on a majority of fills",
            "the +1..+3 session window stops containing the drift",
        ],
        "not_retire_if": ["a losing quarter -- 6 of 11 were negative in the wide study"],
    },
    "market": {
        "name": "PASSIVE_BETA_v1",
        "licence": "PRODUCT_EXPERIMENT",
        "prose": "docs/CONTRACT_2026-08-27_SOURCE_PEAD_MID.md (section 5 names this arm)",
        "hypothesis": "None. This is the bar every other arm must clear.",
        "qualifying_event": {"source": "none -- one purchase at the next regular open"},
        "instruments": ["shares"],
        "forbidden_instruments": ["*"],
        "max_round_trip_cost_frac_of_spot": 0.005,
        "fill_convention": {"entry": "next regular-session open, market order, once",
                            "exit": "never", "zero_cost_diagnostic_permitted": False},
        "objective": "terminal wealth of a buy-and-hold index book, path included",
        "benchmarks": ["itself -- it IS the benchmark"],
        "risk": {"note": "fully invested, no leverage, no stop. The drawdown it takes is the "
                         "number every other arm is competing against and must not be smoothed."},
        "retire_if": ["never -- retiring the benchmark destroys every comparison built on it"],
        "not_retire_if": ["a drawdown. That is the measurement."],
    },
}


def _canonical(d: dict) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"))


def _hash(d: dict) -> str:
    return hashlib.sha256(_canonical(d).encode("utf-8")).hexdigest()


def _account(role: str) -> dict | None:
    try:
        creds = config.credentials(role)
    except config.CredentialRefusal:
        return None
    req = urllib.request.Request(config.base_url() + "/v2/account", headers=creds.headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None


def _has_traded(role: str) -> bool | None:
    """True/False, or None when the broker could not be asked. None is not False."""
    try:
        creds = config.credentials(role)
    except config.CredentialRefusal:
        return None
    for path in ("/v2/orders?status=all&limit=1", "/v2/positions"):
        req = urllib.request.Request(config.base_url() + path, headers=creds.headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                if json.loads(r.read().decode()):
                    return True
        except Exception:
            return None
    return False


def freeze(role: str) -> int:
    if role not in DECLARATIONS:
        print(f"no declaration for {role!r}; have {sorted(DECLARATIONS)}")
        return 2
    traded = _has_traded(role)
    if traded is None:
        print(f"REFUSED: could not ask the broker whether {role} has traded. "
              "'Before the first decision' is the property being claimed and it cannot be "
              "claimed against an unanswered question.")
        return 1
    if traded:
        print(f"REFUSED: {role} already has orders or positions. A contract frozen after the "
              "first decision is back-dated, which is the tampering this file exists to expose.")
        return 1
    decl = DECLARATIONS[role]
    acct = _account(role) or {}
    payload = {
        "role": role,
        "declaration": decl,
        "account_number": acct.get("account_number"),
        "equity_at_freeze": acct.get("equity"),
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
    }
    payload["hash"] = _hash({k: v for k, v in payload.items() if k != "hash"})
    CONTRACT_DIR.mkdir(parents=True, exist_ok=True)
    out = CONTRACT_DIR / f"{decl['name'].lower()}.json"
    if out.exists():
        print(f"REFUSED: {out} already exists. Freezing twice would silently replace the "
              "record whose immutability is the point. Delete it deliberately, or use _v2.")
        return 1
    out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"FROZEN {decl['name']} for role {role}")
    print(f"  account {payload['account_number']}  equity ${float(payload['equity_at_freeze'] or 0):,.2f}")
    print(f"  hash    {payload['hash']}")
    print(f"  receipt {out}")
    return 0


def verify(role: str) -> int:
    if role not in DECLARATIONS:
        print(f"no declaration for {role!r}")
        return 2
    decl = DECLARATIONS[role]
    p = CONTRACT_DIR / f"{decl['name'].lower()}.json"
    if not p.exists():
        print(f"{role}: NOT FROZEN -- no {p}. This account has no contract, so it must not trade.")
        return 1
    stored = json.loads(p.read_text(encoding="utf-8"))
    recomputed = _hash({k: v for k, v in stored.items() if k != "hash"})
    if recomputed != stored.get("hash"):
        print(f"{role}: RECEIPT TAMPERED -- stored hash {stored.get('hash')[:16]}... "
              f"but content hashes to {recomputed[:16]}...")
        return 1
    if _canonical(stored["declaration"]) != _canonical(decl):
        print(f"{role}: CONTRACT CHANGED since it was frozen at {stored['frozen_utc']}.")
        print("  The code's declaration no longer matches the frozen receipt. That is a "
              "contract breach, not a merge conflict -- a new threshold is _v2, never an edit.")
        return 1
    print(f"{role}: OK  {decl['name']}  frozen {stored['frozen_utc']}  hash {stored['hash'][:16]}...")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", metavar="ROLE")
    p.add_argument("--verify", metavar="ROLE")
    p.add_argument("--list", action="store_true")
    args = p.parse_args()
    config.load_env()
    if args.list or not (args.freeze or args.verify):
        print(f"{'role':10} {'contract':22} {'frozen?':8} prose")
        for role, d in DECLARATIONS.items():
            f = CONTRACT_DIR / f"{d['name'].lower()}.json"
            print(f"{role:10} {d['name']:22} {'yes' if f.exists() else 'NO':8} {d['prose']}")
        return 0
    return freeze(args.freeze) if args.freeze else verify(args.verify)


if __name__ == "__main__":
    raise SystemExit(main())
