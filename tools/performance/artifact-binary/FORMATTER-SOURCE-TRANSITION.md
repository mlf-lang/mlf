# Formatter compatibility: live source endpoint maintenance

This follow-on updates the exact live endpoint of
`pr43-reconciliation-migration.json`. It does not change the pinned predecessor
`4fd6730d35b6ecaf8e169ad228ac3c7a3ed56160`, its tree, its reader, any historical
manifest, or any recorded benchmark evidence. The previous published endpoint
is retained in Git at `d925341c0f617db3ba9847a1975cc8720196f400` (tree
`feb2870d5067b8b434b2ebaf2843d468288838c7`).

The complete inventory differs from that endpoint at exactly these paths:

- `libraries/mlf-frontend/Bootstrap/Layout.hs`: shared-Haskell inline layout,
  let groups, case scrutinee closure, and dedented continuation checks.
- `libraries/mlf-crates/Bootstrap/SourceInference.hs`: newline-only presentation
  of a nested explicit case, preserving its tokens.
- `tests/shared/MLF/Tests/SharedFrontend.hs`: formatter layout acceptance,
  explicit-brace AST equivalence, and rejection regressions.
- `tools/shared/build.py`: read real syntax marker comments throughout the
  leading prologue, including after formatter-reordered LANGUAGE pragmas.
- `bootstrap/MLF/BuiltinPreludeData.hs`: builtin source identity only; bytes
  other than the `builtin-source-v1` digest are unchanged from the published
  endpoint.
- `mlf.lock`: regenerated package source and dependency identities.

All other owned source hashes are unchanged. The sole maintenance follow-on
updates the live `patricia/test_adapters.py` endpoint to check Layout's exact
formatter transition after its DeclId repair. Its original frozen oracle hash
and all predecessor bytes remain unchanged. The boundary test authenticates
both layers separately, rejects intermediate bytes as live inputs and live
bytes as DeclId inputs, and retains the original mutation and wrong-owner
rejections. Package-local locks outside the historical inventory are not
silently added to it. New formatter fixtures and tools have their own tests;
this inventory does not claim to authenticate every repository file.

The existing reversible predecessor-to-live transition supports these explicit
endpoint changes without adding another executable projection layer. New
transition rows use hashes from the immutable predecessor, not invented
intermediate bytes. Existing rows retain their old side. The independently
pinned manifest and reader hashes are updated together; source, metadata, and
historical-oracle validation remain mandatory.

`test_pr43_reconciliation.py` additionally authenticates the previous endpoint's
commit tree and manifest hash, checks that only these six paths differ, rejects
previous-endpoint and modified bytes as live input, and preserves existing
complete-tree round trips and negative controls. Historical replay runs the
unchanged suites in their pinned source trees. The benchmark bridge checks
historical evidence reconstruction; none of these checks constitutes a new
runtime, A/B, fixed-point, or performance qualification.
