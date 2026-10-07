# Cross-language compiler and runtime benchmarks

Run from the repository root:

```sh
cabal bench -j1
cabal bench --benchmark-options='--compile-only'
cabal bench --benchmark-options='--runtime-only'
cabal bench --benchmark-options='--benchmark binary-trees'
cabal bench --benchmark-options='--runs 5 --size 16 --output bench-results.json'
```

Requires Python 3.9+, GHC, Clang, Rust (`rustc`, no Cargo), `pkg-config`, and
GMP on macOS or Linux. Git is used only to record repository metadata.
Dependencies and tools must already be installed.
Cabal builds the optimized `emlf` compiler and the small benchmark launcher
before measurement. Baseline sources are vendored: benchmarking never
downloads code or dependencies. All four toolchains are required; missing
tools, pin mismatches, failed commands and output mismatches fail the run.

The initial corpus contains **binary-trees**. It exercises allocation,
recursive functions, ADTs and pointer traversal. See
[source provenance and MLF correspondence](binary-trees/PROVENANCE.md) and
[candidate investigation and blockers](INVESTIGATION.md). Four source
languages are necessary to compare practical language/compiler pipelines;
one shared frontend would answer a different question.

The [measured results](RESULTS.md) include the current-machine table and an
archived JSON report with all raw samples.

Defaults are three serial samples per dimension at maximum depth 16. On the
development machine, each optimized MLF execution takes roughly 0.3 seconds
and uses about 22 MiB. The original unoptimized results remain archived. Inputs
0–20 are accepted, but high depths can require substantial time/memory.
`--size 10 --runs 2` is a quick integration check; its runtime results are too
short for performance conclusions. The driver flags medians below 100 ms.
`--timeout 600` bounds each subprocess, kills its process group on timeout,
and records failure. Change it when deliberately testing larger inputs.

## Exact optimized pipelines

The driver resolves each executable and records its path, SHA-256, version,
flags and **every actual argv list and working directory** in the JSON. The
equivalent commands, using a fresh `$OUT` directory for each compilation, are:

```sh
clang -O3 benchmarks/binary-trees/c/main.c -lm -o "$OUT/program"
rustc -O benchmarks/binary-trees/rust/main.rs -o "$OUT/program"
ghc -O2 -XBangPatterns -fno-full-laziness -fno-cse -fforce-recomp \
  benchmarks/binary-trees/haskell/upstream.hs -outputdir "$OUT" -o "$OUT/program"
emlf --emit-llvm benchmarks/binary-trees/mlf/main.emlf > "$OUT/program.ll"
clang -O2 -Wno-override-module "$OUT/program.ll" "$(emlf --llvm-runtime)" \
  $(pkg-config --cflags --libs gmp) -o "$OUT/program"
```

In the actual driver, runtime path and GMP flag discovery happen **before**
measurement. Paths are passed as argument arrays, not interpreted by a shell.
MLF uses this repository's normal checked eMLF → xMLF → LLVM pipeline, then
Clang `-O2` compiles the LLVM IR **and fresh C runtime** and links GMP. There
is no prebuilt runtime object reused between samples. C uses the requested
`-O3`, Rust `-O`, and GHC `-O2`. No native CPU tuning, LTO, profile-guided
optimization, parallel runtime or debug/sanitizer build is enabled. The
special Haskell anti-sharing flags preserve required work; see provenance.

## Compilation measurement

Tool metadata and GMP probes, Cabal configuration, compiler/harness builds,
correctness checks and runtime execution are outside compilation samples.
Each sample starts immediately before the first compiler subprocess and ends
after linking. It includes compiler startup, MLF IR writes, backend/runtime
compilation and linking. Fresh temporary directories and GHC force-recompile
prevent reuse of object/interface/output files. OS file caches remain warm;
this is not a disk-cache-flushing or cold-machine experiment. Language order
rotates between rounds, all builds are serial, and the median is reported.
Each timed build is subsequently executed on a small input to check its
product; that execution is outside the compilation interval.

JSON also reports the sum of per-program compilation latencies for each
round and its reciprocal corpus rate. With the current one-program corpus,
this is the same experiment as latency. It **does not** separate compiler
startup from processing throughput. Even with more programs it includes a
fresh compiler process per program; no persistent/batch MLF API exists here.

## Runtime and correctness

First build all four binaries outside runtime timing. Before either type
of measurement, validate inputs 0, 7 and 10 against an independent output
oracle; the oracle itself must match the pinned upstream depth-10 fixture.
Before runtime measurement, also validate the exact runtime input for all
four languages. That run warms the executable, including macOS first-launch
checks. `--compile-only` needs only the small correctness cases. Prepared
binaries are reused for runtime samples, independently of the fresh binaries
used to time compilation. There is no compiler invocation inside a runtime
sample. Each sample's output is checked again after stopping the timer.

Every implementation fully constructs the same trees and traverses them;
all use the same maximum depth, tree count and observable checks. Only
whitespace is normalized; no numeric tolerance is needed for binary-trees.
The driver never supplies precomputed answers to programs. A separate
untimed allocation probe and both-backend MLF regression cases are included
in `cabal test`; the measured programs are uninstrumented.

Wall timing uses Python's high-resolution monotonic `perf_counter`; POSIX
`wait4` supplies per-process user/system CPU and peak RSS. Darwin reports RSS
in bytes, Linux in KiB, converted to bytes. CPU is summed over compilation
stages and stage RSS is reported as a maximum, not a sum. OS resource usage
for compiler subprocess descendants has platform-specific accounting;
runtime programs are single-process. Wall timing includes process startup,
input parsing, output, garbage collection and exit. Temporary file IO avoids
pipe deadlocks; reading and validating the small output happens after timing.
No startup cost is subtracted. Binary sizes are recorded after linking.

Haskell is sometimes faster than C. Ratios are median(language) / median(C),
so values below one are valid. Geometric means are calculated only when
multiple distinct workloads have measured results. A one-workload geometric
mean adds no information and is omitted. Linux `perf` counters are not
implemented; they are not a prerequisite on either platform.

The driver controls locale and clears inherited `GHCRTS` and GHC package
environments. Toolchain identities, runtime hashes and controlled variables
are recorded. All source, harness, manifest, tool and runtime hashes are
checked again at completion; changes during a run invalidate its results.
CPU frequency, system load, thermal state and OS filesystem
caches are not controlled. Run on an otherwise idle machine, repeat runs,
and compare matching toolchains, inputs, hardware and schema versions.

## Reports and extension

`bench-results.json` (ignored by Git) contains schema version, pass/fail status,
UTC timestamp, OS/architecture, tool identities, exact commands/flags, source
hashes and pinned provenance, preparation/correctness evidence, raw compile
and runtime samples, medians, ratios, CPU, RSS and binary sizes. Unmeasured
dimensions are `null`, never zero. Execution failures replace stale success reports
with `status: "failed"`; only `status: "passed"` is suitable for performance
history. Temporary binaries are removed after the run; their hashes, build
commands and source identities remain in the report. Save reports by commit
and machine for CI history; this suite sets no arbitrary cross-language
performance pass threshold.

To add another workload: first pin and inspect comparable sequential
baseline submissions with their license and original source; document any
necessary adaptations and retain patches. Implement the same work in MLF,
prove all four outputs agree at several small/boundary and intended inputs,
and audit any risk of reducing or sharing work. Then add sources/flags,
input bounds, provenance and checksums to `manifest.json`; add an independent
oracle/normalizer in the driver (with a specified tolerance for floats),
positive and deliberately wrong-output tests, both-backend MLF cases, and
Cabal source-distribution entries. Pin hashes must only be updated after
reviewing an intentional source adaptation. Measure the added workload end
to end before including it in aggregate ratios.

The previous Snake compilation benchmark remains available with
`cabal bench --benchmark-options='snake'`. Compiler revision comparisons
remain under `compare-revisions --before /path/to/emlf-before`.

This benchmark measures practical end-to-end compiler/language implementation performance. It does NOT perfectly isolate backend code-generation quality because C, Rust, Haskell and MLF have different language semantics, runtime systems, allocation models and abstractions.
