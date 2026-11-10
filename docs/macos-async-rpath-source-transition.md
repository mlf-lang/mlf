# macOS build-driver source transition

The macOS dependency-closure repair changes one live source endpoint owned by
the PR43 reconciliation contract: `tools/shared/build.py`. It does not qualify a
new compiler, regenerate an oracle, or extend old benchmark measurements to the
repaired build driver.

## Exact boundary

The starting point is main commit
`f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`, with tree
`3148203097e7622ced1b272e606bfa892fad746b`. Its reconciliation manifest has SHA-256
`63598306f049a050def3fd21ddf21878a7f4f882b59a48a86c53a3398624e9c5`, and its build
driver has SHA-256
`eff291112f318206ce0f7ab85cb8a2e474be41489441204696630a395f4ca3df`.
The repaired driver has SHA-256
`cafdee99cd2800250e478b034adc8b9708699f12c0d07ef9b1375713c1fe7cce`.

`pr43-reconciliation-migration.json` records the repaired build driver's exact
SHA-256 both as the final `changes["tools/shared/build.py"]` endpoint and in the
new `live_transition` record. `reconciliation_contract.py` independently pins
the starting commit, tree, manifest and source bytes. It reads the fixed Git
objects with replacement objects disabled and requires the successor manifest
to equal that old manifest except for this one live endpoint and its explicit
transition record. Both the manifest and contract implementation retain their
separate SHA-256 pins in `source_migration_adapter.py`.

The original `4fd6730` predecessor, every original first endpoint, all other
current endpoints, module ownership, additions and Patricia maintenance hashes
are unchanged. Historical projection and advancement still delegate through
the original immutable implementations. This new record does not admit the
immediate predecessor's bytes as current bytes, nor introduce a permissive
fallback when the current driver or registry differs. Full Git history must
include the fixed main commit as well as the already required predecessors.

## Regression checks

`test_pr43_reconciliation.py` independently recovers the fixed main manifest
and proves that only the declared build-driver endpoint changes. It also
checks:

- exact historical-to-live source round trips;
- rejection of old main, older predecessor, mutated and wrong-layer bytes;
- rejection of a relocated source tree containing the old driver;
- rejection of additional paths, changed first endpoints, maintenance changes,
  incorrect predecessor identities and inconsistent transition endpoints;
- unchanged full registry, host and runtime checks and immutable oracle replay.

Run the current contract suite normally and with `python3 -O -B`, followed by
`tools/release/check-benchmark-provenance.sh` and the historical metadata
compatibility checks. The source transition proves exact source identity and
adapter compatibility only. The macOS workflow must independently exercise the
actual Mach-O resolver; native A/B and fixed-point qualification are not part of
this source-contract repair.
