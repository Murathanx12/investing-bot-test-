"""P&L ATTRIBUTION for every open structure -- why a position is red, not just that it is.

    P&L  =  delta * dS  +  1/2 gamma * dS^2  +  vega * d(sigma)  +  theta * dt
            + spread paid at entry  +  residual

computed per leg from Black-Scholes at the ENTRY snapshot (the ledger row keeps
every leg's IV, delta and the spot it was priced against) and summed per
structure. The NVDA condors on 25 Aug were red on rising IV into the print --
vega against a short-vol position, which is the position working as designed,
not the outcome. Reading "-$981" without the decomposition would have closed
them on a mark and crystallised the premium they were opened to collect.

Realised vs unrealised are separated at the ACCOUNT level: the venue reports
unrealised P&L per position; realised is what equity has moved net of that.

Nothing here decides. The arbiter (`alpha/arbiter.py`) reads it.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from alpha import book as book_mod
from alpha.data.chain import _bs_greeks, _bs_price

logger = logging.getLogger(__name__)

MULT = 100.0
STARTING_EQUITY = 100_000.0


@dataclass
class LegAttribution:
    symbol: str
    side: str
    qty: float
    entry_price: float
    mark: float
    iv_entry: float | None
    iv_now: float | None
    actual_usd: float
    delta_usd: float = 0.0
    gamma_usd: float = 0.0
    vega_usd: float = 0.0
    theta_usd: float = 0.0
    spread_usd: float = 0.0
    residual_usd: float = 0.0
    note: str = ""


@dataclass
class StructureAttribution:
    decision_id: str
    brain: str
    symbol: str
    kind: str
    contracts: int
    event_node: str | None
    spot_entry: float | None
    spot_now: float | None
    actual_usd: float
    delta_usd: float
    gamma_usd: float
    vega_usd: float
    theta_usd: float
    spread_usd: float
    residual_usd: float
    max_loss_usd: float
    legs: list[LegAttribution] = field(default_factory=list)
    net_delta_shares: float = 0.0
    """Share-equivalent delta of the whole structure right now (BS at current IV)."""
    net_vega_usd_per_pt: float = 0.0

    def as_dict(self) -> dict:
        d = asdict(self)
        return d

    def line(self) -> str:
        return (f"{self.symbol:5s} {self.kind:16s} x{self.contracts:<3d} {self.brain[:12]:12s} "
                f"P&L {self.actual_usd:+8,.0f} = d {self.delta_usd:+7,.0f} g {self.gamma_usd:+6,.0f} "
                f"v {self.vega_usd:+7,.0f} t {self.theta_usd:+6,.0f} spr {self.spread_usd:+6,.0f} "
                f"res {self.residual_usd:+6,.0f} | maxloss {self.max_loss_usd:,.0f}")


def implied_vol(price: float, s: float, k: float, t: float, right: str) -> float | None:
    """Bisection on Black-Scholes. None when the price is outside no-arbitrage bounds."""
    if price <= 0 or s <= 0 or t <= 0:
        return None
    intrinsic = max(0.0, s - k) if right == "C" else max(0.0, k - s)
    if price < intrinsic - 1e-9:
        return None
    lo, hi = 1e-4, 5.0
    if _bs_price(s, k, t, hi, right) < price:
        return None
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if _bs_price(s, k, t, mid, right) < price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _years(expiry: str, at: datetime) -> float:
    exp = datetime.fromisoformat(expiry + "T20:00:00+00:00")
    return max(0.0, (exp - at).total_seconds() / (365.0 * 86400.0))


def attribute_structure(struct: book_mod.OpenStructure, positions_by_symbol: dict[str, dict],
                        spot_now: float | None, *, now: datetime | None = None) -> StructureAttribution:
    now = now or datetime.now(timezone.utc)
    row = struct.row or {}
    snap = row.get("quote_snapshot") or {}
    entry_legs = {l.get("symbol"): l for l in (snap.get("legs") or [])}
    spot_entry = snap.get("spot")
    entry_ts = row.get("ts_utc")
    try:
        t_entry = datetime.fromisoformat(entry_ts) if entry_ts else now
        if t_entry.tzinfo is None:
            t_entry = t_entry.replace(tzinfo=timezone.utc)
    except ValueError:
        t_entry = now
    days = max(0.0, (now - t_entry).total_seconds() / 86400.0)

    out = StructureAttribution(
        decision_id=struct.decision_id, brain=struct.brain, symbol=struct.symbol, kind=struct.kind,
        contracts=struct.contracts, event_node=struct.event_node, spot_entry=spot_entry,
        spot_now=spot_now, actual_usd=0.0, delta_usd=0.0, gamma_usd=0.0, vega_usd=0.0,
        theta_usd=0.0, spread_usd=0.0, residual_usd=0.0, max_loss_usd=struct.max_loss_usd,
    )
    for sym, side, ratio in struct.legs:
        pos = positions_by_symbol.get(sym) or {}
        sign = 1.0 if side == "buy" else -1.0
        qty = ratio * struct.contracts
        entry = entry_legs.get(sym) or {}
        entry_px = float(pos.get("avg_entry_price") or 0.0) or float(
            (entry.get("ask") if side == "buy" else entry.get("bid")) or 0.0)
        mark = float(pos.get("current_price") or 0.0)
        if book_mod.is_share(sym):
            # A share is all delta: one unit, no greeks, the spread is the half bid-ask.
            actual = sign * qty * (mark - entry_px)
            leg = LegAttribution(sym, side, sign * qty, entry_px, mark, None, None, actual)
            mid0 = None
            if entry.get("bid") is not None and entry.get("ask") is not None:
                mid0 = 0.5 * (float(entry["bid"]) + float(entry["ask"]))
            leg.spread_usd = -abs(entry_px - mid0) * qty if mid0 is not None else 0.0
            leg.delta_usd = actual - leg.spread_usd
            leg.note = "shares: delta only"
            out.net_delta_shares += sign * qty
            out.legs.append(leg)
            out.actual_usd += actual
            out.delta_usd += leg.delta_usd
            out.spread_usd += leg.spread_usd
            continue
        actual = sign * qty * (mark - entry_px) * MULT
        leg = LegAttribution(sym, side, sign * qty, entry_px, mark, entry.get("iv"), None, actual)
        _, right, strike, expiry = book_mod.decode_occ(sym)
        iv0 = entry.get("iv")
        if spot_entry and iv0 and spot_now:
            t0 = _years(expiry, t_entry)
            t1 = _years(expiry, now)
            g0 = _bs_greeks(spot_entry, strike, t0, iv0, right)
            iv1 = implied_vol(mark, spot_now, strike, t1, right) if mark > 0 and t1 > 0 else None
            ds = spot_now - spot_entry
            leg.iv_now = iv1
            leg.delta_usd = sign * qty * g0["delta"] * ds * MULT
            leg.gamma_usd = sign * qty * 0.5 * g0["gamma"] * ds * ds * MULT
            leg.vega_usd = sign * qty * g0["vega"] * ((iv1 - iv0) * 100.0 if iv1 is not None else 0.0) * MULT
            leg.theta_usd = sign * qty * g0["theta"] * days * MULT
            mid0 = entry.get("adjusted_mid")
            if mid0 is None and entry.get("bid") is not None and entry.get("ask") is not None:
                mid0 = 0.5 * (entry["bid"] + entry["ask"])
            if mid0 is not None:
                leg.spread_usd = -abs(entry_px - mid0) * qty * MULT
            leg.residual_usd = actual - (leg.delta_usd + leg.gamma_usd + leg.vega_usd + leg.theta_usd + leg.spread_usd)
            if iv1 is None:
                leg.note = "current IV not invertible from the mark; vega term is zero and lands in residual"
            g1 = _bs_greeks(spot_now, strike, t1, iv1 if iv1 else iv0, right)
            out.net_delta_shares += sign * qty * g1["delta"] * MULT
            out.net_vega_usd_per_pt += sign * qty * g1["vega"] * MULT
        else:
            leg.note = "no entry IV/spot in the ledger snapshot; actual only"
            leg.residual_usd = actual
        out.legs.append(leg)
        out.actual_usd += actual
        out.delta_usd += leg.delta_usd
        out.gamma_usd += leg.gamma_usd
        out.vega_usd += leg.vega_usd
        out.theta_usd += leg.theta_usd
        out.spread_usd += leg.spread_usd
        out.residual_usd += leg.residual_usd
    return out


def spots(client, symbols: list[str]) -> dict[str, float]:
    if not symbols:
        return {}
    try:
        raw = client.latest_trade(sorted(set(symbols)))
    except Exception as exc:                                             # noqa: BLE001
        logger.warning("latest_trade failed: %s", exc)
        return {}
    trades = raw.get("trades") or {}
    out = {}
    for sym, t in trades.items():
        px = t.get("p")
        if px:
            out[sym] = float(px)
    return out


def attribute_book(client, *, account_role: str | None = None, now: datetime | None = None) -> dict:
    """Every open structure attributed; the account's realised/unrealised split on top."""
    acct = client.account()
    equity = float(acct.get("equity") or 0.0)
    positions = client.positions()
    by_symbol = {p.get("symbol"): p for p in positions}
    bk = book_mod.reconstruct(positions, equity=equity, account_role=account_role)
    spot_now = spots(client, [s.symbol for s in bk.structures])
    structs = [attribute_structure(s, by_symbol, spot_now.get(s.symbol), now=now) for s in bk.structures]
    unrealised = sum(float(p.get("unrealized_pl") or 0.0) for p in positions)
    realised = equity - STARTING_EQUITY - unrealised
    return {
        "generated_utc": (now or datetime.now(timezone.utc)).isoformat(),
        "account_role": account_role,
        "equity": equity,
        "starting_equity": STARTING_EQUITY,
        "unrealised_usd": unrealised,
        "realised_usd": realised,
        "book": {"true_max_loss_usd": bk.max_loss_usd, "fraction": bk.fraction,
                 "premium_paid_usd": bk.premium_paid_usd, "unbounded": bk.unbounded,
                 "residual_legs": [asdict(r) for r in bk.residuals if not math.isinf(r.charge_usd)],
                 "unbounded_legs": [r.symbol for r in bk.residuals if r.unbounded]},
        "totals": {
            k: sum(getattr(s, k) for s in structs)
            for k in ("actual_usd", "delta_usd", "gamma_usd", "vega_usd", "theta_usd", "spread_usd", "residual_usd")
        },
        "structures": [s.as_dict() for s in structs],
        "_structs": structs,
    }
