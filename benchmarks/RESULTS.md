# Native 3× compilation gate — 2026-10-18

> Historical evidence notice: Raw files previously stored under
> `tools/profile/results/` were removed from this branch and its Git history.
> References to those files below describe historical evidence that is not
> available in this repository; retained summaries are not independent access
> to the original raw records.


All nine workloads pass the median 3× C compilation / 2× C runtime gate, with every observed maximum MLF sample also below the limit relative to the corresponding minimum C sample.

Seven samples were collected for each compiler/workload with alternating order, fresh runtime/object/output directories, unchanged C reference flags, equal exact-executable runtime warm-up and independent output validation. All compilation stages, including runtime C, LLVM compilation and linking, remain timed. Decisions use unrounded ratios.

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

[The raw native report](../tools/profile/results/2026-10-18-compile3/bench-final.json) contains all 189 compilation and 189 runtime samples. [The detailed report](../tools/profile/RESULTS.md) includes ranges, MADs, stage overlap, diagnostic phases, rejected experiments, reproducible commands, source/toolchain hashes and all six native test groups. All 63 final standard LLVM outputs match the starting compiler.

Ordinary self-compilation on identical frozen sources measured 257.289 s for the original and 181.955 s for the candidate (-29.280%). This is the separately reported source-to-LLVM boundary.

Compiler SHA-256: `0bc6f35450ec7bf03df75a1dbebedea3d5de5ed692aabb69e97ed2dbb364806d`. Measurements use Apple M1 Max, macOS 26.6.2, Clang/LLVM 23.1.3, GMP 6.3.0 and BDWGC 8.2.12. The native benchmark uses the explicitly configured LLVM backend described in the reproduction commands. No commit or push was made; the earlier report below is preserved verbatim.

---

# Native MLF profiling milestone: 2026-10-16

All nine workloads pass the **5x C compilation / 2x C runtime** limits with
seven samples per compiler and workload. The runner, package manager, compiler
and test suites are native MLF; this run uses no GHC, Cabal or Python.
The [raw report](../tools/bench/results/2026-10-16-native-macos-arm64.json)
contains 189 fresh compilation samples and 189 timed runtime samples across
C, the original native MLF compiler and the final native MLF compiler.
Haskell and Rust were not remeasured.

| Workload | C compile (ms) | MLF compile (ms) | Compile / C | C runtime (s) | MLF runtime (s) | Runtime / C |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| binary-trees | 139.18 | 479.10 | 3.442x | 0.34950 | 0.29660 | 0.849x |
| pidigits | 142.36 | 471.08 | 3.309x | 0.37409 | 0.44486 | 1.189x |
| n-body | 154.50 | 764.37 | 4.947x | 0.10844 | 0.12236 | 1.128x |
| fannkuch-redux | 145.33 | 548.59 | 3.775x | 0.21508 | 0.23457 | 1.091x |
| spectral-norm | 144.75 | 502.74 | 3.473x | 0.20542 | 0.16582 | 0.807x |
| fasta | 149.12 | 715.56 | 4.798x | 0.22969 | 0.35480 | 1.545x |
| mandelbrot | 140.01 | 533.57 | 3.811x | 0.95914 | 0.65273 | 0.681x |
| reverse-complement | 137.27 | 584.30 | 4.257x | 0.18693 | 0.29164 | 1.560x |
| k-nucleotide | 160.55 | 693.47 | 4.319x | 0.17519 | 0.29314 | 1.673x |

The largest compilation ratio is **4.947x** for n-body, leaving only about 1%
margin. The largest runtime ratio is **1.673x** for k-nucleotide. These are
medians on this machine, not a guarantee against timing variation. Workload
sources, default inputs, correctness oracles and C optimization flags are
unchanged. All 63 final MLF LLVM outputs match the original compiler's
corresponding output byte for byte.

Each compilation uses a fresh runtime object and output directory. MLF source
emission overlaps runtime C compilation, followed by LLVM compilation and
linking. Every freshly linked executable receives one untimed, output-checked
invocation at the measured input before its timed fresh process. Startup, IO,
collection and exit remain inside the timed run. This avoids the operating
system's one-time verification of a newly linked executable dominating runtime
ratios. The [runner instructions](../tools/bench/README.md) describe reproduction.

An [earlier run](../tools/profile/results/2026-10-16/earlier-unwarmed-v2-benchmark.json)
using an intermediate compiler failed n-body compilation at 5.006x and lacked
this exact-file runtime warm-up. Its runtime ratios are not the final results.
A [controlled first-launch check](../tools/profile/results/2026-10-16/first-launch.json)
recorded 0.7742 s on first execution versus 0.1089 s on repeat execution of the
same n-body binary. The failed run is retained as diagnostic evidence.

See the [self-compilation report](../tools/profile/RESULTS.md) for the compiler
changes, phase profiles, ordinary compiler comparison and native validation.

---

# Stage 3 validation reuse: 2026-10-14

The rebuilt stage 3 compiler passes the **5x C compilation / 2x C runtime
limits for all nine workloads**, using seven samples per language and workload.
**n-body: 4.742x compilation, 1.122x runtime. FASTA: 4.526x compilation,
1.518x runtime.** The largest compilation ratio is n-body's 4.742x; the largest
runtime ratio is reverse-complement's 1.686x.

The solver now reuses final graph validation across normalization. The complete
graph and its structural, binding and scope indexes are checked first.
Normalization only strengthens flags on non-generalization nodes, preserving
every field examined by graph validation and index construction. The independent
xMLF type, inferred-type agreement and source-erasure checks still run.

The measured command was:

```sh
cabal bench compiler-bench -j1 --benchmark-options='--emlf dist-newstyle/compile-margin/bootstrap/emlf-stage3 --runs 7 --max-compile-ratio 5 --max-runtime-ratio 2 --output dist-newstyle/compile-margin/stage3-benchmarks.json'
```

The [raw benchmark report](results/2026-10-14-stage3-normalization-macos-arm64.json)
contains **252 fresh compilation samples and 252 runtime samples**, independent
correctness checks, commands, hashes, CPU time, peak RSS and executable sizes.
The [validation archive](results/2026-10-14-stage3-normalization-validation.json)
binds those measurements to the same compiler used for the bootstrap and both
native backend matrices. Dates here use Asia/Shanghai; raw timestamps use UTC.

## Compilation

Wall-clock medians in milliseconds. LLVM emission includes parsing, inference,
elaboration and xMLF checking. Total compilation overlaps emission with a fresh
runtime compilation, then compiles and links the LLVM. Each sample uses a new
directory and runtime object, with the existing flags and measured build phases.

| Workload | C | Rust | Haskell | MLF emit LLVM | MLF total | MLF/C |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| binary-trees | 143.47 | 164.12 | 457.66 | 129.84 | 417.94 | 2.913x |
| pidigits | 149.18 | 136.40 | 457.93 | 114.08 | 424.03 | 2.842x |
| n-body | 160.50 | 145.79 | 513.53 | 520.91 | 761.09 | 4.742x |
| fannkuch-redux | 155.20 | 198.65 | 499.33 | 253.49 | 490.10 | 3.158x |
| spectral-norm | 153.18 | 164.33 | 565.61 | 236.71 | 446.94 | 2.918x |
| fasta | 157.93 | 174.69 | 513.18 | 436.26 | 714.84 | 4.526x |
| mandelbrot | 142.88 | 175.12 | 466.07 | 239.20 | 484.31 | 3.390x |
| reverse-complement | 147.30 | 153.74 | 517.00 | 285.47 | 531.66 | 3.609x |
| k-nucleotide | 168.80 | 233.93 | 1052.27 | 478.84 | 708.52 | 4.197x |

Geometric mean of compilation ratios: **3.525x**.

## Runtime

Wall-clock medians in seconds, including startup, input, output, collection and
exit. Inputs and correctness checks follow the [methodology](README.md).

| Workload | Input | C | Rust | Haskell | MLF | MLF/C |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| binary-trees | 16 | 0.34074 | 0.40601 | 0.12730 | 0.29159 | 0.856x |
| pidigits | 10,000 | 0.36498 | 0.37001 | 0.48466 | 0.42342 | 1.160x |
| n-body | 2,000,000 | 0.10699 | 0.10628 | 0.12692 | 0.12008 | 1.122x |
| fannkuch-redux | 10 | 0.21258 | 0.16023 | 0.23360 | 0.23508 | 1.106x |
| spectral-norm | 2,000 | 0.20174 | 0.27857 | 0.88081 | 0.16262 | 0.806x |
| fasta | 2,000,000 | 0.22014 | 0.24375 | 0.39393 | 0.33420 | 1.518x |
| mandelbrot | 4,096 | 0.93320 | 0.22036 | 0.99613 | 0.64127 | 0.687x |
| reverse-complement | 10,000,000 | 0.15138 | 0.08011 | 0.38123 | 0.25524 | 1.686x |
| k-nucleotide | 1,000,000 | 0.17173 | 1.49497 | 1.80880 | 0.28249 | 1.645x |

Geometric mean of runtime ratios: **1.124x**.

## Controlled comparison and validation

A separate [15-run alternating comparison](results/2026-10-14-stage3-normalization-comparison.json)
compares the previous and rebuilt stage 3 compilers. Each invocation starts a
fresh process and includes source checking and captured xMLF output; it excludes
LLVM generation and native linking. Both compilers emit byte-identical xMLF,
which is checked again independently of source inference.

| Workload | Before (ms) | After (ms) | Frontend time reduction |
| --- | ---: | ---: | ---: |
| n-body | 428.37 | 421.73 | 1.55% |
| fasta | 364.24 | 347.44 | 4.61% |

The C ratios above use freshly measured C baselines. Changes between separate
C-comparison runs also reflect timing variation; the alternating comparison
isolates the compiler change more closely. All 36 workload sources, default
sizes, runtime stdin bytes, other tool binaries, libraries, runtime and benchmark
harness hashes match the preceding measurement. The compiler binary is the
intentionally changed input.

Validation passed:

- A fresh three-stage bootstrap, with byte-identical stage 2/3 LLVM and **7,083
  parity cases**: 3,199 accepted, 3,884 rejected, and 80 runtime cases executed
  on both backends.
- **536 rows x 2 backends in each runtime layout** (standard and compact), with
  both native drivers freshly built by the measured stage 3 compiler; 487 shared
  fixtures per layout and no missing executions.
- 636 compiler checks, 43 Figure 12 expectations, 36 supplementary checks, and
  53 benchmark-harness tests.
- The focused `GraphDense` and `SolverReuse` fixtures on both backends.
  `GraphDense` compares 624 normalization cases against the independent Haskell
  implementation, fully revalidates their results, checks the preserved fields,
  and covers sparse and arbitrary-precision identities. `SolverReuse` checks six
  malformed graph/index states and compares the optimized route with the prior
  route that explicitly validates after normalization.
- All 18 per-workload performance limits, with compiler and source hashes
  consistent across the recorded gates.

These measurements use the recorded macOS ARM64 toolchain and default workload
inputs. The compiler retains its 512 MiB initial GC heap and free-space divisor
1; maximum per-child compilation RSS was 532.9 MiB. Workload executables use the
ordinary runtime. The raw report retains short-measurement warnings, including
reverse-complement/Rust below 100 ms.

---

# Verified stage 3 release: 2026-10-14

The **stage 3 release passes every 5x C compilation / 2x C runtime limit**
across all nine workloads. The worst compilation ratio is **4.641x** (n-body);
the worst runtime ratio is **1.649x** (k-nucleotide). These are fresh five-sample
measurements from the same compiler binary that passed full stage 3 parity and
both native backend matrices.

The complete automated gate ran with:

```sh
python3 scripts/release.py build --output dist-newstyle/release-2026-10-14
python3 scripts/release.py verify --release dist-newstyle/release-2026-10-14
python3 scripts/release.py install --release dist-newstyle/release-2026-10-14 --prefix dist-newstyle/native-release-2026-10-14
```

Its benchmark step is `cabal bench compiler-bench -j1`, selecting the exact
stage 3 binary, five samples, default inputs and both per-workload limits. The
[raw report](results/2026-10-14-stage3-release-macos-arm64.json) contains all
180 fresh compilation samples and 180 runtime samples, correctness checks,
commands, source/tool/library hashes, CPU time, RSS and executable sizes.
The [release validation archive](results/2026-10-14-release-validation.json)
binds the compiler, packaged files, correctness evidence and installation checks.
The date above uses Asia/Shanghai; the report records UTC timestamps on October 13.

## Release compilation

Wall-clock medians in milliseconds. LLVM emission includes the checked source
frontend. Total compilation overlaps that phase with fresh C runtime compilation,
then compiles and links the LLVM. Every sample uses a new directory and fresh
runtime object; no source checks, target checks or measured build phases are skipped.

| Workload | C | Rust | Haskell | MLF emit LLVM | MLF total | MLF/C |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| binary-trees | 142.16 | 162.46 | 458.77 | 126.64 | 420.98 | 2.961x |
| pidigits | 146.51 | 134.81 | 455.39 | 111.30 | 423.47 | 2.890x |
| n-body | 159.79 | 146.70 | 498.81 | 512.10 | 741.63 | 4.641x |
| fannkuch-redux | 151.76 | 197.26 | 482.53 | 252.97 | 495.64 | 3.266x |
| spectral-norm | 153.42 | 161.63 | 559.06 | 239.36 | 449.38 | 2.929x |
| fasta | 158.31 | 177.72 | 504.96 | 444.92 | 720.11 | 4.549x |
| mandelbrot | 143.56 | 177.89 | 458.05 | 241.61 | 490.74 | 3.418x |
| reverse-complement | 146.28 | 157.71 | 511.04 | 282.97 | 542.15 | 3.706x |
| k-nucleotide | 166.46 | 231.02 | 1022.28 | 476.93 | 711.39 | 4.274x |

Geometric mean of compilation ratios: **3.568x**.
The internal 4.5x compilation-headroom goal remains open; the required 5x gate passes.

## Release runtime

Wall-clock medians in seconds, including startup, input, output, collection and
exit. Each language uses the same workload inputs and independent correctness
checks described in the [methodology](README.md).

| Workload | Input | C | Rust | Haskell | MLF | MLF/C |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| binary-trees | 16 | 0.34374 | 0.41040 | 0.12850 | 0.29182 | 0.849x |
| pidigits | 10,000 | 0.36761 | 0.37068 | 0.48507 | 0.42372 | 1.153x |
| n-body | 2,000,000 | 0.10791 | 0.10748 | 0.12730 | 0.12136 | 1.125x |
| fannkuch-redux | 10 | 0.21539 | 0.16267 | 0.24302 | 0.23852 | 1.107x |
| spectral-norm | 2,000 | 0.20369 | 0.28102 | 0.88251 | 0.16404 | 0.805x |
| fasta | 2,000,000 | 0.21206 | 0.24413 | 0.39570 | 0.33698 | 1.589x |
| mandelbrot | 4,096 | 0.94087 | 0.22254 | 1.00663 | 0.64016 | 0.680x |
| reverse-complement | 10,000,000 | 0.15982 | 0.08200 | 0.37505 | 0.25394 | 1.589x |
| k-nucleotide | 1,000,000 | 0.17369 | 1.54319 | 1.86811 | 0.28633 | 1.649x |

Geometric mean of runtime ratios: **1.120x**.
All nine also meet the internal 1.8x runtime-headroom goal in this run.

## Release changes and validation

The compiler shares generalization-scope reachability within each immutable
graph, uses direct integer container operations, and avoids rebuilding map paths
for minimum/maximum lookups. Both emitters inline checked state-array access
while preserving bounds failures, lazy cells, snapshots and opaque-action fallback.
The runtime uses a shared 64 KiB stdin buffer for byte/text reads. Boundary,
aliasing and failure-order regressions run through both backends.

All **36 workload source hashes**, default sizes, correctness inputs and stdin
bytes match the preceding stage 3 report. C baselines are measured afresh: ratios
across runs are not isolated optimization speedups. In particular, reverse-complement's
MLF runtime changed from 0.26675 s to 0.25394 s while C changed from 0.14231 s to
0.15982 s; both changes contribute to its lower ratio.

The release gate passed:

- All five Cabal suites: 564 compiler checks, 43 Figure 12 expressions and 36
  supplementary checks, 26 port fixtures on both backends, 53 Python harness
  tests, and the 475-row shared backend matrix.
- A fresh three-stage bootstrap with byte-identical stage 2/3 LLVM.
- **7,083 parity cases through stage 3**: 3,199 accepted, 3,884 rejected, and
  80 runtime cases executed on both backends; this includes all 60 module cases.
- **475 rows x 2 backends in each native layout**, with drivers built by stage 3
  and module CLI tests selecting stage 3. Compact generated programs use an
  8 MiB initial heap. Runtime allocation, state, ABI and emitted-force probes pass.
- All 18 compilation/runtime performance limits, with five samples per language
  and workload. Package hashes and the compiler identity remain consistent
  across every gate.
- Package smoke tests outside the checkout; a local installation moved to a
  path containing spaces still compiled and ran Snake through both backends.
  The installed driver selected the packaged stage 3 binary and runtime.

The compiler retains the 512 MiB initial GC heap and free-space divisor 1;
maximum per-child compilation RSS in this benchmark was **532.8 MiB**.
Workload executables use the ordinary runtime. The package is verified on macOS
ARM64 with the recorded toolchain and shared libraries; these results do not
certify other machines or inputs. Earlier measurements and the failed checkpoint
remain below and in their immutable reports.

---

# Native MLF bootstrap benchmarks: 2026-10-13

All **three native stages pass all nine workloads at the 5x C compilation and
2x C runtime limits**, with five samples per language and workload in each run.
Stage 2's largest compilation ratio is **4.664x** (n-body); its largest runtime
ratio is **1.886x** (reverse-complement). Stage 1's respective maxima are **4.686x** and
**1.887x**; stage 3's are **4.892x** and **1.874x**.

Stage 1 is the compiler written in MLF, built by the Haskell seed. Stage 2 is
built from the same MLF sources by stage 1, and stage 3 is built by stage 2.
All three native executables perform
parsing, inference, checked xMLF elaboration and LLVM generation themselves.
They do not invoke the seed during measured compilation. The main tables below
show stage 2; stages 1 and 3 have their own complete reports and comparison tables.

```sh
cabal bench compiler-bench -j1 --benchmark-options='--emlf dist-newstyle/bootstrap-force-complete/emlf-stage2 --runs 5 --max-compile-ratio 5 --max-runtime-ratio 2 --output benchmarks/results/2026-10-13-stage2-force-macos-arm64.json'
cabal bench compiler-bench -j1 --benchmark-options='--emlf dist-newstyle/bootstrap-force-complete/emlf-stage1 --runs 5 --max-compile-ratio 5 --max-runtime-ratio 2 --output benchmarks/results/2026-10-13-stage1-force-macos-arm64.json'
cabal bench compiler-bench -j1 --benchmark-options='--emlf dist-newstyle/bootstrap-force-complete/emlf-stage3 --runs 5 --max-compile-ratio 5 --max-runtime-ratio 2 --output benchmarks/results/2026-10-13-stage3-force-macos-arm64.json'
```

Each report ([stage 2](results/2026-10-13-stage2-force-macos-arm64.json),
[stage 1](results/2026-10-13-stage1-force-macos-arm64.json),
[stage 3](results/2026-10-13-stage3-force-macos-arm64.json)) contains **180 fresh
compilation samples and 180 runtime samples**, independent correctness checks,
exact commands, source/library/tool hashes, CPU time, peak RSS and executable
sizes. All input hashes remained unchanged, and each run passed all **18
per-workload limits**. Geometric means do not replace individual workload checks.

## Stage 2 compilation

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
| binary-trees | 143.63 | 163.43 | 444.73 | 127.61 | 409.17 | 2.849x |
| pidigits | 148.10 | 137.79 | 436.94 | 112.69 | 413.85 | 2.794x |
| n-body | 158.07 | 146.93 | 489.47 | 512.88 | 737.20 | 4.664x |
| fannkuch-redux | 153.15 | 194.40 | 464.34 | 251.53 | 485.10 | 3.168x |
| spectral-norm | 154.52 | 169.43 | 543.38 | 239.01 | 438.05 | 2.835x |
| fasta | 157.50 | 176.98 | 487.82 | 448.25 | 717.00 | 4.552x |
| mandelbrot | 142.62 | 177.21 | 444.32 | 240.77 | 475.30 | 3.333x |
| reverse-complement | 145.25 | 154.20 | 491.29 | 285.41 | 527.92 | 3.635x |
| k-nucleotide | 169.10 | 230.29 | 1002.35 | 471.67 | 695.25 | 4.112x |

Geometric mean of MLF/C compilation ratios: **3.484x**.
Median sum of nine fresh compilations: **4.906 s** for MLF and
**1.362 s** for C. Each compilation starts a fresh process.

## Stage 2 runtime

Wall-clock medians in seconds, including startup, input, output, GC and exit.
Inputs, flags and independent oracles are in the [manifest](manifest.json)
and [methodology](README.md). FASTA input generation is outside timing;
reading the resulting stdin bytes is timed.

| Workload | Input | C | Rust | Haskell | MLF | MLF/C |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| binary-trees | 16 | 0.33925 | 0.40518 | 0.12696 | 0.28903 | 0.852x |
| pidigits | 10,000 | 0.36360 | 0.36618 | 0.48308 | 0.41481 | 1.141x |
| n-body | 2,000,000 | 0.10659 | 0.10549 | 0.12651 | 0.11984 | 1.124x |
| fannkuch-redux | 10 | 0.21146 | 0.16013 | 0.23166 | 0.23069 | 1.091x |
| spectral-norm | 2,000 | 0.20122 | 0.27803 | 0.87724 | 0.16126 | 0.801x |
| fasta | 2,000,000 | 0.20993 | 0.24109 | 0.38886 | 0.33296 | 1.586x |
| mandelbrot | 4,096 | 0.93251 | 0.21977 | 0.99444 | 0.63303 | 0.679x |
| reverse-complement | 10,000,000 | 0.13926 | 0.07854 | 0.37407 | 0.26268 | 1.886x |
| k-nucleotide | 1,000,000 | 0.17087 | 1.48764 | 1.80831 | 0.28270 | 1.654x |

Geometric mean of MLF/C runtime ratios: **1.138x**.
The reports retain short-measurement warnings where startup can materially affect ratios.

## Stage 1 confirmation

This separate five-sample run uses the seed-built native MLF compiler. Its C
baselines were freshly measured in that run; no stage 2 or earlier timings are
substituted. Both limits pass for every workload.

| Workload | Compilation/C | Runtime/C |
| --- | ---: | ---: |
| binary-trees | 2.862x | 0.850x |
| pidigits | 2.812x | 1.138x |
| n-body | 4.686x | 1.122x |
| fannkuch-redux | 3.146x | 1.088x |
| spectral-norm | 2.897x | 0.805x |
| fasta | 4.636x | 1.590x |
| mandelbrot | 3.312x | 0.677x |
| reverse-complement | 3.586x | 1.887x |
| k-nucleotide | 4.167x | 1.650x |

## Stage 3 confirmation

This separate five-sample run uses the native compiler built by stage 2. Its
LLVM matches stage 2 byte for byte, and the benchmark selects the recorded
stage 3 executable explicitly. All nine workloads pass correctness checks and
both performance limits. C baselines are freshly measured in each stage's run,
so these ratios are not a direct speed comparison between compiler stages.

| Workload | Compilation/C | Runtime/C |
| --- | ---: | ---: |
| binary-trees | 2.899x | 0.838x |
| pidigits | 2.908x | 1.155x |
| n-body | 4.892x | 1.123x |
| fannkuch-redux | 3.215x | 1.084x |
| spectral-norm | 2.929x | 0.806x |
| fasta | 4.677x | 1.625x |
| mandelbrot | 3.503x | 0.680x |
| reverse-complement | 3.785x | 1.874x |
| k-nucleotide | 4.182x | 1.651x |

Geometric means are **3.597x** for compilation and **1.140x** for runtime.

## Compiler changes and resource tradeoffs

This continuation fixes the native module loader's rejection of unused missing
include directories and adds the complete prescribed module corpus to native
parity. The module CLI matrix now uses the selected native compiler and fails
if that selection is missing or does not match the coverage log.

The [first stage 2 run](results/2026-10-13-stage2-modules-macos-arm64.json)
missed n-body compilation at **5.016x C**; that failed report is retained. The
compiler now exposes the compact runtime's non-evaluating WHNF test to LLVM,
avoiding external calls for ready values and one completed indirection.
Deferred values and invalid recursive demands retain the runtime evaluator.
Independent probes check memoization, lazy fields, long spines and cycle errors.
The optimization is in both the Haskell and MLF emitters; the ordinary generated
workload layout and all type/erasure checks remain intact. Paired private probes
guided the change; the reports above are the full production validation.

Earlier general improvements include shared type translation results, dense
ST graph traversals, bounded higher-order specialization, checked small-integer
arithmetic with GMP fallback, and compact constructors with inline fields.
All **36 workload source hashes** match the
[previous native report](results/2026-10-13-stage1-final-macos-arm64.json).
Algorithms, inputs, compiler flags and per-workload limits are unchanged.

The native compiler uses a **512 MiB initial GC heap** and free-space divisor 1.
This trades memory for compilation speed; the largest observed per-child
compilation RSS across the three runs was **532.8 MiB**. RSS is the largest
child peak, not simultaneous aggregate memory. CPU time sums all compiler
children. Automatic and IO-boundary collection remain enabled, collector
settings and heap caps are honored, and workload binaries use the ordinary pool.

## Bootstrap and correctness validation

The [validation archive](results/2026-10-13-bootstrap-force-validation.json)
binds all three measured compiler hashes to a fresh three-stage bootstrap and records:

- Byte-identical stage 2/3 LLVM and **7,083 parity cases run through stage 2**:
  3,199 accepted and
  3,884 rejected, with 80 runtime rows executed on both native backends.
  This includes 21 positive module programs and 39 prescribed module rejections,
  explicit Prelude modes, and the unused missing include-directory regression.
- **468 rows x 2 backends** in each of the standard, compact, and native MLF
  driver matrices. The compact matrix uses an 8 MiB initial heap. The native
  drivers are freshly built by stage 2, and module CLI tests use that same stage 2
  executable. Each matrix audits every execution; no native fallback is allowed.
- **26 port fixtures x 2 backends**, 564 compiler checks, all 43 Figure 12
  expressions and 36 supplementary checks, and 40 harness tests including
  fault injection for compiler selection and rejection validation.
- Runtime allocation, collection, state and ABI link checks, plus emitted-force
  probes from both compilers in both layouts: 14 ready-value forms, memoization,
  20,000-link spines, recursive data and four explicit failure modes.

All three stages were freshly compiled. The stage 2/3 LLVM SHA-256 is
`47b0f9bd6051b096fb2d163f94d031d669a7de06e2de599f4d18d0089c7d0f78`.
Build and validation commands are in [bootstrap/README.md](../bootstrap/README.md).
The earlier [stage 1 archive](results/2026-10-13-stage1-validation.json) remains
historical evidence; its native module CLI checks still used the Haskell seed.

## Comparison scope

Host: macOS 26.6.2, ARM64, 10 logical CPUs; Python 3.14.8. Toolchains:
Clang 23.1.3, rustc 1.99.0, GHC 9.14.1 and GMP 6.3.0. Stage 2 was measured from
2026-10-13T14:15:01.627509+00:00 to 2026-10-13T14:21:27.465835+00:00; stage 1 from
2026-10-13T14:21:29.962760+00:00 to 2026-10-13T14:27:50.046017+00:00; stage 3 from
2026-10-13T14:37:59.042402+00:00 to 2026-10-13T14:44:23.363720+00:00.
The checkout is based on `10f1a0f` with uncommitted changes; input hashes identify
the measured sources. C uses `-O3`, Rust `-O`, GHC `-O2`, and the MLF LLVM/runtime
pipeline Clang `-O2`. All compiler/test jobs finished before benchmark timing,
and the stage runs were sequential. OS caches and thermal state are not
controlled. These are measurements on this host, not guarantees for every
machine or input.
