# docs/seed — what a fresh container starts with

Copied into `/app/state` on container start with `cp -rn`: **never overwrites**
a file the volume already holds. The volume is the ledger; this directory is
the seed.

- `genesis_<role>.json` — the birth certificate of a judged account. Frozen
  ONCE by `scripts.genesis --freeze` on the laptop, committed here, so the
  container verifies against the same record a reviewer can read in git.
- `universe/` — the whole-market `HIGH_DISPERSION_US_v1` snapshot that
  `scripts.candidates` reads. Rebuilt by `alpha.universe.build` when stale.
