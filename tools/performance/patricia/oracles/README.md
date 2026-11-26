# Independent runtime reference programs

These fixed programs are independent inputs to the maintained differential
tests. They are copied and compiled directly. Current compiler sources are
separately authenticated by their ordinary build receipt and exercised by the
tests; changing current source does not regenerate an oracle.

## Direct source inventory

| Fixed reference | Established input | One-time compile-ready change |
| --- | --- | --- |
| `graph/FrozenGraph.hs`, `FrozenSolver.hs`, `FrozenConstraint.hs` | C4 full algorithm modules, originally from `875e483de49655030c4ffba1995b60610a50273a` | Keep the existing frozen module names; import `OracleTypes` and the frozen integer collections. Algorithm bodies are unchanged. |
| `graph/FrozenMap.hs`, `FrozenIntMap.hs`, `FrozenIntSet.hs` | The independently retained A1 collection sources | Import the existing test representation bridge; no algorithm-body change. |
| `p123/FrozenSelectors.hs` | The independently retained P1 selector oracle | Use `FrozenSelectorMap` and `FrozenSelectorSet`. |
| `p123/FrozenFingerprint.hs` | The independently retained P2 fingerprint oracle | Retain its existing GHC rule/unfolding-isolation pragma. |
| `LegacyArtifactWriter.hs` | The pre-binary text writer described below | Expose the old writer as a test module and explicitly reject binary-envelope objects. |
| `V1FrozenSession.hs` | The pre-validation-reuse session described below | Retain the established rank-view interface adaptation and test module name. |

Unchanged references are reused from their original locations:
`crate-optimizations/p1/FrozenSelectorMap.hs`, `FrozenSelectorSet.hs`,
`crate-optimizations/p3/FrozenPrefix.hs`, and `FrozenInferenceUnit.hs`.
Existing historical manifests retain the original source provenance for those
inputs. The original map-balance references are owned by the separate current
`map-policy` suite, not this adapter.

The sources above preserve the final preparation output of the established
Patricia controls at `171717ad5bd025ee977d4ca9fd8f93abcbc68612`. The conversion
was checked once against all 38 prepared Haskell files across graph, P1/P2/P3,
and validation: 36 are byte-identical, and two maintained controls only remove
an extra final blank line for the repository whitespace check. It copied neither candidate outputs nor current
candidate algorithms into the independent references. Ordinary runs now need
only these direct files and their fixture hashes, not Git history or inverse
source-rewrite steps.

`controls/` contains ordinary maintained tests, fixtures, and comparison
helpers. In particular, names such as `SessionOracle`, `TransactionOracle`,
and `C4ProjectionOracle` describe comparison helpers, not frozen algorithms.
Their Int64 annotations, Patricia boundary checks, compact-scope comparisons,
and authored expectations are explicit Haskell/JSON source. They have no fixed
SHA admission rule; receipts hash the inputs used by each run. The same applies
to the existing `OracleTypes.hs` bridge and `PatriciaOracleControls.hs`.

## Writer and validation references

`LegacyArtifactWriter.hs` preserves the writer prepared by
`legacy_controls.prepare_binary_p2` at `171717ad5bd025ee977d4ca9fd8f93abcbc68612`.
Its source is `libraries/mlf-crates/Bootstrap/CrateArtifact.hs` at
`a03307734554b6fe49b0d0b6960064025b3a5b51`, whose SHA-256 is
`88758de08e6ac15b37381b8e78dd5e47d2b50e535794aa3056513fda969fab0a`.
The retained writer declarations hash to
`8a6c58e021d4e687617af3ab309d7aeb0dc3ee9a41c0d7b0aee6ee66b0f4ed40`.
The established preparation exports those declarations under the
`LegacyArtifactWriter` module and explicitly rejects envelope objects. Its
prepared bytes are unchanged. The same P2 run still executes the current
`BinaryP2WriterControls` against the actual public binary writer.

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
