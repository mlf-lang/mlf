# Cross-language compiler and runtime benchmarks

Run from the repository root:

```sh
cabal bench -j1
cabal bench --benchmark-options='--compile-only'
cabal bench --benchmark-options='--runtime-only'
cabal bench --benchmark-options='--benchmark binary-trees'
cabal bench --benchmark-options='--benchmark binary-trees --runs 5 --size 16 --output bench-results.json'
cabal bench --benchmark-options='--benchmark pidigits --size 1000 --runs 2'
cabal bench --benchmark-options='--benchmark n-body --size 1000 --runs 2'
cabal bench --benchmark-options='--benchmark fannkuch-redux --size 7 --runs 2'
cabal bench --benchmark-options='--benchmark spectral-norm --size 100 --runs 2'
cabal bench --benchmark-options='--benchmark fasta --size 1000 --runs 2'
cabal bench --benchmark-options='--benchmark mandelbrot --size 200 --runs 2'
cabal bench --benchmark-options='--benchmark reverse-complement --size 1000 --runs 2'
cabal bench --benchmark-options='--benchmark k-nucleotide --size 1000 --runs 2'
cabal bench -j1 --benchmark-options='--runs 7 --max-compile-ratio 5 --max-runtime-ratio 2'
```

Requires Python 3.9+, GHC with its boot `array`, `bytestring` and `text` packages,
Clang, Rust (`rustc`, no Cargo), `pkg-config`, and
GMP on macOS or Linux. Git is used only to record repository metadata.
System tools must already be installed. Cabal resolves/builds the pinned
Haskell `hashtables` 1.4.2 and `hashable` 1.5.1.0 library dependencies, the
optimized `emlf` compiler and the small benchmark launcher before measurement. Baseline sources and khash are vendored; the measurement
driver never downloads code or builds dependencies. Dependency setup is
outside all measured intervals, as are Cabal and compiler builds. All four
toolchains are required; missing tools, pin mismatches, failed commands and output mismatches fail the run.

The suite contains nine workloads, all with pinned C/Rust/Haskell
baselines and an MLF implementation:

| Workload | Default input | What it exercises | Source selection |
| --- | ---: | --- | --- |
| binary-trees | depth 16 | Allocation, recursion, ADTs, pointer traversal | [Provenance](binary-trees/PROVENANCE.md) |
| pidigits | 10,000 digits | Arbitrary-precision multiplication/division, recursion | [Provenance](pidigits/PROVENANCE.md) |
| n-body | 2,000,000 steps | Double arithmetic/sqrt, indexed state updates | [Provenance](n-body/PROVENANCE.md) |
| fannkuch-redux | n = 10 | Integer loops, mutable arrays, permutations | [Provenance](fannkuch-redux/PROVENANCE.md) |
| spectral-norm | n = 2000 | Matrix-vector products, indexed Double arrays | [Provenance](spectral-norm/PROVENANCE.md) |
| fasta | n = 2,000,000 | LCG, probability selection, buffered byte output | [Provenance](fasta/PROVENANCE.md) |
| mandelbrot | 4096×4096 pixels | Floating branches, bit packing, binary PBM output | [Provenance](mandelbrot/PROVENANCE.md) |
| reverse-complement | FASTA n = 10,000,000 | Raw input, growing records, indexed bytes, buffered output | [Provenance](reverse-complement/PROVENANCE.md) |
| k-nucleotide | FASTA n = 1,000,000 | Integer hash tables, substring counting, sorting | [Provenance](k-nucleotide/PROVENANCE.md) |

See [candidate investigation and remaining work](INVESTIGATION.md). Four source
languages are necessary to compare practical language/compiler pipelines;
one shared frontend would answer a different question.

The [measured results](RESULTS.md) include the current-machine table and an
archived JSON report with all raw samples.

All nine MLF sources use the current surface syntax: function declarations,
typed recursion, indentation, conditionals, and infix integer/string operators.
Binary-trees also uses constructor equations and a local `let rec`;
k-nucleotide uses literal equations. There is no hand-written `Rec`/`fix`
plumbing. Double operations retain their explicit primitives and original
evaluation order. The existing strictness checks, algorithms, workload sizes,
baseline sources, compiler flags, and correctness/work audits are preserved.
The ratio-limit command above measures these source files directly through
the checked compiler; it does not bypass the new parser or desugaring.

Defaults are three serial samples per dimension, using the per-workload inputs
above. All languages execute the same substantial inputs. Use `--compile-only`
or the small-input
commands above for integration checks. Small-input runtime ratios are dominated
by startup; the driver flags medians below 100 ms. `--size` requires exactly
one `--benchmark` selection; without it, each selected workload uses its own
default. Supported ranges are depths 0–20, digits 1–20,000, steps 0–5,000,000
and permutation size 1–11, spectral size 1–5500, fasta n=0–25,000,000,
Mandelbrot width 1–16,000, reverse-complement FASTA n=1–25,000,000,
and k-nucleotide FASTA n=1–2,000,000. Large inputs can need a higher timeout.
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
  $(pkg-config --cflags --libs gmp) -lm -o "$OUT/program"
```

In the actual driver, runtime path and GMP flag discovery happen **before**
measurement. Paths are passed as argument arrays, not interpreted by a shell.
MLF uses this repository's normal checked eMLF → xMLF → LLVM pipeline, then
Clang `-O2` compiles the LLVM IR **and fresh C runtime** and links GMP. There
is no prebuilt runtime object reused between samples. C uses the requested
`-O3`, Rust `-O`, and GHC `-O2`. No native CPU tuning, LTO, profile-guided
optimization, parallel runtime or debug/sanitizer build is enabled. The
special Haskell anti-sharing flags preserve required tree work; see provenance.
Other workloads use the same optimization levels. Pidigits C also links GMP,
and its Rust program links GMP directly with the discovered native library
search path (`rustc -O --edition=2021 -Lnative=...`). The other Rust programs
use `-O --edition=2021`. Pidigits Haskell uses `-O2 -fforce-recomp`; n-body and
fannkuch-redux add `-XBangPatterns`. The fannkuch Haskell build source is its
documented `main.hs` storage adaptation. Exact per-workload argv lists remain
in the JSON; no Cargo or package installation runs inside the driver.
Spectral-norm uses C and Haskell unchanged, with Rust's dispatcher made
sequential and its pair loop completed for odd sizes. Fasta uses all three
baselines unchanged; Haskell needs `-XBangPatterns -XOverloadedStrings`.
Mandelbrot's Rust/Haskell row dispatchers run sequentially and handle partial
bytes; C's accumulator is unsigned. Its Haskell build adds `-XBangPatterns`.
Originals and exact adaptation patches are retained and tested.

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
round and its reciprocal corpus rate. It **does not** separate compiler
startup from processing throughput. It includes a
fresh compiler process per program; no persistent/batch MLF API exists here.

## Runtime and correctness

First build all four binaries outside runtime timing. Before either type
of measurement, validate each workload's small/boundary inputs against an
independent oracle; every oracle must also match its pinned upstream fixture.
Before runtime measurement, also validate the exact runtime input for all
four languages. That run warms the executable, including macOS first-launch
checks. `--compile-only` needs only the small correctness cases. Prepared
binaries are reused for runtime samples, independently of the fresh binaries
used to time compilation. There is no compiler invocation inside a runtime
sample. Each sample's output is checked again after stopping the timer.

| Workload | Small checks | Oracle and output rule |
| --- | --- | --- |
| binary-trees | 0, 7, 10 | Mathematical node counts; pinned depth 10 output; whitespace only |
| pidigits | 1, 10, 27, 30 | Independent fixed-point Machin formula; pinned 30 digits; whitespace only, including partial rows |
| n-body | 0, 1, 1000 | Independent Python scalar integration; pinned 1000 steps; exactly two finite energies with absolute error ≤ 1e-8 |
| fannkuch-redux | 1, 2, 5, 7 | Independent factoradic unranking of every permutation; pinned n=7 checksum/max; whitespace only |
| spectral-norm | 1, 2, 3, 100 | Dense Python matrix with `math.fsum`; pinned n=100; exactly one finite value with absolute error ≤ 1e-8 |
| fasta | 0, 1, 29, 30, 31, 1000, 12288, 12289 | Exact decimal probability oracle; pinned n=1000; exact bytes including headers, 60-column lines and buffer boundaries |
| mandelbrot | 1, 2, 7, 8, 9, 200 | Python complex recurrence; pinned 200×200 PBM; exact header, pixels and zero padding, including partial bytes |
| reverse-complement | FASTA n=1, 7, 31, 1000, 12288, 12289 | Python translation/reversal; pinned n=1000 input/output; exact headers, bases and wrapping |
| k-nucleotide | FASTA n=1, 7, 31, 1000 | Python slices/Counter for all lengths; pinned n=1000 input/output; rational frequency rounding (both neighbours only at exact midpoints), exact tie ordering, separators and query counts |

Reference calculations are cached by input inside the driver and run outside
all timed intervals. They also validate every exact runtime input. Programs
receive only their size or input bytes, never oracle state or results.
For reverse-complement and k-nucleotide, `--size` is the FASTA generator n.
All languages receive the same bytes without command-line arguments. The
driver generates FASTA outside measurement and writes it to the input file
before starting the timer; reading it is timed. The report records input byte
length and SHA-256 instead of embedding megabytes of input. The generated
n=1000 bytes must exactly match each workload's pinned upstream input. Non-finite n-body
values, missing/extra output, bad checksums/digits and mutated pins fail closed.
Every tree is constructed and traversed; every pi digit is extracted with
both safety tests; every n-body step and every fannkuch permutation executes.
Spectral-norm performs all 40 matrix-vector products; fasta updates the LCG
for every random base; Mandelbrot evaluates each pixel for up to 50 iterations.
Reverse-complement transforms every record; k-nucleotide builds all seven
complete frequency tables using library hash tables. An untimed native audit
counts the actual writes and distinct insertions for every table.
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
pipe deadlocks; reading and validating output happens after timing, including
the full FASTA text and PBM bitmap. Their bytes are never decoded or normalized.
No startup cost is subtracted. Binary sizes are recorded after linking.

Haskell is sometimes faster than C. Ratios are median(language) / median(C),
so values below one are valid. Geometric means are calculated only when
multiple distinct workloads have measured results. A one-workload geometric
mean adds no information and is omitted. Linux `perf` counters are not
implemented; they are not a prerequisite on either platform.

The driver controls locale and clears inherited `GHCRTS` and GHC package
environments. Toolchain identities, runtime hashes and controlled variables
are recorded. For Haskell k-nucleotide, the selected package IDs and transitive
Cabal source identities, archive hashes and configuration hashes are recorded.
Its GHC samples use those preinstalled library units explicitly with
`-package-db` and `-package-id`, preserving `GHC_ENVIRONMENT=-`.
All source, harness, manifest, tool and runtime hashes are
checked again at completion; changes during a run invalidate its results.
CPU frequency, system load, thermal state and OS filesystem
caches are not controlled. Run on an otherwise idle machine, repeat runs,
and compare matching toolchains, inputs, hardware and schema versions.

## Reports and extension

`bench-results.json` (ignored by Git) contains schema version, pass/fail status,
UTC timestamp, OS/architecture, tool identities, exact commands/flags, source
hashes and pinned provenance, preparation/correctness evidence, raw compile
and runtime samples, medians, ratios, CPU, RSS and binary sizes. Unmeasured
dimensions are `null`, never zero. A run first replaces old output with
`status: "running"`, so interruption cannot leave stale success. Ctrl-C writes
a failed report and reaps the active child. Execution failures replace reports
with `status: "failed"`; only `status: "passed"` is suitable for performance
history. Temporary binaries are removed after the run; their hashes, build
commands and source identities remain in the report. Save reports by commit
and machine for CI history.

There is no performance threshold by default. `--max-compile-ratio 5` and
`--max-runtime-ratio 2` enable explicit limits on the ratio of MLF's median
wall time to C's median for **each** selected workload. All enabled checks
must pass; geometric means cannot hide a failed workload. The limits must be
finite and positive, and cannot be requested for an unmeasured dimension.
Reports record the requested limits and every check. Exceeding any limit
retains the full measurement report with `status: "failed"` and exits nonzero.

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
