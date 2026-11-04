# Experimental IR8: real bodies and native runtime

Stage05 adds an opt-in C body emitter and a real runtime for checked raw IR8.
Generated callbacks are compiled and linked with the production implementation,
then run by a small test driver. There are no dummy callbacks or v7 fallback.
This is separate from the maintained source frontend and default runtime.

## What is implemented

- `resource_ir_v8.runtime_emit.emit_runtime(raw)` and `loads_runtime(text)` return
  an immutable `RuntimeEmission`. They freshly check raw input, emit the packet
  and runtime header/source pairs, and return correspondence/budget manifests.
  Each Code row has one real generated body, including retained dead definitions.
  Emission itself does not compile or execute anything.
- `runtime_v8/rir8_binding.c` checks the packet/body binding. The real helpers,
  typed guards, allocation/ownership operations, forcing and sessions live in
  `rir8_guard.c`, `rir8_memory.c`, `rir8_runtime.c`, `rir8_force.c` and
  `rir8_session.c`. Together with `packet_v8/ir8_packet.c`, these are the seven
  common production C translation units used by the native tests.
- `runtime_v8/rir8_session.h` exposes diagnostic sessions, ordinary runs,
  repeated runs and explicit terminal destruction. Failure does not imply
  rollback or automatic terminal-heap cleanup. Immutable program roots must
  outlive a session; expected-binding and workspace storage must satisfy the
  documented lifetime and non-overlap requirements.

Some preserved source comments say "source preparation", "not compiled" or
"unresolved" because they describe the earlier stage in which those files were
written. The runtime is now implemented and has finite compiled tests. The
emitter's `emitted-uncompiled-runtime-source` status remains correct for each
emission: producing source is not evidence that that artifact was compiled or
run. Packet-only metadata status is likewise not rewritten by a later test.

## Host-only tests

Use POSIX and unoptimized Python 3.12. No third-party Python packages are needed.
The existing declaration/resource/metadata/packet runner is unchanged:

```sh
python3 -B -S tools/experimental/resource-native/tests/run_ir8_host.py \
  --output /tmp/ir8-host-fresh
```

That runner has 475 tests. The separate Stage05 emitter suite has 128 tests,
including source correspondence, rejection/mutation cases and budget controls.
It makes 67 public emission attempts, retains 33 successful emission sets, and
does not invoke a compiler or native code. Run it directly from the repository
root with its required clean environment:

```sh
repo=$(pwd -P)
python=$(command -v python3)
work=$(mktemp -d /tmp/ir8-stage05-host.XXXXXX)
mkdir -m 700 "$work/home" "$work/tmp"
timeout --signal=TERM --kill-after=5s 180s env -i \
  PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
  PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 \
  HOME="$work/home" TMPDIR="$work/tmp" \
  "$python" -B -S \
  "$repo/tools/experimental/resource-native/tests/test_stage05_runtime_emit.py" \
  --evidence-root "$work/results"
```

The script and evidence paths must be absolute, without symlink components.
The results directory must not exist and must be outside the checkout; HOME
and TMPDIR are separate external support directories. A successful run retains
168 files, including `HOST_RESULTS.json`, `ATTEMPTS.jsonl` and generated source
sets. Require exit zero as well as the test result: a late persistence failure
must not be counted as a pass. An ordinary timeout is sufficient; the historical
custom supervisor is not a prerequisite for this repository command.

## Native tests

Use Linux/POSIX, Python 3.12 or newer and an ordinary C11 compiler, such as GCC. The test
script generates C through the public emitter from repository-contained raw
cases, then compiles, links and runs the real production code. It does not need
an archived workspace, object manifest or historical output directory.

```sh
python3 -B tools/experimental/resource-native/tests/test_stage05_runtime_native.py \
  --output /tmp/ir8-stage05-native-fresh
```

Use a new output directory for every attempt. Select a compiler with `CC` or
`--cc`; the default is `cc`. Select `--optimization O0` (the default) or
`--optimization O2` explicitly. The ordinary run builds eleven programs and runs
sixteen tests. `--stress` adds six one-run/100-run comparisons, for twenty-two
tests. The seven common translation units are compiled once, then each generated
packet/runtime pair is linked with them: eighteen compiler invocations in total.
Optional repeat and sanitizer checks are explicit:

```sh
CC=gcc python3 -B tools/experimental/resource-native/tests/test_stage05_runtime_native.py \
  --output /tmp/ir8-stage05-native-stress --stress
CC=gcc python3 -B tools/experimental/resource-native/tests/test_stage05_runtime_native.py \
  --output /tmp/ir8-stage05-native-o2 --optimization O2
CC=gcc python3 -B tools/experimental/resource-native/tests/test_stage05_runtime_native.py \
  --output /tmp/ir8-stage05-native-sanitize --sanitize
```

`--sanitize` enables ASan and UBSan for the same selected tests and omits the
native address-space limit so ASan can reserve its shadow memory. The ordinary
subprocess time and output limits still apply. It honors `ASAN_OPTIONS` and
`UBSAN_OPTIONS`; leak detection is not disabled by default. If LeakSanitizer is
unsupported under ptrace, use a separate, explicitly qualified run:

```sh
ASAN_OPTIONS=detect_leaks=0:abort_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
python3 -B tools/experimental/resource-native/tests/test_stage05_runtime_native.py \
  --output /tmp/ir8-stage05-native-sanitize-no-lsan --sanitize
```

That command does not test leaks. Do not describe it as a LeakSanitizer pass.

Evidence includes generated source and binaries under `build/`, compiler logs
under `compilation/`, per-run commands/results under `runs/`, and `summary.json`.
Keep compile logs, run output and result summaries when a command fails. A
timeout or sanitizer startup failure is not a semantic rejection. The workflow
adds separate emitter-host and O0/O2 native-runtime jobs; the existing host job and
its artifacts remain separate. Running these tests does not enable IR8 in any
default command or source exporter.

## Observed scope and remaining work

The local finite runtime qualification compiled and linked eleven genuine
programs and passed sixteen semantic checks plus six one-run/100-run comparisons.
D1–D8 passed AddressSanitizer/UndefinedBehaviorSanitizer with LeakSanitizer
disabled because leak checking was unsupported under the local ptrace setup.
That is not a LeakSanitizer pass. D1–D8 also produced identical parsed reports at
O0 and O2; this checks optimizer-sensitive correctness, not performance.

These results exercise real callbacks, ownership and forcing, expected fault
paths, repeated execution and terminal retirement. They are a finite regression
set, not a proof of all programs or capacities. In particular:

- There is no current-target source proof/lowering bridge for shared terms used
  at different closed types. Raw IR8 success does not establish ordinary source
  checking, erasure correspondence, imported-library support or full MLF coverage.
- The runtime carries lexical Env and actual Access through values, loans,
  instantiation and forcing. Passing scalar results and aggregate reports does
  not independently observe every Env/Access/Transport identity or transition.
  Direct observation and adversarial correspondence coverage remain incomplete.
- All 27 guard families still need comprehensive independent positive/negative
  coverage. A checked-mask bit, one expected fault or an executed branch is not
  that complete guard qualification.
- Callable-valued SUM storage remains outside the admitted domain. Callable
  DATA and external callable factories do not remove that restriction.
- Whole-runtime/model equivalence, maximal storage/stack bounds, general cycle
  reclamation, complete tracing-GC replacement and measured speedup remain
  unproven. Repeat-count comparisons are not performance benchmarks.

The v7 allocator, terminal policy, source route and default entrypoints remain
unchanged. See [README_STAGE04.md](README_STAGE04.md) for the earlier static and
packet-only layer boundaries.
