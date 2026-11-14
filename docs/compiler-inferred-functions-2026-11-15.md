# Inferred independent-function compilation, 2026-11-15

This study starts from `829fe756790cc204c71122560697bc3893f85070` on the existing
`codex/flat-functions-performance` branch, which already includes the signed-function
optimization above main `fc300bc9fdc389b585cbef0630fc8915d53e89c5`. The new opt-in
`inferred_functions` family removes exactly the N generated `fN :: Int -> Int`
signatures from `flat_functions`. Function bodies, balanced aggregation, runtime
inputs and independent arithmetic oracles stay identical. The entry/IO harness
retains its annotations. These functions infer closed `Int -> Int` types; this
study does not claim performance for every polymorphic unsigned function.

## Method and baseline

Both compilers consume the same source bytes. The endpoint remains
`crate-bootstrap-v1`: GHC-hosted MLF O2, source to checked crate, LLVM, then a
Clang O2 executable. GHC 9.14.1 uses `--make -j1 -O2 -fforce-recomp`. Fixed
Prelude, primitive package and runtime setup is outside the timed legs.
The same resource limits, alternating paired schedule and correctness oracles
apply. Every leg gets fresh target outputs and an empty inference cache.
OS page caches are not flushed. macOS RSS enforcement is sampled.

The acceptance plan was saved before measuring: N=32,64,128,256,512, six
repetitions per lane, plus the empty baseline. Every size must have a lower MLF
median than GHC; both the endpoint incremental slope and OLS slope with an
intercept must be lower. This is a finite-range criterion, not a Big-O proof.
Screens are exploratory and cannot substitute for the final complete cohort.

| Functions | Starting MLF (s) | Paired baseline GHC (s) |
| ---: | ---: | ---: |
| 32 | 0.638 | 0.574 |
| 64 | 0.854 | 0.614 |
| 128 | 1.262 | 0.737 |
| 256 | 2.100 | 1.028 |
| 512 | 3.789 | 1.878 |

Starting slopes are 6.559 ms/function for MLF and 2.745 for GHC. At N=512,
MLF's source-to-checked median is 2.974 s. A separate phase-clock run attributed
1.765 s to graph preparation and 0.541 s to inference/recording. Instrumented
GHC cost-centre profiling attributed about 60% of sampled CPU to discarded
scope binary encoding; those instrumented times and allocations are diagnostic,
not normal compiler measurements.

## Implementation

- Scope inventory and scope-read values use complete domain-separated text
  framing after ordinary wire bounds validation. Each scope lane keeps just
  its preceding validated value and digest. Structural equality reuses that
  digest without constructing an encoding before bounds checking; each query
  still records its own key and dependency edges.
- Unsigned, nonrecursive monotypes may use partial synthesis. Only known closed
  call domains constrain lambda parameters. Undetermined variables, unknown
  callees, local generalization, polymorphic imports and unsupported syntax
  use the existing solver. The synthesized type is checked again by the existing
  monotype elaborator and independent xMLF checker. No default type or unchecked
  fragment is manufactured.
- Unsigned lowering retains the full definition scope. If it produces no
  evidence slots, finalization cannot consult candidate evidence, so unused
  candidates and their layouts no longer enter that query. Actual references
  remain binding/layout dependencies. Any evidence slot preserves the complete
  conservative candidate inventory and all provenance checks.
- Open-fragment owners use the versioned, length-framed crate and full sorted
  ownership set. They avoid decimal-escaping names that were already escaped.
  Reading validates the exact set and retains the previous legacy owner check.
  Separate-unit identifiers and binary payload checksums are unchanged.

The benchmark family is opt in; the default matrix and its costs stay fixed.
The existing SourceSCC fixture's obsolete ten-field pattern was corrected to
match the current eight-field SourcePlan. It still poisons exactly the old
whole-program lowering field, preserving that regression's original purpose.
Its local test linker also now merges the private datatype declarations of
predecessor bodies that it inlines. The original helper stripped these contexts
and relied on the consumer incidentally retaining unused candidate layouts.
The archived compiler passed that helper; the optimized compiler exposed its
missing `Make_Tag` declaration. Merging and validating the imported declarations
repairs the helper without changing the runtime or ABI oracles.

## Final results

All three frozen acceptance criteria passed. These are medians of six fresh
compilations per lane; GHC here is the paired final cohort, not the earlier
baseline GHC samples.

| Functions | Starting MLF (s) | Final MLF (s) | Final GHC (s) | MLF time below GHC |
| ---: | ---: | ---: | ---: | ---: |
| 32 | 0.638 | 0.453 | 0.526 | 13.7% |
| 64 | 0.854 | 0.515 | 0.571 | 9.7% |
| 128 | 1.262 | 0.633 | 0.673 | 5.9% |
| 256 | 2.100 | 0.854 | 0.964 | 11.4% |
| 512 | 3.789 | 1.359 | 1.764 | 22.9% |

The OLS slope with an intercept falls from 6.559 to **1.878 ms/function**;
paired GHC is **2.607 ms/function**, so MLF's overall slope is 28.0% lower.
The independent endpoint measure `(T(512)-T(32))/480` is 1.887 versus
2.580 ms/function, 26.9% lower. A descriptive 10,000-draw paired-round bootstrap
gives [-0.789, -0.693] ms/function for the MLF-minus-GHC OLS slope difference.
This interval summarizes six rounds; it is not a general complexity bound.

At N=512, total MLF time is 64.1% below the starting cohort. The median
source-to-checked stage falls from 2.974 to 0.660 s; final LLVM and Clang stage
medians are 0.339 and 0.314 s. Stage medians do not sum exactly to the full-leg
median, which also includes driver work. The empty baseline is 0.409 s for MLF
and 0.496 s for GHC.

All 72 compilations and 216 native runtime oracles passed without guard
failures or inference-cache hits. The claim concerns this fixed family and
N=32..512. It does not establish a better Big-O bound or a uniformly lower
local derivative: the N=32..128 incremental rise is still larger for MLF.

The plot and complete numeric analysis are retained in
`.mlf-build/compiler-inferred-flat-20261115/results/inferred-scaling.png` and
`results/inferred-comparison.json` under the same evidence root. Plot error bars
show the observed minimum and maximum, not confidence intervals.

## Validation

- Fresh authenticated O2 producer: all 137 shared modules, inferred-interface
  and source checks, exact Prelude regeneration verification.
- Benchmark contract suite: 75 tests, including exact signature removal,
  unchanged default matrix and independent new/legacy owner validation.
- Signed and inferred cache controls: 24 commands and 15 assertions each,
  including cold/warm reuse, selective invalidation, corrupt-payload recovery,
  publication rollback and physical builtin admission. Both check dictionary
  results through `--run-crate`.
- Field-layout regression: all five commands passed. The query-index fixture
  passed its exact legacy/v2 encoding, bounded decoder and publication-failpoint
  checks. SourceSCC passed all 29 PASS lines, including dictionary proof/layout
  dependencies and managed support protection. Its repaired test linker also
  passed against the archived starting compiler.
- Authenticated direct suite: all 12 commands passed, including frozen async,
  frontend and build-receipt expectations. Lock regeneration and locked plan
  succeeded.
- Supplementary N=8 cohort: signed independent functions, a recursive ring,
  an inferred dependency chain and polymorphic calls, three repetitions per
  lane plus the baseline. All 30 compilations and 90 native runtime oracles
  passed. These results are separate from the acceptance cohort.

All exploratory attempts and the rejected SourceSCC test-helper run are
retained. The broad legacy source-context harness was not rerun here; the
[signed study](compiler-flat-functions-2026-11-14.md) records its prior scratch
cleanup failure. No claim is made that every historical gate is green.
`./mlfpkg --locked build` still reports a missing native package manager, so
native self-hosting and the installed-driver endpoint remain unqualified.

## Evidence and reproduction

All evidence is under `.mlf-build/compiler-inferred-flat-20261115/`:
`acceptance-plan.json`, `baseline/cohorts/inferred-baseline/`, `screens/`,
`producer/`, `final-study.json`, `final-study-resumed.json`,
`extra-controls-v2/receipt.json`, `qualification.json`, and
`final/cohorts/inferred-final/`.
The offline comparison is `analyze-inferred.py`; raw receipts and per-stage logs
are retained, and different cohorts are never pooled into one median.

```sh
python3 -B tools/shared/build.py --bootstrap-only --optimization 2 \
  --ghc /Users/ares/.ghcup/bin/ghc-9.14.1 \
  --cc /opt/homebrew/opt/llvm/bin/clang --build-dir NEW_PRODUCER
python3 -B tools/shared/test_flat_compiler.py --inferred \
  --build-receipt NEW_PRODUCER/receipt.json \
  --builtin EXISTING_BUILTIN_PREFIX --output NEW_CONTROLS
python3 -B tools/performance/compiler-shapes/bench.py prepare \
  --producer NEW_PRODUCER --builtin-prefix EXISTING_BUILTIN_PREFIX \
  --ghc /Users/ares/.ghcup/bin/ghc-9.14.1 \
  --clang /opt/homebrew/opt/llvm/bin/clang --workdir NEW_BENCH
python3 -B tools/performance/compiler-shapes/bench.py run \
  --workdir NEW_BENCH --cohort inferred-final --family inferred_functions \
  --size 32 --size 64 --size 128 --size 256 --size 512 --repeats 6
python3 -B tools/performance/compiler-shapes/bench.py analyze \
  --workdir NEW_BENCH --cohort inferred-final
```
