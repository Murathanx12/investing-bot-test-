"""POST_EVENT_DRIFT_v1 -- the name that just printed keeps going, for three days.

The pre-event RELAY is refuted and the post-event PEER relay is refuted. What
survived both is the least exotic thing in the file: **the SOURCE itself drifts
in the direction of its own day-0 move**, and it is the first mechanism in this
project with a positive t on real data.

    signal    r_0   = the close-to-close move across the first close that
                      reflects the print (SEC 8-K Item 2.02 dated, so `bmo`
                      is the same session and `amc` is the next one)
    forecast  the next sessions' return, in the SIGN of r_0, excess over
              beta * QQQ with beta fitted on the 120 sessions BEFORE the print

WHY THIS ONE IS BELIEVED MORE THAN THE OTHERS
=============================================
`scripts/post_event_relay.py` produced +1.13% / hit 64% / t 2.72 on n=108.
A t on 108 overlapping legs is not evidence, so it was taken apart
(`scripts/source_pead_decompose.py`, `state/source_pead_decompose.json`):

  * NOT ONE NAME. Ten of eleven names are positive; leave-one-name-out never
    drops the t below 2.37. The only negative name is GOOGL, and removing it
    RAISES the headline -- the opposite of a result carried by one winner.
  * NOT A CLUSTERING ARTEFACT. Earnings print in the same weeks, so the legs
    share a market. One observation per calendar week -- 62 blocks, the
    honest n -- still gives t 2.23; per event day, t 2.78.
  * NOT LONG DRIFT. "Continuation" on an up day would be market drift wearing
    a costume. The DOWN side is the stronger half: hit 72%, t 2.37, against
    the up side's 54% and 1.65. A bad print keeps being bad.
  * IT LIVES IN THE MIDDLE. By |r_0| tercile: small (<3.5%) t 0.66, mid
    (3.5-8.2%) t 3.45 at hit 81%, large (>8.3%) t 1.26. A print the market
    shrugged at has nothing to continue, and a 20% move has already
    over-reacted. So this brain REFUSES below 3.5% and halves its conviction
    above 8.2%.
  * IT DIES OF COSTS, NOT OF DOUBT. At a round-trip cost of 1% of spot the
    mean is +0.13% and the t is 0.32. That is the real constraint, and it is
    why this brain must never buy a lottery ticket: the whole edge is 1% of
    spot and a wide long option gives it back in half-spread.

AND IT SURVIVES ARRIVING LATE, which is the only reason it can be traded in a
competition whose account is created after the print (`scripts/source_pead_horizon.py`,
`state/source_pead_horizon.json`): the drift is spread evenly over +1/+2/+3
(+0.41 / +0.31 / +0.41%) and the overnight gap is worth +0.05% (t 0.42). Entering
at the day+1 OPEN keeps +1.08% of the +1.13% at t 2.82; a full session late still
keeps +0.72% at t 2.17.

WHAT SHAPE THIS IS
==================
GRADIENT, and it is labelled so deliberately. centre/sd is about 0.21 -- a tilt,
not a tail. `shape.py` maps GRADIENT to size rather than to convexity, and the
cost table above says why that mapping is not academic here: a long option pays
for a jump that the tercile split says is not in this signal. The engine still
enumerates every structure and ranks by EV/max-loss; this brain's job is only to
hand it a distribution that is not a lie.

DELIBERATELY CONSERVATIVE IN TWO PLACES
=======================================
1. It REFUSES while the day-0 bar is still forming. Daily bars cannot tell an
   in-progress session from a closed one, and the measured entry is the day+1
   open anyway -- which costs +0.05%.
2. When one session has elapsed it quotes the LATER arrival's number (+0.72%,
   two sessions left) even though it may be entering at that session's open,
   where the measurement says +1.08%. Under-sizing is the safe error.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from alpha.brains.base import Forecast
from alpha.brains.event_move import event_days_from_sec
from alpha.brains.vol_gap import _daily_bars, _ewma_sd

#: Measured on 108 SEC-dated prints, 11 names, 2024-03-21 .. 2026-08-05.
#: Key: completed sessions since the day-0 close. Value: (centre, sd, sessions left).
#: `sd` is the dispersion of the signed excess in that arrival bucket, recovered
#: from the receipt's own mean/t/n -- it is a FLOOR on the brain's spread, never
#: a substitute for the name's live volatility.
#: Receipts: state/source_pead_horizon.json, state/source_pead_decompose.json
ARRIVAL: dict[int, tuple[float, float, float]] = {
    1: (0.0072, 0.0345, 2.0),
    2: (0.0041, 0.0255, 1.0),
}

#: THE ELEVEN NAMES THE +1.13% TWO-SIDED DRIFT WAS MEASURED ON. Outside them the
#: rule is DIFFERENT, and it was measured on 2,532 names / 25,856 SEC-dated prints
#: (`scripts/pead_wide.py`, `state/pead_wide.json`, 2024-02 .. 2026-08):
#:   DOWN day-0 (3.5-8.2%): +0.44% further in 3 sessions, hit 54%, t +4.29
#:                (>8.2%):  +0.64%, t +5.16; small caps +0.73%, t +4.08; positive every year
#:   UP   day-0 (3.5-8.2%): REVERSES -0.22%, t -1.99; (>8.2%): -0.44%, t -3.23
#: Bad news drifts, good news fades. So outside the mega-caps the brain SHORTS a
#: print that fell and REFUSES a print that rose. The 11-name numbers stay for
#: the 11 names (reproduced in the same run: +1.09%, t 2.72).
MEGA_MEASURED = frozenset({"AAPL", "AMD", "AMZN", "AVGO", "GOOGL", "META", "MSFT", "MU", "NVDA", "PANW", "TSLA"})
#: AMENDED 2026-08-26 after the adversarial battery (`scripts/pead_adversarial.py`,
#: `state/pead_adversarial.json`, `docs/FINDING_2026-08-26_PEAD_ADVERSARIAL.md`):
#:   * the numbers above are EXCESS OVER beta*QQQ. With NO benchmark the mid-band loser
#:     moves +0.03% (t 0.25) -- the "drift" was the loser not joining the index's rise.
#:     An unhedged short is sized on an ABSOLUTE move, so the brain must quote the RAW
#:     short return, not the excess: short at the NEXT OPEN, 3 sessions, raw:
#:       5-8.2%: +0.27% sd 6.7% t 1.87 (hedged long IWM +0.56%, t 3.95)
#:       >8.2%:  +0.32% sd 7.8% t 2.51 (hedged +0.55%, t 4.49)
#:       3.5-5%: -0.05%  -> REFUSED; the response curve is dead below a 5% drop
#:   * UP prints do NOT reverse raw (+0.25%, t 2.49); they only trail QQQ. They stay
#:     refused -- there is no excess to sell and no raw edge to buy -- but the reason is
#:     "no edge", not "reversal".
#:   * the raw short is NEGATIVE in 2026 (-0.14%, t -0.8) and 6 of 11 quarters are
#:     negative in the mid band: conviction is cut, and `hedged_vs_iwm` travels on the row
#:     so a pair expression can be built later without re-measuring.
#:   * AND THEN (agent 1's attack, same day): the legs are LOG returns and a short is paid
#:     in SIMPLE returns (-(exp(r)-1)); a -113% log leg costs a real short -211%. In
#:     simple terms the unhedged raw short is +0.04% (5-8.2%, t 0.22) and +0.00% (>8.2%,
#:     t 0.03): NOTHING. The pair keeps +0.35% / +0.26% (t 2.2 / 2.0). So the wide DOWN
#:     side is REFUSED until a pair structure exists; the constants stay as the record.
WIDE_MIN_ABS_MOVE = 0.05
WIDE_UNHEDGED_SHORT_ENABLED = False
WIDE_DOWN_SIMPLE = {"mid": (0.00036, 0.22), "big": (0.00004, 0.03)}
WIDE_HEDGED_IWM_SIMPLE = {"mid": (0.00346, 2.22), "big": (0.00259, 1.96)}
#: Wide-universe DOWN side: (3-session RAW short-from-next-open centre, 3-session sd).
WIDE_DOWN: dict[str, tuple[float, float]] = {"mid": (0.00272, 0.0673), "big": (0.00319, 0.0780)}
WIDE_HEDGED_IWM = {"mid": (0.00555, 3.95), "big": (0.00548, 4.49)}
WIDE_HEADLINE = {"legs": 25856, "names": 2532, "down_mid_t": 1.87, "down_big_t": 2.51, "up_raw_3d": 0.0025,
                 "up_raw_t": 2.49, "up_vs_qqq_t": -1.99, "two_way_cluster_t_mid_excess": 2.15,
                 "raw_2026": -0.0014, "receipt": "state/pead_adversarial.json"}

#: Below this the tercile split says there is nothing to continue (t 0.66).
MIN_ABS_MOVE = 0.035
#: Above this the print has over-reacted and the drift weakens (t 1.26 vs 3.45).
OVEREXTENDED_MOVE = 0.082
#: The day-0 move must be this recent in the bar series to still be actionable.
MAX_ELAPSED_SESSIONS = max(ARRIVAL)
BETA_WINDOW = 120
VOL_HALF_LIFE = 10.0


class NotApplicable(RuntimeError):
    pass


def forecast(client, symbol: str, horizon_days: float, *, lookback_days: int = 400) -> Forecast:
    bars = _daily_bars(client, symbol, lookback_days)
    if len(bars) < BETA_WINDOW + 10:
        raise NotApplicable(f"{symbol}: only {len(bars)} daily bars, need {BETA_WINDOW + 10}")
    days = [b["t"][:10] for b in bars]
    closes = [float(b["c"]) for b in bars]

    events = event_days_from_sec(bars, symbol)
    if not events:
        raise NotApplicable(f"{symbol}: no SEC 8-K Item 2.02 print in the bar window")
    event = events[-1]
    if event["event_day"] not in days:
        raise NotApplicable(f"{symbol}: print day {event['event_day']} is not a session in the bars")
    i0 = days.index(event["event_day"])
    elapsed = (len(days) - 1) - i0

    if elapsed <= 0:
        raise NotApplicable(
            f"{symbol}: the day-0 close ({event['event_day']}) is still forming. Daily bars cannot "
            "tell an in-progress session from a closed one, and the measured entry is the day+1 "
            "open, which costs +0.05% (t 0.42) to wait for.")
    if elapsed > MAX_ELAPSED_SESSIONS:
        raise NotApplicable(
            f"{symbol}: {elapsed} sessions since the print on {event['event_day']}; the measured "
            f"drift window is +1..+3 and is spent after {MAX_ELAPSED_SESSIONS}")

    r0 = event["move"]                       # log return across the reflecting close
    if abs(r0) < MIN_ABS_MOVE:
        raise NotApplicable(
            f"{symbol}: day-0 move {r0:+.2%} is inside the flat tercile (|move| < {MIN_ABS_MOVE:.1%}, "
            "t 0.66) -- there is nothing to continue and the spread would eat it")

    wide = symbol.upper() not in MEGA_MEASURED
    if wide and r0 > 0:
        raise NotApplicable(
            f"{symbol}: day-0 move {r0:+.2%} is UP and {symbol} is outside the eleven names the two-sided "
            f"drift was measured on. Across {WIDE_HEADLINE['names']} names an UP print carries NO EDGE: raw "
            f"+{WIDE_HEADLINE['up_raw_3d']:.2%}/3d (t {WIDE_HEADLINE['up_raw_t']}) is the index's own drift, and "
            f"against QQQ it trails (t {WIDE_HEADLINE['up_vs_qqq_t']}). Refused: nothing to buy, nothing to sell.")
    if wide and abs(r0) < WIDE_MIN_ABS_MOVE:
        raise NotApplicable(
            f"{symbol}: day-0 move {r0:+.2%} is a drop of less than {WIDE_MIN_ABS_MOVE:.0%}; on the response curve "
            f"({WIDE_HEADLINE['receipt']}) the 3.5-5% zone is dead (raw short -0.05%, t -0.3). Refused.")
    if wide and not WIDE_UNHEDGED_SHORT_ENABLED:
        band_key = "big" if abs(r0) > OVEREXTENDED_MOVE else "mid"
        raise NotApplicable(
            f"{symbol}: day-0 move {r0:+.2%} is a wide-universe DROP, and the unhedged short of it is worth "
            f"{WIDE_DOWN_SIMPLE[band_key][0]:+.2%}/3d in SIMPLE returns (t {WIDE_DOWN_SIMPLE[band_key][1]}) -- the "
            f"log-return drift was the index rising and the short being paid in simple terms. The PAIR (short "
            f"stock / long IWM) keeps {WIDE_HEDGED_IWM_SIMPLE[band_key][0]:+.2%} (t {WIDE_HEDGED_IWM_SIMPLE[band_key][1]}) "
            f"and the engine has no pair structure yet. Refused: nothing to sell unhedged.")
    base_centre, floor_sd, sessions_left = ARRIVAL[elapsed]
    sign = 1.0 if r0 > 0 else -1.0
    centre = sign * base_centre
    if wide:
        # DOWN side, wide universe: the RAW short-from-next-open numbers scaled to the
        # sessions left. Raw, because the structure is an unhedged short and the gate
        # sizes an absolute move; the hedged (long IWM) number rides along in evidence.
        band_key = "big" if abs(r0) > OVEREXTENDED_MOVE else "mid"
        c3, sd3 = WIDE_DOWN[band_key]
        base_centre = c3 * sessions_left / 3.0
        floor_sd = sd3 * math.sqrt(sessions_left / 3.0)
        centre = -base_centre

    # Live spread: the name's own ordinary volatility, measured on the sessions
    # BEFORE the print so the print day cannot inflate it, scaled to what is left
    # of the window -- floored at the dispersion the backtest actually observed.
    event_days_set = {e["event_day"] for e in events}
    pre = [math.log(closes[i] / closes[i - 1]) for i in range(1, i0)
           if days[i] not in event_days_set]
    daily_sd = _ewma_sd(pre[-BETA_WINDOW:], VOL_HALF_LIFE) if pre else 0.0
    sd = max(daily_sd * math.sqrt(sessions_left), floor_sd)

    overextended = abs(r0) > OVEREXTENDED_MOVE
    if wide:
        # Raw t is 1.9 / 2.5 and 2026 is negative: a tilt the gate may well refuse. That
        # is the honest number; the hedged pair (t ~4) is the expression to build next.
        conviction = 0.6 * (1.0 if elapsed == 1 else 0.7)
        band = (f"WIDE universe, DOWN, {'>8.2%' if overextended else '5-8.2%'} band, RAW short from next open "
                f"(t {WIDE_HEADLINE['down_big_t'] if overextended else WIDE_HEADLINE['down_mid_t']}; hedged vs IWM "
                f"t {WIDE_HEDGED_IWM['big' if overextended else 'mid'][1]}; n={WIDE_HEADLINE['legs']} legs)")
    else:
        conviction = (0.6 if overextended else 1.0) * (1.0 if elapsed == 1 else 0.7)
        band = ("over-extended (>8.2%, t 1.26)" if overextended
                else f"mid band ({MIN_ABS_MOVE:.1%}-{OVEREXTENDED_MOVE:.1%}, t 3.45, hit 81%)")

    return Forecast(
        brain="post_event_drift", symbol=symbol, horizon_days=sessions_left,
        centre=centre, sd=sd, conviction=round(conviction, 3), claim="direction",
        rationale=(
            f"{symbol} printed {event['session']} on {event['release_date']}; the first reflecting "
            f"close {event['event_day']} moved {r0:+.2%} -- {band}. {elapsed} session(s) elapsed, so "
            f"{sessions_left:.0f} of the measured +1..+3 drift window remain, worth {centre:+.2%} "
            f"excess over beta*QQQ (n=108, t {2.17 if elapsed == 1 else 1.67:.2f}). Spread {sd:.1%} "
            f"= max(live {daily_sd:.2%}/day over {sessions_left:.0f}d, measured floor {floor_sd:.1%})."),
        signal_shape="gradient",
        evidence={
            # `event_date` is the key `runner.event_node` reads. The drift trade is
            # deliberately booked under the SAME node as the print it follows: a
            # residual condor and a drift spread on that name are two expressions
            # of one scheduled event, and giving the drift its own node would be a
            # carve-out that doubles the exposure the cap exists to bound.
            "event_date": event["event_day"],
            "event_day": event["event_day"], "release_date": event["release_date"],
            "session": event["session"], "date_source": event["date_source"],
            "r_day0": r0, "abs_move_band": band, "elapsed_sessions": elapsed,
            "sessions_left": sessions_left, "measured_centre": base_centre,
            "measured_sd_floor": floor_sd, "live_daily_sd_pre_print": daily_sd,
            "last_close": closes[-1], "asof_utc": datetime.now(timezone.utc).isoformat(),
            "receipts": (["state/pead_wide.json"] if wide else
                         ["state/post_event_relay.json", "state/source_pead_decompose.json",
                          "state/source_pead_horizon.json"]),
            "universe_rule": ("wide: DOWN >=5% only, RAW short-from-open centre (excess-vs-QQQ was the old, wrong, number)"
                              if wide else "mega-11: two-sided"),
            "hedged_vs_iwm": ({"centre_3d": WIDE_HEDGED_IWM["big" if overextended else "mid"][0],
                               "t": WIDE_HEDGED_IWM["big" if overextended else "mid"][1],
                               "note": "short stock + long IWM; not an expression the engine has yet"} if wide else None),
            "raw_2026_3d": WIDE_HEADLINE["raw_2026"] if wide else None,
            "headline": {"n": 108, "names": 11, "mean": 0.0113, "hit": 0.639, "t": 2.72,
                         "week_block_t": 2.23, "worst_leave_one_out_t": 2.37},
        },
    )
