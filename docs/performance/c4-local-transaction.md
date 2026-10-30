# C4: operation-local prepared fallback transaction

## Integration scope

This ports the two algorithm files from research commit
`6be0c51f93ae8f31e4048aebe4c9a9bba3ce0a88` (parent P3
`875e483de49655030c4ffba1995b60610a50273a`) onto PR #25's
`d3906cbaefc9d5965ee59bb87b6be8f730ec3204`. It does not merge the divergent
research branch history, stack C1/C2/C3, modify the sealed A1 implementation,
change fingerprint/serialization algorithms, or cache target inference.

The current Graph, Solver and Constraint originals equal P3 byte-for-byte.
Current host/library integration is nevertheless different. In particular,
generic Map.unionWith and the generated builtin representation changed. C4's
Solver alias/node unions use the unchanged IntMap.union implementation, not
that generic unionWith. The prepared differential is checked under the same
current collections/runtime on both sides. The separate complete historical
P3 algorithm/collection oracle remains untouched in the A1 controls.

## One mechanism and its lifetime

C4 retains the full expanded persistent Graph. For a narrowly admitted
prepared-instantiation fallback it avoids first building the expanded reverse
indexes and subsequently rediscovering the same fresh portion of the local
component. It discovers the old closure from the old equations and all external
old endpoints of fresh child/binder edges, appends the known contiguous fresh
range, and builds the same compact local graph.

Full local unification and both validators, hidden stubs, scope/rigid checks,
canonical equation/error order, and complete projectionChanges remain. Graph
restoration uses the same physical starting tree and update sequence. The
transaction publishes old-node changes and **all** surviving fresh nodes,
including fresh survivors whose payload did not change during local unification.
There is no persistent plan reused after graph/index/alias/counter changes.
Unknown shapes and payload-demand barriers take the complete old fallback.

The new entry is used only after the actual preparation barrier in
`Constraint.flushGeneration` and `Constraint.solvePrepared`. Existing public
single-step APIs retain their old path. The sealed A1 `CrateSession` has its own
solver loop and is not rerouted here. Thus this is not a claim that every
instantiation in the current compiler executes C4.

## Exact comparison contract

The original C4 contract already permitted only the two reverse-index trees and
their bucket trees to rebalance. Graph node trees and payloads, alias trees,
nextId and scope-index trees remain physically identical. Complete ordered
reverse-edge sets are equal and independently enumerated from graph nodes;
BST order, cached sizes, balance, nonempty buckets, full Frozen finish and both
graph validators must also pass. Errors retain exact first-diagnostic bytes.

The relevant legal index readers use ordered enumeration, membership/null,
edge difference and complete audits, not tree shape to choose Graph updates.
The source-level domain is a state reached through actual prepare and the
prepared drivers. This does **not** promise arbitrary raw Solver constructor
observations, forged-state equivalence or unrestricted partial-input semantics.
Finite demand/error/retry/rollback/continuation controls supplement, rather than
replace, that boundary argument.

The A1 current runner's single public `C.solvePrepared` assertion is adapted in
a test-only generated copy to this same already-reviewed C4 comparator.
Inverse byte transformation must recover the original SessionTests exactly.
All other public and private comparisons, original fixture/oracle bytes and
privacy controls remain unchanged. Thirteen extra comparator rejection cases
include malformed self-comparisons; they are not a replacement for the full
existing A1 gate. See its current-source README for the exact adaptation.

## Reviewable controls and reproduction

[The repository control package](../../tools/performance/c4-local-transaction/README.md)
contains the complete pre-C4 core algorithms and independently authored
expectations, rather than pointing to an unavailable external test bundle.
It provides:

- Complete old finite controls: 12,000 validation cases, 5,616 unification
  cases, 400 ID renamings, 28 traces, eight parsed expressions, permission,
  exact-error and rollback boundaries.
- 28 C4-specific fixtures (19 successes, nine expected rejections), physical
  compact graph/equation/scope/stub comparisons and both real prepared drivers.
- 216 fixed nonmonotone ID-layout executions, including sparse and huge-negative
  coordinates. These are executions, not independent random topologies;
  rank-normalized inputs include at least 36 cross-label duplicates.
- Nine two-producer parsed-file controls with independent checking, fresh
  inference, exact outcomes and complete raw checked-byte comparison.
- A separate fixed historical 14-module qualification: unchanged 81-file
  fixture contract and ordered 544-query projection, common independently
  admitted current builtin/dependencies, 544 fresh / zero reused on each side,
  complete raw checked-byte equality and a plain-GHC 14-fresh/56-reused control.
  This finite qualification produces no speedup estimate.

Use fresh output directories, retain failures, and follow the exact parameterized
commands in that README. Ordinary producers must be newly authenticated GHC
9.14.1 `--bootstrap-only --optimization 2` builds. A source-identity token change
alone is not builtin validation: the maintained builder freshly regenerates the
entire split literal byte-for-byte and performs the complete independent builtin
checks. The integration preserves all 74 split term declarations and every
non-identity byte of the target's generated file.

CI adds the explicitly **focused** one-producer graph gate at ordinary O2 and
retains all existing CI jobs, old finite gates and resource bounds. That gate
runs the complete finite graph controls, 28 C4 fixtures and 216 layouts; it does
not claim the local two-producer nine-file or fixed-14 qualification. Its receipts
encode that distinction. Full local verification results are recorded separately
below, rather than relabelling a focused receipt as a full pass.

## Performance evidence boundary

Historical P3/C4 research used six fixed blocks, 12 adjacent pairs and six GHC
controls. Its block-log estimate was 2.9963% faster, with nominal 95% improvement
interval [0.7480%, 5.1937%], nine of 12 faster and both orientations positive.
Order effects and shared-cloud noise remained; the nominal interval is not
familywise coverage over the candidate search. C4 remained about 10.59 times
the GHC endpoint, not the long-term three-times target. A separate diagnostic
observed 2.8068% fewer allocated bytes; that is not a wall-clock speedup claim.

Those numbers describe only the historical exact-P3 inputs and cohort. Current
PR25 additionally contains A1/F1 and other changes and uses different driver
routes. This integration does not claim a measured current-head 3% improvement,
add acceleration percentages, or repeat the historical timing campaign.

## Integration validation record

The final integration evidence summary is added only after the actual local
gates complete. This section is not an assertion that pending native tests or
hosted CI already passed.
