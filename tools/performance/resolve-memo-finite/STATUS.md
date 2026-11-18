# Invocation-local canonical resolution memo candidate

UNQUALIFIED research candidate. Main fc300bc9 remains unchanged. No performance
claim. Pure source transformer is pinned to original Graph Git blob
380d29e7b951da022b49517237d74df2ecd3ee3a. Original DenseValidation constructor and
all existing dense helper functions remain unchanged; validateDense alone uses a
fresh one-cell IntMap memo and privately suffixed versions of nine dense helpers.
Only existing strict resolver consumers (edge child, structural DFS, direct-child
predicate) use cached successful terminal IDs. Full validation, parent-dependent
edge gates, prepasses, kind/occurs/binder rules remain. Sparse path unchanged.
No cache survives a call or Graph mutation. No path compression/cycle shortcut.

Finite gate: 24 cases at O0 and O2, original validator plus hand-authored outcomes;
96 sidecars must match. Includes repeated/multi-hop aliases, cached child under a
failing different parent, used/unused/earlier-error-masked link poison, unreachable
alias cycles, sparse fallback, existing payload poison/error-order controls.
Reachable cycles get a separate bounded one-second nontermination smoke check on
both sides, with kill/reap verification. This is not a general divergence proof.

Next, if finite controls qualify, independent review and paired unchanged-output
main workload measurement are required. Extra memo map allocation/lookups may be
slower than uncached resolution; discard on regression. No cross-call reuse or
native A/B fixed-point work is authorized by this candidate.
