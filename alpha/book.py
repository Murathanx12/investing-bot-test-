"""The BOOK: what is actually at risk, reconstructed from the venue and the ledger.

WHY THIS MODULE EXISTS
======================
Until 26 Aug the aggregate risk number the sizer saw was

        sum(cost_basis of every LONG option leg) / equity

which is the premium paid, not the risk carried. A credit spread or an iron
condor contributes a long wing that cost almost nothing and a short leg the sum
ignores -- so the dev book on 25 Aug carried two NVDA condors (15 + 19 units,
call-side width 10 and 7.5 points) whose true worst case was ~$20k, and the
risk function credited them with ~$5k. Every entry decision that day sized
against a ceiling that was not the ceiling.

The same defect, once more: `EVENT_NODE_CAP` (25% per scheduled event) was
accumulated in a dict that lived for one pass. Every pass started at zero and
the cap was a per-pass cap wearing a per-event name.

Both are the same mistake -- risk was a property of the PASS, not of the BOOK.
This module makes it a property of the book:

  1. Every `submitted` ledger row carries its legs, its per-unit max loss and
     its contract count. Rows are matched, oldest first, against the broker's
     open positions; a row whose legs are all still held is an OPEN STRUCTURE
     and contributes `max_loss_per_unit * contracts`.
  2. Position quantity the ledger cannot explain (the first TSLA straddle was
     recorded before legs were stamped; partial closes; anything sent by hand)
     is charged conservatively: a long leg at its cost basis; a short leg at
     the FULL WIDTH to the nearest protective long of the same right and
     expiry; a short leg with no protective long is UNBOUNDED, and an unbounded
     book refuses every new entry until a human looks at it.
  3. Exposure is also totalled per underlying and per EVENT NODE (the
     scheduled event a structure exists because of), so the node cap can be
     applied to what is already held, not just to what this pass proposes.

The ledger rows before 15:39 UTC on 25 Aug carry no `account_role`; they are
matched against whichever account actually holds their legs. A row is never
matched twice and never matched against a book that does not hold it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from alpha import ledger

logger = logging.getLogger(__name__)

MULT = 100.0


def decode_occ(symbol: str) -> tuple[str, str, float, str]:
    """`NVDA260828C00232500` -> ("NVDA", "C", 232.5, "2026-08-28")."""
    if len(symbol) <= 15:
        raise ValueError(f"{symbol!r} is not an OCC option symbol")
    root = symbol[:-15]
    yy, mm, dd = symbol[-15:-13], symbol[-13:-11], symbol[-11:-9]
    right = symbol[-9]
    strike = float(symbol[-8:]) / 1000.0
    return root, right, strike, f"20{yy}-{mm}-{dd}"


@dataclass
class OpenStructure:
    decision_id: str
    brain: str
    symbol: str                   # underlying
    kind: str
    contracts: int
    max_loss_per_unit: float
    entry_cost_per_unit: float | None
    legs: list[tuple[str, str, int]]
    event_node: str | None
    ts_utc: str
    account_role: str | None
    row: dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def max_loss_usd(self) -> float:
        return self.max_loss_per_unit * self.contracts


@dataclass
class Residual:
    """Position quantity no ledger row explains, and what it was charged."""
    symbol: str
    qty: float
    charge_usd: float
    how: str
    unbounded: bool = False


@dataclass
class BookRisk:
    equity: float
    structures: list[OpenStructure]
    residuals: list[Residual]
    unbounded: bool
    """True when a short leg has no protective long. The number is then a floor,
    and the correct reading of it is 'refuse'."""
    max_loss_usd: float
    by_underlying: dict[str, float]
    by_node: dict[str, float]
    premium_paid_usd: float
    """The OLD number, kept beside the new one so the two can be compared on
    every receipt. When they differ the difference is short premium."""

    @property
    def fraction(self) -> float:
        if self.equity <= 0:
            return 1.0
        if self.unbounded:
            return 1.0
        return self.max_loss_usd / self.equity

    def node_fraction(self, node: str | None) -> float:
        if node is None or self.equity <= 0:
            return 0.0
        return self.by_node.get(node, 0.0) / self.equity

    def summary(self) -> str:
        parts = [f"true max loss ${self.max_loss_usd:,.0f} = {self.fraction:.1%} of "
                 f"${self.equity:,.0f} (premium-paid view ${self.premium_paid_usd:,.0f}); "
                 f"{len(self.structures)} structures matched, {len(self.residuals)} residual legs"]
        if self.unbounded:
            parts.append("UNBOUNDED: a short leg has no protective long -- entries refused")
        if self.by_node:
            parts.append("nodes: " + ", ".join(f"{k} {v / self.equity:.1%}" for k, v in
                                               sorted(self.by_node.items())))
        return "; ".join(parts)


def is_share(symbol: str) -> bool:
    """An equity symbol, as opposed to an OCC option contract."""
    return not (len(symbol) >= 15 and symbol[-8:].isdigit())


def _open_option_positions(positions: list[dict]) -> dict[str, dict]:
    """Every open OPTION leg and every open SHARE position, by symbol.

    Shares are legs too (`alpha/engine/equity.py`): a ledger row whose single
    leg is `("NVDA", "buy", 1)` x 120 is matched against 120 held shares exactly
    as a straddle row is matched against its two contracts."""
    out = {}
    for pos in positions:
        cls = pos.get("asset_class") or ""
        sym = pos.get("symbol") or ""
        if cls == "us_option":
            try:
                decode_occ(sym)
            except ValueError:
                continue
        elif cls != "us_equity" or not sym:
            continue
        out[sym] = {
            "qty": float(pos.get("qty") or 0.0),
            "cost_basis": abs(float(pos.get("cost_basis") or 0.0)),
            "avg_entry_price": float(pos.get("avg_entry_price") or 0.0),
            "share": cls == "us_equity",
        }
    return out


def _signed_leg_qty(side: str, ratio: int, contracts: int) -> float:
    return (1.0 if side == "buy" else -1.0) * ratio * contracts


def _event_node_of(row: dict) -> str | None:
    outcome = row.get("outcome") or {}
    node = outcome.get("event_node")
    if node:
        return node
    return None


def submitted_rows(rows: list[dict] | None = None) -> list[dict]:
    rows = rows if rows is not None else ledger.read_all()
    return [r for r in rows if r.get("action") == "submitted" and (r.get("legs") or [])]


def reconstruct(positions: list[dict], *, equity: float, account_role: str | None,
                rows: list[dict] | None = None) -> BookRisk:
    """Match ledger structures against the broker's open legs; charge the rest."""
    open_legs = _open_option_positions(positions)
    remaining = {sym: p["qty"] for sym, p in open_legs.items()}
    premium_paid = sum(p["cost_basis"] for p in open_legs.values()
                       if p["qty"] > 0 and not p.get("share"))

    structures: list[OpenStructure] = []
    # Rows stamped with THIS account's role are unambiguous and go first. Rows
    # from before the stamp existed (25 Aug < 15:39 UTC) could belong to either
    # account; they are tried afterwards, largest first, so a book holding 8 QQQ
    # straddles is explained by the x8 row and not by a x4 row that belongs to
    # the other account.
    pool = submitted_rows(rows)
    stamped = sorted((r for r in pool if r.get("account_role") == account_role),
                     key=lambda r: r.get("ts_utc") or "")
    unstamped = sorted((r for r in pool if r.get("account_role") is None),
                       key=lambda r: (-int((r.get("order") or {}).get("qty") or 0),
                                      r.get("ts_utc") or ""))
    candidates = stamped + unstamped
    for row in candidates:
        role = row.get("account_role")
        order = row.get("order") or {}
        try:
            contracts = int(order.get("qty") or 0)
        except (TypeError, ValueError):
            contracts = 0
        mlpu = row.get("max_loss_per_unit")
        legs = [(str(l[0]), str(l[1]), int(l[2])) for l in (row.get("legs") or [])]
        if contracts < 1 or mlpu is None or mlpu <= 0 or not legs:
            continue
        # Every leg must still be held in the direction and size the row states.
        fits = True
        for sym, side, ratio in legs:
            need = _signed_leg_qty(side, ratio, contracts)
            have = remaining.get(sym, 0.0)
            if need > 0 and have < need - 1e-9:
                fits = False
            if need < 0 and have > need + 1e-9:
                fits = False
            if not fits:
                break

        # PARTIAL FILLS. A single-leg SHARE row is matched at whatever the venue
        # actually holds, because an entry limit is DAY and fills partially all
        # the time. Before this, a row for 120 shares against a 60-share fill
        # failed to match and became a residual -- and a residual SHORT share
        # position is scored UNBOUNDED, which refuses every subsequent entry in
        # the account for the rest of the day (`runner.run_pass`). So a routine
        # partial fill silently halted the whole book. (Audit defect 5.)
        #
        # Deliberately single-leg only: an option STRUCTURE matched at partial
        # size is not the same structure -- half an iron condor is two naked
        # legs and a different worst case -- so those still fail to match and
        # are explained as residuals, which is the correct, loud outcome.
        if not fits and len(legs) == 1 and is_share(legs[0][0]):
            sym, side, ratio = legs[0]
            need = _signed_leg_qty(side, ratio, contracts)
            have = remaining.get(sym, 0.0)
            filled = int(min(abs(need), abs(have)) / max(1, abs(ratio)))
            if filled >= 1 and (need > 0) == (have > 0):
                contracts, fits = filled, True
        if not fits:
            continue
        for sym, side, ratio in legs:
            remaining[sym] -= _signed_leg_qty(side, ratio, contracts)
        try:
            underlying = decode_occ(legs[0][0])[0]
        except ValueError:
            underlying = row.get("symbol") or ""
        structures.append(OpenStructure(
            decision_id=row.get("decision_id", ""), brain=row.get("brain", ""),
            symbol=underlying, kind=row.get("instrument", ""), contracts=contracts,
            max_loss_per_unit=float(mlpu), entry_cost_per_unit=row.get("entry_cost_per_unit"),
            legs=legs, event_node=_event_node_of(row), ts_utc=row.get("ts_utc", ""),
            account_role=role, row=row,
        ))

    residuals: list[Residual] = []
    unbounded = False
    # Residual longs first: they are both a charge and the protection for residual shorts.
    long_left = {s: q for s, q in remaining.items() if q > 1e-9}
    short_left = {s: -q for s, q in remaining.items() if q < -1e-9}
    for sym, qty in sorted(short_left.items()):
        if is_share(sym):
            # Short shares no ledger row explains: nothing declared their stop,
            # so nothing bounds them. The book is unbounded until someone looks.
            unbounded = True
            residuals.append(Residual(sym, -qty, float("inf"),
                                      "short SHARES with no ledger row -- no declared stop, unbounded", True))
            continue
        root, right, strike, expiry = decode_occ(sym)
        protectors = []
        for lsym, lq in long_left.items():
            lroot, lright, lstrike, lexp = decode_occ(lsym)
            if lroot != root or lright != right or lexp != expiry or lq <= 1e-9:
                continue
            if (right == "C" and lstrike > strike) or (right == "P" and lstrike < strike):
                protectors.append((abs(lstrike - strike), lsym, lq))
        protectors.sort()
        covered = 0.0
        charge = 0.0
        for width, lsym, lq in protectors:
            take = min(qty - covered, lq)
            if take <= 0:
                break
            charge += width * MULT * take
            long_left[lsym] -= take
            covered += take
            if covered >= qty - 1e-9:
                break
        if covered < qty - 1e-9:
            unbounded = True
            residuals.append(Residual(sym, -(qty - covered), float("inf"),
                                      "short leg with NO protective long -- unbounded", True))
        if covered > 0:
            residuals.append(Residual(sym, -covered, charge,
                                      f"short leg charged at full width to its protective long"))
    for sym, qty in sorted(long_left.items()):
        if qty <= 1e-9:
            continue
        pos = open_legs.get(sym, {})
        if pos.get("share"):
            from alpha.engine.equity import MAX_LOSS_FRACTION

            per = (pos.get("avg_entry_price") or 0.0) * MAX_LOSS_FRACTION
            residuals.append(Residual(sym, qty, per * qty,
                                      f"unmatched long SHARES at the declared {MAX_LOSS_FRACTION:.0%} stop+gap"))
            continue
        per = (pos.get("avg_entry_price") or 0.0) * MULT
        residuals.append(Residual(sym, qty, per * qty, "unmatched long leg at cost basis"))

    total = sum(s.max_loss_usd for s in structures) + sum(
        r.charge_usd for r in residuals if not r.unbounded)
    by_underlying: dict[str, float] = {}
    by_node: dict[str, float] = {}
    for s in structures:
        by_underlying[s.symbol] = by_underlying.get(s.symbol, 0.0) + s.max_loss_usd
        if s.event_node:
            by_node[s.event_node] = by_node.get(s.event_node, 0.0) + s.max_loss_usd
    for r in residuals:
        if r.unbounded:
            continue
        root = r.symbol if is_share(r.symbol) else decode_occ(r.symbol)[0]
        by_underlying[root] = by_underlying.get(root, 0.0) + r.charge_usd
    return BookRisk(equity=equity, structures=structures, residuals=residuals,
                    unbounded=unbounded, max_loss_usd=total, by_underlying=by_underlying,
                    by_node=by_node, premium_paid_usd=premium_paid)


def read(client, *, account_role: str | None = None, rows: list[dict] | None = None) -> BookRisk:
    """The live book of this client, reconstructed. One venue round-trip per call."""
    import os

    acct = client.account()
    equity = float(acct.get("equity") or 0.0)
    role = account_role if account_role is not None else (
        os.getenv("AAT_ACCOUNT_ROLE", "").strip().lower() or None)
    book = reconstruct(client.positions(), equity=equity, account_role=role, rows=rows)
    logger.info("book: %s", book.summary())
    return book
