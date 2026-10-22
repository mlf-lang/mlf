# Native MLF compiler tests

Pull requests use the explicit [PR smoke group](../docs/ci.md): Figure 12,
four independent checker controls, 12 selected interpreter/LLVM fixtures and
three package/cache checks. It builds and tests checkout tools. The six full
root groups below retain their existing coverage and do not repeat smoke.

The local `mlf-tests` package preserves the original assertions, input corpora,
runtime event traces, generated graph properties, and harness fault injections.
Root `mlfpkg test` builds these executables through the MLF package manager.
The old Haskell/Python suites and Haskell compiler have been removed.
No GHC, Cabal, or Python executable is needed. C fixtures live in `tests/native/`;
benchmark baselines and golden oracle data remain unchanged.

The shared test library contains eight helper, transport, collection-wrapper
and independent-checker modules. Each executable explicitly lists the private
test modules imported by its entry point. All 78 test modules remain reachable
across those entries. Building `port` and its six reference programs now compiles
21 test modules including their two entries, instead of compiling all 79 first.
`mlfpkg --manifest tests/mlf-package.json plan` checks those import boundaries;
adding a test module also requires adding it to each importing target's
`modules` map, or to the shared library when it is common support.

Root builds and nested test builds share a checked artifact store through
`{cache}` and `--cache-dir`. Each test group keeps its own `suite-build` report
and logs. Source/tool identities, artifact checksums and recursive dependency
receipts still control reuse; a fresh self-host stage keeps a new store.
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
| unit | CoreMain, Figure12SuiteMain, HarnessMain | 686 compiler checks; 6712 Algorithm W cases represented by 6703 executions; annotations, crate resolution, SCC queries and codegen caching, POSIX/Windows crate paths and native cache commands, indexed optimizer and legacy differential checks; all 43 Figure 12 labels with 41 distinct executions and 36 controls; 58 benchmark/bootstrap/release harness methods |
| packages | PackagesMain | 15 original resolver methods plus three additional checks; 29 compiler integration cases, including native PGO isolation, shared cache survival, corruption recovery and source invalidation |
| backends | BackendSuiteMain | 523 fixtures and 575 execution rows on interpreter and LLVM, compact-GC layout |
| port | PortMain, ReferencesMain | 25 LLVM fixtures with compact-GC, six reference programs, generated inference input equality |
| parity | CorpusMain, CheckTarget | All 7086 prescribed acceptance/type/rejection cases, 7075 distinct source compilations, and 80 runtime rows on both backends |
| self-host | Package.CompilerTests | Fresh next-stage compiler build and LLVM/native binary fixed point |

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
