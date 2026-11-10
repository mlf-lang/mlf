# R3 prepared fallback membership bitmap (parked, unvalidated)

Baseline: f9bdb40a659bfdff4cbb782d438afbb0417dd2e1. The only production owner is
`libraries/mlf-inference/Bootstrap/Graph/Solver.hs`. This candidate has not been
compiled or run. No performance or qualification result is claimed.

Astra stopped this direction before any CPU gate because the precise P1
direct lookup coverage ceiling is only 0.649%, not the 5.09% global lookup
share, and bitmap insertion and retention can offset its benefit. The production
Solver has been restored to exact f9 bytes. The untouched candidate is retained
in `candidate.patch` for research provenance only, not in an active queue.
`Main.hs` and `run_controls.py` are uncompiled review drafts. The harness requires
the candidate owner SHA and therefore refuses the restored production source.
Do not run it or apply the patch without a new scheduling decision.

## Mechanism and scope

The current canonical component visitor already reads each newly discovered
Graph node once and retains it. Its `IntMap` membership test is repeated for
all pending edges, including already discovered nodes. The parked candidate prepared fallback
keeps a separate `IntSet` bitmap of discovered keys, using the existing
64-bit bitmap collection implementation for membership. The original Node map
and its insertion order are retained. This adds a bitmap insertion for each
new key, so a benefit is a hypothesis, not an inference from profile shares.

Only `preparedFallbackProjection` enters the new helper, starting both views
empty. On every nonempty pending step, the retained map root is forced at the original member boundary, avoiding a deferred insertion
chain. A hit reads neither Graph nor Node payload. A Gen stops traversal before
its root/binder/reverse-index payloads. Edge order, missing-node errors, scope
projection, unifier checks, hidden-root checks and restoration are unchanged.
The old visitor and `unifyDistinct` remain unchanged. The helper does not admit
an externally supplied mismatched bitmap/map pair or certify a mutated Solver.

## Pending controls and measurement

`Main.hs` compares directly with an exact complete f9 Solver, renamed only to
`R3FrozenSolver` by a source-pinned harness. It covers physical map/set layouts,
signed Int64 dense/sparse/wide/end-point coordinates, cyclic direct traversals,
first missing-node order, Gen/seen/unused-field/first-child demand, and complete
prepared/projection/fallback outcomes with immutable retry. Direct malformed
helper fixtures are not represented as valid prepared states.

The maintained current-ABI graph suite under `tools/performance/patricia`
retains the independently frozen C4/public/session/admission and 216 layout
controls. It must be used through its current Int64/Patricia adapters; the old
unadapted Integer controls are not the current compiler contract. Do not relax
its source/producer authentication to admit this candidate. A dedicated narrow
owner-control overlay can be diagnostic only; a full ordinary candidate build
and applicable maintained qualification remain separate gates.

Before local owner timing: independent review; exact before/after source and
object pins; O0/O2 differential and demand controls with ordinary flags. A small
ordinary owner comparison would be the decision gate if this direction were
reopened, not a full compiler build. Full producer qualification and identical full 90-module workload and
artifacts are required only if this candidate merits further scheduling.
Scheduling is exclusive. No native A/B/fixed point, no extra profile run, no legacy R1 work.
The checked baseline currently does not complete within the old 600-second
limit, so no ordinary end-to-end benefit is established by bounded prefixes.

## Profile coverage ceiling

P1 profile SHA256: f83eee5c87165f847b7fd9b938ed9753a5ba7690ea6557b63b4391a53ae86e91.
In the 89,395-tick bounded diagnostic, the union of subtrees with both
preparedFallbackProjection and componentCanonicalNodesVisit ancestors has
1,589 self ticks (1.778%) and 1,324,692,576 allocation bytes. Within it, all
IntMap.lookupTree variants sum to 580 self ticks (0.649%, 0.580 sampled seconds)
and 70,926,544 allocation bytes. This includes original Graph and reverse-index
lookups, so the membership-only coverage is smaller and not separately known.
The global 5.09% specialized lookup share is not this candidate's opportunity.
These profiling shares are not ordinary performance estimates or additive
percentages, and GC attribution is separate. The new bitmap inserts and its
extra retained tree can eliminate any small benefit. No complete producer
build should be scheduled before a useful small ordinary result.
