# Backends, Port, and native runtime handoff

The comparison baseline is `720dd649627fbf8b19c7447493a4fdf6fd05eb39`.
This implementation is unverified. The commands below are for Phase 2.

## 5. Backends

The 50 reviewed families still partition the 541 legacy fixture actions. The
541 IDs consist of the existing family ID, a slash, and the original action
label with each character other than ASCII alphanumerics, hyphen, or dot
escaped as `_DECIMAL_`. The case name remains the exact original label.
The 593 expected matrix rows keep their reviewed fixture labels, original
execution order, and interpreter/LLVM pairing. The compatibility row format
remains `{label,index,backends}`. Each new backend observation identifies its
case, coordinate within that case, backend, checked target digest, supervisor
status, ordered IO events, remaining input, and diagnostic. The adjacent raw
stdout, stderr, trace, and supervisor files retain byte and process evidence.
The original literal or independent assertions still decide the result.

The default, `--families`, and `--from` paths now use one registry, and
`--list`, `--exact`, `--format`, and `--report` use the common runner.
The parent maintains its family and matrix receipts alongside the case
report. Routine CI supplies the GHC-hosted -O0 compiler and manager, and the
C build runner is built explicitly. The campaign builds the traced runtime
interpreter and the LLVM driver from source using that producer. These
driver binaries retain the test-only stdio interposition required for raw
byte traces. The native release campaign retains the self-built producer.

Within one matrix, identical serialized target, entry mode, and emitter
identity share successful LLVM emission. The previously existing native
binary reuse by LLVM digest remains. Each backend still gets its own process,
arguments, input, and trace. Expected savings are one emitter launch for
each repeat beyond the first matching target and mode. No baseline call
count was executed. Count first emissions versus `*.llvm-source` reuse
markers and compare Clang links, child executions and the wall time of
preparation/emission/links separately. Log-ready coordinates have independent
results even when a recoverable error prevents the legacy row from completing.

With GHC 9.14.1, Clang, GMP and BDWGC on the path, run the following on
the candidate. Give the baseline separate absolute work/cache directories,
using the same candidate-independent environment and the legacy native
qualification producer recorded by that revision.

```sh
python3 -B tools/shared/build.py --bootstrap-only --optimization 0 --build-dir .mlf-build/phase2/host
phase2_tools="$PWD/.mlf-build/phase2/host/bin"
clang -O2 -std=c11 -Wall -Wextra -Werror runtime/mlf_build_runner.c -o "$phase2_tools/mlf-build-runner"
export MLF_BUILD_RUNNER="$phase2_tools/mlf-build-runner"
"$phase2_tools/compiler-tests" select --family backends/strict-wrappers --manager "$phase2_tools/mlfpkg" --compiler "$phase2_tools/emlf" --build-dir "$PWD/.mlf-build/phase2/backend-focused" --cache-dir "$PWD/.mlf-build/phase2/cache"
"$phase2_tools/compiler-tests" backends --manager "$phase2_tools/mlfpkg" --compiler "$phase2_tools/emlf" --build-dir "$PWD/.mlf-build/phase2/backends" --cache-dir "$PWD/.mlf-build/phase2/cache"
```

Run discovery and exact selection with the built suite and the already
prepared matrix runtime. Use a fresh campaign directory for comparisons
because rerunning the child in the campaign directory replaces matrix files.

```sh
matrix="$PWD/.mlf-build/phase2/backends"
suite="$matrix/suite-build/bin/backends"
"$suite" --list --format json
env MLF_TEST_WORK="$matrix" MLF_TEST_ROOT="$matrix" MLF_TEST_HOST_SUPPORT="$matrix/host-support" MLF_TEST_BINARY_FILES="$matrix/binary-files" MLF_TEST_LINK_FLAGS_FILE="$matrix/link-flags.bin" MLF_BOOTSTRAP_INTERPRETER="$matrix/RuntimeDriver" MLF_BOOTSTRAP_LLVM="$matrix/LLVMDriver" MLF_BOOTSTRAP_COMPILER="$phase2_tools/emlf" "$suite" --exact backends/strict-wrappers/strict_32_unary_32_representation_58__32_evaluated_32_recursive_32_producer --format json --report .mlf-build/phase2/backend-exact.jsonl
```

In a disposable Phase 2 checkout, change one strict-wrapper literal output
and rerun the exact command. Both backend observations should remain
available and the common case should fail. Repeat with a deliberately
failing LLVM driver selected through `MLF_BOOTSTRAP_LLVM`. Confirm that
trace/status data still identifies which backend observed the result.
Normal failure, timeout, crash, and diagnostic matching on the hosted path
still need execution, including the recovery boundary for ordinary assertions.

## 6. Port

The existing 25 family IDs `port/<fixture>` are also case IDs. The six
independent reference invocations retain their own executable, expected
bytes, and output/status. The inference generator comparison and the Figure 12
A8 target remain. The prepared target checker still verifies independent
type, compiler inference, serialization erasure and transported type. Each
fixture still runs natively. Four preparation shards and the cache identity
from the original producer remain unchanged. A single authenticated manifest
snapshot now supplies all selected cases. Each checked target and receipt is
still validated, and the manifest digest is checked again after the run.

The default and the compatibility `--families`, `--only`, `--list`,
`--list-families`, and `--prepare` paths remain available. The common inventory
is `--list --format json`. Exact IDs can run against the matching focused
prepared manifest or a full prepared manifest. The independent reference
files now use fixture-specific paths. A full suite avoids 24 duplicate
manifest reads/parses and 23 repeated manifest hash calls inside the suite.
Large preparation/link/runtime costs remain and need to be measured separately.
Preparation-only jobs still import/export genuine cache artifacts.

Use authenticated native release tools `MLF_COMPILER`, `MLF_PACKAGE_MANAGER`,
`MLF_BUILD_RUNNER`, `MLF_GC_PREFIX` where needed, and an absolute
`NATIVE_TEST_RUNNER` path.

```sh
export MLF_BUILD_RUNNER
"$NATIVE_TEST_RUNNER" select --family port/InferenceConformance --manager "$MLF_PACKAGE_MANAGER" --compiler "$MLF_COMPILER" --build-dir "$PWD/.mlf-build/phase2/port-focused" --cache-dir "$PWD/.mlf-build/phase2/port-cache"
for pass in cold warm; do
  "$NATIVE_TEST_RUNNER" port --manager "$MLF_PACKAGE_MANAGER" --compiler "$MLF_COMPILER" --build-dir "$PWD/.mlf-build/phase2/port-$pass" --cache-dir "$PWD/.mlf-build/phase2/port-cache-$USER"
done
port="$PWD/.mlf-build/phase2/port-cold"
"$port/suite-build/bin/port" --list --format json
targets="$port/prepared-port.json"
target_sha=$(shasum -a 256 "$targets" | awk '{print $1}')
env MLF_TEST_WORK="$port" MLF_TEST_ROOT="$port" MLF_TEST_HOST_SUPPORT="$port/host-support" MLF_TEST_BINARY_FILES="$port/binary-files" MLF_TEST_LINK_FLAGS_FILE="$port/link-flags.bin" MLF_BOOTSTRAP_LLVM="$port/LLVMDriver" MLF_TEST_REFERENCES="$port/suite-build/bin/references" MLF_TEST_PORT_TARGETS="$targets" MLF_TEST_PORT_TARGETS_SHA256="$target_sha" "$port/suite-build/bin/port" --exact port/InferenceConformance --format json --report .mlf-build/phase2/port-exact.jsonl
```

Use an empty cache for the first pass and the same cache for the second.
Compare build-report cache keys, checker artifacts, reference launches and
matrix observations against the pinned checkout. Repeat after changing one
input in a disposable checkout and confirm invalidation. The macOS
`profile-port.yml` profiling matrix still independently measures SolverReuse
and InferenceConformance at collector divisors 1, 2 and 4.

## 13. Native runtime and async

The shell and C adapters use existing assertions and publish common
framework reports through `tools/testing/backend-native-suites.json`.

| Baseline coverage | Registered adapter and result boundary |
| --- | --- |
| Tuple/list sugar source and nine output lines per backend | `tuple-list-native/interpreter` and `tuple-list-native/llvm`. Both compare the original literal oracle. One checked source compilation supplies both executions. |
| POSIX native build runner and process supervision | `native-build-tools`. The 22 build-runner and 31 supervised scenarios have individual IDs; the original scheduling, exit/status, Job Object or process-group, descendant, and plan/result checks remain. |
| Native typed completion | `native-async-runtime`. Six independent C representation scenarios and the single ordered primitive driver retain callback and assertion counts. One runtime object supplies both binaries. |
| Typed completion language parity | `async-completion`. Six runtime fixtures retain source-interpreter, target-interpreter and LLVM comparisons. Nine source rejections and seven target negatives across three entry points retain precise phase checks. The capability gate has its own ID. The manual `async-completion-full` profile also keeps the native C runs. Ordinary CI runs those C cases only in the native job. |
| Legacy representation gate | `async-gate`. Four positive, ten negative, two interpreter and one compile-only case. The compile-accepted incorrect-quantifier example remains compile/check only. |
| Async.Process and Async.Task | `async-process` and `async-task`. IDs retain the source rejections plus each named literal result on each backend (13 Process and 31 Task results per backend). Full runs remain batched and exact selection executes the indicated leaf. Normal process, panic-and-join, scheduler, wait graph and guard runs retain separate processes/directories and the existing independent output/status records. |
| Async checked packages | `async-package`. The fresh/cached pair is one relational case; seven separately selectable failures use the genuine cached interface. Fresh roots, package receipts and negative diagnostics are retained. |
| Native Windows runtime | `windows-runtime` combines the C inventories and the three POSIX-independent Windows scenarios for reproducible C/LLVM bytes, path guards and compact-GC runtime. Release uses that adapter with the already-qualified filesystem helper. |
| Windows pre-fix long-path control | `windows-long-path` selects the one meaningful regression scenario against the pinned pre-fix binary. It still requires launch failure 126, PID 0 and a complete typed result. |
| GHC async preparation controls | `python-shared-prepare-async-ghc` keeps the individual unittest methods in both Python optimization modes. The hosted producer now defaults to GHC -O0 and records its optimization in the receipt. Native C harness compiler flags remain unchanged. |

The exact controls retain real subprocesses, signals, watchdog and fresh
directory behavior. Both POSIX and Windows adapters support exact selection of native C
scenarios and their platform profiles. Supplementary C ABI probes
already dispatched by Harness and the direct hosted controls keep their
separate owners and checks.

Expected savings are one source compilation on full tuple/list, one C runtime
compilation in the native-async POSIX job, removal of the pair of repeated C
jobs from the async-language script on each host, and up to 21 unnecessary
scenario starts on the Windows negative control. Count builds and process
launches before and after; compare startup and cleanup separately. Windows
byte reproducibility keeps the two independent builds and time separation.

```sh
python3 -B tools/shared/prepare_async_ghc.py --build-dir .mlf-build/phase2/async-ghc --optimization 0 --clang clang
async_tools="$PWD/.mlf-build/phase2/async-ghc/bin"
python3 -B tools/testing/run.py tuple-list-native -- "$async_tools/emlf" .mlf-build/phase2/tuple-list-native
python3 -B tools/testing/run.py tuple-list-native --exact tuple-list-native/llvm -- "$async_tools/emlf" .mlf-build/phase2/tuple-list-native-focused
python3 -B tools/testing/run.py native-build-tools -- .mlf-build/phase2/native-build-tools
python3 -B tools/testing/run.py native-build-tools --exact native-process-supervisor/cancel-running-tree -- .mlf-build/phase2/process-cancel
python3 -B tools/testing/run.py native-async-runtime -- .mlf-build/phase2/native-async-runtime
EMLF="$async_tools/emlf" MLF_ASYNC_COMPLETION_BUILD_DIR=.mlf-build/phase2/async-completion python3 -B tools/testing/run.py async-completion
EMLF="$async_tools/emlf" MLF_ASYNC_COMPLETION_BUILD_DIR=.mlf-build/phase2/async-completion-full python3 -B tools/testing/run.py async-completion-full
EMLF="$async_tools/emlf" python3 -B tools/testing/run.py async-gate
python3 -B tools/testing/run.py async-process -- "$async_tools/emlf" .mlf-build/phase2/async-process
python3 -B tools/testing/run.py async-process --exact async-process/panic-cleanup/llvm -- "$async_tools/emlf" .mlf-build/phase2/async-panic
python3 -B tools/testing/run.py async-task -- "$async_tools/emlf" .mlf-build/phase2/async-task
python3 -B tools/testing/run.py async-package -- "$async_tools/emlf" "$async_tools/mlfpkg" .mlf-build/phase2/async-package
python3 -B tools/testing/run.py python-shared-prepare-async-ghc
python3 -B tools/testing/run.py python-shared-prepare-async-ghc --python-optimization
tools/release/qualify-tuple-list.sh
```

Also run the Windows paths from PowerShell after provisioning the same pinned
Windows native tools as CI.

```powershell
python -B tools/testing/run.py windows-runtime -- -NativePrefix $env:MLF_NATIVE_PREFIX -Clang $env:MLF_CLANG -Output .mlf-build/phase2/windows-runtime
python -B tools/testing/run.py windows-runtime --exact native-process-supervisor/cancel-running-tree -- -NativePrefix $env:MLF_NATIVE_PREFIX -Clang $env:MLF_CLANG -Output .mlf-build/phase2/windows-cancel
python -B tools/testing/run.py windows-long-path -- -Clang $env:MLF_CLANG -Output .mlf-build/phase2/windows-runtime
```

Use `run.py SUITE --list` to compare the registered scopes. Run both native
POSIX architectures and the Windows release rehearsal. Deliberately interrupt
a supervised run and check the started and missing IDs, preserved exit status
and process tree. Also compare timeout and panic results with and without a
wrong oracle using disposable copies. GHC -O0 exact output, target rejections,
Windows event-file encoding, and the isolated 126/PID 0 negative control
still need execution.

## Exact selection for retained native receipts

A follow-up keeps the same producer and literal oracles while allowing the
common runner to enumerate and select retained native receipt cases before
producing any build output. The gate-specific receipts still contain their
original native-case and raw command data.

| Adapter | Coverage and focused dispatch |
| --- | --- |
| `native-library` | The original 34 runtime outcomes retain the same labels and native O0/O2 variants. Six named host checks are also selectable. A focused runtime case builds only its selected emitter, library or root, and native optimization lane. A focused host case compiles its fixture and any required header adapters. |
| `installed-native-library` | The same 40 cases plus the installed frontend contract. A full run still uses the copied source snapshot and requires its installed frontend source root. |
| `io-action-sharing` | The original 18 source labels and 19 optimizer-shape assertions. Exact source selection still checks original, serialized and optimized-erased forms, plus native execution when a GC prefix is supplied. Exact shape selection has no native link. |
| `artifact-binary-native` | All 142 original command labels. Exact selection runs only the producing backend and authenticates required setup. Genuine cold-state, Session seed, pack, unpack or legacy-pair dependencies are retained and reported separately. The full path still checks the other backend byte-for-byte and runs the independent reference corpus. |

For Phase 2, use fresh output directories and the existing configured GHC
producer, private native library install, and BDWGC prefix. The artifact
binary command is Linux-only and keeps the existing outer resource guard and
literal failure sink.

```sh
for suite in native-library installed-native-library io-action-sharing artifact-binary-native; do
  python3 -B tools/testing/run.py "$suite" --list
done
python3 -B tools/testing/run.py native-library --exact native-library/poison7-O2-demand-fails -- --build-receipt .mlf-build/shared-ghc/receipt.json --gc-prefix .mlf-build/io-action-gc --output .mlf-build/phase2/native-poison-demand
python3 -B tools/testing/run.py installed-native-library --exact installed-native-library/installed-frontend-controls -- --build-receipt .mlf-build/stdlib-default/receipt.json --gc-prefix .mlf-build/io-action-gc --frontend-source-root .mlf-build/stdlib-default/sources/libraries/mlf-foundation --output .mlf-build/phase2/installed-frontend
python3 -B tools/testing/run.py io-action-sharing --exact io-action-sharing/bare-do-loop -- --build-receipt .mlf-build/shared-ghc/receipt.json --gc-prefix .mlf-build/io-action-gc --output .mlf-build/phase2/io-bare-do
python3 -B tools/shared/resource_watchdog.py --seconds 1800 --address-space-mib 6144 --rss-mib 5120 --max-output-mib 640 --disk-free-mib 4096 .mlf-build/phase2/artifact-exact-guard python3 -B tools/testing/run.py --inherit-process-group artifact-binary-native --exact artifact-binary-native/shared-native-public-pair -- --source-root "$PWD" --build-receipt .mlf-build/shared-ghc/receipt.json --clang clang --gc-prefix "$PWD/.mlf-build/io-action-gc" --partial-write-sink /dev/full --output .mlf-build/phase2/artifact-exact-guard/results
```

Compare full commands and specialized receipts with the pinned revision.
For focused runs, count emitter calls, fixture links and child processes.
Direct hosted artifact cases should avoid the fresh native crate closure;
a native case still compiles that closure cold. Repeat one warm cache or
publication selection and verify its cold seed occurs with the original
oracle and carries no separate test credit. Verify that the copied
installation contains the common selection helper and that the borrowing
batch-replacement fixture still compiles under its existing module adapter.
