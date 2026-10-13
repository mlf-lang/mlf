# Native MLF stage 1 benchmarks: 2026-10-13

All **nine workloads pass the 5x C compilation and 2x C runtime limits** using
**the compiler written in MLF**. The largest compilation ratio is **4.762x**
(n-body); the largest runtime ratio is **1.876x** (reverse-complement).

The measured executable is native stage 1, built from `bootstrap/Main.emlf` by
the Haskell seed. It performs source parsing, inference, checked xMLF elaboration
and LLVM generation itself. Timed workload binaries use the ordinary runtime.
The [preceding report](results/2026-10-09-bootstrap-macos-arm64.json) measured
the Haskell seed; its timing results are not substituted for native compilation.

```sh
cabal bench compiler-bench -j1 --benchmark-options='--emlf /Volumes/src/mlf/dist-newstyle/bootstrap-stage1-final/emlf-stage1 --runs 5 --max-compile-ratio 5 --max-runtime-ratio 2 --output benchmarks/results/2026-10-13-stage1-final-macos-arm64.json'
```

The [archived report](results/2026-10-13-stage1-final-macos-arm64.json) contains
**180 fresh compilation samples and 180 runtime samples**, independent
correctness checks before timing and after every fresh build, exact commands,
source/library/tool hashes, CPU time, peak RSS and executable sizes. All recorded
input hashes remained unchanged; all **18 per-workload limits** passed.
Geometric means do not substitute for individual workloads passing.

## Compilation

Wall-clock medians in milliseconds. MLF total includes checked eMLF -> xMLF
-> LLVM emission, IR writes, compiling the complete C runtime afresh and linking.
The general [native build driver](../scripts/compile_native.py) overlaps the
frontend with fresh runtime compilation, then compiles and links the LLVM IR.
At most two compiler processes overlap within a build; samples and languages
run serially. No emitted LLVM or runtime object is reused between samples.
The LLVM emission column is the frontend subprocess and is included in total.
Compiler, dependency and harness builds are outside the measured regions.

| Workload | C | Rust | Haskell | MLF emit LLVM | MLF total | MLF/C |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| binary-trees | 142.92 | 159.89 | 433.68 | 133.42 | 411.72 | 2.881x |
| pidigits | 147.51 | 133.63 | 433.36 | 117.55 | 412.44 | 2.796x |
| n-body | 159.32 | 146.83 | 484.98 | 533.70 | 758.62 | 4.762x |
| fannkuch-redux | 150.80 | 193.46 | 464.43 | 262.18 | 483.00 | 3.203x |
| spectral-norm | 151.32 | 163.73 | 533.42 | 249.65 | 436.85 | 2.887x |
| fasta | 153.49 | 171.90 | 484.90 | 465.78 | 729.56 | 4.753x |
| mandelbrot | 140.58 | 174.23 | 443.87 | 248.80 | 472.11 | 3.358x |
| reverse-complement | 144.07 | 151.88 | 491.66 | 295.57 | 530.42 | 3.682x |
| k-nucleotide | 166.29 | 229.41 | 982.52 | 487.19 | 711.89 | 4.281x |

Geometric mean of MLF/C compilation ratios: **3.549x**.
Median sum of nine fresh compilations: **4.947 s** for MLF and
**1.358 s** for C. Each compilation starts a fresh process.

## Runtime

Wall-clock medians in seconds, including startup, input, output, GC and exit.
Inputs, flags and independent oracles are in the [manifest](manifest.json)
and [methodology](README.md). FASTA input generation is outside timing;
reading the resulting stdin bytes is timed.

| Workload | Input | C | Rust | Haskell | MLF | MLF/C |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| binary-trees | 16 | 0.33955 | 0.40532 | 0.12687 | 0.28742 | 0.846x |
| pidigits | 10,000 | 0.36363 | 0.36601 | 0.48198 | 0.41496 | 1.141x |
| n-body | 2,000,000 | 0.10668 | 0.10566 | 0.12638 | 0.11937 | 1.119x |
| fannkuch-redux | 10 | 0.21139 | 0.16037 | 0.23192 | 0.22981 | 1.087x |
| spectral-norm | 2,000 | 0.20139 | 0.27754 | 0.87670 | 0.16153 | 0.802x |
| fasta | 2,000,000 | 0.21044 | 0.24145 | 0.38273 | 0.33410 | 1.588x |
| mandelbrot | 4,096 | 0.93338 | 0.22023 | 0.98915 | 0.63220 | 0.677x |
| reverse-complement | 10,000,000 | 0.13902 | 0.07680 | 0.37961 | 0.26079 | 1.876x |
| k-nucleotide | 1,000,000 | 0.17015 | 1.48676 | 1.80226 | 0.28199 | 1.657x |

Geometric mean of MLF/C runtime ratios: **1.136x**.
All C and MLF runtime medians exceed 100 ms. The harness flags the shorter
reverse-complement/Rust measurement, where startup can materially affect the ratio.

## Compiler changes and resource tradeoffs

The native compiler now reuses type translation results, traverses dense graph
state through directly lowered ST operations, and specializes bounded recursive
higher-order calls. Ordinary integer multiplication and quotient/remainder use
checked machine arithmetic with the existing unbounded-integer fallback.
Compact BDWGC objects remove unused ordinary-collector headers and store large
constructor fields inline. These changes are general compiler/runtime paths;
the workload sources, algorithms, inputs and optimization flags are unchanged.
The native build driver also overlaps the independent frontend and runtime
compilation phases while including both in the measured interval.

The native compiler uses a **512 MiB initial GC heap** and free-space divisor 1.
This trades memory for compilation speed; the largest observed per-child
compilation RSS was **532.0 MiB**. The reported RSS is the largest child peak,
not the sum of simultaneous child memory. CPU time sums all compiler children.
Automatic collection and IO-boundary collection remain enabled. Environment
settings can override the initial heap and divisor, and configured heap caps
are respected. Generated workload programs retain the ordinary pooled runtime.

The [first native baseline](results/2026-10-11-stage1-baseline-macos-arm64.json)
failed all nine compilation limits, with a worst ratio of 291.649x C. Later
checkpoint reports retain unsuccessful candidates and partial measurements.
These separate runs demonstrate the overall improvement, including scheduling
and allocation changes; they do not isolate each optimization's contribution.

## Workloads and validation

All **36 workload source hashes** match the preceding Haskell-seed report.
The MLF programs use declarations, typed recursion, layout, conditionals,
infix operators and constructor or literal equations. All four languages pass
the independent oracles for every preparation input and timed execution;
every fresh compilation also runs a post-build correctness check.

The [archived validation record](results/2026-10-13-stage1-validation.json)
identifies the same stage 1 executable by SHA-256 and records these passing gates:

- Byte-identical stage 2/3 LLVM, with **7,023 parity cases**: 3,178 accepted and
  3,845 rejected, plus 59 runtime rows executed on both native backends.
- **468 rows x 2 backends** in each of three matrices: standard runtime,
  compact runtime with an 8 MiB initial heap, and native MLF interpreter/LLVM
  drivers built by stage 1. No executions are missing; the native driver matrix
  has no fallback to the Haskell implementations.
- **26 port fixtures x 2 backends**, 564 compiler checks, all 43 Figure 12
  expressions and 36 supplementary checks, and 36 benchmark-harness tests.
- Runtime allocation, sharing, collection and state regressions, plus positive
  and negative ABI link tests. The compact profile also passes collector debug,
  incremental collection and disabled-interior-pointer checks.

The latest fixed-point gate reused matching seed-produced stage 1 LLVM after
checking its provenance, then freshly compiled stages 2 and 3 and reran all
parity checks. The stage 2/3 LLVM SHA-256 is
`2c9a554702c19354688eb849981c2547ae6e204744fec34f38f2f6da3fce1c59`.
Build and validation commands are documented in [bootstrap/README.md](../bootstrap/README.md).

## Comparison scope

Host: macOS 26.6.2, ARM64, 10 logical CPUs; Python 3.14.8. Toolchains:
Clang 23.1.3, rustc 1.99.0, GHC 9.14.1 and GMP 6.3.0. This run spans
2026-10-13T12:06:16.727474+00:00 to 2026-10-13T12:12:34.044067+00:00.
The checkout is based on `818c7a0b6a08902f43aad1595cdddc735a3260f0` with uncommitted
changes; recorded hashes identify the measured inputs. C uses `-O3`, Rust `-O`,
GHC `-O2`, and the MLF LLVM/runtime pipeline Clang `-O2`. Compiler/test jobs
finished before benchmark timing began. OS caches and thermal state are not
controlled, and these margins are measurements on this host rather than
performance guarantees for other machines or inputs.
