# Compiler shape screen

This suite compares **the same shared-Haskell source bytes** compiled by GHC
and by GHC-hosted MLF, starting from fresh target outputs and ending at a native
executable. It investigates the low-level **crate route used by the compiler
compilation work**. It does not measure the installed `emlf SOURCE -o OUTPUT`
driver with its native standard-library installation.

The distinction matters: this MLF producer has `PreparedNativeData.enabled =
False`. Its pipeline is `--compile-crate`, `--crate-to-llvm-gc`, then ordinary
Clang `-O2`. Fixed checked builtin dependencies and the C runtime object are
prebuilt; emission and optimization of the resulting LLVM remain timed. GHC
uses a prebuilt, isolated package containing the unchanged `MLF.Primitive` host
adapter and compiles each Main module with `--make -j1 -O2 -fforce-recomp`.
Both routes produce native executables, but they perform different internal
proof, serialization and optimization work.

## 2026-10-31 result

Compiler source: `fffb66a370c472a930995496f87fb926d19d13d5` (PR #25 head when
the experiment began). GHC 9.14.1, Apple M1 Max, macOS 26.6.2, one pipeline at a
time, ordinary Clang `-O2`, no target inference reuse.

The initial screen contains ten families at sizes 8, 32 and 128, plus a minimal
IO program: **31 cells / 186 native compilations**. After that window closed, a
separate, fixed extension compared five families at sizes 128 and 512:
**10 cells / 60 native compilations**. These are two exploratory cohorts, not
independent confirmation of an optimized compiler. They are never pooled.

All 246 timed builds completed. Their executables passed 738 checks against
closed-form expected outputs. All 123 MLF builds had positive fresh counts and
zero reused groups. Within every cell, both repeated MLF checked outputs were
compared as raw `.mlfci` and `.mlfco` bytes against the first output, and ordered
query-group identities were checked. This qualifies these fixtures and inputs;
it is not a new full-language correctness proof.

Times below are seconds, three-sample medians. Ratios are MLF median / GHC
median. No confidence intervals or universal speed claims are attached.

| Initial screen, n=128 | GHC | MLF crate | Ratio | Fresh top-level groups |
|---|---:|---:|---:|---:|
| Independent annotated functions | 0.627 | 2.218 | 3.54 | 131 |
| Annotated dependency chain | 0.569 | 2.041 | 3.59 | 131 |
| Inferred dependency chain | 0.583 | 2.508 | 4.30 | 131 |
| Mutually recursive ring | 0.707 | 1.600 | 2.26 | 4 |
| Monomorphic Box calls | 0.643 | 1.181 | 1.84 | 5 |
| Polymorphic Box calls | 0.649 | 1.457 | 2.24 | 5 |
| Skewed constructor tree | 0.651 | 1.152 | 1.77 | 4 |
| Balanced constructor tree | 0.638 | 1.157 | 1.82 | 4 |
| Generated literal table | 0.582 | 1.011 | 1.74 | 5 |
| Higher-order composition chain | 0.603 | 1.108 | 1.84 | 6 |

The minimal program takes GHC 0.558 s and MLF 0.893 s. Its MLF checked-to-LLVM
stage alone takes 0.530 s. This is a useful fixed-cost observation, not an
amount to subtract from other programs. None of the 41 cell medians favors
MLF on this particular route.

| Separate extension, n=512 | GHC | MLF crate | Ratio | Fresh top-level groups |
|---|---:|---:|---:|---:|
| Independent top-level functions | 1.149 | 8.106 | 7.06 | 515 |
| Same independent functions inside a local let | 0.980 | 5.295 | 5.40 | 3 |
| Annotated dependency chain | 0.827 | 7.575 | 9.16 | 515 |
| Inferred dependency chain | 0.747 | 9.345 | 12.52 | 515 |
| Mutually recursive ring | 1.450 | 4.502 | 3.10 | 4 |

The top-level/local pair preserves the functions' arithmetic bodies and
runtime-dependent result. Local functions are still inferred inside `entry`;
the smaller query count does not mean their bodies were skipped.

| MLF n=512 diagnostic | Top-level functions | Local functions |
|---|---:|---:|
| Source to checked wall | 6.521 | 1.767 |
| Source to checked user CPU | 2.741 | 1.624 |
| Source to checked system CPU | 2.834 | 0.067 |
| Checked to LLVM wall | 0.990 | 1.948 |
| LLVM to executable wall | 0.472 | 1.536 |

Each stage column is a separate median, so medians need not sum to whole-run
wall. Local placement increases later-stage work in this experiment. This is
why a frontend-only result would overstate the total effect. Cached query file
footprint also drops from about 66.8 MB to 1.98 MB. This is retained `.mlfq`
file size, **not measured cumulative disk traffic**.

## What this suggests investigating

1. **Per-group cache publication and context work.**
   `CrateSession.runSourceGroupsWithEncodings` writes/hashes a key, compiles and
   finalizes each missed group, and publishes its cache object.
   `CrateQuery.writeCache` currently launches a supervised `/bin/mv` for each
   publication. The 515-fresh-group cases therefore take this path at least
   515 times. The high system CPU and local/top-level control make this a
   concrete lead. They do not prove that all of the gap is process launch or
   that an atomic-file-operation change would save a particular percentage.
   A candidate must preserve publication failures, first-error order, resource
   supervision, key semantics and rollback behavior.
2. **Repeated per-group preparation, checking and serialization.**
   `compileLoweredGroupUsing` reconstructs external schemes, lowers the group,
   infers/elaborates/checks it, collects bindings and checks the resulting
   payload. Query format 1 intentionally retains a self-contained context for
   current source keys. Inspect repeated immutable work and its cost before
   proposing reuse; neither the checks nor the target's fresh work may be
   deleted. The cache-file volume is evidence of repeated representation, not
   a timing attribution to encoding.
3. **Fixed checked-to-LLVM cost.** The tiny-program floor deserves its own
   entry/path comparison, including the installed standard-library driver.
   It cannot be extrapolated from this bootstrap crate producer to all `emlf`
   invocations. Preserve the plain Clang `-O2` endpoint.

The tested tree shapes, rank-1 polymorphic calls and higher-order compositions
do not justify prioritizing them over the large top-level-group effect here.
They do not cover wide sums, difficult higher-rank constraints, class-instance
search, rejected programs, many-module DAGs, or the full compiler workload.
The current evidence narrows the next hypothesis; it does not establish a new
optimization gain on the real 14-module/full-compiler target or disprove the
existing C5 solver hypothesis. Any production change still needs the existing
semantic oracle and a fresh whole-compiler screen.

There is visible drift between cohorts: e.g. n=128 independent functions take
2.218 s in the first window and 2.715 s in the extension. Three repetitions are
not enough to resolve small percentage changes. Do not pool the windows,
infer an asymptotic exponent, or select a favorable stage as the main result.

## Reproduce

`prepare.py` accepts an authenticated ordinary `-O2` producer and an existing
checked builtin dependency. The producer must match the checkout, including
the retained authentication contract. The setup creates only a private GHC
package DB. Example from this experiment (run from the repository root):

```sh
python3 -B tools/performance/compiler-shapes/prepare.py \
  --producer .mlf-build/validation-reuse-integration-20261030/producer \
  --builtin-prefix .mlf-build/validation-reuse-integration-20261030/a1/builtin \
  --output .mlf-build/shapes-setup
python3 -B tools/performance/compiler-shapes/run.py \
  --setup .mlf-build/shapes-setup/setup.json \
  --output .mlf-build/shapes-screen
python3 -B tools/performance/compiler-shapes/run.py \
  --setup .mlf-build/shapes-setup/setup.json \
  --output .mlf-build/shapes-extension \
  --family flat_functions --family local_functions --family inferred_chain \
  --family dependency_chain --family recursive_ring --size 128 --size 512
python3 -B tools/performance/compiler-shapes/analyze.py \
  .mlf-build/shapes-screen .mlf-build/shapes-extension \
  --output .mlf-build/shapes-results
```

Use `--pilot` for untimed fixture qualification. The initial generator failed
two such checks because shared syntax requires explicit `forall`; the fixtures
were corrected and requalified before the timing window. Those failures and
their original scripts remain in `generator-pilot/`; they were not timing
samples. The local-let fixture was qualified before the separate extension.

`run.py` freezes its schedule and source hashes before samples, retains scripts
and per-command receipts, authenticates the producer before/after, and launches
one compilation pipeline at a time. Cases are shuffled with seed 20261031 and
the three paired rounds alternate which compiler runs first; start directions
are balanced across cases. Repeated target directories and query caches are
always fresh. No target warming or filesystem cache flushing is used.

The unchanged exact-child resource helper measures worker startup through
`wait4`; the small Python dispatcher is included on both sides. Compiler
subprocess stage wall and CPU are recorded without solver instrumentation.
Preparation, native output checks and file inventories are outside the timed
boundary and never overlap the next timed compilation. Resource guards retain
a 5 GiB disk floor, 3 GiB available-memory floor and sampled 5 GiB process-group
RSS ceiling; each leg is bounded at 90 seconds and 512 MiB output. The latest
runner also checks the 2 GiB aggregate output budget between legs. macOS does
not supply the Linux hard address-space guarantee and sampling may miss peaks.
The directory lock coordinates this runner, not unrelated programs on the Mac.

A failed/guarded execution is retained and stops further samples for that
case. It is never replaced. The analyzer refuses incomplete schedules,
duplicate/nonfinite data, qualification-only samples and missing fresh/raw-byte
evidence. Sources, artifacts and stdout/stderr are retained; only the isolated
query-cache copies are removed after inventory/hashing and correctness checks.

The offline `--plot` option additionally needs Matplotlib and the two original
cohort names (`screen`, `group-extension`). JSON/CSV analysis uses only the
Python standard library. Plotting dependencies for this run were installed in
the ignored experiment directory, after every timed sample had completed.

## Local evidence

The full retained experiment is in `.mlf-build/compiler-shapes-20261031/`:

- `screen/plan.json`, `screen/receipt.json`, `screen/legs/` and frozen scripts;
- `group-extension/plan.json`, `group-extension/receipt.json` and its legs;
- `results/summary.json`, `results/summary.csv`, `results/compiler-shapes.png`;
- `setup.json`, dependency build logs, producer authentication and fixture pilots;
- `reproduction-setup/` for qualification of the reusable setup script.

The analyzer's 41 median pairs and ratios were independently recomputed from
the raw receipts using sorted middle values. The figure was visually inspected.
No compiler implementation was changed by this experiment.
