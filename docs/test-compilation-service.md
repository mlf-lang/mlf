# Test Compilation Service

[`Tests.TestCompilation`](../tests/Tests/TestCompilation.hs) shares successful
compilation products through the existing `Package.Build` checked artifact
store. Each selected test still executes its assertions, independent checks,
interpreter/native processes and runtime observations. The store does not retain
test passes, expected outputs or execution results.

## Opening and completing a service

Use `open repositoryRoot compiler cacheDirectory reportDirectory`, or `openWith`
with the package builder's JSON options when selecting Clang, pkg-config or a GC
prefix. Explicit options take precedence over the usual `CC`, `MLF_CLANG` and
`MLF_GC_PREFIX` defaults. Give each invocation its own report directory; compatible
invocations may share the cache directory.

`openWith` creates a real private manifest in `reportDirectory/context`. Its sole
command target describes the selected compiler's `--help` query. Ordinary
`Package.Manifest.load` and `Package.Build.create` validate this package, which
has no source modules or crate build targets. Opening a stage service therefore
does not parse the entire repository package graph. Each stage captures the
source, tool and native dependencies that it actually uses. The parent compiler
test campaign retains its whole-repository source snapshot before and after
execution.

The private package directory does not become the compilation working directory.
`workingDirectory` retains the repository root for emission, native dependency
queries and native commands. Source preparation uses the working directory
captured by source discovery. `gcFlags` uses `Package.Build.gcFlagsIn` to keep
pkg-config resolution in the real working directory. The builder's existing
creation probes continue to use their original process working directory.

An existing package build can use `fromBuilder`; that retains its original graph,
configuration and report. Driver preparation uses this route.

Always call `finish` before accepting a completed invocation. It verifies all
registered producer snapshots and the native environment, then runs the normal
builder validation and completion. A compilation report marked complete describes
compilation preparation; it is not evidence that the test assertions passed.
Unexpected failures leave the report incomplete. Requests using one service are
sequential because they share a report and command numbering. Concurrent clients
use separate report directories and the store's per-key writer locks.

## Stage APIs

All successful stage results identify an artifact directory. Use `receipt` to
record the checked-store decision, artifact checksums and this invocation's
hit/miss status. File existence alone is not an admission check.

| API | Product and contract |
| --- | --- |
| `checkedSource service includes source` | Normal source compilation followed by target-checker admission. Produces `target.xmlf`, `source.stderr` and `checked.type`. |
| `checkedSourceWith service options includes source` | The same route with explicit source options. Currently only `--no-prelude` is supported; ordered import roots belong in `includes`. |
| `registerProducer service executable` | Captures a stable producer for one invocation and registers its final verification. |
| `emittedLLVMWithIdentity service producer mode options target timeout` | Emits `program.ll` from the exact serialized target using a registered producer. |
| `emittedLLVM service executable mode options target timeout` | Captures and verifies a fresh producer identity per request; suitable for tests that deliberately replace the producer. |
| `llvmObject` / `llvmObjectResult` | Produces `program.o` using the existing package builder's LLVM-object key and options. |
| `nativeIdentity service flags` | Resolves native libraries and headers once for an invocation. Reuse with the same ordered flags avoids repeated tool queries. |
| `nativeLLVMWithIdentityResult` / `nativeLLVMResult` | Compiles LLVM and links the supplied objects with one Clang command, producing the platform's `program` executable. Trailing optimization and target options retain their original effect. |
| `cObject` | Produces `object.o`; Clang's dependency scan captures the actual source and transitive headers. |
| `linkObjects` / `linkObjectsResult` / `linkObject` | Links ordered object inputs. `linkObject` retains the existing driver's object-directory convention. |

Emission and the `Result` native APIs return either the artifact directory or
`(exitCode, stdout, stderr)`. The non-result native helpers fail the invoking
preparation command. Ordinary compiler rejection, native compilation failure and
successful emission with unexpected diagnostics are not published. Repeated
failures therefore run the producer again. Recoverable IO errors release the
store lock and remove failed action staging before the caller continues.

`checkedSource`'s checker invocation admits a serialized compilation product.
Tests that require an independent checker or oracle still run that check for
this invocation. Callers also decide when to replay the saved source diagnostics.

## Consumers

| Consumer | Shared preparation | Work that still executes |
| --- | --- | --- |
| Parity campaign | Uses the xMLF already produced by the existing batch, then shares LLVM, runtime objects and native executables. Runtime execution no longer recompiles the source through `--run` and `--emit-llvm`. | The source batch, independent checker, expected-type/rejection checks, interpreter and native observations. |
| `Tests.Backends`, including Backend, Port and PR Smoke callers | Content-identical serialized targets and native products can cross suite/output directories. | Every registered coordinate, process, input stream, trace comparison and assertion. |
| Driver preparation through `Tests.TestDrivers` | Existing package LLVM preparation plus service C objects and native links. The old helper API delegates to the service. | Driver provenance checks and each selected matrix. |
| Runtime and transport preparation | Ordinary/traced runtimes and native transport helper objects/executables. | Native helper tests and their own observations. |
| Tuple/list shell fixture | `compiler-tests prepare-fixture` shares checked source and native preparation between the interpreter and LLVM selections. The package target requires both `emlf` and `compiler-tests`. | Both backends compare their own nine results. An interpreter-only selection keeps its direct source route. |

These are compilation consumers. Pure in-process source/type assertions and
separately qualified cold-build or self-host campaigns have not been replaced by
stored test results.

## Keys and reuse boundaries

| Stage | Identity that controls reuse |
| --- | --- |
| Checked source | Producer identity; working directory; entry and ordered search roots; freshly discovered source/import closure and its bytes; source options; stage protocol. Discovery runs again so a newly introduced shadow module invalidates reuse. |
| Serialized target to LLVM | Producer bytes, exact target bytes, entry mode, ordered options, platform and stage protocol. Copied identical producers and targets may share products across output directories. |
| LLVM object | LLVM bytes and the existing builder's native toolchain, environment and ordered object options. |
| C object | Actual source inputs, Clang-resolved transitive headers, native tool/environment identity and ordered options. Trace interposition flags distinguish traced from ordinary runtime objects. |
| Native executable/link | Exact LLVM and ordered object bytes, including duplicate inputs; resolved native libraries/headers; native tool/platform/environment; ordered flags and stage protocol. Group-local object paths do not prevent reuse of identical bytes. |

The calling suite's binary, label and output directory do not identify a shared
LLVM/native product. The actual executing harness is still recorded and checked
in its own builder report. Change the service's stage protocol when the meaning
of its inputs or output contract changes. Do not replace these keys with a
checkout hash or a fixture label.

Every lookup validates the stored artifact checksums and its requested input
bytes. Large registered producer and Clang executable hashes need not be reread
for every warm row: the invocation verifies those snapshots at completion.
Every cache miss verifies the relevant tools before and after the command,
before publication. A tool changed during a warm lookup invalidates the
invocation; a tool changed during a miss cannot publish under the old identity.
Native environment checks and input/library/header checks remain on the request
path. A supplied native identity with different flags is resolved again.

Cold-build, cache-invalidation, corruption-recovery and bootstrap fixed-point
scenarios retain their explicitly chosen stores and producer identities. Select
a private empty cache when fresh compilation is the assertion. Do not route such
a scenario through a prewarmed shared store merely to shorten its run. Different
producers, entry modes, optimization flags and trace configurations remain
separate requests.

## Validation

The maintained regression is
[`Tests.TestCompilationCache`](../tests/Tests/TestCompilationCache.emlf), registered
as `harness/test-compilation-cache`. It exercises actual source, LLVM, C and native
stages, cross-directory hits, changed inputs, corruption repair, uncached failure
retries, producer/mode/option separation and live Backend observations. Its warm
Backend case deliberately supplies a wrong independent expectation and checks
that the assertion still fails.

| Check | Recorded result |
| --- | --- |
| Final GHC 9.14.1 `-O0` build | Passed: 151 shared modules, 13 executables, and exact builtin regeneration verification. |
| Ormolu / shared AST compatibility | Passed for the four changed shared-source pairs. |
| Manifest snapshot controls | 31 passed. |
| Driver-cache transfer controls | 9 passed. |
| Tuple/list qualification orchestration controls | 11 passed; these exercise the shell gate, not compiler qualification. |
| Tuple/list fixture, cold and warm | Both passed, with nine results from each backend. Warm preparation reused the checked products while executing both backends again. |
| Final GHC projection of the cache regression | Passed actual cache and `Tests.Backends` integration controls using a mechanical GHC projection of the maintained test sources. This is GHC-hosted harness evidence, not a native MLF-built harness qualification. |
| Three complete selected Parity families | Passed readability (18), state (97) and modules (60): 175 cases, 104 accepts and 71 expected rejects. All 80 runtime rows performed 160 executions with zero additional source compilations. The independent checker performed 106 checks, including the two prescribed module-cycle reference targets. |
| Native MLF-built harness | Passed: 20 build jobs, then the exact `harness/test-compilation-cache`, `harness/source-dependency-cache` and `harness/native-driver-cache` families. Each invocation selected, executed and passed one family, with complete case/family/coverage reports and unchanged inputs. The producer was the GHC `-O0` compiler; the harness itself was MLF-compiled and executed natively. |
| Paired compilation/service timings | Passed all checks in 12 of 12 trials across three serial rounds. Median warm time fell 38.14%; median cold time rose 67.63%. Workload, complete samples and boundaries are recorded below. |

Useful maintained entry points:

```sh
python3 tools/shared/build.py --bootstrap-only --optimization 0 \
  --build-dir .mlf-build/test-compilation-ghc
python3 tools/testing/test_manifest_snapshot.py
python3 tools/testing/test_driver_cache.py
python3 tools/release/test-tuple-list-qualification.py
```

Linux native harness runs use `ulimit -s unlimited`, as required by
[`native-environment.sh`](../tools/release/native-environment.sh). An initial
direct driver-cache run inherited an 8 MiB stack and crashed while checking a
builtin dependency object. The same executable, source and flags passed all
three families with fresh caches under the documented stack setting. No object
checks or exception cleanup were removed to obtain that result.

The compiler-test `select --family harness/test-compilation-cache` route runs the
registered integration regression with the selected compiler and package manager.
The [test runner documentation](../tests/README.md) describes selection and
required tool environment. For the shell fixture, run
`tools/release/test-tuple-list.sh COMPILER OUTPUT_DIRECTORY` twice with one
`MLF_TEST_COMPILATION_CACHE` and distinct output directories; both invocations
must execute their selected observations.

## Paired performance experiment

The workload is the 18 maintained readability Parity cases. The baseline uses
the original `Tests.CompilerTests` from `b2e0f70`, with only its module name
changed so it can link beside the current implementation. Both call their actual
production Parity functions, link the same final GHC `-O0` shared objects and run
the same final `emlf`. This isolates the orchestration change; it is not a
historical rebuild of the complete toolchain.

The host is a Linux 6.18.57 x86_64 container on an AMD EPYC 9V74 processor,
with nine CPUs in its affinity mask and no extra CPU pinning. The common runner
and compiler use GHC 9.14.1 `-O0`;
generated native programs use Clang 23.1.6 with the production `-O2` flags,
BDWGC 8.2.12 and GMP 6.3.0. Both variants use the same environment and the
repository's unlimited Linux stack setting.

Three rounds alternate variant order and run strictly serially, after all other
builds and correctness tests have stopped. Every trial starts a fresh process
and output directory. Cold means an empty application source-query cache and
checked artifact store, without flushing the OS page cache. Warm retains only
that variant's caches from the same round; the two variants never share a cache.

The timer includes the common runner's startup, source/candidate-check batch,
independent checker batch, source diagnostic positive/negative controls, runtime
preparation, interpreter/native execution and service completion checks. It
excludes one-time helper construction, corpus export, the outer campaign's
whole-repository inventory, experiment setup and external result validation.
Each trial also verifies the fixture bytes, expected types and stdout against
the committed corpus. These timings do not describe the complete CI pipeline.

All 12 trials completed successfully, with no failed samples or retries. Wall
times in seconds were:

| Round | Original cold | Service cold | Original warm | Service warm |
| --- | ---: | ---: | ---: | ---: |
| 1 | 55.666 | 90.463 | 41.119 | 24.752 |
| 2 | 53.639 | 90.292 | 40.972 | 25.457 |
| 3 | 53.947 | 90.432 | 41.060 | 25.399 |
| Median | 53.947 | 90.432 | 41.060 | 25.399 |
| Range | 53.639–55.666 | 90.292–90.463 | 40.972–41.119 | 24.752–25.457 |

The warm median is 38.14% lower (an original/service elapsed-time ratio of
1.62), while the cold median is 67.63% higher. This establishes a reuse
benefit and a substantial first-fill cost in this configuration. Cold requests
still emit and compile every target while also filling and validating checked
artifacts. The experiment does not attribute the cold overhead to individual
operations. It does not support a claim that one-off cold campaigns or complete
CI runs become faster.

| Work per trial | Original, cold or warm | Service, cold | Service, warm |
| --- | ---: | ---: | ---: |
| Main source batch requests | 18 | 18 | 18 |
| Additional source requests for runtime rows | 36 | 0 | 0 |
| Source requests including diagnostic controls | 57 | 21 | 21 |
| Candidate target checks | 18 | 18 | 18 |
| Independent target checks | 18 | 18 | 18 |
| Main interpreter/native observations | 36 | 36 | 36 |
| Additional diagnostic-control observations | 2 | 2 | 2 |
| LLVM emissions | 18 | 18 | 0 |
| Native compile/link commands | 18 | 18 | 0 |
| Runtime C compilations | 1 | 1 | 0 |
| Compilation-store hits / misses | No lookup | 0 / 37 | 37 / 0 |

Source-request counts follow the production call paths and retained batch/case
receipts; they are not syscall-trace counts. Service compilation counts come
from the actual checked-store decisions. The original runtime path always
emits and links each case, including in a warm source-query cache. A failed or
timed-out trial is retained as a failure and cannot contribute a speed sample.

| Work item | State | Completion condition |
| --- | --- | --- |
| Service and consumer integration | Implemented | Stage identities, failure handling and independent observations are covered by the checks above. |
| End-to-end qualification | Complete | The selected Parity families and all three native cache regressions passed. |
| Performance result | Complete | Three serial cold/warm rounds retained all semantic checks; both warm savings and cold regression are recorded above. |
