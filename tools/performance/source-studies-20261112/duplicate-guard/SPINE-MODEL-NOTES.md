# Lazy append observation model

This is a small Python demand-event model, not Haskell execution, a heap model,
or a performance result. It addresses the previous eager-tuple model's blind
spot: removing the repeated guard can defer flattening the admitted inventory.

## Compared variants

| Variant | Before Either Right WHNF | Repeated closure probes |
| --- | --- | --- |
| Original guard | Demand the complete owned list spine | One per export |
| Delete-only candidate | May leave flattened append spine delayed | None |
| Spine-only candidate | Demand the complete owned list spine | None |
| Weak negative control, `seq owned` | Demand at most the first available constructor | None |

The spine-only source candidate uses `seq (all (\_ -> True) owned)` around the
final Right expression. It is a separate unapplied patch, not an amendment to
or silent replacement of the earlier delete-only experiment. Full traversal of
the spine does not force arbitrary element payloads or establish type validity.

## What is modeled

Each admitted source chunk is a lazy list of shared entry-pair thunks. The first
closure guards demand the chunks and the pairs needed by their symbolic type
predicates. Each pair still contains a separately lazy name payload. `append`
constructs a separate flattened spine while preserving those same pairs.
Consequently, a subsequent head-pair observation does not mistakenly count an
entirely new field evaluation that the first guard already performed.

The test session distinguishes these observations in order:

1. No observation of the check expression.
2. The outer Either constructor in weak head normal form (WHNF).
3. The contained Fragment constructor in WHNF.
4. The owned list's first constructor and first pair.
5. Its complete list spine.
6. An optional name-payload demand, which can still fail after all spine work.

For four source chunks of three closed entries each, the model constructs 12
flattened cons cells before Either WHNF in both original and spine-only modes.
Delete-only constructs zero then, one on the first owned constructor demand,
and 12 after complete traversal. These are **symbolic cons events**, not real
allocations, retained bytes, or claims about optimizer behavior.

## Tests and boundaries

Twelve pure tests cover 259 bounded chunk protocols across original, delete
and spine-only modes; multiple observation points; shared pair/spine behavior;
ignored partial name payloads; failed first closure guards and source tails;
and negative controls outside the admitted-inventory invariant. An unadmitted
bad head can pass spine-only traversal while failing a closure predicate. A raw
partial tail also demonstrates why forcing only the first list constructor is
not sufficient. These synthetic invalid raw values are not alleged reachable
outputs of the current successful inventory producer.

The earlier `admission_model.py` handles two-stage inference/inventory error
ordering. This new model starts with abstract groups at the admission stage:
it does not implement type inference, kinds, datatype validation or real FV.
Its thunk forcing memoizes finite modeled results/errors, not arbitrary Haskell
semantics. It does not model stack limits, asynchronous exceptions, compiler
transformations, thunk update retention, free-name/stamp computations or GC.
Its Python objects retain their computation/parent references; their memory
usage must not be interpreted as Haskell liveness.

Matching the original trace after deleting repeated-predicate events is
evidence about this model only. Actual host tests, fully demanded artifact
comparisons and measured allocation/retention remain required before adopting
either source candidate. No Haskell/compiler or heavy test ran here.

Run the tiny model from this directory:

```text
python3 -B -m unittest -v test_lazy_spine_model
```
