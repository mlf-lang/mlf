# Independent runtime reference programs

These fixed programs are independent inputs to the maintained differential
tests. They are copied and compiled directly. Current compiler sources are
separately authenticated by their ordinary build receipt and exercised by the
tests; changing current source does not regenerate an oracle.

## Direct source inventory

| Fixed reference | Established input | One-time compile-ready change |
| --- | --- | --- |
| `graph/FrozenGraph.hs`, `FrozenSolver.hs`, `FrozenConstraint.hs` | C4 graph algorithms from `875e483de49655030c4ffba1995b60610a50273a` | Reference graph operations use the collection models below. Reverse-edge insertion and removal operate on set membership. Disjointness checks key membership. |
| `graph/GraphMapModel.hs`, `GraphSetModel.hs` | Standard-library `Data.Map.Lazy` and `Data.Set` over signed `Int64` | `OracleTypes` converts between the finite model and graph fields and checks prefixes, cardinalities and bitmaps with `Data.Bits`. |
| `p123/FrozenSelectors.hs` | The independently retained P1 selector oracle | Use `FrozenSelectorMap` and `FrozenSelectorSet`. |
| `V1FrozenSession.hs` | The pre-validation-reuse session described below | Retain the established rank-view interface adaptation and test module name. |

Unchanged references are reused from their original locations:
`crate-optimizations/p1/FrozenSelectorMap.hs`, `FrozenSelectorSet.hs`,
`crate-optimizations/p3/FrozenPrefix.hs`, and `FrozenInferenceUnit.hs`.
The original source provenance for these inputs is archived at `0704d216`.
The `map-policy` suite owns the separate map-balance references.

The established Patricia preparation is recorded at
`171717ad5bd025ee977d4ca9fd8f93abcbc68612`. The current graph suite uses
the maintained collection models directly and records their bytes in each run.

`controls/` contains ordinary maintained tests, fixtures, and comparison
helpers. In particular, names such as `SessionOracle`, `TransactionOracle`,
and `C4ProjectionOracle` describe comparison helpers, not frozen algorithms.
Their Int64 annotations, Patricia boundary checks, compact-scope comparisons,
and authored expectations are explicit Haskell/JSON source. They have no fixed
SHA admission rule; receipts hash the inputs used by each run. The same applies
to the existing `OracleTypes.hs` bridge and `PatriciaOracleControls.hs`.

## Validation reference

`V1FrozenSession.hs` preserves the reference prepared for the validation-reuse
boundary checks at the same commit. Its source is
`libraries/mlf-crates/Bootstrap/CrateSession.hs` at
`76c6eac4f13ca39ae45590281fe4ced8c07512e8`, whose SHA-256 is
`8900a34bf977eaec0d44948be816ca2b5ddb8955170908e7df8fa93967d179df`.
This is the already established pre-optimization oracle, not a copy of the
current implementation. The existing preparation changes the three
`Map Int Node` signatures to the current rank-view representation, adds the
rank-view import/access, and exposes the reference as `V1FrozenSession`.
The prepared bytes are unchanged. `V1SessionUnderTest` continues to be copied
from the current source with only its module export header changed.

The fixture hashes in `frozen_oracles.py` protect only the fixed reference inputs
listed above.
They do not assert that arbitrary current source bytes are equivalent to an
older implementation. Compiler behavior is checked by running the existing
authored cases and comparing against these references.
