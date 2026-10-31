# Int64 Patricia collection qualification

The compiler now uses a lazy IntMap Patricia tree and a bitmap-leaf IntSet,
ported from `containers-0.8.1`. `provenance.json` pins the downloaded archive and
upstream sources; the complete BSD attribution is in
`tools/release/licenses/containers-0.8.1.txt`. Cached cardinalities retain the
previous constant-time `size` and rank/select operations. Signed enumeration,
left/right union bias, and lazy map payloads are part of the contract.

This is also an explicit public representation migration. The former balanced
`Map Int` tree is no longer the physical representation of IntMap or IntSet.
The tests do not describe the old BST shape contract as unchanged.

## Retained independent controls

`run_controls.py` checks both optimization levels against independent
`Data.IntMap`/`Data.IntSet` models and an independent bit/routing model. The
kind-routing controls include malformed five-node prefix trees which would
have passed a sorted-leaf check while routing lookups incorrectly.

`run_integrated.py` authenticates an ordinary O2 producer and copies its
objects. Only test modules are compiled; pre-existing production objects must
remain byte-identical. Select `p123`, `map-balance`, `graph`, or `validation`.
`--source` identifies an installed producer's owned source snapshot. It is not
a way to skip source authentication.

Original oracle files and manifests are retained. `legacy-controls-pins.json`
anchors the additional original finite controls to `3b566893`. Test-only
adaptations save a byte-exact reversible diff. Host control annotations change
from `Integer` to `Int64`; string fixtures remain literal. All original rows
remain, including oversized literals, which now wrap and can duplicate other
rows. This does not claim the old arbitrary-precision contract.

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
The validation-reuse baseline is reconstructed from its pinned original
source contract after inversely replacing exactly three collection type
signatures. Its algorithm body remains unchanged.

The P3 gate exposed an Int64 boundary bug: composing an encoding with a large
positive seed can differ from the original recurrence because multiplication
wraps before the first remainder. `appendDatatypeEncoding` now admits only
canonical residues to composition. The gate keeps all 922 old checks and adds
seven full-width seed checks.

`run_fingerprint.py` retains the frozen F1 control bodies, both O0/O2 host
builds, exact expected output and actual Separate proof.
Command transport uses the existing resource guard. The obsolete Integer-to-Int64
narrowing RULES are intentionally retired. Both Probe and actual Separate
workers must now contain direct Int64 arithmetic, with zero retired-rule firings. Type-only
copies use independent `Data.Int.Int64` arithmetic; 30 full-width pairs are
added per optimization level. An old 2^1024 noncanonical divergence seed is
explicitly replaced with -1, since the old value wraps to zero. The unmatched
Core obligation now requires signed Int64 primitive operations and no fusion,
rather than the obsolete arbitrary-Integer operations.

`run_file_controls.py` retains all nine authored file cases. For local
qualification its baseline is the independently qualified Int64 balanced-map
producer, and both candidate Crate and CrateSession routes must agree in raw
bytes, errors, types and fresh-group inventory. Across the intentional numeric
ABI change, the old P3 whole-artifact bytes are not a valid raw oracle; its
frozen semantic algorithms remain in the suites above.

## Performance

Correctness runs and instrumentation are not performance samples. A/B timing
uses the existing `process-spawn/compare.py`, a fixed fresh workload, raw-byte
reference checks, and a schedule frozen before sampling. Successful finite
controls alone do not imply a speedup. Sparse lookup and sorted construction
can regress even when a compiler task improves; retain those observations.
