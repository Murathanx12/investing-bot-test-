"""Execution, pricing, node caps and the tournament objective.

Every check here pins something that was WRONG in COMPETITION_BOOK_v1 as
reviewed on 2026-08-28, or a bias found while measuring it. The book was
internally consistent and would not have placed.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import numpy as np

from alpha import nodes, spreads, timing, tournament
from alpha.data.chain import ChainSnapshot, Contract

fails: list[str] = []
ran = 0


def check(name: str, cond: bool, why: str = "") -> None:
    global ran
    ran += 1
    if cond:
        print(f"  ok   {name}")
    else:
        fails.append(name)
        print(f"  FAIL {name}  {why}")


def refuses(fn, exc=Exception) -> bool:
    try:
        fn()
    except exc:
        return True
    return False


# ============================================================ timing
print("execution timing")

check("options accept ONLY tif=day",
      timing.OPTION_TIF == ("day",),
      "the book said MARKET-ON-CLOSE for a core made of multileg options; "
      "Alpaca rejects that with 'not supported for options trading'")

opt = timing.entry_timing("option", signal_frozen_et=time(15, 40))
check("  so an option entry is a LIMIT with tif=day, not an auction order",
      opt.time_in_force == "day" and opt.order_type == "limit")
check("  and it is worked in a late-RTH window instead",
      opt.window_et == timing.OPTION_ENTRY_WINDOW_ET)

eq = timing.entry_timing("equity", signal_frozen_et=time(15, 40))
check("an equity MOC is legal when the signal froze before the cutoff",
      eq.time_in_force == "cls")

check("a signal frozen AFTER the deadline refuses the MOC",
      refuses(lambda: timing.entry_timing("equity", signal_frozen_et=time(16, 0)),
              timing.TimingRefusal),
      "an MOC must be in the book by 15:50 ET, so a signal read off the 16:00 "
      "close could not have produced it -- that is lookahead in the execution layer")

check("  and an UNKNOWN freeze time refuses too, rather than assuming",
      refuses(lambda: timing.entry_timing("equity", signal_frozen_et=None),
              timing.TimingRefusal))

check("the freeze deadline is strictly before the venue cutoff",
      timing.SIGNAL_FREEZE_ET < timing.CLS_CUTOFF_ET,
      "no slack means a slow computation becomes a rejected order")

bad = timing.validate_payload(
    {"legs": [{"symbol": "SPY260904P00600000"}], "type": "market",
     "time_in_force": "cls"})
check("validate_payload catches the exact bad order the book described",
      any("not accepted for options" in m for m in bad))
check("  and refuses a MARKET order on a multileg spread",
      any("should be a LIMIT" in m for m in bad),
      "a market order on a 10%-wide spread quote is an unbounded fill")
check("a well-formed option limit passes",
      timing.validate_payload({"legs": [1], "type": "limit",
                               "limit_price": "1.20",
                               "time_in_force": "day"}) == [])

check("a marketable BUY limit sits between mid and ask",
      1.10 < timing.marketable_limit(1.00, 1.20, "buy") <= 1.20)
check("a marketable SELL limit sits between bid and mid",
      1.00 <= timing.marketable_limit(1.00, 1.20, "sell") < 1.10)
check("  and a crossed or empty quote is refused, not averaged",
      refuses(lambda: timing.marketable_limit(0.0, 1.2, "sell"),
              timing.TimingRefusal))


# ============================================================ spreads
print("\nlive spread constructor")


def contract(strike, right, bid, ask, delta, expiry, oi=5000):
    return Contract(
        symbol=f"SPY{expiry.replace('-', '')[2:]}{right}{int(strike * 1000):08d}",
        underlying="SPY", right=right, strike=strike, expiry=expiry,
        bid=bid, ask=ask, bid_size=50, ask_size=50,
        quote_ts=datetime.now(timezone.utc), quote_age_seconds=5.0,
        implied_vol=0.18, delta=delta, gamma=0.01, theta=-0.05, vega=0.1,
        open_interest=oi, greeks_source="feed")


exp = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
cs = ChainSnapshot(
    underlying="SPY", spot=600.0, spot_ts=datetime.now(timezone.utc),
    spot_source="iex", feed="indicative", fetched_at=datetime.now(timezone.utc),
    contracts=[
        contract(580, "P", 4.00, 4.10, -0.25, exp),
        contract(570, "P", 2.50, 2.60, -0.16, exp),
        contract(550, "P", 1.10, 1.20, -0.08, exp),
    ],
    median_quote_age_seconds=5.0, n_raw=3)

search = spreads.enumerate_verticals(cs, right="P", min_dte=21, max_dte=45)
check("the constructor finds real verticals from a real chain",
      len(search.candidates) >= 1, search.summary())

s0 = search.candidates[0]
# Two strikes (580 at 0.25d and 570 at 0.16d) both sit inside the short-delta
# band, so several verticals are legitimately generated. Checking one hardcoded
# pair asserted the SEARCH's ordering rather than its PRICING; every candidate
# is verified against its own legs instead.
BID = {580: 4.00, 570: 2.50, 550: 1.10}
ASK = {580: 4.10, 570: 2.60, 550: 1.20}
check("credit is computed by CROSSING the spread on both legs, for EVERY candidate",
      all(abs(c.credit - (BID[int(c.short_strike)] - ASK[int(c.long_strike)])) < 1e-9
          for c in search.candidates),
      "a mid-to-mid credit spread replay manufactures edge that is not there")
check("  never using the mid on either leg",
      all(c.credit < (BID[int(c.short_strike)] + ASK[int(c.short_strike)]) / 2
          - (BID[int(c.long_strike)] + ASK[int(c.long_strike)]) / 2 + 1e-9
          for c in search.candidates))
check("  so max loss is (width - credit) x 100, from quotes not from a guess",
      all(abs(c.max_loss_per_contract - (c.width - c.credit) * 100) < 1e-9
          for c in search.candidates))

check("NO measured credit floor means the caller is TOLD so, not defaulted",
      any("NO MEASURED CREDIT FLOOR" in r
          for r in spreads.best_spread(search)[1]),
      "the old code hardcoded credit = 30% of width, which is the invention "
      "this module exists to remove")

best, why = spreads.best_spread(search, min_credit_ratio=0.99)
check("an unmeetable floor returns CASH, not the least-bad structure",
      best is None and any("CREDIT TOO THIN" in r for r in why))

# --- the defect the LIVE run exposed --------------------------------------
# Ranking a whole chain by credit/width reliably picks the narrowest spread
# closest to the money. On SPY at $770.83 that was a 763P/762P paying 43% of
# width -- near a coin flip, and NOT the structure the 30-year replay measured.
narrow = contract(599, "P", 3.00, 3.05, -0.48, exp)
coinflip = ChainSnapshot(
    underlying="SPY", spot=600.0, spot_ts=datetime.now(timezone.utc),
    spot_source="iex", feed="indicative", fetched_at=datetime.now(timezone.utc),
    contracts=cs.contracts + [narrow, contract(598, "P", 2.40, 2.45, -0.44, exp)],
    median_quote_age_seconds=5.0, n_raw=5)
cf = spreads.enumerate_verticals(coinflip, right="P", min_dte=21, max_dte=45,
                                 short_delta_range=(0.15, 0.50))
top = spreads.best_spread(cf)[0]
check("ranking by credit ratio picks the near-ATM COIN FLIP",
      top is not None and top.width <= 2.0,
      "this is the behaviour, not a bug in the test -- it is why "
      "best_spread is the wrong default")
matched, _ = spreads.matching_spread(cf, spot=600.0, target_delta=0.25,
                                     target_width_frac=0.05)
check("  while matching_spread picks the REPLAYED geometry instead",
      matched is not None and abs(abs(matched.short_delta) - 0.25) < 0.05
      and matched.width > 5.0,
      f"{matched.describe() if matched else None} -- the measured distribution "
      "describes ONE structure; applying it to a different one is a silent "
      "substitution of the bet")

no_oi = ChainSnapshot(
    underlying="SPY", spot=600.0, spot_ts=datetime.now(timezone.utc),
    spot_source="iex", feed="indicative", fetched_at=datetime.now(timezone.utc),
    contracts=[contract(580, "P", 4.00, 4.10, -0.25, exp, oi=None),
               contract(550, "P", 1.10, 1.20, -0.08, exp, oi=None)],
    median_quote_age_seconds=5.0, n_raw=2)
_m, _r = spreads.matching_spread(
    spreads.enumerate_verticals(no_oi, right="P", min_dte=21, max_dte=45),
    spot=600.0)
check("a MISSING open interest is reported as an UNRUN check, not a pass",
      any("did not run" in r for r in _r),
      "the live feed returns no OI, so the liquidity gate silently passed "
      "everything -- a missing field reads exactly like a cleared one")

wide = ChainSnapshot(
    underlying="SPY", spot=600.0, spot_ts=datetime.now(timezone.utc),
    spot_source="iex", feed="indicative", fetched_at=datetime.now(timezone.utc),
    contracts=[contract(580, "P", 1.00, 4.00, -0.25, exp),
               contract(570, "P", 0.50, 3.00, -0.16, exp)],
    median_quote_age_seconds=5.0, n_raw=2)
ws = spreads.enumerate_verticals(wide, right="P", min_dte=21, max_dte=45)
check("a chain quoted too wide yields NOTHING tradeable",
      spreads.best_spread(ws, min_credit_ratio=0.05)[0] is None,
      "cash must beat a bad chain")
check("  and the refusal names the count that killed it",
      "rejected" in ws.summary() or ws.rejected != {},
      "a refusal that does not say what it measured is a silence")


# ============================================================ nodes
print("\nrisk nodes")

core = [nodes.Position("SPY", "short_put_spread", 7_000),
        nodes.Position("QQQ", "short_put_spread", 7_000),
        nodes.Position("IWM", "short_put_spread", 7_000)]
att = nodes.attribute(core, equity=100_000,
                      betas={"SPY": 1.0, "QQQ": 1.15, "IWM": 1.10})
check("SPY+QQQ+IWM register as ONE market-beta bet, not three positions",
      att.by_node[nodes.MARKET_BETA] > 20_000,
      f"{att.by_node.get(nodes.MARKET_BETA)} -- the book called this "
      "'three diversified positions'")
check("  and selling premium on all three stacks a SHORT_VARIANCE node too",
      att.by_node[nodes.SHORT_VARIANCE] == 21_000)
check("  which breaches the node cap the ticker-count check never saw",
      any("MARKET_BETA" in b for b in att.breaches), str(att.breaches))
check("effective NODE count exposes it as ~2 causes, not 3 names",
      nodes.effective_node_count(att) < 2.5,
      f"{nodes.effective_node_count(att):.2f}")

check("an unmeasurable beta is charged IN FULL, never defaulted to 1.0 silently",
      "DECLARED" in nodes.attribute(
          [nodes.Position("XYZ", "long_shares", 1_000)],
          equity=100_000).basis[nodes.MARKET_BETA])
check("realised beta returns None rather than a made-up 1.0",
      nodes.realised_beta(np.array([0.01, 0.02]), np.array([0.01, 0.02])) is None,
      "too few points must not silently produce a number")

rng = np.random.default_rng(3)
mkt = rng.normal(0, 0.01, 300)
check("  and recovers a known beta when there IS data",
      abs(nodes.realised_beta(2.0 * mkt + rng.normal(0, 1e-6, 300), mkt) - 2.0) < 0.05)


# ============================================================ tournament
print("\ntournament utility")

rng = np.random.default_rng(11)
# A credit-spread-like payoff: wins small and often, loses large and rarely.
credit_like = np.where(rng.random(4000) < 0.85, 0.06, -0.75)
# A convex payoff: loses small and often, wins large and rarely.
convex_like = np.where(rng.random(4000) < 0.25, 2.2, -1.0)

base = tournament.simulate({}, {}, 100_000.0, n_paths=2000)
check("a cash book has zero dispersion", float(np.std(base)) == 0.0)

opps = [
    tournament.Opportunity("beta_core", credit_like, structure="short_put_spread",
                           symbol="SPY", increment_usd=2_000, max_usd=20_000),
    tournament.Opportunity("event_convex", convex_like, structure="call_debit_spread",
                           symbol="AVGO", increment_usd=2_000, max_usd=12_000),
]

# BEHIND, late: a +0.4% median book cannot reach a +8% target.
alloc_behind = tournament.auction(opps, equity=100_000, target=108_000,
                                  floor=80_000, budget=24_000, n_paths=3000)
# AHEAD: target already almost met, so the utility of extra variance is low.
alloc_ahead = tournament.auction(opps, equity=100_000, target=100_500,
                                 floor=80_000, budget=24_000, n_paths=3000)

conv_behind = alloc_behind.by_name.get("event_convex", 0.0)
conv_ahead = alloc_ahead.by_name.get("event_convex", 0.0)
check("chasing a FAR target buys more convexity than chasing a near one",
      conv_behind > conv_ahead,
      f"behind={conv_behind:,.0f} ahead={conv_ahead:,.0f} -- if these are equal "
      "the objective is not responding to rank, which is the whole point")

check("the auction records WHAT won each increment",
      any("->" in l for l in alloc_behind.log)
      and any("objective =" in l for l in alloc_behind.log))
check("  and never exceeds its budget", alloc_behind.total <= 24_000 + 1e-9)

check("a hard floor breach is a VETO, not a penalty term",
      tournament.contest_utility(np.full(100, 50_000.0), equity=100_000,
                                 target=110_000, floor=80_000) == -1.0,
      "a weighted penalty would trade ruin away for upside")

m, why = tournament.mode_for(99_000, target=108_000, start_equity=100_000,
                             sessions_left=1)
check("behind with one session left selects ATTACK", m == "ATTACK", why)
m2, _ = tournament.mode_for(112_000, target=108_000, start_equity=100_000,
                            sessions_left=1)
check("  and already ahead selects BASE", m2 == "BASE")

# A double-or-halve is EXACTLY zero in log terms and +25% in arithmetic terms.
# An earlier version of this check asserted the log value was negative, which is
# wrong -- log(2) + log(0.5) = 0 -- and the correct statement is the sharper one
# anyway: the two objectives disagree about the SAME gamble.
coin = np.array([50_000.0, 200_000.0])
# --- the per-name cap must not be defeated by DECOMPOSITION ----------------
# SPY appears as SPY:long_shares, SPY:long_atm_call and SPY:call_debit_spread.
# With a ceiling per CANDIDATE, a "6% per name" rule permitted 18% on one
# underlying, and the auction broke no rule it could see.
grouped = [
    tournament.Opportunity(f"SPY:{k}", convex_like, structure=k, symbol="SPY",
                           increment_usd=1_000, max_usd=6_000,
                           group="SPY", group_max_usd=6_000)
    for k in ("long_atm_call", "call_debit_spread", "long_shares")
]
g_alloc = tournament.auction(grouped, equity=100_000, target=108_000,
                             floor=80_000, budget=30_000, n_paths=2500)
spy_total = sum(v for k, v in g_alloc.by_name.items() if k.startswith("SPY:"))
check("one symbol's TOTAL risk respects the per-name cap across structures",
      spy_total <= 6_000 + 1e-9,
      f"${spy_total:,.0f} allocated to SPY against a $6,000 per-name cap")

# --- the MODE must choose the OBJECTIVE ------------------------------------
# An earlier run printed BASE while the auction bought three index calls with
# medians of -3.8% and -7.4%, because P(target) was the only thing being asked.
steady = np.full(2000, 0.02)                              # reliable and small
lottery = np.where(rng.random(2000) < 0.05, 3.0, -1.0)    # negative median
pair = [
    tournament.Opportunity("steady", steady, structure="long_shares",
                           symbol="A", increment_usd=2_000, max_usd=10_000),
    tournament.Opportunity("lottery", lottery, structure="long_call",
                           symbol="B", increment_usd=2_000, max_usd=10_000),
]
growth = tournament.auction(pair, equity=100_000, target=130_000, floor=70_000,
                            budget=10_000, n_paths=3000, objective="growth")
attack = tournament.auction(pair, equity=100_000, target=130_000, floor=70_000,
                            budget=10_000, n_paths=3000, objective="target")
check("the GROWTH objective refuses the negative-median lottery",
      growth.by_name.get("lottery", 0.0) == 0.0,
      f"{growth.by_name} -- log wealth must not buy a -1.0 tail for a 5% chance")
check("  while the TARGET objective buys it, because reliability cannot win",
      attack.by_name.get("lottery", 0.0) > 0.0,
      f"{attack.by_name} -- a structure that cannot reach the target is "
      "worthless however dependable it is")
check("  and an unknown objective is refused, not defaulted",
      refuses(lambda: tournament.auction(pair, equity=1e5, target=1.1e5,
                                         floor=9e4, budget=1e3,
                                         objective="vibes"), ValueError))

check("a double-or-halve is worth ZERO to a log-wealth investor",
      abs(tournament.expected_log_wealth(coin, 100_000)) < 1e-9)
check("  while being +25% to anyone ranking on the arithmetic mean",
      abs(float(np.mean(coin)) / 100_000 - 1.25) < 1e-9,
      "this is exactly why the contest and the real account cannot share an "
      "objective function")
check("  and a contest chasing a 150k target PREFERS the gamble to cash",
      tournament.contest_utility(coin, equity=100_000, target=150_000,
                                 floor=40_000)
      > tournament.contest_utility(np.full(2, 100_000.0), equity=100_000,
                                   target=150_000, floor=40_000))

print(f"\n{ran} checks")
print("ALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
