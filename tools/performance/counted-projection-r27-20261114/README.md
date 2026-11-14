# r27: lazy counted projection, negative performance result

This is an experimental evidence archive, not a promoted compiler change.
The candidate reuses the already-computed projection count rather than taking
`length originals` later. The compatibility wrapper preserves the old four-field
result and does not explicitly force the new count thunk.

## Result and limits

One fixed ordinary 12-sample ABBAABBAABBA batch, no retries or added samples:
A allocation 60,040,794,280 B; B 60,040,489,688 B (−304,592 B, −0.000507308%).
Wall medians 19.994897665 s versus 20.041906542 s (+0.235104%; 2 pairs faster,
4 slower). No demonstrated practical speedup; not promoted. This is neither a
statistical-significance claim nor a GHC-parity result. Native-generation A/B
fixed-point testing remains paused. Residency is sampled GC liveness, not RSS.

Each sample passed 475 fresh queries, zero reuse, all 14 owners and three raw
artifact byte comparisons (36 total). Qualification covered full builds
(141 modules, 13 links and actual builtin literal), 39 direct cases / 41 public
unify calls per side, 23 separate legacy cases per side and five CLI controls
per side. These finite controls do not establish universal semantic equivalence.
The fixed run had a 600-second total and 180-second child cap; all child guards
finished cleanly. See RESULT.md and samples.json for all observed metrics.

## Reconstructing the source variants

Start from public commit `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1` in a fresh
checkout. Apply `01-input-sharing-baseline.patch` with `git apply --check` then
`git apply`; this produces the Graph.hs part of baseline F25. In a second copy
apply both patches in order; the second changes only Graph/Solver.hs for F27.
Patch applicability and resulting Graph/Solver bytes were independently checked
without compiling during publication. source-pins.json gives exact expected
file SHA-256 values. The local provenance commit identifiers in that file are
NOT claimed to be available remotely.

Both variants also require their own **actual regenerated**
`bootstrap/MLF/BuiltinPreludeData.hs`. Use the repository's ordinary checked
build/generator workflow: build `MLF.Entry.BuiltinPrelude` from that variant's
nongenerated sources, give it the exact computed nongenerated source identity,
and save its real stdout. Verify the expected generated-file SHA-256 and run the
full checked build again. Do not edit an identity token manually or copy the
other variant's generated literal. The large generated files are not bundled
here; until regenerated and verified, the patches alone are not qualified builds.

The accompanying LegacyPublicApi.hs, UnifySharedInput.hs and expected.stdout
are the frozen direct-test inputs. The draft header in UnifySharedInput.hs is
preserved byte-for-byte; the formal validation subsequently compiled and ran
these inputs. Compile the fixture against each variant's complete ordinary
module closure, using LegacyPublicApi as its extra reference module, then
compare stdout exactly. Do not regenerate the oracle after a failed test.

This archive does not ship the machine-specific controller, raw internal
receipts, producer object closure or complete historical artifact oracle.
Consequently it documents the measured batch and permits source reconstruction
but is not a one-command reproduction of the complete benchmark environment.
No new compiler run, CI qualification, merge or performance retest was performed
as part of preparing this archive.
