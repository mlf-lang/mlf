# Seven-workload results: 2026-10-08

The suite now includes **spectral-norm, fasta and mandelbrot**, alongside the
four first-milestone workloads. All seven pass independent correctness checks
in C, Rust, Haskell and MLF at their measured inputs.

Every MLF compilation median is within **5x C**. The original four runtime
medians remain within **2x C**. The new runtime ratios are **2.73x** for
spectral-norm, **3.92x** for fasta, and **3.19x** for mandelbrot, so the expanded
corpus does not yet meet the runtime target on every workload.

```sh
cabal bench -j1 --benchmark-options='--runs 5 --output benchmarks/results/2026-10-08-seven-workloads-macos-arm64.json'
```

The [complete JSON report](results/2026-10-08-seven-workloads-macos-arm64.json)
contains 140 compilation samples and 140 runtime samples, exact commands,
compiler/runtime/source hashes, provenance, correctness evidence, CPU/RSS and
binary sizes. All recorded input hashes were unchanged throughout the run and
were checked again afterwards. This run uses the default correctness gates;
performance limits were not enabled. Its `passed` status does not mean every
workload meets the optional 5x/2x performance limits.

Host: macOS 26.6.2, ARM64, 10 logical CPUs; Python 3.14.8. Toolchains: Clang
23.1.2, rustc 1.99.0, GHC 9.14.1, GMP 6.3.0. Measurement ran from 07:39:42 to
07:44:26 UTC on 2026-10-08. The checkout is based on
`45de83826698d7eed17ecc96baf5b2048865839c` with uncommitted changes; hashes
identify the actual compiler binary, runtime and workload sources.

C uses Clang `-O3`, Rust uses `rustc -O --edition=2021`, Haskell uses GHC `-O2`
with the documented per-source extensions, and MLF uses the normal checked
eMLF → xMLF → LLVM pipeline followed by Clang `-O2`. Every MLF compilation
builds its C runtime afresh and links GMP. There is no cached runtime object,
LTO, native CPU tuning, fast-math, profiling or sanitizer instrumentation in
these measurements. See [methodology](README.md) and [exact flags](manifest.json).

## Compilation

Fresh source-to-executable wall-clock medians, in milliseconds. Each includes
compiler startup, frontend processing, code generation, native runtime compilation
and linking. Cabal/compiler builds, dependency probes and correctness checks
are outside the samples. Language order rotates between rounds.

| Workload | C (ms) | Rust (ms) | Haskell (ms) | MLF (ms) | MLF / C |
| --- | ---: | ---: | ---: | ---: | ---: |
| binary-trees | 142.25 | 165.22 | 446.67 | 436.96 | 3.07x |
| pidigits | 147.24 | 137.19 | 444.16 | 437.28 | 2.97x |
| n-body | 159.54 | 148.82 | 504.23 | 775.75 | 4.86x |
| fannkuch-redux | 155.17 | 197.93 | 469.13 | 510.21 | 3.29x |
| spectral-norm | 154.08 | 165.48 | 559.88 | 516.95 | 3.35x |
| fasta | 156.50 | 174.34 | 494.65 | 608.33 | 3.89x |
| mandelbrot | 143.89 | 184.06 | 456.53 | 507.33 | 3.53x |

MLF's geometric mean compilation ratio is 3.52x C. N-body is closest to the
limit at 4.86x, so modest compiler/runtime or machine changes can affect that
margin. Corpus latency sums seven fresh per-program compilations in each round;
it includes seven compiler startups, not a persistent compiler's throughput.

| Pipeline | Seven-program latency (s) | Programs/s |
| --- | ---: | ---: |
| Clang/C | 1.05943 | 6.607 |
| rustc/Rust | 1.17911 | 5.937 |
| GHC/Haskell | 3.38578 | 2.067 |
| MLF/LLVM | 3.79802 | 1.843 |

## Runtime

Wall-clock medians in seconds, using independently prepared binaries. Each
runtime input was validated before sampling and every timed output was checked
after stopping the timer. Startup, parsing, output, GC and exit are included.
All 28 language/workload medians exceed 100 ms; no startup time is subtracted.

| Workload | Input | C (s) | Rust (s) | Haskell (s) | MLF (s) | MLF / C |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| binary-trees | 16 | 0.34066 | 0.40660 | 0.12793 | 0.33106 | 0.97x |
| pidigits | 10,000 | 0.36503 | 0.36787 | 0.47913 | 0.43153 | 1.18x |
| n-body | 2,000,000 | 0.10698 | 0.10577 | 0.13274 | 0.11897 | 1.11x |
| fannkuch-redux | 10 | 0.21212 | 0.15998 | 0.23822 | 0.27241 | 1.28x |
| spectral-norm | 2,000 | 0.20266 | 0.27901 | 0.88950 | 0.55300 | 2.73x |
| fasta | 2,000,000 | 0.21169 | 0.24283 | 0.39346 | 0.82967 | 3.92x |
| mandelbrot | 4,096 | 0.93358 | 0.22268 | 0.99885 | 2.97764 | 3.19x |

Geometric mean runtime ratios are C 1.00x, Rust 0.86x, Haskell 1.29x and MLF
1.78x. The MLF average does not satisfy a per-workload 2x target: each of the
three additions still exceeds it. In particular, Rust's Mandelbrot source
processes eight scalar lanes together, permitting compiler auto-vectorization;
C, Haskell and MLF stop individual pixels separately. No source uses explicit
SIMD intrinsics, but this source-structure difference matters to interpretation.

Fasta's MLF counters are explicitly demanded at each recursive call. An initial
version stayed in the lazy IO path and took roughly 36 seconds at n=2,000,000;
the current version enters the native loop and takes 0.83 seconds, without
changing any nucleotide work. Further optimization of the three new numeric
and byte workloads remains open.

## Sources and required work

All baseline sources are pinned at Benchmarks Game revision
`40296663ed350d5fe4a6ab5e367bab61cb77c219`, with original files, authors,
Git blob IDs, SHA256 hashes, license, URLs and exact adaptation patches.
Baseline adaptations are tested by reconstructing each build source from its
original and patch. All measured programs are sequential.

| Workload | C | Rust | Haskell | Work and adaptations |
| --- | --- | --- | --- | --- |
| binary-trees | `binarytrees-gcc-1` | `binarytrees-rust-1` | `binarytrees-ghc-1` | 14,985,902 allocated tree nodes at depth 16; existing anti-sharing rules unchanged; [provenance](binary-trees/PROVENANCE.md) |
| pidigits | `pidigits-gcc-1` | `pidigits-rust-1` | `pidigits-ghc-6` | 10,000 digits, both extraction safety tests, three-integer spigot; [provenance](pidigits/PROVENANCE.md) |
| n-body | `nbody-gcc-1` | `nbody-rust-1` | `nbody-ghc-1` | Five bodies and all 2,000,000 integration steps; baselines unchanged; [provenance](n-body/PROVENANCE.md) |
| fannkuch-redux | `fannkuchredux-gcc-1` | `fannkuchredux-rust-2` | `fannkuchredux-ghc-4` | All 3,628,800 permutations; serial Rust dispatcher and Haskell array storage adaptation; [provenance](fannkuch-redux/PROVENANCE.md) |
| spectral-norm | `spectralnorm-gcc-1` | `spectralnorm-rust-3` | `spectralnorm-ghc-2` | All 40 matrix-vector products; C/Haskell unchanged, Rust serial dispatcher and odd tail; [provenance](spectral-norm/PROVENANCE.md) |
| fasta | `fasta-gcc-1` | `fasta-rust-4` | `fasta-ghc-1` | All 20,000,000 bases, with a fresh LCG update for every random base; baselines unchanged; [provenance](fasta/PROVENANCE.md) |
| mandelbrot | `mandelbrot-gcc-2` | `mandelbrot-rust-1` | `mandelbrot-ghc-2` | All 16,777,216 pixels, up to 50 iterations each; sequential dispatch, partial byte handling, unsigned C accumulator; [provenance](mandelbrot/PROVENANCE.md) |

The new MLF programs are [spectral-norm](spectral-norm/mlf/main.emlf),
[fasta](fasta/mlf/main.emlf) and [mandelbrot](mandelbrot/mlf/main.emlf).
They use ordinary recursion, arrays, arithmetic and prelude IO/do. ByteArray,
UTF-8 copying and raw slice output are general language operations implemented
on both backends. Native regions now support byte loads/stores and correctly
rounded integer-to-Double conversion. No runtime helper computes a benchmark
kernel, and no executable receives or contains oracle results.

Array layout, buffering, floating association and the retained scalar lane
structure differ across the source languages; per-workload provenance explains
them. Fasta compares full bytes, including wrapping and newlines; Mandelbrot
compares the exact PBM header, pixels and zero padding. Spectral-norm and n-body
require finite results within absolute error 1e-8. Independent driver oracles
also match pinned upstream fixtures and run outside all measured intervals.

## Validation and resources

Fresh validation after the final source edits:

- `cabal test -j1 --test-show-details=direct`: all four suites pass; 287 compiler
  checks, 43 Figure 12 expressions plus 36 supplementary checks, 23 benchmark
  harness tests, and 209 backend fixtures covering 205 execution rows on each
  of the interpreter and LLVM backends.
- `MLF_LLVM_TEST_OPT=-O0 cabal test backend-tests -j1 --test-show-details=direct`:
  all 205 rows pass on both backends with native optimization disabled.
- `MLF_LLVM_TEST_CFLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer -DMLF_GC_INTEGER_BYTES=64' cabal test backend-tests -j1 --test-show-details=direct`:
  all 205 rows pass on both backends, with frequent native collection.
- The five-sample `cabal bench` run above validates all four languages on small,
  odd, partial-row/buffer-boundary inputs and on each exact timing input.

MLF resource measurements follow. CPU is the median user+system time; RSS is
the largest per-process peak across samples; binary size excludes dynamic
libraries. The JSON contains the corresponding values for all four languages.

| Workload | CPU (s) | Peak RSS (MiB) | Binary (KiB) |
| --- | ---: | ---: | ---: |
| binary-trees | 0.3279 | 21.41 | 69.20 |
| pidigits | 0.4263 | 197.59 | 69.18 |
| n-body | 0.1162 | 1.56 | 134.12 |
| fannkuch-redux | 0.2698 | 1.48 | 85.41 |
| spectral-norm | 0.5500 | 1.61 | 85.45 |
| fasta | 0.8221 | 1.92 | 101.60 |
| mandelbrot | 2.9707 | 1.75 | 85.43 |

Pidigits still uses more memory than the C baseline because immutable GMP
results are retained until IO collection points. Native numeric regions also
defer collection until returning to the IO driver. The new kernels mostly
reuse mutable buffers with immediate integers and unboxed doubles.

The [earlier four-workload optimization run](results/2026-10-08-optimized-macos-arm64.json)
and [original milestone run](results/2026-10-08-first-milestone-macos-arm64.json)
remain unchanged. All first-four workload sources, flags, input sizes and
manifest entries are unchanged from the optimization run; the compiler/runtime
has gained general byte operations and native integer conversion. Compare
matching workload rows rather than comparing geometric means across different
corpora or sample counts.

These results apply to this machine, toolchain, source snapshot and inputs.
System load, thermal state and filesystem caches are not controlled. Future
work includes bringing each added runtime below 2x C, then investigating
reverse-complement and k-nucleotide after byte input and record/lookup support
exist; see [investigation](INVESTIGATION.md).

This benchmark measures practical end-to-end compiler/language implementation performance. It does NOT perfectly isolate backend code-generation quality because C, Rust, Haskell and MLF have different language semantics, runtime systems, allocation models and abstractions.
