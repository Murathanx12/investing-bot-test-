"""THE FIVE EQUITY CURVES, RE-DERIVED FROM THE VENUE. Read-only, by construction.

WHY THIS FILE EXISTS AT ALL
===========================
`scripts/allocator.py` marks a curve by APPENDING one equity a day to
`state/allocator/curves/<role>.jsonl`. That is the right shape for a machine
with a disk. The seal authority has **no Railway volume** (`docs/HANDOFF.md`:
"seal-authority (no volume, so the redeploy ...")): it rebuilds from the image
on every boot, so an appended curve would be silently truncated to "since the
last deploy" -- and a drawdown measured from a peak that a reboot deleted is not
a drawdown, it is a smaller number that looks like good news.

So the allocator running inside the authority does not accumulate. It asks the
venue for each account's own daily equity series every day
(`GET /v2/account/portfolio/history`, fields `timestamp[]` epoch-seconds and
`equity[]`, parallel -- Alpaca's reference, verified 2026-09-13), and a reboot
loses nothing because nothing was being kept.

WHY IT IS NOT IN `scripts/allocator.py`
=======================================
`tests_smoke_allocator.py` greps `alpha/allocator.py` and `scripts/allocator.py`
for `alpha.broker`, `submit` and `/v2/orders` and fails if any appears -- the
pin that says the allocator has no order path. Putting a venue client in either
file would have made that pin go red, and relaxing a pin to make a run start is
the failure mode this repository names most often. The venue reader gets its own
file instead.

WHICH DOOR THE CREDENTIALS COME THROUGH, AND WHY THERE ARE TWO
==============================================================
`config.credentials(for_role=X)` REFUSES when `AAT_ACCOUNT_ROLE` names a
different role (audit defect 6: orders to one account, ledger rows under
another's name). The authority runs under `AAT_ACCOUNT_ROLE=hack3`
(`docs/RUNBOOK_2026-09-08_REARM.md` C.0), so four of the five reads would hit
that refusal.

Both doors are used, and the row says which:

  * `config.credentials(for_role=r)` when the process's declared role already IS
    `r` (or is unset) -- the ordinary door, and the one the chunk asked for;
  * `config.peer_credentials(r)` otherwise -- the door `alpha/crossbook.py`
    opened for exactly this case, "a cross-book READ is the single legitimate
    disagreement, so it gets a door of its own instead of widening that one".

Neither door is widened here and `AAT_ACCOUNT_ROLE` is never mutated. An earlier
draft set it per role around each read; in a long-lived server thread that
re-stamps whatever the maintainer does next, which is the same bug
`config.credentials` documents at its own line 290.

THE REFUSAL THIS FILE OWNS
==========================
**A role whose account number differs from the anchor's is refused BY NAME and
its curve is dropped.** Every other piece of state in this repo is keyed by
ROLE (`alpha/genesis.py`'s warning), so a role re-pointed at a fresh account --
which is what Alpaca's "reset" does, since it is delete-and-recreate and rotates
the keys -- would carry the old account's peak forward under the same label and
inherit a drawdown that belongs to money that no longer exists.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

from alpha import allocator as A

#: Days of history asked for. 1M is Alpaca's default; the trial's horizon is 60
#: sessions and the drawdown is measured from the book's own peak SINCE THE
#: ANCHOR, so the window must comfortably cover anchor-to-today. 6M does, and
#: the payload is two float arrays.
HISTORY_PERIOD = "6M"
HISTORY_TIMEFRAME = "1D"

try:                                                            # pragma: no cover
    from zoneinfo import ZoneInfo as _ZI
    _ZONE_ET = _ZI("America/New_York")
except Exception:                                               # noqa: BLE001
    _ZONE_ET = _dt.timezone(_dt.timedelta(hours=-4))


class VenueRead(Exception):
    """This role's equity could not be read. Never silently a number."""


def _reader(role: str):
    """A client for `role` that this module can only READ with.

    Built the way `alpha/crossbook.open_peer` builds one -- `__new__` plus
    `object.__setattr__` -- because `AlpacaPaper.__post_init__` calls
    `config.credentials(self.role)` and would hit the role-disagreement refusal
    before the object existed. Returns `(client, door)`.
    """
    import os

    from alpha import config
    from alpha.broker.alpaca import AlpacaPaper

    r = (role or "").strip().lower()
    declared = (os.getenv("AAT_ACCOUNT_ROLE") or "").strip().lower()
    if not declared or declared == r:
        creds, door = config.credentials(for_role=r), "config.credentials"
    else:
        creds, door = config.peer_credentials(r), "config.peer_credentials"
    client = AlpacaPaper.__new__(AlpacaPaper)
    object.__setattr__(client, "role", r)
    object.__setattr__(client, "timeout", 20.0)
    object.__setattr__(client, "_creds", creds)
    object.__setattr__(client, "_verified", False)
    return client, door


def curve_from_history(payload: dict, *, account: str | None = None) -> list[dict]:
    """`{timestamp[], equity[]}` -> the allocator's `[{day, equity}, ...]`.

    ONE MARK PER DAY, the LAST one on that date, mirroring
    `scripts.allocator.load_curve`: a second observation on one day is a
    correction, not a second observation, and counting it twice inflates every
    block count downstream. Zero and null equities are DROPPED rather than
    carried as 0.0 -- a zero equity is how a history payload says "before this
    account existed", and a book whose curve starts at 0 is a book at a
    +infinity drawdown-from-trough and a 100% drawdown-from-peak.
    """
    stamps = list(payload.get("timestamp") or [])
    equities = list(payload.get("equity") or [])
    if len(stamps) != len(equities):
        raise VenueRead(f"history arrays disagree: {len(stamps)} timestamps vs "
                        f"{len(equities)} equities -- refusing rather than zipping "
                        f"a curve to the shorter of the two")
    by_day: dict[str, float] = {}
    for ts, eq in zip(stamps, equities):
        if eq is None:
            continue
        try:
            value = float(eq)
        except (TypeError, ValueError):
            continue
        if value <= 0.0:
            continue
        day = _dt.datetime.fromtimestamp(int(ts), _dt.timezone.utc).astimezone(
            _ZONE_ET).date().isoformat()
        by_day[day] = value
    rows = [{"day": d, "equity": by_day[d], "source": "venue portfolio history"}
            for d in sorted(by_day)]
    if account:
        for r in rows:
            r["account"] = account
    return rows


def read_role(role: str, *, anchor: dict | None = None) -> dict:
    """`{role, account, equity, curve, door}` or `{role, why}`. Never raises.

    `equity` is the LAST point of the venue's own daily history, not
    `/v2/account`'s live `equity`: the two disagree intraday, and the allocator
    marks CLOSES. The account number comes from `/v2/account` because the
    history payload does not carry one, and it is checked against the anchor.
    """
    r = (role or "").strip().lower()
    try:
        client, door = _reader(r)
    except Exception as exc:                                     # noqa: BLE001
        return {"role": r, "equity": None, "curve": [],
                "why": f"no credentials: {type(exc).__name__}: {str(exc)[:160]}"}
    try:
        acct = client.account()                     # also asserts a 'PA' paper account
        number = str(acct.get("account_number") or "") or None
        expected = (((anchor or {}).get("books") or {}).get(r) or {}).get("account")
        if expected and number and str(expected) != number:
            return {"role": r, "equity": None, "curve": [], "account": number,
                    "why": (f"REFUSED BY NAME: {r} now answers on account {number} but "
                            f"the anchor recorded {expected}. Every other piece of state "
                            f"here is keyed by ROLE, so marking this curve would carry "
                            f"{expected}'s peak forward under {r}'s label. An Alpaca "
                            f"'reset' is delete-and-recreate: re-anchor on purpose or "
                            f"fix the key pair; this will not guess.")}
        payload = client.portfolio_history(period=HISTORY_PERIOD,
                                           timeframe=HISTORY_TIMEFRAME)
        curve = curve_from_history(payload, account=number)
    except Exception as exc:                                     # noqa: BLE001
        return {"role": r, "equity": None, "curve": [],
                "why": f"{type(exc).__name__}: {str(exc)[:160]}"}
    if not curve:
        return {"role": r, "equity": None, "curve": [], "account": number,
                "why": "the venue returned an EMPTY equity history; an empty curve and "
                       "an unread curve are different facts and neither is a number"}
    return {"role": r, "account": number, "equity": curve[-1]["equity"],
            "curve": curve, "door": door,
            "source": f"venue portfolio history {HISTORY_PERIOD}/{HISTORY_TIMEFRAME}"}


def read_fleet(roles: tuple[str, ...] = A.ROLES, *, anchor: dict | None = None) -> dict:
    """Every allocated role's curve, or the REASON that role has none."""
    return {r: read_role(r, anchor=anchor) for r in roles}


def curves_and_equities(fleet: dict) -> tuple[dict, dict, list[str]]:
    """`(curves, equities, notes)` in the shapes `alpha.allocator.allocate` wants."""
    curves: dict[str, list[dict]] = {}
    equities: dict[str, Any] = {}
    notes: list[str] = []
    for role, row in fleet.items():
        if row.get("equity") is None:
            curves[role] = []
            notes.append(f"{role}: NO MARK TODAY -- {row.get('why')}")
            continue
        curves[role] = [{"day": p["day"], "equity": p["equity"]} for p in row["curve"]]
        equities[role] = {"equity": row["equity"], "account": row.get("account"),
                          "source": row.get("source")}
    return curves, equities, notes
