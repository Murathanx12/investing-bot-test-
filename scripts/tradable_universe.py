"""TRADABLE_UNIVERSE -- the CRSP-common proxy, exported as a plain symbol list.

    python -m scripts.tradable_universe --start 2015-01-01 --end 2026-12-31
    python -m scripts.tradable_universe --start 2015-01-01 --end 2026-12-31 --with-alpaca-active
    python -m scripts.tradable_universe --show

WHY
===
Every collector in this repo has been pointed at `--universe fleet`: MURAT_NAMES
plus a theme basket plus whatever `window_universe.json` held, about 156 names,
and on 2026-09-07 `window_universe.json` was ABSENT, so it was fewer. Murat's
stated intent is WHOLE-MARKET coverage (VISION §4.1). A backfill over 156 names
answers a question about 156 names; it cannot answer "what does the market's
news look like", and every coverage number computed from it silently means
"coverage of the slice we already liked".

WHAT "TRADABLE" MEANS HERE, EXACTLY
===================================
CRSP `dsenames`, filtered to

    shrcd in (10, 11)      ordinary common shares of a US corporation --
                           this is what drops ADRs, closed-end funds, REIT
                           preferreds, units, warrants and SPAC rights
    exchcd in (1, 2, 3)    NYSE / NYSE American / NASDAQ

and to name rows whose validity interval overlaps the requested window, so a
company that was delisted in 2018 is IN a 2015-2026 universe (it existed and
had news then) and is not in a 2025-2026 one. That is the standard CRSP-common
screen and it is a PROXY: it is a share-class and listing filter, not a
liquidity filter. The execution floor (`TRADABLE_DOLLAR_VOL`, $3m/day) is a
different question asked at a different stage, and applying it here would
delete precisely the small names whose news coverage we are trying to measure.

THE HONEST LIMIT, STATED ON THE RECEIPT
=======================================
The local CRSP names table ends **2024-12-31**. Any window past that date is
therefore covered by names that were alive at the end of 2024, and EVERY
company listed since is missing. That is not a rounding error for a 2025-2026
news pull -- it is a systematic hole in exactly the direction that flatters a
coverage number (missing names cannot be reported as uncovered). So:

  * the receipt carries `crsp_names_end` and `window_beyond_crsp_days`;
  * `--with-alpaca-active` unions in Alpaca's own active `us_equity` asset
    list (one GET on the trading host, places nothing), which is the only free
    source here that knows about a 2026 listing. It is filtered to
    `exchange in {NYSE, NASDAQ, AMEX}` and `tradable`, because that is the
    venue-side analogue of `exchcd in (1,2,3)`: ARCA and BATS listings are
    overwhelmingly ETFs and OTC is not a listing at all, and unioning 9,936 of
    them in would have doubled the pull's cost while calling ETFs "common
    stock". Dotted suffixes (`.WS` warrants, `.U` units, `.PR*` preferreds)
    are dropped for the same reason;
  * a symbol contributed only by Alpaca is tagged in the receipt, because
    "CRSP said it was common stock" and "our broker will quote it" are
    different claims.

Nothing here fetches news, sizes anything, or places an order.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = Path(os.getenv("AAT_STATE_DIR", str(ROOT / "state")))
OUT = STATE / "tradable_universe.json"

#: The research repo, read-only. Overridable because the two repos are cloned
#: side by side by convention and not by contract.
FINANCE = Path(os.getenv("AEGIS_FINANCE_ROOT", str(ROOT.parent / "aegis-finance")))
DSENAMES = FINANCE / "backend" / "data" / "optimus" / "wrds" / "bulk" / "crsp__dsenames.parquet"

COMMON_SHRCD = (10, 11)
LISTED_EXCHCD = (1, 2, 3)

#: Alpaca news symbols are plain root tickers. CRSP writes class shares as
#: `BRK` + shrcls `B`; the venue writes `BRK.B`. We keep the CRSP ticker as it
#: stands (that is what Benzinga tags) and refuse anything that is not a
#: plausible US equity root, rather than inventing a mapping we cannot verify.
_SYMBOL_OK = re.compile(r"^[A-Z][A-Z0-9.]{0,6}$")

#: Alpaca listing venues that correspond to CRSP `exchcd in (1, 2, 3)`.
#: ARCA and BATS are where ETFs list; OTC is not a listing.
ALPACA_LISTED = ("NYSE", "NASDAQ", "AMEX")

#: Warrants, units, rights and preferreds carry a dotted suffix at Alpaca.
#: They are not common shares and their news is the common share's news.
_NOT_COMMON = re.compile(r"\.(WS|U|R|PR|P)[A-Z]?$")


class UniverseRefusal(RuntimeError):
    """The universe will not be built, and the reason is stated."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def crsp_common(start: str, end: str) -> tuple[list[str], dict]:
    """Tickers of CRSP common shares whose name interval overlaps [start, end]."""
    if not DSENAMES.exists():
        raise UniverseRefusal(
            f"{DSENAMES} not found. Set AEGIS_FINANCE_ROOT to the aegis-finance "
            "checkout, or pass --symbols-file with a list you built elsewhere. "
            "This REFUSES rather than falling back to the 156-name fleet, because "
            "a silent fallback is how a whole-market claim gets made from a slice.")
    try:
        import pandas as pd
    except ImportError as exc:                                          # pragma: no cover
        raise UniverseRefusal(f"pandas is required to read {DSENAMES.name}: {exc}") from exc

    df = pd.read_parquet(DSENAMES, columns=["permno", "namedt", "nameendt", "shrcd",
                                            "exchcd", "ticker", "comnam"])
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    names_end = df["nameendt"].max()
    common = df[df["shrcd"].isin(COMMON_SHRCD) & df["exchcd"].isin(LISTED_EXCHCD)]
    win = common[(common["namedt"] <= e) & (common["nameendt"] >= s)]
    syms = sorted({str(t).strip().upper() for t in win["ticker"].dropna()
                   if str(t).strip() and _SYMBOL_OK.match(str(t).strip().upper())})
    dropped = sorted({str(t).strip().upper() for t in win["ticker"].dropna()
                      if str(t).strip() and not _SYMBOL_OK.match(str(t).strip().upper())})
    beyond = (e - names_end).days if hasattr(names_end, "year") else None
    receipt = {
        "source": str(DSENAMES),
        "filter": {"shrcd": list(COMMON_SHRCD), "exchcd": list(LISTED_EXCHCD),
                   "overlap_window": [start, end]},
        "name_rows_in_window": int(len(win)),
        "permnos_in_window": int(win["permno"].nunique()),
        "tickers": len(syms),
        "tickers_rejected_by_shape": dropped[:20],
        "n_tickers_rejected_by_shape": len(dropped),
        "crsp_names_end": str(names_end),
        "window_beyond_crsp_days": beyond,
    }
    return syms, receipt


def alpaca_active(role: str | None = None) -> tuple[list[str], dict]:
    """Alpaca's own active us_equity list. One GET, places nothing."""
    from alpha import config
    from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal
    config.load_env()
    r = (role or os.getenv("AAT_ACCOUNT_ROLE", "").strip() or "hack1").lower()
    try:
        rows = AlpacaPaper(role=r).assets(status="active", asset_class="us_equity")
    except BrokerRefusal as exc:
        # A refusal is a finding. The universe is still built from CRSP; the
        # receipt says the venue leg did not answer, so nobody later reads the
        # missing 2025-26 listings as "there were none".
        return [], {"ok": False, "role": r, "error": str(exc)[:200]}
    by_exch: dict[str, int] = {}
    for a in rows:
        by_exch[str(a.get("exchange"))] = by_exch.get(str(a.get("exchange")), 0) + 1
    syms = sorted({
        str(a.get("symbol", "")).strip().upper() for a in rows
        if a.get("tradable")
        and str(a.get("exchange", "")).upper() in ALPACA_LISTED
        and _SYMBOL_OK.match(str(a.get("symbol", "")).strip().upper() or "-")
        and not _NOT_COMMON.search(str(a.get("symbol", "")).strip().upper())})
    return syms, {"ok": True, "role": r, "assets_returned": len(rows),
                  "by_exchange": by_exch, "kept_exchanges": list(ALPACA_LISTED),
                  "tradable_listed_symbols": len(syms)}


def build(start: str, end: str, *, with_alpaca: bool = False, role: str | None = None,
          out: Path | None = None) -> dict:
    syms, crsp_receipt = crsp_common(start, end)
    crsp_set = set(syms)
    alp_receipt: dict = {"requested": with_alpaca}
    alp_only: list[str] = []
    if with_alpaca:
        alp, alp_receipt2 = alpaca_active(role)
        alp_receipt.update(alp_receipt2)
        alp_only = sorted(set(alp) - crsp_set)
        syms = sorted(crsp_set | set(alp))
    payload = {
        "schema": "tradable_universe/1",
        "at": _utcnow(),
        "start": start, "end": end,
        "universe": syms,
        "n": len(syms),
        "receipt": {
            "crsp": crsp_receipt,
            "alpaca_active": alp_receipt,
            "n_crsp_only": len(crsp_set - set(alp_only)),
            "n_alpaca_only": len(alp_only),
            "alpaca_only_sample": alp_only[:25],
            "caveat": ("CRSP names end "
                       f"{crsp_receipt.get('crsp_names_end')}; every company first "
                       "listed after that date is absent unless the Alpaca leg ran."),
        },
    }
    dest = out or OUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return payload


def load(path: Path | None = None) -> list[str]:
    """The exported list, or a REFUSAL naming the command that writes it."""
    p = path or OUT
    if not p.exists():
        raise UniverseRefusal(
            f"{p} does not exist. Build it first:\n"
            "  python -m scripts.tradable_universe --start 2015-01-01 --end 2026-12-31 "
            "--with-alpaca-active")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise UniverseRefusal(f"{p} is unreadable: {exc}") from exc
    u = [str(s).upper() for s in d.get("universe", [])]
    if not u:
        raise UniverseRefusal(f"{p} holds an EMPTY universe -- refusing rather than "
                              "quietly pulling news for nobody")
    return u


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2026-12-31")
    ap.add_argument("--with-alpaca-active", action="store_true",
                    help="union Alpaca's active us_equity list (one GET, places nothing)")
    ap.add_argument("--role", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--show", action="store_true", help="print the existing export and exit")
    args = ap.parse_args()

    if args.show:
        try:
            u = load(Path(args.out) if args.out else None)
        except UniverseRefusal as exc:
            print(f"REFUSED: {exc}")
            return 1
        d = json.loads((Path(args.out) if args.out else OUT).read_text(encoding="utf-8"))
        print(json.dumps({k: v for k, v in d.items() if k != "universe"}, indent=1))
        print(f"{len(u)} symbols, first 15: {' '.join(u[:15])}")
        return 0

    p = build(args.start, args.end, with_alpaca=args.with_alpaca_active,
              role=args.role, out=Path(args.out) if args.out else None)
    print(json.dumps({k: v for k, v in p.items() if k != "universe"}, indent=1))
    print(f"wrote {args.out or OUT}: {p['n']} symbols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
