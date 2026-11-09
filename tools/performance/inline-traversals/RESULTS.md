# Inlining traversal measurements — 2026-11-01

The first guarded run completed successfully: all eight ordinary/diagnostic LLVM byte comparisons passed, and the two independent control processes produced identical exact counts. No compilation or runtime fixes were needed after execution started. The production integration was already pushed at `3b367be8aa0dd265c2d624bfad983d1e54bb4568` before this run.

Both annotated and inferred dependency chains produced the following identical traversal counts. Depth is the maximum explicitly threaded recursion depth, starting at zero for each traversal root.

| Chain size | commonCalls roots | commonCalls visits | Max depth | substituteUsed roots | substituteUsed visits | Max depth |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 32 | 57 | 1,411 | 68 | 437 | 8,098 | 91 |
| 128 | 153 | 17,539 | 260 | 533 | 32,242 | 261 |
| 512 | 537 | 266,371 | 1,028 | 917 | 405,298 | 1,029 |
| 2,048 | 2,073 | 4,210,819 | 4,100 | 2,453 | 6,321,202 | 4,101 |

Alias elimination has a different growth pattern:

| Chain size | Annotated alias roots | Annotated copy visits | Annotated structural rebuilds | Inferred copy visits | Inferred structural rebuilds |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 32 | 351 | 42,723 | 21,930 | 42,501 | 21,835 |
| 128 | 447 | 43,395 | 22,218 | 42,501 | 21,835 |
| 512 | 831 | 46,083 | 23,370 | 42,501 | 21,835 |
| 2,048 | 2,367 | 56,835 | 27,978 | 42,501 | 21,835 |

Inferred chains have 319 alias-copy roots at every size. Both families have maximum alias-copy depth 60 throughout.

For a 4× increase from 512 to 2048 bindings, `commonCalls` visits grow 15.808× and `substituteUsed` visits grow 15.596×. Their maximum depths grow from 1028/1029 to 4100/4101. Annotated alias-copy visits grow only 1.233× and structural rebuilds 1.197×; inferred alias copying stays constant.

Across these four measured sizes, visits fit `commonCalls = N² + 8N + 131` and `substituteUsed = (3N² + 23N)/2 + 6194` exactly. These are descriptive fits to this finite input set, not proofs of global complexity.

At size 2048, `commonCalls` records 4,206,686 positive-use visits and 4,133 pruned visits. `substituteUsed` records 4,212,238 positive-use visits, 2,108,964 pruned visits, and 4,209,568 positive-use parent reconstruction branches. Copies of substituted replacement values visit only 18,380 nodes. This distinguishes repeated scans/reconstruction of the path to a use from copying the replacement itself. `useApplications` independently records 6,372,032 spine visits, compared with 416,192 at size 512.

These measurements support investigating repeated per-binder positive-use path discovery and reconstruction in common-call detection and substitution before alias-copy elimination on these chain workloads. They do not establish general asymptotic complexity, ordinary CPU-time attribution, or an optimization speedup.

Counters describe demanded source paths in the diagnostic build, which disables CSE and full laziness. Ordinary optimized execution can share or eliminate work differently. Exact LLVM equality establishes output equivalence on these inputs, not identical demand or physical work. Structural rebuild events are logical constructor branches, not physical node allocations or bytes; map/list/tuple allocations are not counted. Roots, visits, branches, and application-spine events overlap and must not be added as independent work totals. An intervention still needs a separate ordinary-build performance experiment.

Validation includes exact source-transform reversibility, zero-use bottoms remaining unforced, positive recursive common-call/substitution controls with exact depths and fresh-name results, a nonzero alias-copy control, complete branch accounting, authentic producer object inventory, and all nine interfaces/eighteen files in the checked dependency closure. Seven Python admission controls passed both normally and under `python -O`.

Raw directory: `/Users/ares/.codex/worktrees/int64-patricia-20261031/mlf/.mlf-build/inline-traversals-20261101/run-01`. The measured harness and production source copies are preserved in `source-snapshot/`, each verified against the measurement receipt. No failed attempts exist.

- `receipt.json` SHA-256: `d69d8e815886e72b2428617d7a0437725252d4131ff4a3895fe9303379b5e437`
- `counts.json` SHA-256: `289bc5bf99c5b554b96d2d7c78bcab3ed7070015c3c43843d766316b503dad0b`

Reproduce this summary without rerunning the compiler:

```sh
python3 -B tools/performance/inline-traversals/summarize.py \
  --results .mlf-build/inline-traversals-20261101/run-01 \
  --output tools/performance/inline-traversals/RESULTS.md
```
