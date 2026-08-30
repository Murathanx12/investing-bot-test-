"""NEWS -> NUMBERS. One (symbol, day) of the observation corpus as a numeric row.

    from alpha.sources import features
    row = features.daily_features("NTLA", "2026-03-04", rows, baseline_rows,
                                  bars=bars, rating_rec=rec, novelty=novelty_fn)

WHY THIS EXISTS
===============
`corpus.py` is prose: 30k rows of titles and summaries the digest reads with an
LLM at ~$0.01 a name. Nothing in the engine could RANK on it, backtest it, or
ask whether attention, novelty or lexicon tone had ever preceded a return.
This module turns one (symbol, day) into a dict of numbers the farm and the
IC harness (`scripts/corpus_features.py`) can consume, with two rules:

1. **POINT IN TIME, enforced here and not by the caller.** Every count uses
   only rows whose `observed_at <= day 23:59:59Z`. A caller may pass the whole
   corpus; the row observed tomorrow never counts today. The test pins it.
2. **NULL, NEVER ZERO BY DEFAULT.** A field the inputs cannot support is
   `None`, and `derivable[field]` says so. A zero that means "we had no data"
   and a zero that means "we measured nothing" are the same number and
   different facts; the arena's `coverage {"1": 206}` was the cost of not
   separating them.

WHAT THE NUMBERS ARE
====================
ATTENTION   n_items_{1,5,20}d over CALENDAR days ending on `day` (inclusive);
            coverage_baseline_90d = items/day over the 90 calendar days that
            END the day before the 5-day window; attention_z = Poisson z of
            the 5-day count against that baseline, floored at 1 item / 90 d
            so a name with a silent baseline still registers a burst.
NOVELTY     novelty_5d = mean over the last 5 days' titles of
            (1 - max cosine to any title in the prior 60 days). Vectors come
            from `novelty` (a callable the caller supplies -- NVIDIA embeddings
            when live, TF-IDF otherwise, `Embedder` below does both). The
            RECEIPT names which one was used, because "novelty" from a bag of
            words and from an embedding are different measurements.
SOURCES     n_sources_5d, source_independence = distinct publishers / items.
            The publisher is the part of `source` after the collector prefix
            (`alpaca:benzinga` -> benzinga, `finnhub:Yahoo` -> yahoo), falling
            back to the URL host. Two wires carrying the same Benzinga note are
            ONE publisher, which is the point.
TONE        sentiment_lex_5d = (pos - neg) / (pos + neg) over title + body with
            a finance lexicon (Loughran-McDonald in spirit; the word lists live
            in this file so a test can pin them). A negator within three
            tokens flips the hit. Null when NO lexicon word appeared -- a
            5-day window with nothing to score is not neutral, it is unread.
EVENTS      event_type_counts_20d from `classify_title`, a regex classifier
            kept in code and tested on fixture titles. A title may carry more
            than one type.
CATALYST    days_to_next_catalyst from `tense == "future"` rows OBSERVED by
            `day` and EFFECTIVE after it.
ANALYST     target_ratio = median 90-day broker target / the day's close, via
            `alpha.analyst_targets.panel` (Opus's Benzinga extraction, MIN_FIRMS
            respected); the close is the ALPACA DAILY BAR CLOSE (SIP,
            adjustment=all) the caller passes as `bars`. rating_counts_mean is
            `consensus_rating` over the Finnhub counts in `rating_rec`, if any.
PRICE       ret_5d, ret_20d (close/close over TRADING days), drawdown_from_60d_
            high (close / max close of the last 60 bars incl. today - 1),
            realised_vol_20d (annualised sd of log close returns),
            dollar_volume_20d (mean close*volume). Null below the bar count.

NO NETWORK IN `daily_features`. The only thing here that can open a socket is
`Embedder.nvidia`, which the script wires; a test never reaches it.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import statistics as st
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Sequence
from urllib.parse import urlparse

try:
    import numpy as np
except ImportError:                                                    # pragma: no cover
    np = None  # type: ignore[assignment]

#: The NVIDIA embedding model that answered on 2026-08-29. `nv-embedqa-e5-v5`,
#: `nv-embed-v1` and `llama-3.2-nv-embedqa-1b-v2` are HTTP 410 (end of life);
#: `embed-qa-4`, `nv-embedqa-mistral-7b-v2`, `arctic-embed-l` are 404 for this
#: account. A listed model is not a live model: `Embedder.probe()` asks.
NVIDIA_EMBED_MODEL = os.getenv("AAT_NVIDIA_EMBED_MODEL", "nvidia/nemotron-3-embed-1b")
NVIDIA_EMBED_BATCH = 50

EVENT_TYPES = ("earnings", "guidance", "analyst_rating", "m_and_a", "clinical", "regulatory",
               "contract", "product", "legal", "macro", "insider")

FEATURE_FIELDS = (
    "n_items_1d", "n_items_5d", "n_items_20d", "n_sources_5d", "coverage_baseline_90d",
    "attention_z", "novelty_5d", "source_independence", "sentiment_lex_5d", "sentiment_hits_5d",
    "event_type_counts_20d", "days_to_next_catalyst", "target_ratio", "n_target_notes_90d",
    "n_target_firms_90d", "rating_counts_mean", "rating_coverage",
    "ret_5d", "ret_20d", "drawdown_from_60d_high", "realised_vol_20d", "dollar_volume_20d",
)

# --------------------------------------------------------------------------- time


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    s = str(value)
    try:
        if len(s) == 10:
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _day(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def day_end(day: str) -> datetime:
    """The PIT bound: the last instant of `day`, UTC."""
    d = _day(day)
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)


def knowable_by(rows: Iterable[dict], bound: str) -> list[dict]:
    """Rows knowable by `bound`.

    `bound` is a DAY (`YYYY-MM-DD`, taken as its last instant) or a full
    timestamp (taken literally). The second form exists so a caller that knows
    the exact moment of its decision can say so instead of rounding up to
    midnight -- a 09:15 seal must not admit a 14:00 headline.
    """
    b = day_end(bound) if len(str(bound)) == 10 else _parse_ts(bound)
    if b is None:
        return list(rows)
    return [r for r in rows
            if (ts := _parse_ts(r.get("observed_at"))) is not None and ts <= b]


def observed_by(rows: Iterable[dict], day: str) -> list[dict]:
    """Only rows KNOWABLE by the end of `day`. The filter every count runs through."""
    return knowable_by(rows, str(day)[:10])


def _in_window(rows: Iterable[dict], day: str, n_days: int, *, end_offset: int = 0) -> list[dict]:
    """Rows observed in the `n_days` calendar days ending `end_offset` days before `day`
    (inclusive both ends). end_offset=0 -> the window ends on `day`."""
    end = _day(day) - timedelta(days=end_offset)
    start = end - timedelta(days=n_days - 1)
    out = []
    for r in rows:
        ts = _parse_ts(r.get("observed_at"))
        if ts is not None and start <= ts.date() <= end:
            out.append(r)
    return out


# ---------------------------------------------------------------------- publisher


def publisher(row: dict) -> str:
    """Who actually wrote it. `alpaca:benzinga` and `finnhub:Benzinga` are one."""
    src = str(row.get("source") or "")
    tail = src.split(":", 1)[1] if ":" in src else src
    tail = tail.strip().lower()
    if tail and tail not in ("news", "company-news", "calendar/earnings"):
        return tail
    url = str(row.get("url") or "")
    if url:
        host = urlparse(url).netloc.lower()
        host = re.sub(r"^www\.", "", host)
        if host:
            return host
    author = str((row.get("extra") or {}).get("author") or "").strip().lower()
    return author or (src.lower() or "unknown")


# ------------------------------------------------------------------------ lexicon

POSITIVE_WORDS = frozenset("""
able abundant accomplish accomplished achieve achieved achievement advance advanced advancement
advantage advantageous approval approve approved attain attractive beat beats beating benefit
benefited benefits best better boost boosted boosts breakthrough collaborate collaboration
confident constructive deliver delivered delivers despite dividend efficiency efficient enable
encouraging enhance enhanced enhancement enjoy excellent exceed exceeded exceeding exceeds
exceptional exciting expand expanded expansion favorable favourable gain gained gains good great
greater growth high higher highest improve improved improvement improving increase increased
increases innovate innovation innovative leader leading lucrative milestone momentum opportunity
opportunities optimistic outperform outperformed outperforming outperforms outstanding pleased
popular positive premier profit profitable profitability progress promising raise raised raises
raising rebound rebounded record recover recovered recovery resilient resolve resolved reward
rewarding robust smooth solid stable strength strengthen strengthened strong stronger strongest
succeed success successful successfully superior surge surged surges surpass surpassed sustain
sustainable top tremendous unlock upbeat upgrade upgraded upgrades upside upturn valuable win
winner winning wins won accretive buyback buybacks overweight bullish rally rallies rallied soar
soared soars jump jumped jumps climb climbed climbs approval approvals granted authorization
authorized cleared clearance fast-track priority designation partnership partnered expands
initiates initiated reinstates reiterates maintains
""".split())

NEGATIVE_WORDS = frozenset("""
abandon abandoned abandonment abnormal abuse accident accuse accused adverse adversely against
alarming allegation allegations allege alleged allegedly antitrust bad bankrupt bankruptcy
breach breached burden burdensome cancel canceled cancelled cancellation catastrophe caution
cautionary cautious cease challenge challenged challenges challenging charge charges claim
claims closure collapse collapsed complaint complaints concern concerned concerning concerns
conflict contraction crash crashed crisis critical criticism cut cuts cutting damage damaged
damages danger dangerous decline declined declines declining decrease decreased decreases
default defect defective deficiency deficit delay delayed delays delist delisted delisting
deteriorate deteriorated deterioration difficult difficulties difficulty diminish diminished
disappoint disappointed disappointing disappointment disaster discontinue discontinued
discontinuation dismiss dismissal disrupt disruption dispute doubt doubtful downgrade
downgraded downgrades downside downturn drag drop dropped drops erode erosion error exposure
fail failed failing fails failure fall fallen falling falls fell fine fined fines fraud
fraudulent halt halted halts harm harmful hurt idle impair impaired impairment inability
inadequate indict indicted indictment inefficiency inferior injunction insolvency insolvent
instability investigate investigation investigations lack lag lagged lagging lawsuit lawsuits
layoff layoffs liability liquidate liquidation litigation lose loses losing loss losses lost
low lower lowered lowers lowest miss missed misses missing mistake negative negatively obsolete
overdue penalty penalties plunge plunged plunges poor postpone postponed postponement pressure
pressures problem problematic problems probe prohibit rebuttal recall recalled recalls
recession redundancy reject rejected rejection restate restated restatement restructure
restructuring revoke revoked risk risks risky scandal scrutiny sell-off selloff serious setback
setbacks severe shortage shortfall shrink shrinking shut shutdown slash slashed slow slowdown
slower slowing sluggish slump slumped stagnant struggle struggled struggles subpoena suffer
suffered suffers suspend suspended suspension terminate terminated termination threat threaten
tumble tumbled tumbles turmoil uncertain uncertainty underperform underperformed
underperforming underperforms undermine unfavorable unfavourable unprofitable unsuccessful
volatile volatility warn warned warning warnings weak weaken weakened weaker weakness worse
worsen worsening worst writedown write-down writeoff write-off crl bearish dilution dilutive
offering underweight sink sinks sank sinking withdraw withdrawn withdrawal
""".split())

#: Phrases that carry the direction more reliably than either word alone. They
#: are scored BEFORE the unigrams and the matched span is removed so "raises
#: guidance" is not also read as neutral "guidance".
POSITIVE_PHRASES = ("raises guidance", "raised guidance", "raise guidance", "raises outlook",
                    "raised outlook", "raises forecast", "beats estimates", "beat estimates",
                    "beats expectations", "beat expectations", "above expectations",
                    "tops estimates", "topped estimates", "better than expected",
                    "better-than-expected", "price target raised", "raises price target",
                    "raised price target", "fda approval", "fda approves", "fda approved",
                    "clinical hold lifted", "lifts clinical hold", "positive topline",
                    "met primary endpoint", "meets primary endpoint", "upgrades to buy",
                    "upgraded to buy", "upgrades to outperform", "upgrades to overweight")
NEGATIVE_PHRASES = ("cuts guidance", "cut guidance", "lowers guidance", "lowered guidance",
                    "lowers outlook", "cuts outlook", "cuts forecast", "lowers forecast",
                    "misses estimates", "missed estimates", "misses expectations",
                    "missed expectations", "below expectations", "worse than expected",
                    "worse-than-expected", "price target cut", "cuts price target",
                    "lowers price target", "lowered price target", "complete response letter",
                    "clinical hold", "trading halt", "trading halted", "failed to meet",
                    "fails to meet", "missed primary endpoint", "did not meet",
                    "downgrades to sell", "downgraded to sell", "downgrades to hold",
                    "downgraded to hold", "downgrades to neutral", "downgrades to underperform",
                    "going concern", "chapter 11", "reverse split", "reverse stock split")
NEGATORS = frozenset(("not", "no", "never", "without", "fails", "failed", "unable", "n't", "neither", "nor"))
_TOKEN = re.compile(r"[a-z][a-z'\-]*")


def lexicon_score(text: str) -> tuple[float | None, int, int]:
    """(score in [-1, 1] or None, positive hits, negative hits)."""
    if not text:
        return None, 0, 0
    t = str(text).lower()
    pos = neg = 0
    for ph in POSITIVE_PHRASES:
        n = t.count(ph)
        if n:
            pos += n
            t = t.replace(ph, " ")
    for ph in NEGATIVE_PHRASES:
        n = t.count(ph)
        if n:
            neg += n
            t = t.replace(ph, " ")
    toks = _TOKEN.findall(t)
    for i, w in enumerate(toks):
        hit = 1 if w in POSITIVE_WORDS else (-1 if w in NEGATIVE_WORDS else 0)
        if not hit:
            continue
        if any(prev in NEGATORS for prev in toks[max(0, i - 3):i]):
            hit = -hit
        if hit > 0:
            pos += 1
        else:
            neg += 1
    if pos + neg == 0:
        return None, 0, 0
    return (pos - neg) / (pos + neg), pos, neg


# ------------------------------------------------------------------- event types

_EVENT_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("earnings", re.compile(r"(?i)\b(earnings|eps|q[1-4]\b|quarter(ly)?|fiscal (year|q)|results|revenue[s]?\b|"
                            r"top[- ]line|bottom[- ]line|profit report)")),
    ("guidance", re.compile(r"(?i)\b(guidance|outlook|forecast[s]?|guides?|raises? (its )?(full[- ]year|fy)|"
                            r"cuts? (its )?(full[- ]year|fy))\b")),
    ("analyst_rating", re.compile(r"(?i)\b(price target|pt\b|upgrade[sd]?|downgrade[sd]?|initiat(es|ed|ion)|"
                                  r"reiterat(es|ed)|maintains|overweight|underweight|outperform|underperform|"
                                  r"analyst[s]?|rating\b|buy rating|sell rating)")),
    ("m_and_a", re.compile(r"(?i)\b(acqui(re|res|red|sition)|merger|merge[sd]?|takeover|buyout|"
                           r"to buy\b|deal to acquire|tender offer|combination|spin[- ]?off)")),
    ("clinical", re.compile(r"(?i)\b(phase [1-3]|phase (i|ii|iii)\b|clinical|trial[s]?\b|topline|top-line|"
                            r"readout|endpoint|enrol+ment|dosing|patients?|efficacy|pdufa|crl\b|"
                            r"complete response letter|data (readout|update)|cohort|ind\b)")),
    ("regulatory", re.compile(r"(?i)\b(fda|ema\b|sec\b|ftc|doj|regulator[sy]?|approv(al|es|ed)|"
                              r"clearance|authoriz(ation|ed)|tariff[s]?|export (control|ban)|"
                              r"sanction[s]?|antitrust|licen[cs]e)")),
    ("contract", re.compile(r"(?i)\b(contract|award(ed|s)?\b|order[s]? (from|for|worth)|agreement|"
                            r"partnership|partners? with|collaborat(ion|es)|supply deal|multi[- ]year|"
                            r"purchase order|selected by)")),
    ("product", re.compile(r"(?i)\b(launch(es|ed)?|unveil[s]?|introduc(es|ed)|debut[s]?|new (chip|product|"
                           r"platform|model|device)|roll[s]? out|rollout|release[sd]? (its|new|the)|"
                           r"announces? (new|the) )")),
    ("legal", re.compile(r"(?i)\b(lawsuit|sues?\b|sued|litigation|class action|settle(s|d|ment)|"
                         r"court|judge|jury|verdict|patent (dispute|infringement)|injunction|"
                         r"investor alert|deadline reminder|securities fraud)")),
    ("macro", re.compile(r"(?i)\b(fed\b|fomc|rate (cut|hike)|interest rates?|inflation|cpi\b|"
                         r"nonfarm|payrolls|jobs report|gdp\b|treasury yields?|recession|tariff war|"
                         r"trade war|geopolitic)")),
    ("insider", re.compile(r"(?i)\b(insider|form 4|ceo (buys|sells|sold|bought)|director (buys|sells|sold|bought)|"
                           r"10b5-1|stake\b|13[dg]\b|activist|sells? shares|buys? shares|open market purchase)")),
)


def classify_title(title: str) -> list[str]:
    """Event types a headline carries. Order follows EVENT_TYPES; may be empty."""
    if not title:
        return []
    out = [name for name, pat in _EVENT_PATTERNS if pat.search(title)]
    return out


# ---------------------------------------------------------------------- vectors


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(str(text).lower())


class Embedder:
    """Titles -> unit vectors, from NVIDIA when live, else TF-IDF. Says which.

    `Embedder.tfidf()` never opens a socket. `Embedder.nvidia()` will, and is
    wired only by the script. The `backend` attribute is what the receipt
    prints; a novelty number without it is a number from an unknown ruler.
    """

    def __init__(self, backend: str, fn: Callable[[list[str]], Any] | None = None,
                 model: str = "") -> None:
        self.backend = backend
        self.model = model
        self._fn = fn
        self.calls = 0
        self.n_embedded = 0

    # ---- TF-IDF, pure numpy -------------------------------------------------
    @classmethod
    def tfidf(cls) -> "Embedder":
        return cls("tfidf", None, "tfidf-unigram+bigram")

    @staticmethod
    def _tfidf_matrix(texts: list[str]):
        docs = []
        for t in texts:
            toks = _tokens(t)
            grams = toks + [a + "_" + b for a, b in zip(toks, toks[1:])]
            docs.append(Counter(grams))
        df: Counter = Counter()
        for d in docs:
            df.update(d.keys())
        vocab = {w: i for i, w in enumerate(sorted(df))}
        n = max(len(docs), 1)
        idf = {w: math.log((1 + n) / (1 + c)) + 1.0 for w, c in df.items()}
        m = np.zeros((len(docs), len(vocab)), dtype=np.float32)
        for r, d in enumerate(docs):
            for w, c in d.items():
                m[r, vocab[w]] = (1.0 + math.log(c)) * idf[w]
        norms = np.linalg.norm(m, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return m / norms

    # ---- NVIDIA -------------------------------------------------------------
    @classmethod
    def nvidia(cls, *, model: str = NVIDIA_EMBED_MODEL, base_url: str | None = None,
               key: str | None = None) -> "Embedder":
        from alpha.sources.http import SourceRefusal
        from alpha.spend import llm_post

        base = (base_url or os.getenv("AAT_NVIDIA_BASE_URL") or "https://integrate.api.nvidia.com/v1").rstrip("/")
        key = (key or os.getenv("AAT_NVIDIA_API_KEY", "")).strip()
        if not key:
            raise RuntimeError("AAT_NVIDIA_API_KEY is not set")

        def call(texts: list[str]):
            body = {"model": model, "input": texts, "input_type": "passage",
                    "encoding_format": "float", "truncate": "END"}
            why = ("Decides the novelty_5d feature of the news panel: a repeated headline "
                   "is ranked as no new information, a genuinely new one is ranked as a "
                   "state change; without vectors the feature is built from TF-IDF instead.")
            for attempt in range(6):
                try:
                    data, _ = llm_post(base + "/embeddings", body, headers={"Authorization": f"Bearer {key}"},
                                       caller="features.embed", why=why, timeout=90.0)
                    break
                except SourceRefusal as exc:
                    # 429 / 5xx on the free tier is a pause, not a verdict on the model.
                    transient = any(code in str(exc) for code in ("HTTP 429", "HTTP 502", "HTTP 503", "HTTP 504", "timed out"))
                    if attempt == 5 or not transient:
                        raise
                    time.sleep(3.0 * (attempt + 1))
            rows = sorted(data["data"], key=lambda r: r["index"])
            return [r["embedding"] for r in rows]

        return cls("nvidia", call, model)

    def probe(self) -> bool:
        if self._fn is None:
            return True
        try:
            v = self._fn(["probe"])
            return bool(v) and len(v[0]) > 8
        except Exception:                                              # noqa: BLE001
            return False

    def encode(self, texts: list[str]):
        """(n, d) unit-norm float32 matrix, rows aligned with `texts`."""
        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        if self._fn is None:
            return self._tfidf_matrix(list(texts))
        out = []
        for i in range(0, len(texts), NVIDIA_EMBED_BATCH):
            batch = [str(t)[:2000] or "empty" for t in texts[i:i + NVIDIA_EMBED_BATCH]]
            out.extend(self._fn(batch))
            self.calls += 1
            self.n_embedded += len(batch)
        m = np.asarray(out, dtype=np.float32)
        norms = np.linalg.norm(m, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return m / norms


def title_key(text: str) -> str:
    return hashlib.sha1(str(text).strip().lower().encode("utf-8")).hexdigest()[:16]


class NoveltyIndex:
    """Per-symbol title vectors + observed dates, so the per-day novelty is a slice.

    Build once per symbol over ALL of its titles (PIT is applied when a day is
    asked for, not at build time -- a vector is not information about a
    return, and a title's presence in the matrix leaks nothing until a
    date-bounded query includes it).
    """

    def __init__(self, rows: Sequence[dict], embedder: Embedder, *, cache: dict | None = None) -> None:
        self.embedder = embedder
        titles, dates = [], []
        for r in rows:
            t = str(r.get("title") or "").strip()
            ts = _parse_ts(r.get("observed_at"))
            if t and ts is not None:
                titles.append(t)
                dates.append(ts.date())
        self.titles = titles
        self.dates = dates
        if not titles:
            self.matrix = None
            return
        if cache is not None and embedder.backend != "tfidf":
            keys = [title_key(t) for t in titles]
            missing = sorted({k for k, t in zip(keys, titles) if k not in cache})
            if missing:
                by_key = {title_key(t): t for t in titles}
                vecs = embedder.encode([by_key[k] for k in missing])
                for k, v in zip(missing, vecs):
                    cache[k] = v
            self.matrix = np.stack([cache[k] for k in keys]).astype(np.float32)
        else:
            self.matrix = embedder.encode(titles)

    def novelty(self, day: str, *, recent_days: int = 5, prior_days: int = 60) -> float | None:
        if self.matrix is None:
            return None
        d = _day(day)
        r0 = d - timedelta(days=recent_days - 1)
        p0 = r0 - timedelta(days=prior_days)
        recent = [i for i, dt in enumerate(self.dates) if r0 <= dt <= d]
        prior = [i for i, dt in enumerate(self.dates) if p0 <= dt < r0]
        if not recent or not prior:
            return None
        sims = self.matrix[recent] @ self.matrix[prior].T
        best = sims.max(axis=1)
        return float(np.clip(1.0 - best, 0.0, 1.0).mean())


# --------------------------------------------------------------------- the row


def _bars_upto(bars: Sequence[dict] | None, day: str) -> list[dict]:
    if not bars:
        return []
    d = str(day)[:10]
    return [b for b in bars if str(b.get("t") or "")[:10] <= d]


def price_context(bars: Sequence[dict] | None, day: str) -> dict[str, float | None]:
    """The five price fields from Alpaca daily bars ending on `day` (inclusive).

    The last bar must BE `day` -- a stale last bar would report yesterday's
    context under today's date."""
    out: dict[str, float | None] = {"ret_5d": None, "ret_20d": None, "drawdown_from_60d_high": None,
                                    "realised_vol_20d": None, "dollar_volume_20d": None}
    hist = _bars_upto(bars, day)
    if not hist or str(hist[-1].get("t") or "")[:10] != str(day)[:10]:
        return out
    closes = [float(b["c"]) for b in hist if b.get("c")]
    vols = [float(b.get("v") or 0.0) for b in hist if b.get("c")]
    n = len(closes)
    if n >= 6 and closes[-6] > 0:
        out["ret_5d"] = closes[-1] / closes[-6] - 1.0
    if n >= 21 and closes[-21] > 0:
        out["ret_20d"] = closes[-1] / closes[-21] - 1.0
        rets = [math.log(closes[i] / closes[i - 1]) for i in range(n - 20, n) if closes[i - 1] > 0]
        if len(rets) >= 15:
            out["realised_vol_20d"] = st.pstdev(rets) * math.sqrt(252.0)
        out["dollar_volume_20d"] = st.mean(c * v for c, v in zip(closes[-20:], vols[-20:]))
    if n >= 60:
        hi = max(closes[-60:])
        if hi > 0:
            out["drawdown_from_60d_high"] = closes[-1] / hi - 1.0
    return out


def rating_from_panel(rec: dict | None) -> tuple[float | None, int | None]:
    if not rec:
        return None, None
    from alpha import analyst_targets
    got = analyst_targets.consensus_rating(rec)
    return (got[0], got[1]) if got else (None, None)


def daily_features(symbol: str, day: str, corpus_rows: Sequence[dict],
                   baseline_rows: Sequence[dict] | None = None, *,
                   bars: Sequence[dict] | None = None, rating_rec: dict | None = None,
                   novelty: NoveltyIndex | Callable[[str], float | None] | None = None,
                   close_source: str = "alpaca_daily_bar_close_sip_adj_all",
                   future_known_by: str | None = None) -> dict[str, Any]:
    """One numeric row for (symbol, day). See the module docstring for each field.

    `corpus_rows`   rows about `symbol` (any tense, any observed_at -- filtered here).
    `baseline_rows` rows used for the 90-day coverage baseline; defaults to
                    `corpus_rows`. Pass a wider history when `corpus_rows` was
                    cut to a short window.
    `bars`          Alpaca daily bars (dicts with t/o/h/l/c/v), any span.
    `rating_rec`    Finnhub recommendation counts captured ON OR BEFORE `day`.
    `novelty`       a `NoveltyIndex` or callable(day) -> float|None.
    `future_known_by`
                    Separate knowledge bound for FORWARD-DATED rows (the
                    catalyst diary). Defaults to `day`, which is what a
                    historical panel must use.

    WHY FORWARD ROWS NEED THEIR OWN BOUND (found 2026-08-30, and it had made
    clause (d) of the selection rule permanently inert)
    ---------------------------------------------------------------------
    `day` here is the last CLOSED session, because the free SIP plan refuses
    recent bars -- on 2026-08-30 that was 2026-08-28. The forward catalyst
    calendar, however, is pulled TODAY, so its rows carry `observed_at`
    2026-08-29/30. One shared bound therefore filtered out every catalyst:
    `days_to_next_catalyst` was None for MU even though the corpus held its
    2026-09-21 earnings date, and every rule reading "a dated catalyst inside
    N sessions" silently evaluated against nothing.

    Two clocks, two bounds. For BACKWARD news the bound must be `day` -- a
    headline published after the decision cannot enter it, and that is the
    whole of PIT discipline. For a FORWARD-dated row the question is different:
    not "had it happened?" but "did we KNOW the date?", and at a 09:15 seal we
    demonstrably do. Passing the seal instant is therefore not lookahead; it is
    the honest bound for a diary entry.

    The default stays `day` precisely so the historical panel is unchanged: a
    backtest that let today's calendar into a 2025 row WOULD be lookahead, and
    a caller has to ask for the other behaviour by name.
    """
    sym = str(symbol).upper()
    day = str(day)[:10]
    pit = observed_by(corpus_rows, day)
    base_pit = observed_by(baseline_rows, day) if baseline_rows is not None else pit
    past = [r for r in pit if r.get("tense") != "future"]
    fut_src = pit if future_known_by is None else knowable_by(corpus_rows, future_known_by)
    future = [r for r in fut_src if r.get("tense") == "future"]
    base_past = [r for r in base_pit if r.get("tense") != "future"]

    f: dict[str, Any] = {k: None for k in FEATURE_FIELDS}
    f["symbol"], f["day"] = sym, day

    w1, w5, w20 = _in_window(past, day, 1), _in_window(past, day, 5), _in_window(past, day, 20)
    has_history = bool(base_past)
    if has_history:
        f["n_items_1d"], f["n_items_5d"], f["n_items_20d"] = len(w1), len(w5), len(w20)
        pubs = {publisher(r) for r in w5}
        f["n_sources_5d"] = len(pubs)
        if w5:
            f["source_independence"] = len(pubs) / len(w5)
        base = _in_window(base_past, day, 90, end_offset=5)
        earliest = min((_parse_ts(r.get("observed_at")) for r in base_past), default=None)
        base_start = _day(day) - timedelta(days=94)
        if base or (earliest is not None and earliest.date() < base_start):
            lam = len(base) / 90.0
            f["coverage_baseline_90d"] = lam
            lam_f = max(lam, 1.0 / 90.0)
            f["attention_z"] = (len(w5) - 5.0 * lam_f) / math.sqrt(5.0 * lam_f)

    if w5:
        text = " . ".join(f"{r.get('title') or ''} . {r.get('body') or ''}" for r in w5)
        score, pos, neg = lexicon_score(text)
        f["sentiment_lex_5d"] = score
        f["sentiment_hits_5d"] = pos + neg if score is not None else 0
    if w20:
        counts = {k: 0 for k in EVENT_TYPES}
        for r in w20:
            for k in classify_title(str(r.get("title") or "")):
                counts[k] += 1
        f["event_type_counts_20d"] = counts

    if novelty is not None:
        f["novelty_5d"] = novelty.novelty(day) if isinstance(novelty, NoveltyIndex) else novelty(day)

    d = _day(day)
    horizons = []
    for r in future:
        if sym not in {str(s).upper() for s in (r.get("symbols") or [])}:
            continue
        eff = _parse_ts(r.get("effective_at"))
        if eff is not None and eff.date() > d:
            horizons.append((eff.date() - d).days)
    if horizons:
        f["days_to_next_catalyst"] = min(horizons)

    # analyst targets: Opus's headline extraction, PIT via observed_at
    news90 = [r for r in _in_window(past, day, 90) if r.get("kind") == "news"]
    if news90:
        from alpha import analyst_targets
        pnl = analyst_targets.panel(sym, as_of=day_end(day).isoformat(), rows=news90)
        f["n_target_notes_90d"] = len(pnl.targets)
        f["n_target_firms_90d"] = pnl.n_firms
        hist = _bars_upto(bars, day)
        close = float(hist[-1]["c"]) if hist and str(hist[-1].get("t"))[:10] == day and hist[-1].get("c") else None
        if pnl.n_firms >= analyst_targets.MIN_FIRMS and close:
            f["target_ratio"] = pnl.upside_ratio(close)
    f["rating_counts_mean"], f["rating_coverage"] = rating_from_panel(rating_rec)

    f.update(price_context(bars, day))
    f["close_source"] = close_source
    f["derivable"] = {k: f.get(k) is not None for k in FEATURE_FIELDS}
    return f


def numeric_fields(row: dict) -> dict[str, float]:
    """Flatten a feature row to the numeric columns the IC harness ranks on."""
    out: dict[str, float] = {}
    for k in FEATURE_FIELDS:
        v = row.get(k)
        if k == "event_type_counts_20d":
            if isinstance(v, dict):
                for et, c in v.items():
                    out[f"ev_{et}_20d"] = float(c)
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v)):
            out[k] = float(v)
    return out


# ----------------------------------------------------------------- rank IC


def _rank(values):
    a = np.asarray(values, dtype=np.float64)
    order = a.argsort()
    ranks = np.empty(len(a), dtype=np.float64)
    ranks[order] = np.arange(1, len(a) + 1, dtype=np.float64)
    # average ties
    sorted_vals = a[order]
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and sorted_vals[j + 1] == sorted_vals[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + j + 2) / 2.0
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) < 3 or len(x) != len(y):
        return None
    rx, ry = _rank(x), _rank(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def rank_ic(feature: Sequence[float], forward: Sequence[float], blocks: Sequence[str], *,
            n_boot: int = 500, ci: float = 0.90, seed: int = 7) -> dict[str, Any]:
    """Spearman IC with a block bootstrap over `blocks` (e.g. 'YYYY-MM').

    Months are resampled with replacement and the IC recomputed on the pooled
    resample; the CI is the (5th, 95th) percentile at ci=0.90. Months are the
    block because the returns overlap inside one and a row-wise bootstrap would
    count each event several times.
    """
    x = np.asarray(feature, dtype=np.float64)
    y = np.asarray(forward, dtype=np.float64)
    b = np.asarray(list(blocks))
    n = len(x)
    ic = spearman(x, y) if n >= 3 else None
    out = {"ic": ic, "n": int(n), "n_blocks": int(len(set(b.tolist()))), "ci_lo": None, "ci_hi": None}
    if ic is None or out["n_blocks"] < 2:
        return out
    rng = np.random.default_rng(seed)
    uniq = sorted(set(b.tolist()))
    idx_by = {u: np.flatnonzero(b == u) for u in uniq}
    boots = []
    for _ in range(n_boot):
        pick = rng.choice(len(uniq), size=len(uniq), replace=True)
        idx = np.concatenate([idx_by[uniq[p]] for p in pick])
        v = spearman(x[idx], y[idx])
        if v is not None:
            boots.append(v)
    if boots:
        lo, hi = (1 - ci) / 2 * 100, (1 + ci) / 2 * 100
        out["ci_lo"] = float(np.percentile(boots, lo))
        out["ci_hi"] = float(np.percentile(boots, hi))
        out["n_boot"] = len(boots)
    return out


def dumps(row: dict) -> str:
    return json.dumps(row, ensure_ascii=False, default=float)
