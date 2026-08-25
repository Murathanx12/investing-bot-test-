# Competitor watch

**Snapshot 2026-08-25** (pre-kickoff). Sources: public lablab team pages under
`lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/<slug>`, meta
descriptions read directly. Re-run after kickoff — most teams publish their
concept only once building starts.

Scale: **2,236 registered participants** on the event page. Teams are 1-6
people, so expect a few hundred submissions and far fewer that actually trade.

## Public concepts at snapshot

| Team | Stated concept | Read |
|---|---|---|
| `midas-gate` | *"Autonomous options-trading agent on Alpaca's MCP server. It sells defined-risk SPY credit spreads — we don't bet on direction, we co[llect]…"* | **The serious one.** Short premium on SPY is the right trade most weeks and it explains itself in a sentence. Structurally **capped**: credit spreads win small. In a five-session P&L race that is very likely mid-pack-positive — beatable on criterion 1 by anything convex that works, and beatable on criterion 3 because "sell SPY spreads" is a known strategy rather than an original one. |
| `AlpacaSentry` | *"autonomous, event-driven trading agent built on Alpaca's Trading API and MCP server. Rather than waiting for user…"* | Closest to us on **presentation** — event triggers plus a rationale dashboard. Their differentiator is the trigger. Ours must be what happens *after* it: the shape decision and the minimum-detectable-move gate. |
| `Dawn Of The Trading Agents` | *"a team of builders… to explore what happens when trad[ing agents debate]"* | The commodity multi-agent debate architecture. Expect many. **Do not build this.** |
| `AgentAlpha` | *"autonomous AI trading agent that analyzes markets, generates strategies, and executes paper trades"* | Generic at snapshot time. No stated edge yet. |
| `Stormers` | no project description published | Watch. |

## What this tells us to do

**The commodity project this week is: LLM reads news → decides bullish → buys a
call.** Anything we can be out-prompted on is not a differentiator.

Three things the field is unlikely to have, in descending order of how hard they
are to copy:

1. **A measured decile-shape library over 32 years of CRSP**, and an agent that
   *refuses* to buy convexity on a signal whose tail was measured to be empty.
   Nobody reproduces this in a week; it took the parent project five months.
2. **A minimum-detectable-move gate computed from real bid/ask** that can refuse
   a trade for agreeing with the option chain. Cheap to describe, and almost
   nobody does it — the spread is invisible unless you go and read the quote.
3. **A shadow arena of counterfactual books** off the same live decision state,
   so the dashboard shows what the agent did *not* do, priced.

## Where we are likely to be out-competed

Stated plainly so it gets defended rather than discovered late:

- **Presentation.** Teams of six with a designer will ship a prettier dashboard.
  Mitigation: our screens must show *reasoning*, not gauges — the refused
  candidates are the screen nobody else has.
- **Raw P&L.** In a five-session field of hundreds, somebody will YOLO 0DTE and
  print +200%. We cannot and should not try to beat that draw; we beat it on the
  other three criteria while staying in the top decile of criterion 1.
- **Social engagement.** Teams with existing audiences start ahead. Mitigation:
  post from day one, and post the *idea* (shape → instrument), which is
  genuinely interesting, rather than build-log screenshots.

## Re-check schedule

- **28 Aug, at kickoff** — re-pull the rules AND the team list.
- **31 Aug** — first working-project descriptions usually appear.
- **3 Sep** — final field read; informs Thursday's risk posture, which is
  `TournamentState.field_leader_estimate` and genuinely changes sizing.

Research is for awareness and idea comparison. **Do not copy unlicensed code.**
