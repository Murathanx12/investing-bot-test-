"""BOOK F -- the calendar-seasonality ranking, read from a frozen engine file.

WHAT THIS BRAIN IS, AND WHAT IT REFUSES TO BE
=============================================
Book F ranks names by their own return in the SAME CALENDAR MONTH at year lags
of 11-15 and 16-20 (Heston-Sadka's structure, mechanically disjoint from the
12-1 momentum window every other book in this fleet prices). Computing that
ranking needs twenty years of CRSP tape and a cross-section of a thousand
names. **None of that happens here.** The research repo
(`aegis-finance/scripts/night_f_seasonality_export.py`) writes one frozen JSON
per calendar month; this brain installs it, verifies it against its own
`content_sha256`, and trades the list -- or declines, loudly, with the reason.

That is the `scripts/seal_authority.py` pattern applied to a second artefact,
and the reason is the same one `tracker_portfolio` gives: if this module could
re-derive the ranking it could drift from the file that was inspected, and then
the hash guarantees nothing.

THE FOUR REFUSALS
=================
1. **no engine file for THIS calendar month** -- a September ranking is not an
   October book, and a missed monthly redeploy must stop the book rather than
   trade last month's names. Fail CLOSED, like every other book here;
2. **hash mismatch** -- checked in the ORDER path, not only in a script
   (2026-09-07, lab C1-5: the seal was verified everywhere except where the
   orders were placed);
3. **the symbol is not in this month's top-k prefix** -- the brain does not
   re-rank at decision time, and a name that is 31st does not trade because it
   looks good now;
4. **fewer than 30 bars** -- the forecast's spread is the name's own realised
   volatility, and a spread that cannot be measured is not invented.

THE CENTRE, AND WHY EVERY SELECTED NAME GETS THE SAME ONE
=========================================================
The book's registered claim is that the TOP TERCILE pays, not that rank 1 pays
more than rank 10: the replay holds its k names equal-weighted. So the centre is
the book's own measured monthly excess over its turnover-matched twin at the
$10M floor -- **+0.4328%/month, t 3.1178, 419 blocks** -- scaled to the horizon
as a drift, and it is identical across the selected names by construction. A
centre that leaned on the score would be a claim this book has never measured.

`claim="direction"`: the ranking says which way, not how wide, and
`runner.effective_sd` integrates a direction claim against the CHAIN's width.

WHICH NAMES, AND HOW MANY
=========================
`AAT_ACCOUNT_ROLE` picks the book, exactly as `tracker_portfolio` does, and the
count comes from that role's OWN frozen sizing (`contract.BOOK_SIZING[role]["n"]`
-- hack3: 10). The engine file ranks and cuts at the registered k=30; the live
book holds a PREFIX of that ranking. The prefix is a documented deviation from
the receipt and it is printed on every forecast's evidence, because a reader
comparing a k=10 live book against a k=30 receipt would otherwise call the
difference alpha.

LICENCE: `PRODUCT_EXPERIMENT`. F is CONDITIONAL, not a claim -- its falsifiers
passed and its primary did not clear the declared effect size. It is deployed to
learn what it does on real fills, not because it is established.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpha import config, exits as _exits
from alpha.brains.base import Forecast

ROOT = Path(__file__).resolve().parent.parent.parent

BRAIN = "seasonality_f"
ENGINE = "seasonality_11_20_v0"
REGISTRATION = "TRIAL-DRAFT-F-calendar-seasonality-v0 (UNSIGNED)"

#: Same two locations and the same order as `tracker_portfolio.BOOKS`, and for
#: the same reason: on Railway `AAT_LEDGER_DIR=/app/state` is a mounted VOLUME
#: that SHADOWS whatever the image ships at that path, so an engine file
#: committed under `state/` is invisible to the loop. `docs/seed/` is not
#: shadowed and is the delivery path.
#:
#: ONE TRAP, WRITTEN DOWN RATHER THAN DISCOVERED: the Dockerfile seeds the
#: volume with `cp -rn /app/seed/. /app/state/`, and `-n` NEVER OVERWRITES. A
#: NEW month's file is a new name and arrives normally; a CORRECTED file for a
#: month already seeded does not, and the volume's stale copy keeps winning
#: because it is checked first. Re-exporting the same month therefore needs the
#: volume copy removed (or the file installed there directly) -- it is not a
#: redeploy away. Said here because the failure is silent: the stale file
#: verifies against its own hash perfectly.
ENGINES = Path(os.getenv("AAT_LEDGER_DIR") or (ROOT / "state")) / "engines"
SEED_ENGINES = ROOT / "docs" / "seed" / "engines"

#: The replay cell this book is the live expression of
#: (`aegis-finance/backend/data/optimus/night_factory_2026-09-13/
#: B_books_efg_replay_run01.json`, secondary $10M floor). Quoted here so a
#: reader of the forecast's evidence does not have to open another repository
#: to learn what the centre is.
RECEIPT = {
    "receipt": "night_factory_2026-09-13/B_books_efg_replay_run01.json",
    "floor_usd": 10_000_000.0,
    "mean_excess_net_monthly": 0.004328,
    "nw_lag2_t": 3.1178,
    "n_blocks": 419,
    "era_2017_2024": {"mean_excess_net_monthly": 0.007637, "nw_lag2_t": 2.2972},
    "cost_curve": "flat_25bps_pending_5c",
    "verdict": "CONDITIONAL",
}

#: The measured monthly excess over the twin, used as the forecast's centre.
MONTHLY_EXCESS = RECEIPT["mean_excess_net_monthly"]

#: Sessions in the month the excess above was earned over. The centre is a
#: DRIFT, so it scales linearly in t and is capped at one month: the book
#: rebalances monthly and re-earns the claim, it does not compound it inside one
#: forecast.
BOOK_HORIZON_SESSIONS = 21
SESSIONS_PER_CALENDAR_DAY = 5.0 / 7.0

#: A tercile book's own confidence in one of its names. Constant, and constant
#: ON PURPOSE: see the module docstring.
CONVICTION = 0.5

MIN_BARS = 30
VOL_WINDOW = 60


class EngineDeclined(Exception):
    """This brain has nothing to say today, and says exactly why."""


def _sha_of(payload: dict) -> str:
    """The engine file's content hash, over the payload WITHOUT `content_sha256`.

    Byte-identical to `scripts.prediction_book._sha` and to
    `night_f_seasonality_export.content_sha256` in the research repo, and
    deliberately RE-WRITTEN here rather than imported, for the same reason
    `tracker_portfolio._sha_of` is: a brain that imports a script inherits that
    script's argparse and module-level paths inside the order path, and the two
    repositories share no code at all. `tests_smoke_engine_seasonality` pins this
    copy against a file the exporter wrote, so the three cannot drift in silence.
    """
    body = dict(payload)
    body.pop("content_sha256", None)
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":")).encode("utf-8")).hexdigest()


def role() -> str | None:
    r = (os.getenv("AAT_ACCOUNT_ROLE") or "").strip().lower()
    return r or None


def month_for(day: str | None = None) -> str:
    """The calendar month this book trades, from the ET TRADING day."""
    return (day or _exits.session_day())[:7]


def _engine_path(month: str) -> Path | None:
    for base in (ENGINES, SEED_ENGINES):
        p = base / f"F_seasonality_{month}.json"
        if p.is_file():
            return p
    return None


def engine(day: str | None = None, *, month: str | None = None) -> dict:
    """This month's verified ranking. Raises `EngineDeclined` with the reason.

    Every check here is a fail-closed one. An engine file that is absent, is for
    another month, fails its own hash or names another selector is DECLINED --
    never substituted, never partially trusted.
    """
    m = month or month_for(day)
    path = _engine_path(m)
    if path is None:
        raise EngineDeclined(
            f"no seasonality engine file for {m} under {ENGINES} or {SEED_ENGINES}. "
            f"Book F trades a ranking computed in the research repo "
            f"(`python -m scripts.night_f_seasonality_export`) and installed here; "
            f"it does not re-derive a twenty-year seasonality average at the open. "
            f"A missed monthly install stops this book, which is the designed "
            f"failure -- trading last month's names would be worse.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EngineDeclined(f"unreadable engine file {path.name}: {exc}") from exc
    claimed, actual = payload.get("content_sha256"), _sha_of(payload)
    if not claimed or claimed != actual:
        raise EngineDeclined(
            f"{path.name} does not match its own content_sha256 (claimed "
            f"{str(claimed)[:16]!r}, recomputed {actual[:16]!r}). The file's only "
            f"guarantee is that these are the names that were inspected; a file "
            f"that fails its own hash carries no such guarantee, so it is "
            f"DECLINED rather than traded.")
    if payload.get("month") != m:
        raise EngineDeclined(
            f"{path.name} declares month {payload.get('month')!r} inside its own "
            f"hashed content, not {m}. Refusing rather than trading another "
            f"month's seasonality.")
    if payload.get("engine") != ENGINE:
        raise EngineDeclined(
            f"{path.name} declares engine {payload.get('engine')!r}, not {ENGINE!r}. "
            f"Refusing rather than trading a ranking this brain did not ask for.")
    if not payload.get("selected"):
        raise EngineDeclined(
            f"{path.name} selected no names for {m}. An empty selection is a "
            f"refusal of the export's own coverage rule, not a decision to hold "
            f"nothing.")
    return payload


def book_k(r: str | None = None) -> int:
    """How many of the ranking THIS role holds, from its own frozen sizing.

    Read from `contract.BOOK_SIZING` rather than declared here, so the count the
    brain admits and the count `contract.worst_case` prices cannot disagree.
    """
    from alpha import contract

    b = (r or role() or "")
    sz = contract.BOOK_SIZING.get(b)
    if not sz:
        raise EngineDeclined(
            f"role {b!r} has no frozen sizing in contract.BOOK_SIZING "
            f"({sorted(contract.BOOK_SIZING)}), so there is no declared name count "
            f"for it. Refusing rather than defaulting -- a default here would size "
            f"one mandate's breadth onto another mandate's account.")
    return int(sz["n"])


def selection(day: str | None = None, *, month: str | None = None,
              r: str | None = None) -> dict:
    """{symbol: rank} for this role's prefix of the month's ranking, plus provenance.

    Exposed separately from `forecast` so a pre-open check can print exactly what
    will trade and compare it against the hash without going near a broker
    client -- "I inspected the artefact the runner consumes" has to be a command
    anyone can run, or it is not a proof.
    """
    payload = engine(day, month=month)
    b = r or role()
    if b is None:
        raise EngineDeclined(
            "AAT_ACCOUNT_ROLE is unset, so there is no way to know how many of "
            "the ranking this account holds. Refusing rather than defaulting.")
    k = book_k(b)
    names = list(payload["selected"])[:k]
    return {
        "book": b,
        "engine": payload.get("engine"),
        "registration": payload.get("registration"),
        "licence": payload.get("licence"),
        "month": payload.get("month"),
        "content_sha256": payload.get("content_sha256"),
        "as_of": payload.get("as_of"),
        "engine_k": (payload.get("construction") or {}).get("k"),
        "book_k": k,
        "construction": payload.get("construction"),
        "coverage": payload.get("coverage"),
        "ranks": {s: i + 1 for i, s in enumerate(names)},
        "engine_selected": list(payload["selected"]),
    }


def universe_symbols(day: str | None = None, *, month: str | None = None) -> list[str]:
    """The symbols the LOOP should be asked about: the engine's own selection.

    The engine's k=30 list, not this role's k=10 prefix, so the shape of what the
    loop considered is visible in the receipt even though only the prefix trades.
    """
    return list(engine(day, month=month)["selected"])


def _bars(client, symbol: str, days: int = 130) -> list[dict]:
    start = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    d = client._request("GET", f"/v2/stocks/{symbol}/bars", base=config.data_url(),
                        params={"timeframe": "1Day", "start": start, "limit": 200,
                                "feed": config.stock_feed(), "adjustment": "all"})
    return (d or {}).get("bars") or []


def forecast(client, symbol: str, horizon_days: float, *, day: str | None = None,
             bars: list[dict] | None = None) -> Forecast:
    sym = str(symbol).upper()
    sel = selection(day)
    rank = sel["ranks"].get(sym)
    if rank is None:
        raise EngineDeclined(
            f"{sym} is not in {sel['book']}'s {sel['month']} seasonality book "
            f"(top {sel['book_k']} of {len(sel['engine_selected'])}: "
            f"{', '.join(sorted(sel['ranks'])) or 'none'}). This brain does not "
            f"re-rank at decision time -- a name outside the month's prefix does "
            f"not trade, however good it looks now.")

    bars = bars if bars is not None else _bars(client, sym)
    closes = [float(b["c"]) for b in bars]
    if len(closes) < MIN_BARS:
        raise EngineDeclined(
            f"{sym}: {len(closes)} bars < {MIN_BARS}. The spread on this forecast "
            f"is the name's own realised volatility and an unmeasurable spread is "
            f"not invented -- a point forecast with no stated uncertainty sizes "
            f"itself to the ceiling.")
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    sd_daily = statistics.pstdev(rets[-VOL_WINDOW:])
    if sd_daily <= 0:
        raise EngineDeclined(f"{sym}: zero realised volatility over the last "
                             f"{VOL_WINDOW} sessions")

    sessions = max(1.0, float(horizon_days) * SESSIONS_PER_CALENDAR_DAY)
    t = min(1.0, sessions / BOOK_HORIZON_SESSIONS)
    centre = MONTHLY_EXCESS * t
    sd = sd_daily * math.sqrt(max(float(horizon_days), 1.0))

    return Forecast(
        brain=BRAIN, symbol=sym, horizon_days=float(horizon_days),
        centre=centre, sd=sd, conviction=CONVICTION,
        claim="direction", signal_shape=None,
        rationale=(f"{sel['book']} seasonality book {sel['month']} "
                   f"({ENGINE}): {sym} rank {rank}/{sel['book_k']} of the engine's "
                   f"{len(sel['engine_selected'])}; centre is the book's measured "
                   f"+{MONTHLY_EXCESS:.4%}/month over its twin at the $10M floor "
                   f"(t {RECEIPT['nw_lag2_t']}, {RECEIPT['n_blocks']} blocks), "
                   f"scaled x{t:.3f}"),
        evidence={
            "book": sel["book"],
            "engine": ENGINE,
            "engine_month": sel["month"],
            "engine_sha256": sel["content_sha256"],
            "engine_as_of": sel["as_of"],
            "registration": sel["registration"],
            "licence": sel["licence"] or "PRODUCT_EXPERIMENT",
            "rank": rank,
            "book_k": sel["book_k"],
            "engine_k": sel["engine_k"],
            "k_is_a_prefix_of_the_registered_ranking": (
                f"the receipt measured k={sel['engine_k']}; this mandate holds "
                f"k={sel['book_k']}, the first {sel['book_k']} of the same "
                f"ranking. A k=10 live book compared against a k=30 receipt "
                f"differs by construction, not by alpha."),
            "receipt": RECEIPT,
            "measured_edge_monthly_vs_twin": MONTHLY_EXCESS,
            "centre_is_the_same_for_every_selected_name": (
                "the registered claim is that the TOP TERCILE pays and the "
                "replay holds its names equal-weighted; a centre that leaned on "
                "the score would be a claim this book has never measured"),
            "sd_daily": sd_daily,
            "sd_source": f"realised volatility, last {VOL_WINDOW} sessions",
            "horizon_scaling": f"centre x {t:.3f} (drift, capped at one month), sd x sqrt(horizon)",
            "coverage": sel["coverage"],
            "no_reranking": ("this brain reads the installed engine file only and "
                             "computes no seasonality; a research re-export after "
                             "the install cannot change today"),
        },
    )
