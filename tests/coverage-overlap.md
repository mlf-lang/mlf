# Coverage ownership after the native compiler migration

The 0.2.0 audit compares assertions, stimuli, oracles and execution paths.
Matching topic names alone do not make tests redundant. The root package keeps
six groups: `unit`, `packages`, `parity`, `backends`, `port` and `self-host`.

`unit` calls compiler libraries in a native test executable. `backends` executes
user programs through interpreter and LLVM drivers and checks IO events, errors,
unused input and exact output. `port` compiles the compiler's own library probes
as programs, independently checks and serializes their targets, then executes
those targets through LLVM. Backend differential tests retain both drivers. Both
matrices use the compact-GC layout. These are different execution paths.

## Consolidations

| Previous coverage | Decision and retained owner |
| --- | --- |
| Five `Tests.OptimizerQueries` unit cases | Remove the duplicated unit module. `bootstrap/tests/OptimizerQueries.emlf` covers the same size boundaries (20–28), use counts (0–5), shadowing, recursive capture and pattern binding, plus four short-circuit/laziness controls. Its 22 assertions now run through LLVM with compact-GC. Indexed/legacy optimizer differential tests remain in unit. |
| Twelve `Tests.StrictFieldAnalysis` unit cases | Remove the duplicated unit module. Every label, constructor, erased input and expected field vector was compared with the corresponding StrictFields port case by an executable MLF audit. Port retains all twelve plus the generated-entry lowering check. Tests.StrictFields runtime/event tests remain in backends. |
| RuntimeSmoke and RuntimeCases | Move the exact printInt 42 nested-runtime call and its success marker into RuntimeCases, retaining the expected `42\nok\n` output. Remove the separate smoke source/expectation and matrix row. |
| ST source/target inputs copied into StateTypes | Import Tests.StateCases as the single input table. All 56 source strings and 12 target strings, including order and labels, were compared before replacement. Unit type assertions, port nested compilation/roundtrip/output assertions and CLI parity frozen independent oracles remain separate. |
| One library containing all 77 test modules | Keep eight shared support modules and assign each entry's remaining imports to its private target. Every original module remains reachable. Port plus references compiles 21 test modules including entries, instead of 79; it no longer has to infer unrelated unit and backend cases. |

The resulting inventory is **686 unit checks**, **523 backend fixtures / 575
execution rows per layout**, and **25 port fixtures / 25 execution rows per
layout**. Seventeen duplicate unit cases and one port row were consolidated;
one unit regression adds POSIX and Windows crate paths, rejection of relative
paths and structured native cache commands. The later reductions below preserve
the full logical parity, Figure 12 and independent Algorithm W inventories.
Native Windows also runs the same 18 resolver and 29 package integration checks,
plus the native 7,086-case parity harness.

## Smaller witnesses and exact execution sharing

The following 17 decisions implement the reviewed static audit. A smaller semantic
witness is paired with the existing scale regression where scale has a separate
purpose. Exact duplicate execution is shared within its original verification
path. The subsequent cleanup below deliberately removes outer port interpretation;
independent reference implementations and the compact-GC runtime remain.

| # | Case | Implemented decision and retained boundary |
| --- | --- | --- |
| 1 | OptimizerQueries | Three large-function witnesses use 25 nodes, above the 24-node threshold. The complete 20–28 size and 0–5 use sweeps and all 22 assertions remain. |
| 2 | Target | Two binding-identity witnesses use depth 2. A separate depth-512 alpha-equivalence regression remains, raising the fixture to 21 assertions. |
| 3 | GraphValidation | Scope escape uses a validated four-node graph and must also be rejected by the uncached reference. Valid depth-1000 validation remains. |
| 4 | Readability | Consume two elements from the cyclic lazy list. |
| 5 | StateCases | The length/unevaluated-initial-value witness uses one element. The worker's 1000/4096 iterations and 512-step fallback boundary remain. |
| 6 | NativeOptimization | The structural recursive encoding runs `sum 2`, covering recursion and termination. Other optimizer cases remain. |
| 7 | DNA | Use 135 updates over the same 67 keys, preserving repeated counts, collisions and growth. GC churn fixtures remain. |
| 8 | Native string bounds | Five sparse bounds failures use a 31-scalar Unicode string and assert that it actually selects sparse indexing. Million-scalar success, slices and 2000 random indexes remain. |
| 9 | Native values modes | Run success once without BDWGC. Every GC profile still runs success and no-interior modes. |
| 10 | Native zero environments | Without BDWGC, test every size 0–40 once. GC configurations retain 100 rounds and their collection/reuse checks. |
| 11 | ProjectionChanges | 672 parameter combinations become 571 distinct ordered before/after lists. Full stimulus equality is independent of candidate graph equality; all scales and integer renamings remain. |
| 12 | IntSetUnions | 360 directional calls become 276 distinct ordered list pairs. Both directions remain whenever their actual inputs differ; the sorted-list and balance oracle remains. |
| 13 | SolverIndexAudit | For each of six integer renamings, check one valid baseline, seven parent corruptions and seven descendant corruptions separately: 15 instead of 64 combinations. Invalid scope and empty-graph controls remain. |
| 14 | HM | Keep all 5000 generated labels and original seeds. Unit runs 4991 distinct seeded ASTs plus 1712 exhaustive terms; parity independently shares nine identical source/configuration/oracle pairs. |
| 15 | Figure 12 | Keep all 43 paper labels and all 36 controls. Unit runs 41 distinct programs, recording A12.1 → A10.1 and E3a → A12.2; parity independently records the same two aliases. |
| 16 | Benchmark harness | Binary-trees input 10 is checked once by the full pinned-workload oracle check. Default depth and input-7 checks remain separate. No benchmark source, pin, result or threshold changes. |
| 17 | PackageResolver | Retain the manifest-relative check and make it independent: change the working directory and add a same-name decoy dependency there. It must still resolve the original manifest's Base module. |

The unit summary distinguishes **6712 HM cases / 6703 actual executions** and
**43 Figure 12 labels / 41 actual executions**. Parity distinguishes **7086
frozen rows / 7075 source compilations**, with 11 explicit aliases and all 160
runtime executions. No successful output or exit record is fabricated for an
alias; reports identify the canonical successful execution. A new harness check
guards source, configuration and oracle equality, bringing the harness to 58
methods. Three real shared-store recovery/invalidation cases bring package
integration to 29; resolver methods remain 18.

This table records the first 17 changes. The subsequent matrix cleanup addresses
the graph/projection candidates; the remaining size candidates are retained.
In particular, GraphStack's 35000 nodes, LLVMBuild/LexerCounters lazy counters,
MapFolds' 1024 small subset pairs, GC churn, large JSON scanning, constructor
spill boundaries, capture counts, benchmark vectors and fresh self-host builds
retain their existing size and execution paths.

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
| SolverReuse | Reuse, solver state and nested inference invariants, with native execution with compact-GC. |
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

## Subsequent matrix cleanup

Port executes all 25 checked targets through compact-GC LLVM. It no
longer interprets the complete compiler/graph probes. This is an intentional loss
of compiler-scale interpreter stress coverage, not a claim of identical backend
coverage. Direct interpreter semantics, CLI parity, package tests and the 575-row
differential backend matrix remain. RuntimeCases and StateRuntime still invoke
the interpreter internally when those probes are compiled through LLVM.

| Area | Selection and preserved coverage |
| --- | --- |
| Component scopes | Small branching fixture plus chains 1/2/5 under all six identity renamings; original 31/33/127/257 chains once each with every start category. Identical raw start lists run once. |
| Component projection | Small branching fixture and chains 1/2/5 under all renamings; original 17/65 scale cases once each. Empty, roots, inner/last node, complete and repeated starts remain. |
| Restoration | All eight modes, four offsets and two strides at sizes 0/1/2/5; all modes at 17/33 with canonical identities. Empty solved lists no longer duplicate the explicit empty control. Negative and out-of-range ranks remain. |
| Projection ranks | Empty case once; 1/2/3/5/17 under all offsets/strides; 65/257 scale plus a large-integer 257 case. Duplicate full/filtered input sets run once; every valid rank, invalid rank, alias and lazy node-value assertion remains. |
| Projection changes | 528 generated pairs / 427 distinct executions (previously 672/571). All mode pairs and six renamings at 0/1/2/5/17; all modes at 65/257 plus a large-identity 257 case. Raw-input equality and independent map-difference oracle remain. |
| Index transitions | All eight modes/four offsets at 0/1/2/5; all modes at 17/33 with canonical identities and at 33 with both large offsets. Both directions and both patch paths remain. |
| Index edits | 912 generated steps instead of 3072: 24 steps across seeds/offsets, with two sequences extended to 96 steps instead of replaying their prefixes. Forty explicit edit steps cover duplicate insertion, absent removal, multiple bucket members and final bucket deletion. Each step retains the independent edge-list oracle. |
| Sorted graph builder | Empty once; 1/2/3/17 at all three offsets; 257/4096 scale once. Map validity, complete nodes, arbitrary identity fields and independent insertion oracle remain. |
| Branching solver | All 36 pairs on a small branching graph; ten selected pairs on the original 1002-node graph retain roots, ancestry, sibling/cross-branch junctions and deep jumps. Full graph/index reference comparisons remain. |
| Scope audit | Exhaustive corruption on the original small graph and a 16-node chain. Scale at 15/16/17 and 255/256/257 scope pairs checks every jump level, exact baseline, roots and malformed intervals; original 512-node graph remains. |
| Copy allocation | Full small counts 0/1/2/7 with offsets/fresh-word boundaries; 31/257 scale and a large-identity scale interaction. Exact fresh/original-list pairs are deduplicated globally; forward/reverse/repeated identities and complete receipts remain. |

Known stack depth, GC churn, constructor spill, captures 28/29, ST fallback,
LLVMBuild/LexerCounters, independent reference code and historical benchmark
sources/pins are unchanged by this follow-up. Timing and validation results are
recorded separately in [test-matrix-cleanup](../docs/test-matrix-cleanup.md).
