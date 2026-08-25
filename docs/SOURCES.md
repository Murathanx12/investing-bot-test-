# Sources — measured, not assumed (2026-08-25, from a Hong Kong IP)

Every row below comes from a request made today. A source that was not probed
is not a source. Re-probe from the deploy host: SEC full-text search and
Bluesky returned 403 here and may be geo-blocks.

## Works, no auth, from a script

| Source | What it measures | Endpoint | Latency | Lag / cadence | Adapter |
|---|---|---|---|---|---|
| **Alpaca news** (Benzinga) | news events per symbol, `summary` + optional `content` | `GET /v1beta1/news?symbols=` | ~1s | real-time; 200 req/min | `sources.attention.alpaca_news` |
| **Alpaca option daily bars** | per-contract volume + trade count | `GET /v1beta1/options/bars` | ~1s/100 contracts | daily; free feed | `brains.options_attention` |
| **Alpaca option trades** | tick prints, no side/open-close flag | `GET /v1beta1/options/trades` | ~1s | delayed on free plan | (not yet used) |
| **Finnhub** free | fiscal periods + EPS surprise; **future** report dates with bmo/amc; company news | `/stock/earnings`, `/calendar/earnings`, `/company-news` | 0.5s | — | `sources.finnhub` |
| **Polymarket** Gamma/CLOB | **public belief** as a price; 24h volume as attention | `gamma-api.polymarket.com/public-search?q=` | <1s | real-time | `sources.belief.polymarket_search` |
| **Kalshi** v2 | **public belief** (Fed, payrolls, CPI, recession) | `api.elections.kalshi.com/trade-api/v2/markets?series_ticker=` | <1s | real-time | `sources.belief.kalshi_markets` |
| **CBOE** | put/call ratios (total/index/equity/SPX); VIX9D/VIX/VIX3M term structure | `cdn.cboe.com/data/us/options/market_statistics/daily/…`, `…/VIX_History.csv` | <1s | daily, T+0 evening | `sources.belief.put_call_ratios`, `vix_term_structure` |
| **Wikipedia pageviews** | attention (count) | `wikimedia.org/api/rest_v1/metrics/pageviews/per-article/…` | 0.6s | daily, **~1 day late** | `sources.attention.wiki_attention` |
| **Hacker News** Algolia | developer-crowd attention | `hn.algolia.com/api/v1/search_by_date?query=` | <1s | real-time | `sources.attention.hn_mentions` |
| **Mastodon** public tag timeline | attention, thin | `mastodon.social/api/v1/timelines/tag/` | <1s | real-time; 300/5min | `sources.attention.mastodon_tag` |
| **SEC submissions** | filing recency (8-K, Form 4) | `data.sec.gov/submissions/CIK##########.json` (UA `Name email`) | <1s | near-real-time | (not yet wired) |
| **YouTube InnerTube** | view counts per search | `POST youtube.com/youtubei/v1/search` | ~1s | brittle, undocumented | (not wired) |
| **DeepSeek** `deepseek-chat` | the extractor | `api.deepseek.com/chat/completions` | 2.4s | $0.0007 / extraction measured | `narrative.extract` |

Live readings taken today: Polymarket NVDA Q2 gross-margin 74–76% at **93%**,
Data Center revenue >$80B at **94%** (both close 26 Aug 21:00 UTC). Kalshi
August payrolls (closes 4 Sep, inside the window): P(>50k)=0.53, P(>100k)=0.21.
VIX9D 14.07 / VIX 15.85 / VIX3M 18.56 — contango. CBOE equity P/C 0.68.

## Refused today

| Source | Status | Note |
|---|---|---|
| StockTwits | 403 | with and without browser UA |
| Reddit `.json` / old.reddit | 403 | needs OAuth; pullpush.io 429 "no free scraping for agents" |
| GDELT doc API | 429 | first call |
| LunarCrush MCP | paywall | available as a claude.ai connector only, not to the agent |
| Finnhub `social-sentiment`, `calendar/economic` | 403 | premium |
| FMP | 402 | payment required |
| Bluesky `searchPosts` | 403 | `getProfile` works; likely regional — retest from US host |
| SEC EFTS full-text | 403 | even with compliant UA; likely geo-block — retest from US host |
| Google Trends explore | 429 | only the US daily-trending RSS works (not per keyword) |

## What this means for the brains

- **Attention** is measurable from four independent, unsigned sources
  (Wikipedia, HN, Mastodon, option volume). Per Cookson et al. (JFE 2024,
  "The Social Signal") attention and sentiment carry *different* information —
  attention predicting negative next-day returns — so every attention adapter
  returns a count and never a sign.
- **Belief** is measurable as a *price* from Polymarket and Kalshi. This is the
  `market_belief` axis with the LLM taken out of it; when the LLM's estimate and
  the prediction market disagree, the disagreement is recorded, not averaged.
- **Sentiment** proper (Reddit/StockTwits/X) is closed from here. The narrative
  brain therefore reads Benzinga news through Alpaca and lets the LLM estimate
  `sentiment_dispersion` from the *news* corpus, which is an admitted
  substitute for the social corpus the literature used.

## Papers the design leans on (verified to exist)

- Cookson, Lu, Mullins, Niessner — *The Social Signal*, JFE 158 (2024) 103870.
- Cookson, Fox, Gil-Bazo, Imbet, Schiller — *Social media as a bank run catalyst*, JFE 176 (2026) 104218.
- Pan & Poteshman — *The Information in Option Volume for Future Stock Prices*, RFS 19(3) 2006.
- Hu — *Does option trading convey stock price information?*, JFE 111(3) 2014.
- Gao, Xing, Zhang — *Anticipating Uncertainty: Straddles around Earnings Announcements*, JFQA 53(6) 2018: ATM straddles bought 3 days pre-print, held to the announcement, **+3.34%** on average — the prior behind `event_move`.
- Kelly, Pástor, Veronesi — *The Price of Political Uncertainty*, JF 71(5) 2016.
- Lopez-Lira & Tang (2023) and Chen, Kelly, Xiu (2022–24) on LLM text and returns.
