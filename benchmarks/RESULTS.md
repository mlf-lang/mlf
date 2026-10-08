# Cross-language benchmarks after module support: 2026-10-09

All **nine workloads pass the 5x C compilation and 2x C runtime limits**
with the module-aware compiler. At the existing default inputs on this machine,
the largest compilation ratio is **4.11x** (fasta);
the largest runtime ratio is **1.90x** (reverse-complement).
Every timing input passes the independent correctness oracle in C, Rust,
Haskell and MLF.

```sh
cabal bench compiler-bench -j1 --benchmark-options='--runs 5 --max-compile-ratio 5 --max-runtime-ratio 2 --output benchmarks/results/2026-10-09-modules-macos-arm64.json'
```

The [archived report](results/2026-10-09-modules-macos-arm64.json)
contains **180 fresh compilation samples and 180 runtime samples**, preparation
and post-build correctness checks, exact commands, source/library/tool hashes,
CPU time, peak RSS and executable sizes. All recorded input hashes remained
unchanged. All **18 per-workload performance checks passed**; geometric means
are descriptive and do not substitute for an individual workload passing.

## Compilation

Wall-clock medians in milliseconds. MLF total includes checked eMLF -> xMLF
-> LLVM emission, IR writes, compiling the complete C runtime afresh and linking.
The LLVM emission column measures the compiler subprocess and is already
included in the total. Compiler, dependency and harness builds are excluded.

| Workload | C | Rust | Haskell | MLF emit LLVM | MLF total | MLF/C |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| binary-trees | 145.47 | 160.68 | 435.39 | 63.70 | 380.62 | 2.62x |
| pidigits | 148.91 | 136.29 | 436.68 | 53.75 | 367.99 | 2.47x |
| n-body | 158.17 | 148.33 | 499.68 | 205.03 | 618.71 | 3.91x |
| fannkuch-redux | 154.49 | 196.39 | 474.33 | 97.87 | 485.10 | 3.14x |
| spectral-norm | 155.23 | 164.69 | 539.75 | 98.09 | 433.59 | 2.79x |
| fasta | 158.44 | 177.16 | 484.54 | 177.96 | 650.46 | 4.11x |
| mandelbrot | 147.80 | 178.47 | 448.92 | 95.85 | 475.57 | 3.22x |
| reverse-complement | 148.21 | 153.30 | 493.96 | 116.69 | 540.34 | 3.65x |
| k-nucleotide | 167.04 | 230.39 | 1004.50 | 188.59 | 603.41 | 3.61x |

Geometric mean of MLF/C compilation ratios: **3.23x**.
The median sum of nine fresh MLF compilations is
**4.570 s**, versus **1.383 s** for C.
These sums include a new compiler process for every program; they do not
isolate persistent-compiler throughput.

## Runtime

Wall-clock medians in seconds, including startup, input, output, GC and exit.
Inputs, flags and independent oracles are in the [manifest](manifest.json)
and [methodology](README.md). FASTA input generation is outside timing;
reading the resulting stdin bytes is timed.

| Workload | Input | C | Rust | Haskell | MLF | MLF/C |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| binary-trees | 16 | 0.33895 | 0.40501 | 0.13019 | 0.34678 | 1.02x |
| pidigits | 10,000 | 0.36449 | 0.36759 | 0.48648 | 0.42555 | 1.17x |
| n-body | 2,000,000 | 0.10695 | 0.10568 | 0.12695 | 0.12022 | 1.12x |
| fannkuch-redux | 10 | 0.21262 | 0.16021 | 0.23333 | 0.23079 | 1.09x |
| spectral-norm | 2,000 | 0.20147 | 0.27829 | 0.88114 | 0.16188 | 0.80x |
| fasta | 2,000,000 | 0.20953 | 0.24163 | 0.38777 | 0.33061 | 1.58x |
| mandelbrot | 4,096 | 0.93247 | 0.21964 | 0.99632 | 0.63194 | 0.68x |
| reverse-complement | 10,000,000 | 0.13990 | 0.08008 | 0.38199 | 0.26578 | 1.90x |
| k-nucleotide | 1,000,000 | 0.17550 | 1.49416 | 1.81986 | 0.28307 | 1.61x |

Geometric mean of MLF/C runtime ratios: **1.16x**.
The harness flags reverse-complement/Rust below 100 ms; startup can materially
affect that particular comparison. Every C and MLF median exceeds 100 ms.

## Source and compiler changes

All nine MLF implementations use function declarations, typed recursive
bindings, layout, conditionals, and infix integer/string operators. Binary-trees
uses constructor equations and a local `let rec`; k-nucleotide uses literal
equations. The hand-written `Rec` datatype and `fix` combinator are removed.

The compiler now also supports named modules, export lists, selective and
qualified imports, aliases, hiding, re-exports, and transitive instances.
Module-free programs retain the existing inference and backend path. These
benchmark files remain standalone: this run checks compatibility and performance
of the new compiler, not the overhead of a large module graph. Multi-file
behavior is covered by the shared interpreter/LLVM tests and module example.

The algorithms, default inputs, C/Rust/Haskell baselines, flags, and performance
limits are unchanged. Tree construction still forces both actual children;
the accumulated tree checks, fannkuch totals, and FASTA counters retain their
strictness points. Floating-point operations keep their original order and
constants. Byte buffering, copy loops, the two Mandelbrot orbits, and all seven
k-mer frequency tables perform the same work. No backend or runtime optimization
was required for module support.

The [preceding syntax-migration report](results/2026-10-09-readable-syntax-macos-arm64.json)
records maxima of 4.31x compilation and 1.92x runtime with the same benchmark
sources. These are separate machine runs, not a paired experiment isolating
parser or module-loader overhead. The current run establishes the requested
limits for the recorded compiler and workload sources.

## Validation

```sh
cabal test -j1 --test-show-details=direct
```

All four suites pass: **470 compiler checks**, **43 Figure 12 cases plus
36 supplementary checks**, **291 shared backend fixtures with 311 execution
rows x 2 backends**, and **30 benchmark-harness tests**. Snake's 7 sessions
and 11 rule checks also match the independent Haskell version on both backends.

Module tests cover import/export visibility, qualified and private identities,
re-exports and diamonds, constructor/type/class imports, instance scope,
Prelude selection, missing files and cycles, search roots, and CLI compilation
from files, stdin and expressions. CLI xMLF is independently parsed and executed
on both backends; direct LLVM emission matches xMLF-to-LLVM emission.

The suite executes benchmark regression cases on both the interpreter and
LLVM backend, checks the pinned fixtures, and audits actual work. The untimed
tree audit counts every allocated node. The k-nucleotide audit compares writes
and distinct insertions in all seven tables against independent Python sets.
Every fresh timed build and every timed runtime output is also checked by the
benchmark harness.

## Comparison scope

Host: macOS 26.6.2, ARM64, 10 logical CPUs; Python 3.14.8. Toolchains:
Clang 23.1.2, rustc 1.99.0, GHC 9.14.1 and GMP 6.3.0. The run spans
2026-10-08T21:11:29.884457+00:00 to 2026-10-08T21:17:48.122362+00:00.
The checkout is based on `e5da2c81118a2f9937e06f8c39e5f622fe105efc` with uncommitted
changes; recorded hashes identify the measured inputs. C uses `-O3`, Rust `-O`,
GHC `-O2`, and MLF's LLVM/runtime pipeline Clang `-O2`. There is no LTO,
fast-math, explicit SIMD, parallel benchmark worker or cached runtime object.
System load, thermal state and OS caches are not controlled, so results apply
to this recorded machine and run.
