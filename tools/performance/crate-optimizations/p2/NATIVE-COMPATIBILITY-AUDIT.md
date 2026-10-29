# P2/P3 native-build compatibility layer

The native standard-library integration after `f6e6788f` changes shared compiler
sources. It does **not** justify refreshing the historical P2/P3 oracle pins.
This later layer records the reviewed edits separately:

- `native-compatibility-manifest.json` pins the current source, an exact line-edit
  transcript, and the historical source reached by reversing that transcript.
- `native_compatibility.py` rejects fuzzy, missing, reordered or changed edits.
  The reconstructed historical bytes must still match the original P2 dependency
  and integrated-P3 pins and the original P3 candidate pins.
- The existing P2 runner still checks the original-vs-P2 outside-region equality
  and P2-vs-P3 fingerprint-region equality (only the previously reviewed comment
  change is permitted). The later additions cannot replace those assertions.
- `FrozenFingerprint.hs`, both P3 `Frozen*.hs` files, original source/excerpts,
  `p2-Separate.hs`, all existing oracle manifests, `candidate.json`, the legacy
  Haskell fixtures and their **2503 / 922** checks are unchanged.
- P3's historical runner is retained byte-for-byte in
  `../p3/historical-run-controls.py.txt`, so its original controls-manifest pin
  remains checked. The executing runners have independent later-layer pins.

## Reviewed source boundary

| Source | Reviewed change and independence boundary |
| --- | --- |
| `Map` | Smaller-map `unionWith` worker; preserve total mapping, left key representative and argument order, but do not assert unchanged demand/evaluation order. P1 freezes the old map/set route separately. P2's old digest does not use the changed union. |
| `Data` | `distinct` now counts a set instead of `nubBy`. Ordinary datatype printers are unchanged. A literal old `distinct` is retained in the supplemental controls for total outcomes and poison/demand checks. A named divergence control records old singleton-bottom success versus the new Map.node key-demand error. The equivalence scope is total parsed names, not all partial values. |
| `Module` | Parser callbacks/fallback loading and prepare/resolve split. Entity/interface/source selector representations are unchanged. No fixture-schema rewrite is necessary. |
| `X.Pretty` | Added chunk encoders only; the ordinary printers used as byte oracles are byte-identical to the historical printers. |
| `X.Checked` | Ordinary `check`, term/type projections and binding projection bodies and the opaque representation are unchanged. New context/composition APIs do not replace the old oracle's ordinary check. |
| `Separate` | Added text-summary/chunk and interface-summary helpers outside the historical P2 fingerprint and P3 pool changes. Exact reversal yields the original integrated-P3 source hash. |
| `CrateArtifact` | Added native summary/linking routes; name-encoding closure and primitive-membership lookup changed inside shared validation. `interfaceFields`, datatype-pool serialization and its framing remain unchanged. This source transcript makes the expanded shared boundary explicit; it is not an independent whole old compiler. |

Parsing, semantic validation and type inference were shared by these controls
before this layer and remain shared. In particular, the old decoder still calls
shared `validateInterface`. These tests establish old digest/byte/error/laziness
controls over their finite inputs, not complete historical semantic validation.
No source edit transcript is used to manufacture expected output.

## Supplemental 1243 controls

`NativeCompatibilityControls.hs` is a separate executable after the unmodified
P2 executable. It tests:

- Text summaries, append/framing, pooled/repeated chunks, scalar lengths and
  canonical seeded states against the **literal pre-P2 indexed recurrence**.
- Every current type, computation and term constructor, including precedence,
  Unicode/NUL strings, bindings, alternatives and datatype contexts: new chunks
  versus unchanged ordinary printers, and summary digest versus the old loop.
- Interface summaries and reuse; pooled fragment summaries against the frozen
  old payload encoder; ordinary and checked fragments and differing header/body
  datatype contexts.
- Old-versus-current `distinct` with literal accepted/duplicate results and
  poisoned names, list spine, list tail and diagnostic labels, including the explicitly different singleton-name demand.
- Ordinary/context checked receipt term/type projections and summary error and
  laziness controls.

The derivation is recorded in the new manifest (16 + 704 + 100 + 18 + 285 + 54 +
20 + 12 + 12 + 4 + 3 + 15 = 1243). New summary APIs promise canonical nonnegative
residues only; the original 2503 controls continue testing signed and arbitrary
large seeds for the public recurrence APIs. No signed-summary claim is added.

The old oracle still compiles with `-fno-enable-rewrite-rules` and
`-fomit-interface-pragmas`; its F1 rewrite dump must remain uncontaminated. Both
runners authenticate the current O2 producer before and after, reject changed
copied producer objects, and check exact test module/output inventories.

Cheap gate (no compiler process):

```sh
python3 -B tools/performance/crate-optimizations/p2/test_native_compatibility.py
python3 -O -B tools/performance/crate-optimizations/p2/test_native_compatibility.py
```

Execution evidence comes from the generated receipts, not this document. No
native-bootstrap execution, full-compiler independence or speedup is claimed.

## Verification (2026-10-29)

On the authenticated cloud GHC **9.14.1**, O2 producer for reviewed source head
`1f4c2f817cc2de2b3b5f3ceb6b35120d7a0976c1`:

- P2's original **2503** controls passed with the old oracle rewrite rules
  disabled and interface pragmas omitted.
- All **1243** supplemental controls passed. In particular, the exact authored
  singleton-name outcomes were executed: old `distinct` returns `Right ()`
  without demanding the name; current `distinct` raises `HostError "distinct
  value"` through `Map.node`'s key demand.
- P3's original **922** controls passed; exactly its three test modules compiled.
- Both producer/input/copy immutability checks passed, and both process-tree
  watchdogs completed without resource-limit termination.
- The **9** cheap static/mutation test methods passed under both Python modes.
- An independent read-only review compared all seven reconstructed historical
  source files against the recorded Git commit; every byte matched.

Retained local receipts are `../pr25-ci-validation/{p2,p3}/receipt.json` and
`../pr25-ci-validation/{p2-guard,p3-guard}/bounded-receipt.json` relative to the
repair checkout. These are finite host controls, not a full CI or speed claim.
