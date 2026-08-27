"""The 25 Aug losses, replayed against the guard that should have stopped them.

Every case here is a REAL position from the dev book, with its real P/L. The test
is not "does the guard have rules" -- it is "would this specific loss have been
refused". A guard written from a finding and never run against the trade the
finding describes is a guard tuned to a paraphrase.
"""
from __future__ import annotations

from alpha import refuted

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


print("refuted routes -- replaying the 25 Aug book")

# --- the two that actually lost money ---------------------------------------
amd = refuted.check(symbol="AMD", kind="long_straddle", event_ahead_on_symbol=False,
                    originators_printing=refuted.peers_printing("AMD", {"NVDA"}))
check("AMD long straddle into NVDA's print is REFUSED (-$4,125 on 25 Aug)",
      amd is not None and amd.route == "PEER_LONG_VOL_INTO_PRINT",
      str(amd))
check("and it cites the 290-leg measurement, not an opinion",
      amd is not None and "290" in amd.evidence)

nvda = refuted.check(symbol="NVDA", kind="long_straddle", event_ahead_on_symbol=True,
                     originators_printing=[])
check("NVDA long premium into its OWN print is REFUSED",
      nvda is not None and nvda.route == "LONG_VOL_INTO_OWN_MEASURED_PRINT", str(nvda))
check("and it cites the 0-for-8", nvda is not None and "0 for 8" in nvda.evidence)

# --- what must STILL be allowed ---------------------------------------------
# A guard that also blocks the working trades is a worse outcome than the losses:
# QQQ (+56%) and SPY (+23%) were the only winners in that book.
for sym, kind in (("QQQ", "long_call"), ("SPY", "long_call")):
    r = refuted.check(symbol=sym, kind=kind, event_ahead_on_symbol=False, originators_printing=[])
    check(f"{sym} {kind} with no event ahead is ALLOWED (it was a winner)", r is None, str(r))

# SHORT premium is not refuted by these findings. The NVDA condors lost, but they
# lost because the implied move they were priced against was computed with the
# 0.85 haircut -- an ARITHMETIC failure, fixed separately. Blocking short vol here
# would be attributing that loss to the wrong cause.
cond = refuted.check(symbol="NVDA", kind="iron_condor", event_ahead_on_symbol=True,
                     originators_printing=[])
check("short premium into a print is NOT refused by these rules", cond is None,
      "the condor loss was an arithmetic bug, not this route")

# A peer with NO pending print is an ordinary name.
quiet = refuted.check(symbol="AMD", kind="long_straddle", event_ahead_on_symbol=False,
                      originators_printing=refuted.peers_printing("AMD", set()))
check("AMD straddle with nobody printing is ALLOWED", quiet is None, str(quiet))

# --- EVIDENCE DOES NOT INHERIT BY ANALOGY (2026-08-27) ----------------------
# The first draft blocked {long_call, long_put} on eight mega caps from a sample
# that contained neither. On 26 Aug that would have refused the one trade the
# research was right about. These cases pin the scope to the sample.

call = refuted.check(symbol="NVDA", kind="long_call", event_ahead_on_symbol=True,
                     originators_printing=[])
check("a DIRECTIONAL long call into NVDA's own print is ADMISSIBLE", call is None,
      "the 0-for-8 is an absolute-move sample; it says nothing about the signed move")

put = refuted.check(symbol="NVDA", kind="long_put", event_ahead_on_symbol=True,
                    originators_printing=[])
check("and so is a long put -- symmetry, not a bullish exception", put is None, str(put))

for sym in ("AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AVGO"):
    r = refuted.check(symbol=sym, kind="long_straddle", event_ahead_on_symbol=True,
                      originators_printing=[])
    check(f"{sym} straddle into its own print is ADMISSIBLE (unmeasured, not refuted)",
          r is None, "the 0-for-8 sample is NVDA's alone")

peer_call = refuted.check(symbol="AMD", kind="long_call", event_ahead_on_symbol=False,
                          originators_printing=refuted.peers_printing("AMD", {"NVDA"}))
check("a peer DIRECTIONAL call into NVDA's print is ADMISSIBLE",
      peer_call is None, "relay_backtest measured peer STRADDLES, not calls")

check("long_call/long_put are NOT in the refusable set",
      not (refuted.LONG_DIRECTIONAL & refuted.LONG_VOL)
      and "long_call" not in refuted.LONG_PREMIUM,
      "LONG_PREMIUM must not be the union again")

# The invariant, not a fixed list: a symbol may be added ONLY with its sample.
# This started as `== {"NVDA"}` and correctly failed when PANW was added, which
# is the right way round -- the test made the author produce the receipt.
check("every refusable symbol names its own sample, with numbers",
      all(len(v) > 40 and any(ch.isdigit() for ch in v)
          for v in refuted.MEASURED_OWN_PRINT.values()),
      "adding a symbol without adding its sample is evidence by analogy")
check("  and cites where the sample lives",
      all(("docs/" in v or "scripts/" in v) for v in refuted.MEASURED_OWN_PRINT.values()),
      "a headline number belongs in a receipt")
check("  and every one of them says how many events",
      all("for" in v or "n=" in v for v in refuted.MEASURED_OWN_PRINT.values()))

check("the untested routes are recorded rather than inferred from silence",
      len(refuted.UNMEASURED) >= 3
      and all("ADMISSIBLE" in why for _, why in refuted.UNMEASURED))

for r in (amd, nvda):
    check(f"{r.route} prints the scope of its own sample", bool(r.scope) and r.scope in r.line())

# --- INDEX STRADDLES: the $14,711 the guard did not cover (2026-08-27) ------
# SPY -$7,849 and QQQ -$6,862 are 63% of both books' realised losses, and neither
# carried a print or a peer relation, so nothing refused them. Measured now:
# scripts/index_premium_backtest, 381 weekly ATM straddles held to expiry.

for sym in ("SPY", "QQQ", "IWM"):
    r = refuted.check(symbol=sym, kind="long_straddle", event_ahead_on_symbol=False,
                      originators_printing=[])
    check(f"{sym} weekly straddle to expiry is REFUSED",
          r is not None and r.route == "INDEX_STRADDLE_TO_EXPIRY", str(r))
    check(f"  and cites {sym}'s OWN measurement, not the pool",
          r is not None and sym in r.evidence and "n=127" in r.evidence)

spy = refuted.check(symbol="SPY", kind="long_straddle", event_ahead_on_symbol=False,
                    originators_printing=[])
check("the refusal carries the caveat that 2026 does NOT resolve",
      "2026 -1.8%" in spy.evidence and "NOT resolvable" in spy.evidence,
      "pooled t -5.90 read alone would overstate what this shows")
check("  and says QQQ 2026 is POSITIVE for the buyer",
      "+14.9%" in spy.evidence,
      "a refusal that hides its own strongest counter-example is not arguable")
check("  and names what the refusal actually rests on -- the median",
      "MEDIAN" in spy.evidence and "median path" in spy.evidence)
check("it reopens for a structure NOT held to expiry",
      "NOT held to expiry" in spy.reopens_if,
      "the loss mechanism is theta; a spread-financed or early-exit trade is a different object")
check("  and it names the theta decomposition that says so",
      "theta -$5,048" in spy.reopens_if)

# A DIRECTIONAL index trade is untouched. QQQ and SPY calls are the structures
# the reviews called winners, and refusing them on straddle evidence would be
# the same inheritance-by-analogy this file was rewritten to remove.
for sym in ("SPY", "QQQ", "IWM"):
    for kind in ("long_call", "long_put"):
        check(f"{sym} {kind} is still ADMISSIBLE",
              refuted.check(symbol=sym, kind=kind, event_ahead_on_symbol=False,
                            originators_printing=[]) is None,
              "the measurement is of the ABSOLUTE move; a call bets the signed move")

check("a non-measured index (DIA) straddle is ADMISSIBLE",
      refuted.check(symbol="DIA", kind="long_straddle", event_ahead_on_symbol=False,
                    originators_printing=[]) is None,
      "no sample, so no refusal -- unmeasured is not refuted")
check("short premium on an index is untouched",
      refuted.check(symbol="SPY", kind="iron_condor", event_ahead_on_symbol=False,
                    originators_printing=[]) is None,
      "realised, condors are -$284 across both books")

# --- PANW AND AVGO, measured BECAUSE they print inside the contest ----------
# Both were admissible only because nobody had looked, and both print in the
# window. One hour of measurement produced one refusal and one null.

panw = refuted.check(symbol="PANW", kind="long_straddle", event_ahead_on_symbol=True,
                     originators_printing=[])
check("PANW straddle into its own print is REFUSED", panw is not None, str(panw))
check("  on 0 for 6 -- every event negative, not a mean dragged by a tail",
      panw is not None and "0 for 6" in panw.evidence and "-2.5" in panw.evidence)

avgo = refuted.check(symbol="AVGO", kind="long_straddle", event_ahead_on_symbol=True,
                     originators_printing=[])
check("AVGO straddle into its own print is ADMISSIBLE", avgo is None,
      "measured +32% mean, and the sample cannot resolve it either way")
_avgo_row = [w for k, w in refuted.UNMEASURED if "AVGO" in k]
check("  and the measurement is RECORDED rather than left as silence", len(_avgo_row) == 1)
check("  naming the tail: one event is 62% of all positive return",
      "62% of all positive return" in _avgo_row[0])
check("  and the leave-one-out that kills it", "+9.2%" in _avgo_row[0]
      and "0.66" in _avgo_row[0])
check("  and that the sample could not have resolved it", "MDE" in _avgo_row[0]
      and "74.8%" in _avgo_row[0])
check("  and that the returns are before costs", "before crossing a spread" in _avgo_row[0])
check("  and WHY the row exists at all", "nobody buys it on the +32%" in _avgo_row[0],
      "AVGO prints 2 Sep and is the obvious thing to buy")

check("AVGO is no longer listed as having NO sample",
      not any("AVGO" in k and "no sample" in w for k, w in refuted.UNMEASURED),
      "it has one now; leaving the old row would make the file disagree with itself")
check("a directional AVGO call into its print stays admissible",
      refuted.check(symbol="AVGO", kind="long_call", event_ahead_on_symbol=True,
                    originators_printing=[]) is None)
check("a directional PANW call stays admissible too",
      refuted.check(symbol="PANW", kind="long_call", event_ahead_on_symbol=True,
                    originators_printing=[]) is None,
      "the PANW sample is an ABSOLUTE-move test; it says nothing about the signed move")

# --- AND THE EIGHT THAT WERE REFUSED ON NVDA'S SAMPLE ----------------------
# The old guard refused long premium on eight mega-caps from one name's numbers.
# Six of those eight now have their own samples and NONE supports the refusal;
# two lean the other way. The guard was wrong on the majority of what it covered.
_mega = [w for k, w in refuted.UNMEASURED if "AAPL" in k]
check("the eight mega-caps are measured and RECORDED", len(_mega) == 1)
check("  and every one of them is ADMISSIBLE",
      all(refuted.check(symbol=s, kind="long_straddle", event_ahead_on_symbol=True,
                        originators_printing=[]) is None
          for s in ("AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AMD", "MU")))
check("  because none of them resolves", "NONE OF THEM RESOLVES" in _mega[0])
check("  stated as observed-effect vs its own MDE", "MDE 29%" in _mega[0]
      and "MDE" in _mega[0])
check("  and pooling is refused as the wrong instrument",
      "average of different things" in _mega[0])
check("  and the standing belief is narrowed to the two names it holds for",
      "TWO NAMES" in _mega[0] and "NVDA and PANW" in _mega[0])
check("only NVDA and PANW are refusable on their own prints",
      set(refuted.MEASURED_OWN_PRINT) == {"NVDA", "PANW"},
      "any addition needs its own resolvable sample")

# --- the rules must be arguable, not obeyed ---------------------------------
for r in (amd, nvda):
    check(f"{r.route} states what would REOPEN it", bool(r.reopens_if and len(r.reopens_if) > 20))

# --- and the guard must actually be WIRED, not merely written ---------------
import inspect

from alpha import runner

src = inspect.getsource(runner)
check("runner imports refuted", "refuted" in src)
check("runner refuses on it", "refuted.check(" in src)
i_ref, i_size = src.find("refuted.check("), src.find("n = contracts_for(")
check("checked BEFORE sizing -- a refuted route is not priced, only declined",
      -1 < i_ref < i_size, f"refuted at {i_ref}, sizing at {i_size}")
check("the printing set is pooled across ALL brains",
      "for f in forecasts:" in src and "printing.add" in src,
      "vol_gap opened the NVDA condors with no event in its own evidence")

print(f"\n{ran} checks")
print("ALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
