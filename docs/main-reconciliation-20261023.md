# Main reconciliation after the staged framework checkpoint

This merges main `cb4c56c3744653c76648e609c06a71afad1ae2d4` **into** the draft
integration branch. It does not merge or publish the PR into main. First parent
is `bea6c93980e47946afc22ee99be0d571ed544489`; the common ancestor remains
`77ac8a7bc551ac71747b38c79fc5812d385165e3`.

## Why reconciliation is necessary

Main now contains squash commits `84db2ac` (#9) and `cb4c56c` (#16), whereas the
integration branch retained the original PR commits. The original #9 head
`9d3d59cd51d3b204c49bcfa7acc8c51c94c1d853` and squash `84db2ac` have identical
Git trees. The latest #16 is not just an ancestry change: it adds conservative
PR-only async change selection and its fault controls. These changes must not
be discarded merely because the branch integrated an earlier #16 snapshot.

Eight textual conflicts were resolved:

- CI workflow, metadata dispatcher and CI policy assertions take current main,
  an additive superset of the integration checkpoint in these files. The six
  required jobs, unconditional lightweight checks, main/manual/merge-queue full
  async behavior, package/release separation and failure gates remain.
- CI/release documentation takes main's scope-aware six-check description.
  The stale 480-second source-smoke sentence is corrected to 900 seconds, matching
  the unchanged actual script and its existing watchdog tests. No timeout changes.
- Changelog and tests README retain guards and tuple/list additions, 739 Core
  actions, 170 families and 583 backend execution rows.
- The root lock is derived anew from actual manifests/sources and is byte-identical
  to the reviewed checkpoint, SHA-256
  `93cd77fadc6eb420bde07fb0cc2efa68598b9d91018c93bcb2fcd36f132b7679`.

## Inventory/provenance boundaries

The original `8a3e69b` migration inventory, 339-role review and staged framework
sources are unchanged. Their frozen census is **not** presented as exhaustive
for this later tree. The accompanying supplemental inventory explicitly owns:

- New upstream selector `tools/release/async-change-scope.py`: selection only,
  never evidence of parity execution.
- New upstream `test-async-change-scope.py`: fourteen selector fault controls.
- Three changed CI/metadata/policy owners.
- The local static supplemental-inventory audit itself.

All six supplemental records retain P6 integration obligations. Source-role
classification is not framework integration, internal leaf export or execution
qualification. In particular, a verified unrelated-only PR's `not-executed`
decision is not a passing async parity receipt. Unknown/malformed selection
runs parity; failed selection fails its required job.

Run `python3 tools/testing/check_reconciliation_inventory.py` to check this
supplement, then the existing migration/tuple/Core/manifest audits. Upstream
policy controls are focused host-script tests only; they do not run MLF suites,
bootstrap or native compilation. The complete metadata `check.sh` is not run.
New MLF contract code remains uncompiled, and all earlier qualification limits,
legacy defaults and unfinished migration phases still apply.
