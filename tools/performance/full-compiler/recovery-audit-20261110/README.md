# Astra recovery audit, 2026-11-10

This is a recovery checkpoint, not a new performance result.

- Restored plan revision15 at22b50be7014ede07db9e41d44cacf286c5ef6206.
- Restored source f9bdb40a659bfdff4cbb782d438afbb0417dd2e1 in a clean independent worktree.
- Recomputed the full90 module inventory:5233364 bytes, all ordered module paths,
  bytecounts and SHA256s equal the original baseline inventory. See source-inventory.json.
- A new shared exclusive heavy-job lock passed contention and release controls.
- Official pinned toolchain restoration is admitted once; compiler builds and
  measurements are separate decisions, not an automatic continuation.
- The real inference11 F3 ABBA remains a negative/variable result. No timings
  have been appended or replaced, and F3 is not integrated.

Large historical local artifacts are not recoverable from hashes alone. New
setup/build/qualification receipts must identify the restored runtime honestly.
No main merge, deployment, native-generation campaign or fixed-point is authorized
by this checkpoint. The three-day sprint budget still begins2026-11-10.
