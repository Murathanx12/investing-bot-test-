"""ONE BET, ONE INSTRUMENT -- what the OTHER books in the fleet already hold.

WHAT FRIDAY ACTUALLY WAS
========================
hack3 (basket) bought twelve theme names and hack5 (convexity) bought five
5-DTE OTM calls on the SAME theme names -- QS at a $6 strike on a $5.9 stock,
SMR at $10 on $9.7. The two accounts were reported as independent selectors.
They were one bet in two instruments, and they lost -8.9% and -8.6% on the same
afternoon. `alpha/drivers.py` bounds this WITHIN one account; nothing looked
across accounts, because nothing could.

WHY THIS IS HARDER THAN IT LOOKS, AND WHAT IT HONESTLY DELIVERS
===============================================================
An Alpaca account is reachable only with its own key pair, and
`scripts/fleet.py` deploys **one role's keys per Railway service** on purpose:
a bug or a compromise in the convexity loop must not be able to reach the
anchor book's account. That blast-radius choice is right and this module does
not ask to change it. The consequence is stated rather than papered over:

* **Locally / attended** (all six pairs in `.env`) the check is REAL. It reads
  the peers' positions and refuses the overlap.
* **On Railway** the peers are UNREADABLE, and this returns exactly that. The
  decision row then carries `cross_book: CANNOT DETERMINE` with the peer named.

`CANNOT DETERMINE` does not refuse. That is deliberate and it is the same
judgement the project made about `monday_gate_check`: a gate that can never go
green is a broken gate, not a strict one, and refusing every convex entry
forever on a check the deployment structurally cannot perform would silently
retire the account rather than protect it. The state is made LOUD instead --
in the metrics, in the pass log, and in `scripts.fleet --overlap`, which runs
where the keys are and prints the fleet's real overlap as a number.

READ ONLY, AND STRUCTURALLY SO
==============================
Peer credentials reach a `PeerBook` that exposes `positions()` and NOTHING
else -- no submit, no cancel, no close. A comment saying "we only read here"
is worth nothing next to an object that cannot do anything else, and this is
the one place in the repo where a process holds another account's keys.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Profiles whose books express a thesis in SHARES. A convex book must not buy
#: premium on a name one of these already holds outright.
SHARE_EXPRESSING_PROFILES = frozenset({"conservative", "aggressive", "maximum", "basket"})


class PeerBook:
    """Another account's positions. It can do nothing else, by construction."""

    __slots__ = ("role", "_client")

    def __init__(self, role: str, client) -> None:
        self.role = role
        self._client = client

    def positions(self) -> list[dict]:
        return self._client.positions()


def peer_roles(role: str | None) -> list[str]:
    """Fleet roles whose mandate holds shares, excluding `role` itself."""
    from alpha import fleet

    me = str(role or "").strip().lower()
    return sorted(r for r, m in fleet.FLEET.items()
                  if r != me and m.profile in SHARE_EXPRESSING_PROFILES)


def open_peer(role: str) -> PeerBook | None:
    """A read-only handle on `role`'s book, or None when this process has no key.

    Goes through `config.peer_credentials`, NOT `config.credentials`: the latter
    refuses when `AAT_ACCOUNT_ROLE` disagrees with the role asked for, and that
    refusal is exactly right for the ORDER path -- it is what stops orders going
    to one account while their rows are written under another's name. A peer
    read is the one legitimate disagreement, so it uses a door of its own rather
    than widening that one.
    """
    from alpha import config
    from alpha.broker.alpaca import AlpacaPaper

    try:
        creds = config.peer_credentials(role)
    except Exception:                                                   # noqa: BLE001
        return None
    client = AlpacaPaper.__new__(AlpacaPaper)
    object.__setattr__(client, "role", role)
    object.__setattr__(client, "timeout", 15.0)
    object.__setattr__(client, "_creds", creds)
    object.__setattr__(client, "_verified", False)
    return PeerBook(role, client)


def held_by_peers(role: str | None, *, opener=open_peer) -> tuple[set[str], list[str]]:
    """(underlyings held by peer books, notes). Never raises.

    A peer we cannot read is NAMED in the notes. A peer we can read but whose
    positions call fails is also named, and with its error -- an empty set from
    a failed read and an empty set from an empty book are different facts and
    must not print alike.
    """
    from alpha import concentration

    held: set[str] = set()
    notes: list[str] = []
    for peer in peer_roles(role):
        book = opener(peer)
        if book is None:
            notes.append(f"UNREADABLE:{peer} (no key pair in this process)")
            continue
        try:
            rows = book.positions()
        except Exception as exc:                                        # noqa: BLE001
            notes.append(f"ERROR:{peer} ({type(exc).__name__})")
            continue
        syms = {concentration.underlying_of(str(p.get("symbol") or "").upper())
                for p in rows}
        syms.discard("")
        held |= syms
        notes.append(f"read:{peer} ({len(syms)} name(s))")
    return held, notes


def overlap_refusal(symbol: str, held: set[str], notes: list[str]) -> str | None:
    """The refusal line, or None. `held` empty with only UNREADABLE notes is
    NOT a pass -- the caller records the state; this returns None because there
    is nothing it can honestly refuse on."""
    sym = str(symbol or "").strip().upper()
    if sym and sym in held:
        return (f"CROSS-BOOK: {sym} is already held outright by another book in the fleet "
                f"({'; '.join(n for n in notes if n.startswith('read:'))}). On 28 Aug the "
                "basket book bought twelve theme names and the convex book bought 5-DTE calls "
                "on the same names; the two 'independent' selectors lost 8.9% and 8.6% on one "
                "afternoon. One bet, one instrument.")
    return None


def status(held: set[str], notes: list[str]) -> str:
    """What the check was actually able to see, for the decision row."""
    readable = [n for n in notes if n.startswith("read:")]
    if not readable:
        return ("CANNOT DETERMINE: no peer book was readable from this process ("
                + "; ".join(notes) + "). On Railway each service carries only its own "
                "key pair by design, so this check is real only where the keys are; "
                "run `python -m scripts.fleet --overlap` to measure it.")
    blind = [n for n in notes if not n.startswith("read:")]
    return (f"read {len(readable)} peer book(s), {len(held)} name(s) held"
            + (f"; BLIND to {len(blind)}: {'; '.join(blind)}" if blind else ""))
