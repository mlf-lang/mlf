# Measured results: 2026-10-08

Collected with `cabal bench -j1 --benchmark-options='--runs 7'`, using unchanged input/tool hashes throughout the run. Date is local time (Asia/Shanghai); the JSON records UTC.

Host: macOS-26.6.2-arm64-arm-64bit-Mach-O, 10 logical CPUs; Python 3.14.8.

Toolchains: Clang 23.1.2, rustc 1.99.0, GHC 9.14.1, GMP 6.3.0; optimized MLF compiler built by Cabal with GHC `-O2`, default `-A32m`. Exact paths, hashes, versions and commands are in the [archived JSON](results/2026-10-08-macos-arm64.json).

Workload: binary-trees, maximum depth 16, seven samples per dimension and language. Compilation is fresh source-to-executable latency, including LLVM emission, runtime compilation, and linking; runtime uses separately prepared and validated executables. Medians:

| Pipeline | Compile (ms) | Compile / C | Runtime (s) | Runtime / C | Runtime CPU (s) | Peak RSS (MiB) | Binary (KiB) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Clang/C | 154.67 | 1.00x | 0.34610 | 1.00x | 0.3432 | 5.41 | 33.02 |
| rustc/Rust | 170.71 | 1.10x | 0.41560 | 1.20x | 0.4109 | 5.61 | 443.91 |
| GHC/Haskell | 495.56 | 3.20x | 0.12706 | 0.37x | 0.1204 | 23.31 | 13294.45 |
| MLF/LLVM | 411.48 | 2.66x | 0.31748 | 0.92x | 0.3136 | 21.45 | 68.26 |

**Both requested targets pass:** compilation is below 5× C and runtime is below 1× C. This also holds in every paired round: the worst compile ratio is 2.91× and the worst runtime ratio is 0.93×. MLF runtime samples span 314.32–321.11 ms; C samples span 344.53–358.97 ms. Haskell remains faster than both.

These are measurements for this workload, input, and machine, not a universal performance guarantee for arbitrary programs or platforms. There is one supported workload, so a cross-workload geometric mean is omitted. The JSON includes summed corpus compilation cost and programs/second, but with one program this duplicates latency and does not isolate processing throughput.

## Optimization and previous baseline

The [original three-sample report](results/2026-10-07-macos-arm64.json) measured MLF at 89.48046 s runtime, 353.30 ms compilation, and 753.19 MiB peak RSS. The new runtime is about **282× faster**, with 21.45 MiB peak RSS. Compilation takes somewhat longer because of the new optimization and generated native workers, while remaining comfortably inside the requested 5× C limit.

All four workload source hashes match the original report; baseline flags and timing boundaries are unchanged. Profiling the original native program showed GC, thunk/application dispatch, and allocation dominating execution. The implementation now:

- Simplifies checked erasure and recognizes the ordinary recursive-datatype fixed-point encoding by expression structure and resolved identities.
- Uses direct native workers for known saturated calls, with conservative demand analysis and lazy wrappers for partial or escaping functions.
- Lowers conditionals and checked small-integer arithmetic directly to LLVM, with GMP overflow fallback.
- Uses immediate integers/booleans/nullary data, inline unary/binary constructor fields, and reusable managed allocation pages.

There is no benchmark-specific tree transformation, precomputed tree check, tree sharing, or change to the workload. Each MLF node remains a separately traced object; the generic allocator reuses pages without a tree-lifetime arena. See [backend design](../docs/llvm-backend.txt).

## Validation

- `cabal test -j1 --test-show-details=direct`: all four suites pass; 285 main checks, 43 Figure-12 expressions and 36 supplementary checks, 130 backend fixtures with 108 rows executed on both backends, and 12 benchmark harness tests.
- The shared backend matrix also passes with AddressSanitizer/UndefinedBehaviorSanitizer and with LLVM optimization disabled (`MLF_LLVM_TEST_OPT=-O0`).
- New cases cover 400 integer arithmetic/comparison results around the immediate/GMP boundary, generic curried overflow, lazy partial workers, mutual captures, escaping recursive functions, cyclic and partially applied constructors, collection with retained closures, and disjoint lexical identities. LLVM emission is invariant under identity renaming and saved-target round trips.
- `cabal bench -j1 --benchmark-options='--runs 7'`: all four native outputs agree with the independent oracle at inputs 0, 7, 10 and 16, including the pinned upstream depth-10 fixture; all timed outputs also match.
- The untimed native allocation audit checks every fully constructed MLF tree node at depths 6, 7, 10, and 16. Depth 16 constructs exactly **14,985,902** nodes across the stretch, retained, and temporary trees.
- `cabal bench -j1 --benchmark-options='snake --runs 2 --output dist-newstyle/native-optimization/snake.json'` passes the existing compilation gate, verifies source/saved-xMLF emission parity, and matches the Haskell game transcript. The native Snake median is 540.25 ms versus GHC's 841.74 ms in this supplementary run.

## Scope and remaining workloads

Sources are pinned at Benchmarks Game revision `40296663ed350d5fe4a6ab5e367bab61cb77c219`: Kevin Carson’s `binarytrees-gcc-1`, Rust Project Developers/TeXitoi’s `binarytrees-rust-1`, and Don Stewart’s `binarytrees-ghc-1`. [Provenance](binary-trees/PROVENANCE.md) records the portability, sequential allocation and anti-sharing adaptations. The [MLF implementation](binary-trees/mlf/main.emlf) uses ADTs, recursion and standard-prelude IO.

C/Rust/Haskell/MLF have different node layouts, integer representations, allocation/GC and cleanup behavior. MLF also uses an input adapter and IO safe points. Normal startup, IO and exit costs remain in runtime samples; OS caches, thermal state and system load are uncontrolled. Haskell anti-sharing flags deliberately preserve tree construction. Seven samples on one machine and one workload are reported; use the raw distributions before drawing fine-grained conclusions.

[Investigation](INVESTIGATION.md) covers n-body, spectral-norm, mandelbrot, fannkuch-redux, pidigits, fasta and reverse-complement. They are deferred for missing floating point, arithmetic, arrays/mutation or byte/string operations, or an incompatible representation. A list-based fannkuch is expressible, but is not a like-for-like array workload. Next: multiply/quotient primitives for pidigits, then Double/sqrt for n-body, followed by indexed arrays.

## Implementation files

- `benchmarks/`: vendored originals, adapted baselines with patches, BSD license, pin manifest, MLF workload, methodology, selection notes and this measured report.
- `scripts/benchmark-languages.py`: fresh-build and independent-runtime driver, correctness oracles, resource usage, integrity checks, summaries and versioned JSON.
- `bench/Main.hs`, `mlf.cabal`: default Cabal integration, source packaging and harness test suite; Snake/revision modes retained.
- `test/BackendCases.hs`: tree checks on both backends.
- `test/BenchmarkHarnessMain.hs`, `test/test_benchmarks.py`, `test/benchmark_allocations.c`: failure-path, timing-boundary, RSS and allocation checks.
- `src/MLF/LLVM.hs`, `src/MLF/LLVM/{Optimize,Analysis,Codegen}.hs`: checked lowering, simplification, demand analysis, and native worker emission.
- `runtime/mlf_runtime.{c,h}`: compact representations, overflow fallback, managed allocation pages, and an opt-in untimed allocation audit hook.
- `test/NativeOptimization.hs`, `test/BackendMain.hs`: active shared-backend optimization regressions.
- Root `README.md` and `.gitignore`: usage and generated-report/cache exclusions.

See the [methodology](README.md) for exact compiler commands, flags, source-to-binary timing boundaries, runtime validation and adding workloads.

This benchmark measures practical end-to-end compiler/language implementation performance. It does NOT perfectly isolate backend code-generation quality because C, Rust, Haskell and MLF have different language semantics, runtime systems, allocation models and abstractions.
