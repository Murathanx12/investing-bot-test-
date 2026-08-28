"""TRANSCRIPT_DIGEST_v1 -- the firm's own words, on declared axes, before the open.

    AAT_ACCOUNT_ROLE=staging python -m scripts.transcript_digest                 # tonight's printers
    AAT_ACCOUNT_ROLE=staging python -m scripts.transcript_digest --symbols S ESTC RBRK
    AAT_ACCOUNT_ROLE=staging python -m scripts.transcript_digest --dry            # fetch, no LLM

WHY THIS EXISTS
===============
Bigdata.com is out of credits and WRDS IBES lags by weeks (0 rows since
2026-08-20 on 28 Aug). Measured the same night: Alpaca's free news feed
(Benzinga) carries the FULL earnings-call transcript within ~90 minutes of the
call -- 58,149 characters for MRVL -- plus the guidance bullets, and it does so
for small caps (ESTC, RBRK, S all had "Full Earnings Call Transcript" items).
That is the analysis, not just the data, and it is the one source on hand that
is not about the eleven mega-caps.

WHAT IT PRODUCES, AND WHAT IT MUST NOT
======================================
An EXPECTATION PACKET per name: `state/expectations/<date>/<SYM>.json` with the
declared fields below, the source ids that fed it, the model and prompt hash,
and the after-hours move seen on the feed. It is expectation data for the human
thesis wire (`scripts.thesis`) and for a later claim-matrix comparison. It
places nothing, sizes nothing, and it is not a forecast: a model reading a
transcript knows what management SAID, not what the market had priced.
`already_priced_note` exists so the reader is forced to compare the two.

FIELDS ARE DECLARED, NUMBERS ARE BOUNDED, LANGUAGE IS PINNED
============================================================
Same contract as `alpha/narrative/extract.py`: the model is asked for values on
named axes with ranges and a JSON object, in English; a non-Latin reply is
refused, not repaired. Every call goes through `alpha.spend.llm_post` so the
ledger says what the money was asked to decide.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from alpha import config
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal
from alpha.spend import llm_post

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
PRICE_IN, PRICE_OUT = 0.27, 1.10          # USD per 1M tokens, cache miss
STATE = Path(os.getenv("AAT_LEDGER_DIR") or "state")

#: What the packet must contain. (lo, hi, description) for numbers; None for text.
FIELDS: dict[str, tuple[Any, Any, str]] = {
    "guide_vs_prior": (None, None, "one of raised|lowered|maintained|initiated|none -- the forward guide against the company's own prior guide"),
    "guide_vs_street_hint": (None, None, "one of above|below|inline|unknown -- ONLY if the text itself compares guidance to consensus/estimates; otherwise unknown"),
    "headline_vs_estimates": (None, None, "one of beat|miss|inline|unknown -- the reported quarter against estimates, ONLY if the text says so"),
    "tone": (-1, 1, "management tone toward the next two quarters, -1 defensive/cautious +1 confident/expansive"),
    "surprise": (0, 1, "how much of what was said would surprise a reader of the previous quarter's call"),
    "direction_claim": (None, None, "one of up|down|none -- the direction the FUNDAMENTAL content argues for over the next 3 sessions, independent of the price reaction"),
    "expected_move": (0, 0.3, "absolute fraction of spot the content alone would justify over 3 sessions; 0 if none"),
    "confidence": (0, 1, "how confident the reading is; low when the transcript is partial or hedged"),
    "key_numbers": (None, None, "list of up to 6 short strings: the numbers that matter, each with its comparator (e.g. 'FY27 rev growth guide 32% vs prior 28%')"),
    "bottleneck_or_supplier_mentions": (None, None, "list of up to 6 short strings: named suppliers, customers, capacity constraints, components -- the causal graph inputs"),
    "observable_in_3_sessions": (None, None, "one sentence: what would be observable within three sessions if the bullish/bearish reading is right"),
    "falsifier": (None, None, "one sentence: what observation would make the direction_claim wrong"),
    "already_priced_note": (None, None, "one sentence comparing direction_claim with the after-hours move given in the prompt: agree / market moved more / market moved the other way"),
    "summary": (None, None, "two sentences, what management said and what is uncertain"),
}

SYSTEM = (
    "You are an equity research reader. You are given an earnings-call transcript or "
    "earnings headlines for one company and asked for values on DECLARED fields. You "
    "must not recommend a trade. Use only the text provided; where the text does not "
    "say, answer unknown/none/0 rather than guessing. Answer ONLY with a single JSON "
    "object, in English, no prose, no markdown fences."
)

TRANSCRIPT_RE = re.compile(r"transcript", re.I)
GUIDE_RE = re.compile(r"guid|outlook|sees|expects|raises|lowers|reaffirm|forecast", re.I)


def _strip_html(s: str) -> str:
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def _non_latin_share(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if ord(c) > 0x024F) / len(letters)


def fetch_items(client, symbol: str, *, days: int = 3) -> list[dict[str, Any]]:
    """Every Benzinga item on the name in the window, WITH content."""
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {"symbols": symbol, "limit": 50, "sort": "desc", "start": start, "include_content": "true"}
    data = client._request("GET", "/v1beta1/news", base=config.data_url(), params=params)
    return (data or {}).get("news") or []


def select_text(items: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]], str]:
    """The transcript if there is one, else the guidance/earnings headlines. Returns
    (text, sources_used, kind)."""
    transcripts = [i for i in items if TRANSCRIPT_RE.search(i.get("headline") or "")
                   and len(i.get("content") or "") > 5000]
    if transcripts:
        t = transcripts[0]
        body = _strip_html(t.get("content") or "")
        return body, [t], "transcript"
    rel = [i for i in items if GUIDE_RE.search(i.get("headline") or "")
           or "earnings" in (i.get("headline") or "").lower()
           or " q" in (i.get("headline") or "").lower()]
    if not rel:
        return "", [], "none"
    lines = []
    for i in rel[:15]:
        body = _strip_html(i.get("content") or i.get("summary") or "")[:600]
        lines.append(f"[{i.get('created_at', '')[:16]} {i.get('source', '')}] {i.get('headline', '')}\n{body}")
    return "\n\n".join(lines), rel[:15], "headlines"


def _fields_spec() -> str:
    out = []
    for k, (lo, hi, desc) in FIELDS.items():
        if lo is None:
            out.append(f'  "{k}": {desc}')
        else:
            out.append(f'  "{k}": number in [{lo}, {hi}] -- {desc}')
    return "\n".join(out)


def build_prompt(symbol: str, text: str, kind: str, ah_move: float | None, *, max_chars: int = 48000) -> str:
    ah = ("not observable on our feed" if ah_move is None else f"{ah_move:+.2%}")
    return (
        f"Company: {symbol}\nText kind: {kind}\n"
        f"After-hours / latest move versus the session close, as seen on our feed: {ah}\n\n"
        f"TEXT:\n{text[:max_chars]}\n\n"
        "Return a JSON object with EXACTLY these keys:\n" + _fields_spec() + "\n"
    )


def digest(symbol: str, text: str, kind: str, ah_move: float | None) -> tuple[dict[str, Any], dict[str, Any]]:
    key = os.getenv("AAT_DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise RuntimeError("AAT_DEEPSEEK_API_KEY is not set")
    prompt = build_prompt(symbol, text, kind, ah_move)
    body = {"model": MODEL, "temperature": 0.2, "max_tokens": 900,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}
    data, dt = llm_post(DEEPSEEK_URL, body, headers={"Authorization": f"Bearer {key}"},
                        caller="transcript_digest", timeout=120.0,
                        why=("Turns the company's own call into declared expectation fields so a human "
                             "thesis on a non-mega-cap printer can be stated with a falsifier before the "
                             "open, instead of from a headline."))
    reply = data["choices"][0]["message"]["content"]
    if _non_latin_share(reply) > 0.10:
        raise RuntimeError("model replied in non-Latin script; refused, not repaired")
    raw = json.loads(reply)
    out: dict[str, Any] = {}
    for k, (lo, hi, _) in FIELDS.items():
        v = raw.get(k)
        if lo is not None:
            try:
                v = min(hi, max(lo, float(v)))
            except (TypeError, ValueError):
                v = 0.0
        out[k] = v
    usage = data.get("usage") or {}
    cost = (usage.get("prompt_tokens", 0) * PRICE_IN + usage.get("completion_tokens", 0) * PRICE_OUT) / 1e6
    import hashlib
    meta = {"model": MODEL, "prompt_hash": hashlib.sha256((SYSTEM + prompt).encode()).hexdigest()[:16],
            "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
            "cost_usd": round(cost, 5), "latency_s": round(dt, 1), "text_chars": len(text)}
    return out, meta


def ah_moves(client, symbols: list[str]) -> dict[str, float | None]:
    """Latest trade vs the session close on the free feed. None when the feed
    has no after-hours print -- IEX after-hours coverage is thin, and a 0.00%
    that is really an absence must not be read as 'flat'."""
    out: dict[str, float | None] = {}
    try:
        data = client._request("GET", "/v2/stocks/snapshots", base=config.data_url(),
                               params={"symbols": ",".join(symbols), "feed": config.stock_feed()})
    except BrokerRefusal:
        return {s: None for s in symbols}
    for s in symbols:
        x = (data or {}).get(s) or {}
        try:
            close = float(x["dailyBar"]["c"]); last = float(x["latestTrade"]["p"])
            lt = x["latestTrade"]["t"]; bt = x["dailyBar"]["t"]
            # A trade stamped at or before the 16:00 ET bell (20:00Z, 20:01 with
            # the closing print) is the close itself, not an after-hours move.
            after_bell = lt[:10] >= bt[:10] and lt[11:16] > "20:02"
            out[s] = (last / close - 1.0) if after_bell else None
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            out[s] = None
    return out


def default_symbols() -> list[str]:
    """Names whose reaction session is today or the next session, from the
    window receipt (`scripts.window_universe`): rows carry `symbol`, `reacts_on`."""
    p = STATE / "window_universe.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    today = (datetime.now(timezone.utc) - timedelta(hours=4)).date()
    keep = []
    for row in d.get("rows") or []:
        react = str(row.get("reacts_on") or "")
        try:
            delta = (datetime.fromisoformat(react).date() - today).days
        except ValueError:
            continue
        if 0 <= delta <= 1 and row.get("status") != "BEFORE_KICKOFF":
            keep.append(str(row.get("symbol")).upper())
    return sorted(set(keep))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--dry", action="store_true", help="fetch and classify, no LLM call")
    ap.add_argument("--max", type=int, default=12, help="cap on LLM calls per run")
    args = ap.parse_args()
    config.load_env()
    client = AlpacaPaper()

    symbols = [s.upper() for s in (args.symbols or default_symbols())]
    if not symbols:
        print("no symbols: pass --symbols or build state/window_universe.json first")
        return 2
    moves = ah_moves(client, symbols)
    day = (datetime.now(timezone.utc) - timedelta(hours=4)).date().isoformat()
    outdir = STATE / "expectations" / day
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"{'sym':<6}{'AH move':>9}  {'text':<11}{'chars':>7}  {'guide':<11}{'dir':<5}{'move':>6}{'conf':>5}  summary")
    calls = 0
    for s in symbols:
        try:
            items = fetch_items(client, s, days=args.days)
        except BrokerRefusal as exc:
            print(f"{s:<6}  news refused: {exc}")
            continue
        text, used, kind = select_text(items)
        ah = moves.get(s)
        ah_s = "n/a" if ah is None else f"{ah:+.2%}"
        if kind == "none":
            print(f"{s:<6}{ah_s:>9}  {'none':<11}{0:>7}  (no earnings item on the feed in {args.days}d)")
            continue
        if args.dry or calls >= args.max:
            print(f"{s:<6}{ah_s:>9}  {kind:<11}{len(text):>7}  (not digested{' -- cap' if calls >= args.max else ''})")
            continue
        try:
            fields, meta = digest(s, text, kind, ah)
            calls += 1
        except Exception as exc:                                        # noqa: BLE001
            print(f"{s:<6}{ah_s:>9}  {kind:<11}{len(text):>7}  DIGEST FAILED: {str(exc)[:80]}")
            continue
        packet = {"schema": "TRANSCRIPT_DIGEST_v1", "symbol": s, "date": day,
                  "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                  "text_kind": kind, "after_hours_move": ah,
                  "sources": [{k: i.get(k) for k in ("id", "source", "created_at", "headline", "url")} for i in used],
                  "fields": fields, "llm": meta,
                  "note": ("expectation data, not a forecast: what management SAID, read by a model. "
                           "Compare with what the market priced before stating a thesis.")}
        (outdir / f"{s}.json").write_text(json.dumps(packet, indent=1), encoding="utf-8")
        print(f"{s:<6}{ah_s:>9}  {kind:<11}{len(text):>7}  {str(fields.get('guide_vs_prior'))[:10]:<11}"
              f"{str(fields.get('direction_claim'))[:4]:<5}{float(fields.get('expected_move') or 0):>6.1%}"
              f"{float(fields.get('confidence') or 0):>5.2f}  {str(fields.get('summary'))[:90]}")
    print(f"\n{calls} digest(s) -> {outdir}   (each packet carries sources, model, prompt hash, cost)")
    print("Next: state a thesis you actually hold with `python -m scripts.thesis --example`; "
          "the packet is the reason and the falsifier, never the order.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
