# Owned depth cursor: finite candidate, not qualified
Baseline fc300. This is NOT OwnedDenseValidation / STUArray and NOT the old
dense-place second-parent-pass shortcut. The old patch only skipped a repeated
densePlaces ps when graft != 0; this patch retains both traversals.

Only denseRebinding's fresh independent arrays dispatch to a cloned Owned
placement chain. Original densePlace/Places/Entries/Common/Many/Fold remain
byte-identical. New functions are exported by the module: privacy is a CALL
DISCIPLINE, not language access control. They are not generic raw-state APIs.

Induction: colour2 is written only after all candidate/structural parents finish;
tree and strict depths are assigned parent depth + 1, or zero at a root. Only
Owned recursion writes these freshly allocated distinct arrays. A completed
ancestor is not rewritten. Thus a successful denseParent step changes depth by
exactly one. Its previous writes already forced the Int; skipping the repeated
array read cannot skip a new user payload evaluation in this owned state.
First call retains equal-ID short circuit, then reads a depth before b depth.
Each subsequent branch retains original denseParent left/right order; equal
depths read left parent before right. Separate roots retain the original no-common-
ancestor Left at the same first missing parent. Equality is checked before
decremented depths are demanded. No Node/Kind/name payload is read by the cursor.

Depth overflow: colour1 rejects dependency cycles; any successful parent chain
contains distinct allocated live identities, at most count. count has already
passed existing allocation size bounds, at most maxInt64 quot8 for this GHC
host. Thus completed depth is between 0 and count-1, and subtraction occurs
only following successful Just parent with positive true depth. This proof
does NOT cover manually forged/aliased raw DenseRebinding; those old entry
points are unchanged and their existing alias tests are retained.

Cost: one pair reads two initial depths; subsequent climb steps reuse them.
Old O(h) depth reads become O(1), but parent traversal stays O(h), total
asymptotic LCA time remains O(h). Additional integer cursor arguments/decrements
and DFS cloning can cost code size/register pressure. Profile readDense is not
all LCA. No claimed speedup. Test whole candidate; no third attribution producer.

Focused closure uses unchanged real baseline Graph and Candidate.Graph sharing
Types. 21 cases / 84 files. Total graph results include actual IntMap physical
tree count/prefix/keys/payloads and alias tree, not merely toList. Existing raw
alias, colour and parents-Probe controls stay. Added cursor tests exercise equal
IDs, initial depth Probe, root-parent first-error, signed IDs, uneven depths and
empty/single list short circuits. These are finite coverage, not full qualification.
FAIL is captured in .result without aborting other cases. COMPLETE is not PASS.
Unexpected exception leaves partial artifacts and failure. No fixture was run.

Ordinary closure: 95 baseline homes, Graph overlay only. Focused: 15 homes.
No new primitive, FFI, array representation, sparse dispatch, validator removal,
first-order/restore change or canonical checkout edit. Focused and exact real
raw-product qualification must precede a small ordinary A/C screen.

Core arithmetic simulation also holds under Int64 wrapping: if a completed
child stored parentDepth+1, subtracting one recovers the exact stored parent
depth modulo 2^64. Comparisons therefore use the same values step by step.
The size argument is supplementary, not a replacement for this identity.
Original placement handles missing entries/aliases/failures before reaching
the new LCA boundary; no new graph-validity guard is imposed.

## v2 focused coverage correction
The v1 six-node success fixture did not reach an unequal owned LCA pair. It is
preserved in v1 but replaced here, not treated as sufficient coverage. One real
unify-owned-multihop case merges Bot nodes 8/10 in a 12-node graph, reaching
(6,4) -> (3,2) -> (1,1) in the fresh-owned path. It is Bot/Bot merging, not a
non-Bottom graft. The original six-node input remains for generalization error.
The candidate algorithm bytes are unchanged. The 21-case/84-file matrix remains
finite O2 coverage; signed raw LCA is not real signed/sparse dispatch coverage.
