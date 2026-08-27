"""COMPETITION_ACCOUNT_GENESIS_v1 -- what the judged account was, before it traded.

    python -m scripts.genesis --freeze     # once, on 28 Aug, before the first order
    python -m scripts.genesis              # verify the live account still matches

WHY A JUDGED ACCOUNT NEEDS A BIRTH CERTIFICATE
==============================================
The rules snapshot (`docs/RULES_SNAPSHOT_2026-08-25.md`) says the judged account
must be **brand new** and start at **$100,000**. That is a claim about a moment
that stops being observable the instant the first order fills: afterwards the
account has an equity curve, and "it started at 100k" becomes something we assert
rather than something we can show.

So it is recorded at the moment it is still true, with the venue as the witness,
and everything downstream verifies against the record instead of against a
memory.

THE FAILURE THIS ACTUALLY PREVENTS
==================================
Not "someone submits the wrong account on purpose". The real path is duller:

    AAT_COMPETITION_KEY_ID=<pasted from the wrong tab>

and the judged run silently resolves to `PA32Q5IW7TAS` -- the dev book, down
15.1% on 27 Aug across 27 orders and 8 open positions. Every guard in this repo
is keyed on the ROLE, so a role pointed at the wrong account passes all of them.

Which is why `DENIED_ACCOUNTS` is keyed on the **account_number the venue
returns**, not on an env var, a role name, or the nickname in the dashboard.
Those three are all things we control; the account number is the thing the judge
sees. A reviewer on 27 Aug read the dashboard label "hackathon", found it at
-13%, and concluded the judged account was already poisoned. The label was a UI
nickname on the dev account. Identity comes from the venue.

WHAT REFUSES, AND WHY EACH ONE
==============================
denylisted account      it has traded; "brand new" is false and unfixable
equity != $100,000      the rule is exact, and a near miss is a different account
any position            not new
any order, ANY status   a cancelled order is still a traded account. Filtering to
                        `status=open` here would let an expired OPG order -- the
                        exact thing that left `market` at 0 positions and 1 order
                        -- read as a clean book
not a PA- number        not a paper account
role is not competition freezing genesis for `dev` would make the record a lie
                        the moment anyone trusted it

None of these is configurable. The only reason to override one is the reason it
exists.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from alpha import config

#: Account numbers that may NEVER hold the `competition` role, and why. Read
#: from the venue on 2026-08-27 by `python -m scripts.accounts` -- not copied
#: from a document, and not inferred from a dashboard nickname.
DENIED_ACCOUNTS: dict[str, str] = {
    "PA32Q5IW7TAS": ("role `dev`, labelled 'hackathon' in the Alpaca UI. $84,888 on 2026-08-27 "
                     "(-15.1%), 8 positions, 27 orders, opened under the PRE_UNITS_FIX "
                     "arithmetic. The corpse being dissected, never the judged book."),
    "PA3AOJPJTSBW": ("role `exp1`. $95,880 on 2026-08-27 (-4.1%), 8 positions, 16 orders, "
                     "daily-loss latched. Legacy."),
    "PA3I7VTCC0BM": ("role `market`. The passive-beta benchmark. 1 order, 0 positions -- an "
                     "OPG order that expired unfilled. It has traded and it is a benchmark, "
                     "which are two separate reasons."),
    "PA3LY4QK3A6A": ("role `pead`. Clean $100k, but DECLARED to another arm in `alpha/arms.py`. "
                     "Reusing a declared arm's account would make two arms one account and "
                     "silently collapse the independence measurement."),
}

#: The role a genesis record may be frozen for.
JUDGED_ROLE = "competition"

STATE_DIR = Path(os.getenv("AAT_LEDGER_DIR") or "state")


class GenesisRefusal(RuntimeError):
    """The judged account is not in a state that can be frozen or verified."""


def path(role: str = JUDGED_ROLE) -> Path:
    return STATE_DIR / f"genesis_{role}.json"


@dataclass(frozen=True)
class Genesis:
    role: str
    account_number: str
    frozen_at_utc: str
    starting_equity: float
    position_count_at_genesis: int
    order_count_at_genesis: int
    rules_snapshot_path: str
    rules_snapshot_sha256: str
    code_commit: str
    competition: dict

    def digest(self) -> str:
        """Hash of every field but the hash. Canonical JSON so it is stable."""
        body = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(body.encode()).hexdigest()

    def as_record(self) -> dict:
        d = asdict(self)
        d["genesis_sha256"] = self.digest()
        return d


def _code_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, timeout=10, cwd=Path(__file__).resolve().parent.parent)
        return out.stdout.strip() or "UNKNOWN"
    except Exception:                                                  # noqa: BLE001
        return "UNKNOWN"


def _rules_digest(rules_path: Path) -> str:
    if not rules_path.exists():
        raise GenesisRefusal(
            f"rules snapshot {rules_path} does not exist. The judged account may not be frozen "
            "against rules nobody re-pulled. `docs/RULES_SNAPSHOT_2026-08-25.md` says in its own "
            "text to re-pull at kickoff."
        )
    return hashlib.sha256(rules_path.read_bytes()).hexdigest()


def inspect(client, *, role: str) -> tuple[str, float, int, int]:
    """(account_number, equity, n_positions, n_orders_any_status). Read-only."""
    acct = client.account()
    number = str(acct.get("account_number") or "")
    equity = float(acct.get("equity") or 0.0)
    positions = client.positions()
    # ANY status. `status=open` would call an account with one expired OPG order
    # and nothing else "clean" -- which is precisely the state `market` is in.
    orders = client.orders(status="all", limit=500)
    return number, equity, len(positions), len(orders)


def freeze(client, *, role: str, rules_snapshot: str | Path,
           required_equity: float | None = None, force_write: bool = False) -> Genesis:
    """Record the judged account's birth state, or refuse and say which rule."""
    if role != JUDGED_ROLE:
        raise GenesisRefusal(
            f"genesis may only be frozen for role {JUDGED_ROLE!r}, not {role!r}. A genesis "
            "record for a non-judged role is a document that looks authoritative and is not."
        )
    required = (required_equity if required_equity is not None
                else float(config.COMPETITION["required_starting_equity"]))
    rules_path = Path(rules_snapshot)
    rules_sha = _rules_digest(rules_path)

    number, equity, n_pos, n_ord = inspect(client, role=role)

    if not number.startswith("PA"):
        raise GenesisRefusal(f"account {number!r} is not a paper account (no 'PA' prefix).")
    if number in DENIED_ACCOUNTS:
        raise GenesisRefusal(
            f"account {number} is DENYLISTED for the judged role: {DENIED_ACCOUNTS[number]} "
            "The competition rules require a brand-new account; this one has a history and "
            "no amount of configuration makes it new again."
        )
    if abs(equity - required) > 0.005:
        raise GenesisRefusal(
            f"account {number} holds ${equity:,.2f}; the rules require exactly "
            f"${required:,.2f}. A near miss is not a rounding problem -- it is a different "
            "account, or an account that has already moved."
        )
    if n_pos:
        raise GenesisRefusal(f"account {number} already holds {n_pos} position(s). Not new.")
    if n_ord:
        raise GenesisRefusal(
            f"account {number} already carries {n_ord} order(s) of any status. A cancelled or "
            "expired order still means the account has been traded."
        )

    existing = path(role)
    if existing.exists() and not force_write:
        prior = json.loads(existing.read_text())
        raise GenesisRefusal(
            f"genesis is already frozen for role {role!r} at {existing} "
            f"(account {prior.get('account_number')}, frozen {prior.get('frozen_at_utc')}). "
            "Re-freezing would overwrite the birth certificate of the account being judged. "
            "Pass force_write only if the earlier record was for an account that was never used."
        )

    g = Genesis(
        role=role,
        account_number=number,
        frozen_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        starting_equity=equity,
        position_count_at_genesis=n_pos,
        order_count_at_genesis=n_ord,
        rules_snapshot_path=str(rules_path).replace("\\", "/"),
        rules_snapshot_sha256=rules_sha,
        code_commit=_code_commit(),
        competition=dict(config.COMPETITION),
    )
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text(json.dumps(g.as_record(), indent=2, sort_keys=True) + "\n")
    return g


def load(role: str = JUDGED_ROLE) -> Genesis | None:
    p = path(role)
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    d.pop("genesis_sha256", None)
    return Genesis(**d)


def verify(client, *, role: str = JUDGED_ROLE) -> tuple[bool, list[str]]:
    """(ok, lines). Never raises on a mismatch -- it reports one, loudly.

    Callers that must not proceed (`scripts/preflight`, the runner's judged
    path) turn a False into their own refusal. This function's job is to be
    readable in a terminal at 10:55 ET.
    """
    lines: list[str] = []
    g = load(role)
    if g is None:
        return False, [f"NO GENESIS RECORD at {path(role)}. The judged account has no frozen "
                       "birth state, so nothing can attest that it started clean at $100,000. "
                       "Run `python -m scripts.genesis --freeze` BEFORE the first order."]

    stored = json.loads(path(role).read_text()).get("genesis_sha256")
    if stored != g.digest():
        lines.append(f"GENESIS HASH MISMATCH: file says {stored}, recompute says {g.digest()}. "
                     "The record was edited after it was written.")

    number, equity, n_pos, n_ord = inspect(client, role=role)
    ok = not lines

    if number != g.account_number:
        ok = False
        lines.append(f"ACCOUNT MISMATCH: genesis froze {g.account_number}, the live credentials "
                     f"resolve to {number}. The judged role is pointed at a different account.")
    if number in DENIED_ACCOUNTS:
        ok = False
        lines.append(f"DENYLISTED: {number} -- {DENIED_ACCOUNTS[number]}")

    lines.append(f"genesis   {g.account_number}  frozen {g.frozen_at_utc}")
    lines.append(f"          started ${g.starting_equity:,.2f}, {g.position_count_at_genesis} "
                 f"positions, {g.order_count_at_genesis} orders")
    lines.append(f"          rules {g.rules_snapshot_path} sha {g.rules_snapshot_sha256[:12]}")
    lines.append(f"          code  {g.code_commit[:12]}")
    lines.append(f"live      ${equity:,.2f}  {n_pos} positions  {n_ord} orders  "
                 f"P&L {equity - g.starting_equity:+,.2f} "
                 f"({(equity / g.starting_equity - 1) * 100:+.2f}%)"
                 if g.starting_equity else "live      (no starting equity)")
    return ok, lines
