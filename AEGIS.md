# AEGIS — canonical context entrypoint

This file is the first document every human or agent working on AEGIS Alpha Terminal should read.

## Canonical reading order

1. `docs/canonical/00_NORTH_STAR.md` — what AEGIS is trying to become and what must never be lost between sessions.
2. `docs/canonical/01_SYSTEM_ARCHITECTURE.md` — the world-intelligence, research, execution and learning architecture.
3. `docs/canonical/02_ROADMAP.md` — the only active strategic roadmap. Update this file instead of creating another dated ROADMAP.
4. `docs/canonical/03_DAILY_INTELLIGENCE_LOOP.md` — the Asia-to-US daily prediction, trading and autopsy cycle.
5. The current execution runbook / live-state receipt for operational details.

`docs/HANDOFF.md`, dated `ROADMAP_*.md`, session handoffs, `FINDING_*.md`, experiment receipts and negative-results files remain valuable evidence. They are **not competing sources of current intent**. If a historical document conflicts with the canonical set, preserve the historical document unchanged and update the canonical set with the current ruling plus a provenance link.

## Priority of truth

For factual questions about what the live machine is doing: broker/venue state and executable code > current test/deployment receipts > canonical docs > historical handoffs. For strategic intent: `00_NORTH_STAR.md` > `01_SYSTEM_ARCHITECTURE.md` > `02_ROADMAP.md` > dated roadmaps.

Safety invariants and tamper-evident ledgers are not overridden by prose. Strategy is allowed to adapt; positions retain the model/version/contract they entered under so later changes do not rewrite history.

## The sentence that must survive every session

AEGIS is not an earnings bot, an NVDA bot, a fixed-factor backtester, or an LLM stock picker. It is an investment-intelligence system intended to observe the world broadly, find under-followed economic changes before they become obvious consensus, propagate those changes through causal relationships to companies and instruments, quantify what is already priced, test the hypothesis against historical and live evidence, choose or refuse a trade, and learn from the prediction afterward.

The target is both short-horizon opportunity and long-horizon discovery: find the future MU/MRVL/NVDA while it is still an underappreciated bottleneck, not merely explain it after it becomes a mega-cap headline.

## Working rule for agents

Do not create another strategic roadmap because a session ended. Put new strategic rulings into `docs/canonical/02_ROADMAP.md`; put measured experimental facts in a `FINDING_*.md` or machine-readable receipt; put temporary operational state in a dated runbook/receipt. A handoff should point to canon and summarize deltas, not restate the entire project.
