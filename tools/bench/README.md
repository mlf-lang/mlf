# Native C/MLF benchmark comparison

The runner is written in MLF and builds with the native package manager. It
compares a candidate compiler, a baseline compiler and C on all nine pinned
Benchmarks Game workloads. It does not run the Haskell or Rust baselines.

```sh
export MLF_GC_PREFIX=/path/to/bdwgc-install
./mlfpkg --manifest tools/bench/mlf-package.json \
  --compiler /path/to/native/emlf --runtime "$PWD/runtime/mlf_runtime.c" \
  --build-dir "$PWD/.mlf-build/native-bench-driver" --timeout 21600 build --target bench
.mlf-build/native-bench-driver/bin/bench \
  /path/to/candidate/emlf /path/to/baseline/emlf \
  "$PWD/.mlf-build/native-bench-results" 7 /absolute/path/to/clang 3 2
```

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
the limits for investigation; omit them for the complete nine-workload gate.
Decisions use the unrounded ratio. Any failed limit exits nonzero. Reports retain
every sample, medians, extrema, median absolute deviation, and hashes of each
executable, LLVM module and object.

The existing native C process and binary-file transports under `tests/native/` supply
clocks, process isolation and raw bytes. Assertions and orchestration run in
MLF. GHC, Python and Cabal are not used.

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
parsing, verification and optimization. Linking waits for all three producers.
Setup, process startup, transport, waiting, runtime compilation, LLVM compilation
and linking all remain inside the measured boundary. Both MLF variants receive
the same treatment; the C command and runtime warm-up remain unchanged.

Streaming LLVM process time includes waiting for source emission. Use the
recorded start/finish intervals to identify the critical path: approximately
`max(frontend + LLVM tail, runtime C) + link`, with setup and scheduling overhead.
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
`runtime.o` and `program.o` files, which remain available for hashing. All
seven stage intervals and commands, marker creation, waiting and linking remain
inside the timed boundary. Failed producers, blocked helpers, timeout and
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
