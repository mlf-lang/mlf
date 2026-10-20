# Native MLF compiler tests

The local `mlf-tests` package preserves the original assertions, input corpora,
runtime event traces, generated graph properties, and harness fault injections.
Root `mlfpkg test` builds these executables through the MLF package manager.
The old Haskell/Python suites and Haskell compiler have been removed.
No GHC, Cabal, or Python executable is needed. C fixtures live in `tests/native/`;
benchmark baselines and golden oracle data remain unchanged.

The shared test library contains eight helper, transport, collection-wrapper
and independent-checker modules. Each executable explicitly lists the private
test modules imported by its entry point. All 77 test modules remain reachable
across those entries. Building `port` and its six reference programs now compiles
21 test modules including their two entries, instead of compiling all 79 first.
`mlfpkg --manifest tests/mlf-package.json plan` checks those import boundaries;
adding a test module also requires adding it to each importing target's
`modules` map, or to the shared library when it is common support.

The [port performance record](../docs/port-test-performance.md) describes the
unchanged-input interpreter measurements. Matrix tests default to GC free-space
divisor 1. `MLF_TEST_MATRIX_GC_DIVISOR=1`, `2` or `4` selects an explicit policy;
each native matrix report records it alongside the initial heap. The release
wrapper chooses 4 for port on hosts with at most 8 GiB RAM, while preserving the
512 MiB standard / 8 MiB compact initial heaps and every test execution.

| Root group | MLF entry | Preserved coverage |
| --- | --- | --- |
| unit | CoreMain, Figure12SuiteMain, HarnessMain | 686 compiler checks, exhaustive/seeded Algorithm W, annotations, crate resolution, SCC queries and codegen caching, POSIX/Windows crate paths and native cache commands, indexed optimizer and legacy differential checks, 43 Figure 12 expressions and 36 controls, 57 benchmark/bootstrap/release harness methods |
| packages | PackagesMain | 15 original resolver methods plus three additional checks; 26 compiler integration cases, including native PGO cache isolation and profile-content invalidation |
| backends | BackendSuiteMain | 523 fixtures and 575 execution rows on interpreter and LLVM, standard and compact GC layouts |
| port | PortMain, ReferencesMain | 25 fixtures, six reference programs, generated inference input equality, both backends and layouts |
| parity | CorpusMain, CheckTarget | 7086 prescribed acceptance/type/rejection cases and 80 runtime rows on both backends |
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
