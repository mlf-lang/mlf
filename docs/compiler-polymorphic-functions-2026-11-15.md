# Inferred polymorphic independent functions, 2026-11-15

This experiment starts from `115954a5` on the existing
`codex/flat-functions-performance` branch, after the signed and inferred-monotype
optimizations. It measures the new opt-in `inferred_poly_functions` family.

## Workload and acceptance

N independent functions rotate four unsigned definitions: identity, constant,
application and composition. None refers to another generated function. Each
is used at both `Int` and `Bool` in the same program. Runtime input controls a
conditional sign, and every function contributes to a balanced sum. The entry
and IO harness retain their signatures, consistently with the earlier studies.
This measures complete programs with polymorphic definitions and their uses;
it does not isolate the time of generalizing declarations alone.

The independent expected output is
`N*x + N*(N-1)/2 - 2*(k*x + k*(k-1)/2)`, where
`k = max(0, min(N, x+1))`. Runtime inputs are -1, 0 and 7. No compiler output is
used to generate this oracle. The default ten-family matrix is unchanged.

The premeasurement acceptance plan fixes N=32,64,128,256,512, six repetitions
per compiler and cell, and an empty baseline: 72 compilations and 216 runtime
checks. Every positive-size MLF median, the endpoint incremental slope and the
OLS slope with an intercept must be below GHC. Screens are exploratory and never
pooled into acceptance medians. These are finite-range criteria, not a Big-O
proof or a requirement on every adjacent interval.

Both compilers consume identical source bytes. The endpoint is
`crate-bootstrap-v1`: authenticated GHC-hosted MLF O2 to checked crate, LLVM,
then a Clang O2 executable; GHC 9.14.1 uses `--make -j1 -O2 -fforce-recomp`.
Fixed primitive package, builtin pair and runtime setup are outside timing.
Every target and inference cache is fresh, paired lane order alternates, and
the existing resource guards are unchanged. OS page caches are not flushed.

## Baseline and diagnosis

| Functions | Starting MLF (s) | Baseline GHC (s) |
| ---: | ---: | ---: |
| 32 | 0.702 | 0.657 |
| 64 | 1.007 | 0.746 |
| 128 | 1.607 | 1.015 |
| 256 | 2.862 | 1.852 |
| 512 | 5.467 | 4.813 |

The initial OLS slopes are 9.936 and 8.761 ms/function. The acceptance assertion
fails on all three criteria against this baseline. All baseline compilations
and runtime checks pass; its failure is performance, not program correctness.

At N=256, source-to-checked takes a median 2.053 s. A separate ordinary phase
clock attributes 1.545 s to inference/recording, versus 0.055 s to graph setup.
A separate instrumented cost-centre run attributes about 45% of CPU to solving,
including about 30% in instance expansion. Instrumented time and allocation
totals are diagnostic and are not included in compiler timing comparisons.

## Change and semantic boundary

`InferenceUnit.groundIndexed` adds a partial specialization route for a signed
closed monotype. Its temporary type variables separate each use of an imported
scheme. First-order constraints and an occurs check determine the required
monotypes; non-bottom MLF bounds also contribute constraints. Sealing resolves
lambda and instance types and constructs explicit instance computations for
each quantifier, including recursively instantiated bounds. `Open.check`
independently checks the complete implementation and exported type before a
fragment can be admitted.

Unbound variable roots merge by rank. A real 256-deep polymorphic-call spine
initially exposed a linear alias chain; the regression now bounds that depth
and checks the sealed term with the frozen independent checker. This prevents
repeated alias walks from introducing quadratic work in that case.

The generated unsigned functions retain their original generalization path.
In particular, MLF's constant and composition schemes have bounded quantifiers;
the optimization does not replace them with narrower rank-1 schemes. It removes
unnecessary generalization-graph work when the annotated consumer needs fully
determined instances. It adds no default types, inference-result memoization or
unchecked checked-IR constructors. Ambiguity, higher-rank arguments, local
generalization, unsupported forms and failed checks use the existing solver.

The focused route test first failed at `ground imported identity route`.
Differential controls compare types and erasures against the ordinary solver,
then check both terms using the frozen independent checker. Controls include
separate Bool/Int instantiations, bounded constant/composition, resolved IDs,
ambiguous arguments, higher-rank fallback and rejection of an incompatible
non-bottom bound. Rejected development attempts are retained.

## Final results and validation

All three predeclared performance criteria pass. The final cohort completes
72 compilations and all 216 runtime checks, without a resource-guard failure.
These are medians in seconds from six fresh builds per compiler and size:

| Functions | Optimized MLF (s) | Paired GHC (s) | MLF time below GHC |
| ---: | ---: | ---: | ---: |
| 32 | 0.512 | 0.576 | 11.1% |
| 64 | 0.631 | 0.681 | 7.4% |
| 128 | 0.882 | 0.956 | 7.8% |
| 256 | 1.395 | 1.719 | 18.8% |
| 512 | 2.492 | 4.565 | 45.4% |

At every positive size even the largest of the six MLF observations is below
the smallest GHC observation. At N=512, MLF takes 54.4% less time than its
archived starting baseline. GHC is remeasured alongside the candidate; the
starting and final cohorts are not pooled. The final empty-program medians are
0.400 s for MLF and 0.509 s for GHC.

The OLS slope over N=32..512 is **4.133 ms/function for MLF versus 8.374 for
GHC**, a 50.6% reduction. The endpoint incremental slope is 4.125 versus
8.311 ms/function, a 50.4% reduction. Independently resampling six balanced
MLF/GHC pairs within each size, with 10,000 draws and seed 20261115, gives a
descriptive 95% percentile interval of [-4.360, -4.186] ms/function for the
MLF-minus-GHC OLS slope difference. This interval describes the observed run;
it is not a guarantee for other machines, programs or sizes. In particular,
the 32-to-64 local increment is slightly larger for MLF even though its total
time is smaller at both points. The accepted slope claim is over the full
predeclared range.

At N=256, source-to-checked falls from the starting median 2.053 s to 0.710 s.
The final checked-to-LLVM and LLVM-to-executable medians are 0.296 s and 0.343 s.
Thus the improvement includes substantially less frontend work, rather than
only a smaller fixed startup cost. These measurements establish the finite
growth curve; they do not prove a new asymptotic complexity class.

The graph is retained as `results/poly-scaling.png` and `.svg` in the evidence
directory. Its left panel shows median total times with observed min/max bars;
the right subtracts each compiler's N=32 median to show measured growth.

The fresh GHC-hosted O2 producer checks all 137 shared modules and exactly
regenerates the canonical builtin artifact. The complete direct suite passes,
including frontend, native-first and native-second cases. Both existing signed
and inferred-monotype controls pass 15 assertions and 24 commands each; field
layout controls pass 55 checks. Query-index roundtrip/publication/failpoint
controls and the 29 SourceSCC checks also pass. The benchmark contract suite
passes 77 tests.

The additional shape smoke cohort passes 36 compilations and 108 runtime checks
across the baseline and signed independent, inferred-monotype independent,
recursive-ring, inferred-chain and polymorphic-call families. The final
authenticated objects also compare the original and optimized interfaces at
all five positive sizes: complete exported type inventories are alpha-equivalent,
protection inventories are identical, and every one of the 992 generated
function exports remains explicitly quantified. Lock regeneration and the
locked package plan both pass.

The repository's native `./mlfpkg --locked build` was attempted and reports
that the native package manager must first be built. No native seed is
installed during this study. Consequently this is qualification of the
authenticated GHC-hosted compiler endpoint, not the native compiler or the
full native package-manager release gate.

## Evidence and reproduction

Evidence is retained under `.mlf-build/compiler-poly-flat-20261115/`, including
`acceptance-plan.json`, `baseline/cohorts/poly-baseline/`, `profile-baseline-256/`,
`cost-baseline-256/`, `screens/ground/`, `producer-v3/` and `final-study.json`.
`results/poly-comparison.json` contains unrounded medians, ranges, stage times,
slopes and acceptance checks. `qualification.json` authenticates the final
producer and pins source, analysis and validation receipts. The private
development probes are separate from the authenticated final run. All samples,
including exploratory and rejected attempts, remain available.

```sh
python3 -B tools/shared/build.py --bootstrap-only --optimization 2 \
  --ghc /Users/ares/.ghcup/bin/ghc-9.14.1 \
  --cc /opt/homebrew/opt/llvm/bin/clang --build-dir NEW_PRODUCER
python3 -B tools/performance/compiler-shapes/bench.py prepare \
  --producer NEW_PRODUCER --builtin-prefix EXISTING_BUILTIN_PREFIX \
  --ghc /Users/ares/.ghcup/bin/ghc-9.14.1 \
  --clang /opt/homebrew/opt/llvm/bin/clang --workdir NEW_BENCH
python3 -B tools/performance/compiler-shapes/bench.py run \
  --workdir NEW_BENCH --cohort poly-final --family inferred_poly_functions \
  --size 32 --size 64 --size 128 --size 256 --size 512 --repeats 6
python3 -B tools/performance/compiler-shapes/bench.py analyze \
  --workdir NEW_BENCH --cohort poly-final
```
