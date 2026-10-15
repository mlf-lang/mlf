# Native MLF compiler tests

The local `mlf-tests` package ports the original assertions, input corpora,
runtime event traces, generated graph properties, and harness fault injections.
Root `mlfpkg test` builds these executables through the MLF package manager.
No GHC or Python executable is needed by the active test path.

| Root group | MLF entry | Preserved coverage |
| --- | --- | --- |
| unit | CoreMain, Figure12SuiteMain, HarnessMain | 636 compiler checks, exhaustive/seeded Algorithm W, annotations, 43 Figure 12 expressions and 36 controls, 53 benchmark/bootstrap/release harness methods |
| packages | PackagesMain | 15 original resolver methods plus three additional checks; 19 compiler integration cases |
| backends | BackendSuiteMain | 494 fixtures and 546 execution rows on interpreter and LLVM, standard and compact GC layouts |
| port | PortMain, ReferencesMain | 26 fixtures, six reference programs, generated inference input equality, both backends and layouts |
| parity | CorpusMain, CheckTarget | 7086 prescribed acceptance/type/rejection cases and 80 runtime rows on both backends |
| self-host | Package.CompilerTests | Fresh next-stage compiler build and LLVM fixed point |

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

The C files `binary_files.c` and `host_support.c` provide binary file transport,
environment-name enumeration, and per-process measurements/process groups.
They contain no test assertions. Existing C ABI fixtures retain their low-level
layout, sharing, and root checks. MLF drives every probe mode and checks exit
status, output, error diagnostics, and allocation counts. The process-group
fault fixture injects a redundant `setpgid` failure; MLF verifies successful
execution and complete child cleanup through both transport APIs.

Validation on 2026-10-15 passed all six root groups through the native MLF
package manager, with GHC, Cabal, and Python blocked on `PATH`. The blocker log
was empty. Both matrices ran independently for both backends and runtime
layouts; the fresh self-host build reproduced the compiler's LLVM and binary
hashes. The [validation record](../docs/native-tests-validation.json) records
the source manifest, artifact hashes, coverage totals, and local log paths.

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
