"""PREMARKET_DIGEST -- read the WHOLE universe's overnight news, East first, and write a bet per name.

    python -m scripts.premarket_digest                 # window + theme universe, last 18h
    python -m scripts.premarket_digest --hours 36      # over a weekend
    python -m scripts.premarket_digest --symbols NVDA MRVL --no-east

WHY (Murat, 28 Aug): "if we are running nights on only few stocks it is a
waste of time -- we are missing the whole world, whole news, for one stock.
Day and news start early in the East and influence the West."

Before this script the overnight machinery looked at (a) the earnings
calendar through one measured brain and (b) a council on <=4 recent
printers. Nothing read the market's news across every name we can trade, and
nothing looked at Asia before New York. This does both, in one pass that
fits before the open:

  1. universe  = window-universe printers + the 40 verified theme names +
                 SPY/QQQ/IWM  (~130 names)
  2. headlines = Alpaca news (Benzinga) per 20-symbol batch, last N hours
                 + GDELT DOC API for the EAST session: Hang Seng / A-shares /
                 PBOC / Chinese-language coverage of US stocks (sourcelang
                 chinese) -- GDELT gives translated titles, DeepSeek reads
                 the originals when present
  3. extraction = DeepSeek turns each batch into JSON bets:
                 {symbol, direction, magnitude_pct, horizon_sessions,
                  catalyst, p_already_priced, confidence, falsifier}
                 and one EAST->WEST macro read
  4. ranking   = |magnitude| x (1 - p_already_priced) x confidence

WHAT IT IS NOT
==============
Shadow. It places nothing and sizes nothing. Its output feeds two things:
`scripts.dislocation_scan` (the council spends its slots on the digest's top
names instead of on whoever printed last) and `scripts.thesis` (a human
reads the table and types the bet they believe, under their own name).
A headline is a HYPOTHESIS; the brains and the chain adjudicate it.

Receipt: state/premarket/<day>.json -- every headline counted, every
provider refusal recorded, every bet with its falsifier.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpha import config, fleet, newsmakers
from alpha.broker.alpaca import AlpacaPaper
from alpha.council import providers

STATE = Path(__file__).resolve().parent.parent / "state"
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
# GDELT MEASURED 28 Aug: the first request answers in ~3s, every request
# inside the next ~20s hangs and dies (code 000) -- it rate-limits per IP, and
# an OR-heavy query times out on its own. So: SIMPLE single-term queries,
# sequential, with a pause between them, timespan=1d.
EAST_QUERIES = [
    ('"Hang Seng"', "east_english"),
    ('sourcelang:chinese 美股', "east_chinese_us_stocks"),
    ('sourcelang:chinese 英伟达', "east_chinese_nvidia"),
    ('"hedge fund" China', "funds"),
]
GDELT_PAUSE_S = 8
# GDELT from a residential Windows IP on 28 Aug: 10060 / handshake timeout /
# 429 on four of four calls. The East read cannot depend on one flaky source,
# so the Asian-session PROXY is the Alpaca news feed on the China/Asia
# instruments, which Benzinga writes during the Asian session. English, and
# recorded as such; the Chinese-language leg is GDELT's when it answers.
EAST_PROXY_SYMBOLS = ["FXI", "KWEB", "MCHI", "BABA", "PDD", "JD", "BIDU", "TSM", "EWJ", "EWY", "EWT", "NIO", "XPEV", "LI"]
SYSTEM = ("You are a sell-side news analyst writing for a quantitative desk. Answer ONLY with a JSON object, in English. "
          "Never invent a headline. A bet needs a CATALYST that is in the text and a FALSIFIER that a price could show.")


def universe(extra: list[str] | None) -> list[str]:
    syms = {"SPY", "QQQ", "IWM"}
    p = STATE / "window_universe.json"
    if p.exists():
        for row in json.loads(p.read_text(encoding="utf-8")).get("rows") or []:
            if row.get("status") != "BEFORE_KICKOFF":
                syms.add(str(row["symbol"]).upper())
    try:
        syms.update(fleet.theme_symbols())
    except Exception:                                                   # noqa: BLE001
        pass
    syms.update(s.upper() for s in (extra or []))
    return sorted(syms)


def _tracker_candidates() -> list[str]:
    """Today's BUY/STRONG_BUY from the tracker -- our own screen's list.

    Read from `latest.json`, which the refresh writes at the END of a run, so a
    refresh in flight cannot hand back a half-built universe. Missing tracker is
    an empty list and SAYS SO: the digest still runs on the news, which is the
    point of making it adaptive.
    """
    p = STATE / "tracker" / "latest.json"
    if not p.exists():
        print("  (no tracker latest.json -- candidates empty, news-only universe)")
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"  (tracker latest.json unreadable: {exc} -- candidates empty)")
        return []
    rows = d.get("candidates") or []
    return [str(r["symbol"]).upper() for r in rows if r.get("symbol")]


def wide_news(client, hours: int, *, max_pages: int = 12) -> list[dict]:
    """The WHOLE market's news -- no symbol filter. What is the world saying.

    The symbol-filtered call answers "what was written about my list", which
    cannot surface a name the list does not already contain. Omitting `symbols`
    answers "who is making news", which is the question the digest needs.
    Measured 2026-08-31: one page carried 79 distinct symbols.
    """
    start = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out, token, pages = [], None, 0
    while pages < max_pages:
        params = {"limit": 50, "sort": "desc", "start": start}
        if token:
            params["page_token"] = token
        try:
            d = client._request("GET", "/v1beta1/news", base=config.data_url(), params=params)
        except Exception as exc:                                        # noqa: BLE001
            # A refusal is recorded, never read as "no news". A rate limit that
            # returns an empty universe would silently shrink the day's list.
            out.append({"refusal": f"wide page {pages}: {type(exc).__name__}: {exc}"})
            break
        for n in (d or {}).get("news") or []:
            out.append({"symbols": [str(x).upper() for x in (n.get("symbols") or [])],
                        "headline": n.get("headline", ""),
                        "summary": (n.get("summary") or "")[:300],
                        "source": n.get("source"), "at": n.get("created_at")})
        token = (d or {}).get("next_page_token")
        pages += 1
        if not token:
            break
    return out


def alpaca_news(client, symbols: list[str], hours: int) -> list[dict]:
    start = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    for i in range(0, len(symbols), 20):
        batch = symbols[i:i + 20]
        try:
            d = client._request("GET", "/v1beta1/news", base=config.data_url(),
                                params={"symbols": ",".join(batch), "limit": 50, "sort": "desc", "start": start})
        except Exception as exc:                                        # noqa: BLE001
            out.append({"refusal": f"{batch[0]}..{batch[-1]}: {type(exc).__name__}"})
            continue
        for n in (d or {}).get("news") or []:
            out.append({"symbols": [s for s in n.get("symbols") or [] if s in symbols], "headline": n.get("headline", ""),
                        "summary": (n.get("summary") or "")[:300], "source": n.get("source"), "at": n.get("created_at")})
    return out


def gdelt(query: str, hours: int, n: int = 25) -> list[dict]:
    q = urllib.parse.urlencode({"query": query, "mode": "artlist", "format": "json", "timespan": f"{max(1, round(hours / 24))}d",
                                "maxrecords": n, "sort": "datedesc"})
    try:
        # MEASURED 28 Aug: without a User-Agent GDELT lets the TLS handshake
        # time out (48s, no reply); with one it answers in ~20s.
        req = urllib.request.Request(f"{GDELT}?{q}", headers={"User-Agent": "Mozilla/5.0 (AEGIS premarket digest)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            arts = json.loads(r.read().decode("utf-8", "replace")).get("articles") or []
    except Exception as exc:                                            # noqa: BLE001
        return [{"refusal": f"gdelt: {type(exc).__name__}: {str(exc)[:80]}"}]
    return [{"title": a.get("title", ""), "source": a.get("domain"), "lang": a.get("language"), "at": a.get("seendate"),
             "url": a.get("url")} for a in arts]


def extract(headlines: list[dict], symbols: list[str], *, live: dict, caller: str) -> tuple[list[dict], list[str]]:
    bets, refusals = [], []
    rows = [h for h in headlines if "refusal" not in h]
    for i in range(0, len(rows), 30):
        chunk = rows[i:i + 30]
        text = "\n".join(f"- [{','.join(h.get('symbols') or [])}] {h.get('headline') or h.get('title')} :: {h.get('summary', '')}"
                         for h in chunk)
        user = (f"Tradeable symbols: {', '.join(symbols)}.\nHeadlines (last session, newest first):\n{text}\n\n"
                'Return {"bets": [{"symbol": str, "direction": "up"|"down", "magnitude_pct": float (expected move over the horizon), '
                '"horizon_sessions": int (1-5), "catalyst": str (quote the headline), "p_already_priced": float 0-1 '
                '(1 = the move already happened, e.g. a post-earnings gap), "confidence": float 0-1, "falsifier": str}]}. '
                "Only symbols from the tradeable list. Omit names with no catalyst. A stock that ALREADY moved on its news "
                "gets p_already_priced >= 0.7 unless the text argues for continuation.")
        prov = next((p for p in ("deepseek", "featherless", "nvidia_kimi", "hf_glm") if live.get(p, {}).get("state") == "live"), None)
        if not prov:
            refusals.append("no live provider"); break
        try:
            obj, _ = providers.chat_json(prov, SYSTEM, user, caller=caller,
                                         why="Ranks which overnight-news names the council SELECTS for its four slots and which bets the human DECIDES to enter via scripts.thesis; a different answer changes the ranking.",
                                         max_tokens=1800)
            for b in obj.get("bets") or []:
                if str(b.get("symbol", "")).upper() in symbols:
                    b["symbol"] = b["symbol"].upper(); b["provider"] = prov; bets.append(b)
        except providers.ProviderRefusal as exc:
            refusals.append(f"{prov}: {str(exc)[:100]}")
    return bets, refusals


def east_read(arts: list[dict], *, live: dict) -> dict:
    rows = [a for a in arts if "refusal" not in a]
    if not rows:
        return {"refusal": "no East articles"}
    text = "\n".join(f"- ({a.get('lang')}, {a.get('source')}) {a.get('title')}" for a in rows[:60])
    user = (f"Asian-session and Chinese-language coverage, newest first:\n{text}\n\n"
            'Return {"east_tone": "risk_on"|"risk_off"|"mixed", "themes": [str], "us_implications": [{"symbol_or_sector": str, '
            '"direction": "up"|"down", "why": str}], "what_hedge_funds_are_doing": str, "one_line": str}. '
            "Read Chinese titles in the original. English output.")
    prov = next((p for p in ("deepseek", "nvidia_kimi", "featherless") if live.get(p, {}).get("state") == "live"), None)
    if not prov:
        return {"refusal": "no live provider"}
    try:
        obj, _ = providers.chat_json(prov, SYSTEM, user, caller="premarket_digest.east",
                                     why="East-first macro read that DECIDES whether the day is risk-on or risk-off before New York opens and which US sectors the digest ranks up or down.",
                                     max_tokens=900)
        obj["provider"] = prov
        return obj
    except providers.ProviderRefusal as exc:
        return {"refusal": f"{prov}: {str(exc)[:100]}"}


def score(b: dict) -> float:
    try:
        return abs(float(b.get("magnitude_pct", 0))) * (1.0 - float(b.get("p_already_priced", 0))) * float(b.get("confidence", 0))
    except (TypeError, ValueError):
        return 0.0


def latest(day: str | None = None) -> dict | None:
    """The receipt other scripts read. None when today's digest was not run."""
    day = day or (datetime.now(timezone.utc) - timedelta(hours=4)).date().isoformat()
    p = STATE / "premarket" / f"{day}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=18)
    ap.add_argument("--symbols", nargs="*", default=None, help="extra names to include")
    ap.add_argument("--no-east", action="store_true")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--top-news", type=int, default=None,
                    help="cap the news-first block (default: NO cap -- adaptive)")
    ap.add_argument("--fixed-universe", action="store_true",
                    help="the pre-2026-08-31 behaviour: window+theme list only, no wide news")
    args = ap.parse_args()
    config.load_env()
    client = AlpacaPaper()
    live = providers.probe(["deepseek", "featherless", "nvidia_kimi", "hf_glm"])

    # NEWS FIRST, THEN OUR LIST. The universe is no longer a fixed set that the
    # news is filtered against; the day decides who is in it.
    uni = None
    if args.fixed_universe:
        syms = universe(args.symbols)
        print(f"universe {len(syms)} names [FIXED -- window+theme only]")
    else:
        # Locals named apart from the digest's own `ranked`/`refusals`, which
        # hold the BETS and are built further down. One shadowed name here
        # would silently replace the bet list with an attention ranking.
        wide = wide_news(client, args.hours)
        wide_refusals = [w["refusal"] for w in wide if "refusal" in w]
        tal = newsmakers.tally(wide)
        news_ranked = newsmakers.score(tal, newsmakers.load_baseline())
        _day_now = (datetime.now(timezone.utc) - timedelta(hours=4)).date().isoformat()
        newsmakers.append_baseline(_day_now, {k: v["n_articles"] for k, v in tal.items()})
        uni = newsmakers.adaptive_universe(
            newsmakers=news_ranked, candidates=_tracker_candidates(),
            always=["SPY", "QQQ", "IWM"], extra=args.symbols,
            top_news=args.top_news)
        syms = uni["symbols"]
        n_new = sum(1 for r in news_ranked if r["is_new"])
        print(f"wide news: {len(wide) - len(wide_refusals)} items -> {len(tal)} names "
              f"making news ({n_new} with no prior baseline)"
              + (f"; {len(wide_refusals)} page refusals" if wide_refusals else ""))
        print(f"universe {uni['n_total']} names ADAPTIVE = {uni['n_news']} news-first "
              f"+ {uni['n_candidates']} tracker candidates + index proxies")
        if news_ranked:
            head = ", ".join(f"{r['symbol']}({r['n_articles']}a/{r['n_sources']}s"
                             + (",NEW" if r["is_new"] else f",z{r['attention_z']:+.1f}") + ")"
                             for r in news_ranked[:8])
            print(f"  today's newsmakers: {head}")
    print("  providers " + str({k: v.get('state') for k, v in live.items()}))

    east = []
    if not args.no_east:
        for i, (q, tag) in enumerate(EAST_QUERIES):
            if i:
                time.sleep(GDELT_PAUSE_S)
            arts = gdelt(q, args.hours)
            for a in arts:
                a["query"] = tag
            east += arts
        proxy = alpaca_news(client, EAST_PROXY_SYMBOLS, args.hours)
        for h in proxy:
            if "refusal" not in h:
                h["title"], h["lang"], h["query"] = h["headline"], "English", "east_proxy_alpaca"
        east += proxy
    news = alpaca_news(client, syms, args.hours)
    n_head = sum(1 for h in news if "refusal" not in h)
    print(f"headlines {n_head} (alpaca), east articles {sum(1 for a in east if 'refusal' not in a)}")

    east_view = east_read(east, live=live) if east else {"refusal": "--no-east"}
    bets, refusals = extract(news, syms, live=live, caller="premarket_digest.bets")
    # one bet per symbol: keep the highest-scored
    best: dict[str, dict] = {}
    for b in bets:
        b["score"] = round(score(b), 4)
        if b["symbol"] not in best or b["score"] > best[b["symbol"]]["score"]:
            best[b["symbol"]] = b
    ranked = sorted(best.values(), key=lambda b: -b["score"])

    print("\nEAST -> WEST:", east_view.get("one_line") or east_view.get("refusal"))
    for imp in (east_view.get("us_implications") or [])[:6]:
        print(f"   {imp.get('direction', '?'):<5} {imp.get('symbol_or_sector', '?'):<14} {str(imp.get('why', ''))[:90]}")
    print(f"\n{'sym':<6}{'dir':<5}{'mag%':>6}{'h':>3}{'priced':>7}{'conf':>6}{'score':>7}  catalyst")
    for b in ranked[:args.top]:
        print(f"{b['symbol']:<6}{str(b.get('direction', ''))[:4]:<5}{float(b.get('magnitude_pct', 0)):>+6.1f}"
              f"{int(b.get('horizon_sessions', 0) or 0):>3}{float(b.get('p_already_priced', 0)):>7.2f}"
              f"{float(b.get('confidence', 0)):>6.2f}{b['score']:>7.3f}  {str(b.get('catalyst', ''))[:70]}")
    if refusals:
        print("refusals:", refusals)

    day = (datetime.now(timezone.utc) - timedelta(hours=4)).date().isoformat()
    out = STATE / "premarket"
    out.mkdir(parents=True, exist_ok=True)
    receipt = {"date": day, "generated_utc": datetime.now(timezone.utc).isoformat(), "hours": args.hours,
               "n_symbols": len(syms), "universe": syms, "n_headlines": n_head, "n_east": len(east), "east": east_view,
               "bets": ranked, "refusals": refusals + [h["refusal"] for h in news + east if "refusal" in h],
               "council_symbols": [b["symbol"] for b in ranked[:8] if b["symbol"] not in ("SPY", "QQQ", "IWM")],
               # WHERE EACH NAME CAME FROM. A universe that cannot say why a
               # name is in it cannot be debugged, and an adaptive one changes
               # every day.
               "universe_mode": "fixed" if args.fixed_universe else "adaptive_news_first",
               "universe_provenance": uni,
               "newsmakers": news_ranked[:60] if not args.fixed_universe else None}
    (out / f"{day}.json").write_text(json.dumps(receipt, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nreceipt: {out / (day + '.json')}   (shadow: feeds dislocation_scan and scripts.thesis; places nothing)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
