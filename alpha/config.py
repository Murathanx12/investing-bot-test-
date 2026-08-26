"""Credentials, endpoints, and the refusals that make this repo safe to run.

THREE REFUSALS, AND EACH ONE HAS A SPECIFIC CORPSE BEHIND IT
============================================================

1. **This repo never reads `ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY`.**
   Those variables exist on the development machine and they are attached to a
   LIVE Alpaca account. A smoke test in the parent project once called `sync()`
   against them and placed **twelve real sell orders**. A tournament bot that
   inherits an ambient credential is one `os.getenv` away from repeating that,
   so the inheritance is severed at the name: everything here is `AAT_*`, and
   `credentials()` REFUSES if the caller tries to fall back.

2. **The base URL must be the paper host.** Not "defaults to paper" -- a
   default is a thing an env var can quietly override. `base_url()` matches the
   host against an allowlist and raises otherwise. There is no flag that turns
   this off, because the only reason to want one is the reason we are guarding.

3. **The competition account is DECLARED, not discovered.** `ACCOUNT_ROLE`
   is `dev` or `competition` and must be set explicitly. A run with no role set
   refuses rather than assuming `dev`, because the failure mode we care about is
   a rehearsal order landing in the judged account -- and that failure looks
   exactly like a missing env var.

WHY A SEPARATE NAMESPACE INSTEAD OF A SHARED ONE
------------------------------------------------
An Alpaca account is ONE account with ONE equity curve. The competition account
is submitted for judging and its history is the deliverable. Sharing a variable
name with anything else -- the parent project's lane mirror, the arena mirror, a
teammate's shell -- means a single stale export can write a rehearsal into the
judged record. There is no undo for that: the rules say a reused account is
ineligible, and a reset is itself a disqualifying reuse.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

def load_env(path: str | None = None) -> int:
    """Load `.env` into the process if present. No dependency, no surprises.

    Deliberately does NOT overwrite a variable that is already set: an explicit
    export on the command line must win over a file, because the file is the
    thing you forget you edited and the export is the thing you just typed.
    """
    import pathlib

    target = pathlib.Path(path or pathlib.Path(__file__).resolve().parent.parent / ".env")
    if not target.exists():
        return 0
    loaded = 0
    for raw in target.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded


#: The options data feed. `opra` is real-time and needs Algo Trader Plus; the
#: free `indicative` feed is delayed ~15 minutes during market hours. Which one
#: is live is a MEASURED fact recorded on every snapshot, never an assumption --
#: see `alpha/data/chain.py`.
def options_feed() -> str:
    return os.getenv("AAT_OPTIONS_FEED", "indicative").strip().lower()


def stock_feed() -> str:
    return os.getenv("AAT_STOCK_FEED", "iex").strip().lower()


#: Hosts this repo is permitted to talk to. `api.alpaca.markets` (the LIVE
#: trading host) is deliberately absent and must stay absent.
_ALLOWED_TRADING_HOSTS = frozenset({"paper-api.alpaca.markets"})

#: Market data is read-only, so the live data host is fine -- it cannot place
#: an order. It is still allowlisted so a typo'd host fails loudly.
_ALLOWED_DATA_HOSTS = frozenset({"data.alpaca.markets"})

#: Reserved roles. `competition` is the judged account, created at kickoff and
#: never touched before it; `dev` is the main rehearsal account. Any other
#: lowercase alphanumeric name is allowed as an EXPERIMENT account -- `exp1`,
#: `aggressive`, `condor` -- so several risk envelopes can run against real
#: paper accounts at once instead of being argued about.
#:
#: An Alpaca account is ONE equity curve, so a variant needs its own account to
#: be measured rather than reasoned about. This is the cheap version of the
#: parent project's portfolio farm: real fills, real marks, no shared history.
RESERVED_ROLES = ("dev", "competition")
ROLES = RESERVED_ROLES  # back-compat alias; membership is no longer exhaustive


def _valid_role(name: str) -> bool:
    return bool(name) and name.replace("_", "").isalnum() and name == name.lower()

#: Variables from the PARENT project that must never be read here. Named so the
#: refusal message can say what it is protecting rather than "missing key".
_FORBIDDEN_INHERITED = (
    "ALPACA_API_KEY_ID",
    "ALPACA_API_SECRET_KEY",
    "ALPACA_ARENA_API_KEY_ID",
    "ALPACA_ARENA_API_SECRET_KEY",
)


class CredentialRefusal(RuntimeError):
    """A credential was missing, ambiguous, or inherited from the wrong place."""


class EndpointRefusal(RuntimeError):
    """A host that is not the paper trading host was requested."""


@dataclass(frozen=True)
class Credentials:
    key_id: str
    secret_key: str
    role: str

    @property
    def headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.key_id,
            "APCA-API-SECRET-KEY": self.secret_key,
        }

    def __repr__(self) -> str:  # never print a secret into a log or a ledger
        return f"Credentials(role={self.role!r}, key_id={self.key_id[:4]}...)"


def role() -> str:
    """The DECLARED account role. Refuses rather than defaulting.

    A default here would mean an unset variable silently selects an account,
    and the whole point of the two roles is that selecting the wrong one is
    unrecoverable.
    """
    declared = os.getenv("AAT_ACCOUNT_ROLE", "").strip().lower()
    if not declared:
        raise CredentialRefusal(
            "AAT_ACCOUNT_ROLE is not set. Declare 'dev' (rehearsal account) or "
            "'competition' (the judged account). This is not defaulted: an "
            "unset variable choosing the judged account is the one mistake "
            "with no undo."
        )
    if not _valid_role(declared):
        raise CredentialRefusal(
            f"AAT_ACCOUNT_ROLE={declared!r} is not a valid role name (lowercase "
            "alphanumeric, underscores allowed)."
        )
    return declared


def credentials(for_role: str | None = None) -> Credentials:
    """Paper credentials for the declared role, from this repo's namespace only."""
    resolved = for_role or role()
    if not _valid_role(resolved):
        raise CredentialRefusal(f"Invalid role name {resolved!r}.")

    # FOURTH REFUSAL: the flag and the environment must AGREE.
    #
    # `scripts/run_pass.py --role X` builds the client, but every ledger stamp
    # and book match reads `AAT_ACCOUNT_ROLE` from the environment instead
    # (`runner`, `exits`, `book`, `recovery`). So
    #     AAT_ACCOUNT_ROLE=dev python -m scripts.run_pass --role competition --live
    # sends orders to the JUDGED account and stamps the rows `dev`; the book is
    # then reconstructed from another account's rows and its risk is computed
    # against positions it does not hold.
    #
    # Neither value is obviously the right one to believe, which is exactly why
    # this refuses instead of picking. (Audit defect 6.)
    declared = os.getenv("AAT_ACCOUNT_ROLE", "").strip().lower()
    if for_role and declared and declared != resolved:
        raise CredentialRefusal(
            f"ROLE DISAGREEMENT: --role/{resolved!r} was requested but "
            f"AAT_ACCOUNT_ROLE={declared!r} is what every ledger stamp, book match "
            "and recovery score will read. One of them is wrong and this refuses "
            "rather than choosing: orders would go to one account and its rows "
            "would be written under another's name. Set both, or neither."
        )
    # NOTE: this deliberately does NOT set AAT_ACCOUNT_ROLE when it is unset.
    # An earlier draft did, and it turned `credentials()` -- which reads like an
    # accessor -- into a function that mutates global process state, so a
    # credential check in one test silently re-stamped the ledger rows of every
    # test after it. Making the flag authoritative is right; the place to do it
    # is the CLI entry point, where it is visible. See `scripts/run_pass.py`.

    prefix = f"AAT_{resolved.upper()}"
    key_id = os.getenv(f"{prefix}_KEY_ID", "").strip()
    secret = os.getenv(f"{prefix}_SECRET_KEY", "").strip()

    if not key_id or not secret:
        inherited = [name for name in _FORBIDDEN_INHERITED if os.getenv(name)]
        hint = ""
        if inherited:
            hint = (
                f" NOTE: {', '.join(inherited)} IS set in this environment and is "
                "deliberately NOT used -- it belongs to a different account "
                "(the parent project's, which has been live). Set "
                f"{prefix}_KEY_ID / {prefix}_SECRET_KEY instead."
            )
        raise CredentialRefusal(
            f"No credentials for role {resolved!r}: set {prefix}_KEY_ID and "
            f"{prefix}_SECRET_KEY.{hint}"
        )
    return Credentials(key_id=key_id, secret_key=secret, role=resolved)


def base_url() -> str:
    """The paper trading host. Allowlisted, not defaulted."""
    url = os.getenv("AAT_TRADING_BASE", "https://paper-api.alpaca.markets").rstrip("/")
    _require_host(url, _ALLOWED_TRADING_HOSTS, "trading")
    return url


def data_url() -> str:
    """The market data host. Read-only, still allowlisted."""
    url = os.getenv("AAT_DATA_BASE", "https://data.alpaca.markets").rstrip("/")
    _require_host(url, _ALLOWED_DATA_HOSTS, "market data")
    return url


def _require_host(url: str, allowed: frozenset[str], kind: str) -> None:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise EndpointRefusal(f"{kind} host must be https, got {url!r}.")
    if parsed.hostname not in allowed:
        raise EndpointRefusal(
            f"Refusing {kind} host {parsed.hostname!r}. Allowed: {sorted(allowed)}. "
            "This repo has no live-trading path and this refusal is not "
            "configurable -- the only reason to override it is the reason it exists."
        )


def known_roles() -> list[str]:
    """Roles that actually have credentials in this environment."""
    seen = set()
    for key in os.environ:
        if key.startswith("AAT_") and key.endswith("_KEY_ID"):
            name = key[len("AAT_"):-len("_KEY_ID")].lower()
            if _valid_role(name) and os.environ.get(key, "").strip():
                seen.add(name)
    return sorted(seen)


#: The competition's own facts, snapshotted from the rules page on 2026-08-25.
#: Kept here rather than in prose so a script can assert against them.
COMPETITION = {
    "kickoff_utc": "2026-08-28T15:00:00Z",
    "deadline_utc": "2026-09-04T15:00:00Z",
    "required_starting_equity": 100_000.0,
    "source": "https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon",
    "snapshot_date": "2026-08-25",
}
