# Native MLF compiler tests

The root `tuple-list` test target checks tuple/list sugar through the checkout
frontend: fixed ASTs and types, malformed syntax, current and frozen target
checking, serialized-target round trips, module scope and lazy interpretation.
Run `./mlfpkg --timeout 21600 test --target tuple-list` with the configured
native input tools. It also runs as part of the ordinary root `mlfpkg test`.
Its harness deliberately uses the previously released source syntax so a seed
compiler can build it while its string fixtures exercise the new parser.
It is separate from the existing Core inventory and does not change the six
full compiler qualification campaigns. These focused checks do not establish
LLVM execution parity or a self-hosting fixed point.
The POSIX root `tuple-list-native` target builds the checkout compiler and runs
the actual interpreter/native fixture. Run
`./mlfpkg --timeout 21600 test --target tuple-list-native`, or use an already
built compiler with `bash tools/release/test-tuple-list.sh /absolute/path/to/emlf`. With
Clang, GMP and BDWGC configured, it checks nine independently specified output
lines on both paths, including recursion, tuple arities, do patterns and lazy
fields. Its source and expected output are `fixtures/tuple-list-runtime.*`;
logs and generated LLVM default to `.mlf-build/tuple-list-runtime/`.

Pull requests require the small [compiler source smoke suite](../docs/ci.md):
the verified seed interprets `PRQuickMain.emlf` against the checkout frontend and
current/frozen target checkers through the split library roots, with two accepted
cases, two source rejections
and one malformed target. This does not build fresh tools or test current LLVM
execution. Fresh native tools, eight CLI cases, three package/cache states and
the complete 79-case package distribution suite, separate target-dependency/
scheduler fixture and 22 native runner checks run separately on pushes to
`main` or manual CI dispatches with `full_validation` enabled.

The broader campaign remains available as `tools/release/native-ci.sh extended-pr-smoke`:
framework/process contracts, Figure 12, four independent checker controls,
12 interpreter/LLVM fixtures and package/cache checks. The six full root groups
below retain their existing coverage.

The local `mlf-tests` package preserves the original assertions, input corpora,
runtime event traces, generated graph properties, and harness fault injections.
Root `mlfpkg test` builds these executables through the MLF package manager.
The test-owned `compiler-tests` runner is a private root executable; its sources
live in `tests/CompilerTestsMain.emlf` and `Tests/CompilerTests.emlf`. It receives
the real package manager through `--manager`, keeps the existing six root groups
and report paths, and fingerprints the manager and runner separately.
The old Haskell/Python suites and Haskell compiler have been removed.
No GHC, Cabal, or Python executable is needed. C fixtures live in `tests/native/`;
benchmark baselines and golden oracle data remain unchanged.

The reusable [`mlf-test` library](../testing/README.md) provides `Test.Case`,
`Test.Assert` and `Test.Runner`. `int-set-unions` is the first focused runner
target; its existing Core entry still runs the same sorted-list oracle and all
276 distinct inputs. `test-framework` checks failure continuation, selection,
inventory validation, JSON diagnostics and legacy adapters. The root `unit`
group runs both the library and CLI contract checks in addition to the current
684 Core checks. The separately reviewed duplicate consolidation below accounts
for the reduction from the original 686 checks.

The shared test library contains eleven modules: the eight original helper,
transport, collection-wrapper and independent-checker modules, `Tests.Coverage`,
`Tests.TestDrivers` and `Tests.TestSources`. The private root campaign explicitly
maps the last three support modules alongside `Tests.CompilerTests`.
Each executable explicitly lists the private test modules imported by its
entry point. The original modules and added framework and regex checks remain reachable
across those entries. Building `port` and its six reference programs now compiles
21 test modules including their two entries, instead of pulling unrelated test
modules into those targets.
`mlfpkg --manifest tests/mlf-package.json plan` checks those import boundaries;
adding a test module also requires adding it to each importing target's
`modules` map, or to the shared library when it is common support.

Root builds and nested test builds share a checked artifact store through
`{cache}` and `--cache-dir`. Each test group keeps its own `suite-build` report
and logs. Source/tool identities, artifact checksums and recursive dependency
receipts still control reuse; a fresh self-host stage keeps a new store.
Prepared port targets and source driver LLVM now use the compiler module loader's
current import closure, including ordered search roots and newly introduced
module shadows. Unrelated example, benchmark and test files remain in the full
verification snapshot without invalidating these artifacts. Port targets retain
their independent checking and serialization receipts.
Driver LLVM objects, native links, runtime objects and trace objects also share
checked artifacts. Their keys include actual native inputs, resolved C headers,
library bytes, compiler/environment identities and ordered flags. Group reports
identify each reused artifact and its checksums. The two new cache regressions
exercise source resolution, cross-group reuse, invalidation, corruption repair
and traced runtime behavior with small programs; every selected matrix still runs.
Self-host selects the candidate artifact from its actual package build report,
checks that report's source snapshot and retains a copy. Equal native binary
hashes elsewhere in the shared store do not identify the producing LLVM input.
The backend group's two test drivers preserve the source frontend's verified LLVM; crate linking
regressed RuntimeDriver's interpreter performance. Their LLVM artifacts are
shared by actual source/tool identity, and each test group retains its own
traced runtime linking. Port prepares only LLVMDriver; it does not build or launch
an outer RuntimeDriver. Focused interpreter coverage remains in backends, parity,
package integration and the LLVM-compiled RuntimeCases/StateRuntime probes.

Port preparation compiles each of the 25 fixtures once per source/tool identity.
It checks the inferred target with the independent checker, checks its serialized
round trip and erased equality, then checks the canonical transport's `IO Unit`
type. Cached targets retain those check receipts and exact SHA256 bytes. Each
compact-GC matrix runs in a fresh process and executes every target through LLVM;
emission, runtime objects, traces, outputs, six references and generated
inference-source checks remain part of execution. The supervisor checks the
pinned target manifest and files before and after the matrix, and reports all
25 target hashes.

The [port performance record](../docs/port-test-performance.md) describes the
unchanged-input interpreter measurements. Matrix tests default to GC free-space
divisor 1. `MLF_TEST_MATRIX_GC_DIVISOR=1`, `2` or `4` selects an explicit policy;
each native matrix report records it alongside the initial heap. The release
wrapper chooses 4 for port on hosts with at most 8 GiB RAM, while preserving the
8 MiB compact-GC initial heap and every test execution.

| Root group | MLF entry | Preserved coverage |
| --- | --- | --- |
| unit | CoreMain, Figure12SuiteMain, HarnessMain, TestFrameworkMain, RegexMain | framework API/CLI contracts; 684 compiler checks; 6712 Algorithm W cases represented by 6703 executions; annotations, crate resolution, SCC queries and codegen caching, POSIX/Windows crate paths and native cache commands, indexed optimizer and legacy differential checks; all 43 Figure 12 labels with 41 distinct executions and 36 controls; 67 benchmark/bootstrap/release/cache harness methods including two cache regressions; 56 regex actions |
| packages | PackagesMain | 79 completed cases: 22 resolver checks; 29 compiler integration cases, including native PGO isolation, shared cache survival, corruption recovery and source invalidation; 28 checked-release cases covering source-free builds, relocation, shared dependencies, compatibility, pins, damaged artifacts, GitHub fetching, offline cache repair and packed asset validation; target dependency/instance selection; scheduler diamond and variant deduplication, jobs 1/2/4 equivalence, concurrent cache publication, failure recovery, empty graphs and target-name collisions; 22 native runner lifecycle and protocol checks |
| backends | BackendSuiteMain | 523 fixtures and 575 execution rows on interpreter and LLVM, compact-GC layout |
| port | PortMain, ReferencesMain | 25 LLVM fixtures with compact-GC, six reference programs, generated inference input equality |
| parity | CorpusMain, CheckTarget | All 7086 prescribed acceptance/type/rejection cases, 7075 distinct source compilations, and 80 runtime rows on both backends |
| self-host | Tests.CompilerTests | Fresh next-stage compiler build and LLVM/native binary fixed point |

The unit group also runs `RegexMain`, covering the portable regex parser and
ordered matcher. The benchmark harness checks all ten workload manifests and
fixtures, including regex-redux with an independent scanner oracle. It compiles
and runs the actual regex-redux MLF source on native boundary/adversarial inputs
and exercises the same source in the interpreter. C/Rust/Haskell baseline
toolchains are not required for these compiler correctness tests.

`Tests.Oracle` has its own monotypes, substitution, and generalization. It imports
no compiler, graph solver, or target checker. `Tests.GraphUnificationReference`
retains the persistent map algorithm, Kahn traversal, and path-based LCA.
`Tests.SnakeBaseline` independently implements the game and scripted console.
`Tests.IndependentCheck` and `Tests.IndependentType` are frozen test checking
modules rather than aliases to the candidate's checking implementation.

`golden/parity-seed.tar.gz` preserves the previously verified source corpus and
Haskell-seed expected types. `Tests.Corpus` reproduces the exhaustive, seeded,
annotation, and Figure 12 inputs and validates their independent acceptance
oracles before use. It checks current repository inputs against the reviewed
baseline. Golden expectations are never rewritten from candidate inference.
Exactly two archived module-import-cycle rejections have explicit, source-guarded
acceptance overlays for crate compilation. Their prescribed type is `Int`,
checked against the independent literal target `42`; the archive itself is
unchanged. The resulting corpus has 3,204 accepted cases. See the
[oracle migration record](../docs/crate-migration.md#oracle-migration).
The `unit` and `packages` groups now validate structured execution evidence
against [`golden/unit-inventory.json`](golden/unit-inventory.json). Completed
callbacks emit case IDs, explicit aliases and measured execution counts. The
parent requires a full start, one terminal completion, the exact reviewed ID
sets, and matching metric counts; partial, duplicate, missing and stale reports
fail the gate. Each receipt hashes the report and reviewed inventory alongside
the compiler, manager, runner and source snapshot. Text logs remain diagnostic.

The original checked-package release amendment added 28 `checked release: ` IDs
from `Tests.PackageReleases` to the then-existing 47 package executions, for 75
total. The parallel-build integration below extends that reviewed inventory to79.
The target-dependency/scheduler integration fixture runs in addition to the 79 structured cases and must report its separate successful completion. Each ID is emitted only after its scenario assertions complete. The full package
entry wraps resolver, source-package and release scenarios in one coverage
report; `--releases` and the fake `gh` helper remain focused entry points and
cannot substitute for the complete campaign. These additions come from the
reviewed release source, not candidate output.

The parallel-build integration adds four existing resolver scenarios for omitted,
selected, empty and invalid target dependencies to the structured inventory.
Their IDs are reviewed from `Tests.PackageResolver`; the merged inventory therefore
requires 79 package executions (22 resolver, 29 source-package and 28 release).
The separate target-dependency and scheduler fixture still completes in addition
to those IDs and must print its successful completion before the group can pass.

The inventory was transcribed from the verified baseline and existing source
registries. A deliberate coverage change must update it separately with a
reviewable explanation of added or removed executions and aliases. Never
regenerate expectations from the candidate's output to make a run pass. The
reviewed `91962c2` source amendment extends the previous 58 harness IDs with five
benchmark checks and two regex-redux checks. Their inner native and interpreter
loops must complete seven and two oracle comparisons respectively. The separate
regex inventory pins 56 completed actions, including 18 invalid-pattern
rejections (17 counted batch callbacks plus one expansion-limit regression),
27 match cases and 11 other assertions. These additions come from the reviewed
source assertions, not a previously completed baseline run or candidate output.
The harness IDs added by this amendment are:

- `test_regex_redux_oracle_counts_each_variant_and_nonoverlapping_matches`
- `test_regex_redux_cleanup_follows_header_and_linefeed_pattern`
- `test_regex_redux_replacements_are_ordered_and_delimiter_matches_exact`
- `test_regex_redux_requires_all_counts_lengths_order_and_exact_bytes`
- `test_native_dependency_headers_survive_suppressed_system_flags`
- `test_regex_redux_measured_native_source_matches_independent_oracle`
- `test_regex_redux_measured_interpreter_source_matches_independent_oracle`

The required new metrics are `harness.regex-redux-native-executed = 7`,
`harness.regex-redux-interpreted-executed = 2`, and
`regex.invalid-patterns-executed = 17`. The regex IDs and the source hashes
reviewed for this amendment are recorded in the inventory metadata.

The separate `4af369d` source amendment retains the upstream duplicate
consolidation and adds two completed cache controls. The Core inventory removes
`choose id retains an MLF bound`, whose source, principal type and target
roundtrip assertions remain under Figure 12's existing `A2 principal type`.
It replaces `indexed unification agrees with map-based reference` and
`indexed graph analysis preserves sparse and negative identities` with
`indexed unification and identity renaming agree with map-based reference`.
The combined action retains all 5,616 canonical inputs, both graph reference
comparisons and all 320 renamed executions, reusing 80 already checked canonical
results. These are execution consolidations, not new report aliases; the
Figure 12 IDs, aliases and required counts remain unchanged.

The harness inventory grows from 65 to 67 IDs with
`test_source_dependency_cache_controls` and `test_checked_native_driver_cache`.
Only the parent harness records these IDs after each complete control returns;
the driver-cache child branch does not emit another completion. All previously
required numeric oracle metrics remain unchanged. The inventory records the
exact ID changes, canonical owners and reviewed upstream source hashes. The
`71c47ee` integration record is historical evidence for upstream `4af369d`,
not an execution report for this merged framework tree. These expectations were
reviewed from the upstream source and were not regenerated from candidate output.

The framework includes literal report
mutation tests for these rules; compiler oracles and the frozen corpus remain
independent of the runner.

The optional [`mlf-test-tools`](../testing/tools/README.md) package supervises
individual `Test.Case` actions in fresh processes using the existing POSIX
measurement helper. Native framework checks exercise failure continuation,
crashes, timeouts, log capture, workspace freshness and malformed reports.

The [coverage audit](coverage-overlap.md) maps retained and consolidated cases.
The 17 duplicate unit checks now run in the port matrix, whose runtime smoke
case is merged into RuntimeCases. Shared ST input data retains separate
unit/type, CLI parity, and nested compiler execution oracles.
The port inference fixture also prescribes `Int` for its module-import cycle;
its declarations are not mutually recursive. Its other inference expectations
and generated source remain unchanged.

Execution sharing is confined to exact duplicates within one verification path.
The independent HM generator still produces all 5000 seeded terms; unit execution
retains the first original seed for each of its 4991 distinct ASTs. Figure 12 keeps
every paper label and shares only equal source, signature environment and expected
acceptance. Parity keeps every frozen row and records 11 aliases to successful
canonical executions (nine HM and two Figure 12); its key contains the complete
source and all configuration/oracle fields except descriptive identity and source
filename. Runtime and module cases never share parity executions. The independent
unit and parity oracles remain separate. The audit lists the 17 implemented
reductions and the stress and boundary cases retained alongside smaller witnesses.

The two graph-unification methods now run as one check: the first 80 canonical
results also supply the identity-renaming comparisons, avoiding 80 repeated
canonical executions while retaining all 320 renamed executions and both graph
reference comparisons. Figure 12's A2 principal-type control owns the exact
choose-id source/type/roundtrip check previously repeated in Core. These changes
reduce Core's method count from 686 to 684; they preserve the underlying graph
inputs, principal-type assertion, Figure 12 labels and independent parity oracle.

The historical [cache-cleanup validation record](../docs/test-cache-cleanup.json)
covers unit, packages, backends and cold/warm port execution on the source
snapshot before upstream integration. The warm port control
changed an unrelated inventory file and corrupted one prepared target: 24
targets were reused, the damaged target was rebuilt, and all driver artifacts
were reused while all 25 fixtures executed again. All prepared target bytes
match the cold run and the prior compact-only baseline. Observed cold/warm port
times were 25m 6s and 5m 13s under concurrent host load; these are not a
controlled before/after speed benchmark. Self-host and parity were not rerun.
These results predate the upstream regex additions and do not validate the
combined source tree.
The subsequent [integration record](../docs/test-cache-cleanup-integration.json)
records a rebuilt manager and a passing full unit group on upstream `4af369d`,
including regex, both cache regressions, Core and Figure 12. That record predates
this framework integration and does not validate the current merged source tree.

The C files `tests/native/binary_files.c` and `tests/native/host_support.c` provide binary file transport,
environment-name enumeration, and per-process measurements/process groups.
They contain no test assertions. Existing C ABI fixtures retain their low-level
layout, sharing, and root checks. MLF drives every probe mode and checks exit
status, output, error diagnostics, and allocation counts. The process-group
fault fixture injects a redundant `setpgid` failure; MLF verifies successful
execution and complete child cleanup through both transport APIs.

Historical validation on 2026-10-15 passed all six root groups through the native MLF
package manager, with GHC, Cabal, and Python blocked on `PATH`. The blocker log
was empty. Both matrices ran independently for both backends and runtime
layouts; the fresh self-host build reproduced the compiler's LLVM and binary
hashes. The [validation record](../docs/native-tests-validation.json) records
the source manifest, artifact hashes, coverage totals, and local log paths.

After retiring the Haskell compiler and old harnesses, the 2026-10-19
[complete native validation](../docs/native-only-validation.json) passed all six
groups with a fresh two-generation native build and `--locked test`. Both full
matrices and the self-host fixed point passed; the forbidden-tool log was
empty. All 72 benchmark pins and the archived measurements remain unchanged.
That record precedes the crate migration and does not validate its changes;
the [crate migration ledger](../docs/crate-migration.md) records separate acceptance.

The 2026-10-20 [crate validation](../docs/crate-validation.json) completes all six
native groups against the immutable R11 source and recorded PGO compiler. Both
backend/port layouts pass, and a fresh source self-host reproduces complete LLVM
and native bytes using the same profile. Each group has a successful actual outer
exit and a complete native report; R2's interrupted controller remains historical.
Every test process reran. Self-host and performance builds used fresh empty
directories. The final isolated builds and all nine native workload gates pass.

Future validation must rerun every group against fresh source/tool snapshots.
`--type` and individual module compilation are development checks, not
substitutes for executing the assertions and backend coverage audits. The full
root run uses `./mlfpkg --timeout 21600 test`; individual fixture limits remain
unchanged.

One representation-specific assertion is adapted explicitly: Haskell graph IDs
use bounded machine `Int`, while the MLF graph uses arbitrary-precision `Int`.
The former overflow fixture therefore checks exact allocation across the same
word boundary in MLF. It preserves the three-copy budget and the original
last-representable-ID case, and validates the expanded graph on both sides of
the boundary. Native array size/index overflow remains covered by the C ST ABI
probes.

The source-position assertion checks `original.emlf:2:12:` in the native parser's
diagnostic format. This preserves the original line 2, column 12 check and also
checks the filename; the Haskell parser renders those coordinates in prose.

Native MLF strings contain Unicode scalars, so a surrogate cannot be constructed
as a host string. The forged-surrogate regression injects the same escaped
literal into the serialized target and sends it to both drivers. Both reject it
before encoding, with no console events; the normal status, trace and execution
coverage checks still apply.

The [matrix cleanup](../docs/test-matrix-cleanup.md) records the deliberate removal
of compiler-scale outer interpretation, exact empty-input deduplication and
small semantic matrices with separate scale regressions. The compact-GC layout,
all 25 port fixtures and all 575 differential backend rows remain.
