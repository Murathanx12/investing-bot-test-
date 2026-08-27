# Rules re-pull — 2026-08-27, ~13:20 ET

Pulled from the live event page and its `/live` dashboard via Exa
(`https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon`), the day
before kickoff. The 25 Aug snapshot instructs a re-pull at kickoff; this is an
early one, and **it must be repeated on the morning of 28 Aug** because the
judging-criteria card did not render to our fetcher (see LIMITS below).

---

## ⚠️ NEW, AND NOT IN THE 25 AUG SNAPSHOT

> **"Registration closes the moment the event starts."**
> `Fri, Aug 28 · 15:00 UTC · Kickoff · Registration closes · All participants`

**Murat must be REGISTERED BEFORE 15:00 UTC / 11:00 ET on 28 August.** There is
no entry after kickoff. This is a hard, irreversible gate that no amount of
engineering recovers from, and it was not in the earlier capture.

**It is now step −2 of the runbook, above everything else.**

---

## CONFIRMED, unchanged from 25 Aug

| fact | live page, 27 Aug |
|---|---|
| kickoff | **2026-08-28 15:00 UTC** |
| submissions close | **2026-09-04 15:00 UTC** |
| technology | *"Alpaca's Trading API, MCP server and CLI"* |
| window | 28 August – 4 September 2026 |

`alpha/config.COMPETITION` already carries both timestamps and needs no change.

## NEW FACTS (not contradicting anything, but worth having)

| fact | value |
|---|---|
| prize pool | **$6,000** |
| track | **"Options Alpha Agents"** — main track, open to all |
| registered builders | **2,723** (+203 in last 24h) |
| teams forming | **727** |
| tech partners listed | 0 |

**The track is called "Options Alpha Agents."** That is the options requirement
stated in the name of the thing, not merely in a rules paragraph — it raises the
cost of submitting a shares-only book, and it is the strongest confirmation yet
that `OPTIONS_REQUIRED` is real.

**727 teams**, against the 555 recorded earlier in the project's memory. The
field is larger than the last count and still growing.

## LIMITS OF THIS PULL — stated rather than glossed

- **The judging-criteria card did not render.** The page is a Next.js app and
  our fetcher receives the shell plus some sections; the criteria block was not
  among them. So this re-pull **does not confirm and does not contradict** that
  P&L is criterion #1 — the 25 Aug capture, which was extracted from the RSC
  payload, remains the authority on criteria.
- **The "$100,000 fresh account" requirement did not appear in what rendered
  either.** Same status: not re-confirmed, not contradicted. `alpha/genesis.py`
  enforces it regardless, which is the right default — the cost of enforcing a
  requirement that was relaxed is one unused account; the cost of skipping one
  that still stands is disqualification.
- **The `/rules` path returned an empty shell** — it is not a real page.

**A section that did not render is not a section that changed.** Recorded as
UNCONFIRMED, not as absent, which is the same discipline the NVDA after-hours
tape got.

## WHAT TO DO ON 28 AUGUST

1. **Register, before 15:00 UTC.** Before anything else in the runbook.
2. Re-pull once more and diff against this file. If the criteria card renders,
   confirm P&L is still first and that the fresh-$100k line is still there.
3. Freeze genesis against **this** file's hash if the morning pull adds nothing;
   against the morning file if it does.
