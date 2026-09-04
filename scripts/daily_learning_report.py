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
* A SECTION DERIVES ITS INPUTS OR REFUSES. A day with no counterfactual rows
  prints CANNOT DETERMINE with the missing input NAMED, never a quiet zero --
  a permanent unexplained red line teaches readers to skim (monday_gate, 2026-08).
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
                  `status: REFUSED` is a FINDING and its reasons are printed;
                  a missing file is only reported, because that repo's nightly
                  job owes us nothing.
(e) WATCHLIST     tracker entrants and dropouts vs the prior tracker day.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpha.exits import ET_OFFSET

ROOT = Path(__file__).resolve().parent.parent
#: The six competition accounts, in fleet order (fleet_health's ROLES).
ROLES = ("hack1", "hack2", "hack3", "hack4", "hack5", "hack6")
CANNOT = "CANNOT DETERMINE"
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
    """SPY over the competition window, the benchmark_regret receipt's own
    convention: first daily bar on/after the genesis kickoff date, to the
    report day's close. Also the day's own return, for the day-P&L column.
    Daily bars are stamped 04:00Z, which IS the ET date -- read t[:10]."""
    seq = sorted((str(b.get("t") or "")[:10], b.get("c")) for b in bars
                 if b.get("c") is not None and str(b.get("t") or "")[:10])
    start = next(((d, c) for d, c in seq if d >= genesis_day), None)
    upto = [(d, c) for d, c in seq if d <= day]
    if not start or not upto:
        return {"status": CANNOT,
                "why": f"no SPY bar on/after {genesis_day} or on/before {day}"}
    end_d, end_c = upto[-1]
    if end_d != day:
        return {"status": CANNOT,
                "why": f"no SPY bar FOR {day} (latest at/under it is {end_d}) -- "
                       f"was {day} a session?"}
    prev = upto[-2] if len(upto) >= 2 else None
    out = {"status": "ok", "start_date": start[0], "start_close": start[1],
           "end_date": end_d, "end_close": end_c,
           "return_pct": round((end_c / start[1] - 1) * 100, 3)}
    if prev:
        out["prev_date"], out["prev_close"] = prev
        out["day_return_pct"] = round((end_c / prev[1] - 1) * 100, 3)
    return out


def scoreboard_row(role: str, genesis: dict | None, history: dict[str, float],
                   day: str, spy: dict) -> dict:
    """One role's line. Every number that cannot be derived says so by NAME --
    a dash in a scoreboard is a number someone will assume."""
    row: dict = {"role": role}
    eq = history.get(day)
    if eq is None:
        row["status"] = CANNOT
        row["why"] = (f"portfolio history has no equity for {day} "
                      f"(days present: {sorted(history)[-3:] if history else 'none'})")
        return row
    row["status"] = "ok"
    row["equity"] = round(eq, 2)
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


def books_vs_fills(portfolio: dict | None, orders: list[dict], day: str) -> dict:
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
        out["why"] = ("this role has no block in the day's seal -- normal for "
                      "non-tracker books; its fills above are still the day's fact")
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

def refusal_day_summary(rows: list[dict], day: str) -> dict:
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
        return {"status": CANNOT,
                "why": (f"no refused counterfactual rows dated {day} (ET) in "
                        f"state/counterfactual.jsonl -- either nothing was refused, the "
                        f"marker did not run, or the day is older than the ledger; this "
                        f"section cannot tell those apart and will not pretend to")}

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


def shadow_dir() -> Path:
    """Where the finance repo's `learner/shadow.py` writes its day files.
    Its own OUT_DIR is `<finance repo>/backend/data/optimus/learner`; the two
    repos are siblings on this machine, and AEGIS_SHADOW_DIR overrides for any
    machine where they are not."""
    env = os.getenv("AEGIS_SHADOW_DIR")
    if env:
        return Path(env)
    return ROOT.parent / "aegis-finance" / "backend" / "data" / "optimus" / "learner"


def shadow_section(path: Path) -> dict:
    """One shadow book file, taken at its word. REFUSED is a finding: the
    shadow's whole design is that it refuses rather than median-imputes a
    third of its model's inputs, so its reasons are the payload."""
    if not path.exists():
        return {"status": "not present",
                "path": str(path),
                "note": ("the finance repo's nightly shadow did not write this day "
                         "(or writes elsewhere -- set AEGIS_SHADOW_DIR). Not an error "
                         "in THIS repo; the shadow owes the terminal nothing.")}
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

def tracker_symbols(day: str) -> set[str] | None:
    path = _state_dir() / "tracker" / f"{day}.jsonl"
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


def prior_tracker_day(day: str) -> str | None:
    days = sorted(p.stem for p in (_state_dir() / "tracker").glob("2*.jsonl")
                  if p.stem < day)
    return days[-1] if days else None


def watchlist_events(day_syms: set[str] | None, prev_syms: set[str] | None,
                     day: str, prev_day: str | None) -> dict:
    if day_syms is None:
        return {"status": CANNOT, "why": f"state/tracker/{day}.jsonl does not exist"}
    if prev_day is None or prev_syms is None:
        return {"status": CANNOT, "n_watchlist": len(day_syms),
                "why": f"no earlier tracker day file before {day} to diff against"}
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


def _load_counterfactual_rows() -> list[dict]:
    path = _state_dir() / "counterfactual.jsonl"
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
    spy: dict = {"status": CANNOT, "why": "venue unreachable for SPY bars"}
    if client0 is not None and kickoff:
        try:
            bars_start = (datetime.fromisoformat(kickoff) - timedelta(days=10)).date().isoformat()
            raw = client0.stock_bars("SPY", start=bars_start)
            spy = spy_window((raw.get("bars") or {}).get("SPY") or [], kickoff, day)
            spy["genesis_kickoff_date"] = kickoff
        except BrokerRefusal as exc:
            spy = {"status": CANNOT, "why": str(exc)[:120]}
    elif not kickoff:
        spy = {"status": CANNOT, "why": "no genesis file names the kickoff date"}

    # -- the sealed book, via utilization's reader (state/ then docs/seed/)
    from scripts.utilization import sealed_book
    payload = sealed_book(day)

    roles_out: dict[str, dict] = {}
    for role in ROLES:
        entry: dict = {}
        try:
            client = AlpacaPaper(role)
            hist = _history_by_day(client)
            entry["scoreboard"] = scoreboard_row(role, _genesis(role), hist, day, spy)
            orders = client.orders(status="all", limit=500)
            port = ((payload or {}).get("portfolios") or {}).get(role)
            entry["books_vs_fills"] = books_vs_fills(port, orders, day)
        except Exception as exc:                                  # noqa: BLE001
            entry["scoreboard"] = {"role": role, "status": CANNOT,
                                   "why": f"venue: {str(exc)[:100]}"}
            entry["books_vs_fills"] = {"status": CANNOT, "why": "venue unreachable"}
        roles_out[role] = entry

    p = prior_tracker_day(day)
    report = {
        "artefact": "DAILY_LEARNING_REPORT",
        "day": day,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "read_only": "GETs and file reads only; nothing submitted, sealed, or repaired",
        "notes": notes,
        "spy": spy,
        "seal_sha256": (payload or {}).get("content_sha256"),
        "roles": roles_out,
        "refusal_regret": refusal_day_summary(_load_counterfactual_rows(), day),
        "holding_discipline": holding_discipline(_load_decision_rows(), day),
        "entry_authority": entry_authority_rows(list(ROLES)),
        "shadow": shadow_section(shadow_dir() / f"shadow_book_{day}.json"),
        "watchlist": watchlist_events(tracker_symbols(day),
                                      tracker_symbols(p) if p else None, day, p),
    }
    return report


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

def _fmt(v, spec=",.0f", dash="--"):
    return format(v, spec) if isinstance(v, (int, float)) else dash


def render(report: dict) -> str:
    L: list[str] = []
    day, spy = report["day"], report["spy"]
    L.append(f"DAILY LEARNING REPORT  {day}   (generated {report['generated_utc']}Z, read-only)")
    if spy.get("status") == "ok":
        L.append(f"SPY since genesis {spy.get('genesis_kickoff_date')}: "
                 f"{spy['start_close']} -> {spy['end_close']} = {spy['return_pct']:+.3f}%"
                 + (f"   day: {spy['day_return_pct']:+.3f}%"
                    if spy.get("day_return_pct") is not None else ""))
    else:
        L.append(f"SPY window: {CANNOT} -- {spy.get('why')}")

    L.append("")
    L.append("(a) SCOREBOARD" + (f"   seal {str(report.get('seal_sha256'))[:12]}"
                                 if report.get("seal_sha256")
                                 else "   (no seal found for this day)"))
    L.append(f"    {'role':<7}{'equity':>11}{'day P&L':>10}{'vs genesis':>12}"
             f"{'':>2}{'regret pp':>10}")
    for role, e in report["roles"].items():
        s = e["scoreboard"]
        if s.get("status") != "ok":
            L.append(f"    {role:<7}{CANNOT}: {s.get('why')}")
            continue
        L.append(f"    {role:<7}{s['equity']:>11,.0f}{_fmt(s.get('day_pnl_usd'), '+,.0f'):>10}"
                 f"{_fmt(s.get('pnl_vs_genesis_usd'), '+,.0f'):>12}"
                 f"{'':>2}{_fmt(s.get('benchmark_regret_pp'), '+.2f'):>10}")

    L.append("")
    L.append("(b) BOOKS vs FILLS  (sealed intent vs the venue's account of the day)")
    for role, e in report["roles"].items():
        b = e["books_vs_fills"]
        if b.get("status") == CANNOT:
            L.append(f"    {role:<7}{CANNOT}: {b.get('why')}")
        elif b.get("status") == "no sealed portfolio":
            extra = ""
            if b.get("filled_buys") or b.get("filled_sells"):
                extra = f"; fills anyway: buys {b['filled_buys']} sells {b['filled_sells']}"
            L.append(f"    {role:<7}no sealed book (normal for non-tracker roles); "
                     f"{b['n_orders_day']} orders{extra}")
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
        L.append(f"    {CANNOT}: {rr.get('why')}")
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
    elif str(sh["status"]).upper() == "REFUSED":
        L.append("    REFUSED -- a finding, not an outage. Reasons:")
        for r in sh.get("refusal_reasons") or ["(none recorded in the file)"]:
            L.append(f"      - {r}")
    elif sh["status"] == CANNOT:
        L.append(f"    {CANNOT}: {sh.get('why')}")
    else:
        L.append(f"    {sh.get('model')} / {sh.get('arm')}  k={sh.get('k')}  "
                 f"picks: {', '.join(sh.get('symbols') or [])}")

    L.append("")
    w = report["watchlist"]
    L.append("(e) WATCHLIST EVENTS  (tracker day file vs the prior one)")
    if w.get("status") != "ok":
        L.append(f"    {CANNOT}: {w.get('why')}"
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
