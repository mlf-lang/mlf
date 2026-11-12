# Single repeated-guard removal candidate

`OpenFragment-remove-duplicate-guard.patch` is an **unapplied source candidate**.
It deletes only the second `S.null (T.freeVars ty)` export check in `Open.check`.
The first closure guards in `Check.closedBindingInventory`, independent type
inference, parameter validation, ownership and output construction are retained.
No production file has been edited and no Haskell/compiler test has run.

Why investigate this rather than the new Set predicate? The second guard uses
the identical predicate on the identical immutable types just admitted by the
inventory. It introduces no new correctness fact at the pinned source revision.
The new Set predicate instead has different demand behavior. See `REVIEW.md`
for the branch-by-branch induction and the maintenance boundary.

## Bounded model evidence

Ten pure Python tests pass, independently rerun. The 6,342 generated examples
are small **admission protocols**, not parsed programs, real xMLF types or a
replacement implementation of the checker. They explicitly distinguish:

- producing a successful outer inference result before any delayed inventory
  guard, without claiming all type payloads are in normal form;
- forcing inventory closure guards in outer-to-inner order;
- terminal type errors versus later fragment-shape errors;
- immutable symbolic closure success, failure and modeled bottom;
- unchanged export ordering and unchanged non-repeated observation traces.

For N successful exports the model counts 2N closure probes before the proposed
removal and N after it. This is not a measured compiler cost or speedup.
Two deliberately corrupted producers, one skipping the first guard and one
forging an extra open export after admission, make old and new behavior differ.
Those mutations are **not proposed edits**: they show that the optimization
depends on the producer invariant and loses a fallback if it is later broken.
The current source induction and future regression tests must cover that fact.

There is also a real demand-timing boundary: the repeated guard forces the
flattened `owned` list spine. The first guards have traversed each finite entry
segment, but may still leave `append` thunks in the combined result. Deleting
the second guard can defer that spine work to ownership or another consumer.
The model uses eager Python tuple concatenation and does **not** model this
Haskell allocation/retention difference. Same modeled protocol traces do not
prove identical host demand, heap behavior or performance.

## Patch byte check

`verify_candidate_patch.py` reads two pinned original files and the patch,
compares SHA-256 values and reconstructs the exact one-line unified diff in
memory. It writes no source. `PATCH-CHECK.json` records the result and candidate
text digest. This is not a compiler, parser, semantic or artifact check.
Changed source hashes deliberately require a fresh review, not automatic patch
adaptation or removal of more guards.

## Tiny checks and deferred gate

From this study directory, the protocol suite needs only Python's standard
library:

```text
python3 -B -m unittest -v test_admission_model
```

Before integration, run the genuine Haskell checker/fragment regressions,
partial-host demand controls, error/shape/ownership checks and exact artifact
comparisons under a separately admitted setup. Then attribute any measured
allocation and end-to-end change. Native generation A/B remains outside this
study, and the unresolved original execution quarantine is not bypassed.
