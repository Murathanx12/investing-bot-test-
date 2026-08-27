# FINDING — the whole contest is three events, and that changes what to build tonight

Measured 2026-08-27 by intersecting `state/window_universe.json` (95 names with
an earnings event reaching inside the contest) with what `post_event_drift` is
actually permitted to trade.

## THE INTERSECTION IS THREE

`post_event_drift` is two-sided on **eleven** names only —
`MEGA_MEASURED = {AAPL, AMD, AMZN, AVGO, GOOGL, META, MSFT, MU, NVDA, PANW, TSLA}`.
Outside that set the brain refuses in both directions, and both refusals are
right:

- an **UP** print in the wide universe carries **no edge** — raw +0.03%/3d, and
  against QQQ it trails. The "drift" was the index rising;
- a **DOWN** print is refused because `WIDE_UNHEDGED_SHORT_ENABLED = False`: the
  unhedged short is worth +0.04%/3d (t 0.22) in simple returns, and the version
  that works — short the loser, long IWM, +0.35% (t ~2) — **needs a pair
  structure the engine does not have**.

Of the eleven, exactly three print inside the window:

| name | reacts | drift window | usable |
|---|---|---|---|
| **NVDA** | Thu 27 Aug | 27, 28, 31 Aug | **day one only** (28 Aug), then spent |
| **PANW** | Wed 2 Sep | 2, 3, 4 Sep | full |
| **AVGO** | Thu 3 Sep | 3, 4 Sep | truncated by the deadline |

Each still needs its day-0 move to clear `MIN_ABS_MOVE`, so **three is a ceiling,
not a forecast.** It could be two. It could be one.

## WHAT THAT MEANS, STATED PLAINLY

**The contest's headline strategy generates single-digit decisions.** At the
conservative profile's ~2% of equity per position, three winning trades at the
measured +0.72%/+1.08% drift move the account by well under one percent. The
realistic P&L contribution from `post_event_drift` alone is **near zero, in
either direction.**

That is not an argument against it. It is an argument that **it cannot be the
only source**, and finding that out tonight is worth more than any guard added
today. The engine is safe, correct, and pointed at almost nothing.

## SO THE PRIORITY ORDER FLIPS

1. **`HUMAN_THESIS_ARM_v1` stops being a nice-to-have and becomes the primary
   decision source.** It is the only channel that can produce a thesis on a name
   with no 8-K in the drift window, on a macro event, or on a view the brains
   have no measurement for. Built and wired today; on this arithmetic it is
   load-bearing.
2. **NFP on Fri 4 Sep, 08:30 ET.** `EVENT_RESERVE` already holds 10% of the cap
   for `2026-09-04` and `scripts/nfp_trade.py` exists. The jobs report is the one
   scheduled macro event inside the window, it lands 2.5 hours before judging,
   and the reserve was put there precisely so ordinary passes could not spend the
   budget before it arrived.
3. **`event_move` on PANW (1 Sep) and AVGO (2 Sep)** is admissible — it needs a
   scheduled print within two days and neither name is in
   `MEASURED_OWN_PRINT`. **Treat with suspicion.** It buys straddles into a
   print, which is the route that produced −$22,017, and the only reason it is
   not refused is that nobody has measured PANW or AVGO. Unmeasured is not
   refuted, and it is also not licensed. Running the 8-print straddle test on
   those two names is a couple of hours of work and would settle it.
4. **The pair structure** — short the loser, long IWM — is the single change that
   would unlock the whole wide universe's DOWN side, where the measurement is
   already positive (+0.35%, t ~2). It is real work and it is **not** a thing to
   build the night before a contest.

## THE HONEST SUMMARY FOR THE MORNING

The system is in the best state it has ever been in and has almost nothing to do
with it. Every guard added today is correct and every one of them was needed;
none of them creates an opportunity. **Three events, one human arm, one jobs
report.**

Anyone reading the refusal log during the contest will see hundreds of
`NotApplicable` lines and should read them as *"the universe is barren for this
brain"*, not as *"the engine is broken"* — and the way to tell the difference is
that the refusal names its measurement every time.
