# Scope materialization and adverse finite families

This supplements the finite closedness study. It is a small Python symbolic
model, not a Haskell evaluator, benchmark, allocation profile or production fix.
`scope_cost_model.py` follows the insertion/balance equations of the pinned
`Bootstrap.Map`; no claim about the rest of Map or machine integer overflow is
made. All generated depths and keys are small finite integers.

## Correcting an easy cost-model mistake

The first `closedness_model.py` uses eager Python frozenset extension. Its
`scope-insert` event records that model's operation, **not** a guaranteed Haskell
Set insertion. The candidate's `closedIn (S.insert ... scope) body` argument is
lazy: a body without variables can finish without inspecting the new scope.

The new recipe model separates `scope-extension-expression` from
`scope-materialized-insert`. Recipes memoize their materialized result when
membership needs it. These are abstract semantic events, not actual closure
allocations, optimized object counts or retained bytes. The model does not
simulate arbitrary bottom, exceptions, compiler transformations or full demand.
Its recipe objects also retain parent links for inspection; this is not a model
of Haskell update-in-place thunk retention or garbage-collector liveness.

## Three families

For D distinct nested binders with Bot bounds:

| Body | D = 64 modeled result | Why it matters |
| --- | --- | --- |
| Bot, no variable use | 64 scope expressions; zero materialized inserts | Eager event counts would overstate Set work. |
| One use of the innermost binder | 64 materialized inserts; 367 insertion key comparisons and 7 lookup key comparisons | Sparse variable use can still force the entire bound-set chain. |
| D uses of the outermost binder | 64 materialized inserts; 367 insertion plus 384 lookup key comparisons; list alternative has 4,096 equality comparisons | Replacing Sets with a naive binder list is not uniformly better. |

These concrete values are results of the specified model and insertion order,
not portable Haskell performance measurements. The original free-variable
reference is kept separate; its events count singleton/union/delete calls and
are **not directly comparable** to tree-node-equation events or allocated bytes.

For the innermost-once family, source inspection also gives a simple contrast:
the original free-variable calculation has one singleton. The innermost delete
removes its sole key; the other D-1 deletes see empty sets, and all unions have
an empty bound side. Thus there is only one key comparison in that particular
reference family, despite D syntactic deletes. It does not follow that overall
runtime is 374 times different: traversal, demand, map nodes, calls and compiler
optimizations have not been measured. No universal winner is selected.

The outer-repeated body is an opaque constructor with D type arguments. Its
closedness is well-defined in the finite model, but this is not a claim that an
actual datatype/kind environment admits that particular constructor arity.

## Validation and limits

Nine tests cover all 720 permutations of six insertion keys (each prefix checks
ordering, cached size, balance and membership), repeated/signed keys, all 888
finite types from the earlier bounded grammar at empty scope, recipe sharing,
the three families, and skipping extension when a forall bound is open.
An independent reviewer rerun is recorded separately when available.

The seven-constructor finite-value property and these insertion tests do not
prove call-site operational equivalence. `CALLSITE-REVIEW.md` records a separate
static check of the real guards. Profiling and actual Haskell qualification
remain deferred; original execution quarantine and native A/B pause remain.

Run only the tiny specification suite:

```text
python3 -B -m unittest -v test_scope_cost_model
```
