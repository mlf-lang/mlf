# Artifact-binary benchmark source transition

These two fixtures preserve the exact benchmark manifest and Bootstrap.Types
source used before the artifact-binary source transition. The manifest is from
commit 80a8bf4407d159eab8e7735b4b5a65581d172426, where its historical Types pin
no longer matched the newly published live compiler source.

The live manifest now identifies the current source for future benchmark runs.
The existing artifact-binary source contract authenticates the complete current
source inventory and reconstructs the old Types bytes with its pinned delta015.
The release provenance check requires exact archived evidence and permits only
this Types pin change plus the two evidence pins in the live manifest.

Existing benchmark measurements and receipts are unchanged. These checks prove
source identity and reconstruction, not unchanged runtime performance, benchmark
correctness, or a new measurement on the current compiler.

## DeclId successor

The live Types input includes the two primitives introduced on #43 and the
declaration-aware term references. Std compares these references during
inference. `benchmarks/manifest.json` records the current hash of each file.
The source transition in
`tools/performance/artifact-binary/declid-source-migration.json` lists each changed
source SHA on both sides and the new module hashes. The loader checks the entire
live inventory, including unchanged sources, before it applies historical
projections. It gets the predecessor bytes from Git commit
`8c4556416023ac727e3fb2294070358a3dae8d9e`, whose tree is
`c20bd3d8e0cdd7e319dfca77ea0b86cfbf77554d`.

`tools/release/check-benchmark-provenance.sh` runs the current manifest, source
and archive controls. It runs the original graph, writer and builtin-regeneration
suites against their pinned physical predecessor in normal and optimized Python.
Use a checkout containing the pinned Git commit when running these controls.

The commit named below is a source-content checkpoint retained on a published
ref. It anchors the source hashes; it is not the qualified installation. The
final qualified commit differs only in the four audited source-pin and
documentation files. Its fresh install, tests, CI and paired measurements are
recorded separately with the child PR.

At integrated source commit `620225f1a17b177e3d1a93f926c889639e207c88`,
55 of the 196 predecessor paths changed. `Bootstrap.IndexVec` and
`Bootstrap.Resolved` add two paths. The loader checks all 198 physical file
identities and the resulting 137-module registry. The benchmark gate also
reconstructs both historical benchmark dependencies byte for byte.
