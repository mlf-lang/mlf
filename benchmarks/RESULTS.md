# Cross-language benchmarks: 2026-10-09

All **nine workloads pass the 5x C compilation and 2x C runtime limits** at
the existing default inputs on this machine. The largest compilation ratio
is **4.20x** (n-body); the largest runtime ratio is **1.90x**
(reverse-complement). Every timing input passes the independent correctness
oracle in C, Rust, Haskell and MLF.

```sh
cabal bench compiler-bench -j1 --benchmark-options='--runs 5 --max-compile-ratio 5 --max-runtime-ratio 2 --output benchmarks/results/2026-10-09-optimized-suite-macos-arm64.json'
```

The [archived report](results/2026-10-09-optimized-suite-macos-arm64.json)
contains **180 fresh compilation samples and 180 runtime samples**, preparation
and post-build correctness checks, exact commands, source/library/tool hashes,
CPU time, peak RSS and executable sizes. All recorded input hashes remained
unchanged. All **18 per-workload performance checks passed**; geometric means
are descriptive and are not used to excuse an individual failure.

## Compilation

Wall-clock medians in milliseconds. MLF total includes checked eMLF -> xMLF
-> LLVM emission, IR writes, compiling the complete C runtime afresh and linking.
The LLVM emission column measures the compiler subprocess and is already
included in the total. Compiler, dependency and harness builds are excluded.

| Workload | C | Rust | Haskell | MLF emit LLVM | MLF total | MLF/C |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| binary-trees | 141.07 | 167.11 | 471.84 | 61.39 | 384.24 | 2.72x |
| pidigits | 148.93 | 134.27 | 468.40 | 61.75 | 387.85 | 2.60x |
| n-body | 163.47 | 153.28 | 524.62 | 266.62 | 687.22 | 4.20x |
| fannkuch-redux | 156.42 | 199.59 | 493.65 | 100.84 | 493.25 | 3.15x |
| spectral-norm | 146.61 | 166.27 | 572.29 | 98.60 | 470.06 | 3.21x |
| fasta | 167.21 | 179.72 | 513.53 | 171.87 | 648.51 | 3.88x |
| mandelbrot | 143.00 | 180.29 | 479.70 | 122.82 | 501.92 | 3.51x |
| reverse-complement | 148.57 | 154.89 | 499.80 | 145.19 | 590.39 | 3.97x |
| k-nucleotide | 167.07 | 239.01 | 1064.95 | 199.30 | 633.15 | 3.79x |

Geometric mean of MLF/C compilation ratios: **3.41x**.
The median sum of nine fresh MLF compilations is
**4.796 s**, versus
**1.390 s** for C.
These sums include a new compiler process for every program; they do not
isolate persistent-compiler throughput.

## Runtime

Wall-clock medians in seconds, including startup, input, output, GC and exit.
Inputs, flags and independent oracles are in the [manifest](manifest.json)
and [methodology](README.md). FASTA input generation is outside timing;
reading the resulting stdin bytes is timed.

| Workload | Input | C | Rust | Haskell | MLF | MLF/C |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| binary-trees | 16 | 0.34497 | 0.41273 | 0.13196 | 0.35284 | 1.02x |
| pidigits | 10,000 | 0.36813 | 0.37027 | 0.48833 | 0.44653 | 1.21x |
| n-body | 2,000,000 | 0.10922 | 0.10962 | 0.13222 | 0.12240 | 1.12x |
| fannkuch-redux | 10 | 0.21572 | 0.16320 | 0.24046 | 0.23570 | 1.09x |
| spectral-norm | 2,000 | 0.20292 | 0.28118 | 0.88484 | 0.16290 | 0.80x |
| fasta | 2,000,000 | 0.21854 | 0.24894 | 0.40227 | 0.33733 | 1.54x |
| mandelbrot | 4,096 | 0.93822 | 0.22382 | 1.01143 | 0.63488 | 0.68x |
| reverse-complement | 10,000,000 | 0.15003 | 0.08595 | 0.39094 | 0.28500 | 1.90x |
| k-nucleotide | 1,000,000 | 0.18032 | 1.69037 | 1.99705 | 0.29892 | 1.66x |

Geometric mean of MLF/C runtime ratios: **1.17x**.
The harness flags reverse-complement/Rust below 100 ms; startup can materially
affect that particular comparison. Every C and MLF median exceeds 100 ms.

## Changes behind these results

- Inference caches immutable generalization-scope ancestry and per-operation
  kinds. Expansion checks its actual fresh-identity requirement instead of
  counting the complete graph on every instance. Full graph/index validation,
  unification permissions and independent xMLF checking remain enabled.
- Native IO regions execute allocation and byte input/output directly. Explicit
  entry and caller roots permit collection while preserving live values.
  Bounded-index workers, branch-local range facts and storage alias metadata
  reduce repeated checks without changing arbitrary-precision fallback.
- Exact byte-copy loops use a guarded LLVM memory intrinsic. Overlapping forward
  copies and invalid ranges retain the original scalar loop and error order.
- Adjacent table read/add/write operations fuse while preserving the old count
  as a snapshot. Tagged-key tables retain arbitrary integer values and promote
  on the first large key. Existing-key updates use khash lookup; insertion and
  table growth remain library operations.
- The collector shares its mark helper instead of duplicating its growable-stack
  code for each object field. This reduces optimization work when compiling the
  fresh runtime. Generated numeric loops retain their existing inlining policy.
- The MLF sources carry spectral-norm row sums in scalar arguments, fill
  reverse-complement output by rows, and maintain rolling k-nucleotide keys
  with the new strict, unbounded `andInt` primitive. These follow the original
  required algorithms and are recorded in their provenance files. All seven
  k-mer tables still count every window; the runtime has no workload helper.

See the [backend design](../docs/llvm-backend.txt),
[numeric semantics](../docs/numeric-arrays.txt), and provenance for
[spectral-norm](spectral-norm/PROVENANCE.md),
[reverse-complement](reverse-complement/PROVENANCE.md) and
[k-nucleotide](k-nucleotide/PROVENANCE.md).

## Validation

- `cabal test -j1 --test-show-details=direct`: **289 compiler checks**,
  **43 Figure 12 cases plus 36 supplementary checks**, **242 shared backend
  fixtures with 260 execution rows x 2 backends**, and **30 benchmark-harness
  tests**, all passing.
- The same backend matrix passes at LLVM `-O0` with AddressSanitizer,
  UndefinedBehaviorSanitizer, collection threshold 32 and GMP threshold 64 bytes.
  It covers nested native collections, caller roots, small/large integer table
  promotion, snapshot values, copy aliasing, bounds and error order.
- Graph regressions compare complete graphs and witness identities against the
  full-graph solver and an independent uncached expansion. Deep branching scopes
  and exact fresh-identity exhaustion are included.
- The untimed work audit checks actual k-nucleotide writes and distinct insertions
  in all seven tables against independent Python sets. Every timed binary's
  output is checked against the appropriate independent oracle.

```sh
MLF_LLVM_TEST_OPT=-O0 MLF_LLVM_TEST_CFLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer -DMLF_GC_INTEGER_BYTES=64' cabal test backend-tests -j1 --test-show-details=direct
```

## Comparison scope

Host: macOS 26.6.2, ARM64, 10 logical CPUs; Python 3.14.8. Toolchains:
Clang 23.1.2, rustc 1.99.0, GHC 9.14.1 and GMP 6.3.0. The run spans
2026-10-08T19:22:16.199853+00:00 to 2026-10-08T19:28:43.048927+00:00.
The checkout is based on `35168108576cc830132f50f361616d9ec6abb749` with uncommitted
changes; recorded hashes identify the measured inputs. C uses `-O3`, Rust `-O`,
GHC `-O2`, and MLF's LLVM/runtime pipeline Clang `-O2`. There is no LTO,
fast-math, explicit SIMD, parallel benchmark worker or cached runtime object.

The pinned C/Rust/Haskell sources, optimization flags, default inputs and
correctness rules match the previous nine-workload snapshot. Haskell dependency
setup happens before measurement; exact package units and transitive library
hashes are recorded. Fresh output directories prevent object reuse, language
order rotates between rounds, and OS file caches remain warm.

This measures practical end-to-end language/compiler implementations. It does
not isolate backend code generation: language semantics, integer representations,
runtimes, allocation and data structures differ. For example, C and MLF use
rolling integer k-mer keys, Haskell packs each window, and Rust uses byte-vector
keys. MLF retains arbitrary-precision arithmetic and checked mutable access.
The limits passed on this machine at these inputs; five samples are not a
performance guarantee for other sizes, machines or future runs.

## Earlier snapshots

The [previous nine-workload report](results/2026-10-08-dna-suite-macos-arm64.json)
is preserved unchanged. It had n-body compilation at 5.19x C and runtime gaps
for spectral-norm (2.73x), reverse-complement (19.38x) and k-nucleotide (11.74x).
The earlier [seven-workload report](results/2026-10-08-mandelbrot-suite-macos-arm64.json)
and [Mandelbrot 5x/1x gate](results/2026-10-08-mandelbrot-optimized-macos-arm64.json)
are also historical snapshots.
