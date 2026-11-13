# Semantic boundary and implementation review

## Changed operation

The old map action is:

```haskell
\node -> mkNode (mapTag (resolve graph) (tag node)) (binder node) (flag node)
```

The new action returns the same node for GBot/GBotK/GTyCon/GSkolem and executes
the exact old action for every other tag. The caller is still `mapNodes`, which
uses `mapNodeTree` and `strictNode` on each action result. The Graph constructor,
alias map, fresh ID, node-map traversal, and all code outside canonicalize are
byte-identical. No public signature, data constructor, or primitive changes.

## Pure value and demand argument

1. For each selected tag, `mapTag` does not call its resolver, and returns the
   same constructor/payload fields. GBot has no payload. GBotK's kind,
   GTyCon's name/kind, and GSkolem's identity/kind are kept unevaluated by both
   `mapTag` and `forceTag`. GSkolem's identity is a payload, not a structural
   child; this patch does not treat it as an alias endpoint.
2. Old action result demand is `mkNode` followed by `strictNode`: force tag to
   its constructor, then binder to Maybe WHNF, then flag to its constructor.
   New action demand for a selected tag is the case on `tag node`, followed by
   the unchanged map boundary's `strictNode`: the same tag, binder and flag
   sequence. `Just binderIdentity` still does not force binderIdentity. No kind,
   name, or skolem payload equality is introduced.
3. Inspecting the source tag to choose the fallback adds no earlier demand:
   the original `mkNode` immediately forces `mapTag`, which immediately cases on
   that same tag. The fallback then runs exactly the old expression.
4. `mapNodeTree` still traverses raw IntMapBin left and then right, applies the
   same `IM.tip` at each tip, and copies the same count/prefix fields. It does
   not enumerate, rebuild from sorted keys, consult routing guards, or assume
   well-formed public map constructors. Forged shape, routing, duplicate keys,
   and lazy count/prefix values take the same traversal, including the same
   poisoned subtree/key ordering. The same `mkGraph` forces map roots and fresh
   counter after the node mapping.
5. Neither graph validation is removed or reordered. All endpoint admission,
   first-order, rebind dense/sparse, parent placement, permission, protected
   variable and merge checks are unchanged. Direct canonicalize has no Either
   errors to reorder; its host demand boundaries remain part of the contract.
   For public unify, this preserves the intended pure graph/error observations
   without treating successful validation as an opaque reusable certificate.

This is a source-level semantic argument under the existing call-by-need
primitives, not executed proof, a GHC Core proof, or a claim of identical
allocation, sharing identity, finalizer/weak-reference behavior, resource
limits, asynchronous exception timing, or retained-space behavior. Changing
allocation is the point; operational correctness controls remain necessary.

## Review of alternatives deliberately excluded

- Dense rebind's old/new node arrays represent different graphs. Old/raised
  binders and permission views likewise are not generally interchangeable.
  Existing `raisedDensePermissions` already checks flexible binding edges
  before sharing its old view. No second cache is stacked on it.
- The dense colours, grafted, and permission memo arrays have different initial
  values/lifetimes. Reuse would require explicit reset/lifetime proof and could
  change public direct-helper behavior or error order; not part of this patch.
- Sparse rebind builds classes, structural parents, candidates, dependencies,
  old/raised permissions from distinct views. It cannot simply share the input
  validation's binding tree. No sparse permission rewrite is attempted.
- `canonicalize` cannot return the original Graph just because aliases are
  absent: it still has strict node-field/map traversal duties for public
  host-constructed values. The candidate does not add this guard.
- Whole-tag or child-list equality would introduce demand, particularly for
  GCon names and lazy children. Even individually defensible unchanged-child
  checks would be a second experiment, so all structural tags remain unchanged.
- No changes to already-specialized checkedFirstOrder, no hashes used as
  equivalence/proof, no ABI changes, global scratch, new primitives, or locks.

## Cost and rejection criteria

The source no longer requests reconstruction of selected Node values; GBotK,
GTyCon and GSkolem also no longer request reconstruction of their tag record in
this action. This is not an object count after compiler optimization. The map
spine is still rebuilt, every original demand remains, and the added case can
cost CPU. Leaf frequency and canonicalize's share of the measured interval
have not been measured. An ordinary neutral/regressive result is a reason to
reject this candidate, not to add cases or adjust the fixed sample plan until
it wins. If rejected, the narrower next diagnostic is to separate canonicalize
from dense/sparse rebind and then dense loading/placing/raising/permissions,
with source-token/demand/cleanup controls maintained independently.
