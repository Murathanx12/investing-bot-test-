# DECISION — 2026-08-31 — HACK4 TRACKER PROFIT-MAX APPROVED

**Human decision:** Murat explicitly approved enabling hack4 as the tracker profit-max paper account at approximately 19:00 +08 on 2026-08-31.

This approval is for the intended experiment in `NEXT_SESSION_2026-08-31h_OPUS_POST_NIGHT_SOURCE_MESH.md`:

- account: `hack4` only;
- brain: `tracker_portfolio`;
- portfolio: sealed `hack4` profit-max personality;
- initial expression: **shares only**;
- exact names come from the sealed portfolio artifact;
- sealed target notional is a reduce-only ceiling; admission/risk may cut and never raise it;
- hard gross/account/opening-range/data-integrity controls remain active.

## Activation condition

Do not interpret approval as permission to trade a stale or partial artifact.

Activation may proceed without asking Murat again once all of the following are true:

1. the 2026-08-31 tracker repair/refill has completed and the final universe is not a partial snapshot;
2. full suite + fleet checks are green;
3. P0 universe injection and sealed-weight ceiling proofs are green on the current commit;
4. a fresh 2026-08-31 portfolio book is sealed from the completed tracker state;
5. the exact hack4 holdings/ranking are non-degenerate and the seal reports deterministic gross/worst-case/source versions;
6. the exact seal is published to `docs/seed/predictions/` and the published content hash matches the dry-run artifact;
7. the source commit containing the artery/P0 fixes and the seed commit are both pushed;
8. hack4 alone is redeployed from source and its live environment is changed to the declared tracker mandate;
9. logs/heartbeat confirm the new build, `AAT_ACCOUNT_ROLE=hack4`, `tracker_portfolio`, shares-only expression, and the same seal hash before an entry pass.

If any condition is false, keep hack4 on its current old mandate or shadow-only and state which condition blocked activation. Never fall back to the 2026-08-30 published book.

This is a PAPER-account research mandate. It does not authorize changes to hack1/hack2/hack3/hack5/hack6.