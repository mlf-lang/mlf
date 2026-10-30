# P1 collection dependency re-audit

The selector fixtures remain literal historical artifacts: neither
`FrozenSelectors.hs` nor `original-selector-excerpts.txt` was regenerated or
edited. The original Map pin is not replaced with the candidate implementation.

The candidate `Bootstrap.Map.unionWith` now folds the smaller input and has
empty-input fast paths. Even though `Bootstrap.Set` has not changed, its union
operations transitively use this changed Map. Sharing either collection module
would make part of the selector oracle depend on the implementation under test.

## Independent dependency layer

- `FrozenSelectorMap.hs` is the complete Map from historical commit
  `af9ea26a2d2d76630a58e82e9e12940a03cfb5f0`, with only its module declaration
  renamed. Reversing that rename must reproduce historical SHA-256
  `d4d9ebfa39a14ae1cbaf48fa9d540eafa7b452aaa3cc73ffc624a34c15417bdb`.
- `FrozenSelectorSet.hs` is that commit's complete Set, with only its module
  declaration renamed and its Map import redirected to `FrozenSelectorMap`.
  Reversing those two edits must reproduce historical SHA-256
  `c2222cc52e2ee750a92d563f8f513ecf4eb60b1afd534b91a37b7c5d5ba6e60f`.
- The runner creates a retained copy of `FrozenSelectors.hs` in its new output
  directory, changing only the two collection imports. It checks the original
  and adapted hashes, and each import replacement must occur exactly once.
  All selector and helper definitions remain byte-for-byte unchanged.
- Both collection modules import the pinned `Bootstrap.Types`; Map and Set
  values therefore retain exactly the candidate's nominal datatype identity.
  The `Interface`, `Entity`, `Role` and `ModuleSpace` constructors continue to
  come from `Bootstrap.Module`, but no candidate selector or collection helper
  is used by the oracle. There is no conversion through candidate functions.
- The harness builds input environments and projects results through the frozen
  collections. Existing noncollection shared pins stay enforced. The reviewed
  candidate Map/Set hashes are separate pins, not oracle dependency substitutions.

Four test modules are compiled against copied, authenticated producer objects:
`FrozenSelectorMap`, `FrozenSelectorSet`, the import-adapted `FrozenSelectors`,
and the harness. No compiler implementation module is rebuilt, and the runner
continues to verify the producer and copied object inventories after execution.

## Coverage and demand scope

The historical 154,072 selector checks, authored expected values, ordered error
checks, and lazy child-enumeration controls remain in place. Another 6,162
collection checks cover all 1,024 pairs of subsets of five distinct ranks, plus
18 explicit lazy-demand/sensitivity controls. For equal ranks the left and
right inputs have different observable key representatives. Independently
written sorted-list expectations check both frozen and candidate `union`,
noncommutative `unionWith`, and Set union, including empty, equal-size and both
unequal-size directions. Each of those six per-pair assertions also checks the
independently computed expected size and uses historical `Map.valid` on the
result tree, including the underlying Set map. This checks every cached subtree
size, key ordering and size-balance invariant rather than accepting correct
ordered enumeration from a malformed tree. Reverse-ordered right input adds
different tree shapes.
The demand checks verify lazy stored values, unused combiners, left-biased value
selection and poison sensitivity, using valid map shapes and total comparators.

This does **not** assert arbitrary-bottom equivalence. A multi-key left map
unioned with an empty right map previously rebuilt the left map and could demand
the comparator; the new empty-right fast path returns the map directly and does
not. The existing `bootstrap/tests/MapFolds.emlf` explicitly specifies the new
empty fast-path behavior. Malformed or partially undefined tree internals and
bottom comparators are outside the differential equivalence claim; no old
selector lazy-demand expectation was relaxed to accommodate this difference.

## Cheap integrity regression tests

Run both (also wired into the release checker):

```sh
python -B tools/performance/crate-optimizations/p1/test_oracle_authentication.py
python -B -O tools/performance/crate-optimizations/p1/test_oracle_authentication.py
```

These check preserved historical hashes and import-only adaptation, and mutate
selector/excerpt/dependency bytes, module inventory, imports and superficial
pins to verify that the independent historical checks still fail closed. They
do not replace the compiled differential against an authenticated O2 producer.

## Balance direction re-audit (2026-10-30)

The candidate changes only the ordering of the two balance bounds, after the unchanged total-size guard. The new manifest entry records the signed-Integer proof and focused controls. FrozenSelectorMap, FrozenSelectorSet, FrozenSelectors and their expected outputs remain unchanged. Their only shared dependencies are still pinned Types, Std and host primitives; candidate Map is never imported into the oracle. Inverse adaptations continue to reproduce the historical hashes. Both the old full selector suite and the new raw-tree/demand controls remain required.
