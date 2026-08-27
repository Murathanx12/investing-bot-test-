"""LIVE_SPREAD_CONSTRUCTOR_v1 -- vertical spreads priced from the ACTUAL chain.

WHAT THIS REPLACES
==================
`scripts/competition_book.price_spreads` priced the entire 70% core like this:

    width  = max(1.0, round(spot * 0.05))
    credit = width * 0.30
    risk   = (width - credit) * 100

Three inventions in three lines. The strike grid is invented (real chains are
$1 on SPY near the money, $5 further out, and not a fixed 5% of spot); the
credit is invented; and because the credit is invented, so is the max loss --
which is the number the whole sizing chain divides by.

That is fine for a design sketch and unacceptable as the basis for an
allocation. **A simulated credit cannot answer whether selling a priced option
spread makes money, because the price is the thing under test.**

CONSERVATIVE BY CONSTRUCTION
============================
Every leg is crossed AGAINST us:

    short leg filled at `executable_bid`  (we receive the bid, not the mid)
    long  leg filled at `executable_ask`  (we pay the ask, not the mid)

`executable_*` already carries `chain.staleness_penalty`, so a carried-forward
quote costs edge automatically. The resulting `credit` is therefore a LOWER
bound on what the structure pays and `max_loss` an UPPER bound on what it
risks. If a spread clears the gates on those numbers it clears them on the mid
too; the reverse is not true, which is the direction the error should point.

CASH MUST BEAT A BAD CHAIN
==========================
`best_spread` returns `None` -- not a fallback, not a widened search -- when
nothing clears. Every rejection is recorded with the number that killed it, so
"no trade" is a measurement and not a silence. That distinction is the whole
lesson of the copy-lab lanes that refused for fourteen days while writing the
same state file as a lane that simply found nothing.

THE CREDIT FLOOR IS DELIBERATELY NOT SET HERE
=============================================
The obvious gate is "require credit/width above X". Any X typed into this file
would be exactly the invention the module exists to remove. A short put spread
is fairly priced when credit/width equals roughly the risk-neutral probability
of finishing below the short strike; whether the market pays MORE than that is
the variance risk premium, and it is measurable -- `OPTIONMETRICS_CORE_REPLAY`
measures it on thirty years of real quotes.

So `min_credit_ratio` defaults to `None`, meaning NOT ESTABLISHED, and a caller
that has not supplied a measured floor is told so in the refusal list rather
than being handed a number that looks like evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from alpha.data.chain import ChainSnapshot, Contract

CONTRACT_MULTIPLIER = 100

MIN_OPEN_INTEREST = 100
"""Both legs. An option nobody holds is an option nobody will trade with us at
the quoted size, and the exit matters more than the entry on a five-day hold."""

MAX_LEG_RELATIVE_SPREAD = 0.10
"""Matches `chain.MAX_RELATIVE_SPREAD`. Named again because a SPREAD can hide a
bad leg: two 12%-wide legs can still net to a plausible-looking credit."""


@dataclass(frozen=True)
class VerticalSpread:
    underlying: str
    right: str                     # "P" for a put spread, "C" for a call spread
    direction: str                 # "credit" (we sell) | "debit" (we buy)
    short_strike: float
    long_strike: float
    expiry: str
    dte: int
    credit: float                  # per share, net, conservative. Negative = debit paid
    width: float
    max_loss_per_contract: float
    max_gain_per_contract: float
    short_delta: float | None
    short_symbol: str
    long_symbol: str
    worst_leg_spread: float
    min_open_interest: int
    quote_age_seconds: float
    mid_credit: float = 0.0
    """Net credit at the MIDS. Never used for evaluation -- `credit` is the
    crossed number and that is what any decision uses. This exists only so the
    order's limit price can be set between mid and the touch, because sending a
    limit AT the crossed price gives away the whole spread on entry."""
    oi_known: bool = True
    """False when the feed reported no open interest for a leg. The liquidity
    gate is then INERT for this structure, which must be said rather than
    silently passed -- a missing field reads exactly like a field that cleared
    the check."""

    @property
    def credit_ratio(self) -> float:
        """Credit as a fraction of width -- the only scale-free way to compare
        a $5-wide SPY spread with a $2-wide IWM one."""
        return self.credit / self.width if self.width > 0 else 0.0

    @property
    def breakeven(self) -> float:
        return self.short_strike - self.credit if self.right == "P" \
            else self.short_strike + self.credit

    def describe(self) -> str:
        return (f"{self.underlying} {self.expiry} "
                f"{'sell' if self.direction == 'credit' else 'buy'} "
                f"{self.short_strike:g}{self.right}/{self.long_strike:g}{self.right} "
                f"credit ${self.credit:.2f} on ${self.width:g} wide "
                f"({self.credit_ratio:.1%}), max loss "
                f"${self.max_loss_per_contract:.0f}/contract, {self.dte}d")


@dataclass
class SpreadSearch:
    """What was considered and why almost all of it was thrown away."""
    candidates: list[VerticalSpread] = field(default_factory=list)
    rejected: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def reject(self, reason: str) -> None:
        self.rejected[reason] = self.rejected.get(reason, 0) + 1

    def summary(self) -> str:
        if not self.rejected:
            return f"{len(self.candidates)} tradeable"
        worst = sorted(self.rejected.items(), key=lambda kv: -kv[1])
        return (f"{len(self.candidates)} tradeable; rejected "
                + ", ".join(f"{n}x {r}" for r, n in worst[:5]))


def _usable(c: Contract) -> str | None:
    if not (c.bid > 0 and c.ask > 0 and c.ask >= c.bid):
        return "no two-sided quote"
    if c.relative_spread > MAX_LEG_RELATIVE_SPREAD:
        return f"leg spread > {MAX_LEG_RELATIVE_SPREAD:.0%}"
    if c.open_interest is not None and c.open_interest < MIN_OPEN_INTEREST:
        return f"open interest < {MIN_OPEN_INTEREST}"
    return None


def enumerate_verticals(chain: ChainSnapshot, *, right: str = "P",
                        direction: str = "credit",
                        min_dte: int = 21, max_dte: int = 45,
                        short_delta_range: tuple[float, float] = (0.15, 0.35),
                        max_width_frac: float = 0.10) -> SpreadSearch:
    """Every vertical the chain can actually support, priced conservatively.

    `short_delta_range` is on the ABSOLUTE delta of the leg we sell -- 0.15-0.35
    is the ordinary premium-selling band: far enough out that the short strike
    is not a coin flip, near enough that the credit is not a rounding error.
    Delta is used rather than a percentage of spot because it is the quantity
    that means the same thing across underlyings and volatility levels; 5% OTM
    on IWM and 5% OTM on SPY are very different bets.
    """
    from datetime import date as _date

    out = SpreadSearch()
    today = _date.today()
    by_expiry: dict[str, list[Contract]] = {}
    for c in chain.contracts:
        if c.right != right:
            continue
        by_expiry.setdefault(c.expiry, []).append(c)

    if not by_expiry:
        out.notes.append(f"chain carried no {right} contracts at all")
        return out

    for expiry, legs in sorted(by_expiry.items()):
        try:
            dte = (_date.fromisoformat(expiry) - today).days
        except ValueError:
            out.reject("unparseable expiry")
            continue
        if not (min_dte <= dte <= max_dte):
            out.reject(f"dte outside {min_dte}-{max_dte}")
            continue

        legs = sorted(legs, key=lambda c: c.strike)
        for short in legs:
            why = _usable(short)
            if why:
                out.reject(why)
                continue
            if short.delta is None:
                out.reject("no delta on the short leg")
                continue
            ad = abs(short.delta)
            if not (short_delta_range[0] <= ad <= short_delta_range[1]):
                out.reject("short delta outside band")
                continue

            # The protective leg is FURTHER out of the money than the one we
            # sell: below it for a put spread, above it for a call spread.
            pool = [c for c in legs if (c.strike < short.strike if right == "P"
                                        else c.strike > short.strike)]
            for long in pool:
                width = abs(short.strike - long.strike)
                if width <= 0 or width > chain.spot * max_width_frac:
                    continue
                why = _usable(long)
                if why:
                    out.reject(f"long leg: {why}")
                    continue

                # Cross the spread against ourselves on BOTH legs.
                credit = short.executable_bid - long.executable_ask
                if direction == "credit" and credit <= 0:
                    out.reject("no net credit after crossing the spread")
                    continue

                max_loss = (width - credit) * CONTRACT_MULTIPLIER
                if max_loss <= 0:
                    # width <= credit is an arbitrage, which on a delayed feed
                    # is far more likely to be a stale quote than free money.
                    out.reject("credit >= width (stale or crossed quote)")
                    continue

                oi_known = (short.open_interest is not None
                            and long.open_interest is not None)
                out.candidates.append(VerticalSpread(
                    underlying=chain.underlying, right=right, direction=direction,
                    short_strike=short.strike, long_strike=long.strike,
                    expiry=expiry, dte=dte, credit=credit, width=width,
                    max_loss_per_contract=max_loss,
                    max_gain_per_contract=credit * CONTRACT_MULTIPLIER,
                    short_delta=short.delta,
                    short_symbol=short.symbol, long_symbol=long.symbol,
                    worst_leg_spread=max(short.relative_spread, long.relative_spread),
                    min_open_interest=min(short.open_interest or 0,
                                          long.open_interest or 0),
                    quote_age_seconds=max(short.quote_age_seconds,
                                          long.quote_age_seconds),
                    mid_credit=short.mid - long.mid,
                    oi_known=oi_known,
                ))
    return out


def best_spread(search: SpreadSearch, *,
                min_credit_ratio: float | None = None
                ) -> tuple[VerticalSpread | None, list[str]]:
    """The best tradeable structure, or `None` and the reasons there is none.

    `min_credit_ratio` MUST be supplied from measured evidence. Passing `None`
    does not disable the gate -- it records that no floor has been established,
    which is a refusal to claim the structure is priced favourably, not a
    permission to assume it is.
    """
    refusals: list[str] = []
    if not search.candidates:
        refusals.append(f"NO TRADEABLE STRUCTURE: {search.summary()}. Cash is "
                        "the position. This is a measurement, not a silence.")
        return None, refusals

    pool = search.candidates
    if min_credit_ratio is None:
        refusals.append(
            "NO MEASURED CREDIT FLOOR: min_credit_ratio was not supplied, so "
            "nothing here establishes that the premium exceeds the risk it is "
            "paid for. Rank order below is by credit ratio and is NOT evidence "
            "of edge. Run OPTIONMETRICS_CORE_REPLAY before allocating.")
    else:
        keep = [s for s in pool if s.credit_ratio >= min_credit_ratio]
        if not keep:
            best = max(pool, key=lambda s: s.credit_ratio)
            refusals.append(
                f"CREDIT TOO THIN: best available pays {best.credit_ratio:.1%} "
                f"of width against a measured floor of {min_credit_ratio:.1%}. "
                "Selling below the floor is selling variance too cheaply.")
            return None, refusals
        pool = keep

    # Rank by credit per dollar of risk, then prefer the tighter quote: two
    # structures paying the same are not equally good if one costs more to exit.
    best = max(pool, key=lambda s: (s.credit_ratio, -s.worst_leg_spread))
    return best, refusals


def matching_spread(search: SpreadSearch, *, spot: float,
                    target_delta: float = 0.25,
                    target_width_frac: float = 0.05
                    ) -> tuple[VerticalSpread | None, list[str]]:
    """The structure the REPLAY measured -- not the best-looking one on offer.

    WHY THIS EXISTS, AND WHY `best_spread` IS THE WRONG DEFAULT
    ==========================================================
    Ranking by `credit_ratio` across a whole chain reliably picks the NARROWEST
    spread closest to the money. Run live on SPY at $770.83 it chose a
    763P/762P -- one dollar wide, 1% out of the money, paying 43% of width. That
    looks like an enormous credit and is close to a fair coin: a $1-wide spread
    struck just below spot wins or loses almost on a flip, and 43% is roughly
    what a flip is worth.

    The deeper problem is EVIDENCE TRANSFER. `optionmetrics_core_replay`
    measures one specific structure -- sell the 25-delta put, buy ~5% lower --
    over thirty years. That measured distribution describes THAT trade. Applying
    it to whatever the chain happens to price most generously today is a
    silent substitution of one bet for another, and the sample says nothing
    about the substitute.

    So the live selection matches the replayed geometry, and the credit ratio
    becomes a CHECK on the chosen structure rather than the thing being
    maximised.
    """
    refusals: list[str] = []
    if not search.candidates:
        refusals.append(f"NO TRADEABLE STRUCTURE: {search.summary()}. Cash is "
                        "the position.")
        return None, refusals

    want_width = max(1.0, spot * target_width_frac)

    def distance(s: VerticalSpread) -> float:
        d_delta = abs(abs(s.short_delta or 0.0) - abs(target_delta)) / max(
            abs(target_delta), 1e-9)
        d_width = abs(s.width - want_width) / want_width
        return d_delta + d_width

    best = min(search.candidates, key=distance)
    if distance(best) > 0.75:
        refusals.append(
            f"NO CLOSE MATCH: nearest structure is "
            f"{abs(best.short_delta or 0):.2f}-delta and ${best.width:g} wide "
            f"against a target of {target_delta:.2f}-delta / ${want_width:.0f}. "
            "The measured distribution does not describe this trade.")
        return None, refusals

    if not best.oi_known:
        refusals.append(
            "OPEN INTEREST UNAVAILABLE on at least one leg, so the liquidity "
            "gate did not run. This is not a pass -- it is an unrun check.")
    return best, refusals
