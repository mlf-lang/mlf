# Owned dense LCA depth cursor candidate

This isolated test branch applies the previously archived candidate to main `fc300bc9fdc389b585cbef0630fc8915d53e89c5`. It is not a merge recommendation or full production qualification. No PR, native bootstrap, self-host fixed-point experiment, or benchmark workflow is started by this branch.

## Change and identity

The fresh-owned rebinding path carries completed binder depths through one LCA traversal instead of reading both depth arrays at every climb. Parent traversal remains O(h); repeated depth reads become O(1) per LCA. Placement, parent reads, validation and first-error order remain. Original raw `densePlace` and `denseCommon` entrypoints are unchanged. The new helpers rely on a call-discipline precondition, not language-enforced privacy.

The production change is confined to `libraries/mlf-inference/Bootstrap/Graph.hs`. Its 144612-byte content has SHA-256 `8d145bd52e8c367dd9d47891754d1727b7f2ae7f68cc271535fa01f1eda0bee9`, matching the tested candidate. The [archived 7995-byte patch](https://github.com/mlf-lang/mlf/blob/a96f9c5ee68cc47206d3a0568a7b54cf49601c57/tools/performance/main-baseline-gap-20261114/dense-common-depth-cursor/candidate.patch) reproduces it from the stated base.

## Completed finite qualification

- [Graph gate, exact commit 4006578](https://github.com/mlf-lang/mlf/actions/runs/44112484188): 29 finite cases and 124 exact files per O0/O2 mode, including graft, signed/gapped and sparse dispatch, aliases, first-error ordering and bounded demand cases.
- [Solver gate, exact commit a55a27d](https://github.com/mlf-lang/mlf/actions/runs/44123639110): four real transaction groups and 32 exact sidecars per O0/O2 mode. Raw A=C=literal expected, with unchanged immutable snapshots.

These are the existing qualification runs for the exact candidate content, not checks of this new branch commit. They do not establish arbitrary payload-demand, hidden-stub, captured prepared-fallback, full Constraint or native-backend qualification.

## Descriptive checking-service screens

Each workload has only two paired samples after separate qualification. They justify continued investigation, not stable speedup or significance:

| Workload | Geometric wall-time reduction | Boundary |
| --- | ---: | --- |
| Foundation | 6.6613% | Historical machine; not pooled with later results |
| Async import closure | 2.1282% | Recovered machine; one pair slower, one faster; not asynchronous runtime execution |
| Parser import closure | 2.4576% | Same recovered machine; not parser actions or the full frontend crate |

Wall measurements include parent polling delay. Peak RSS is not allocation or retained-heap measurement. The whole candidate ELF grew by 10512 bytes (0.0521%); this is not a text-section measurement. See the [archived raw-number summary and limits](https://github.com/mlf-lang/mlf/blob/a96f9c5ee68cc47206d3a0568a7b54cf49601c57/tools/performance/main-baseline-gap-20261114/dense-common-depth-cursor/README.md).

## Whole-crate artifact qualification

The first attempt cancelled A after a live-output sampling control exception; C never started. Its partial outputs were not used as a reference, and the original failure was retained locally. Only the narrow active-temporary-path sampling and terminal-wait controls were repaired; the next batch uses a fresh A reference and strict A/C raw-artifact equality, without producer-identity exemptions.

A fresh Foundation15 whole-crate A reference and C qualification passed independent raw audit. The complete CI (329871 bytes), CO (1072662 bytes) and query report (666349 bytes) are directly byte-identical. Both sides have the same 1653 result files and bytes; every file passed independent SHA and CRC checks. All 532 report-selected values additionally passed schema-6 decoding, raw-group mapping and query-key recomputation, with identical 539 members, 14 owners and ordered witnesses. The 15 control regressions passed, both targets had empty stdout/stderr, and terminal cleanup preceded strict postchecks. The run took 62.918 seconds as a control cost, not a performance sample. Its original evidence and independent audit are retained locally, not uploaded to Library. This is finite whole-crate artifact qualification, not full production or native qualification. This branch does not automatically trigger CI; no new-commit green check is implied by the earlier frozen-source runs. Native A/B remains paused. Main and PR51 are not modified. Further production promotion requires an explicit decision and suitable broader qualification; this note does not grant it.
