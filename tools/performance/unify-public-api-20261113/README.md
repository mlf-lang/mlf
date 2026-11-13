# Public Graph.unify baseline fixture: actual result

Against source `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`, the unchanged
`UnifyPublicApi.hs` fixture was independently compiled and relinked with the
authenticated ordinary GHC 9.14.1 producer. **All 23 authored cases passed**
on the first and only execution. No expected result or source correction was
needed. The previously source-only package remains unchanged as authored; this
new result establishes its baseline compilation and execution.

- Fixture SHA256: `3d856410f66c9afc809d1edca752680d33b0010cd8f90551feee479295da049f`.
- Complete actual stdout SHA256: `14eff8e4d92abf2f07cc15d0b5b425f23472e5623b6e808f4eb605ce54b8073a` (2,694 bytes).
- `SUMMARY\t23\t23`; all three commands exited 0; all three stderr files were empty.
- Compile: 1.265 s; link: 1.888 s; fixture: 0.004 s. These are job diagnostics, not a compiler performance comparison.
- Original unchanged r13 guard: 6.467 s within 180 s, `test_only=false`, complete cleanup, independent two-lock reacquisition and lease clearance.
- The five final r17 guards were verified before starting. The current epoch has no active lease or quarantine after completion.
- Producer authentication and bound source/tool/fixture/object pins passed before and after. The original producer Main object was not linked; this fixture produced its own Main.

The cases include dense/signed/sparse/extreme-ID graph contents, alias
canonicalization, higher-kinded application, exact rejection and endpoint error
priority, input rejection before poisoned equations, and the declared
Either/Graph/counter/full-render partial-host boundaries. Exact observations
are preserved in `commands/fixture/stdout` and `RESULT.json`. No hash substitutes
for the fixture's full logical graph/error comparisons.

This baseline job rebuilt no full compiler, ran no candidate, native A/B,
fixed-point or benchmark, and made no production change. It does not prove
universal semantics, async-exception timing or retained-memory equivalence.
A future candidate must pass the same fixture bytes and complete actual-output
comparison under its separately authenticated producer.
