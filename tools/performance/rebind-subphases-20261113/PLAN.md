# Next diagnostic: canonicalization versus dense/sparse rebinding

**Static plan only. No production/mirror edits, compiler, profile, guard, lock,
or benchmark launched. No r19 partial sample results were inspected.** All
source locations refer to frozen f9bdb40a659bfdff4cbb782d438afbb0417dd2e1 Graph.hs.

## What r17 does and does not establish

The finalized r17 verification records 61,005,709,048 source-demand allocated
bytes. SOLVE / `SOLVER_UNIFY_REBIND` is 8,830,980,432 B, about 14.4757% of that
total. Its actual annotated expression is **`rebind before (canonicalize
skeleton)`**, not an already-canonicalized graph passed to a rebind-only timer.
The lazy canonicalize argument is deliberately included. That cell does not
separate canonicalize, dense/sparse routing, scratch initialization, placement,
permissions, or final graph construction. It is not exclusive ordinary CPU,
peak-live memory, or bytes that can be saved. Source/profile pins are in
`planned-sites.json`; the formal verification was read directly in this review.

## Minimum next split: three SCC prefixes, no eager boundary

Retain the existing REBIND label and all r17 labels. Add only these three
prefixes in a new diagnostic mirror, using `planned-sites.json` exact anchors:

| f9 line | Label | Expression being annotated |
|---|---|---|
|1261|`SOLVER_UNIFY_CANONICALIZE`|existing `(canonicalize skeleton)` argument|
|1476|`SOLVER_UNIFY_REBIND_SPARSE`|existing sparse case-arm `rebindSparse old skeleton`|
|1477|`SOLVER_UNIFY_REBIND_DENSE`|existing dense case-arm `rebindDense old skeleton low high`|

Do **not** insert seq/deepseq, force the Graph first, introduce strict lets,
freeze arrays, change branch choice, or move `runST`/ST binds. Branch labels
wrap the existing result expressions, not merely construction of an ST action.
The dense arm already calls `rebindDense` -> `runST (denseRebinding ...)` at
1507–1510; the sparse arm directly calls the pure implementation at 2040–2102.
These are the smallest three sites that separate the requested alternatives
while preserving current syntactic demand boundaries. Removing the three
prefix strings must recover exact r17 bytes, then the existing r17 inverse
must recover exact f9. Token identity alone is not an operational equivalence
proof: SCCs may alter optimization, allocation/sharing, residency, or async
behavior. Requalify the new producer rather than relying on the inverse alone.

### Readout, without double-counting

Extend the strict fine-site inventory to 14 sites / 13 labels / 41 total edits.
The unchanged nearest-fine-after-deepest-coarse rule partitions each raw stack
node's **self** allocation once. Present four disjoint rebind-family cells:

- CANONICALIZE: canonicalize-labelled source demand, including delayed payload
  work attributed there. Not necessarily a contiguous elapsed interval.
- REBIND_DENSE and REBIND_SPARSE: their nearest-label source demand, excluding
  any allocations whose nearest fine label is CANONICALIZE.
- REBIND residual: dispatch (`denseBounds old`, 1475), result/thunk work outside
  the new branch sites, and other work the profile actually leaves there.

Never sum inclusive CCS totals. Add the four cells only as a parallel family
rollup, not extra allocation. Preserve all coarse contexts and coarse resets;
local-unify family expands from five to eight labels. Verify every coarse row,
site partition and global self total against the unchanged strict coarse parser.
Report raw route-labelled stack evidence rather than inferring route call
counts from entries, nodes or allocation size. Canonicalize thunks may retain
their creation stack instead of their forcing branch: do not force every
canonicalize byte into a dense/sparse subcategory if the raw stack cannot say.
Nested/escaped attribution and residuals must remain visible. No equality of
new family bytes to r17's 8,830,980,432 is required or expected.

### Execution sequence for the coordinator, after r19 finishes

1. Freeze this diagnostic decision independently of r19's partial results.
   Start from f9 plus the authenticated r17 overlay, **not** the leaf candidate;
   r19's optimization is a separate variable. Use a fresh source/run directory.
2. Reuse the exact controller, guard, resource limits, ordinary/profiling
   producer provenance, unit-byte control, deferred/source-value-demand
   controls, target three-artifact comparison, and cleanup/lease gates. Follow
   the existing BUILD -> QUALIFY -> PROBE-CONTROLS -> TARGET-QUALIFICATION ->
   ATTRIBUTION chain, with fresh stage-specific admissions. This plan is not
   an admission and does not resume any previous epoch.
3. Extend only insertion metadata and fine-reader/tests for these exact sites:
   unique labels/modules/spans, CAF rejection, missing/unknown labels fail
   closed, new count expectations, exact three-token inverse, nested family
   partition/coarse-reset/conservation cases. Every site must be declared;
   a declared but unobserved sparse route is valid and must remain reported.
4. Reuse the already real 54 direct-canonicalize and 23 public-unify fixtures,
   their exact expected values/partial boundaries and byte-comparison rules.
   The direct fixture's production calls are not relabelled merely to inflate
   coverage; the public fixture exercises both dense and sparse routing.
   Preserve existing actual deferred-demand profiling controls. No new Python
   graph/solver model or regenerated semantic oracle is needed.
5. Authenticate real raw profiles and source locations, rerun strict readers,
   preserve unit evidence and complete cleanup, then publish all four cells
   with residuals. Only then select the next production candidate or narrower
   diagnostic. Do not use profiled ticks as ordinary-exclusive CPU or fit
   r19's ordinary performance outcome from these allocations.

## Concrete source repetitions, not measured savings

| Location | Static fact | Consequence / boundary |
|---|---|---|
|781–785 vs 1475|`denseBounds` recomputes on the same original graph at input validation and rebind dispatch.|Actual repeated pure query, not a demonstrated large allocation. A lexical shared query inside unify would need helpers preserving public validateGraph/rebind behavior and exact error order. Measure residual before prioritizing.|
|1555–1560|Dense rebind already let-shares `originals = IM.toList (nodes old)` and `remaining = IM.toList (nodes skeleton)`.|Do not claim each use reconstructs these lists. Repeated passes below are over the shared spine.|
|1563–1621; 1869–1912|Dense success traverses originals/remaining for loading, marks, placement, final nodes, raising, permissions and checks; newDensePermissions creates four arrays and a child index.|Distinct computations and old/new views, not redundant validation. Raised permissions already share the old view when every relevant flexible edge agrees.|
|2066 and 2089|Sparse rebind literally repeats `IM.toList (nodes old)` for raisedBinder and permission checking.|Narrow potential follow-up: one lazy local `originals` binding used at both sites, leaving both traversals and order intact. Same pure input, but actual duplicate allocation may be removed by compiler CSE; sharing can change retention. Prioritize only if SPARSE warrants it. `graftedNodes` has another enumeration at 1275 and classesIndex uses keys at 1281; do not widen the first patch to refactor those helpers.|
|1770–1779|For a graft, candidates ends in `ps`; densePlaces traverses candidates, then traverses `ps` again. On successful internally fresh state, the latter finds placed nodes.|A genuine repeat of that list walk/read, not proof it can be removed for all exported helpers. DenseRebinding and ST arrays are public; forged/aliased scratch arrays can violate the fresh-state argument. Do not change densePlace solely on an opaque invariant.|
|78–87; 1625; 2893–2901|The final list goes through `length` before strict node insertion.|Two spine traversals, but length-before-payload demand is a public partial-input contract. Dropping length changes possible error order. Not a free removal.|

The strongest immediately narrow *source* duplicate is sparse's two identical
enumeration expressions; the largest runtime route is still unknown. If DENSE
wins the split, next instrument existing dense action arguments for load,
mark/place, final/raise, and old/raised permission construction/checks, leaving
array initialization and final-result residual explicit. If CANONICALIZE wins,
inspect its exact map/tag/alias demand rather than assuming r19 leaf frequency
or savings. If residual wins, localize denseBounds/result construction first.
Do not stack these additional sites or optimizations into the initial split.
