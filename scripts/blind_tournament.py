"""BLIND_TOURNAMENT -- does news carry direction once the NAME is removed?

    python -m scripts.blind_tournament --dry-run                 # build + blind, call nothing
    python -m scripts.blind_tournament --max-calls 120           # seal predictions, then grade
    python -m scripts.blind_tournament --grade-only <run_id>     # re-grade a sealed run

THE QUESTION
============
An LLM asked "what happens to Micron over the next month" answers from memory
of what DID happen to Micron -- its training set contains the outcome. The
parent project tested this once (TRIAL-LLM-AMNESIA-1) and the protocol is
Murat's: strip the company name, the ticker, the product names and every price
from a dated 30-day news window, ask for a 21-session percentage view, SEAL the
answer before any price is looked at, then grade against realised returns.

If the model still calls direction after blinding, news->direction carries
information the engine could use. If it cannot, every "the model read the
news and was right" result in this project was memorised outcome, and the
pre-open prediction book should stop asking it.

WHAT KEEPS THIS HONEST, IN CODE
===============================
- **SEAL BEFORE GRADE.** `blind_<run>.jsonl` is written per prediction, with a
  sha256 over the exact prompt text, before a single bar is fetched. Grading
  appends a SEPARATE `graded_<run>.jsonl`. Neither file is ever rewritten; a
  run id that already has a sealed file is refused, not resumed over.
- **THE CANARY.** 5% of cells (chosen by hash, not by us) get one fabricated
  headline. Every cell also asks the model to GUESS the company. A guess that
  matches the true name means the blinding leaked -- and a leaky run is
  FLAGGED in the receipt, because a hit rate computed on recognised names is
  a memory test, not a news test.
- **THE NULL.** Predictions are permuted across cells 200 times. The p-value
  is where the observed hit rate and IC sit in that distribution. n < 30
  graded cells prints the numbers and REFUSES a verdict.
- **COST.** `--max-calls` caps the run (default 300); `--dry-run` spends
  nothing and prints three blinded samples so the blinding can be read by a
  human before it is paid for. DeepSeek is not in the provider order -- this
  is bulk work on prepaid capacity.

GRADING CONVENTION
==================
Entry is the OPEN of the first session strictly after `month_end` (the bars
carry it, so we do not need the weaker first-close); exit is the CLOSE 20
sessions later -- 21 sessions held. Raw, SPY-relative and sector-ETF-relative
returns are all recorded; the headline metrics use RAW because the model was
asked a raw question. A cell whose 21 sessions have not elapsed is `immature`,
not graded, and counted.

SHADOW. Nothing here places an order or sizes a position.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import re
import sys
import time
from calendar import monthrange
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from alpha import config
from alpha.council import providers
from alpha.sources import corpus

from scripts.news_backfill import MURAT_NAMES

TOURNAMENT = corpus.STATE / "tournament"

#: Prepaid capacity first; DeepSeek (metered) deliberately absent.
# `openai` is FIRST from 2026-08-30: it is the only family independent of the
# original run that is actually live (HF is off by instruction and NVIDIA
# 429s), which makes it the second-family control this test has been waiting
# for. `featherless` is the ORIGINAL run's family (alibaba) and is therefore
# useless as a control -- it stays in the order only as a fallback for work
# that is not the control.
PROVIDER_ORDER = ("openai", "featherless", "nvidia_kimi", "hf_glm")

CONTROL = "SPY"
#: Instruments whose "identity" is the market itself. Derived aliases are
#: skipped for these -- see `derive_aliases`.
INDEX_SYMBOLS = frozenset({"SPY", "QQQ", "IWM", "DIA", "XBI", "SMH", "XLE"})
MONTHS_DEFAULT = ("2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02",
                  "2026-03", "2026-04", "2026-05", "2026-06", "2026-07")
WINDOW_DAYS = 30
MIN_ROWS = 5
MAX_ROWS_PER_CELL = 40          # most recent kept; the drop is recorded on the cell
HOLD_SESSIONS = 21
CANARY_SHARE = 0.05
CANARY_HEADLINE = "the company announced a reverse split"
N_PERMUTATIONS = 200
MIN_GRADED_FOR_VERDICT = 30

#: Sector ETF map, per the brief. Names not listed grade against IWM.
BIOTECH = {"BHVN", "KYTX", "NTLA", "ABSI", "AARD", "SRRK", "OLMA", "SLNO", "BEAM"}
SECTOR_ETF = {**{s: "XBI" for s in BIOTECH},
              **{s: "SMH" for s in ("MU", "MRVL", "AMD", "TSM", "QUBT")},
              "SOC": "XLE"}
DEFAULT_SECTOR_ETF = "IWM"

#: Company names the corpus is known to spell out. The DERIVED aliases (below)
#: are the mechanism the brief asks for; this list is a floor under it, because
#: a blinding that depends on a frequency threshold being right is a blinding
#: that leaks on the thin names. Both are recorded in the receipt.
KNOWN_ALIASES: dict[str, tuple[str, ...]] = {
    "SLDP": ("Solid Power",), "DKNG": ("DraftKings",), "HUBS": ("HubSpot",),
    "BHVN": ("Biohaven",), "AMSC": ("American Superconductor", "AMSC"),
    "KYTX": ("Kyverna",), "PRCH": ("Porch Group", "Porch"), "NTLA": ("Intellia",),
    "ABSI": ("Absci",), "QUBT": ("Quantum Computing Inc", "Quantum Computing Inc.",),
    "AARD": ("Aardvark Therapeutics", "Aardvark"), "SOC": ("Sable Offshore", "Sable"),
    "TSM": ("Taiwan Semiconductor", "TSMC"), "MU": ("Micron Technology", "Micron"),
    "MRVL": ("Marvell Technology", "Marvell"), "AMD": ("Advanced Micro Devices",),
    "SRRK": ("Scholar Rock",), "OLMA": ("Olema Pharmaceuticals", "Olema"),
    "SLNO": ("Soleno Therapeutics", "Soleno"), "BEAM": ("Beam Therapeutics",),
    "SPY": ("SPDR S&P 500", "S&P 500 ETF"),
}

#: Capitalised tokens that co-occur with everything and name nobody.
_ALIAS_STOP = set("""
The A An And Or Of For In On At To By With From As Is Are Was Were Be Been This That These Those
Stock Stocks Share Shares Market Markets Analyst Analysts Rating Ratings Price Target Targets
Earnings Revenue Guidance Report Reports Results Quarter Quarterly Q1 Q2 Q3 Q4 FY Year
Buy Sell Hold Upgrade Upgrades Downgrade Downgrades Outperform Neutral Overweight Underweight
Wall Street Nasdaq NASDAQ NYSE Dow Jones S&P Fed FOMC Trump China Taiwan US U.S. USA Europe
Monday Tuesday Wednesday Thursday Friday January February March April May June July August
September October November December Today Tonight Week Month Why What How Here Top Best
Inc Corp Co Ltd Group Holdings Technologies Technology Therapeutics Pharmaceuticals
AI Chip Chips Semiconductor Semiconductors Tech Data Center Centers Cloud Software Quantum
Big Bull Bear Bullish Bearish Rally Rallies Crash Drop Drops Jump Jumps Soar Soars
Investors Investor Trading Trade Trades Options Option Call Calls Put Puts Premarket Pre-Market
After-Hours Update Updates News Alert Alerts Movers Mover Gainers Losers Watch Watchlist
ETF ETFs Fund Funds Index Sector Sectors Company Companies Business CEO CFO FDA SEC EPS
""".split())

SYSTEM = (
    "You are an equity analyst. You are shown a BLINDED 30-day window of dated news about ONE "
    "unnamed US-listed company: the company name, ticker, product names and all prices and "
    "price moves have been replaced with placeholders. You do NOT know which company it is and "
    "must not try to identify it from memory of events. From the NEWS ALONE, give your view of "
    "the stock's percentage move over the NEXT 21 trading sessions after the window ends.")

USER_TEMPLATE = (
    "Blinded news window ending {month_end} (dates kept, names and prices removed):\n\n"
    "{headlines}\n\n"
    "Return ONE JSON object with exactly these keys:\n"
    '{{"direction": "up"|"down"|"flat", "expected_move_pct_21d": float (percent, e.g. -4.5), '
    '"confidence": float 0..1, "sector_guess": str, "company_guess": str|null '
    "(your best guess of the company's name, or null), \"rationale\": str (<= 40 words)}}")

WHY = ("Decides whether the pre-open prediction book keeps ASKING an LLM for news-implied "
       "direction: a blinded hit rate that the shuffled null cannot beat REFUSES that input "
       "and ranks it below the bars-only selectors.")


# ------------------------------------------------------------------ cells
def month_end(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    return f"{y:04d}-{m:02d}-{monthrange(y, m)[1]:02d}"


def _dedupe(rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        k = re.sub(r"[^a-z0-9]+", " ", str(r.get("title", "")).lower()).strip()
        if k and k not in seen:
            seen.add(k)
            out.append(r)
    return out


def build_cells(symbols: list[str], months: list[str], rows: list[dict]) -> list[dict]:
    """(symbol, month_end) cells from PAST rows observed within WINDOW_DAYS before month_end.

    The filter is on `observed_at` -- what was KNOWABLE -- never on
    `effective_at` (`corpus.py` docstring: filtering on the latter reads the
    future and improves every number).
    """
    by_sym: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("tense") != "past":
            continue
        for s in r.get("symbols") or []:
            by_sym.setdefault(s.upper(), []).append(r)
    cells = []
    for sym in symbols:
        for month in months:
            end = month_end(month)
            start = (datetime.fromisoformat(end) - timedelta(days=WINDOW_DAYS)).date().isoformat()
            win = [r for r in by_sym.get(sym, [])
                   if start < str(r.get("observed_at", ""))[:10] <= end]
            win = _dedupe(sorted(win, key=lambda r: str(r.get("observed_at", ""))))
            n_available = len(win)
            if n_available > MAX_ROWS_PER_CELL:
                win = win[-MAX_ROWS_PER_CELL:]
            cells.append({"cell_id": f"{sym}:{end}", "symbol": sym, "month": month, "month_end": end,
                          "window_start": start, "n_rows": len(win), "n_available": n_available,
                          "thin": n_available < MIN_ROWS, "rows": win})
    return cells


# ------------------------------------------------------------------ blinding
_CAP_TOKEN = re.compile(r"\b[A-Z][A-Za-z&'.-]{2,}\b")


def derive_aliases(symbol: str, all_rows: list[dict], *, min_count: int = 3,
                   min_specificity: float = 0.30) -> list[str]:
    """Capitalised tokens that co-occur with the ticker in titles AND are specific to it.

    Specificity = share of the token's title occurrences that are in this
    symbol's titles. Without it, "Nvidia" (in half of every chip title) and
    "Trump" would be stripped from MU -- harmless for blinding, but a strip
    list of 40 macro words is not a company alias list, and the receipt should
    say what was actually removed and why.
    """
    # AN INDEX HAS NO COMPANY TO BLIND (2026-08-30). The derivation looks for
    # capitalised tokens SPECIFIC to the symbol's own titles, which for a company
    # is its name and its products. For SPY the specific tokens are the macro
    # story -- measured on this corpus: U.S, Iran, Bessent, Hormuz, Warsh,
    # Trump's -- so the blinder deleted the news and left "the company.-Israel
    # Agreement On Trade" and "the company. stock futures swung". The control
    # would have measured whether a model can read shredded text.
    #
    # Declared aliases still apply ("SPDR S&P 500", "S&P 500 ETF"): those really
    # are the instrument's identity. The asymmetry is deliberate and it is
    # recorded on the receipt, because the index cells are then blinded less
    # than the single-name cells and a reader must be able to see that.
    if symbol.upper() in INDEX_SYMBOLS:
        return []

    tick = re.compile(rf"\b{re.escape(symbol)}\b", re.I)
    mine, everywhere = Counter(), Counter()
    lowercase_words = _lowercase_vocab(all_rows)
    for r in all_rows:
        title = str(r.get("title", ""))
        toks = {t.rstrip("-.'") for t in _CAP_TOKEN.findall(title)}
        toks = {t for t in toks if len(t) >= 3 and t not in _ALIAS_STOP and t.upper() != symbol
                and t.lower() not in lowercase_words}
        for t in toks:
            everywhere[t] += 1
        if symbol.upper() in {s.upper() for s in r.get("symbols") or []} or tick.search(title):
            for t in toks:
                mine[t] += 1
    out = [t for t, c in mine.most_common(200)
           if c >= min_count and c / max(1, everywhere[t]) >= min_specificity]
    return out[:8]


_VOCAB: set[str] | None = None


def _lowercase_vocab(rows: list[dict]) -> set[str]:
    """Words the corpus uses in LOWERCASE somewhere. A company name is never
    written lowercase; "memory", "cancer" and "whale" are. Without this the
    derived list stripped the very nouns the model needs ("Memory" from MU)."""
    global _VOCAB
    if _VOCAB is None:
        _VOCAB = set()
        for r in rows:
            _VOCAB.update(re.findall(r"\b[a-z][a-z'-]{2,}\b",
                                     str(r.get("title", "")) + " " + str(r.get("body", ""))[:400]))
    return _VOCAB


_PRICE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?\s*(?:[KMBT]|million|billion|trillion)?\b", re.I)
_MOVE_WORDS = (r"(?:shares?|stock|jump\w*|fall\w*|fell|rise\w*|rose|drop\w*|surge\w*|plunge\w*|gain\w*|"
               r"los\w*|slid\w*|slip\w*|rall\w*|climb\w*|soar\w*|tumbl\w*|sink\w*|sank|dip\w*|"
               r"up|down|higher|lower|crash\w*|pop\w*|spike\w*|rebound\w*|decline\w*|advance\w*|"
               r"retreat\w*|move\w*|moving|trading|traded|premarket|pre-market|after-hours|session)")
_MOVE_PCT = re.compile(rf"({_MOVE_WORDS}[^.;\n]{{0,40}}?)([+-]?\d+(?:\.\d+)?\s?%)", re.I)
_PCT_MOVE_AFTER = re.compile(rf"([+-]?\d+(?:\.\d+)?\s?%)(\s+(?:{_MOVE_WORDS}))", re.I)
_PRODUCT = re.compile(r"\b[A-Z]{2,}-?\d{2,}[A-Za-z0-9-]*\b")
_EXCHANGE_TICK = re.compile(r"\((?:NASDAQ|NYSE|NYSEARCA|AMEX|OTC)\s*:\s*[A-Z.]{1,6}\)|\b(?:NASDAQ|NYSE|NYSEARCA):\s*[A-Z.]{1,6}\b")

BLINDING_RULES = [
    "exchange-prefixed tickers '(NASDAQ:XX)' / 'NYSE:XX' -> '[ticker]'",
    "the cell's own ticker, case-insensitive, word-bounded -> '[ticker]'",
    "every OTHER tracked ticker (Murat's 20, SPY, fleet theme list) word-bounded -> '[ticker]'",
    "company name and aliases (KNOWN_ALIASES floor + derived co-occurring capitalised tokens, "
    "specificity >= 0.30, count >= 3) -> 'the company'",
    "dollar prices ($12.50, $1.2B) -> '[price]'",
    "percentages within 40 chars after a move/stock word, or directly before one -> '[pct]'",
    "product/drug code names [A-Z]{2,}-?\\d{2,} -> '[product]'",
    "dates kept; person names kept",
]


class Blinder:
    def __init__(self, symbol: str, aliases: list[str], other_tickers: list[str]):
        self.symbol = symbol.upper()
        self.aliases = sorted({a for a in aliases if a}, key=len, reverse=True)
        self.other = [t for t in other_tickers if t.upper() != self.symbol]
        self._tick = re.compile(rf"\b{re.escape(self.symbol)}\b", re.I)
        self._alias = [re.compile(rf"\b{re.escape(a)}(?:'s)?\b", re.I) for a in self.aliases]
        others = "|".join(re.escape(t) for t in sorted(set(self.other), key=len, reverse=True))
        self._others = re.compile(rf"\b(?:{others})\b") if others else None
        self.counts: Counter = Counter()

    def _sub(self, rx: re.Pattern, repl: str, text: str, key: str) -> str:
        text, n = rx.subn(repl, text)
        self.counts[key] += n
        return text

    def blind(self, text: str) -> str:
        text = self._sub(_EXCHANGE_TICK, "[ticker]", text, "exchange_ticker")
        for rx in self._alias:
            text = self._sub(rx, "the company", text, "alias")
        text = self._sub(self._tick, "[ticker]", text, "ticker")
        if self._others is not None:
            text = self._sub(self._others, "[ticker]", text, "other_ticker")
        text = self._sub(_PRICE, "[price]", text, "price")
        text = self._sub(_MOVE_PCT, r"\1[pct]", text, "pct_move")
        text = self._sub(_PCT_MOVE_AFTER, r"[pct]\2", text, "pct_move")
        text = self._sub(_PRODUCT, "[product]", text, "product")
        return text


def tracked_tickers() -> list[str]:
    out = set(MURAT_NAMES) | {CONTROL}
    try:
        from alpha import fleet
        out |= set(fleet.theme_symbols())
    except Exception:                                                   # noqa: BLE001
        pass
    return sorted(out)


def is_canary(cell_id: str, run_id: str) -> bool:
    h = int(hashlib.sha256(f"{run_id}|{cell_id}".encode()).hexdigest()[:8], 16)
    return (h % 10000) / 10000.0 < CANARY_SHARE


def render_headlines(cell: dict, blinder: Blinder, *, canary: bool) -> str:
    lines = []
    for r in cell["rows"]:
        d = str(r.get("observed_at", ""))[:10]
        title = blinder.blind(html.unescape(str(r.get("title", ""))).strip())
        body = blinder.blind(html.unescape(str(r.get("body", ""))).strip())[:240]
        lines.append(f"- {d}: {title}" + (f" -- {body}" if body else ""))
    if canary:
        d = cell["month_end"]
        lines.insert(max(0, len(lines) - 2), f"- {d}: {CANARY_HEADLINE}")
    return "\n".join(lines)


def build_prompt(cell: dict, blinder: Blinder, *, canary: bool) -> str:
    return USER_TEMPLATE.format(month_end=cell["month_end"],
                                headlines=render_headlines(cell, blinder, canary=canary))


def guess_matches(guess: Any, symbol: str, aliases: list[str]) -> bool:
    g = str(guess or "").strip().lower()
    if not g or g in ("null", "none", "unknown", "n/a"):
        return False
    if g == symbol.lower() or re.search(rf"{re.escape(symbol.lower())}", g):
        return True
    names = {a.lower() for a in aliases} | {a.lower() for a in KNOWN_ALIASES.get(symbol, ())}
    return any(n and (n in g or g in n) for n in names if len(n) >= 3)


# ------------------------------------------------------------------ sealing
def run_paths(run_id: str) -> tuple[Path, Path, Path]:
    return (TOURNAMENT / f"blind_{run_id}.jsonl", TOURNAMENT / f"graded_{run_id}.jsonl",
            TOURNAMENT / f"receipt_{run_id}.json")


def seal(path: Path, row: dict) -> None:
    TOURNAMENT.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def choose_cells(cells: list[dict], max_calls: int) -> list[dict]:
    """Round-robin across months so a small budget still spans the calendar."""
    live = [c for c in cells if not c["thin"]]
    by_month: dict[str, list[dict]] = {}
    for c in live:
        by_month.setdefault(c["month"], []).append(c)
    months = sorted(by_month)
    out: list[dict] = []
    i = 0
    while len(out) < max_calls and any(by_month[m] for m in months):
        m = months[i % len(months)]
        if by_month[m]:
            out.append(by_month[m].pop(0))
        i += 1
    return out


def ask(cell: dict, prompt: str, live_order: list[str], *, max_tokens: int) -> tuple[dict | None, dict, list[str]]:
    """First provider in `live_order` that answers with the required keys."""
    refusals = []
    for prov in live_order:
        try:
            obj, meta = providers.chat_json(prov, SYSTEM, prompt, caller="blind_tournament.ask",
                                            why=WHY, max_tokens=max_tokens, temperature=0.1)
        except providers.ProviderRefusal as exc:
            refusals.append(f"{prov}: {str(exc)[:160]}")
            continue
        d = str(obj.get("direction", "")).lower().strip()
        try:
            mv = float(obj.get("expected_move_pct_21d"))
            conf = float(obj.get("confidence"))
        except (TypeError, ValueError):
            refusals.append(f"{prov}: missing numeric fields {str(obj)[:80]!r}")
            continue
        if d not in ("up", "down", "flat"):
            refusals.append(f"{prov}: direction {d!r} not in up/down/flat")
            continue
        pred = {"direction": d, "expected_move_pct_21d": mv, "confidence": max(0.0, min(1.0, conf)),
                "sector_guess": str(obj.get("sector_guess") or "")[:60],
                "company_guess": (None if obj.get("company_guess") in (None, "", "null") else str(obj.get("company_guess"))[:60]),
                "rationale": str(obj.get("rationale") or "")[:300]}
        return pred, meta, refusals
    return None, {}, refusals


# ------------------------------------------------------------------ grading
def fetch_daily_bars(symbols: list[str], start: str, end: str) -> dict[str, list[dict]]:
    """Daily bars from the venue, SIP feed (the free plan serves historical SIP
    bars; IEX volume is a different market -- `alpaca.bars` docstring).
    Module-level so a test can monkeypatch it without a socket."""
    from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal
    client = AlpacaPaper()
    out: dict[str, list[dict]] = {}
    feed = "sip"
    for i in range(0, len(symbols), 50):
        batch = symbols[i:i + 50]
        token = None
        while True:
            params = {"symbols": ",".join(batch), "timeframe": "1Day", "start": start, "end": end,
                      "adjustment": "all", "limit": 10000, "feed": feed, "page_token": token}
            try:
                page = client._request("GET", "/v2/stocks/bars", base=config.data_url(), timeout=90.0, params=params)
            except BrokerRefusal as exc:
                # Measured 2026-08-29: "subscription does not permit querying recent SIP
                # data" -- a window that reaches today is refused on the free plan even
                # for DAILY bars. Fall back to the configured feed once and record it.
                if feed == "sip" and "SIP" in str(exc):
                    feed = config.stock_feed()
                    BARS_FEED_USED["feed"] = feed
                    BARS_FEED_USED["why"] = str(exc)[:160]
                    continue
                raise
            for s, bars in (page.get("bars") or {}).items():
                out.setdefault(s, []).extend(bars)
            token = page.get("next_page_token")
            if not token:
                break
    for s in out:
        out[s].sort(key=lambda b: b["t"])
    return out


#: Which feed the grade actually used; the receipt reads it.
BARS_FEED_USED: dict[str, str] = {"feed": "sip", "why": ""}


def realised(bars: list[dict], after: str, hold: int = HOLD_SESSIONS) -> dict | None:
    """Entry = OPEN of first session > `after`; exit = CLOSE `hold-1` sessions later."""
    sess = [b for b in bars if b["t"][:10] > after]
    if len(sess) < hold:
        return None
    e, x = sess[0], sess[hold - 1]
    return {"entry_date": e["t"][:10], "entry_open": float(e["o"]), "exit_date": x["t"][:10],
            "exit_close": float(x["c"]), "ret": float(x["c"]) / float(e["o"]) - 1.0}


def grade_rows(sealed: list[dict], bars: dict[str, list[dict]]) -> tuple[list[dict], Counter]:
    out, why = [], Counter()
    for s in sealed:
        if not s.get("prediction"):
            why["no_prediction"] += 1
            continue
        sym, after = s["symbol"], s["month_end"]
        r = realised(bars.get(sym, []), after)
        if r is None:
            why["immature_or_no_bars"] += 1
            continue
        spy = realised(bars.get(CONTROL, []), after)
        etf_name = SECTOR_ETF.get(sym, DEFAULT_SECTOR_ETF) if sym != CONTROL else None
        etf = realised(bars.get(etf_name, []), after) if etf_name else None
        out.append({**{k: s[k] for k in ("cell_id", "symbol", "month_end", "canary", "prompt_sha256", "provider")},
                    "prediction": s["prediction"], "graded_at": corpus.utcnow(),
                    "entry_convention": "next-session OPEN after month_end; exit CLOSE 20 sessions later (21 held)",
                    "realised": r, "ret_raw": r["ret"],
                    "ret_vs_spy": (r["ret"] - spy["ret"]) if spy else None,
                    "sector_etf": etf_name, "ret_vs_sector": (r["ret"] - etf["ret"]) if etf else None})
        why["graded"] += 1
    return out, why


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return float("nan")
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def _hit(dirs: list[str], rets: np.ndarray) -> tuple[float, int]:
    idx = [i for i, d in enumerate(dirs) if d in ("up", "down")]
    if not idx:
        return float("nan"), 0
    hits = sum(1 for i in idx if (rets[i] > 0) == (dirs[i] == "up"))
    return hits / len(idx), len(idx)


def metrics(graded: list[dict], *, ret_key: str = "ret_raw", n_perm: int = N_PERMUTATIONS,
            seed: int = 7) -> dict[str, Any]:
    rows = [g for g in graded if g.get(ret_key) is not None]
    n = len(rows)
    out: dict[str, Any] = {"ret_key": ret_key, "n": n}
    if n == 0:
        return out
    rets = np.array([g[ret_key] for g in rows], dtype=float)
    dirs = [g["prediction"]["direction"] for g in rows]
    moves = np.array([g["prediction"]["expected_move_pct_21d"] for g in rows], dtype=float)
    conf = np.array([g["prediction"]["confidence"] for g in rows], dtype=float)

    hit, n_dir = _hit(dirs, rets)
    ic = _spearman(moves, rets)
    up = rets[[d == "up" for d in dirs]]
    dn = rets[[d == "down" for d in dirs]]
    out.update({"n_directional": n_dir, "hit_rate": hit, "ic_spearman": ic,
                "n_up": int(len(up)), "n_down": int(len(dn)), "n_flat": int(sum(d == "flat" for d in dirs)),
                "mean_ret_up_calls": float(up.mean()) if len(up) else None,
                "mean_ret_down_calls": float(dn.mean()) if len(dn) else None,
                "up_minus_down": (float(up.mean() - dn.mean()) if len(up) and len(dn) else None),
                "mean_ret_all": float(rets.mean())})

    # calibration by confidence tercile
    terc = {}
    if n >= 3:
        qs = np.quantile(conf, [1 / 3, 2 / 3])
        for name, mask in (("low", conf <= qs[0]), ("mid", (conf > qs[0]) & (conf <= qs[1])), ("high", conf > qs[1])):
            if mask.sum():
                h, k = _hit([d for d, m in zip(dirs, mask) if m], rets[mask])
                terc[name] = {"n": int(mask.sum()), "n_directional": k, "hit_rate": h,
                              "mean_conf": float(conf[mask].mean())}
    out["calibration_by_confidence_tercile"] = terc

    # shuffled null: permute PREDICTIONS across cells, keep realised fixed
    rng = np.random.default_rng(seed)
    null_hit, null_ic = [], []
    for _ in range(n_perm):
        p = rng.permutation(n)
        h, _k = _hit([dirs[i] for i in p], rets)
        null_hit.append(h)
        null_ic.append(_spearman(moves[p], rets))
    nh = np.array(null_hit, dtype=float)
    ni = np.array(null_ic, dtype=float)
    out["null"] = {
        "n_permutations": n_perm,
        "p_hit_rate": (float(np.mean(nh[~np.isnan(nh)] >= hit)) if not np.isnan(hit) else None),
        "p_ic": (float(np.mean(ni[~np.isnan(ni)] >= ic)) if not np.isnan(ic) else None),
        "null_hit_mean": float(np.nanmean(nh)) if np.isfinite(nh).any() else None,
        "null_ic_sd": float(np.nanstd(ni)) if np.isfinite(ni).any() else None,
        "note": "one-sided: share of permutations at or above the observed statistic",
    }
    return out


def verdict(m: dict[str, Any], *, leaky: bool) -> str:
    n = m.get("n", 0)
    if n < MIN_GRADED_FOR_VERDICT:
        return f"REFUSED: n={n} graded cells < {MIN_GRADED_FOR_VERDICT}; the numbers are printed, a verdict is not"
    if leaky:
        return "FLAGGED LEAKY: identification rate above 5%; hit rate is a memory test, not a news test"
    p = (m.get("null") or {}).get("p_hit_rate")
    pi = (m.get("null") or {}).get("p_ic")
    if p is not None and p < 0.05 and pi is not None and pi < 0.05:
        return "news carries direction after blinding (both hit rate and IC beat the shuffled null at p<0.05)"
    if (p is not None and p < 0.05) or (pi is not None and pi < 0.05):
        return "MIXED: one of hit rate / IC beats the null, the other does not"
    return "NO INFORMATION: blinded predictions are indistinguishable from shuffled predictions"


# ------------------------------------------------------------------ driver
def _fmt(x: Any, nd: int = 3) -> str:
    return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="build + blind, print 3 samples, call nothing")
    ap.add_argument("--max-calls", type=int, default=300)
    ap.add_argument("--max-tokens", type=int, default=600)
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--months", nargs="*", default=list(MONTHS_DEFAULT))
    ap.add_argument("--provider", default=None,
                    help="pin the model family (featherless | nvidia_kimi | hf_glm). "
                         "Without it the run takes whichever probed live first, so the "
                         "second-family CONTROL could never be requested.")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--grade-only", default=None, metavar="RUN_ID")
    ap.add_argument("--no-grade", action="store_true", help="seal only; grade later with --grade-only")
    args = ap.parse_args(argv)
    config.load_env()
    try:                                   # Windows console is cp1252; the corpus is not
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    if args.grade_only:
        return grade_run(args.grade_only)

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sealed_path, graded_path, receipt_path = run_paths(run_id)
    if sealed_path.exists() and not args.dry_run:
        print(f"REFUSED: {sealed_path} already exists; a sealed run is never overwritten. Pick another --run-id.")
        return 2

    symbols = [s.upper() for s in args.symbols] if args.symbols else list(MURAT_NAMES) + [CONTROL]
    rows = corpus.read(tense="past")
    cells = build_cells(symbols, list(args.months), rows)
    n_thin = sum(c["thin"] for c in cells)
    thin_by_sym = Counter(c["symbol"] for c in cells if c["thin"])
    print(f"corpus rows (past): {len(rows)}   cells: {len(cells)}   thin (<{MIN_ROWS} rows): {n_thin}")
    if thin_by_sym:
        print("  thin by symbol: " + " ".join(f"{s}:{n}" for s, n in sorted(thin_by_sym.items())))

    others = tracked_tickers()
    aliases = {s: list(dict.fromkeys(list(KNOWN_ALIASES.get(s, ())) + derive_aliases(s, rows))) for s in symbols}
    blinders = {s: Blinder(s, aliases[s], others) for s in symbols}
    chosen = choose_cells(cells, args.max_calls)
    print(f"cells to ask: {len(chosen)} (cap {args.max_calls}); months covered: "
          + " ".join(f"{m}:{n}" for m, n in sorted(Counter(c['month'] for c in chosen).items())))

    if args.dry_run:
        rng = random.Random(run_id)
        for c in rng.sample(chosen, min(3, len(chosen))):
            canary = is_canary(c["cell_id"], run_id)
            print("\n" + "=" * 72 + f"\nSAMPLE {c['cell_id']}  rows={c['n_rows']}/{c['n_available']}  canary={canary}"
                  f"  aliases={aliases[c['symbol']]}")
            print(render_headlines(c, blinders[c["symbol"]], canary=canary)[:2500])
        print("\nblinding counts: " + json.dumps(sum((b.counts for b in blinders.values()), Counter())))
        print("DRY RUN: no LLM call made, nothing sealed.")
        return 0

    # --provider PINS the family (roadmap section 6 asked for this flag). A
    # negative result on ONE model is ambiguous between "the news carries no
    # direction" and "this model cannot read it", and the only way to tell them
    # apart is to run the same sealed cells through a different family. Without
    # the flag the run silently takes whichever provider probed live first, so
    # the second family could never be requested -- and a control you cannot
    # request is a control that never happens.
    order = list(PROVIDER_ORDER)
    if args.provider:
        if args.provider not in PROVIDER_ORDER:
            print(f"REFUSED: --provider {args.provider!r} is not one of {PROVIDER_ORDER}")
            return 2
        order = [args.provider]
    live = providers.probe(order)
    live_order = [p for p in order if live.get(p, {}).get("state") == "live"]
    print("providers: " + "  ".join(f"{p}={live.get(p, {}).get('state')}" for p in order))
    if not live_order:
        print("REFUSED: no live provider in " + ", ".join(order)
              + (" (pinned by --provider; NOT falling back to another family, because a run "
                 "that silently changes model answers a different question)" if args.provider else ""))
        return 2

    n_calls, n_refused, n_sealed, t0 = 0, 0, 0, time.time()
    prov_mix: Counter = Counter()
    tokens = 0
    refusal_log: list[str] = []
    for i, c in enumerate(chosen, 1):
        if n_calls >= args.max_calls:
            break
        canary = is_canary(c["cell_id"], run_id)
        prompt = build_prompt(c, blinders[c["symbol"]], canary=canary)
        sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        n_calls += 1
        pred, meta, refs = ask(c, prompt, live_order, max_tokens=args.max_tokens)
        refusal_log += [f"{c['cell_id']} {r}" for r in refs]
        row = {"run_id": run_id, "cell_id": c["cell_id"], "symbol": c["symbol"], "month": c["month"],
               "month_end": c["month_end"], "window_start": c["window_start"], "n_rows": c["n_rows"],
               "n_available": c["n_available"], "canary": canary, "prompt_sha256": sha,
               "prompt_chars": len(prompt), "blinded_prompt": prompt, "sealed_at": corpus.utcnow(),
               "provider": meta.get("provider"), "model": meta.get("model"), "llm_meta": meta,
               "prediction": pred, "refusals": refs,
               "company_guess_matches": (guess_matches(pred["company_guess"], c["symbol"], aliases[c["symbol"]])
                                         if pred else None)}
        seal(sealed_path, row)                       # SEALED BEFORE ANY BAR IS FETCHED
        if pred:
            n_sealed += 1
            prov_mix[meta.get("provider")] += 1
            tokens += int(meta.get("prompt_tokens") or 0) + int(meta.get("completion_tokens") or 0)
        else:
            n_refused += 1
        print(f"[{i}/{len(chosen)}] {c['cell_id']:<16} "
              + (f"{pred['direction']:<5} {pred['expected_move_pct_21d']:+6.1f}% conf {pred['confidence']:.2f} "
                 f"guess={pred['company_guess']!r:<20} {meta.get('provider')} {meta.get('latency_s')}s"
                 if pred else f"REFUSED {refs[-1][:70] if refs else ''}")
              + f"   | calls {n_calls} sealed {n_sealed} refused {n_refused} tokens {tokens} {time.time() - t0:.0f}s",
              flush=True)

    print(f"\nsealed {n_sealed} predictions -> {sealed_path}   refused {n_refused}   tokens {tokens} (our telemetry)")
    receipt = {"run_id": run_id, "sealed_at": corpus.utcnow(), "symbols": symbols, "months": list(args.months),
               "counts": {"cells": len(cells), "thin": n_thin, "thin_by_symbol": dict(thin_by_sym),
                          "asked": n_calls, "sealed": n_sealed, "refused": n_refused,
                          "canary_cells": sum(1 for c in chosen[:n_calls] if is_canary(c["cell_id"], run_id))},
               "provider_mix": dict(prov_mix), "providers_probed": live, "tokens_total": tokens,
               "max_tokens": args.max_tokens, "blinding_rules": BLINDING_RULES,
               "aliases_applied": aliases, "other_tickers_stripped": others,
               "blinding_counts": dict(sum((b.counts for b in blinders.values()), Counter())),
               "refusals_sample": refusal_log[:20], "n_refusal_lines": len(refusal_log),
               "graded": None, "prompt_system_sha256": hashlib.sha256(SYSTEM.encode()).hexdigest()}
    TOURNAMENT.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=1, ensure_ascii=False), encoding="utf-8")
    if args.no_grade:
        print(f"receipt (ungraded) -> {receipt_path}")
        return 0
    return grade_run(run_id)


def grade_run(run_id: str) -> int:
    sealed_path, graded_path, receipt_path = run_paths(run_id)
    sealed = _read_jsonl(sealed_path)
    if not sealed:
        print(f"REFUSED: nothing sealed at {sealed_path}")
        return 2
    if graded_path.exists():
        print(f"REFUSED: {graded_path} exists; a graded file is never rewritten")
        return 2
    syms = sorted({s["symbol"] for s in sealed} | {CONTROL} | set(SECTOR_ETF.values()) | {DEFAULT_SECTOR_ETF})
    start = min(s["month_end"] for s in sealed)
    # End YESTERDAY: the free plan refuses a SIP window that touches today.
    end = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    print(f"grading {len(sealed)} sealed rows: bars for {len(syms)} symbols {start}..{end}")
    from alpha.broker.alpaca import BrokerRefusal
    try:
        bars = fetch_daily_bars(syms, start, end)
    except BrokerRefusal as exc:
        print(f"REFUSED (grading): venue refused bars: {str(exc)[:200]}; sealed rows are intact")
        return 2
    except config.CredentialRefusal as exc:
        # Measured 2026-08-29: the first real run sealed 120 rows and then died here,
        # because bars go through the venue client and the client needs a role even
        # for a read-only GET. The seal survived; the grade is re-run with
        # `AAT_ACCOUNT_ROLE=dev ... --grade-only <run_id>`.
        print(f"REFUSED (grading): {str(exc)[:200]}")
        print(f"  sealed rows are intact; re-run with "
              f"AAT_ACCOUNT_ROLE=dev python -m scripts.blind_tournament --grade-only {run_id}")
        return 2
    graded, why = grade_rows(sealed, bars)
    for g in graded:
        seal(graded_path, g)
    print(f"graded {len(graded)} -> {graded_path}   skipped: {dict(why)}")

    with_pred = [s for s in sealed if s.get("prediction")]
    n_guess = sum(1 for s in with_pred if s.get("prediction", {}).get("company_guess"))
    n_ident = sum(1 for s in with_pred if s.get("company_guess_matches"))
    ident_rate = n_ident / len(with_pred) if with_pred else None
    leaky = bool(ident_rate is not None and ident_rate > 0.05)
    canary_cells = [s for s in with_pred if s.get("canary")]
    canary_ident = sum(1 for s in canary_cells if s.get("company_guess_matches"))

    m_raw = metrics(graded, ret_key="ret_raw")
    m_spy = metrics(graded, ret_key="ret_vs_spy")
    m_sec = metrics([g for g in graded if g["symbol"] != CONTROL], ret_key="ret_vs_sector")
    v = verdict(m_raw, leaky=leaky)

    print("\n" + "=" * 72)
    print(f"BLIND TOURNAMENT {run_id}   n graded = {m_raw.get('n', 0)}   (n directional = {m_raw.get('n_directional')})")
    print(f"identification: {n_ident}/{len(with_pred)} guesses matched the company = {_fmt(ident_rate)}"
          f"   (guessed anything: {n_guess}; canary cells {len(canary_cells)}, identified {canary_ident})"
          + ("   ** FLAGGED LEAKY **" if leaky else ""))
    for label, m in (("raw", m_raw), ("vs SPY", m_spy), ("vs sector ETF", m_sec)):
        nl = m.get("null") or {}
        print(f"  {label:<14} n={m.get('n', 0):<4} hit={_fmt(m.get('hit_rate'))} (null {_fmt(nl.get('null_hit_mean'))}, "
              f"p={_fmt(nl.get('p_hit_rate'))})  IC={_fmt(m.get('ic_spearman'))} (p={_fmt(nl.get('p_ic'))})  "
              f"up={_fmt(m.get('mean_ret_up_calls'), 4)} down={_fmt(m.get('mean_ret_down_calls'), 4)} "
              f"up-down={_fmt(m.get('up_minus_down'), 4)}  n_up/down/flat={m.get('n_up')}/{m.get('n_down')}/{m.get('n_flat')}")
    terc = m_raw.get("calibration_by_confidence_tercile") or {}
    if terc:
        print("  calibration (raw) by confidence tercile: "
              + "  ".join(f"{k}: n={t['n']} hit={_fmt(t['hit_rate'])} conf={t['mean_conf']:.2f}" for k, t in terc.items()))
    print(f"VERDICT: {v}")

    receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else {"run_id": run_id}
    receipt["graded"] = {
        "graded_at": corpus.utcnow(), "counts": {"sealed": len(sealed), "with_prediction": len(with_pred),
                                                  "graded": len(graded), "skipped": dict(why)},
        "identification": {"n_guessed": n_guess, "n_matched": n_ident, "rate": ident_rate, "leaky": leaky,
                           "canary_cells": len(canary_cells), "canary_identified": canary_ident},
        "metrics_raw": m_raw, "metrics_vs_spy": m_spy, "metrics_vs_sector": m_sec,
        "provider_mix_graded": dict(Counter(g["provider"] for g in graded)),
        "verdict": v, "entry_convention": "next-session OPEN after month_end; exit CLOSE 20 sessions later",
        "bars_feed": BARS_FEED_USED["feed"], "bars_feed_note": BARS_FEED_USED["why"], "bars_adjustment": "all"}
    receipt_path.write_text(json.dumps(receipt, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    print(f"receipt -> {receipt_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
