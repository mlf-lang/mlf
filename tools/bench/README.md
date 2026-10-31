# Native C/MLF benchmark comparison

The runner is written in MLF and builds with the shared package manager. It
compares a candidate compiler, a baseline compiler and C on all ten pinned
Benchmarks Game workloads. It does not run the Haskell or Rust baselines.
The regex-redux C baseline requires PCRE2, discoverable as `libpcre2-8` through
pkg-config. The MLF program imports the portable `Bootstrap.Regex` module;
its source dependencies participate in the integrity checks.

## Current shared compiler and native runner

The existing runner and positional CLI below are unchanged. Build the current
shared compiler and package manager with GHC 9.14.1 (Python 3 is used only for
this build helper), or supply an already qualified shared-native pair. The public
`tools/shared/build.py` installation supports the qualified macOS and Linux host
paths and requires Clang plus GMP/BDWGC development dependencies. Its normal
source, toolchain, and independent-generation gates still apply on either host.
A legacy release seed is not a substitute for the current shared sources.

On macOS, install Clang/LLVM, GMP, pkg-config and BDWGC; for example:

```sh
brew install llvm gmp pkg-config bdw-gc
export CLANG="$(brew --prefix llvm)/bin/clang"
export MLF_GC_PREFIX="$(brew --prefix bdw-gc)"
export PKG_CONFIG_PATH="$(brew --prefix gmp)/lib/pkgconfig:$(brew --prefix bdw-gc)/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
```

All ten workloads additionally require **PCRE2 10.49**, not an arbitrary Homebrew
version. Install that exact official release separately if necessary and prepend
its `lib/pkgconfig` directory to `PKG_CONFIG_PATH`. The runner rejects a version
mismatch rather than skipping regex-redux. Check before a long run:

```sh
pkg-config --modversion gmp bdw-gc libpcre2-8
# The final line must be 10.49.
```

On Linux, from the repository root (use absolute paths for GHC and Clang):

```sh
python3 tools/shared/build.py --ghc /absolute/path/to/ghc-9.14.1 \
  --cc "$CLANG" --optimization 2 --build-dir "$PWD/.mlf-build/shared-ghc-o2"
export MLF_PACKAGE_MANAGER="$PWD/.mlf-build/shared-ghc-o2/bin/mlfpkg"
export COMPILER="$PWD/.mlf-build/shared-ghc-o2/bin/emlf"
# The package scheduler helper is not produced by tools/shared/build.py.
"$CLANG" -O2 -std=c11 -Wall -Wextra -Werror runtime/mlf_build_runner.c \
  -o "$PWD/.mlf-build/shared-ghc-o2/bin/mlf-build-runner"
export MLF_BUILD_RUNNER="$PWD/.mlf-build/shared-ghc-o2/bin/mlf-build-runner"
"$MLF_BUILD_RUNNER" --protocol-version # must print 1
./mlfpkg --manifest tools/bench/mlf-package.json \
  --compiler "$COMPILER" --clang "$CLANG" --runtime "$PWD/runtime/mlf_runtime.c" \
  --build-dir "$PWD/.mlf-build/native-bench-driver" --timeout 21600 build --target bench
# Use a second compatible compiler for a real before/after comparison.
# Using the same compiler twice is a runnable C comparison, not an A/B speedup.
BASELINE="$COMPILER"
.mlf-build/native-bench-driver/bin/bench \
  "$COMPILER" "$BASELINE" "$PWD/.mlf-build/native-bench-results" \
  3 "$CLANG" 3 2
```

For a qualified native pair, set `MLF_PACKAGE_MANAGER`, `COMPILER` and
`MLF_BUILD_RUNNER` to that pair's tools and keep the same package-build and bench
commands. The runner itself is a compiled native MLF executable in either case;
when a GHC-hosted compiler is selected, its frontend time is included honestly.
No Rust, Haskell baseline packages or historical `cabal bench` entry are needed.

The migrated MLF workloads use current unit syntax; algorithms, C sources,
flags, inputs and independent oracles are unchanged. Regex remains the original
MLF regex library versus the official PCRE2 C implementation: this is a
cross-implementation benchmark, not a same-algorithm compiler-isolation claim.
The current compiler uses its checked, prepared builtin Prelude for eligible
standalone roots, with ordinary fallback. Imported-module roots currently retain
the ordinary pipeline; the separate prepared-library draft is not selected by
these commands. The complete ten-workload performance gate remains under repair.

## Correctness-only migration check

After building the same runner above, use a separate fresh output directory:

```sh
.mlf-build/native-bench-driver/bin/bench \
  "$COMPILER" "$BASELINE" "$PWD/.mlf-build/native-bench-checks" \
  3 "$CLANG" --check-only
```

This mode always checks all ten workloads. `3` is a required odd sample-count
placeholder for CLI compatibility; no samples are measured (`runs: 0`). Do not
append limits or workload names to `--check-only`. Each C/baseline/candidate
executable is freshly built and checked on the existing manifest correctness
inputs and pinned fixtures. It does not execute default-size performance loops.
Success is `status: "correctness-passed"`, `mode: "check-only"`,
`performance_checked: false`, with an empty `performance_checks` array. It is
not a compilation/runtime target PASS. Missing PCRE2 or any failed source,
fixture, oracle or integrity check still stops the complete ten-workload gate.

Static migration checks (no compilation or benchmark execution) are available as
`python3 tools/bench/check-migration.py`; see [validation protocol](MIGRATION-VALIDATION.md).

Run from the repository root with a fresh output directory and no other builds
or measured jobs running. An odd sample count of at least three is required.
Each measured compilation uses a new directory and runtime object. MLF source
compilation overlaps runtime compilation. LLVM compilation starts when emission
finishes; linking waits for both objects. The full boundary includes all four
stages. Both candidate and baseline emit compact-GC using the historical -gc
CLI spelling and link BDWGC. Collector flags and library/header identities are
recorded in collector.json and the integrity fingerprints. Older compilers used
as a baseline must support -gc. C uses the manifest's unchanged flags.
Historical standard-layout measurements remain historical; new compact-GC
measurements are a separate comparison series. The critical path is approximately
`max(frontend + LLVM, runtime C) + link`, plus process and scheduling overhead;
summing all four phase durations double-counts overlapping work.
Process creation, IO, collection and exit remain in runtime measurements.
Each freshly linked executable receives one untimed, output-checked invocation
at the measured input before its timed fresh process. This keeps the operating
system's one-time executable verification out of steady-state runtime ratios.

Dedicated correctness executables for all three compilers are checked against
the independent MLF oracle at all manifest check sizes. The pinned fixtures are
also checked against those oracles. Each measured executable's warm-up and timed
run use the unchanged manifest default size and compare output
against the validated C implementation. Floating-point comparisons use the
existing 1e-8 tolerance; textual integer results compare tokens; byte workloads
compare complete file hashes. DNA inputs come from the pinned C FASTA program,
which is independently checked in the FASTA workload before they are used.

`results.json` starts with a non-success status and is only completed after all
correctness, source-integrity and performance checks. Each sample retains wall
and CPU time, RSS, process status, commands and build stages, alongside the
executables and output. The report records input and tool/source hashes. Sample
order alternates to reduce ordering bias. The final two arguments set the per-workload compilation and runtime limits.
Omitting both retains the historical 5x/2x defaults. The command above explicitly
requires **3x C compilation and 2x C runtime**. Optional workload names may follow
the limits for investigation; omit them for the complete ten-workload gate.
Decisions use the unrounded ratio. Any failed limit exits nonzero. Reports retain
every sample, medians, extrema, median absolute deviation, and hashes of each
executable, LLVM module and object.

The existing native C process and binary-file transports under `tests/native/` supply
clocks, process isolation and raw bytes. Assertions and orchestration run in
MLF. The measured orchestration does not invoke Python or Cabal; GHC is only
needed to build a GHC-hosted compiler/manager when that route is selected.

## Optional native backend configuration

On Darwin ARM64, configure the generic MLF backend before measuring:

```sh
node tools/bench/configure-backend.cjs \
  /absolute/path/to/clang /absolute/path/to/opt \
  /absolute/path/to/ld64.lld "$PWD/.mlf-build/backend-config"
MLF_BENCH_MLF_CLANG="$PWD/.mlf-build/backend-config/clang-mlf" \
  .mlf-build/native-bench-driver/bin/bench \
  /path/to/candidate/emlf /path/to/baseline/emlf \
  "$PWD/.mlf-build/native-bench-results" 7 /absolute/path/to/clang 3 2
```

Configuration records the exact link job supplied by Clang and toolchain hashes
in `toolchain.json`, including reachable on-disk dynamic libraries. System
shared-cache dependencies retain their install names; the measurement context
records the OS build. Configuration does not compile a runtime or any workload.
Each measured build compiles fresh runtime C with its unchanged O2 flags, runs
the recorded LLVM optimization pipeline, generates machine code at O1, and
links fresh objects. The direct linker
uses Clang's platform, SDK and system-library arguments. Unsupported command forms
fall back to the Clang driver. Both MLF compiler variants use this backend; the C
baseline invokes the real Clang executable with the original manifest flags.
Retain the configuration and verify its toolchain hashes alongside the report.

For a paired backend investigation, set `MLF_BENCH_BASELINE_CLANG` to the
absolute baseline backend executable. The baseline lane uses that executable;
the candidate lane continues to use `MLF_BENCH_MLF_CLANG`. If unset, both lanes
use the candidate backend as before. The runner records the setting and hashes
both selected backend executables. Keep streaming and runtime-splitting settings
compatible with both backends.

Set `MLF_BENCH_SPLIT_RUNTIME=1` to compile the runtime core and process supervisor
as two fresh translation units in parallel. This option applies to both MLF
compiler variants and works with the ordinary Clang backend as well as the
streaming modes below. Each build compiles `mlf_runtime.c` with
`-DMLF_RUNTIME_EXTERNAL_PROCESS_SUPERVISOR=1` into `runtime.o` and its sibling
`mlf_process_supervisor.c` into `runtime-supervisor.o`, with the same O2 flags and
library/include arguments. Linking consumes both objects directly; all process,
async and filesystem operations remain available. No runtime object is cached.
Unset the option to retain the embedded single-object runtime build.

The external-supervisor macro is a general runtime build interface: clients that
define it must compile and link `mlf_process_supervisor.c` separately. The default
runtime includes that same implementation. The benchmark reports the two C
compilations as `runtime` and `runtime-supervisor`, including both commands,
intervals and CPU costs. The core and supervisor also overlap source compilation;
their combined CPU cost is counted even when their wall intervals overlap.
With this option there are five stages in ordinary mode, six with streaming LLVM,
and nine with a prestarted linker. The prestarted linker waits for a separate
successful-producer marker for each of the three objects. Failure or timeout
cancels the whole process group graph, including a blocked linker.

To avoid an intermediate bitcode file and a second LLVM process, build the
optional LLVM C-API helper through the native MLF package manager and builder:

```sh
./mlfpkg --manifest tools/bench/mlf-package.json \
  --compiler /path/to/native/emlf \
  --build-dir "$PWD/.mlf-build/backend-builder" --timeout 21600 \
  build --target build-backend
.mlf-build/backend-builder/bin/build-backend \
  /absolute/path/to/clang /absolute/path/to/llvm-install \
  "$PWD/tools/bench/llvm-backend.c" "$PWD/.mlf-build/llvm-backend"
node tools/bench/configure-backend.cjs \
  /absolute/path/to/clang /absolute/path/to/opt \
  /absolute/path/to/ld64.lld "$PWD/.mlf-build/backend-config" \
  --single-process "$PWD/.mlf-build/llvm-backend/mlf-llvm"
```

The helper parses and verifies input IR, runs the same recorded passes, verifies
the optimized IR, and emits an object with LLVM's O1 machine-code pipeline
using GlobalISel with instruction scheduling disabled. The lite IR pipeline
removes dead functions, runs early CSE before instruction combining, simplifies
control flow and eliminates tail recursion. It leaves helper calls out of line
to avoid forced expansion at every call site. O1 retains optimized register
allocation; O0 showed substantial runtime regressions in the compact-GC audit.
Clang supplies the target triple, CPU, tuning, features and ABI. Both the helper
and linked LLVM library are fingerprinted in `build.json`. Runtime C compilation
and linking remain separate timed stages, with fresh objects on every build.
An optional `llc` path instead of `--single-process ...` selects the two-process
`opt`/`llc` implementation for comparison. These configurations are generic and
never inspect workload names or sources.

With the single-process helper, start LLVM initialization while source checking
is still running:

```sh
MLF_BENCH_STREAM_LLVM=1 \
MLF_BENCH_MLF_CLANG="$PWD/.mlf-build/backend-config/clang-mlf" \
  .mlf-build/native-bench-driver/bin/bench \
  /path/to/candidate/emlf /path/to/baseline/emlf \
  "$PWD/.mlf-build/native-bench-results" 7 /absolute/path/to/clang 3 2
```

The timed dependency graph first creates a fresh FIFO, then starts the frontend
and LLVM helper; fresh runtime C compilation runs independently. A pipe with
`pipefail` and `cat` handles even a producer that exits before the FIFO reader
opens. The helper archives the exact received bytes as `program.ll` before
parsing, verification and optimization. Linking waits for the frontend, LLVM
helper and runtime compiler (both runtime compilers when splitting is enabled).
Setup, process startup, transport, waiting, runtime compilation, LLVM compilation
and linking all remain inside the measured boundary. Both MLF variants receive
the same treatment; the C command and runtime warm-up remain unchanged.

Streaming LLVM process time includes waiting for source emission. Use the
recorded start/finish intervals to identify the critical path: approximately
`max(frontend + LLVM tail, runtime C) + link`, with setup and scheduling overhead.
For a split runtime, use the later core/supervisor completion as `runtime C`.
Here LLVM tail is its completion time minus frontend completion. Do not add the
LLVM process's whole lifetime to the frontend time. Unset
`MLF_BENCH_STREAM_LLVM` to use the ordinary dependency graph described above.

To initialize the linker early as well, build its native helper and configure a
fresh backend directory with that helper:

```sh
./mlfpkg --manifest tools/bench/mlf-package.json \
  --compiler /path/to/native/emlf \
  --build-dir "$PWD/.mlf-build/linker-builder" --timeout 21600 \
  build --target build-linker
.mlf-build/linker-builder/bin/build-linker \
  /absolute/path/to/clang /absolute/path/to/llvm-install \
  /absolute/path/to/lld-install "$PWD/tools/bench/link-backend.cpp" \
  "$PWD/.mlf-build/linker-helper"
node tools/bench/configure-backend.cjs \
  /absolute/path/to/clang /absolute/path/to/opt \
  /absolute/path/to/ld64.lld "$PWD/.mlf-build/backend-ready-link" \
  --single-process "$PWD/.mlf-build/llvm-backend/mlf-llvm" \
  --prestart-link "$PWD/.mlf-build/linker-helper/mlf-link"
```

Use that configuration with both `MLF_BENCH_STREAM_LLVM=1` and
`MLF_BENCH_STREAM_LINK=1`. A fresh linker process loads its libraries early,
then waits for completion markers. Each marker is created by a separate stage
only after its compiler succeeds. The linker reads the complete regular
`runtime.o` and `program.o` files, plus `runtime-supervisor.o` when splitting is
enabled; every object remains available for hashing. All seven stage intervals
(nine with a split runtime) and commands, marker creation, waiting and linking
remain inside the timed boundary. Failed producers, blocked helpers, timeout and
process-group cleanup are covered by native tests. No object is reused.

The link process's elapsed time includes waiting. Its completion minus the
later object-production completion is the link tail, including readiness
notification and final linking. The critical path is approximately
`max(frontend + LLVM tail, runtime C) + link tail`, plus setup and scheduling.

The generated driver also supports the package manager's combined LLVM/link
command. Pass it as `./mlfpkg --clang /absolute/path/to/clang-mlf ... build` to
use this backend for other programs. The compiler itself is built at O2 (with
optional PGO); this latency-oriented backend is an explicit choice for compiled
programs. Flags outside the supported link form retain Clang's normal driver.

## Default executable build comparison

`native-default.py` measures the direct `emlf SOURCE -o EXE --build-dir DIR`
command, including process startup, installed-library validation, fresh user
frontend and LLVM generation, one ordinary Clang O2 object compilation and a
fresh link. Fixed library installation is excluded and its separately measured
receipt and timing are recorded. This is a distinct measurement boundary from
the fresh-runtime runner above. Every workload must use the installed standard
library path; a zero native-export count is allowed and recorded. The report
separately records fixed runtime reuse, native library export reuse and checked
builtin unfolding; these are distinct mechanisms.

Supply a prebuilt independent oracle executable that implements
`ORACLE WORKLOAD SIZE OUTPUT` by calling `Package.Benchmark.validateOutput`;
`Oracle.hs` is a thin GHC-hosted adapter. Supply a complete check-only result
directory from the existing runner for fixture evidence and its checked input
files. Supply a baseline directory containing a `results.json` correctness
report with compiler fingerprints and one independently checked executable at
`WORKLOAD/program` per canonical workload. Run from the repository root, with
fresh output and no other measured work:

```sh
python3 tools/bench/native-default.py \
  --compiler /absolute/path/to/emlf \
  --install-receipt /absolute/path/to/native/receipt.json \
  --install-timing /absolute/path/to/install-timing.json \
  --oracle /absolute/path/to/independent-oracle \
  --baseline-dir /absolute/path/to/checked-baseline \
  --check-dir /absolute/path/to/check-only-results \
  --clang /absolute/path/to/clang \
  --output "$PWD/.mlf-build/default-native-comparison"
```

Each workload has an excluded warmup and five fresh paired candidate/C builds,
plus candidate/C/baseline runtime processes. The report retains exact commands,
receipts, correctness cases, medians, reuse counts and input identities. Its
`complete` status means collection and correctness succeeded; evaluate ratios
against the desired limits separately. Do not describe it as the ten-workload
fresh-runtime gate.
