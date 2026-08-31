"""COMPANYSTATE -- one append-only row per company per day. The dataset AEGIS owns.

WHY THIS IS THE ITEM THAT COMPOUNDS
===================================
Everything else in the roadmap is worth the same tomorrow as today. This is
worth more every night it runs and cannot be backfilled: a missing COLUMN can
be recovered from the tracker's own history, a missing DAY cannot. A year over
~3,000 names is roughly 750,000 labelled state transitions with what happened
next -- the training table for every model in the promotion order, and the only
one no vendor can sell us because it is a record of OUR decisions and OUR
inputs at the moment we had them.

So it starts imperfect and starts NOW.

ONE COMPANY DOES NOT HAVE ONE TRUTH
===================================
Murat: a name can be *avoid at 1 week*, *buy at 3 months* and *strong buy at 1
year* simultaneously. A single BUY/HOLD/SELL column cannot hold that and forces
the engine to pick a clock it was never asked about. So status is recorded PER
HORIZON, and a horizon with no basis is `None` WITH A REASON rather than a
default.

WHAT IS DERIVED HERE AND WHAT IS ONLY CARRIED
=============================================
Derived (cheap, deterministic, from measured studies):

  * `band` / `band_name`      the dollar-volume ladder from the TAQ spread study
  * `expected_round_trip_bps` that band's MEASURED cost -- so a downstream model
                              can price a name instead of assuming a flat fee.
                              `FINDING_2026-08-31_SPREAD_BY_LIQUIDITY_BAND`
  * `analyst_disagreement`    (target_high - target_low) / close. A wide range on
                              a thin name is one analyst who knows something and
                              one who does not; a point estimate hides that.
  * `upside_downside_ratio`   the hack6 ranking, kept as a column so the book's
                              choice is auditable against the state that produced it.

Carried verbatim, never recomputed: everything the tracker, the news baseline
and EDGAR already measured. A column recomputed in two places drifts in one.

NOTHING HERE FORECASTS OR TRADES. It records what was knowable at the close of
`day`, so that a model trained later sees the world as it was and not as it was
revised. Every row carries `observed_at` from the tracker and `written_at` from
this module; those are different clocks and conflating them is how a backtest
learns tomorrow's news.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "company-state-1"
STORE = Path("state") / "company_state"

#: The ladder, and its MEASURED round-trip cost in bps. Identical cuts to
#: `scripts/liquidity_migration.py` and `scripts/taq_spread_by_liquidity_band.py`
#: so a band means one thing across the programme.
BAND_EDGES = (1e5, 1e6, 5e6, 1e7, 5e7)
BAND_NAMES = ("<100k", "100k-1m", "1m-5m", "5m-10m", "10m-50m", "50m+")
BAND_ROUND_TRIP_BPS = {"<100k": None,        # never measured; not assumed
                       "100k-1m": 148.9, "1m-5m": 38.7, "5m-10m": 21.0,
                       "10m-50m": 20.2, "50m+": 6.7}

#: The horizons a status may be stated for. Several clocks, never one.
HORIZONS = ("1w", "1m", "3m", "6m", "12m")


def band_of(mdv: float | None) -> tuple[int | None, str | None]:
    """(index, name) on the dollar-volume ladder. (None, None) when unreadable.

    An unreadable volume is NOT band 0. Band 0 is a measurement that the name
    trades under $100k/day; absence is absence.
    """
    if mdv is None:
        return None, None
    try:
        v = float(mdv)
    except (TypeError, ValueError):
        return None, None
    b = 0
    for e in BAND_EDGES:
        if v >= e:
            b += 1
    b = min(b, len(BAND_NAMES) - 1)
    return b, BAND_NAMES[b]


def analyst_disagreement(target_high, target_low, close) -> float | None:
    """(high - low) / close. The SPREAD of opinion, not its centre.

    Murat's hypothesis: on a thinly covered name a wide target range is one
    analyst who knows something against one who does not, and that conditions
    the upside edge. Recorded so it can be tested, not acted on.
    """
    try:
        hi, lo, px = float(target_high), float(target_low), float(close)
    except (TypeError, ValueError):
        return None
    if px <= 0 or hi <= 0 or lo <= 0 or hi < lo:
        return None
    return round((hi - lo) / px, 6)


def _ratio(num, den) -> float | None:
    try:
        n, d = float(num), abs(float(den))
    except (TypeError, ValueError):
        return None
    return None if d < 1e-9 else round(n / d, 6)


def build_row(*, day: str, tracker_row: dict, prior_band: int | None = None,
              attention: dict | None = None, filings: dict | None = None,
              book_row: dict | None = None) -> dict:
    """One company's state on one day. Pure: no IO, no clock beyond `written_at`.

    Every optional input is genuinely optional and its absence is recorded as
    absence -- `attention_z: None` with `attention_basis` saying why -- because
    a zero here would later train a model that the name had no news.
    """
    t = tracker_row
    sym = str(t.get("symbol", "")).upper()
    mdv = t.get("median_dollar_volume")
    band, band_name = band_of(mdv)
    att = attention or {}
    fil = filings or {}
    bk = book_row or {}

    row = {
        "schema": SCHEMA,
        "symbol": sym,
        "day": day,
        # TWO CLOCKS, kept apart. `observed_at` is when the market fact was
        # captured; `written_at` is when this row was assembled. A model that
        # conflates them can learn from data that did not exist yet.
        "observed_at": t.get("observed_at"),
        "written_at": datetime.now(timezone.utc).isoformat(),

        # -- identity ------------------------------------------------------
        "sector": t.get("sector"),
        "exchange": t.get("exchange"),
        "market_cap_usd": t.get("market_cap_usd"),
        "tradable": t.get("tradable"),
        "shortable": t.get("shortable"),

        # -- liquidity, and what it COSTS to touch -------------------------
        "median_dollar_volume": mdv,
        "dv_bucket": t.get("dv_bucket"),
        "band": band,
        "band_name": band_name,
        "band_change_12m": (None if band is None or prior_band is None
                            else band - prior_band),
        "expected_round_trip_bps": BAND_ROUND_TRIP_BPS.get(band_name),

        # -- coverage: how much is KNOWN, kept apart from how good it looks --
        "coverage": t.get("coverage"),
        "coverage_bucket": t.get("coverage_bucket"),
        "coverage_source": t.get("coverage_source"),

        # -- the street's numbers ------------------------------------------
        "close": t.get("close"),
        "mean_target": t.get("mean_target"),
        "target_high": t.get("target_high"),
        "target_low": t.get("target_low"),
        "upside": t.get("upside"),
        "analyst_disagreement": analyst_disagreement(
            t.get("target_high"), t.get("target_low"), t.get("close")),
        "consensus": t.get("consensus"),
        "rec_counts": t.get("rec_counts"),

        # -- price path ----------------------------------------------------
        "ret_12m": t.get("ret_12m"),
        "drawdown_60d": t.get("drawdown_60d"),
        "realised_vol_20d": t.get("realised_vol_20d"),
        "past_winner": t.get("past_winner"),
        "days_to_catalyst": t.get("days_to_catalyst"),

        # -- attention. ABSENCE IS ABSENCE ---------------------------------
        "news_articles": att.get("n_articles"),
        "news_sources": att.get("n_sources"),
        "attention_z": att.get("attention_z"),
        "attention_is_new": att.get("is_new"),
        "attention_basis": att.get("basis") or "no news row for this name today",

        # -- filings: the source with no fame bias -------------------------
        "edgar_filings_6m": fil.get("total"),
        "edgar_by_form": fil.get("by_form"),

        # -- what the rule/brain said, carried not recomputed ---------------
        "p_up_21d": bk.get("p_up_21d"),
        "exp_return": bk.get("exp_return"),
        "downside_5pct": bk.get("downside_5pct"),
        "confidence": bk.get("confidence"),
        "numbers_source": bk.get("numbers_source"),
        "upside_downside_ratio": _ratio(t.get("upside"), bk.get("downside_5pct")),

        # -- status, PER HORIZON -------------------------------------------
        # The tracker's status is a 21-session judgement and is recorded as
        # such. The other horizons are None WITH A REASON: no generator states
        # them yet, and a copied value would look like five agreeing opinions.
        "status_by_horizon": {h: (t.get("status") if h == "1m" else None)
                              for h in HORIZONS},
        "status_basis": {h: ("tracker 21-session rule" if h == "1m"
                             else "no generator states this horizon yet")
                         for h in HORIZONS},
        "status_blocked_by": t.get("status_blocked_by"),
    }
    return row


def write_day(rows: list[dict], day: str, store: Path = STORE) -> Path:
    """Append-only, one file per day. REFUSES to overwrite an existing day.

    The history is the whole value. A re-run that silently replaced a day would
    destroy the vintage it was supposed to preserve -- and would do it quietly,
    which is worse. A second run writes `<day>.rerun_<n>.jsonl` beside it.
    """
    store.mkdir(parents=True, exist_ok=True)
    path = store / f"{day}.jsonl"
    if path.exists():
        n = 1
        while (alt := store / f"{day}.rerun_{n}.jsonl").exists():
            n += 1
        path = alt
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


def load_day(day: str, store: Path = STORE) -> list[dict]:
    """The NEWEST vintage for `day` -- a rerun supersedes for reading, and the
    original stays on disk so the two can be compared."""
    cands = sorted(store.glob(f"{day}.jsonl")) + sorted(store.glob(f"{day}.rerun_*.jsonl"))
    if not cands:
        return []
    out = []
    for line in cands[-1].read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out
