# Mandelbrot optimization and seven-workload results: 2026-10-08

Mandelbrot now runs faster than the pinned C baseline at **4096 x 4096**.
The seven-sample gated run measures **0.64706 s for MLF versus
0.95496 s for C (0.678x)**. Fresh MLF compilation takes
**546.36 ms (3.76x C)**. Both explicit gates pass.
The earlier MLF runtime was 2.97764 s, so this is about
**4.60x faster** than the previous five-sample snapshot.

```sh
cabal bench -j1 --benchmark-options='--benchmark mandelbrot --runs 7 --max-compile-ratio 5 --max-runtime-ratio 1 --output benchmarks/results/2026-10-08-mandelbrot-optimized-macos-arm64.json'
cabal bench -j1 --benchmark-options='--runs 5 --max-compile-ratio 5 --output benchmarks/results/2026-10-08-mandelbrot-suite-macos-arm64.json'
```

The [Mandelbrot report](results/2026-10-08-mandelbrot-optimized-macos-arm64.json) contains
28 compilation and 28 runtime samples. The [full-suite report](results/2026-10-08-mandelbrot-suite-macos-arm64.json)
contains 140 samples of each. Both retain exact commands, source/compiler/runtime
hashes, correctness evidence, provenance and resource measurements. Every
recorded input hash remained unchanged during measurement.

All seven workloads pass their independent output checks in C, Rust, Haskell
and MLF at the timing inputs. Every MLF compilation median passes the 5x C
gate. Six runtime medians are within 2x C; **spectral-norm remains at 2.73x**.
The full-suite run has no global runtime gate: its passing status does not
claim that spectral-norm meets the earlier 2x target.

## Changes and comparison scope

The compiler now specializes private native workers from proven scalar values.
Double arguments and captures remain unboxed through recursive calls; existing
payload loads are reused only along dominating paths. Zero-tested nonnegative
counters carry range proofs through countdown branches. Multiplication,
quotient, remainder and byte validation have checked machine paths with the
same arbitrary-precision fallback. Specialization is capped at eight variants
per function plus its general worker; the public non-forcing lazy boundary is
unchanged. See [backend design](../docs/llvm-backend.txt).

The [MLF Mandelbrot source](mandelbrot/mlf/main.emlf) now keeps orbit state in
scalar arguments and interleaves **two adjacent orbits**. Escaped lanes stay
masked until the neighbour finishes; an odd final pixel uses the single-orbit
loop. All pixels use the same recurrence and at most 50 iterations. No symmetry,
interior-region shortcut, precomputed output, explicit SIMD, fast-math or
benchmark-specific runtime helper is used. PBM bytes and padding remain exact.

The pinned C, Rust and Haskell sources, flags, inputs, manifest and oracles are
unchanged. C/Haskell stop individual pixels separately; Rust retains eight
scalar lanes and MLF now uses two. Auto-vectorization is allowed. These source
structures and language/runtime differences mean the result includes both
compiler improvements and a source restructuring; it does not isolate backend
code-generation quality. See [Mandelbrot provenance](mandelbrot/PROVENANCE.md).

A wider diagnostic caught an n-body regression from specializing every proven
nonnegative argument. Restricting that mode to zero-tested parameters avoids
unnecessary versions for array offsets. The final full-suite n-body runtime is
1.11x C, consistent with the preceding snapshot. Fasta also benefits from the
general integer paths: its runtime ratio falls from 3.92x to 1.55x C.

## Methodology

Host: macOS 26.6.2, ARM64, 10 logical CPUs; Python 3.14.8. Toolchains: Clang
23.1.2, rustc 1.99.0, GHC 9.14.1, GMP 6.3.0. The full run was measured from
10:22:17 to 10:26:50 UTC; the focused run from 10:27:13 to 10:28:57 UTC on
2026-10-08. Both use a checkout based on
`ca725a8544631a489a3eba1eb9683b65b90c1815` with uncommitted changes; hashes
identify the measured compiler and sources.

C uses Clang `-O3`, Rust `-O --edition=2021`, Haskell GHC `-O2` with documented
extensions, and MLF the checked eMLF -> xMLF -> LLVM pipeline with Clang `-O2`.
Every MLF compilation builds the runtime afresh and links GMP. There is no
cached runtime object, LTO, CPU-specific tuning, profiling or sanitizer
instrumentation in the timed runs. See [methodology](README.md) and [flags](manifest.json).

Compilation includes startup, frontend processing, code generation, runtime
compilation and linking. Cabal/compiler builds and correctness checks are
outside the samples. Runtime includes startup, input, output, GC and exit.
Language order rotates between rounds. Each timing input is checked before
sampling and every timed output is checked after the timer stops. All 28
full-suite runtime medians exceed 100 ms; startup time is not subtracted.

## Compilation

Full-suite wall-clock medians, in milliseconds:

| Workload | C (ms) | Rust (ms) | Haskell (ms) | MLF (ms) | MLF / C |
| --- | ---: | ---: | ---: | ---: | ---: |
| binary-trees | 148.91 | 171.07 | 462.86 | 452.46 | 3.04x |
| pidigits | 148.83 | 139.69 | 485.04 | 455.57 | 3.06x |
| n-body | 170.34 | 152.11 | 533.63 | 829.52 | 4.87x |
| fannkuch-redux | 162.91 | 207.70 | 501.85 | 546.16 | 3.35x |
| spectral-norm | 158.83 | 181.36 | 573.86 | 537.56 | 3.38x |
| fasta | 166.97 | 185.56 | 532.84 | 651.95 | 3.90x |
| mandelbrot | 151.32 | 188.41 | 492.24 | 574.34 | 3.80x |

MLF's geometric mean compilation ratio is 3.59x C. N-body is close to the
5x limit, so this margin is sensitive to system load and toolchain changes.
Corpus latency sums seven fresh compilations per round, including all seven
compiler startups; it is not persistent-compiler throughput.

| Pipeline | Seven-program latency (s) | Programs/s |
| --- | ---: | ---: |
| Clang/C | 1.11080 | 6.302 |
| rustc/Rust | 1.23276 | 5.678 |
| GHC/Haskell | 3.58151 | 1.954 |
| MLF/LLVM | 4.06266 | 1.723 |

## Runtime

Full-suite wall-clock medians, in seconds:

| Workload | Input | C (s) | Rust (s) | Haskell (s) | MLF (s) | MLF / C |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| binary-trees | 16 | 0.34513 | 0.41452 | 0.13066 | 0.33613 | 0.97x |
| pidigits | 10,000 | 0.37159 | 0.37576 | 0.50156 | 0.44479 | 1.20x |
| n-body | 2,000,000 | 0.10918 | 0.10907 | 0.13333 | 0.12134 | 1.11x |
| fannkuch-redux | 10 | 0.21637 | 0.16425 | 0.24318 | 0.24989 | 1.15x |
| spectral-norm | 2,000 | 0.20617 | 0.28461 | 0.88695 | 0.56345 | 2.73x |
| fasta | 2,000,000 | 0.21700 | 0.24946 | 0.39964 | 0.33591 | 1.55x |
| mandelbrot | 4,096 | 0.94426 | 0.22460 | 1.02050 | 0.65124 | 0.69x |

The geometric mean MLF runtime ratio is 1.23x C. This average does not
replace a per-workload target: spectral-norm still needs optimization. The
separate seven-sample Mandelbrot run above also passes its stricter 1x gate.

## Correctness and validation

All baseline sources remain pinned at Benchmarks Game revision
`40296663ed350d5fe4a6ab5e367bab61cb77c219`, with authors, original files,
exact patches, SHA256 hashes and the BSD license recorded in the manifest.
All programs are sequential. The harness still checks all allocated tree nodes,
all digits and permutations, all n-body integration steps, all matrix-vector
products, every FASTA base and every Mandelbrot pixel. No measured executable
can access oracle results. Per-workload provenance records source differences.

Mandelbrot requires exact headers, raster bytes, MSB-first packing and zero
padding against an independent Python complex recurrence at 1, 2, 7, 8, 9,
200 and 4096. The oracle also matches the pinned upstream 200-pixel fixture.
Fasta uses exact bytes; n-body/spectral-norm require finite results within 1e-8.

Validation of the final compiler and sources:

- `cabal test -j1 --test-show-details=direct`: 287 compiler checks, 43 Figure 12
  expressions plus 36 supplementary checks, 23 benchmark harness tests, and
  216 backend fixtures containing 214 execution rows on each of the interpreter
  and LLVM backends.
- `MLF_LLVM_TEST_OPT=-O0 cabal test backend-tests -j1 --test-show-details=direct`:
  the same 214 rows on both backends without native optimization.
- `MLF_LLVM_TEST_CFLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer -DMLF_GC_INTEGER_BYTES=64' cabal test backend-tests -j1 --test-show-details=direct`:
  the same matrix with address/undefined-behavior sanitizers and frequent GMP collection.
- New regressions cover recursive Double captures, signed zero/NaN/infinity,
  lazy failing arguments, branch-local payload loads, the specialization cap,
  integer promotion and negative-range transitions, 189 native arithmetic
  results independently calculated with Haskell Integer, and GMP byte errors.

## Resources and retained history

MLF CPU is median user+system time; RSS is the maximum per-process peak across
samples; binary size excludes dynamic libraries. The full JSON includes every
language's measurements.

| Workload | CPU (s) | Peak RSS (MiB) | Binary (KiB) |
| --- | ---: | ---: | ---: |
| binary-trees | 0.3326 | 21.47 | 69.20 |
| pidigits | 0.4398 | 197.62 | 69.18 |
| n-body | 0.1184 | 1.53 | 134.12 |
| fannkuch-redux | 0.2468 | 1.50 | 85.41 |
| spectral-norm | 0.5583 | 1.61 | 85.45 |
| fasta | 0.3313 | 1.92 | 101.60 |
| mandelbrot | 0.6457 | 1.72 | 85.40 |

GMP results and allocations made within native regions remain live until the
next IO-driver collection point. Pidigits therefore still uses substantially
more memory than C. These changes do not alter collection semantics.

The [previous seven-workload report](results/2026-10-08-seven-workloads-macos-arm64.json),
[earlier four-workload optimization](results/2026-10-08-optimized-macos-arm64.json)
and [original milestone](results/2026-10-08-first-milestone-macos-arm64.json)
remain unchanged. Compare matching workload rows, inputs and sample counts.
These results apply to this host/toolchain/source snapshot; system load,
thermal state and filesystem caches are not controlled. Remaining work is
tracked in [INVESTIGATION.md](INVESTIGATION.md).

This benchmark measures practical end-to-end compiler/language implementation performance. It does NOT perfectly isolate backend code-generation quality because C, Rust, Haskell and MLF have different language semantics, runtime systems, allocation models and abstractions.
