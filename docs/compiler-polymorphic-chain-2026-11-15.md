# Inferred polymorphic dependency chains, 2026-11-15

This study starts from `590b8317` on `codex/flat-functions-performance`. That
commit records the previously qualified independent-polymorphic-function
optimization before any compiler change for this dependency-chain experiment.

## Workload and fixed acceptance

The opt-in `inferred_poly_chain` family defines N unsigned functions:

```haskell
f0 step y = step y
f1 step y = step (f0 step y)
f2 step y = step (f1 step y)
```

Each later function refers to its immediate predecessor once, forming a strict
acyclic chain. The annotated entry uses the final function at both `Int` and
`Bool`: integer increment and Boolean negation are each applied N times. All
generated functions are reachable. The entry and IO harness retain signatures,
consistently with the earlier studies. Both compilers consume identical source
bytes; the default ten-family matrix is unchanged.

For runtime input x, the expected integer is x+N. Its sign is positive when
`(x < 0) XOR (N is odd)` and negative otherwise. This closed-form oracle is
independent of compiler output. The runtime inputs are -1, 0 and 7. Generator
tests additionally cover odd and singleton chains using a separate iterative
oracle, dependency edges and both type-specific uses.

The premeasurement plan fixes N=32,64,128,256,512, plus an empty-program baseline,
with six fresh compilations per compiler per cell: 72 compilations and 216
runtime checks. Acceptance requires every positive-size MLF median, the endpoint
incremental slope and the OLS slope with an intercept to be below paired GHC.
Exploratory screens are separate from formal acceptance cohorts. A finite-range
slope is not a proof of asymptotic complexity or a guarantee for every adjacent
interval or other program shape.

The original measured endpoint is `crate-bootstrap-v1`: authenticated GHC-hosted MLF O2
through checked crate and LLVM to a Clang O2 executable, versus GHC 9.14.1
`--make -j1 -O2 -fforce-recomp`. Fixed builtin, primitive package and runtime
setup remain outside timing. The GHC primitive package is built from that
candidate checkout's host adapters and pinned within its cohort; host-adapter
changes therefore also change that package between compiler versions, while
its public primitive ABI remains unchanged. Historical before/after deltas are
not an isolated measurement of one compiler component. Every target and
inference cache is fresh, paired
lane order alternates, and existing resource guards remain unchanged. The host
is an Apple M1 Max on macOS, using Clang 23.1.3; OS caches are not flushed.

## Baseline and implementation

The archived six-repeat baseline measured the following median seconds:

| N | MLF checkpoint | GHC |
| ---: | ---: | ---: |
| 0 | 0.4290 | 0.5574 |
| 32 | 0.5569 | 0.6006 |
| 64 | 0.6492 | 0.5930 |
| 128 | 0.8657 | 0.6119 |
| 256 | 1.3865 | 0.6972 |
| 512 | 2.6351 | 0.8323 |

Its OLS slope was 4.3668 ms/function versus 0.5148 for GHC. This workload exposes
both repeated polymorphic elaboration and expansion of the nested iterator
calls in the checked optimizer. After those costs were reduced, artifact
encoding, decoding and their temporary allocation became substantial costs.

The retained changes are:

- Extend owned delayed substitution to at most three occurrences. Queue fresh
  copies in the original occurrence order; preserve the public raw optimizer.
- Reuse an opaque checked inference template only for matching resolved source,
  closed polymorphic dependency schemes and datatype context. Keep each
  declaration's query key and dependency reads. Raw template payloads share a
  normalized body, with exact structural keys and content-addressed integrity.
- Recognize checked pure iterators and fold literal Int64 add/subtract and Bool
  negation callbacks. Preserve scopes, wrapping arithmetic, unknown/effectful
  callbacks and bounded count fallback.
- Memoize one identical type-syntax hash with exact work charging; retain an
  opaque metadata hash receipt only when its complete input value still matches.
- Use unboxed host IntArray cells, inline the existing ordered host accessors,
  and expose total integer literals through GHC's ordering barrier. Unknown
  operands and continuations retain their barriers. The final host ByteArray
  uses pinned, GC-managed unboxed storage for scalar access, with explicit owner
  lifetime protection for bulk pointer callbacks; file/digest snapshots remain.
- Carry one bounded exact contract-value hash between declarations and reuse
  the already computed immutable inference-template key. Every declaration
  still records its own Binding and FinishScc nodes and dependency reads.
- Inline the existing ordered bit primitives. For buffers of at least 16 KiB,
  advance CRC32 four bytes at a time using four tables derived from the original
  recurrence. Smaller buffers keep their original paths. The checksum field is
  still logically zero, and neither the wire version nor primitive ABI changes.
- Pack owned bitstream output a complete byte at a time, use exact-equality hash
  buckets for decoder node lookup, and reuse validated graph work summaries.
  Public planner state and the public low-level encoder keep their old behavior.
- Admit small internal rebuilt-receipt trees through conservative resource upper
  bounds; larger values retain the original planner. Group ASCII fingerprint
  input without changing the canonical recurrence or the signed/indexed API.

Private screens retained exact checkpoint `.mlfci` and `.mlfco` bytes. LLVM
changes from iterator simplification are intentional and checked against
independent runtime outputs. The first generated function has type
`forall a b. (a -> b) -> a -> b`; subsequent functions have type
`forall a. (a -> a) -> a -> a`. The first function must not be restricted to the
subsequent scheme merely to simplify caching.

## Separate retained-root endpoint

After the original two-stage path was faster at every sampled size but still
had a steeper slope than GHC, a separate plan was recorded in
`acceptance-fused-plan.json` before implementing or measuring the new entry.
`crate-fused-v1` invokes
`emlf --compile-crate-to-llvm-gc SPEC -o UNIT`, followed by the same Clang link.
The source, query publication, checked artifacts and native runtime checks are
unchanged. The compiler retains the checked root through linking and LLVM
emission; it avoids a second compiler startup and re-decoding its own root.
Dependency objects still undergo ordinary integrity and interface checks.

This is an explicit driver improvement. It does not establish that the original
`crate-bootstrap-v1` endpoint meets the slope target. Both final endpoints are
measured separately; their MLF samples and their paired GHC samples are never
pooled. Each uses the original N range, six repetitions and all three fixed
acceptance criteria. Neither is the installed `emlf SOURCE -o` native driver.

## Rejected experiments

Retained exploratory logs include changes that were reverted: more aggressive
substitution rewrites, compact name-hint serialization, fragment bundling,
planner hash indexing, bulk text planning, cached
context rendering, a fixed CRC table, writer IO wrappers, dense decoder slots,
interface-encoding equality, larger speculative symbol scans, loop unrolling,
and larger GHC nursery defaults. Their gains were absent, noisy or too small
for their added complexity. Later paired screens also rejected string-comparison
inlining, a specialized entry-tree loop and a bounded planner lookup memo.
Public planner demand behavior was restored. The earlier pinned-ByteArray screen
was inconclusive; a new paired screen on the current host loops supported the
final storage change, with the GC and error-order controls described below.
A private C bulk-IO prototype was diagnostic only and introduced no production
primitive or C runtime change. A GHC LLVM-host build was stopped because the
installed LLVM version is outside that GHC's supported range.

## Intermediate formal results (not accepted)

Both complete producer-v2 cohorts and both producer-v3 cohorts were retained.
They were faster than paired GHC at every positive size but failed the two
fixed slope criteria. No sample was relabelled, pooled across endpoints or
replaced to turn those cohorts into a pass. Slopes below are ms/function:

| Producer | Endpoint | MLF OLS | GHC OLS | MLF endpoint | GHC endpoint |
| --- | --- | ---: | ---: | ---: | ---: |
| v2 | two-stage | 0.6742 | 0.5468 | 0.6850 | 0.5555 |
| v2 | single invocation | 0.5375 | 0.5215 | 0.5461 | 0.4984 |
| v3 | two-stage | 0.6347 | 0.4719 | 0.6434 | 0.4642 |
| v3 | single invocation | 0.5064 | 0.5009 | 0.5134 | 0.4968 |

The v3 single-invocation cohort measured 0.6200 s at N=512 versus 0.8120 s
for GHC, yet its OLS slope was still 1.1% higher and its endpoint slope 3.3%
higher. Its descriptive 95% paired bootstrap interval for MLF minus GHC OLS
was [-0.0380, 0.0356] ms/function: it does not establish a slope difference.
These were failed point-estimate acceptance results, not a reason to claim
that either compiler has a worse asymptotic complexity.

A fresh v3 profile at N=32 and N=512 isolated roughly 29 ms of extra sampled
CPU time in CRC and 22 ms in aligned text output. These are diagnostic profile
estimates, not final wall-time measurements. The final changes were then
screened in separate paired runs before rebuilding the authenticated producer.
A checksum-only diagnostic included table construction in each timed call:
at 4 KiB, one-table/four-table medians were 82.5/85.5 us; at 16 KiB, 343/215 us;
at 1 MiB, 16.890/9.082 ms. This supports retaining the small-buffer path and
using a 16 KiB threshold, rather than changing the measured program sizes.

The v4 builtin regeneration changed only its source-identity witness line
relative to v3; the generated payload remained identical. The fixed benchmark
builtin artifacts, GHC/Clang flags, runtime and resource guards remain the same.

## Results and validation

The final authenticated producer-v4 cohorts give the following median seconds.
Each endpoint has its own six paired repetitions; the GHC columns are separate
measurement windows, not interchangeable baselines.

| N | MLF single invocation | Paired GHC | MLF two-stage | Paired GHC |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 0.3476 | 0.5660 | 0.4055 | 0.5733 |
| 32 | 0.3782 | 0.5859 | 0.4387 | 0.5958 |
| 64 | 0.4085 | 0.6277 | 0.4696 | 0.6186 |
| 128 | 0.4228 | 0.6221 | 0.4860 | 0.6420 |
| 256 | 0.4929 | 0.7333 | 0.5441 | 0.6472 |
| 512 | 0.6067 | 0.8297 | 0.7004 | 0.7895 |

Slopes exclude the empty baseline and use N=32..512. The endpoint slope is
`(median(512) - median(32)) / 480`; OLS includes an intercept.

| Endpoint | MLF OLS (ms/function) | GHC OLS | MLF endpoint | GHC endpoint | All three criteria |
| --- | ---: | ---: | ---: | ---: | --- |
| Single invocation | 0.46625 | 0.50405 | 0.47590 | 0.50806 | pass |
| Two-stage | 0.52930 | 0.37672 | 0.54519 | 0.40362 | fail: both slopes |

The single-invocation point estimates satisfy the predeclared criteria: positive
size medians are 26.9–35.4% below paired GHC, the OLS slope is 7.5% lower and the
endpoint slope is 6.3% lower. At N=512 it takes 0.6067 s versus 0.8297 s.
The archived checkpoint took 2.6351 s through the two-stage endpoint; that
historical comparison is a 77.0% reduction with the endpoint change explicitly
included. The final two-stage time is 0.7004 s, a 73.4% reduction from that
checkpoint, but its slopes still fail the target.

The descriptive 95% paired bootstrap interval for single-invocation MLF minus
GHC OLS is **[-0.13435, 0.00183] ms/function** (10,000 draws, fixed seed 20261115).
It slightly crosses zero. Thus the fixed point-estimate gate passes, but this
cohort does not establish a statistically resolved slope advantage. The
two-stage interval is [0.05888, 0.23830] ms/function. Sizes were measured in
separate blocks; six repetitions do not remove between-window variation.
Neither result proves lower asymptotic complexity. No extra repetitions were
added after looking at these results.

The [single-invocation curve](../.mlf-build/compiler-poly-chain-20261115/final-v4/final-fused-results/chain-scaling.png)
and [two-stage curve](../.mlf-build/compiler-poly-chain-20261115/final-v4/final-two-stage-results/chain-scaling.png)
show medians with observed min/max whiskers. Their right panels show the current
cohort's extra time over N=32, keeping the archived checkpoint out of that panel.

All 28 required steps in the final study completed successfully:

- Authenticated O2 producer build, exact builtin regeneration, shared frontend
  and direct compiler/native smoke, 55 field-layout checks, and locked plan.
- Six CLI suites cover signed, inferred and polymorphic-chain declarations
  through both entries, including cache reuse, ICH verification, corrupt shared
  payload recovery, dependency invalidation and disk-link LLVM parity.
- Both O0/O2 optimizer differential suites and the 47-command focused host/codec
  run passed. Controls include 42 independent zlib CRC vectors, short-buffer
  failures, checksum-field masking, exact wire bytes, bounded hash-cache
  fallbacks, frozen ByteArray values and errors, IO action laziness, GC pointer
  ownership and binary file snapshots.
- Query-index/publication controls and 29 source SCC checks passed. Native IO
  sharing controls and 40 odd-chain/Int64-boundary executable checks passed.
- Each endpoint completed 72 timed compilations and 216 independent executable
  output checks. Its separate six-family regression cohort completed another
  42 compilations and 126 output checks, covering the preceding independent
  function families, recursive rings, inferred chains and polymorphic calls.
- All 992 generated polymorphic exports across the five sizes retain their
  checkpoint types up to alpha-equivalence and their exact protection inventory.
  All 81 benchmark harness tests passed.

The first frozen-IO fixture compilation exited successfully but emitted the
known bytestring `hGetLine` deprecation warning; the strict harness rejected
that stderr. Its source stayed frozen, and the next test driver suppressed only
that fixture's deprecation warning. The failed receipt and driver are retained.
The old fingerprint fixture also has a recorded observer-type adaptation for
the current Int64 host API; its frozen oracle hash remains unchanged. The
historical 2026-11-01 mechanism-counter workflow is deferred because its exact
producer/source/text-format corpus is unavailable. This study makes no new
logical-traversal-counter claim from that workflow.

The native `./mlfpkg --locked build` was attempted and reports that the native
package manager must first be built. This experiment therefore qualifies the
GHC-hosted endpoint, not a native compiler installation or its release gate.

## Evidence

Retained evidence lives in `.mlf-build/compiler-poly-chain-20261115/`, beginning
with `acceptance-plan.json`, `baseline-study.json` and the separate pilot and
formal baseline cohorts. The baseline producer is the authenticated
`compiler-poly-flat-20261115/producer-v3` whose compiler sources match the
starting commit exactly.

Final evidence is in `final-v4/`: `final-study.json`, the two endpoints' separate
`cohorts/chain-final/{plan,receipt}.json`, `cohorts/regression-smoke/receipt.json`,
`final-{fused,two-stage}-results/chain-comparison.json`, PNG/SVG plots, and
`type-parity/receipt.json`. `qualification.json` authenticates the producer,
checks all required receipts, and records the final changed-file hashes.
`verify-final.py` is the local qualification driver. Intermediate failures stay
in the root and `final-v3/`; the exploratory screens and profiles remain separate.

To reproduce with fresh output directories from this checkout:

```sh
python3 -B tools/shared/build.py --bootstrap-only --optimization 2 \
  --ghc /Users/ares/.ghcup/bin/ghc-9.14.1 \
  --cc /opt/homebrew/opt/llvm/bin/clang \
  --build-dir "$PWD/.mlf-build/poly-chain-reproduction-producer"
python3 -B tools/performance/compiler-shapes/bench.py prepare \
  --endpoint crate-fused-v1 \
  --workdir "$PWD/.mlf-build/poly-chain-reproduction" \
  --producer "$PWD/.mlf-build/poly-chain-reproduction-producer" \
  --builtin-prefix "$PWD/.mlf-build/compiler-shapes-scaling-20261114-fc300bc9/setup/builtin" \
  --ghc /Users/ares/.ghcup/bin/ghc-9.14.1 \
  --clang /opt/homebrew/opt/llvm/bin/clang
python3 -B tools/performance/compiler-shapes/bench.py run \
  --endpoint crate-fused-v1 \
  --workdir "$PWD/.mlf-build/poly-chain-reproduction" --cohort chain \
  --family inferred_poly_chain \
  --size 32 --size 64 --size 128 --size 256 --size 512 --repeats 6
python3 -B tools/performance/compiler-shapes/bench.py analyze \
  --workdir "$PWD/.mlf-build/poly-chain-reproduction" --cohort chain
```

Use `crate-bootstrap-v1` and another fresh work directory for the two-stage
endpoint. The builtin prefix above is the original pinned local artifact;
another machine must prepare its own fixed builtin and record that as a new
cohort, rather than claim it is the original experiment. Final source changes
remain uncommitted after the requested checkpoint commit.
