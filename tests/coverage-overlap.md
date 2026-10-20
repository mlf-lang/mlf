# Coverage ownership after the native compiler migration

The 0.2.0 audit compares assertions, stimuli, oracles and execution paths.
Matching topic names alone do not make tests redundant. The root package keeps
six groups: `unit`, `packages`, `parity`, `backends`, `port` and `self-host`.

`unit` calls compiler libraries in a native test executable. `backends` executes
user programs through interpreter and LLVM drivers and checks IO events, errors,
unused input and exact output. `port` compiles the compiler's own library probes
as programs, independently checks and serializes their targets, then executes
those targets through both drivers. Both matrices run under standard and compact
GC layouts. These are different execution paths.

## Consolidations

| Previous coverage | Decision and retained owner |
| --- | --- |
| Five `Tests.OptimizerQueries` unit cases | Remove the duplicated unit module. `bootstrap/tests/OptimizerQueries.emlf` covers the same size boundaries (20–28), use counts (0–5), shadowing, recursive capture and pattern binding, plus four short-circuit/laziness controls. Its 22 assertions run through both backends/layouts. Indexed/legacy optimizer differential tests remain in unit. |
| Twelve `Tests.StrictFieldAnalysis` unit cases | Remove the duplicated unit module. Every label, constructor, erased input and expected field vector was compared with the corresponding StrictFields port case by an executable MLF audit. Port retains all twelve plus the generated-entry lowering check. Tests.StrictFields runtime/event tests remain in backends. |
| RuntimeSmoke and RuntimeCases | Move the exact printInt 42 nested-runtime call and its success marker into RuntimeCases, retaining the expected `42\nok\n` output. Remove the separate smoke source/expectation and matrix row. |
| ST source/target inputs copied into StateTypes | Import Tests.StateCases as the single input table. All 56 source strings and 12 target strings, including order and labels, were compared before replacement. Unit type assertions, port nested compilation/roundtrip/output assertions and CLI parity frozen independent oracles remain separate. |
| One library containing all 77 test modules | Keep eight shared support modules and assign each entry's remaining imports to its private target. Every original module remains reachable. Port plus references compiles 21 test modules including entries, instead of 79; it no longer has to infer unrelated unit and backend cases. |

The resulting inventory is **685 unit checks**, **523 backend fixtures / 575
execution rows per layout**, and **25 port fixtures / 25 execution rows per
layout**. The decrease of seventeen unit cases and one port row reflects the
consolidations above, not missing executions. Package, parity, Figure 12,
independent Algorithm W, harness and self-host requirements are unchanged.
Native Windows also runs the same 18 resolver and 26 package integration checks,
plus the native 7,086-case parity harness.

## Retained port coverage

| Fixture | Reason to retain |
| --- | --- |
| foundation | Mixed map/list oracle, laziness, recursion and primitive ABI numbering in compiled compiler-library code. |
| MapFolds | Exhaustive 1,024 subset pairs, key representatives and lazy folds against a finite membership oracle. |
| IntegerContainers | 1,200 mixed updates, rotation prefixes, unbounded integers and lazy keys/values against association lists. |
| OptimizerQueries | Consolidated optimizer assertions and unique bounded-traversal controls. |
| ConstructorProjection | Direct code-generation state and environment projection checks; runtime fixtures exercise another path. |
| ForceReuse | Direct builder dominance/branch-state invariants; backend IO/error ordering is separately tested. |
| StrictFields | Consolidated field inference assertions and lowering check; runtime field behavior remains in backends. |
| prelude | Free-name analysis, implicit prelude selection and source-structure equality. |
| Target | Target construction/checking, invalid identities, floating-point serialization and deep binder scopes. |
| frontend | Parser/class/surface structures, name capture and wide type counts; complements source acceptance tests. |
| LexerCounters | Large-input counter and bounded traversal behavior. |
| LLVMBuild | 100,001 fresh names with deliberately unevaluated fields and prefixes. |
| RuntimeCases | Nested interpreter laziness, recursion, arrays, success and failure, including the former smoke call. Direct primitive calls additionally check lazy branches, argument error order, partial application and overapplication. |
| StateRuntime | Nested runtime ST effects, references and lazy values; direct backend ST traces remain independent. |
| StateTypes | Nested compiler/type-checker execution using shared stimuli and unchanged expected output. |
| GraphConformance | Independent persistent graph reference output. |
| GraphScopes | Independent scope construction/reference output. |
| GraphDense | Independent dense graph reference output and stress coverage. |
| OrderedTraversal | Independent traversal reference output. |
| SolverReuse | Reuse, solver state and nested inference invariants, including expensive interpreter execution. |
| TypeCache | Cached type operations and invalidation in compiled library code. |
| GraphStack | Deep graph/stack behavior. |
| EmbeddingPruning | Independent reference program; preserve its oracle despite overlap with unit examples. |
| InferenceConformance | Independent reference output and byte-exact input regeneration, including Figure 12 A8 rejection. |
| PrimitiveMetadata | Compiled metadata agrees with the host transport contract; all 82 constant arities are checked against the unchanged type signatures. Foundation independently checks ABI ordering. |

The six reference programs remain distinct implementations. They are not replaced
by candidate output. The parity archive, benchmark source pins and independent
Snake implementation retain their separate roles.

Full release qualification must rerun the new inventory on the actual candidate.
The historical 702/523/26 R11 record describes the earlier source and must not be
relabeled as validation of this cleanup.

The [port performance record](../docs/port-test-performance.md) documents the
allocation optimizations, unchanged-input comparisons and rejected experiments.
