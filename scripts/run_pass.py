"""One decision pass over a universe. The agent's main entry point.

    python -m scripts.run_pass --expiry 2026-08-28 --dry-run
    python -m scripts.run_pass --expiry 2026-08-28 --brains vol_gap,event_move --live
    python -m scripts.run_pass --role exp1 --profile maximum --live

`--dry-run` is the default and `--live` must be typed. The asymmetry is
deliberate: the failure that costs something is an unintended order, never an
unintended dry run.

Brains listed in `--shadow` forecast and enumerate but never execute.
"""

from __future__ import annotations

import argparse
import logging
import sys

from alpha import (brains, config, exits, genesis, human, ledger,
                   refusal_classes, runner, sentinels)
from alpha.broker.alpaca import AlpacaPaper

#: Starting universe. Liquid, optionable, spanning several volatility regimes.
UNIVERSE = ["SPY", "QQQ", "IWM", "NVDA", "AVGO", "AMD", "TSLA", "META",
            "AAPL", "MSFT", "GOOGL", "AMZN", "NIO", "PANW", "SMH"]

DEFAULT_BRAINS = "vol_gap,event_move,options_attention,narrative_dispersion,relay,post_event_drift"
#: Brains that WIDEN sigma by construction win the MDM comparison by construction
#: on long premium -- the sizer rewards disagreement, and a wider claim is a bigger
#: disagreement. They earn execution by beating the others in the counterfactual
#: ledger first, not by being loudest.
#:
#: `post_event_drift` is deliberately NOT on this list, and the reason the list
#: exists is the reason: it does the OPPOSITE of widening sigma. It quotes a
#: centre of +0.72% against a spread floored at the dispersion the backtest
#: measured, and it FALLS BACK to the later, smaller arrival number when it
#: cannot tell how late it is. A brain that cannot inflate its own edge does not
#: need the veto this list applies -- the MDM gate and the EV/max-loss ranker are
#: the gates it must pass, and on a 1%-of-spot edge the spread will refuse most
#: structures without help. It is `PRODUCT_EXPERIMENT` on paper accounts; the
#: evidence is in state/source_pead_decompose.json and _horizon.json.
DEFAULT_SHADOW = "options_attention,narrative_dispersion,relay"


def sentinels_rows() -> list[dict]:
    """The decision rows the sentinels judge. One read per pass, not per brain."""
    import json
    from pathlib import Path

    p = Path(__import__("os").getenv("AAT_LEDGER_DIR") or "state") / "decisions.jsonl"
    if not p.exists():
        return []
    out = []
    with p.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:                                          # noqa: BLE001
                continue
    return out


def inject_news_universe(universe_syms: list[str], *, enabled: bool,
                         day: str | None = None, digest: dict | None = None,
                         max_age_hours: float = 18.0, top_n: int | None = None
                         ) -> tuple[list[str], str | None]:
    """Add today's NEWS-DISCOVERED names to the universe. Returns (universe, refusal).

    THE CUT THIS CLOSES (2026-08-31)
    ================================
    `premarket_digest` reads the whole market's news, asks the LLM for a dated
    bet on each name it finds, and writes `state/premarket/<day>.json`. On
    2026-08-31 it ranked **WBUY first** and wrote a real bet: up, +10%, one
    session, 70% already priced, with a falsifier. The stock then moved 20%.

    Nothing acted on it, and not because a gate rejected it -- because no code
    path could see it. Every reader of that file is a shadow tool:
    `dislocation_scan` takes `council_symbols` as a ranking and "places
    nothing"; `discovery_autopsy` classifies movers after the close and "places
    nothing". `run_pass` -- the only thing that places -- built its universe
    from the hardcoded list, the window universe, the candidate file and the
    seal. The digest was never among its inputs.

    This is the SAME SHAPE as the sealed-portfolio cut fixed hours earlier, one
    stage upstream: there the book could not reach the runner, here discovery
    cannot reach the book. Each component ran, wrote a receipt and passed its
    tests; the defect lived between the files, which is why 2,687 checks never
    saw it. A pipeline needs a reachability test, not per-stage correctness.

    WHY IT REFUSES INSTEAD OF PASSING QUIETLY
    ========================================
    "the digest ran and found nothing" and "the digest never ran" are the same
    silence on disk. If the caller asked for news names and there is no fresh
    digest, this returns a refusal so the pass exits non-zero, rather than
    trading a universe that merely looks normal. Absence of a file is not a
    finding of no news.

    WIDENING THE UNIVERSE IS NOT AUTHORISING A TRADE. This adds names the
    brains are ASKED about. Admission, sizing, the liquidity floor and the
    sealed-weight ceiling all still apply downstream and are untouched.

    `digest` is injectable so a test can stage a day without a clock, an LLM or
    a network.
    """
    if not enabled:
        return universe_syms, None
    import json
    from datetime import datetime, timedelta, timezone
    from pathlib import Path

    if digest is None:
        d = day or (datetime.now(timezone.utc) - timedelta(hours=4)).date().isoformat()
        p = Path("state") / "premarket" / f"{d}.json"
        if not p.exists():
            return universe_syms, (
                f"--news-universe was given but {p} does not exist. Refusing: an "
                f"absent digest is not a digest that found nothing.")
        try:
            digest = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return universe_syms, f"--news-universe: {p} is unreadable: {exc}"

    # A STALE DIGEST IS WORSE THAN NONE. Yesterday's news ranked today reads as
    # a live opinion and grades as one.
    gen = str(digest.get("generated_utc") or "")
    try:
        age_h = (datetime.now(timezone.utc)
                 - datetime.fromisoformat(gen.replace("Z", "+00:00"))).total_seconds() / 3600.0
    except ValueError:
        return universe_syms, (f"--news-universe: digest has no readable "
                               f"generated_utc ({gen!r}); refusing to date it by guess.")
    if age_h > max_age_hours:
        return universe_syms, (f"--news-universe: digest is {age_h:.1f}h old "
                               f"(limit {max_age_hours}h). Refusing to trade stale news.")

    # RANK ORDER IS THE DIGEST'S OWN. It scored these names against the news it
    # read; re-scoring them here would be a second, unrecorded opinion.
    bets = digest.get("bets") or []
    ranked = [str(b.get("symbol", "")).upper() for b in bets if b.get("symbol")]
    for s in (digest.get("council_symbols") or []):
        s = str(s).upper()
        if s and s not in ranked:
            ranked.append(s)
    if top_n is not None:
        ranked = ranked[:top_n]

    extra = [s for s in ranked if s not in universe_syms]
    logging.info("news universe from digest %s (%s, %.1fh old): %d bets, "
                 "+%d names -> %s", digest.get("date"),
                 digest.get("universe_mode", "?"), age_h, len(bets), len(extra),
                 ",".join(extra[:12]))
    return universe_syms + extra, None


def inject_sealed_portfolio(universe_syms: list[str], brains: str | None,
                            *, sealed_holdings=None) -> tuple[list[str], str | None]:
    """Add the sealed book's names to the universe. Returns (universe, refusal).

    Extracted from `main` so it can be TESTED rather than grepped. The first
    version of this guard was verified by searching `main`'s source for a
    substring, which proves a string exists and not that a name reaches a
    forecast -- the exact shape of the bug it was written to catch.

    `sealed_holdings` is injectable so a test can stage a book without a
    tracker, a seal or a clock.
    """
    if "tracker_portfolio" not in (brains or ""):
        return universe_syms, None
    try:
        if sealed_holdings is None:
            from alpha.brains import tracker_portfolio as _tp
            sealed_holdings = _tp.sealed_holdings
        sealed = sealed_holdings()
        extra = [s for s in sealed["holdings"] if s not in universe_syms]
        logging.info("sealed portfolio %s (%s, sha %s): +%d names -> %s",
                     sealed.get("book"), sealed.get("day"),
                     str(sealed.get("content_sha256"))[:12], len(extra),
                     ",".join(sorted(sealed["holdings"])))
        return universe_syms + extra, None
    except Exception as exc:                                        # noqa: BLE001
        return universe_syms, (f"tracker_portfolio is enabled but its sealed "
                               f"portfolio could not be read: {exc}")


def _record_deadline_refusal(reason: str) -> None:
    """One typed ledger row for a pass that refused to enter at all.

    Written at PASS scope, not per candidate: no candidate was evaluated, so
    attributing the refusal to a symbol would invent a decision that was never
    made. `symbol` is the sentinel `-` and `brain` names the gate, so the row
    groups cleanly and never contaminates a per-name recall count.

    NEVER RAISES. This is bookkeeping on a control path; a failure to record the
    refusal must not turn a refusal into a crash whose exit code some caller
    reads as something else.
    """
    from datetime import datetime, timezone
    try:
        ledger.record(ledger.Decision(
            decision_id=ledger.new_decision_id("-", "deadline_gate"),
            ts_utc=datetime.now(timezone.utc).isoformat(),
            symbol="-",
            brain="deadline_gate",
            signal_shape=None,
            instrument="none",
            thesis="entry pass refused before any candidate was evaluated",
            predicted_move=None, predicted_sd=None, implied_move=None,
            breakeven_move=None, mdm_edge=None, quote_snapshot={},
            action="refused",
            refusal_reason=reason,
            terminal_state=refusal_classes.terminal_state(reason, action="refused"),
            risk_fraction=0.0, max_loss_usd=0.0, order=None,
            account_role=config.role(),
        ))
    except Exception as exc:                                        # noqa: BLE001
        logging.error("could not record the deadline refusal (the refusal STANDS): %s", exc)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--expiry", required=True, help="YYYY-MM-DD")
    p.add_argument("--role", default=None, help="account role (default: AAT_ACCOUNT_ROLE)")
    p.add_argument("--profile", default=None, choices=sorted(__import__(
        "alpha.engine.sizing", fromlist=["x"]).PROFILES))
    p.add_argument("--horizon", type=float, default=None,
                   help="forecast horizon in TRADING SESSIONS. Default: derived from --expiry. "
                        "This was hardcoded to 3.0 until 27 Aug, so every brain was asked for "
                        "three sessions of movement however long the option actually had -- and "
                        "on the last day before expiry that overstated the width by sqrt(3).")
    p.add_argument("--universe", nargs="*", default=UNIVERSE)
    p.add_argument("--brains", default=DEFAULT_BRAINS, help="comma list of brains to run")
    p.add_argument("--shadow", default=DEFAULT_SHADOW,
                   help="comma list of brains that may not execute (pass '' to let all execute)")
    p.add_argument("--live", action="store_true", help="actually send orders")
    p.add_argument("--allow-expiry-past-deadline", action="store_true",
                   help=("permit an expiry after the judging deadline. It will be liquidated "
                         "at 10:45 ET on the final morning at whatever the spread is."))
    p.add_argument("--allow-entry-past-deadline", action="store_true",
                   help=("permit NEW positions after the liquidation deadline. Attended "
                         "override only: the exit pass liquidates on sight past "
                         "`exits.LIQUIDATE_BY_ET`, so an entry taken after it is round-tripped "
                         "for the spread within minutes. See the churn incident of 2026-09-04."))
    p.add_argument("--no-sentinels", action="store_true",
                   help=("skip the sanity sentinels. They withdraw NEW-POSITION authority "
                         "from a brain that is one-sided against the chain on >90%% of its "
                         "decisions -- the 96.4%% pathology, generalised."))
    p.add_argument("--window-universe", action="store_true",
                   help=("add every name with an earnings event whose drift window reaches "
                         "inside the competition (state/window_universe.json). The hardcoded "
                         "UNIVERSE is fifteen mega-caps and they all report in late July, so "
                         "in late August it produces zero forecasts."))
    p.add_argument("--candidates", action="store_true",
                   help="add today's whole-market candidates (state/candidates/<date>.json) to the universe")
    p.add_argument("--news-universe", action="store_true",
                   help=("add the names TODAY'S NEWS surfaced (state/premarket/<date>.json) "
                         "to the universe, in the digest's own rank order. Closes the cut "
                         "where premarket_digest wrote a bet nothing could act on. REFUSES "
                         "if the digest is missing or stale rather than passing quietly."))
    p.add_argument("--news-top", type=int, default=None,
                   help="cap --news-universe at the N highest-ranked news names")
    p.add_argument("--field-leader", type=float, default=None,
                   help="estimated podium return, e.g. 0.25 for +25%%")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config.load_env()
    # THE FLAG IS AUTHORITATIVE, AND IT IS MADE SO HERE RATHER THAN IN
    # `config.credentials`, so the mutation is visible at the entry point.
    # Every ledger stamp, book match and recovery score reads AAT_ACCOUNT_ROLE
    # from the environment; a `--role` that never reaches it writes rows under
    # the wrong name. `config.credentials` REFUSES if the two disagree, so this
    # only ever fills in a blank. (Audit defect 6.)
    if args.role:
        import os
        os.environ["AAT_ACCOUNT_ROLE"] = args.role.strip().lower()
    client = AlpacaPaper(role=args.role)

    # -- THE JUDGED ACCOUNT MAY NOT BE TRADED WITHOUT A GENESIS RECORD -------
    # `scripts/preflight` prints this too, but preflight is something a person
    # chooses to run. This is on the path every order actually takes, and it is
    # the difference between a limit and a proposal. Non-judged roles are
    # unaffected: the whole point of the record is that only ONE account is
    # being judged.
    if config.role() == genesis.JUDGED_ROLE and args.live:
        ok_gen, gen_lines = genesis.verify(client, role=genesis.JUDGED_ROLE)
        if not ok_gen:
            logging.error("REFUSED -- the judged account cannot be traded:")
            for line in gen_lines:
                logging.error("  %s", line)
            return 2

    # -- THE EXPIRY MUST BE ONE THE CONTEST LIVES TO SEE ---------------------
    # Checked here, before a single chain is fetched, because the cost of getting
    # it wrong is paid on the last morning: exits liquidates at 10:45 ET on
    # judging day, so an option that outlives the window is SOLD into whatever
    # spread exists then, for a thesis that never completed.
    try:
        runner.check_expiry_against_deadline(
            args.expiry,
            slack_days=(365.0 if args.allow_expiry_past_deadline
                        else runner.MAX_EXPIRY_SLACK_DAYS))
    except runner.ExpiryPastDeadline as exc:
        logging.error("REFUSED: %s", exc)
        return 2

    # -- NO NEW RISK ONCE THE EXIT PASS IS LIQUIDATING ON SIGHT ---------------
    # THE ASYMMETRY THAT COST REAL MONEY (2026-09-04, hack1 and hack2).
    #
    # `exits.deadline_liquidation_due` made the EXIT pass liquidate everything
    # past `LIQUIDATE_BY_ET` (10:45 ET) on judging day. Nothing said the same to
    # the ENTRY pass, so the loop kept entering on its ordinary 30-minute
    # cadence and the very next exit pass -- five minutes later, or immediately,
    # because `agent_loop` runs exits straight after entries -- closed what had
    # just been opened. hack2 sold 74 PANW at 11:03:39 ET and bought it back at
    # 11:03:44 ET: five seconds of exposure, two spreads, for a thesis that was
    # never allowed to complete. hack1 left a working short at 11:01:32 ET on a
    # book whose mandate is SAFE.
    #
    # A ONE-SIDED GUARD CATCHES HALF THE ERROR. The deadline is a property of
    # the SESSION, not of the position, so both passes must read it from the
    # same predicate and the same constant -- which is why this calls
    # `exits.deadline_liquidation_due` rather than re-deriving 10:45 here.
    #
    # This is a REFUSAL, not a skip: it writes one typed row so the pass that
    # did not trade is visible in the ledger as a decision. An entry pass that
    # silently produced nothing reads exactly like a quiet market, and this repo
    # has paid twice for an absence that read as a decision.
    _deadline_utc = config.COMPETITION["deadline_utc"]
    if not args.allow_entry_past_deadline and exits.deadline_liquidation_due(_deadline_utc):
        reason = (
            f"{refusal_classes.PAST_LIQUIDATION_DEADLINE}: past "
            f"{exits.LIQUIDATE_BY_ET.strftime('%H:%M')} ET on judging day "
            f"({_deadline_utc}). The exit pass liquidates every open position on "
            "sight from this minute, so a new position would be round-tripped for "
            "the spread within one cycle. Entry authority is withdrawn for the rest "
            "of the session; exits, stops, fills and marking continue. Override with "
            "--allow-entry-past-deadline."
        )
        logging.error("REFUSED: %s", reason)
        _record_deadline_refusal(reason)
        return 3

    universe_syms = list(args.universe)
    if args.window_universe:
        # THE UNIVERSE IS A CONSEQUENCE OF THE CALENDAR, NOT A CONSTANT.
        #
        # `UNIVERSE` above is fifteen mega-caps, and mega-caps report in the last
        # week of JULY. On 27 Aug a dry pass over it produced ZERO forecasts --
        # every line `NotApplicable`, every name 19-25 sessions past its print
        # against a drift window of +1..+3. The agent was pointed at the one
        # slice of the market guaranteed to have no events during the contest,
        # and a book that refuses everything scores zero while looking careful.
        import json as _json
        from pathlib import Path as _Path

        src = _Path("state") / "window_universe.json"
        if not src.exists():
            logging.error("--window-universe needs state/window_universe.json; run "
                          "`python -m scripts.window_universe --json` first")
            return 2
        data = _json.loads(src.read_text(encoding="utf-8"))
        extra = [s for s in data.get("universe", []) if s not in universe_syms]
        universe_syms += extra
        logging.info("window universe from %s (generated %s): +%d names with an event "
                     "reaching inside the contest", src.name,
                     data.get("generated_utc", "?")[:16], len(extra))
    if args.candidates:
        import json
        from pathlib import Path

        files = sorted((Path("state") / "candidates").glob("*.json"))
        if files:
            data = json.loads(files[-1].read_text(encoding="utf-8"))
            extra = [c["symbol"] for c in data.get("candidates", []) if c["symbol"] not in universe_syms]
            universe_syms += extra
            logging.info("candidates from %s: +%d symbols (%s)", files[-1].name, len(extra), ",".join(extra[:12]))
        else:
            logging.warning("--candidates given but no state/candidates/*.json exists; universe unchanged")

    # DISCOVERY MUST REACH THE BOOK. The digest reads the whole market's news
    # and ranks what it finds; until 2026-08-31 nothing that could place an
    # order read its output. See `inject_news_universe` for the full account.
    universe_syms, refusal = inject_news_universe(
        universe_syms, enabled=bool(getattr(args, "news_universe", False)),
        top_n=getattr(args, "news_top", None))
    if refusal:
        logging.error("%s", refusal)
        return 2

    # THE SEALED PORTFOLIO MUST BE ASKABLE. The universe was built from the
    # hardcoded list, the window universe and the candidate file -- none of
    # which reads the seal. So a name could be in `portfolios[<role>].holdings`,
    # with `tracker_portfolio` enabled and the brain ready to answer for it, and
    # the runner would never ASK, because the name was not in the universe. The
    # book would have proved which names trade and then traded none of them.
    #
    # Injected whenever the brain is enabled -- not behind its own flag, because
    # a flag that must be remembered is the same failure one step later.
    universe_syms, refusal = inject_sealed_portfolio(universe_syms, args.brains)
    if refusal:
        # REFUSE rather than trade a partial book. Silently running the other
        # brains over a universe missing the sealed names would look like a
        # normal session and would grade as one.
        logging.error("%s", refusal)
        return 2
    args.universe = universe_syms
    names = [b.strip() for b in args.brains.split(",") if b.strip()]
    unknown = [b for b in names if b not in brains.BRAINS]
    if unknown:
        logging.error("unknown brains %s; have %s", unknown, sorted(brains.BRAINS))
        return 2
    horizon = args.horizon
    if horizon is None:
        from datetime import datetime, timezone
        from alpha.engine.structures import _days as _sessions_to

        class _Now:                       # _days only reads .fetched_at
            fetched_at = datetime.now(timezone.utc)
        horizon = _sessions_to(_Now(), args.expiry)
        logging.info("horizon derived from expiry %s: %.2f trading sessions", args.expiry, horizon)
    if horizon <= 0:
        logging.error("horizon resolved to %.2f sessions; refusing to forecast a zero-length window", horizon)
        return 2
    # -- SANITY SENTINELS (alpha/sentinels.py) -------------------------------
    # A brain that thinks the chain is cheap on >90% of its decisions is holding
    # a ruler that reads long, not finding an edge. Measured on the whole ledger:
    # relay 99.0%, narrative_dispersion 96.1%, options_attention 95.4%, vol_gap
    # 93.1% -- four of five, not just the one quarantined by hand. event_move,
    # the only brain that never executed, is the only one that reads balanced.
    #
    # It withdraws NEW-POSITION authority and nothing else, by adding the brain
    # to the shadow set: it still forecasts, still enumerates, still gets graded
    # in the counterfactual. Exits, marking and management are untouched --
    # quarantining those would turn a measurement problem into a trapped book.
    shadow_list = [b.strip() for b in args.shadow.split(",") if b.strip()]
    if not args.no_sentinels:
        try:
            _rows = sentinels_rows()
            _broken = sentinels.broken(_rows)
        except Exception as exc:                                       # noqa: BLE001
            logging.warning("sentinels could not run (%s); proceeding WITHOUT them and "
                            "saying so rather than treating silence as a pass", exc)
            _broken = set()
        for b in sorted(_broken - set(shadow_list)):
            logging.warning("SENTINEL: %s loses NEW-POSITION authority this pass", b)
            shadow_list.append(b)
        if _broken:
            logging.info("run `python -m scripts.sentinels` for the numbers behind that")

    forecasts, declined = brains.forecast_all(
        client, args.universe, horizon, brains=names, expiries=[args.expiry])
    for d in declined:
        logging.info("declined %-20s %-6s %s", d["brain"], d["symbol"], d["why"])

    # -- THE HUMAN ARM (alpha/human.py) --------------------------------------
    # A module with no caller is the failure this whole session is about:
    # `book_limits.py` was "implemented, tested, and called by NOTHING" while
    # the book it should have bounded reached 72.9% of equity. So the human
    # theses enter HERE, in the one function that produces the forecast list,
    # and they enter as ordinary forecasts with no privileges -- the same claim
    # matrix, chain width, sizer, refuted routes, admission and latch.
    #
    # Their symbols are UNIONED into the universe rather than filtered against
    # it. A thesis about a name nobody put on the command line is exactly the
    # case this exists for: on 26 Aug the view existed and the universe did not
    # contain the expression that would have paid.
    human_forecasts = human.forecasts_for(
        set(args.universe) | {t.symbol.upper() for t in human.open_theses()})
    for f in human_forecasts:
        args.universe = list(dict.fromkeys(list(args.universe) + [f.symbol]))
        logging.info("HUMAN THESIS %-6s %-12s centre %+.2f%% conv %.2f  falsifier: %s",
                     f.symbol, f.claim, f.centre * 100, f.conviction,
                     str(f.evidence.get("falsifier"))[:70])
    forecasts = list(forecasts) + human_forecasts
    if human_forecasts:
        logging.info("human arm contributed %d forecast(s); %d open thesis/theses on file",
                     len(human_forecasts), len(human.open_theses()))

    if not forecasts:
        logging.error("no forecasts produced; refusing to run an empty pass")
        return 1

    result = runner.run_pass(
        client, forecasts, expiry=args.expiry, risk_profile=args.profile,
        dry_run=not args.live, field_leader_estimate=args.field_leader,
        shadow_brains=tuple(shadow_list),
    )
    ok, msg = ledger.verify_chain()
    logging.info("brains=%d forecasts=%d declined=%d | considered=%d submitted=%d refused=%d "
                 "dry_run=%d shadow=%d errors=%d | ledger: %s", len(names), len(forecasts),
                 len(declined), result.considered, result.submitted, result.refused,
                 result.dry_run, result.shadow, result.errors, msg)
    # WHY it refused, which is the only part that says what to work on next. A
    # pass that refused everything on `risk` and one that refused everything on
    # `evidence` print the same headline and call for opposite work.
    logging.info("refusals by class: %s", result.decomposition())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
