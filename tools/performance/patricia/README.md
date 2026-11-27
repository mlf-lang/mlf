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

The [oracle notes](oracles/README.md) identify the reference algorithms and
the maintained collection models used by the integrated suites.

Private graph checks still need a test-only view of the current
`Bootstrap.CrateSession`. The small header lexer changes its module name and
removes the export restriction, preserving every body byte. Export order,
comments, and whitespace are accepted. The same helper serves the retained C3
checks; actual public-export rejection tests continue to compile against the
ordinary production interfaces.

Historical adapters, `legacy-controls-pins.json`, and source migration manifests
have been retired from the current tree. Their exact sources and old reports
remain available in Git at `496dcae024cae1a93096d9bdb9d6b93e57359dc0` (including
the earlier `171717ad5bd025ee977d4ca9fd8f93abcbc68612` preparation). Routine
controls use the direct fixtures and the actual validation and binary-writer
executions below. They do not replay source projections or inverse diff ledgers.

Map maintenance uses the existing `map-policy` framework entry. That suite
checks contents, balance, cached counts, demand/error order, and the intentional
step-21 shape difference from the old Map. The obsolete integrated `map-balance`
group required the entire current 400-step trace to keep the historical tree
shape and has been retired. Its original runner and source-migration proof
can be inspected in Git at `496dcae024cae1a93096d9bdb9d6b93e57359dc0`.

All retained finite rows remain, including oversized literals which wrap under
Int64 and can duplicate other rows. This does not claim the former arbitrary
precision arithmetic contract.

The graph controls use `Data.Map.Lazy` and `Data.Set` with full-width `Int64`
keys. `OracleTypes.hs` checks finite Patricia spines with `Data.Bits`, reads
their entries and independently encodes the model's results into graph fields.
It also supplies a balanced-tree view for graph algorithms that consume ranks
and ordered projections. All conversions preserve lazy map values.
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

P2 compares the current scalar and block fingerprints against a two-residue
reference using fixed digests, Unicode and block boundaries, signed seeds, and
deterministic generated strings. The binary writer tests exercise publication,
corrupt files, and both supported text and binary reads. The separate summary
controls compare serialized text and pooled chunk digests to the same reference.

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

`file_cases.py` executes the authored file cases through an ordinary function
with explicit selection. `controls/files/FileControls.hs` and
`fixtures/file-cases.json` contain the directly compiled test and its handwritten
expectations. Each receipt records the maintained runner/control bytes used in
that run; no historical Python function extraction or current-source hash
allowlist is involved.

The independent reader/schema fixtures live in `oracles/file-format`. They were
extracted once from `8c4556416023ac727e3fb2294070358a3dae8d9e`; normal runs load
them directly and work without Git history. The typed reader has one explicit
`primitive_max` parameter: own artifacts and linked terms keep the original
0..131 domain, while dependency declarations use 0..136. The dependency entry
point also checks the exact Prelude identities of codes 132..136, their reverse
name-to-code association and per-container uniqueness. Unknown codes, changed
owners/names, malformed structures and noncanonical/trailing bytes remain
errors. There is no intermediate 133-source adapter or inverse text proof.
Fixture hashes protect only these fixed independent reference inputs. The
origin and the small interface change are documented in
[`oracles/file-format/README.md`](oracles/file-format/README.md).

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
529 identity-inventory cases, plus signed rank/select and demand probes.
The planner reference and the identity visitor live in `design-controls`.
The visitor collects identifiers in `Data.Set Int64` and compares their
signed enumeration and exception behavior to the compiler's inventory.
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
historical source-admission and `index-design-migration.json` proofs are
archived in Git at `496dcae024cae1a93096d9bdb9d6b93e57359dc0`; they are not
current qualification gates. The retained result file records that dated run.

The fixed ABBA/BAAB screen has eight ordinary legs. Geometric wall times were
47.598 seconds for the previous installed compiler and 47.641 seconds for this
candidate (B/A 1.000897, descriptively 0.090% slower). This supports retaining
the design change under its screening rule, but supplies no speedup or
statistical noninferiority claim. No extra samples were added.
