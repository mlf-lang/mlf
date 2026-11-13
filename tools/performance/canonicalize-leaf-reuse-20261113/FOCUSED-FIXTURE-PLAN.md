# Focused observations required before promotion

**This is a test plan, not a claim that these cases have been run.**
The separate public G.unify fixture must still run unchanged against both
producers. Add these observations in an isolated fixture using
`CanonicalizeReference.canonicalizeBefore` versus `G.canonicalize`. Do not
silently substitute this direct-helper comparison for public-unify tests.
The old reference delegates only to byte-identical production helpers.

## Total finite values

- Each optimized tag: GBot, GBotK Star, GBotK (KArrow Star Star), GTyCon with
  nonempty name/higher kind, and GSkolem with a nontrivial identity/kind. Use
  Nothing and Just binders, Flexible and Rigid flags, and unrelated alias maps.
  In particular a GSkolem payload that is also an alias key must not resolve.
- Mixed maps containing all eight GTag constructors. Include real alias chains
  for GArr/GTyApp/GGen/GCon children so the unchanged fallback is exercised.
  Compare complete nodes, tags/payloads, aliases and fresh counter, not hashes.
- Public unify, valid Gen-rooted dense and sparse/signed graphs, empty/self and
  real merge equations, including GBotK/GTyCon/GSkolem leaves. Retain exact
  output/error/permission checks from the generic fixture. Input validation
  may force kinds that direct canonicalize intentionally leaves lazy.

## Ordered partial-host observations

Use distinct custom synchronous Sentinel exceptions, never infinite loops or
call-stack-dependent ErrorCall strings. Do not catch asynchronous cancellation.
Observe Graph WHNF, fresh counter, chosen Node/tag constructor, and only then
force the selected payload. Run each observation afresh for old and candidate;
a previous full rendering must not pre-force the intended boundary.

- GBotK kind; GTyCon name and kind independently; GSkolem identity and kind
  independently: Graph/tag WHNF succeeds and explicit payload demand throws
  exactly its sentinel. KArrow partial domain/codomain should likewise remain
  deferred until inspected. Do not serialize all fields before these probes.
- Every leaf's binder WHNF poison must throw during canonicalize. A flag poison
  is demanded only after a nonpoisoned binder. With both poisoned, binder wins.
  With tag and binder poisoned, tag wins. A `Just` with poisoned identity is
  allowed to reach Graph WHNF, then fails only on binder payload observation.
- Unchanged fallback: partial GCon name, argument-list spine, and argument
  element; unused alias values; GArr/GTyApp/GGen child poison/alias demand.
  These controls guard against accidentally making the entire node deep strict.
- Node-map poison precedes alias-map-root and fresh-counter poison. Aliases'
  values remain lazy unless an actual structural child resolves through them.

## Public forged-map observations

Construct IntMap/IntMapTree directly, not through fromList or a repairing map
builder. Compare the raw output tree shape as well as logical graph values:
IntMapNil/Tip/Bin, keys, stored counts, prefixes, and left/right branch order.

- Deliberately invalid routing prefix with otherwise finite leaf nodes; signed
  branching with physical left/right order not equal to sorted-key order;
  duplicate tips; bogus stored counts; Nil child under Bin.
- Poisoned left and right subtree values with different sentinels must retain
  raw left-before-right map traversal. Repeat for branch prefixes/counts left
  lazy at Graph WHNF, demanded only by explicit raw-tree inspection.
- At a Tip, poison the node and key separately/together: node strictness occurs
  before IM.tip's key force. Require the same sentinel for both implementations.
- Keep invalid public-unify route/error-priority tests as a separate check; do
  not infer canonicalize behavior from graphs the validator rejects earlier.

## Acceptance

Require exact equality of fully forced actual observation payloads, all declared
case IDs in order exactly once, expected sentinel identity at the stated demand
boundary, exit 0 and complete summary. Record failed or unrun cases honestly.
Expected payloads for finite cases should be independently authored where
possible; direct reference equality is an additional control, not license to
bless a mis-specified expected result. Successful focused tests still do not
prove all infinite/partial inputs, retained space, or async timing equivalent.
