# Checked cold bootstrap memory — 2026-10-19

> Historical evidence notice: Raw files previously stored under
> `tools/profile/results/` were removed from this branch and its Git history.
> References to those files below describe historical evidence that is not
> available in this repository; retained summaries are not independent access
> to the original raw records.


This report measures the earlier per-module pipeline. The current crate
migration and its validation are recorded in [the migration ledger](../../docs/crate-migration.md).
The measurements below retain their original source and test provenance.

The measured compiler target used checked separate compilation, with the native
package manager still source-linked. Three alternating cold build pairs on
identical compiler/runtime sources measured median sampled aggregate RSS of
**9,994,472,504 → 3,269,801,760 bytes** (67.283899% lower), with a candidate
maximum of **3,275,260,344 bytes**. Per-command RSS medians fell from
9,772,531,712 to 2,612,903,936 bytes. Fresh runtime C, Clang `-O2` LLVM
compilation, and linking remain inside the complete build boundary; every
native build report records zero cache hits.

Local median complete build time increased **332.38s → 460.87s** (38.657561%).
Ranges were 324.25–403.17s / 459.68–470.15s; MADs were 8.13s / 1.19s.
This improves memory headroom for the requested 7 GB runner, with a measured
local time cost. It does not establish a hosted speedup or explain the
historical hour-long CI job. Compiler checks and test implementations are
unchanged. The CI helper now enforces a 5.5 GB per-command RSS budget before
passing a candidate to later stages; the paired driver also gates sampled
aggregate RSS.

All six native groups passed on the same candidate and 426-file source
snapshot, including an entirely fresh LLVM/binary self-host fixed point and
both backend layouts. All nine workloads emit byte-identical LLVM in both
layouts. Primary-log hashes, every matrix row, and unchanged source/tool
identities were independently audited; raw evidence is retained in the report.

The [hosted cold bootstrap](https://github.com/mlf-lang/mlf/actions/runs/39169819058)
also passed on the actual 7 GiB, three-CPU Apple M1 virtual runner: **995.59s**,
**2,733,703,168 bytes maximum process RSS**, with all 48 cache decisions misses.
Both LLVM modules and executable hashes exactly match the locally tested
candidate. This confirms the runner fit; one hosted observation does not prove
a paired speedup or the cause of the historical hour-long run.

See the [full report and reproducible commands](results/2026-10-19-bootstrap-memory/README.md),
[all samples and variation](results/2026-10-19-bootstrap-memory/pairs/summary.json),
and [exact frozen source/tool identities](results/2026-10-19-bootstrap-memory/pairs/context.json).
This stock native module-built compiler has SHA-256
`d207c9a8988f9163c3ded6f9eca13f10452bfcf6e7ac93ea42a73924822b0bc6`;
the historical PGO results below retain their original binary/input scope.

# Native compilation optimization — 2026-10-18

All nine workloads pass the median 3× C compilation / 2× C runtime gate, with every observed maximum MLF sample also below the limit relative to the corresponding minimum C sample.

These are seven-sample **per-workload** decisions. No averages or rounded ratios determine the gate. The [native report](results/2026-10-18-compile3/bench-final.json) retains all 189 compilation and 189 timed runtime samples across candidate MLF, baseline MLF and C. Each exact executable receives an untimed, output-checked run before its timed runtime. C and MLF receive the same warm-up treatment. Raw correctness/warm-up process records and [output hashes](results/2026-10-18-compile3/bench-output-sha256.json) are also archived.

| Workload | C compile ms | MLF compile ms | Compile / C | C runtime ms | MLF runtime ms | Runtime / C | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| binary-trees | 125.742 | 327.445 | 2.604102050 | 339.305 | 288.541 | 0.850388294 | PASS |
| pidigits | 132.988 | 327.212 | 2.460462598 | 366.014 | 420.549 | 1.148997033 | PASS |
| n-body | 141.021 | 400.672 | 2.841222229 | 105.716 | 159.232 | 1.506224223 | PASS |
| fannkuch-redux | 133.679 | 333.933 | 2.498021380 | 212.006 | 274.181 | 1.293270002 | PASS |
| spectral-norm | 135.273 | 332.952 | 2.461333747 | 201.439 | 181.797 | 0.902491573 | PASS |
| fasta | 137.789 | 342.982 | 2.489182736 | 222.628 | 363.866 | 1.634412563 | PASS |
| mandelbrot | 125.477 | 335.219 | 2.671557337 | 935.824 | 698.645 | 0.746555976 | PASS |
| reverse-complement | 127.317 | 337.822 | 2.653392713 | 195.893 | 293.922 | 1.500421148 | PASS |
| k-nucleotide | 149.863 | 369.828 | 2.467773900 | 170.390 | 280.410 | 1.645695170 | PASS |

The machine is Apple M1 Max, 32 GiB, macOS 26.6.2 (25G83), ARM64. The toolchain is Clang/LLVM 23.1.3, GMP 6.3.0 and BDWGC 8.2.12. Every workload uses fresh output directories, runtime objects and LLVM objects. Runtime C compilation, LLVM compilation and linking are inside the compilation boundary. Workload sources, inputs, correctness oracles and C reference optimization flags are unchanged; runtime C also retains O2.

## Variation and remaining margin

| Workload | C compile range ms | MLF compile range ms | C runtime range ms | MLF runtime range ms | Max MLF / min C compile | Max MLF / min C runtime |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| binary-trees | 123.098–132.251 | 321.799–331.655 | 338.551–341.558 | 285.828–293.919 | 2.694235487 | 0.868167573 |
| pidigits | 126.806–136.219 | 326.128–336.766 | 363.058–385.021 | 414.609–434.477 | 2.655757614 | 1.196715125 |
| n-body | 138.774–142.398 | 397.004–406.397 | 105.260–110.549 | 157.892–162.618 | 2.928480839 | 1.544917348 |
| fannkuch-redux | 132.786–139.209 | 332.085–336.294 | 210.789–215.840 | 274.006–278.762 | 2.532601328 | 1.322469389 |
| spectral-norm | 131.997–138.375 | 328.903–341.313 | 200.110–203.415 | 180.478–183.663 | 2.585763313 | 0.917810204 |
| fasta | 136.101–146.751 | 340.718–351.263 | 215.397–224.774 | 361.271–369.146 | 2.580899479 | 1.713793600 |
| mandelbrot | 122.660–131.699 | 330.913–346.164 | 934.167–952.972 | 692.806–744.933 | 2.822142508 | 0.797430224 |
| reverse-complement | 126.140–133.121 | 333.946–352.548 | 185.532–207.614 | 280.347–319.070 | 2.794894562 | 1.719757239 |
| k-nucleotide | 147.285–157.090 | 360.506–376.857 | 170.244–177.131 | 278.138–307.311 | 2.558692331 | 1.805120885 |

The largest observed same-index sample ratios are 2.898656890× compilation and 1.805120885× runtime. These are additional variation checks, not a replacement for the specified median gate. Median absolute deviations, CPU times, RSS, stage intervals, commands and every raw sample are in [summary.json](results/2026-10-18-compile3/summary.json) and the native report. Passing this run does not guarantee arbitrary host load.

## Reproduced baseline

The fresh three-sample baseline measured n-body at 5.236399161× C compilation and FASTA at 4.851256519×. Thus the historical seven-sample 5× result did not reproduce with the same margin in this session. The [fresh baseline report](results/2026-10-18-compile3/experiments/baseline-bench.json) retains every sample; the prior 4.947× / 4.798× observations remain in the historical report below. The final gate is based on a separate complete seven-sample run, not on those historical denominators.

## Changes retained

- Solver normalization uses bounded dense scratch storage with a sparse fallback. The final reverse-index audit checks both directions without constructing a second index. Component projection reuses ordered-set ranks/selects and enumerates consecutive projected identities. Boundary discovery is fused into component traversal. Restoration merges sorted node streams, size-biased set union reduces rebuilding, and reverse-edge updates touch only changed edges. Each reverse-index edit now finds and updates its entry in one tree traversal; ordered restoration reuses saved original nodes while keeping checked inverse lookups for fields and alias resolution for generalization roots. Independent reference and corruption cases cover these transformations.
- The compact runtime coallocates private suspended-thunk captures and clears them after loading, before evaluation. It uses smaller value and capture prefixes, writable static string headers, inline small captured-thunk allocation, batched constructor allocation and shared generated allocation helpers. The generated compact force helper updates a single thunk directly while preserving the runtime fallback for other deferred values. Compact builds rely on BDWGC allocation scheduling instead of redundant full collections at IO boundaries. Reusable closure environments keep their captures.
- A compact-only representation pass removes eligible unary wrappers whose fields are already in weak head normal form. Canonical-pointer facts remain distinct from mere evaluatedness; escaping and partial constructors retain their representation.
- Compiler-only PGO trains on a frozen compiler source tree with type/emission weights 4:1. No benchmark sources or inputs enter the training profile.
- The native build transport supports a dependency graph: source emission, runtime C compilation and a fresh LLVM process can start together. The LLVM process initializes while the frontend runs, consumes that build's FIFO stream, archives exactly the received LLVM, verifies and emits its object; a fresh linker can also initialize early, waiting for completion markers and then reading the complete regular object files. Marker stages depend on successful object production; the full graph waits for every process. Setup, notification and waiting remain timed. Failure, interruption, timeout and child cleanup remain checked.
- The optional generic native backend verifies LLVM before and after its recorded optimization passes, emits O1 machine code using GlobalISel, and invokes the recorded Darwin linker command. C reference builds invoke the real Clang with the pinned manifest flags. The benchmark limits are configurable and the final command explicitly selects 3 and 2.

The two final solver changes were measured independently against their immediate predecessors: single-pass index updates reduced n-body emission by 3.04% and FASTA by 2.04%; ordered restoration reduced them by a further 2.04% and 3.66%. Each comparison alternated three pairs across all nine workloads and kept all 27 candidate LLVM outputs equal. The native suites include 3,072 direct index operations, 768 graph-index transitions and 1,536 ordered restoration cases.

The initial opaque CheckedTerm/Compilation implementation is preserved. Independent xMLF checking, inferred-type agreement, source erasure, module boundaries and witness privacy remain enforced. No workload-name shortcuts were introduced.

## Ordinary critical path

The following are medians from the seven actual MLF build intervals. Overlap is the sum of recorded process intervals minus their interval union; in streaming mode this includes LLVM waiting for input. LLVM tail is the time from frontend completion to LLVM completion, rather than the LLVM process's entire lifetime. Link tail includes readiness notification and linking after both regular objects are complete; it excludes the prestarted linker's earlier waiting.

| Workload | Total ms | Frontend ms | Runtime C ms | LLVM tail ms | Link tail ms | Overlap ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| binary-trees | 327.445 | 74.241 | 309.108 | 12.060 | 16.868 | 472.759 |
| pidigits | 327.212 | 65.056 | 309.098 | 13.630 | 17.934 | 457.234 |
| n-body | 400.672 | 314.877 | 325.051 | 63.199 | 18.143 | 1024.130 |
| fannkuch-redux | 333.933 | 145.101 | 316.866 | 27.148 | 18.201 | 638.445 |
| spectral-norm | 332.952 | 134.845 | 314.529 | 24.112 | 17.851 | 612.833 |
| fasta | 342.982 | 269.496 | 324.885 | 48.268 | 17.947 | 916.002 |
| mandelbrot | 335.219 | 136.339 | 318.298 | 32.945 | 18.334 | 629.424 |
| reverse-complement | 337.822 | 169.563 | 320.652 | 34.697 | 18.129 | 705.219 |
| k-nucleotide | 369.828 | 298.544 | 327.283 | 49.535 | 18.347 | 978.634 |

The critical path follows the later of the fresh runtime object and LLVM object, then linking. With streaming it is approximately max(frontend + LLVM tail, runtime C) + link tail, plus setup and scheduling overhead. Adding the process medians double-counts waiting and overlap and does not reconstruct the median total. For n-body, the source/LLVM branch remains the relevant bottleneck; several smaller workloads are limited by runtime C compilation.

The separate diagnostic driver records loading, parsing/lowering, inference/elaboration, independent checking/agreement, optimization, LLVM generation and output. It runs three times per workload.

| Workload | Load ms | Parse/lower ms | Infer/elaborate ms | Check/agreement ms | Optimize ms | LLVM generate ms | Write ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| binary-trees | 0.056 | 3.849 | 57.393 | 1.699 | 1.808 | 2.386 | 0.355 |
| pidigits | 0.063 | 2.606 | 49.921 | 1.122 | 1.427 | 2.453 | 0.331 |
| n-body | 0.066 | 11.813 | 273.975 | 8.026 | 10.849 | 14.062 | 1.091 |
| fannkuch-redux | 0.067 | 5.221 | 119.144 | 4.339 | 4.126 | 7.090 | 0.588 |
| spectral-norm | 0.066 | 4.768 | 112.288 | 3.451 | 4.542 | 5.315 | 0.484 |
| fasta | 0.063 | 7.951 | 233.527 | 5.200 | 11.665 | 9.881 | 0.729 |
| mandelbrot | 0.059 | 5.793 | 112.335 | 2.762 | 3.513 | 7.208 | 0.506 |
| reverse-complement | 0.056 | 6.086 | 142.440 | 5.006 | 4.890 | 9.092 | 0.601 |
| k-nucleotide | 0.065 | 11.117 | 255.859 | 6.204 | 8.621 | 10.193 | 0.789 |

These forced diagnostic timings are **not ordinary compiler timings**. The diagnostic executable is separately built, keeps intermediate results alive and forces complete phase results; its repeated-forcing checkpoints can also trigger collection. The table omits those repeated checkpoints, which remain in the [raw phase logs](results/2026-10-18-compile3/phases/context.json). It must not be used to assign additive costs to the ordinary frontend interval. All 27 diagnostic LLVM outputs match the starting compiler byte for byte.

## Ordinary self-compilation

The original and final compiler ran on the identical frozen source tree in alternating order: original/candidate, candidate/original, original/candidate. Each fresh process includes source loading through complete compact LLVM output. This preserves the earlier secondary source-to-LLVM boundary; it is separate from the full benchmark executable-build boundary.

| Compiler | Three wall samples s | Median s | Range s | MAD s |
| --- | --- | ---: | --- | ---: |
| original | 257.289, 257.535, 254.577 | 257.289 | 254.577–257.535 | 0.246 |
| candidate | 182.307, 181.955, 181.335 | 181.955 | 181.335–182.307 | 0.352 |

The candidate median changes by -29.280% relative to the freshly remeasured original. The earlier 270.03 s / 279.94 s medians are historical observations, not substituted samples. All repetitions within each variant have identical LLVM. Original and candidate compact LLVM differ with the retained representation and allocation changes; standard benchmark LLVM remains identical. The archived [original LLVM](results/2026-10-18-compile3/ordinary/original.ll.gz) and [candidate LLVM](results/2026-10-18-compile3/ordinary/candidate.ll.gz) contain 0 and 3413 static string headers respectively. The candidate also contains the new thunk allocator, shared constructor allocator and single-thunk force path; the summary records their presence in each variant. Raw argv, status, CPU time, RSS, output hashes and frozen-source hashes are retained under [ordinary](results/2026-10-18-compile3/ordinary/context.json).

## Native correctness verification

All six groups were built and run through the native MLF package manager with compiler SHA-256 `0bc6f35450ec7bf03df75a1dbebedea3d5de5ed692aabb69e97ed2dbb364806d`:

- Unit: 654 checks, the 6,712-term independent oracle, Figure12 43/43 plus 36 supplementary checks, and 57 native harness tests.
- Packages: 18 resolver and 19 integration cases.
- Self-host: a fresh native self-build reached the same LLVM fixed point.
- Parity: 7,086 cases; 3,202 accepted, 3,884 rejected, and 160 runtime executions.
- Backends: 500 fixtures / 552 rows × two backends in **each** standard and compact-GC layout.
- Port: all 26 fixtures × two backends in each layout, including independent graph/inference references and target serialization checks.

The [six verification reports](results/2026-10-18-compile3/summary.json) bind the exact compiler and 426 source files; original logs and the native package manager build report are preserved with hashes. The first unit launch stopped at its stale 652-check coverage guard after two new checks were added; the guard was raised to 654 and all six groups rerun on the resulting identical source snapshot. The failed attempt is archived separately, and no test was removed. The compiler-test groups use their ordinary Clang build path; the performance gate uses the explicit backend configuration below. The final benchmark separately validates the unchanged oracles, check sizes, pinned fixtures and every measured output. All 63 final candidate standard LLVM outputs equal the starting compiler's output. Machine objects can differ because the LLVM optimization/selection policy changed; the resulting executables are independently output-checked.

## Reproduction and provenance

The measured gate command, with a new output directory, is:

```sh
MLF_BENCH_STREAM_LINK=1 MLF_BENCH_STREAM_LLVM=1 MLF_BENCH_MLF_CLANG="/Volumes/src/mlf/.mlf-build/compile3/backend-ready-link-v2/clang-mlf" \
  "/Volumes/src/mlf/.mlf-build/compile3/final-bench-driver-v5/bin/bench" \
  "/Volumes/src/mlf/.mlf-build/compile3/pgo7/candidate/bin/emlf" \
  "/Volumes/src/mlf/.mlf-build/self-profile/candidate-v3/bin/emlf" \
  "$PWD/.mlf-build/repeat-compile3-bench" 7 \
  /opt/homebrew/Cellar/llvm/23.1.3/bin/clang-23 3 2
```

Use [the benchmark README](../bench/README.md) to build the native benchmark driver and generic LLVM helper/configuration, and [the profiling README](README.md) for two native generations, compiler-only PGO, diagnostic phases and alternating ordinary measurements. Build the current native package manager and the test-owned campaign runner, then run its groups serially:

```sh
/absolute/path/to/current/native/mlfpkg \
  --compiler "/Volumes/src/mlf/.mlf-build/compile3/pgo7/candidate/bin/emlf" \
  --build-dir "$PWD/.mlf-build/repeat-checks/runner" --timeout 21600 \
  build --target compiler-tests
for group in unit packages self-host parity backends port; do
  "$PWD/.mlf-build/repeat-checks/runner/bin/compiler-tests" "$group" \
    --manager /absolute/path/to/current/native/mlfpkg \
    --compiler "/Volumes/src/mlf/.mlf-build/compile3/pgo7/candidate/bin/emlf" \
    --build-dir "$PWD/.mlf-build/repeat-checks/compiler-tests/$group"
done
```

[The context](results/2026-10-18-compile3/bench-context.json) verifies the compiler, runner, LLVM/GMP/GC libraries, headers and backend configuration before and after measurement. [Source hashes](results/2026-10-18-compile3/source-sha256.json), [tested-source archive](results/2026-10-18-compile3/tested-source.tar.gz), [frozen self-source archive](results/2026-10-18-compile3/frozen-self-source.tar.gz), PGO profile/provenance, package build reports and [artifact index](results/2026-10-18-compile3/artifact-index.json) bind the implementation and measurements. [The final audit](results/2026-10-18-compile3/final-audit.json) rechecks source/tool hashes, all 378 timed statuses and raw medians, the six groups, and preservation of the initial worktree; [SHA256SUMS](results/2026-10-18-compile3/SHA256SUMS) covers the archived evidence. [The raw measurement index](results/2026-10-18-compile3/raw-measurement-index.json) locates every retained experiment; the complete fresh build/executable directories remain under `.mlf-build/compile3`.

Rejected and exploratory measurements remain available. The first seven-sample run passed every median gate but lacked n-body margin. The later complete v4 run also passed all median gates but lacked n-body margin (2.996301304× median; 3.127611875× maximum MLF/minimum C); k-nucleotide had a 3.527674073× observed extreme. All samples remain in its report. The interrupted v3 run has no acceptance status; its individual sample records are archived. An object-FIFO linker experiment was stopped after LLD blocked reading EOF in binary-trees; its partial run and native stack are retained. The retained linker helper instead waits for completion markers and reads regular files, with 50 fresh native builds and a failed-producer cleanup check. Other retained exploratory reports include smaller/larger heaps, unsuccessful projection variants, allocation variants, LTO, LLVM pass/selector variants and earlier runtime-O1 experiments. The llc experiment whose tool manifest changed during measurement is explicitly invalid and is not acceptance evidence. Diagnostic microbenchmarks and three-sample screening runs are not substituted for the final seven-sample gate.

GHC, Cabal, Python and subagents were not used. No commit or push was made. Starting worktree files remain present; the initial dirty snapshot is retained in the evidence archive. The historical report below is preserved verbatim.

---

# Native self-compilation profiling milestone — 2026-10-16

The compiler changes reuse a successful independent xMLF check and reduce
allocation while reconstructing solver graphs. The production runtime and
graph validation rules are unchanged. Measurements use an Apple M1 Max (32 GiB), macOS 26.6.2 ARM64,
Clang 23.1.3, GMP 6.3.0 and BDWGC 8.2.12. No GHC, Cabal, Python or subagents
were used. Node was used for file editing and report aggregation; the compiler,
test orchestration and benchmark runner execute as native MLF.

The measured solver allocation reduction is **2.9%**. Ordinary self-compilation
did **not** improve: its three-run median was **3.7% slower**. All native test
groups and all nine C-relative benchmark gates passed. This milestone establishes
safe check reuse and lower solver allocation, not an end-to-end speedup.

## Checked emission

`Bootstrap.X.Checked` exports an opaque `CheckedTerm`. Its private constructor
can only be reached through the independent xMLF checker. `Compilation` is
also opaque and stores that witness. Source compilation still verifies the
inferred type and source erasure; source and separate-module LLVM entry points
then reuse the witness. Raw/deserialized xMLF still goes through the checker,
and IO entry points still require an IO type. Separate-module object boundary
and graft checks remain in place.

Four new regression entries compare checked/raw LLVM in both layouts, reject
malformed external terms, enforce IO entry types and verify constructor privacy
through the real module loader.

## Solver allocation

`strictNode`, `strictGraph` and `strictScopes` force the same required fields
and return their existing immutable records. Previously they constructed new
wrappers for already existing records. `buildNodeTree` now forces each finished
map subtree before returning it, avoiding a deferred construction spine.

Three new regression entries compare graph construction against independent
insertion, check lazy unused fields and arbitrary-precision identities, and
compare graph expansion against an independent implementation.

A first split/join-map-union and batched-expansion experiment did not provide
convincing improvement and was reverted. The retained
[sample summary](results/2026-10-16/sample-summary.json) and
[compressed native stacks](results/2026-10-16/solver-named.sample.gz) come from
that experimental snapshot, whose
[patch](results/2026-10-16/reverted-union-experiment.patch) is retained for
provenance. They guided the subsequent allocation changes; they are not a
post-change performance measurement. Among 4,509 samples, the nearest graph
function was `solverUnify` in 17.2% and `buildNodeTree` in 14.5%; nearest source
functions included `IntMap.lookupTree` (10.8%) and `Map.balance` (9.5%).
These are sampled stack attributions, not exclusive function timings.

## Measurement boundaries

Both revisions compile the same frozen original compiler source from commit
`ff8362d6cd5678b062e68b105ba23890ef847e33`. The expected LLVM SHA-256 is
`b5866443a271d7d7a7463bdc65958aa9b0c28541be7600e1209051cd40f9eabc`.
The original native compiler SHA-256 is
`6f658807be3a2fb1955ee42284b4ba34a736f7927ac9964da9c3cd234cb41bc0`;
the final compiler is
`6a04cdf5fbd6e1f304fb3b2847e081e58b659594f8d722712b977758007fd0ce`.

The diagnostic driver forces each phase's complete result and explicitly
measures an extra recheck. Its raw LLVM API checks again. Its total therefore
must not be treated as ordinary compiler time. Full forcing and longer-lived
intermediates alter collection/evaluation order; repeated-force checkpoints
can include IO-boundary collection. Allocation totals count managed BDWGC
allocation, not every operating-system allocation. See the
[profiling instructions](README.md) and
[toolchain fingerprint](results/2026-10-16/toolchain-fingerprint.json).

Ordinary measurements use fresh compiler processes, alternate original/final
order and include complete source-to-LLVM emission. They exclude Clang
optimization and native linking. The full Benchmarks Game compilation gate
includes those later stages and uses the unchanged workload inputs.

## Diagnostic results

The final profiler emitted exactly the same LLVM as the original profiler.
The [phase archive](results/2026-10-16/phases.json) contains every checkpoint
and the frozen input hashes; raw
[original](results/2026-10-16/baseline-phases.jsonl) and
[final](results/2026-10-16/final-phases.jsonl) logs are retained.

| Diagnostic measurement | Original | Final |
| --- | ---: | ---: |
| Instantiation wall time | 67.850 s | 59.150 s |
| Instantiation managed allocation | 91.016 GB | 88.393 GB |
| Instantiation GC time | 33.206 s | 29.687 s |
| Final normalization wall time | 19.245 s | 17.647 s |
| LLVM phase wall time | 136.503 s | 106.468 s |
| Total managed allocation | 365.347 GB | 362.140 GB |
| Peak resident memory | 8.851 GB | 8.930 GB |

GB means decimal billions of bytes. Instantiation allocated **2.62 GB less
(2.9%)**, with **12.8% lower observed phase wall time**. These are single
diagnostic runs; wall-time differences also include GC and operating-system
variation. The ordinary paired runs are the basis for the end-to-end timing
comparison. Peak live/resident memory did not fall with cumulative allocation.

The deliberately retained repeat-check phase in the final profiler took
**1.605 s** and allocated **5.017 GB** on the already evaluated target. The
ordinary source and linked-module LLVM paths now reuse the successful check.
LLVM emission remains the largest diagnostic phase at **106.468 s**; it
includes optimization, code generation, output construction and the raw API's
independent target check.

## Ordinary self-compilation

The [ordinary-run archive](results/2026-10-16/ordinary.json) preserves all six
measurements, CPU time, peak RSS, commands and binary hashes. Each fresh process
compiled the same frozen original source, and every emitted LLVM file matched
the reference byte for byte. Runs were sequential, with no concurrent build or
test jobs; normal desktop background services were not disabled.

| Pair | Execution order | Original wall time | Final wall time |
| --- | --- | ---: | ---: |
| 1 | Original, final | 259.858 s | 264.285 s |
| 2 | Final, original | 270.033 s | 302.320 s |
| 3 | Original, final | 284.509 s | 279.942 s |
| Median | | **270.033 s** | **279.942 s** |

The final median is **9.908 s (3.7%) slower**. The paired changes vary from
1.6% faster to 12.0% slower; three pairs do not establish how much of the
difference comes from the changes versus GC and host variation. The single
diagnostic run's lower phase times cannot override this ordinary result.
Resident memory also did not consistently improve: original runs peaked at
9.679–11.181 GB and final runs at 9.799–10.887 GB.

Further speed work should first profile allocation and retained memory during
ordinary LLVM emission, the largest phase in the diagnostic run. Within the
solver, the sampled unification, graph-map construction and lookup paths remain
the next targets. Any further change needs the same frozen-input comparison;
less cumulative allocation alone is not enough to claim faster compilation.

## Benchmarks

All 18 limits pass across nine workloads, with seven samples per language.
Maximum compilation is n-body at **4.947x C**; maximum runtime is k-nucleotide
at **1.673x C**. N-body has only about 1% compilation margin. All 63 final
benchmark LLVM outputs match the original compiler byte for byte. The
[benchmark table](../../benchmarks/RESULTS.md) and
[raw report](../bench/results/2026-10-16-native-macos-arm64.json) preserve the
measurements, commands, tool/source hashes and correctness checks.

## Native validation

The full native package-manager test command passed all six groups. Every
group records the final compiler hash above and unchanged source hashes. The
[validation archive](results/2026-10-16/native-validation.json) retains those
reports and the package-manager build/test report.

- Unit: **643 checks**, including the seven new regression entries; an
  independent oracle over **6,712 closed terms**; **43 Figure 12** expectations
  and **36 supplementary checks**; **53 native harness tests**.
- Packages: **18 resolver tests** and **19 integration cases**.
- Self-host: a fresh next-stage build reproduced both LLVM and the native
  compiler executable byte for byte, without reusing the candidate build.
  The current-source LLVM fixed-point hash is
  `e6f08662f59e2b4468373bf3c75cb82585f5323a2531fd7fa3ee10639b1adff9`.
  This differs from the frozen-original-source hash used for timing above.
- Parity: **7,086 cases**, with **3,202 accepted**, **3,884 rejected**, and
  **80 runtime cases executed on both backends**.
- Backends: **546 rows × 2 backends in each of two layouts**, standard and
  compact GC; **494 shared fixtures per layout**, with no failures or missing
  executions.
- Compiler port: **26 rows × 2 backends in each layout**, including independent
  graph/inference references, solver validation reuse, state typing and
  primitive metadata; no failures or missing executions.

The test command used the native `mlfpkg` executable via `MLF_PACKAGE_MANAGER`:

```sh
export MLF_PACKAGE_MANAGER="$PWD/.mlf-build/self-profile/candidate/bin/mlfpkg"
export MLF_GC_PREFIX="$PWD/dist-newstyle/bootstrap-deps/bdwgc-8.2.12-install"
export PATH="$PWD/.mlf-build/self-profile/blocked:$PATH"
./mlfpkg --locked \
  --compiler "$PWD/.mlf-build/self-profile/candidate-v2/bin/emlf" \
  --build-dir "$PWD/.mlf-build/self-profile/candidate-v3" \
  --timeout 21600 test
```

The seed supplied to package building was the preceding native compiler;
every test group used the final compiler in `candidate-v3/bin/emlf`. Failing
PATH wrappers guarded GHC, Cabal and Python commands; their invocation log
remained absent. The port group includes long interpreted compiler and graph
fixtures, which account for most of the verification time.
