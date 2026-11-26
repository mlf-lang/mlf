# Int64 Patricia collection qualification

The compiler now uses a lazy IntMap Patricia tree and a bitmap-leaf IntSet,
ported from `containers-0.8.1`. `provenance.json` pins the downloaded archive and
upstream sources; the complete BSD attribution is in
`tools/release/licenses/containers-0.8.1.txt`. Cached cardinalities retain
constant-time `size` and support rank/select without a second tree. Signed enumeration,
left/right union bias, and lazy map payloads are part of the contract.

This is also an explicit public representation migration. The former balanced
`Map Int` tree is no longer the physical representation of IntMap or IntSet.
The tests do not describe the old BST shape contract as unchanged.

## Retained independent controls

`run_controls.py` checks both optimization levels against independent
`Data.IntMap`/`Data.IntSet` models and an independent bit/routing model. The
kind-routing controls include malformed five-node prefix trees which would
have passed a sorted-leaf check while routing lookups incorrectly.

`run_integrated.py` authenticates an ordinary producer and copies its objects.
Only test modules are compiled; existing production objects must remain
byte-identical. Select `p123`, `graph`, `validation`, or `builtin`.
`--source` identifies the producer's authenticated source snapshot, including
its current private session implementation. Test controls come from this
checkout and are recorded separately in the receipt.

The maintained Haskell controls are direct sources in `controls/`. They already
express the current Int64 ABI and Patricia representation; the runner copies
and compiles them without rewriting types, import lists, labels, or assertion
bodies. Unchanged controls in other performance directories are reused in
place. Ordinary control edits require no fixed SHA update. Receipts record
all control inputs before execution and verify them again afterwards.

Independent old algorithms live in `oracles/` or their existing frozen source
locations. Their small fixture hash inventory protects those reference bytes;
it does not qualify current compiler source or reconstruct a historical commit
chain. [The oracle notes](oracles/README.md) identify their origins and scope.
The direct sources were compared once with the previous preparation's final
Haskell output: graph, P1/P2/P3, and validation match, with only an extra final
blank line removed from two maintained controls.
That conversion check is not a recurring CI gate.

Private graph checks still need a test-only view of the current
`Bootstrap.CrateSession`. The small header lexer changes its module name and
removes the export restriction, preserving every body byte. Export order,
comments, and whitespace are accepted. The same helper serves the retained C3
checks; actual public-export rejection tests continue to compile against the
ordinary production interfaces.

Historical adapters, `legacy-controls-pins.json`, and source migration manifests
remain available for reproducing the old reports from commit
`171717ad5bd025ee977d4ca9fd8f93abcbc68612`. Routine controls no longer run their
source projections or reversible diff ledgers. In particular, the historical
validation projection and P2 writer bridge tests are replaced in the current
route by the actual validation and binary-writer executions below.

Map maintenance uses the existing `map-policy` framework entry. That suite
checks contents, balance, cached counts, demand/error order, and the intentional
step-21 shape difference from the old Map. The obsolete integrated `map-balance`
group required the entire current 400-step trace to keep the historical tree
shape; it has been retired rather than weakening its old assertion. Its
original sources remain in `tools/performance/map-balance/` for historical use.

All retained finite rows remain, including oversized literals which wrap under
Int64 and can duplicate other rows. This does not claim the former arbitrary
precision arithmetic contract.

For graph controls, `OracleTypes.hs` bridges finite, total container spines to
the old frozen Graph/Solver/Constraint algorithms. Its representation checks
use `Data.Bits`, not candidate constructors. Map payloads remain lazy. This
finite bridge does not prove equivalence for arbitrary partial tree spines.
Wide identity layouts use 2^60 instead of 10^40/10^30, with unchanged injective
relationships, success/rejection expectations, and test count. The 216
heteroinput cases retain all permutations and authored outcomes. Their wide-ID
label and coordinate are explicitly migrated; actual output is not normalized
back into the historical label.

The C4 transaction boundary now checks independent Patricia invariants instead
of the nine historical BST representation probes. All remaining transaction,
public trace, demand, first-error, rollback and private-export cases remain.
The validation-reuse suite compiles the independent fixed `V1FrozenSession`
reference beside the current `V1SessionUnderTest`. It retains the 20 authored
programs, raw solver and skeleton-demand probes, three raw rejections, four
partial-value orders, and three private-export rejections. Its reference is no
longer reconstructed from the candidate source.

The P3 gate exposed an Int64 boundary bug: composing an encoding with a large
positive seed can differ from the original recurrence because multiplication
wraps before the first remainder. `appendDatatypeEncoding` now admits only
canonical residues to composition. The gate keeps all 922 old checks and adds
seven full-width seed checks.

The P2 suite executes both the retained pure/fingerprint and old text-writer
cases and the current `BinaryP2WriterControls`; it also retains the separate
native-compatibility checks. The fixed text writer is only an independent
reference for those old cases and explicitly refuses binary-envelope objects.
Current binary IO is exercised through the actual public writer and readers.

`run_fingerprint.py` directly compiles `controls/fingerprint/Oracle.hs`,
`Probe.hs`, and `Tests.hs`, with authored stdout/stderr expectations beside
them. Its explicit Python runners preserve both O0/O2 host builds and the
actual Separate proof without editing a historical Python driver's AST or
rewriting Haskell source at runtime. Both Probe and actual Separate workers
must contain direct Int64 arithmetic, with zero retired Integer-narrowing-rule
firings. The independent `Data.Int.Int64` oracle and 30 full-width pairs per
optimization level remain. The noncanonical divergence seed is -1 because the
old 2^1024 value wraps to zero; unmatched Core must use signed Int64 primitive
operations without the fusion call.

`run_file_controls.py` retains all nine authored file cases and their frozen
handwritten status/type/error expectations. The ordinary `Crate` route keeps
the original complete raw-byte comparison against its authenticated reference.
`CrateSession` already emitted an open schema-7 object at the fixed DeclId
baseline, whereas `Crate` emitted a closed schema-4 object. Their bytes and
object fingerprints necessarily differ. The explicit boundary comparison
therefore checks every original fragment body, ordered parameter/owner/use and
datatype inventories, interface fields, content hashes and complete linked
terms. Step 14 deliberately links only entry-reachable local fragments. An
independent closure over the already-compared ordered used-reference inventories
selects the reference's outer declarations, requiring every original owner and
the actual terminal entry identity. It retains all RHSs and lexical bindings;
missing live groups, retained unreachable groups, owner swaps and local-shadow
changes are negative controls. The receipt lists exactly selected and omitted
groups. This is a finite C4 oracle over actual used references, not a general
model of the production linker's additional parameter/support roots. Other
representation allowances are external type alpha-renaming,
all-Star datatype spelling, and capture-safe linked identity renaming. Actual
public readers, linking, target checking and returned `Open.audit` fragments
remain required. Separate fresh/fresh, warm-cache and audited-rebuild checks
require complete open-artifact byte equality; three actual corrupted artifacts
exercise the native admission/audit and independent comparison boundaries.

The independent reader/schema triple is unchanged from pinned Git commit
`8c4556416023ac727e3fb2294070358a3dae8d9e` and loaded into an isolated directory
before execution. Each file has its original literal SHA256; tests reject a
changed tree, changed file and checkout-module substitution. This finite C4
corpus's own artifacts and linked terms use the old primitive domain: codes
132 and 133 are explicitly rejected there. The actual builtin dependency
interface declares both new primitives, so its separate validator applies only
the authenticated reader's exact one-anchor 131-to-133 bound extension and
requires the specified Prelude owner and `freezeSTArray`/`stToIO` spelling.
It retains every dependency byte and content hash; code 134, wrong owners and
wrong spellings are rejected. This is metadata qualification, not execution
qualification of those new primitives. All production source pins and the
three frozen C4 inputs remain unchanged. Across the earlier intentional numeric
ABI change, old P3 whole-artifact bytes are not an oracle for current output;
its frozen semantic algorithms remain in the suites above.

## Performance

Correctness runs and instrumentation are not performance samples. A/B timing
uses the existing `process-spawn/compare.py`, a fixed fresh workload, raw-byte
reference checks, and a schedule frozen before sampling. Successful finite
controls alone do not imply a speedup. Sparse lookup and sorted construction
can regress even when a compiler task improves; retain those observations.

## Allocation and index interfaces

`ClassDemand.Universe` now owns a checked `nextSlot` counter. Slot allocation
does not derive identities from container cardinality, and repeated transitions
do not consume identities. The added constructor field is an explicit internal
API change; dense plans retain their previous identities and observations.

`Bootstrap.IntRank` owns rank/select and exposes immutable map/set index views.
Solver and CrateSession share these views without enumerating or copying trees.
The collection entry points delegate for compatibility. Per-node cardinalities
remain because the public constant-time `size` contract also needs them; this
refactor does not claim a smaller ordinary-tree representation.

Interpreter ST/async stores, datatype pool indexes, identity inventories and
renaming tables use the shared Patricia collections. Name-keyed collections
retain their comparison and payload-demand semantics. The GHC IntTable primitive
uses containers IntMap when machine Int can represent every Int64 key, and a
lossless generic fallback on narrower hosts. Writes preserve key-before-value
demand and failed-write behavior.

Run `run_design_controls.py --reference-producer PRODUCER --reference-source SOURCE
--output FRESH_DIRECTORY` before the ordinary installation build. It checks all
shared modules, O0/O2, the narrower-host fallback, 150 frozen planner cases and
529 frozen identity-inventory cases, plus signed rank/select and demand probes.
The original oracle bodies and their source hashes are in `design-controls`.
The runner rejects a stale canonical builtin source identity before compiling;
the normal installation subsequently verifies exact fresh regeneration. These
controls also run in the existing bounded Int64/Patricia CI step.
The fallback test selects that code path; it does not emulate a 32-bit ABI.
Full retained graph/P1/P2/P3/file/native controls and fresh compiler-task raw-byte
checks remain required. Small ordinary A/B screens qualify this design change;
they do not establish an isolated data-structure speedup.

The [2026-10-31 design qualification](index-design-results.json) passed the
retained controls, twelve installed direct commands, and the fresh 711/0
compiler task with independent raw-byte equality. The three compiled paths
also exercise 35 explicit rank-view checks, including lazy payloads. The
unchanged Int64 source-admission manifest is followed by a separately pinned
`index-design-migration.json`; it is not rewritten to admit this refactor.

The fixed ABBA/BAAB screen has eight ordinary legs. Geometric wall times were
47.598 seconds for the previous installed compiler and 47.641 seconds for this
candidate (B/A 1.000897, descriptively 0.090% slower). This supports retaining
the design change under its screening rule, but supplies no speedup or
statistical noninferiority claim. No extra samples were added.
