"""THE DAILY LEARNING REPORT -- one page: what the books did, what they refused,
what the shadow said, and what moved onto or off the watchlist.

    python -m scripts.daily_learning_report                    # last COMPLETED session
    python -m scripts.daily_learning_report --day 2026-09-02
    python -m scripts.daily_learning_report --json

WHY THIS EXISTS (build-queue item #11, HANDOFF_2026-09-03_S36)
==============================================================
Every piece of this page already existed somewhere -- fleet_health has the
venue sweep, utilization has the seal-vs-held delta, refusal_regret prices the
roads not taken, the finance repo's shadow book scores the tracker nightly --
and NOBODY READ THEM TOGETHER. The sequential-learning rule (mission rule 1)
says the question is "given what was knowable at t, what action, what
alternative, what happened, and what should change?" -- which is a single page
per day, not five consoles. This script is that page.

THE HOUSE RULES IT OBEYS
========================
* READ-ONLY. It issues GETs and reads files. It submits nothing, cancels
  nothing, touches no seal, and writes exactly one artefact: its own receipt at
  `state/learning_report/<day>.json`. Every headline number on the console is
  in the receipt -- `corr = 0.516` once lived in prose only and turned out to
  be a filtered subset nobody had named.
* A SECTION DERIVES ITS INPUTS OR REFUSES, **AND NAMES WHOSE FAULT IT IS**
  (B3, 2026-09-05). Every refusal carries `cause`: `PLUMBING` (our own wiring
  did not deliver an input that exists -- a dead job, an unset path) or
  `NO_DATA_YET` (the input genuinely does not exist, which is a CORRECT refusal
  and stays). The header prints the census of both, because a permanent red
  line teaches readers to skim whichever kind it is, and the two need opposite
  responses: fix the first, leave the second alone.
* ONE SPY CLOSE SOURCE: `alpha/spy.py`, on the SIP tape. This page used
  `client.stock_bars` (feed = `config.stock_feed()`) while `move_decomposition`
  and `logic_brain` used `stock_bars_multi` (feed = sip). Measured on the
  2026-09-04 page: the two tapes gave SPY genesis closes of 769.28 and 769.35,
  a 0.01pp difference in every role's benchmark regret. Small, and exactly the
  kind of unnamed disagreement nobody can adjudicate later.
* FAILURES ARE COLLECTED, NEVER FATAL. One unreachable account must not
  collapse the page (fleet_health's contract, Murat 2026-09-02).
* THE DAY IS DERIVED, NEVER ASSUMED. Default is the most recent COMPLETED
  session by the VENUE's own calendar and clock -- the machine runs UTC+8 and
  the scheduler runs ET, and asserting "today" from either local clock is the
  two-clocks trap. With the venue unreachable and no --day given it refuses.
* KNOWN FACT, REPORTED NOT REPAIRED: the decisions-ledger hash chain has been
  torn since 25 Aug. This report reads refusal rows from the counterfactual
  ledger beside it and does not verify, repair, or conceal that tear --
  repairing a tamper-evident chain IS the tampering.

WHAT EACH SECTION MEANS
=======================
(a) SCOREBOARD    equity at the session close, day P&L, P&L vs the frozen
                  $100k genesis, and benchmark regret vs SPY -- same window
                  convention as state/benchmark_regret_20260903.json: SPY's
                  first daily bar on/after the genesis kickoff date to the
                  report day's close, venue bars, so cash drag is a NUMBER.
(b) BOOKS vs FILLS  yesterday's sealed book per role against what the venue
                  says actually happened: admitted / filled / expired /
                  canceled / stopped, all NAMED. The seal is intent; fills are
                  fact; the difference is the execution lesson of the day.
(c) REFUSAL REGRET  the day's refused decisions from the counterfactual
                  ledger, grouped by guard, graded and ungraded split -- an
                  ungraded world contributes its COUNT and nothing else
                  (the daily_latch 312/312-on-$0.00 lesson, retro 2026-09-02).
(d) SHADOW        the finance repo's shadow book for the day, if it wrote one.
                  `status: REFUSED` is a FINDING and its reasons are printed.
                  A missing DIRECTORY is PLUMBING and names `AEGIS_SHADOW_DIR`;
                  a present directory missing this one day is NO_DATA_YET and
                  says which day IS the newest, because that repo's nightly job
                  owes us nothing.
(e) WATCHLIST     tracker entrants and dropouts vs the prior tracker day, out of
                  `AAT_TRACKER_DIR` (default `<ledger dir>/tracker`). A missing
                  directory and a missing day are separate refusals.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpha import spy as _spy
from alpha.exits import ET_OFFSET

ROOT = Path(__file__).resolve().parent.parent
#: The six competition accounts, in fleet order (fleet_health's ROLES).
ROLES = ("hack1", "hack2", "hack3", "hack4", "hack5", "hack6")
CANNOT = "CANNOT DETERMINE"

# ---------------------------------------------------------------------------
# THE TWO KINDS OF "CANNOT DETERMINE" (B3, 2026-09-05)
# ---------------------------------------------------------------------------
# They were the same red line until tonight, and they are not the same fact.
#
#   PLUMBING   -- OUR wiring did not deliver an input that exists. A job that
#                 stopped writing, a path nobody set, an env var missing. This
#                 is a BUG with an owner and a command, and it must not be read
#                 as evidence about the market.
#   NO_DATA    -- the input genuinely does not exist yet: the day has no rows
#                 because nothing happened, or the producer legitimately owes us
#                 nothing. This is a CORRECT REFUSAL and it stays.
#
# "A gate that cannot go green is a broken gate" cuts both ways: a permanent red
# line that is actually a correct refusal teaches the reader to skim, and a
# permanent red line that is actually our own dead job teaches them to skim
# harder. Every refusal below carries `cause`, and the page prints it.
CAUSE_PLUMBING = "PLUMBING"
CAUSE_NO_DATA = "NO_DATA_YET"


def _cannot(why: str, cause: str, **extra) -> dict:
    """A refusal that names WHOSE fault it is. `fix` is the command, when there is one."""
    return {"status": CANNOT, "cause": cause, "why": why, **extra}


#: Reported as a standing fact wherever this page reads beside the decisions
#: ledger. Do not repair it here; do not stop printing it until it is resolved
#: by an attended investigation.
LEDGER_TEAR_FACT = ("known fact: the decisions-ledger hash chain is TORN (since 25 Aug, "
                    "~line 1203). Read, reported, NOT repaired -- repairing a "
                    "tamper-evident chain is the tampering.")


def _state_dir() -> Path:
    return Path(os.getenv("AAT_LEDGER_DIR") or (ROOT / "state"))


def _et_date(ts: str | None) -> str | None:
    """The ET session date of an ISO UTC timestamp, by the repo's ONE clock
    convention (`alpha.exits.ET_OFFSET`). A 20:05 ET fill is already the next
    UTC date; matching order timestamps to a session by their raw UTC prefix
    mis-files everything in that four-hour window."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt.astimezone(timezone.utc) + ET_OFFSET).date().isoformat()


# ---------------------------------------------------------------------------
# The day: derived from the venue's calendar, never from a local clock
# ---------------------------------------------------------------------------

def most_recent_completed_session(now_utc: datetime, calendar_days: list[dict]) -> str | None:
    """The latest venue session whose CLOSE is behind us.

    `calendar_days` is the venue's own `/v2/calendar` payload: dicts carrying
    `date` (YYYY-MM-DD) and `close` (HH:MM, ET). A session is completed when
    now-in-ET is past its close. Half-days close at 13:00 and this honours
    that, which a hardcoded 16:00 would not. Returns None when no listed
    session has closed -- the caller refuses rather than guessing."""
    now_et = now_utc.astimezone(timezone.utc) + ET_OFFSET
    done: list[str] = []
    for c in calendar_days:
        d, close = str(c.get("date") or ""), str(c.get("close") or "16:00")
        try:
            close_et = datetime.fromisoformat(f"{d}T{close}:00").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if now_et.replace(tzinfo=timezone.utc) > close_et:
            done.append(d)
    return max(done) if done else None


# ---------------------------------------------------------------------------
# (a) SCOREBOARD
# ---------------------------------------------------------------------------

def spy_window(bars: list[dict], genesis_day: str, day: str) -> dict:
    """SPY over the competition window -- ONE implementation, in `alpha.spy`.

    This wrapper exists only so callers that already hold a bar list keep
    working; the convention (first bar on/after genesis, refuse if the day has
    no bar) and the FEED now live in exactly one file. Before tonight four
    modules read SPY closes and two of them were on different tapes.
    """
    return _spy.window(_spy.closes_from_bars(bars), genesis_day=genesis_day, day=day)


def scoreboard_row(role: str, genesis: dict | None, history: dict[str, float],
                   day: str, spy: dict, *, live_equity: float | None = None,
                   live_equity_day: str | None = None) -> dict:
    """One role's line. Every number that cannot be derived says so by NAME --
    a dash in a scoreboard is a number someone will assume.

    THE LIVE-EQUITY FALLBACK (B3, 2026-09-05). `portfolio_history` is the venue's
    own daily series and it does not always carry the newest session: on
    2026-09-04 it lagged the account by a session on three roles, and the whole
    scoreboard printed CANNOT DETERMINE beside a venue that would have answered
    `GET /v2/account` instantly. That was OUR plumbing, not missing data. So:
    when the history has no row for `day` AND `day` is the session the live
    account is reporting, the live equity is used and the row SAYS SO in
    `equity_source`. It is never used for an older day -- `GET /v2/account` is
    today's number, and stamping it onto last Tuesday would be a fabrication.
    """
    row: dict = {"role": role}
    eq = history.get(day)
    source = "portfolio_history 1D"
    if eq is None and live_equity is not None and live_equity_day == day:
        eq, source = float(live_equity), "LIVE account equity (portfolio_history had no row)"
    if eq is None:
        row["status"] = CANNOT
        # live equity READ and for another day => the day itself has no row: honest.
        # live equity NOT read at all => we never asked the venue: our plumbing.
        row["cause"] = CAUSE_NO_DATA if live_equity is not None else CAUSE_PLUMBING
        row["why"] = (f"portfolio history has no equity for {day} "
                      f"(days present: {sorted(history)[-3:] if history else 'none'})"
                      + (f"; the live account reports {live_equity_day}, not {day}, so its "
                         "equity is NOT stamped onto this day"
                         if live_equity is not None else ""))
        return row
    row["status"] = "ok"
    row["equity"] = round(eq, 2)
    row["equity_source"] = source
    prior = [d for d in history if d < day]
    if prior:
        prev_d = max(prior)
        row["prev_session"] = prev_d
        row["day_pnl_usd"] = round(eq - history[prev_d], 2)
    else:
        row["day_pnl_usd"] = None
        row["day_pnl_why"] = "no earlier session in portfolio history"
    start_eq = ((genesis or {}).get("starting_equity")
                or ((genesis or {}).get("competition") or {}).get("required_starting_equity"))
    if start_eq:
        row["genesis_equity"] = start_eq
        row["pnl_vs_genesis_usd"] = round(eq - start_eq, 2)
        row["pnl_vs_genesis_pct"] = round((eq / start_eq - 1) * 100, 3)
        if spy.get("status") == "ok":
            row["benchmark_regret_pp"] = round(row["pnl_vs_genesis_pct"] - spy["return_pct"], 3)
        else:
            row["benchmark_regret_pp"] = None
            row["regret_why"] = f"SPY window: {spy.get('why')}"
    else:
        row["pnl_vs_genesis_usd"] = None
        row["pnl_vs_genesis_why"] = f"no genesis file for {role} (state/genesis_{role}.json)"
    return row


# ---------------------------------------------------------------------------
# (b) BOOKS vs FILLS
# ---------------------------------------------------------------------------

def _is_stop(order: dict) -> bool:
    return "stop" in str(order.get("order_type") or order.get("type") or "").lower()


def books_vs_fills(portfolio: dict | None, orders: list[dict], day: str,
                   *, seal_exists: bool = True) -> dict:
    """The sealed intent against the venue's account of the day.

    `portfolio` is one role's block from the sealed prediction book (the same
    object `scripts/utilization.intent_row` reads); `orders` is the venue's
    order list for that role. An order belongs to `day` by the ET date of its
    fill if it filled, else of its submission -- an order submitted Tuesday
    that filled Wednesday is Wednesday's fact."""
    day_orders = [o for o in orders
                  if _et_date(o.get("filled_at") or o.get("submitted_at")) == day]
    filled = [o for o in day_orders if str(o.get("status")) == "filled"]
    expired = sorted({str(o.get("symbol")) for o in day_orders
                      if str(o.get("status")) == "expired"})
    canceled = sorted({str(o.get("symbol")) for o in day_orders
                       if str(o.get("status")) == "canceled"})
    stopped = sorted({str(o.get("symbol")) for o in filled
                      if _is_stop(o) and str(o.get("side")) == "sell"})
    buys = {str(o.get("symbol")) for o in filled if str(o.get("side")) == "buy"}
    sells = {str(o.get("symbol")) for o in filled if str(o.get("side")) == "sell"}

    out: dict = {"n_orders_day": len(day_orders), "n_filled": len(filled),
                 "filled_buys": sorted(buys), "filled_sells": sorted(sells),
                 "expired": expired, "canceled": canceled, "stopped": stopped}
    if portfolio is None:
        out["status"] = "no sealed portfolio"
        # TWO DIFFERENT FACTS, and reading them as one was a real mis-report: on
        # 2026-09-04 every role including the three TRACKER books printed
        # "normal for non-tracker books" when the truth was that NO seal existed
        # for the day at all. A sentence that is right for hack1 and wrong for
        # hack4 is worse than a refusal.
        if not seal_exists:
            out["cause"] = CAUSE_PLUMBING
            out["why"] = (f"there is NO sealed book for {day} in state/predictions or "
                          f"docs/seed/predictions -- nothing was sealed that day, for any "
                          f"role. The fills above are still the day's fact.")
            out["fix"] = "python -m scripts.prediction_book --seal --universe tracker"
        else:
            out["cause"] = CAUSE_NO_DATA
            out["why"] = ("a seal EXISTS for this day and this role has no block in it -- "
                          "normal for non-tracker books; its fills above are still the "
                          "day's fact")
        return out
    sealed = [str(h.get("symbol")) for h in (portfolio.get("holdings") or [])]
    out.update({
        "status": "ok",
        "admitted": portfolio.get("n_selected"),
        "sealed_symbols": sealed,
        "sealed_filled": sorted(s for s in sealed if s in buys),
        "sealed_unfilled": sorted(s for s in sealed if s not in buys),
        "off_book_fills": sorted((buys | sells) - set(sealed)),
    })
    return out


# ---------------------------------------------------------------------------
# (c) REFUSAL REGRET, one day
# ---------------------------------------------------------------------------

def refusal_day_summary(rows: list[dict], day: str, *,
                        marker_last_day: str | None = None) -> dict:
    """The day's refusals from the counterfactual ledger, by guard.

    Reuses the standing machinery rather than re-deriving it:
    `alpha.guards.classify` names the guard and its class, and
    `scripts.refusal_regret.is_graded` decides whether a world was PRICED.
    The grading split is load-bearing: an ungraded world carries pnl_usd = 0.0
    which is an absence wearing a number, and pooling those made daily_latch
    report 312 wins out of 312 on $0.00. Last mark per decision_id, so an
    hourly re-mark is not counted twenty times."""
    from alpha import guards
    from scripts.refusal_regret import is_graded

    last: dict[str, tuple] = {}
    for r in rows:
        if r.get("action") != "refused":
            continue
        if _et_date(r.get("ts_utc")) != day:
            continue
        reason = str(r.get("refusal_reason") or "")
        if reason.startswith("the null"):
            continue  # abstaining pays exactly zero, by construction
        out = r.get("outcome") or {}
        pnl = out.get("pnl_usd")
        last[str(r.get("decision_id"))] = (reason, pnl, str(r.get("symbol")), is_graded(r))

    if not last:
        # THE MARKER'S OWN CLOCK DECIDES WHICH SILENCE THIS IS (B3, 2026-09-05).
        # Until tonight this returned one CANNOT DETERMINE for three different
        # facts and said it could not tell them apart. It can: the newest row in
        # the ledger dates the marker. On 2026-09-05 that row was 2026-08-28 --
        # the counterfactual pass had not run for eight days, and the page was
        # reporting that as "either nothing was refused or ...". It was neither.
        if marker_last_day is None:
            return _cannot(
                f"state/counterfactual.jsonl has NO readable rows at all, so the "
                f"counterfactual marker has never run against this ledger directory "
                f"({_state_dir()}). Nothing about {day} follows from this.",
                CAUSE_PLUMBING, fix="python -m scripts.counterfactual --record")
        if marker_last_day < day:
            return _cannot(
                f"the counterfactual marker last wrote {marker_last_day}, which is BEFORE "
                f"{day}. This is our own job not running, not a day on which nothing was "
                f"refused -- do not read it as evidence either way.",
                CAUSE_PLUMBING, marker_last_day=marker_last_day,
                fix="python -m scripts.counterfactual --record")
        return {"status": "ok", "n_refused_decisions": 0, "n_graded": 0, "n_ungraded": 0,
                "by_guard": {}, "marker_last_day": marker_last_day,
                "ledger_note": LEDGER_TEAR_FACT,
                "reading": (f"the marker ran through {marker_last_day} and recorded NO refusal "
                            f"dated {day}. That is a fact about the day, not a gap in the page.")}

    by: dict[str, dict] = {}
    for reason, pnl, sym, graded in last.values():
        g = guards.classify(reason)
        key = g.key if g else "UNCLASSIFIED: " + reason[:40]
        b = by.setdefault(key, {"class": g.cls if g else "UNCLASSIFIED", "n": 0,
                                "graded": 0, "ungraded": 0, "saved_usd": 0.0,
                                "cost_usd": 0.0, "symbols": []})
        b["n"] += 1
        b["graded" if graded else "ungraded"] += 1
        if sym and sym not in b["symbols"] and len(b["symbols"]) < 8:
            b["symbols"].append(sym)
        if graded and pnl is not None:
            if pnl < 0:
                b["saved_usd"] = round(b["saved_usd"] + -float(pnl), 2)
            elif pnl > 0:
                b["cost_usd"] = round(b["cost_usd"] + float(pnl), 2)
    n_graded = sum(b["graded"] for b in by.values())
    return {"status": "ok", "n_refused_decisions": len(last), "n_graded": n_graded,
            "n_ungraded": len(last) - n_graded,
            "by_guard": dict(sorted(by.items(), key=lambda kv: -kv[1]["n"])),
            "ledger_note": LEDGER_TEAR_FACT,
            "reading": ("saved = refused worlds that LOST; cost = refused worlds that "
                        "WON; both over GRADED rows only, at the marker's stated risk "
                        "budget. An ungraded row is counted and priced at nothing.")}


# ---------------------------------------------------------------------------
# (d) SHADOW
# ---------------------------------------------------------------------------

def holding_discipline(rows: list[dict], day: str) -> dict:
    """Did the books HOLD, and when they did not, under which typed reason.

    THE QUESTION THAT TOOK A MONTH TO ASK (S39, 2026-09-04)
    ======================================================
    60% of this fleet's round trips finished in the session they opened, on
    books whose sealed thesis is a 21-session drift. Nothing in any report said
    so: exits carried PROSE, and prose does not aggregate. `ExitVerdict.code`
    now writes one of `alpha.contract.EXIT_REASONS` onto every exit row, and
    this section is the `group by` that makes the churn visible the morning
    after rather than the month after.

    Read it as: HORIZON_SPENT and PROFIT_TARGET are the book working. Anything
    else in quantity is the EXIT RULE trading, not the thesis.
    """
    from alpha import contract as _contract

    by_reason: dict[str, int] = {}
    untyped = 0
    same_session = 0
    exits_today = 0
    entries = {}
    for r in rows:
        if r.get("action") == "submitted" and r.get("symbol"):
            entries.setdefault(str(r["symbol"]), _et_date(r.get("ts_utc")))
        if r.get("brain") != "exit" or r.get("action") != "closed":
            continue
        if _et_date(r.get("ts_utc")) != day:
            continue
        exits_today += 1
        code = ((r.get("outcome") or {}).get("exit_reason") or "").strip()
        if not code:
            untyped += 1
            code = "UNTYPED (row written before 2026-09-05)"
        by_reason[code] = by_reason.get(code, 0) + 1
        if entries.get(str(r.get("symbol"))) == day:
            same_session += 1
    if not exits_today:
        return {"status": "ok", "n_exits": 0,
                "reading": "no exits today -- with entries armed, that is a book holding."}
    return {
        "status": "ok",
        "n_exits": exits_today,
        "same_session_round_trips": same_session,
        "same_session_pct": round(100.0 * same_session / exits_today, 1),
        "by_reason": dict(sorted(by_reason.items(), key=lambda kv: -kv[1])),
        "untyped": untyped,
        "enum": list(_contract.EXIT_REASONS),
        "reading": ("HORIZON_SPENT / PROFIT_TARGET = the thesis finishing. HARD_RISK_LIMIT in "
                    "quantity = the stop is inside the noise. Anything closing before a book's "
                    "`min_normal_hold_sessions` should be a typed emergency and rare; if it is "
                    "not, the exit rule is the strategy."),
    }


def entry_authority_rows(roles: list[str]) -> dict:
    """Armed or disarmed, per role, and the BINDING constraint. Shared with
    `scripts/utilization.py` so the two pages cannot disagree about it."""
    from scripts.utilization import entry_authority

    out = {}
    for role in roles:
        try:
            out[role] = entry_authority(role)
        except Exception as exc:                                  # noqa: BLE001
            out[role] = {"role": role, "armed": None, "binding": f"CANNOT DETERMINE: {exc}"}
    return out


#: Where the finance repo's learner writes, relative to a repo root. One string,
#: so the search below and any documentation of it cannot drift apart.
_SHADOW_SUFFIX = ("backend", "data", "optimus", "learner")


def shadow_dir() -> Path:
    """Where the finance repo's `learner/shadow.py` writes its day files.

    ORDER, AND WHY IT IS A SEARCH AND NOT A GUESS (B3, 2026-09-05):

    1. `AEGIS_SHADOW_DIR`, when set. Explicit beats derived, always.
    2. the sibling checkout `../aegis-finance/backend/data/optimus/learner`.
    3. the same suffix under `../Aegis-Finance` -- Windows is case-insensitive
       but a mounted volume, a WSL path or a rename is not, and a benchmark
       section that reads "not present" because of a capital F is exactly the
       silent-plumbing failure this whole exercise is about.

    Returns the FIRST path that exists; if none does, the sibling default, so
    the caller can report the path it looked for by name.
    """
    env = os.getenv("AEGIS_SHADOW_DIR")
    if env:
        return Path(env)
    default = ROOT.parent.joinpath("aegis-finance", *_SHADOW_SUFFIX)
    for cand in (default, ROOT.parent.joinpath("Aegis-Finance", *_SHADOW_SUFFIX)):
        if cand.exists():
            return cand
    return default


def shadow_section(path: Path) -> dict:
    """One shadow book file, taken at its word. REFUSED is a finding: the
    shadow's whole design is that it refuses rather than median-imputes a
    third of its model's inputs, so its reasons are the payload.

    A MISSING FILE IS TWO DIFFERENT FACTS and this now separates them: a
    missing DIRECTORY is our path wiring (PLUMBING, and it names the env var);
    a present directory whose other day-files exist but not this one is the
    finance repo's nightly not having run for this day (NO_DATA_YET), and it
    names the newest day that IS there so a reader can see how far behind it is.
    """
    if not path.exists():
        parent = path.parent
        if not parent.exists():
            return _cannot(
                f"the shadow directory {parent} does not exist, so this section has no "
                f"input at all. Set AEGIS_SHADOW_DIR to the finance repo's "
                f"{'/'.join(_SHADOW_SUFFIX)}.",
                CAUSE_PLUMBING, path=str(path),
                fix="set AEGIS_SHADOW_DIR=<aegis-finance>/backend/data/optimus/learner")
        days = sorted(p.stem.replace("shadow_book_", "")
                      for p in parent.glob("shadow_book_*.json"))
        return {"status": "not present", "cause": CAUSE_NO_DATA, "path": str(path),
                "dir_exists": True, "n_day_files": len(days),
                "latest_day_present": days[-1] if days else None,
                "note": (f"the directory is there and holds {len(days)} shadow day-file(s)"
                         + (f" (newest {days[-1]})" if days else "")
                         + f", but none for this day. The finance repo's nightly did not "
                           f"write it; that repo owes the terminal nothing, and this is a "
                           f"correct refusal rather than a broken path.")}
    try:
        book = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"status": CANNOT, "path": str(path), "why": f"unreadable: {exc}"}
    out = {"status": book.get("status") or "ok", "path": str(path),
           "model": (book.get("model") or {}).get("kind"),
           "arm": (book.get("model") or {}).get("arm"),
           "k": (book.get("mandate") or {}).get("k")}
    if str(book.get("status")).upper() == "REFUSED":
        out["refusal_reasons"] = book.get("refusal_reasons") or book.get("reasons") or []
        out["note"] = "a refusal is a finding; a garbage book is not"
    else:
        picks = book.get("book") or book.get("holdings") or book.get("selected") or []
        out["symbols"] = [str(p.get("symbol")) for p in picks if isinstance(p, dict)][:15]
    return out


# ---------------------------------------------------------------------------
# (e) WATCHLIST EVENTS
# ---------------------------------------------------------------------------

def tracker_dir() -> Path:
    """Where the nightly tracker refresh writes `<day>.jsonl`.

    `AAT_TRACKER_DIR` overrides; otherwise `<ledger dir>/tracker`, and the
    ledger dir is `AAT_LEDGER_DIR` (the Railway volume) or `state/`. Wired as
    its own function -- and its own env var -- because the seal authority runs
    with a mounted volume where `state/` is NOT the tracker's home, and the
    watchlist section reporting an empty diff there would be a silent zero.
    """
    env = os.getenv("AAT_TRACKER_DIR")
    return Path(env) if env else (_state_dir() / "tracker")


def tracker_symbols(day: str) -> set[str] | None:
    path = tracker_dir() / f"{day}.jsonl"
    if not path.exists():
        return None
    syms: set[str] = set()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                syms.add(str(json.loads(line)["symbol"]))
            except (ValueError, KeyError):
                continue
    return syms


def tracker_days() -> list[str]:
    d = tracker_dir()
    return sorted(p.stem for p in d.glob("2*.jsonl")) if d.exists() else []


def prior_tracker_day(day: str) -> str | None:
    days = [x for x in tracker_days() if x < day]
    return days[-1] if days else None


def watchlist_events(day_syms: set[str] | None, prev_syms: set[str] | None,
                     day: str, prev_day: str | None) -> dict:
    if day_syms is None:
        d = tracker_dir()
        if not d.exists():
            return _cannot(
                f"the tracker directory {d} does not exist. Set AAT_TRACKER_DIR (or "
                f"AAT_LEDGER_DIR) to wherever the nightly refresh writes.",
                CAUSE_PLUMBING, tracker_dir=str(d),
                fix="python -m scripts.tracker --refresh")
        present = tracker_days()
        if not present:
            return _cannot(
                f"the tracker directory {d} exists and holds NO day files at all -- the "
                f"nightly refresh has never written here.",
                CAUSE_PLUMBING, tracker_dir=str(d),
                fix="python -m scripts.tracker --refresh")
        return _cannot(
            f"{d / (day + '.jsonl')} does not exist; the refresh's newest day is "
            f"{present[-1]}. The tracker did not run for {day}.",
            CAUSE_PLUMBING if present[-1] < day else CAUSE_NO_DATA,
            tracker_dir=str(d), latest_day_present=present[-1],
            fix="python -m scripts.tracker --refresh")
    if prev_day is None or prev_syms is None:
        return _cannot(f"no earlier tracker day file before {day} to diff against",
                       CAUSE_NO_DATA, n_watchlist=len(day_syms))
    entrants = sorted(day_syms - prev_syms)
    dropouts = sorted(prev_syms - day_syms)
    return {"status": "ok", "vs_day": prev_day, "n_watchlist": len(day_syms),
            "n_prev": len(prev_syms), "n_entrants": len(entrants),
            "n_dropouts": len(dropouts), "entrants": entrants[:25],
            "dropouts": dropouts[:25],
            "truncated": len(entrants) > 25 or len(dropouts) > 25}


# ---------------------------------------------------------------------------
# The receipt
# ---------------------------------------------------------------------------

def write_receipt(report: dict) -> Path:
    out_dir = _state_dir() / "learning_report"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{report['day']}.json"
    path.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Live assembly (everything above is pure and offline-testable)
# ---------------------------------------------------------------------------

def _load_decision_rows() -> list[dict]:
    """The decisions ledger, read as JSONL. The hash chain has been torn since
    25 Aug and is REPORTED, not repaired (see LEDGER_TEAR_FACT); a torn chain
    does not stop us counting exit reasons, it stops us claiming the count is
    tamper-evident, and that distinction is the whole point of saying so."""
    path = _state_dir() / "decisions.jsonl"
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


#: How much of the counterfactual ledger to read. It is APPEND-ONLY and on this
#: machine it is 1.07 GB; a page that reports one session does not need 1.07 GB
#: of history, and reading it all made the report take minutes and allocate the
#: whole file. 64 MB is thousands of marks -- comfortably more than any single
#: day -- and the first (probably truncated) line is discarded, which is why the
#: seek is not a correctness risk.
_CF_TAIL_BYTES = 64 * 1024 * 1024


def _load_counterfactual_rows() -> list[dict]:
    path = _state_dir() / "counterfactual.jsonl"
    rows: list[dict] = []
    if not path.exists():
        return rows
    size = path.stat().st_size
    with path.open("rb") as fh:
        if size > _CF_TAIL_BYTES:
            fh.seek(size - _CF_TAIL_BYTES)
            fh.readline()          # discard the partial line the seek landed in
        for raw in fh:
            try:
                rows.append(json.loads(raw.decode("utf-8", "replace")))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
    return rows


def marker_last_day(rows: list[dict]) -> str | None:
    """The newest ET day the counterfactual marker wrote. This is what turns
    "no rows for this day" from an unresolvable silence into either 'the job is
    dead' or 'nothing was refused'."""
    days = [d for d in (_et_date(r.get("ts_utc")) for r in rows) if d]
    return max(days) if days else None


def _genesis(role: str) -> dict | None:
    path = _state_dir() / f"genesis_{role}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _history_by_day(client) -> dict[str, float]:
    h = client.portfolio_history(period="1M", timeframe="1D")
    out: dict[str, float] = {}
    for ts, eq in zip(h.get("timestamp") or [], h.get("equity") or []):
        if eq is None:
            continue
        d = (datetime.fromtimestamp(int(ts), tz=timezone.utc) + ET_OFFSET).date().isoformat()
        out[d] = float(eq)
    return out


def build_report(day: str | None = None) -> dict:
    """Assemble the whole page. Venue failures per role are COLLECTED into the
    affected section as CANNOT DETERMINE; only 'no day derivable at all'
    refuses the run."""
    from alpha import config
    from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal

    config.load_env()
    notes: list[str] = []
    client0 = None
    for role in ROLES:
        try:
            client0 = AlpacaPaper(role)
            client0.account()
            break
        except Exception as exc:                                  # noqa: BLE001
            notes.append(f"{role}: broker unreachable for shared data: {str(exc)[:80]}")
            client0 = None

    if day is None:
        if client0 is None:
            raise SystemExit(
                "REFUSED: no --day given and no venue reachable to derive the most "
                "recent completed session from the exchange calendar. Pass --day "
                "YYYY-MM-DD explicitly.")
        now = datetime.now(timezone.utc)
        start = (now + ET_OFFSET - timedelta(days=10)).date().isoformat()
        end = (now + ET_OFFSET).date().isoformat()
        cal = client0.calendar(start=start, end=end)
        day = most_recent_completed_session(now, cal)
        if day is None:
            raise SystemExit("REFUSED: the venue calendar lists no completed session "
                             f"in {start}..{end}, which should be impossible; pass --day.")

    # -- SPY window (same convention as state/benchmark_regret_20260903.json)
    genesis_any = next((g for g in (_genesis(r) for r in ROLES) if g), None)
    kickoff = str(((genesis_any or {}).get("competition") or {}).get("kickoff_utc")
                  or "")[:10]
    spy: dict = _cannot("venue unreachable for SPY bars", CAUSE_PLUMBING)
    if client0 is not None and kickoff:
        try:
            bars_start = (datetime.fromisoformat(kickoff) - timedelta(days=10)).date().isoformat()
            # ONE SPY close source for the whole repo (alpha/spy.py), on the SIP
            # tape. `client.stock_bars` sent `config.stock_feed()`, which is not
            # necessarily the tape `move_decomposition` and `logic_brain` read.
            closes = _spy.daily_closes(client0, start=bars_start)
            spy = _spy.window(closes, genesis_day=kickoff, day=day)
            if spy.get("status") == CANNOT:
                spy["cause"] = CAUSE_NO_DATA
            spy["genesis_kickoff_date"] = kickoff
        except BrokerRefusal as exc:
            spy = _cannot(str(exc)[:120], CAUSE_PLUMBING)
    elif not kickoff:
        spy = _cannot("no genesis file names the kickoff date "
                      f"({_state_dir()}/genesis_<role>.json)", CAUSE_PLUMBING)

    # -- the sealed book, via utilization's reader (state/ then docs/seed/)
    from scripts.utilization import sealed_book
    payload = sealed_book(day)

    roles_out: dict[str, dict] = {}
    for role in ROLES:
        entry: dict = {}
        try:
            client = AlpacaPaper(role)
            hist = _history_by_day(client)
            # THE LIVE-EQUITY FALLBACK. Read once per role, used only when the
            # 1D history has no row for `day` AND the account's own session day
            # IS `day`. `_session_day` is the venue clock, not this machine's.
            live_eq, live_day = None, None
            try:
                acct = client.account()
                live_eq = float(acct.get("equity")) if acct.get("equity") is not None else None
                from alpha import exits as _exits
                live_day = str(_exits.session_day())
            except Exception as exc:                              # noqa: BLE001
                notes.append(f"{role}: live equity unavailable: {str(exc)[:60]}")
            entry["scoreboard"] = scoreboard_row(role, _genesis(role), hist, day, spy,
                                                 live_equity=live_eq, live_equity_day=live_day)
            orders = client.orders(status="all", limit=500)
            port = ((payload or {}).get("portfolios") or {}).get(role)
            entry["books_vs_fills"] = books_vs_fills(port, orders, day,
                                                     seal_exists=payload is not None)
        except Exception as exc:                                  # noqa: BLE001
            entry["scoreboard"] = dict(_cannot(f"venue: {str(exc)[:100]}", CAUSE_PLUMBING),
                                       role=role)
            entry["books_vs_fills"] = _cannot("venue unreachable", CAUSE_PLUMBING)
        roles_out[role] = entry

    p = prior_tracker_day(day)
    cf_rows = _load_counterfactual_rows()
    report = {
        "artefact": "DAILY_LEARNING_REPORT",
        "day": day,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "read_only": "GETs and file reads only; nothing submitted, sealed, or repaired",
        "notes": notes,
        "spy": spy,
        "seal_sha256": (payload or {}).get("content_sha256"),
        "roles": roles_out,
        "refusal_regret": refusal_day_summary(cf_rows, day,
                                              marker_last_day=marker_last_day(cf_rows)),
        "holding_discipline": holding_discipline(_load_decision_rows(), day),
        "entry_authority": entry_authority_rows(list(ROLES)),
        "shadow": shadow_section(shadow_dir() / f"shadow_book_{day}.json"),
        "watchlist": watchlist_events(tracker_symbols(day),
                                      tracker_symbols(p) if p else None, day, p),
    }
    # Assembled LAST: it reads every other section's `cause`.
    report["refusal_census"] = refusal_census(report)
    return report


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

def _fmt(v, spec=",.0f", dash="--"):
    return format(v, spec) if isinstance(v, (int, float)) else dash


def _refusal(sec: dict | None, label: str = CANNOT) -> str:
    """One refusal line that says WHOSE fault it is, and the command if we own it."""
    sec = sec or {}
    cause = sec.get("cause")
    tag = {CAUSE_PLUMBING: "OUR PLUMBING", CAUSE_NO_DATA: "no data yet"}.get(cause, "cause not stated")
    fix = f"   fix: {sec['fix']}" if sec.get("fix") else ""
    return f"{label} [{tag}]: {sec.get('why')}{fix}"


def refusal_census(report: dict) -> dict:
    """Every refusal on the page, split by cause. THE HEADLINE OF THIS BUILD:
    a reader must be able to see at a glance how many red lines are our own
    dead wiring and how many are the honest absence of data."""
    plumbing: list[str] = []
    honest: list[str] = []
    unstated: list[str] = []

    def take(name: str, sec) -> None:
        if not isinstance(sec, dict):
            return
        st = str(sec.get("status") or "")
        if st in ("ok", ""):
            return
        c = sec.get("cause")
        (plumbing if c == CAUSE_PLUMBING else honest if c == CAUSE_NO_DATA
         else unstated).append(name)

    for k in ("spy", "refusal_regret", "holding_discipline", "shadow", "watchlist"):
        take(k, report.get(k))
    for role, e in (report.get("roles") or {}).items():
        take(f"{role}.scoreboard", (e or {}).get("scoreboard"))
        take(f"{role}.books_vs_fills", (e or {}).get("books_vs_fills"))
    for role, ea in (report.get("entry_authority") or {}).items():
        if (ea or {}).get("armed") is None:
            plumbing.append(f"{role}.entry_authority")
    return {"plumbing": plumbing, "no_data_yet": honest, "cause_unstated": unstated,
            "reading": ("PLUMBING lines are OUR bugs and each names a command. "
                        "NO_DATA_YET lines are correct refusals and are meant to stay. "
                        "A line under cause_unstated is a section that has not been "
                        "taught the difference -- treat it as unfinished, not as green.")}


def render(report: dict) -> str:
    L: list[str] = []
    day, spy = report["day"], report["spy"]
    L.append(f"DAILY LEARNING REPORT  {day}   (generated {report['generated_utc']}Z, read-only)")
    cen = report.get("refusal_census") or {}
    if cen:
        L.append(f"REFUSALS: {len(cen.get('plumbing') or [])} OUR PLUMBING "
                 f"{sorted(cen.get('plumbing') or []) or ''} | "
                 f"{len(cen.get('no_data_yet') or [])} no data yet "
                 f"{sorted(cen.get('no_data_yet') or []) or ''}"
                 + (f" | {len(cen['cause_unstated'])} CAUSE NOT STATED "
                    f"{sorted(cen['cause_unstated'])}" if cen.get("cause_unstated") else ""))
    if spy.get("status") == "ok":
        L.append(f"SPY since genesis {spy.get('genesis_kickoff_date')}: "
                 f"{spy['start_close']} -> {spy['end_close']} = {spy['return_pct']:+.3f}%"
                 + (f"   day: {spy['day_return_pct']:+.3f}%"
                    if spy.get("day_return_pct") is not None else ""))
    else:
        L.append("SPY window: " + _refusal(spy))

    L.append("")
    L.append("(a) SCOREBOARD" + (f"   seal {str(report.get('seal_sha256'))[:12]}"
                                 if report.get("seal_sha256")
                                 else "   (no seal found for this day)"))
    L.append(f"    {'role':<7}{'equity':>11}{'day P&L':>10}{'vs genesis':>12}"
             f"{'':>2}{'regret pp':>10}")
    for role, e in report["roles"].items():
        s = e["scoreboard"]
        if s.get("status") != "ok":
            L.append(f"    {role:<7}" + _refusal(s))
            continue
        L.append(f"    {role:<7}{s['equity']:>11,.0f}{_fmt(s.get('day_pnl_usd'), '+,.0f'):>10}"
                 f"{_fmt(s.get('pnl_vs_genesis_usd'), '+,.0f'):>12}"
                 f"{'':>2}{_fmt(s.get('benchmark_regret_pp'), '+.2f'):>10}")

    L.append("")
    L.append("(b) BOOKS vs FILLS  (sealed intent vs the venue's account of the day)")
    for role, e in report["roles"].items():
        b = e["books_vs_fills"]
        if b.get("status") == CANNOT:
            L.append(f"    {role:<7}" + _refusal(b))
        elif b.get("status") == "no sealed portfolio":
            extra = ""
            if b.get("filled_buys") or b.get("filled_sells"):
                extra = f"; fills anyway: buys {b['filled_buys']} sells {b['filled_sells']}"
            tag = "NO SEAL FOR THE DAY" if b.get("cause") == CAUSE_PLUMBING else "not in the seal"
            L.append(f"    {role:<7}{tag}; {b['n_orders_day']} orders{extra}")
        else:
            L.append(f"    {role:<7}admitted {b.get('admitted')}  "
                     f"filled {len(b['sealed_filled'])}/{len(b['sealed_symbols'])}  "
                     f"expired {len(b['expired'])}  canceled {len(b['canceled'])}  "
                     f"stopped {len(b['stopped'])}")
            if b.get("sealed_unfilled"):
                L.append(f"    {'':<7}sealed but NOT filled: {', '.join(b['sealed_unfilled'])}")
            if b.get("stopped"):
                L.append(f"    {'':<7}stopped out: {', '.join(b['stopped'])}")
            if b.get("off_book_fills"):
                L.append(f"    {'':<7}fills OUTSIDE the seal: {', '.join(b['off_book_fills'])}")

    L.append("")
    rr = report["refusal_regret"]
    L.append("(c) REFUSAL REGRET  (this day's refused decisions, by guard)")
    if rr.get("status") != "ok":
        L.append("    " + _refusal(rr))
    else:
        L.append(f"    {rr['n_refused_decisions']} refused decisions -- "
                 f"{rr['n_graded']} graded, {rr['n_ungraded']} ungraded "
                 f"(an ungraded row is counted and priced at nothing)")
        L.append(f"    {'guard':<36}{'cls':<12}{'n':>4}{'grd':>4}"
                 f"{'saved $':>9}{'cost $':>9}  names")
        for key, b in rr["by_guard"].items():
            L.append(f"    {key[:35]:<36}{b['class']:<12}{b['n']:>4}{b['graded']:>4}"
                     f"{b['saved_usd']:>9,.0f}{b['cost_usd']:>9,.0f}  "
                     f"{', '.join(b['symbols'][:4])}")
    L.append(f"    {LEDGER_TEAR_FACT}")

    L.append("")
    hd = report.get("holding_discipline") or {}
    L.append("(c2) HOLDING DISCIPLINE  (did the books hold, and under which typed reason)")
    if hd.get("n_exits"):
        L.append(f"    {hd['n_exits']} exit(s); {hd['same_session_round_trips']} were opened the "
                 f"SAME SESSION ({hd['same_session_pct']:.0f}%)")
        for code, n in (hd.get("by_reason") or {}).items():
            L.append(f"      {code:<34}{n:>4}")
        if hd.get("untyped"):
            L.append(f"    {hd['untyped']} row(s) carry no typed reason (written before 2026-09-05)")
    else:
        L.append(f"    {hd.get('reading', 'no exits')}")

    L.append("")
    L.append("(c3) ENTRY AUTHORITY  (may each book OPEN a position, and what stops it)")
    for role, ea in (report.get("entry_authority") or {}).items():
        state = "ARMED" if ea.get("armed") else ("DISARMED" if ea.get("armed") is False else CANNOT)
        L.append(f"    {role:<7}{state:<10}{ea.get('binding') or 'nothing -- this book may enter'}")
    L.append("    two disarms are RAILWAY VARIABLES, invisible from here: "
             "`railway variables --service aat-loop-<role>`")

    L.append("")
    sh = report["shadow"]
    L.append("(d) SHADOW  (the finance repo's learner book for this day)")
    if sh["status"] == "not present":
        L.append(f"    not present at {sh['path']}")
        L.append(f"    [no data yet] {sh.get('note')}")
    elif str(sh["status"]).upper() == "REFUSED":
        L.append("    REFUSED -- a finding, not an outage. Reasons:")
        for r in sh.get("refusal_reasons") or ["(none recorded in the file)"]:
            L.append(f"      - {r}")
    elif sh["status"] == CANNOT:
        L.append("    " + _refusal(sh))
    else:
        L.append(f"    {sh.get('model')} / {sh.get('arm')}  k={sh.get('k')}  "
                 f"picks: {', '.join(sh.get('symbols') or [])}")

    L.append("")
    w = report["watchlist"]
    L.append("(e) WATCHLIST EVENTS  (tracker day file vs the prior one)")
    if w.get("status") != "ok":
        L.append("    " + _refusal(w)
                 + (f"  ({w['n_watchlist']} names on {day})" if w.get("n_watchlist") else ""))
    else:
        L.append(f"    {w['n_watchlist']} names ({w['n_prev']} on {w['vs_day']}): "
                 f"{w['n_entrants']} entrants, {w['n_dropouts']} dropouts"
                 + ("  [lists truncated to 25]" if w.get("truncated") else ""))
        if w["entrants"]:
            L.append(f"    in : {', '.join(w['entrants'])}")
        if w["dropouts"]:
            L.append(f"    out: {', '.join(w['dropouts'])}")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=None, help="session day YYYY-MM-DD "
                    "(default: most recent COMPLETED session per the venue calendar)")
    ap.add_argument("--json", action="store_true",
                    help="print the receipt instead of the page")
    args = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                         # noqa: BLE001
            pass

    report = build_report(args.day)
    receipt = write_receipt(report)
    if args.json:
        print(json.dumps(report, indent=1, default=str))
    else:
        print(render(report))
        print(f"\nreceipt: {receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
