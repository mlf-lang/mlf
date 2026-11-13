# Static review, not execution

The fixture calls the real exported `Bootstrap.Graph.unify` from the linked
producer. It does not copy the algorithm, expose a private API, fabricate a
validation receipt or call a proposed replacement. Public `Graph`/`Node`
constructors are used deliberately (`Bootstrap.Types:322–326`). Graph references
below are to `libraries/mlf-inference/Bootstrap/Graph.hs` at f9.

## Authored finite results

- `unify:1256–1262` validates, performs first-order merging, canonicalizes,
  rebinds, and validates output. Empty/self equations do not merge identities;
  the simple fixtures' common root binders and flexible flags remain unchanged.
- A flexible bottom and `GCon "Int" []`, both bound at the flexible gen root,
  merge to the smaller identity. `tagEquations:1051–1056` selects the non-bottom
  tag; `firstOrderValidated:1221–1242` removes the larger node and inserts its
  alias. The expected graph explicitly contains those nodes, alias and unchanged
  counter, including negative/sparse/extreme identity variants.
- `canonicalize:1138–1144` resolves structural tag references but preserves the
  alias map and counter. The empty-equation alias fixture therefore expects
  `GGen 10` to become `GGen 1` while retaining `10 -> 1`. The alias merge also
  explicitly expects `2 -> 1`.
- The higher-kinded graph has `F :: Star -> Star`, an `Int` argument and
  `GTyApp F Int :: Star`. It exercises the non-simple kind-cache path and merges
  the Star application with a Star bottom. The expected surviving application,
  constructor kinds, binders and `4 -> 3` alias are all explicit.
- `denseBounds:755–770` admits compact spans and rejects a sufficiently sparse
  or signed-overflow span. `MLF.Host.Base:53` makes graph IDs signed Int64. The
  extreme case must be sparse; it deliberately does not call `advanceIdentity`
  or assert a stronger fresh-counter policy than public `G.unify` provides.

## Exact errors and their order

- `checkedFirstOrder:1244–1254` checks every endpoint before merging on the
  simple path and traverses all endpoint kinds before merging on the fallback.
  Both late-missing-endpoint cases expect `missing graph node 99`, not the earlier
  `Int`/`Bool` merge error. The ordinary constructor mismatch is checked separately
  with the exact `tagDescription`/`typeMismatch` text at 1030–1050.
- Kind mismatch text uses `kindDescription:275–287`, **not** `prettyKind`:
  `kind mismatch during unification: KArrow Star Star versus Star`.
- The rigid bottom reaches the separate permission check in
  `denseCheckOriginal:1991–2029`; a known kind does not make it instantiable.
- The binding-cycle graph has one root and a **disconnected** two-node cycle.
  All binder targets exist, but root traversal visits only two of four nodes,
  so `denseValidateEntries:903–927` returns `cyclic binding tree`. It does not
  deliberately launch an unbounded traversal of a reachable malformed cycle.
- The structural self-cycle has a valid binding tree. `denseKind:971–991`
  encounters colour 1 and returns `infinite type (occurs check)`.
- Dense validation checks all binders before traversing kinds; sparse validation
  calls all-node `kindsAt` first (`1022–1029`). The paired bad-kind/missing-binder
  cases consequently have different authored first errors. Reusing a cache must
  not normalize these error orders merely because both graphs are invalid.
- `applyKind:288–299` supplies the exact invalid-Star-application diagnostic.
  `denseKindBinder:950–969` supplies the non-Gen binding-root diagnostic.

These derivations have not been checked by GHC or a baseline run. Any failed
baseline assertion must be investigated before using the fixture for a candidate.

## Partial-host observations

`G.bindE:109–115` must decide input validation before evaluating the following
continuation. Missing-binder input with a poisoned equation list should return
its exact error without triggering the list sentinel. The same list on valid
input should trigger its sentinel while demanding result `Either` WHNF.

The last case uses an unused `GCon` name as a sentinel. Kind/binding validation
inspects children/kinds/binders, while an empty equation list never compares
constructor names. `forceTag:34–42` does not force `GCon` name payloads. Thus the
authored expectation is Right-constructor success, Graph WHNF and fresh-counter
success, followed by the sentinel only on full snapshot rendering. The case
performs those probes in order before the generic output renderer runs.

Sentinels are fixture-owned exception constructors, not error-string matching
that could accidentally accept a compiler failure. Unexpected synchronous
exceptions fail the case. Asynchronous exceptions are rethrown; output does not
claim unchanged interruption timing. Output rendering and failure rendering are
guarded against deferred synchronous exceptions, with a stable fallback detail.

## Independent relink boundary and omissions

The five direct project imports have a 13-module static transitive closure, all
in the existing ordinary 94-module non-Main inventory. `base` covers the new
standard imports; there is no new package dependency. The closure was obtained
from the pinned source headers, not by GHC. Runtime object/interface/toolchain
authentication and actual linking remain the coordinator's responsibility.

The expected finite graphs are built from literal public constructors and the
unchanged IntMap builder. This is an oracle for the intended Graph-only change,
not an independent implementation of IntMap. Full logical graph data is compared,
not raw tree shapes. Exhaustive forged routing trees, alias cycles, all protected
permission combinations, infinite values, heap retention and universal lazy or
async equivalence are outside this focused fixture. No production fix is included.
