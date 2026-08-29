"""OBSERVATION_CORPUS_v1 -- the append-only memory the digest never had.

    from alpha.sources import corpus
    corpus.append(corpus.Observation(...))          # one fact, deduped by uid
    corpus.read(since="2026-02-01", kinds=("news",))
    corpus.stats()

WHY THIS EXISTS
===============
Measured 2026-08-29 (`docs/ROADMAP_2026-08-29_WEEKEND_TO_MONDAY.md` §7): the
Featherless digest ran over 156 names and 394 headlines and **not one of
Murat's twenty names received a bet**, because none of them had an Alpaca
headline in the last 48 hours. The pipe could only ever see what Benzinga
wrote about this week. It re-discovered this week's earnings prints and never
SLDP, KYTX or AARD.

Two things were missing, and they are the same thing in opposite directions:

- **BACKWARD** -- there was no memory. Every digest started from an empty
  48-hour window, so a name's *story* (the clinical hold in March, the
  reverse split in June, the guidance cut that made the drawdown) did not
  exist. `premarket_digest` writes `state/premarket/<day>.json` and nothing
  ever reads yesterday's.
- **FORWARD** -- there was no diary. Murat's selection rule requires "a NAMED
  catalyst inside 12 months" (roadmap §3(d)), and the engine held no dated
  future events at all beyond the earnings window.

This module is the store both directions write into. It is deliberately dumb:
a schema, an append, a dedupe and a read. Everything clever happens in the
collectors above it and the digest beside it.

POINT-IN-TIME IS TWO TIMESTAMPS, NOT ONE
========================================
Every row carries both, and conflating them is the bug this schema exists to
prevent:

- `effective_at` -- when the fact became TRUE (the quarter it describes, the
  date the trial reads out, the day the 8-K event occurred);
- `observed_at`  -- when the fact became KNOWABLE to us (publication).

A backtest may condition only on rows whose `observed_at <= t`. Taiwan's July
export figure is a fact about July that did not EXIST until 7 August
(`registry.py`); a forward catalyst dated 2026-11-20 is *observed* today and
*effective* in November. `read(as_of=...)` filters on `observed_at`, which is
the only filter that cannot leak. Filtering on `effective_at` would read the
future and improve every number.

APPEND-ONLY, AND WHY DEDUPE IS BY CONTENT
=========================================
Re-running a backfill must be free and must not double-count. `uid` is a hash
of (source, kind, symbols, title, effective_at) -- deliberately NOT of the
body, because wires silently re-edit summaries and a body-keyed hash would
re-admit the same headline every run. The index is loaded once per process
and consulted per append, so a second run over the same year appends nothing
and says so.

A row is NEVER overwritten. Where a source restates (`revision_policy` in the
registry), the restatement is a NEW row with a later `observed_at`, and both
vintages survive. Overwriting is how point-in-time discipline dies silently.

NO LLM LIVES HERE
=================
Collectors fetch, this stores, the digest reasons. A module that both fetched
and interpreted is how `explain_move.py` shipped a bug every caller inherited.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

ROOT = Path(__file__).resolve().parent.parent.parent
STATE = Path(os.getenv("AAT_STATE_DIR", str(ROOT / "state")))
CORPUS = STATE / "corpus"
OBS_DIR = CORPUS / "observations"

#: What a row IS. Ranked loosely by how directly it bears on a price.
KINDS = (
    "news",         # a wire or outlet wrote something
    "filing",       # SEC 8-K / 10-Q / 13D / Form 4
    "earnings",     # a report, past or scheduled
    "macro",        # a scheduled statistical release (NFP, CPI, FOMC)
    "clinical",     # a trial milestone (readout, PDUFA, completion)
    "analyst",      # a target or rating, level or revision
    "corporate",    # split, offering, index add, M&A
)

#: A row is either something that HAPPENED or something SCHEDULED to happen.
#: The digest treats them differently and a mixed store that cannot say which
#: is a store that will quietly backtest the future.
TENSES = ("past", "future")


class CorpusRefusal(RuntimeError):
    """The row will not be stored, and the reason is stated."""


@dataclass(frozen=True)
class Observation:
    """One fact, with the provenance needed to decide whether to believe it."""

    kind: str
    tense: str
    title: str
    source: str
    source_type: str                    # registry.SOURCE_TYPES
    observed_at: str                    # ISO8601 UTC -- when it became KNOWABLE
    effective_at: str                   # ISO8601 date -- when it is/was TRUE
    symbols: tuple[str, ...] = ()
    body: str = ""
    url: str = ""
    independence_group: str = ""        # who is really speaking (registry.py)
    source_verified: bool = False       # did WE confirm the date at the issuer?
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise CorpusRefusal(f"unknown kind {self.kind!r}; one of {KINDS}")
        if self.tense not in TENSES:
            raise CorpusRefusal(f"unknown tense {self.tense!r}; one of {TENSES}")
        if not self.title.strip():
            raise CorpusRefusal("an observation with no title is not an observation")
        if not self.observed_at or not self.effective_at:
            raise CorpusRefusal(
                f"{self.title[:40]!r}: both observed_at and effective_at are required; "
                "a row with one timestamp cannot be filtered without leaking")

    @property
    def uid(self) -> str:
        payload = "|".join([self.source, self.kind, ",".join(sorted(self.symbols)),
                            self.title.strip().lower()[:180], self.effective_at[:10]])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["symbols"] = list(self.symbols)
        row["uid"] = self.uid
        return row


def _shard(effective_at: str) -> Path:
    """One file per calendar month of EFFECTIVE date -- so a forward catalyst
    lands in the month it happens and a backfill lands in the month it
    described. Reading "what is coming in November" is then one file."""
    return OBS_DIR / f"{effective_at[:7]}.jsonl"


def _index_path() -> Path:
    return CORPUS / "uid_index.json"


_INDEX: set[str] | None = None


def _index() -> set[str]:
    global _INDEX
    if _INDEX is None:
        p = _index_path()
        try:
            _INDEX = set(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else set()
        except (json.JSONDecodeError, OSError):
            # A corrupt index must not silently re-admit a year of duplicates.
            # Rebuild it from the shards, which are the truth.
            _INDEX = {r["uid"] for r in read() if "uid" in r}
    return _INDEX


def flush_index() -> int:
    CORPUS.mkdir(parents=True, exist_ok=True)
    idx = sorted(_index())
    _index_path().write_text(json.dumps(idx), encoding="utf-8")
    return len(idx)


def rebuild_index() -> int:
    """Re-derive the dedupe index from the shards, which are the only truth.

    THE INDEX IS NOT CONCURRENCY-SAFE AND IS NOT MEANT TO BE. Each process
    holds it in memory and writes the whole file at `flush_index()`, so two
    collectors running at once end with last-writer-wins: the loser's uids
    vanish from the index while its ROWS remain on disk, and the next run
    happily appends them a second time.

    The shards themselves survive that (an append of one line is safe), so the
    repair is cheap and total. Run this after any deliberate parallel
    collection, and prefer running collectors one at a time.
    """
    global _INDEX
    _INDEX = {r["uid"] for r in read() if "uid" in r}
    return flush_index()


def append(obs: Observation) -> bool:
    """Store one observation. Returns False if it was already known (not an error)."""
    idx = _index()
    if obs.uid in idx:
        return False
    OBS_DIR.mkdir(parents=True, exist_ok=True)
    with _shard(obs.effective_at).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obs.to_row(), ensure_ascii=False) + "\n")
    idx.add(obs.uid)
    return True


def append_many(rows: Sequence[Observation]) -> tuple[int, int]:
    """(newly stored, already known). Flushes the index once at the end."""
    new = sum(1 for o in rows if append(o))
    flush_index()
    return new, len(rows) - new


def read(*, since: str | None = None, until: str | None = None,
         as_of: str | None = None, kinds: Sequence[str] | None = None,
         tense: str | None = None, symbols: Sequence[str] | None = None) -> list[dict[str, Any]]:
    """Rows matching the filters, oldest first.

    `since`/`until` bound `effective_at` (what window of the world).
    `as_of` bounds `observed_at` (what we could have KNOWN by then) -- this is
    the point-in-time filter, and the only one safe for a backtest.
    """
    want = set(kinds) if kinds else None
    syms = {s.upper() for s in symbols} if symbols else None
    out: list[dict[str, Any]] = []
    if not OBS_DIR.exists():
        return out
    for shard in sorted(OBS_DIR.glob("*.jsonl")):
        month = shard.stem
        if since and month < since[:7]:
            continue
        if until and month > until[:7]:
            continue
        for line in shard.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if want and row.get("kind") not in want:
                continue
            if tense and row.get("tense") != tense:
                continue
            if since and str(row.get("effective_at", ""))[:10] < since[:10]:
                continue
            if until and str(row.get("effective_at", ""))[:10] > until[:10]:
                continue
            if as_of and str(row.get("observed_at", ""))[:10] > as_of[:10]:
                continue
            if syms and not (syms & {s.upper() for s in row.get("symbols") or []}):
                continue
            out.append(row)
    out.sort(key=lambda r: (str(r.get("effective_at", "")), str(r.get("observed_at", ""))))
    return out


def symbols_covered(**kw: Any) -> dict[str, int]:
    """How many rows each symbol has. The coverage gap, as a number."""
    counts: dict[str, int] = {}
    for row in read(**kw):
        for s in row.get("symbols") or []:
            counts[s.upper()] = counts.get(s.upper(), 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def stats() -> dict[str, Any]:
    rows = read()
    by_kind: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for r in rows:
        by_kind[r.get("kind", "?")] = by_kind.get(r.get("kind", "?"), 0) + 1
        by_source[r.get("source", "?")] = by_source.get(r.get("source", "?"), 0) + 1
    eff = [str(r.get("effective_at", ""))[:10] for r in rows if r.get("effective_at")]
    return {
        "n_observations": len(rows),
        "n_symbols": len(symbols_covered()),
        "by_kind": dict(sorted(by_kind.items(), key=lambda kv: -kv[1])),
        "by_source": dict(sorted(by_source.items(), key=lambda kv: -kv[1])),
        "effective_span": [min(eff), max(eff)] if eff else None,
        "n_future": sum(1 for r in rows if r.get("tense") == "future"),
        "n_verified": sum(1 for r in rows if r.get("source_verified")),
        "shards": sorted(p.name for p in OBS_DIR.glob("*.jsonl")) if OBS_DIR.exists() else [],
    }


def purge_source(prefix: str, *, reason: str, dry_run: bool = True) -> dict[str, Any]:
    """Remove rows a COLLECTION BUG wrote, and leave a receipt saying so.

    Append-only is a rule about OBSERVATIONS. A row that a broken collector
    invented was never an observation -- on 2026-08-29 a one-letter endpoint
    slip (`/releases/dates` vs `/release/dates`) stamped every macro date with
    the wrong release's name, so the store held 'FOMC Press Release' on a
    Saturday. Keeping that to honour append-only would be honouring the letter
    of the rule against its purpose, which is that the record be TRUE.

    What must not happen is a silent deletion, so this writes
    `state/corpus/purges.jsonl` with the reason, the count and a sample, and
    defaults to `dry_run=True` -- the caller has to mean it.
    """
    removed, kept_total, sample = 0, 0, []
    for shard in sorted(OBS_DIR.glob("*.jsonl")) if OBS_DIR.exists() else []:
        kept: list[str] = []
        for line in shard.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("source", "")).startswith(prefix):
                removed += 1
                if len(sample) < 5:
                    sample.append({"effective_at": row.get("effective_at"), "title": row.get("title")})
                continue
            kept.append(line)
            kept_total += 1
        if not dry_run:
            if kept:
                shard.write_text("\n".join(kept) + "\n", encoding="utf-8")
            else:
                shard.unlink()
    out = {"prefix": prefix, "reason": reason, "removed": removed, "kept": kept_total,
           "sample": sample, "dry_run": dry_run, "at": utcnow()}
    if not dry_run and removed:
        CORPUS.mkdir(parents=True, exist_ok=True)
        with (CORPUS / "purges.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(out, ensure_ascii=False) + "\n")
        # The uid index must be rebuilt from the shards, or the purged rows
        # stay "known" and the corrected collector re-adds nothing.
        global _INDEX
        _INDEX = {r["uid"] for r in read() if "uid" in r}
        flush_index()
    return out


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def iter_months(start: str, end: str) -> Iterator[tuple[str, str]]:
    """[(month_start, month_end_exclusive)] ISO dates, for paging a year of news."""
    y, m = int(start[:4]), int(start[5:7])
    while f"{y:04d}-{m:02d}" <= end[:7]:
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        yield f"{y:04d}-{m:02d}-01", f"{ny:04d}-{nm:02d}-01"
        y, m = ny, nm
