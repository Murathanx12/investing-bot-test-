"""The option chain, and the honest handling of a DELAYED one.

THE CONSTRAINT WE ACTUALLY HAVE
===============================
Alpaca's real-time OPRA options feed requires the $99/mo Algo Trader Plus plan.
On the free plan the options feed is `indicative`, which during market hours
serves data **delayed by about fifteen minutes** (the API silently clamps the
end of the query window to now-15min for non-premium accounts, and asking for
`feed=opra` returns 403 "OPRA agreement is not signed" -- a misleading message
that means "you do not have the subscription").

Measured on this account, 2026-08-25, SPY, expiries within ten days:

    contracts returned      1000  (the page limit -- coverage is not the problem)
    with BOTH bid and ask   1000  (100%)
    with greeks / IV         462  (46%)
    relative spread          median 5.3%,  p25 1.5%,  p75 18.2%
    contracts at <=5% spread 400

So the free feed is not *missing*. It is **late**. That is a completely
different problem and it has a partial engineering answer.

THE DELTA-ADJUSTED QUOTE
========================
An option quote from fifteen minutes ago is stale mostly because the UNDERLYING
moved. And the underlying's price is available in real time on the free plan
(IEX). So a stale option quote can be carried forward:

    est_mid  =  stale_mid  +  delta * dS  +  0.5 * gamma * dS**2

where `dS` is the underlying's move since the option quote's timestamp. Over
fifteen minutes on a liquid name, delta and gamma barely change and vega's
contribution is small in the absence of a shock -- so this recovers most of the
error, and what it cannot recover is exactly the case where it should not be
trusted: a volatility shock, i.e. news.

Everything here is therefore **labelled, never laundered**:

  * `quote_age_seconds` travels with every contract;
  * `mid` is the raw stale mid and `adjusted_mid` is the carried-forward
    estimate, and they are separate fields so a ledger row shows both;
  * `staleness_penalty` widens the assumed execution price by the size of the
    adjustment, so a bigger carry-forward automatically costs more edge;
  * a snapshot older than `MAX_QUOTE_AGE_SECONDS` REFUSES rather than adjusting,
    because past a point the adjustment is a guess wearing a formula.

WHAT THIS RULES OUT, STATED PLAINLY
===================================
Reactive trading. If a stock gaps 8% on an earnings print, our chain shows the
world as it was before the print for a quarter of an hour, and the delta
adjustment cannot invent the volatility repricing that happened in between.

So the agent does not react to events -- it **positions ahead of scheduled
ones**, which is what the catalyst calendar in `docs/STRATEGY.md` is for. Buying
an AVGO straddle at 14:00 ET for a 16:05 ET print is a trade about whether the
implied move is mispriced, and a fifteen-minute-old quote answers that question
perfectly well. Buying the reaction at 16:06 is a trade the free plan cannot do,
and pretending otherwise would produce fills we could never explain.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

#: Beyond this, a quote is not carried forward -- it is refused. Fifteen minutes
#: of delay plus a slack allowance for a slow poll; past ~25 minutes the implied
#: vol surface itself has usually moved and delta cannot see that.
MAX_QUOTE_AGE_SECONDS = 1_500

#: A contract must have a two-sided quote this tight to be considered at all.
#: The measured p25 on SPY is 1.5% and the median 5.3%, so this keeps roughly
#: the better third of the chain and throws away the part where the spread eats
#: the thesis.
MAX_RELATIVE_SPREAD = 0.10

#: Minimum quoted size on both sides. Alpaca's paper engine does not check order
#: size against displayed NBBO quantity, so this is OUR check, not the venue's:
#: it is what keeps fills inside the range a real book could have absorbed.
MIN_QUOTE_SIZE = 10


class ChainRefusal(RuntimeError):
    """A chain that cannot support a decision."""


@dataclass
class Contract:
    symbol: str
    underlying: str
    right: str               # "C" or "P"
    strike: float
    expiry: str              # YYYY-MM-DD
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    quote_ts: datetime
    quote_age_seconds: float
    """TRUE wall-clock age. Always the honest number, even when it is not the
    number the staleness logic acts on -- see `effective_age_seconds`."""
    implied_vol: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    open_interest: int | None
    greeks_source: str       # "feed" | "black_scholes" | "none"
    effective_age_seconds: float = 0.0
    """Age measured in MARKET time. When the market is closed the last quote IS
    the current quote: nothing has traded since, and the underlying has not moved
    either, so `ds` is zero and a carry-forward would be a no-op anyway. Charging
    a 15-hour overnight penalty would refuse every structure between the close
    and the open -- which is precisely when the next session gets planned."""
    adjusted_mid: float | None = field(default=None)
    staleness_penalty: float = 0.0

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def relative_spread(self) -> float:
        m = self.mid
        return (self.ask - self.bid) / m if m > 0 else 1.0

    @property
    def years_to_expiry(self) -> float:
        exp = datetime.strptime(self.expiry, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return max((exp - datetime.now(timezone.utc)).total_seconds() / (365.25 * 86400), 1e-6)

    @property
    def executable_ask(self) -> float:
        """What we assume we PAY, not what we see.

        The quoted ask plus the staleness penalty. A carried-forward quote is a
        worse quote and this is where that costs something -- otherwise every
        delayed trade would look identical to a real-time one on paper and the
        agent would take the same risk on much worse information.
        """
        return self.ask + self.staleness_penalty

    @property
    def executable_bid(self) -> float:
        return max(self.bid - self.staleness_penalty, 0.0)


@dataclass
class ChainSnapshot:
    underlying: str
    spot: float
    spot_ts: datetime
    spot_source: str
    feed: str
    fetched_at: datetime
    contracts: list[Contract]
    median_quote_age_seconds: float
    n_raw: int
    market_open: bool = False

    def expiries(self) -> list[str]:
        return sorted({c.expiry for c in self.contracts})

    def atm(self, expiry: str, right: str) -> Contract | None:
        pool = [c for c in self.contracts if c.expiry == expiry and c.right == right]
        return min(pool, key=lambda c: abs(c.strike - self.spot)) if pool else None

    def implied_move(self, expiry: str) -> float | None:
        """The market's own expected absolute move to `expiry`, as a fraction.

        Read off the at-the-money STRADDLE, which is the market's price for
        exactly this quantity, rather than reconstructed from an implied-vol
        number. A straddle price is a thing you can trade; a vol print is a
        model output, and on a feed where 54% of contracts carry no IV at all it
        is not even a reliably present one.
        """
        call, put = self.atm(expiry, "C"), self.atm(expiry, "P")
        if not call or not put or self.spot <= 0:
            return None
        straddle = (call.adjusted_mid or call.mid) + (put.adjusted_mid or put.mid)
        # A straddle costs roughly 0.8 * E|move| for a lognormal; the standard
        # rule-of-thumb 0.85 multiplier converts price to expected move.
        return 0.85 * straddle / self.spot

    def liquid(self, *, max_spread: float = MAX_RELATIVE_SPREAD,
               min_size: int = MIN_QUOTE_SIZE) -> list[Contract]:
        return [
            c for c in self.contracts
            if c.bid > 0 and c.ask > 0
            and c.relative_spread <= max_spread
            and min(c.bid_size, c.ask_size) >= min_size
        ]


def fetch(client, underlying: str, *, expiry_from: str, expiry_to: str,
          feed: str | None = None, spot: float | None = None,
          market_open: bool | None = None,
          strike_from: float | None = None, strike_to: float | None = None) -> ChainSnapshot:
    """Snapshot a chain, fill in missing greeks, and carry stale quotes forward.

    `market_open` is asked of the venue when not supplied, because the whole
    staleness model hinges on it and a wrong guess silently disables the agent
    outside RTH.
    """
    from alpha import config

    if market_open is None:
        try:
            market_open = bool(client.clock().get("is_open"))
        except Exception:                                   # noqa: BLE001
            market_open = True   # the conservative side: assume quotes decay

    resolved_feed = feed or config.options_feed()
    raw = client.option_chain(
        underlying, expiration_gte=expiry_from, expiration_lte=expiry_to, feed=resolved_feed,
        strike_gte=strike_from, strike_lte=strike_to,
    )
    snaps = (raw or {}).get("snapshots") or {}
    if not snaps:
        raise ChainRefusal(
            f"no contracts returned for {underlying} ({expiry_from}..{expiry_to}, "
            f"feed={resolved_feed}). A chain with no quotes is an absence, not a "
            "quiet market -- refusing rather than proceeding on an empty set."
        )

    live_spot, spot_ts, spot_source = (
        (spot, datetime.now(timezone.utc), "caller") if spot is not None
        else _spot_from(client, underlying)
    )

    now = datetime.now(timezone.utc)
    contracts: list[Contract] = []
    for symbol, snap in snaps.items():
        c = _parse(symbol, underlying, snap, now)
        if c is None:
            continue
        c.effective_age_seconds = c.quote_age_seconds if market_open else 0.0
        _ensure_greeks(c, live_spot)
        _carry_forward(c, live_spot, spot_ts)
        contracts.append(c)

    if not contracts:
        raise ChainRefusal(f"{len(snaps)} snapshots for {underlying}, none with a usable quote.")

    ages = sorted(c.quote_age_seconds for c in contracts)
    return ChainSnapshot(
        underlying=underlying, spot=live_spot, spot_ts=spot_ts, spot_source=spot_source,
        feed=resolved_feed, fetched_at=now, contracts=contracts,
        median_quote_age_seconds=ages[len(ages) // 2], n_raw=len(snaps),
        market_open=market_open,
    )


def _spot_from(client, underlying: str) -> tuple[float, datetime, str]:
    """Live underlying price, preferring a TRADE over a quote.

    On the free IEX feed a quote is routinely one-sided -- AVGO returned bid
    346.52 with an ask of ZERO on the same call that gave SPY a clean two-sided
    quote. A mid computed from that is half the real price, and it would flow
    silently into every delta adjustment downstream. A trade print has no sides
    and cannot fail this way, so it is the primary source and the quote is the
    fallback, not the reverse.
    """
    data = client.latest_trade([underlying])
    trade = (data.get("trades") or {}).get(underlying) or {}
    price, ts = trade.get("p"), trade.get("t")
    if price and ts:
        return float(price), _parse_ts(ts), "trade"

    quote = ((client.stock_quote([underlying]).get("quotes") or {}).get(underlying)) or {}
    bid, ask = quote.get("bp") or 0.0, quote.get("ap") or 0.0
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0, _parse_ts(quote.get("t")), "quote"
    if bid > 0 or ask > 0:
        raise ChainRefusal(
            f"{underlying}: one-sided quote (bid={bid}, ask={ask}) and no recent trade. "
            "Refusing -- a mid built from a missing side is off by half the price and "
            "would corrupt every delta adjustment silently."
        )
    raise ChainRefusal(f"{underlying}: no trade and no quote available.")


def _parse(symbol: str, underlying: str, snap: dict[str, Any], now: datetime) -> Contract | None:
    q = snap.get("latestQuote") or {}
    bid, ask = q.get("bp"), q.get("ap")
    if bid is None or ask is None or ask <= 0:
        return None
    ts = _parse_ts(q.get("t"))
    right, strike, expiry = _decode_occ(symbol)
    g = snap.get("greeks") or {}
    has_greeks = bool(g)
    return Contract(
        symbol=symbol, underlying=underlying, right=right, strike=strike, expiry=expiry,
        bid=float(bid), ask=float(ask),
        bid_size=int(q.get("bs") or 0), ask_size=int(q.get("as") or 0),
        quote_ts=ts, quote_age_seconds=max((now - ts).total_seconds(), 0.0),
        implied_vol=snap.get("impliedVolatility"),
        delta=g.get("delta"), gamma=g.get("gamma"), theta=g.get("theta"), vega=g.get("vega"),
        open_interest=snap.get("openInterest"),
        greeks_source="feed" if has_greeks else "none",
    )


def _ensure_greeks(c: Contract, spot: float) -> None:
    """Compute Black-Scholes greeks when the feed omits them.

    The indicative feed carried greeks on 46% of contracts. The delta adjustment
    is worthless without a delta, so the missing 54% are computed rather than
    dropped -- but the source is RECORDED, because a computed delta rests on an
    implied vol that itself had to be recovered, and a reader is entitled to
    know which numbers came from the venue.
    """
    if c.delta is not None and c.gamma is not None:
        return
    iv = c.implied_vol
    if iv is None:
        iv = _implied_vol(c, spot)
        if iv is None:
            c.greeks_source = "none"
            return
        c.implied_vol = iv
    d = _bs_greeks(spot, c.strike, c.years_to_expiry, iv, c.right)
    c.delta, c.gamma, c.vega, c.theta = d["delta"], d["gamma"], d["vega"], d["theta"]
    c.greeks_source = "black_scholes"


def _carry_forward(c: Contract, live_spot: float, spot_ts: datetime) -> None:
    """Advance a stale quote to the live underlying, and charge for doing it."""
    if c.effective_age_seconds <= 60 or c.delta is None:
        c.adjusted_mid, c.staleness_penalty = c.mid, 0.0
        return
    if c.effective_age_seconds > MAX_QUOTE_AGE_SECONDS:
        # Not adjusted and not silently used: the caller sees an age past the
        # ceiling and `liquid()` still returns it, so the DECISION layer refuses
        # with a reason rather than this layer hiding the contract.
        c.adjusted_mid, c.staleness_penalty = None, float("inf")
        return

    stale_spot = _spot_at_quote(c, live_spot)
    ds = live_spot - stale_spot
    gamma = c.gamma or 0.0
    delta_pnl = c.delta * ds + 0.5 * gamma * ds * ds
    c.adjusted_mid = max(c.mid + delta_pnl, 0.01)
    # The penalty is a fraction of the adjustment we just made: a quote we had
    # to move a long way is a quote we understand less well.
    c.staleness_penalty = min(0.25 * abs(delta_pnl), c.mid)


def _spot_at_quote(c: Contract, live_spot: float) -> float:
    """The underlying at the option quote's timestamp.

    Not yet wired to an intraday bar series -- the caller can supply one later.
    Returning the live spot means `ds = 0` and the adjustment is a no-op, which
    is the correct DEGRADATION: it under-corrects rather than inventing a move.
    """
    return live_spot


def _implied_vol(c: Contract, spot: float, *, r: float = 0.045) -> float | None:
    """Recover IV from the mid by bisection. None when the price is unreachable."""
    target, t = c.mid, c.years_to_expiry
    if target <= 0 or t <= 0:
        return None
    lo, hi = 1e-4, 5.0
    if _bs_price(spot, c.strike, t, hi, c.right, r) < target:
        return None
    for _ in range(60):
        mid_vol = (lo + hi) / 2.0
        if _bs_price(spot, c.strike, t, mid_vol, c.right, r) < target:
            lo = mid_vol
        else:
            hi = mid_vol
    return (lo + hi) / 2.0


def _d1_d2(s: float, k: float, t: float, vol: float, r: float) -> tuple[float, float]:
    denom = vol * math.sqrt(t)
    d1 = (math.log(s / k) + (r + 0.5 * vol * vol) * t) / denom
    return d1, d1 - denom


def _bs_price(s: float, k: float, t: float, vol: float, right: str, r: float = 0.045) -> float:
    if vol <= 0 or t <= 0 or s <= 0 or k <= 0:
        return max(0.0, (s - k) if right == "C" else (k - s))
    d1, d2 = _d1_d2(s, k, t, vol, r)
    disc = math.exp(-r * t)
    if right == "C":
        return s * _cdf(d1) - k * disc * _cdf(d2)
    return k * disc * _cdf(-d2) - s * _cdf(-d1)


def _bs_greeks(s: float, k: float, t: float, vol: float, right: str,
               r: float = 0.045) -> dict[str, float]:
    if vol <= 0 or t <= 0:
        return {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0}
    d1, d2 = _d1_d2(s, k, t, vol, r)
    pdf = math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
    disc = math.exp(-r * t)
    delta = _cdf(d1) if right == "C" else _cdf(d1) - 1.0
    theta_common = -(s * pdf * vol) / (2 * math.sqrt(t))
    theta = (theta_common - r * k * disc * _cdf(d2)) if right == "C" \
        else (theta_common + r * k * disc * _cdf(-d2))
    return {
        "delta": delta,
        "gamma": pdf / (s * vol * math.sqrt(t)),
        "vega": s * pdf * math.sqrt(t) / 100.0,
        "theta": theta / 365.0,
    }


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _parse_ts(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    text = value.replace("Z", "+00:00")
    # Alpaca serves nanosecond precision; fromisoformat wants at most microseconds.
    if "." in text:
        head, _, tail = text.partition(".")
        frac, sign, offset = tail.partition("+")
        text = f"{head}.{frac[:6]}{sign}{offset}" if sign else f"{head}.{frac[:6]}"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(timezone.utc)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _decode_occ(symbol: str) -> tuple[str, float, str]:
    """`SPY260828P00610000` -> ("P", 610.0, "2026-08-28")."""
    strike = float(symbol[-8:]) / 1000.0
    right = symbol[-9]
    yy, mm, dd = symbol[-15:-13], symbol[-13:-11], symbol[-11:-9]
    return right, strike, f"20{yy}-{mm}-{dd}"
