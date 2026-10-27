# mlf-crates 14-module compiler speed checkpoints

These are **new restoration commits made on 2026-10-27**, not fabricated earlier
commits. The measurements and validation logs were executed in the previous
cloud workspace on 2026-10-26/27 and recovered from the authenticated Library
checkpoint after that workspace was replaced. They are **not new-machine runs**.

The implementation baseline is PR25 `aa11ffd318a2efa5be9805524710d0677eedb86f`.
The observed performance-branch head `92e4d5eff1ab2f195c70ccd49ad3331c946f4da4`
is an ancestor (12 existing upstream commits); no existing history is rewritten.

## Scope and correctness

The benchmark recompiles the same frozen 14 `mlf-crates` modules, reuses compiled
dependencies, and does not reuse target inference results (544 inferred groups,
0 reused). GHC 9.14.1 plain `-O2` emits optimized object files; GHC-hosted MLF
emits independently checked xMLF and query-cache files. These endpoints differ.
The three-times goal has **not been reached**. No completed 74-module native
bootstrap, platform parity, or self-hosting fixed-point claim is made.

All existing checks remain. Original independent oracles, control runners,
historical output receipts and recipes are preserved without rewriting their
hashes or original paths. Historical recipes contain original absolute paths
and expect their recorded authenticated producer/input state; they are not a
promise of turnkey execution in an arbitrary checkout. Recovery/setup recipes
and new-machine qualification belong to the continuing experiment.

Evidence is outside the manifest-selected implementation/host source closures.
Each stage records exact cumulative implementation patch equality and unchanged
builtin identity before/after adding its documentation. Package lock snapshots
enumerate explicit manifest module/main paths; no manifest includes this folder.

## Included stages

- `baseline`: `cumulative-source.patch` SHA256 `a09180199c536610c3f22bb4169d3ecc495531fd37dffb5d13fe9c6881d45855`.
- `p1`: `cumulative-source.patch` SHA256 `082b947872d7ee003039d602d616d45d45ac2172eca6836e0092ac20a5b0bfd5`.
- `p2`: `cumulative-source.patch` SHA256 `8d07e0962909fdf9f5ac34e5ff65036e39a9dc73c85a879ccf0ba06637b95be7`.
- `p3`: `cumulative-source.patch` SHA256 `01410b8c004187aa4878f10542967ad8d3b5d448511257c68ab62f466ade64ec`.

P1 observed MLF median 105.914294467 s / GHC 8.001561806 s (13.2367x);
154,072 selector controls passed. See its full stage results for scoped gates.

P2 observed MLF median 97.958729957 s / GHC 8.387828030 s (11.6787x);
2,503 differential controls passed. Actual optimized-source qualification had
553 fresh groups and is not the frozen-input performance sample.

P3 observed MLF median 88.601739724 s / GHC 7.986013657 s (11.0946x);
922 differential controls passed. Actual optimized-source qualification had
576 fresh groups. Short read-only analyses overlapped parts of this timing
sequence: it is **not a clean causal ABBA experiment**. One later quiet control
was 88.335022101 s, not a replacement median. Mandatory details are in
`p3/evidence/prefix-3-background-exposure.json` and the stage result text.

The complete historical checkpoint is retained as a **separately delivered
archive**, not vendored into this Git repository:
`mlf-crates-profile-20261026-v3.zip` (21,941,703 bytes, 945 members),
SHA256 `7ba5f352557178a3d384627965759eda197c7d25e0e7db7b11faa59458cbaf27`.
See `checkpoints/README.md`, `checkpoints/SHA256SUMS`, and
`checkpoints/archive-inventory.json` for its identity, scope, and member inventory.
No private download link or access credential is published here.

The external archive preserves all earlier profiles, phase-accounting scripts,
source/test changes, validation/timing receipts and manifests. Query bodies,
toolchains and compiler binaries were intentionally excluded. Its negative
graph-index screen is **not an accepted optimization**.

The repository retains the exact accepted implementation, frozen control
oracles and runners, reproducibility recipes, result summaries, and qualification
receipts. The archive is a historical evidence/recovery artifact, not a compiler
build or runtime dependency. As noted above, historical replay still requires
the recorded authenticated inputs and toolchain; neither this checkout nor the
archive alone is a turnkey replacement for that environment.
