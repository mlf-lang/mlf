# Query graph source transition

The live source snapshot is PR 29 commit
`bdc5db805975c3d77fb3eb93c6199b7452820658`: 135 shared modules and 196
tracked production/build files. It still uses 132 primitives and the unchanged
`mlf-primitive-132-v7` ABI. This is a source-provenance update, not a new
performance measurement or runtime-compatibility claim.

## Preserved evidence

The existing binary132 source manifest, source contract, byte deltas, maintenance
deltas, builtin generation receipt and original benchmark evidence remain
byte-identical. The old builtin receipt and its compiler/generator/source-root
identities describe that historical132 snapshot only. They do not qualify
builtin regeneration on the current135 source.

The new independently pinned loader and `query-graph-migration.json` authenticate
every current file, including unchanged host/runtime inputs, the three added
graph modules and the changed builtin data. Thirteen changed files have
full-input/full-output SHA256-checked, positioned byte deltas. These reconstruct
the exact frozen132 bytes, after which the original contract reconstructs the
historical128 source. This proves identity and byte reconstruction, not semantic
equivalence of the two compilers.

The public bridge remains current135 to historical128: seven added modules need
their actual bytes before registry projection, and eight added paths (including
the binary runtime header) need actual bytes for complete tree roundtrips.
Shared-module and lock transitions retain exact structural checks. Generated
builtin data is authenticated as source here; current exact regeneration remains
the separate ordinary bootstrap build gate.

## Maintenance and controls

Only two previously pinned maintenance entrypoints change: the boundary tests
now expect135 modules and copy both metadata bundles, and the finite driver
records the complete metadata dependency closure. Two additional byte deltas
restore their exact previous132 versions before the unchanged historical chain.
No original golden test or measurement is rebased.

The release metadata gate runs `test_query_graph_migration.py` in normal and
optimized Python modes. It checks full source/registry/tree/lock roundtrips,
actual added bytes, mixed/missing/extra inputs, frozen evidence preservation and
metadata mutation rejection. Existing boundary tests retain real checkout
relocation coverage. Source checks do not replace the actual compiler, F1,
Separate, native or open-artifact runtime suites.

