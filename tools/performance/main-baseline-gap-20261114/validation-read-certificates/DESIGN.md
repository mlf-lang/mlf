# One candidate: transaction-local validation read certificates

## Proposed boundary, not an implemented Graph optimization

At baseline `fc300bc9fdc389b585cbef0630fc8915d53e89c5`, `Graph.unify` performs:

```text
validateGraph before
  -> checkedFirstOrder equations before
  -> canonicalize skeleton
  -> rebind before canonicalSkeleton
  -> validateGraph rebuilt
```

The single proposed direction is to record **successful validation facts** during the first successful validation, invalidate them using every intervening relevant change, and replay the final validation in its original order. A future shadow keeps the original complete final validator as an oracle. Nothing here removes initial validation, changes unification/rebinding, or includes placement or cross-Solver reuse.

## Identity and dependency contract

A fact belongs to one transaction owner, rule, stable original node identity and all rule arguments. Numeric local ranks, hash equality and coincidental field equality are not ownership certificates. The toy Engine is its transaction namespace; no cache escapes it.

Dependencies must include:
1. Exact fields actually read, including absent cells and alias resolution.
2. Control predicates and short-circuit decisions, including currently unselected alternatives through their controlling fields.
3. Successful subfact dependencies, including cache-hit dependencies.
4. Global or ordered entry premises where relevant: members, roots, existence and the traversal that selects the first error.

Only completed successful facts are published. Errors and cycles are not cached; a successful child of a failed parent may remain. Writes invalidate transitively through reverse dependencies before any old fact can be reused. Recomputing a fact replaces its old dependencies and removes obsolete reverse edges. The model's explicit writes invalidate even when values are equal and never deep-compare fields to decide whether a change matters.

The model replays root/member checks uncached and in order. Fresh evaluation starts without inherited facts but still memoizes within that evaluation. Explicit Poison exceptions are finite controls, not a model of every Haskell bottom.

## Why this is not yet a Graph certificate

The toy semantics has Leaf/Gen/Arrow kinds, aliases and direct-child binder containment. It does **not** implement complete kinds, structural reachability, Euler binding-tree dependencies, dominance, permissions or Graph's arbitrary partial domain.

In particular, Graph's cached child kind does not suppress the per-edge Gen, binder and dominance checks in `denseChild`. A reused toy kind cannot justify skipping those checks. Binding intervals derive from the whole binding tree; unchanged node fields or equal interval numbers alone do not certify containment.

No production write/dependency log currently transports facts through `checkedFirstOrder`, canonicalization and rebinding. Alias redirects, removed representatives, redirected children, binders, flags and global tree changes can invalidate dependencies outside the explicit equation IDs. Computing a whole old/new diff is itself a full scan and may add payload demand; it cannot be hidden as a free log. The certificate must not force previously lazy field values merely to compare them.

This is a specific research direction, not a claim that clean regions are large, cheap to discover or safe to skip.

## Algorithmic inspiration, not transferred proofs

- [A Consistent Semantics of Self-Adjusting Computation](https://arxiv.org/abs/1106.0478), Acar, Blume and Donham, §§2–3: consistency relies on valid, well-formed evaluations and the read traces and change-propagation semantics specified by the paper. The useful lesson is to treat reuse and invalidation as one correctness problem. It does not justify reusing an MLF result merely because visible fields look unchanged.
- [Adapton: Composable, Demand-Driven Incremental Computation](https://matthewhammer.org/adapton/adapton-pldi2014.pdf), §§3–5: inner computations read while outer computations perform writes; changes dirty dependencies before original demand drives recomputation. Its evaluation also accounts for construction, dirtying and retained-state costs. These are obligations for a candidate, not permission to transfer its reported speedups.
- [Incremental Computation with Names, v6](https://arxiv.org/abs/1503.07792v6), §2.4 and Appendix B: names require unambiguous namespaces and consistency between reads, writes and the demanded computation graph. Appendix A discusses the unsoundness risk of losing weak reverse dependencies. This model instead uses a fresh Engine namespace, strong reverse edges and prohibits writes while a fact is active; that is not a complete implementation of the paper.

These primary papers supply algorithmic ideas and assumptions to examine. Their theorems, implementations, benchmark numbers and complexity results are **not** proofs or performance predictions for MLF, this Python model, or lazy ordered Graph validation. No paper performance number is used here.
