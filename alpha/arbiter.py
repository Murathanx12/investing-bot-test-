"""POSITION_ARBITER_v1 -- HOLD / CLOSE / HEDGE from REMAINING edge, not entry P&L.

The exit rules in `alpha/exits.py` are stops and targets on a leg's unrealised
percentage. They are the right last line of defence and the wrong first one:
a short-premium structure marked red on pre-event IV lift is doing its job,
and a long straddle marked green with its catalyst already spent is not. Both
questions are about what the position is worth FROM HERE, and that is what
this module asks, per STRUCTURE, every management cycle:

    remaining_edge = E[value at expiry | our latest forecast] - liquidation value now

  HOLD   remaining edge is positive after the cost of closing; or the event the
         structure was opened for has not happened yet (a mark before the event
         is a mark of the market's nerves, not of the thesis);
  CLOSE  the venue pays more now than the forecast says the position is worth,
         by more than the round-trip spread;
  HEDGE  advisory: the structure has drifted directional -- its share-equivalent
         delta is large against its max loss -- and a delta-neutral thesis is
         now carrying a directional bet it never made.
  SWITCH is NOT evaluated yet: it needs the alternative structures re-enumerated
         on the live chain, which is the entry pass's job. Said here so that a
         reader does not believe the arbiter compared against them.

MODES (env `AAT_ARBITER`):
  advise  (default) every verdict is written to the ledger as `arbiter_hold` /
          `arbiter_close` / `arbiter_hedge`; the exit rules act unchanged. The
          grade that promotes it accrues from these rows.
  act     an arbiter CLOSE closes the whole structure; an arbiter HOLD on a
          structure whose event is still pending overrides a leg-level stop.
  off     nothing runs.

The forecast used is the LATEST from the brain that opened the structure, read
from the forecasts ledger. A brain that has not forecast the symbol since entry
still has its entry forecast. A brain that forecasts wrongly will hold wrongly
-- which is why this starts in advise and is graded before it acts.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from alpha import book as book_mod
from alpha import ledger
from alpha.engine import payoff, sizing

logger = logging.getLogger(__name__)

MULT = 100.0

#: A structure whose share-equivalent delta, moved by one sigma of the
#: forecast, would swing more than this fraction of its max loss is directional
#: -- and if its brain's forecast was two-sided, that is a hedge advisory.
HEDGE_DELTA_FRACTION = 0.35


def mode() -> str:
    m = os.getenv("AAT_ARBITER", "advise").strip().lower()
    return m if m in ("advise", "act", "off") else "advise"


@dataclass(frozen=True)
class ArbiterVerdict:
    decision_id: str
    symbol: str
    kind: str
    brain: str
    action: str                 # HOLD | CLOSE | HEDGE
    reason: str
    remaining_edge_usd: float
    expected_terminal_usd: float
    liquidation_usd: float
    close_cost_usd: float
    event_pending: bool
    net_delta_shares: float
    forecast_centre: float | None
    forecast_sd: float | None
    forecast_ts: str | None

    def as_dict(self) -> dict:
        return asdict(self)


def latest_forecast(symbol: str, brain: str, rows: list[dict] | None = None) -> dict | None:
    rows = rows if rows is not None else ledger.read_all("forecasts")
    best = None
    for r in rows:
        if r.get("symbol") != symbol or r.get("brain") != brain or r.get("predicted_sd") in (None, 0):
            continue
        if best is None or (r.get("ts_utc") or "") > (best.get("ts_utc") or ""):
            best = r
    return best


def _event_pending(struct: book_mod.OpenStructure, forecast: dict | None, today: str,
                   *, all_forecasts: list[dict] | None = None) -> bool:
    """Is the event this structure sits on still ahead of us?

    Three sources, any one suffices: the structure's own event node; its brain's
    forecast evidence; and ANY brain's latest forecast for the symbol carrying
    an `event_date` on or after today -- vol_gap opened the NVDA condors on
    25 Aug with no event in its evidence, and event_move knew the print was on
    the 26th. The book does not care which brain knew.
    """
    node = struct.event_node or ""
    if node.startswith("print:") and node[6:] >= today:
        return True
    ev = ((forecast or {}).get("outcome") or {}).get("evidence") or {}
    date = ev.get("event_date")
    if date and str(date) >= today:
        return True
    latest: dict[str, dict] = {}
    for r in all_forecasts or []:
        if r.get("symbol") != struct.symbol:
            continue
        b = r.get("brain") or ""
        if b not in latest or (r.get("ts_utc") or "") > (latest[b].get("ts_utc") or ""):
            latest[b] = r
    for r in latest.values():
        d = (((r.get("outcome") or {}).get("evidence") or {}).get("event_date"))
        if d and str(d) >= today:
            _, _, _, expiry = book_mod.decode_occ(struct.legs[0][0])
            if str(d) <= expiry:
                return True
    return False


def _structure_for(struct: book_mod.OpenStructure, now: datetime) -> sizing.Structure:
    _, _, _, expiry = book_mod.decode_occ(struct.legs[0][0])
    exp = datetime.fromisoformat(expiry + "T20:00:00+00:00")
    dte = max(0.01, (exp - now).total_seconds() / 86400.0)
    row = struct.row or {}
    entry_cost = float(struct.entry_cost_per_unit if struct.entry_cost_per_unit is not None else 0.0)
    return sizing.Structure(
        symbol=struct.symbol, kind=struct.kind, direction="both",
        entry_cost=entry_cost, max_loss=struct.max_loss_per_unit,
        breakeven_move=float(row.get("breakeven_move") or 0.0),
        implied_move=float(row.get("implied_move") or 0.0),
        quote_spread_pct=_entry_spread_pct(row), days_to_expiry=dte,
        legs=tuple(struct.legs),
    )


def _entry_spread_pct(row: dict) -> float:
    legs = ((row.get("quote_snapshot") or {}).get("legs") or [])
    tot, n = 0.0, 0
    for l in legs:
        b, a = l.get("bid"), l.get("ask")
        if b and a and (a + b) > 0:
            tot += (a - b) / (0.5 * (a + b))
            n += 1
    return tot / n if n else 0.10


def judge(struct: book_mod.OpenStructure, positions_by_symbol: dict[str, dict], spot_now: float | None,
          *, forecast: dict | None, now: datetime | None = None,
          net_delta_shares: float = 0.0, all_forecasts: list[dict] | None = None) -> ArbiterVerdict:
    now = now or datetime.now(timezone.utc)
    today = now.date().isoformat()
    pending = _event_pending(struct, forecast, today, all_forecasts=all_forecasts)
    liquidation = 0.0
    marks_ok = True
    for sym, side, ratio in struct.legs:
        pos = positions_by_symbol.get(sym) or {}
        mark = float(pos.get("current_price") or 0.0)
        if mark <= 0 and side == "buy":
            marks_ok = False
        liquidation += (1.0 if side == "buy" else -1.0) * ratio * struct.contracts * mark * MULT
    base = dict(decision_id=struct.decision_id, symbol=struct.symbol, kind=struct.kind,
                brain=struct.brain, liquidation_usd=liquidation, event_pending=pending,
                net_delta_shares=net_delta_shares,
                forecast_centre=(forecast or {}).get("predicted_move"),
                forecast_sd=(forecast or {}).get("predicted_sd"),
                forecast_ts=(forecast or {}).get("ts_utc"))
    if forecast is None or not spot_now or not marks_ok:
        why = ("no forecast on record from this brain for this symbol" if forecast is None else
               "no current spot" if not spot_now else "a long leg has no mark")
        return ArbiterVerdict(action="HOLD", reason=f"cannot judge: {why}; the exit rules stand alone",
                              remaining_edge_usd=0.0, expected_terminal_usd=liquidation,
                              close_cost_usd=0.0, **base)
    s = _structure_for(struct, now)
    centre = float(forecast.get("predicted_move") or 0.0)
    sd = float(forecast.get("predicted_sd"))
    horizon = float(((forecast.get("outcome") or {}).get("horizon_days")) or s.days_to_expiry)
    econ = payoff.economics(s, spot_now, centre, sd, horizon_days=horizon)
    # economics.ev is per unit AFTER entry cost and spread; the expected terminal
    # VALUE is ev + entry_cost + spread, and the whole structure is `contracts` units.
    expected_terminal = (econ.ev_usd + s.entry_cost + econ.spread_cost_usd) * struct.contracts
    close_cost = abs(s.quote_spread_pct * liquidation) * 0.5
    remaining = expected_terminal - liquidation
    base.update(remaining_edge_usd=remaining, expected_terminal_usd=expected_terminal,
                close_cost_usd=close_cost)

    if pending:
        return ArbiterVerdict(action="HOLD", reason=(
            f"event pending ({struct.event_node or 'forecast event_date'}): a pre-event mark is the "
            f"market's nerves, not the thesis. Remaining edge {remaining:+,.0f} vs close cost "
            f"{close_cost:,.0f}; judged after the print."), **base)
    if remaining < -close_cost:
        return ArbiterVerdict(action="CLOSE", reason=(
            f"the venue pays ${liquidation:,.0f} now; the {struct.brain} forecast "
            f"({centre:+.2%} +/- {sd:.2%}) values expiry at ${expected_terminal:,.0f}. "
            f"Remaining edge {remaining:+,.0f} is below the close cost {close_cost:,.0f}: "
            "holding pays for the privilege of a worse expected exit."), **base)
    one_sigma_swing = abs(net_delta_shares) * spot_now * sd
    if s.direction == "both" and struct.kind in ("long_straddle", "iron_condor") and \
            struct.max_loss_usd > 0 and one_sigma_swing > HEDGE_DELTA_FRACTION * struct.max_loss_usd:
        return ArbiterVerdict(action="HEDGE", reason=(
            f"two-sided structure carrying {net_delta_shares:+,.0f} share-equivalent delta: a one-sigma "
            f"move swings ${one_sigma_swing:,.0f} = {one_sigma_swing / struct.max_loss_usd:.0%} of max "
            f"loss. Remaining edge {remaining:+,.0f} says hold the thesis; the delta is a bet it never "
            "made. (advisory -- no hedge is placed)"), **base)
    return ArbiterVerdict(action="HOLD", reason=(
        f"remaining edge {remaining:+,.0f} after close cost {close_cost:,.0f}: expiry under the "
        f"{struct.brain} forecast ({centre:+.2%} +/- {sd:.2%}) is worth ${expected_terminal:,.0f} "
        f"against ${liquidation:,.0f} now."), **base)


def judge_book(client, *, account_role: str | None = None, now: datetime | None = None,
               record: bool = True) -> list[ArbiterVerdict]:
    """Every open structure judged; verdicts recorded to the ledger as `arbiter_*` rows."""
    from alpha import attribution

    now = now or datetime.now(timezone.utc)
    report = attribution.attribute_book(client, account_role=account_role, now=now)
    positions = {p.get("symbol"): p for p in client.positions()}
    forecasts = ledger.read_all("forecasts")
    structs = report.pop("_structs")
    bk = book_mod.reconstruct(client.positions(), equity=report["equity"], account_role=account_role)
    by_id = {s.decision_id: s for s in bk.structures}
    verdicts = []
    for att in structs:
        st = by_id.get(att.decision_id)
        if st is None:
            continue
        fc = latest_forecast(st.symbol, st.brain, forecasts)
        v = judge(st, positions, att.spot_now, forecast=fc, now=now,
                  net_delta_shares=att.net_delta_shares, all_forecasts=forecasts)
        verdicts.append(v)
        logger.info("arbiter %-5s %-16s x%-3d %-5s %s", v.symbol, v.kind, st.contracts, v.action, v.reason[:110])
        if record:
            ledger.record(ledger.Decision(
                decision_id=f"{st.decision_id}:arbiter:{now.strftime('%Y%m%dT%H%M')}",
                ts_utc=now.isoformat(), symbol=st.symbol, brain="arbiter", signal_shape=None,
                instrument=st.kind, thesis=v.reason, predicted_move=v.forecast_centre,
                predicted_sd=v.forecast_sd, implied_move=None, breakeven_move=None, mdm_edge=None,
                quote_snapshot={"liquidation_usd": v.liquidation_usd,
                                "expected_terminal_usd": v.expected_terminal_usd},
                action=f"arbiter_{v.action.lower()}", refusal_reason=None, risk_fraction=0.0,
                max_loss_usd=st.max_loss_usd, order=None,
                outcome={"mode": mode(), "verdict": v.as_dict(), "attribution": att.as_dict()},
                legs=tuple(st.legs), account_role=account_role,
            ))
    return verdicts
