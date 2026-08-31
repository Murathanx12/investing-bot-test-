"""COMPANYSTATE: absence must stay absence, and a day must never be overwritten.

This is the one artefact whose value is its HISTORY, so the failures that matter
are not wrong arithmetic -- they are a zero standing in for a missing
measurement, and a re-run quietly replacing a vintage. Both are silent, and both
would only be discovered by a model trained months later on a corrupted table.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from alpha import company_state as CS

_fails: list[str] = []


def check(name: str, cond: bool, why: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        _fails.append(name)
        print(f"  FAIL {name}  {why}")


def _tracker_row(**kw):
    base = dict(symbol="TEST", observed_at="2026-08-31T07:00:00+00:00", sector="Tech",
                exchange="NASDAQ", market_cap_usd=1e9, tradable=True, shortable=True,
                median_dollar_volume=7.5e6, dv_bucket="mid", coverage=8,
                coverage_bucket="4-10", coverage_source="yfinance_numberOfAnalystOpinions",
                close=10.0, mean_target=15.0, target_high=20.0, target_low=12.0,
                upside=0.5, consensus=4.2, ret_12m=0.3, drawdown_60d=-0.1,
                past_winner=False, days_to_catalyst=10, status="BUY")
    base.update(kw)
    return base


def test_an_unreadable_dollar_volume_is_not_band_zero():
    """Band 0 MEASURES that a name trades under $100k/day. Absence is absence,
    and collapsing the two would teach a model that unmeasured names are the
    thinnest ones in the market."""
    check("None -> no band", CS.band_of(None) == (None, None))
    check("garbage -> no band", CS.band_of("n/a") == (None, None))
    b, n = CS.band_of(50_000)
    check("$50k/day IS band 0, measured", b == 0 and n == "<100k")
    check("$7.5m/day is 5m-10m", CS.band_of(7.5e6)[1] == "5m-10m")
    check("$80m/day is 50m+", CS.band_of(8e7)[1] == "50m+")


def test_the_unmeasured_band_has_no_invented_cost():
    """`<100k` was never measured by the TAQ study. It must carry None, not a
    guess -- a fabricated cost is worse than a missing one because it prices."""
    check("<100k carries no cost", CS.BAND_ROUND_TRIP_BPS["<100k"] is None)
    for b in ("100k-1m", "1m-5m", "5m-10m", "10m-50m", "50m+"):
        check(f"{b} carries its measured cost",
              isinstance(CS.BAND_ROUND_TRIP_BPS[b], float))
    check("the cost ladder is monotone -- thinner costs more",
          CS.BAND_ROUND_TRIP_BPS["100k-1m"] > CS.BAND_ROUND_TRIP_BPS["1m-5m"]
          > CS.BAND_ROUND_TRIP_BPS["5m-10m"] > CS.BAND_ROUND_TRIP_BPS["50m+"])


def test_analyst_disagreement_refuses_impossible_inputs():
    check("normal range", abs(CS.analyst_disagreement(20, 12, 10) - 0.8) < 1e-9)
    for bad in ((None, 12, 10), (20, None, 10), (20, 12, None),
                (20, 12, 0), (12, 20, 10), (-5, -8, 10)):
        check(f"refuses {bad}", CS.analyst_disagreement(*bad) is None)


def test_a_name_with_no_news_records_absence_not_zero():
    """`news_articles: 0` would say we looked and found nothing. We did not look
    -- the name had no row in today's feed at all."""
    r = CS.build_row(day="2026-08-31", tracker_row=_tracker_row())
    check("no attention -> None, not 0", r["news_articles"] is None)
    check("no attention_z", r["attention_z"] is None)
    check("and it says why", "no news row" in r["attention_basis"])
    check("no filings -> None, not 0", r["edgar_filings_6m"] is None)
    check("no rule numbers -> None", r["exp_return"] is None)


def test_band_change_is_absent_without_a_prior_band():
    r = CS.build_row(day="2026-08-31", tracker_row=_tracker_row(), prior_band=None)
    check("no prior band -> no change, not 0", r["band_change_12m"] is None)
    r2 = CS.build_row(day="2026-08-31", tracker_row=_tracker_row(), prior_band=1)
    check("prior band 1, now 3 -> climbed 2", r2["band_change_12m"] == 2,
          str(r2["band_change_12m"]))


def test_status_is_per_horizon_and_unstated_horizons_say_so():
    """A company can be avoid at 1 week and strong buy at 1 year. Copying the
    21-session status across five horizons would look like five agreeing
    opinions when only one was ever computed."""
    r = CS.build_row(day="2026-08-31", tracker_row=_tracker_row(status="BUY"))
    sbh, sb = r["status_by_horizon"], r["status_basis"]
    check("every horizon has a slot", set(sbh) == set(CS.HORIZONS))
    check("the tracker's 21-session judgement lands on 1m", sbh["1m"] == "BUY")
    for h in ("1w", "3m", "6m", "12m"):
        check(f"{h} is unstated, not copied", sbh[h] is None)
        check(f"{h} says why", "no generator" in sb[h])


def test_the_two_clocks_are_kept_apart():
    r = CS.build_row(day="2026-08-31",
                     tracker_row=_tracker_row(observed_at="2026-08-31T07:00:00+00:00"))
    check("observed_at is the market fact's clock",
          r["observed_at"] == "2026-08-31T07:00:00+00:00")
    check("written_at is this module's clock and differs",
          r["written_at"] != r["observed_at"])


def test_a_rerun_never_overwrites_a_vintage():
    """The history IS the value. A re-run that replaced a day would destroy the
    vintage it exists to preserve, and would do it silently."""
    d = Path(tempfile.mkdtemp())
    rows = [CS.build_row(day="2026-08-31", tracker_row=_tracker_row())]
    p1 = CS.write_day(rows, "2026-08-31", store=d)
    p2 = CS.write_day(rows, "2026-08-31", store=d)
    p3 = CS.write_day(rows, "2026-08-31", store=d)
    check("the first write takes the plain name", p1.name == "2026-08-31.jsonl")
    check("a second write goes beside it", p2.name == "2026-08-31.rerun_1.jsonl")
    check("and a third", p3.name == "2026-08-31.rerun_2.jsonl")
    check("all three vintages survive on disk", len(list(d.glob("2026-08-31*"))) == 3)
    check("reading returns the NEWEST vintage", len(CS.load_day("2026-08-31", store=d)) == 1)
    check("a day never written reads empty, not a crash",
          CS.load_day("1999-01-01", store=d) == [])


def test_a_truncated_line_does_not_destroy_the_day():
    d = Path(tempfile.mkdtemp())
    CS.write_day([CS.build_row(day="2026-08-31", tracker_row=_tracker_row())],
                 "2026-08-31", store=d)
    with (d / "2026-08-31.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"symbol": "HALF\n')
    got = CS.load_day("2026-08-31", store=d)
    check("the good row survives a truncated write", len(got) == 1)


def test_every_row_is_json_serialisable():
    """It is written as JSONL. A value that cannot serialise loses the DAY."""
    r = CS.build_row(day="2026-08-31", tracker_row=_tracker_row(),
                     attention={"n_articles": 3, "n_sources": 2, "attention_z": 1.4,
                                "is_new": False, "basis": "z vs own trailing history"},
                     filings={"total": 12, "by_form": {"8-K": 5, "4": 7}},
                     book_row={"p_up_21d": 0.52, "exp_return": 0.01,
                               "downside_5pct": -0.2, "confidence": 0.8})
    try:
        json.dumps(r)
        check("a fully-populated row serialises", True)
    except (TypeError, ValueError) as exc:
        check("a fully-populated row serialises", False, str(exc))
    check("upside_downside_ratio is derived from upside and the rule's downside",
          abs(r["upside_downside_ratio"] - 2.5) < 1e-9, str(r["upside_downside_ratio"]))
    check("attention is carried, not recomputed", r["attention_z"] == 1.4)
    check("filings are carried", r["edgar_filings_6m"] == 12)


def _run_all() -> int:
    import traceback
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    print(f"\n-- COMPANYSTATE: the daily vintage ({len(tests)} groups)")
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:                                        # noqa: BLE001
            _fails.append(name)
            print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
    print(f"\n{len(_fails)} failures" + (": " + ", ".join(_fails) if _fails else ""))
    return 1 if _fails else 0


# Guard at the BOTTOM: `_run_all` reads globals() at call time.
if __name__ == "__main__":
    raise SystemExit(_run_all())
