# Declaration signatures and declared polymorphic fields

This follow-up fixes two inherited source-inference false negatives identified
while auditing the recursive-inference milestone. The previous milestone and
its validation receipts remain immutable historical evidence. This document
records the separately rebuilt and verified repair source, based on local
checkpoint `499221ada0b168bca39b99e67adda25d74f13f91`.

## Declaration checking without class-dependent routing

`SSignature` retains declaration provenance through parsing, surface and do
lowering, module resolution, hygiene, class elaboration, separate inference,
query canonicalization and source traversal. Declaration signatures without explicit existential binders use the existing
checked-expression path, including references to enclosing scoped variables
and scoped leading universals. Annotations introducing `exists` retain the
previous coercion path. Ordinary
expression `SAnn` nodes remain expression coercions. In particular, adding an
unused class no longer changes whether an explicitly signed higher-rank local
function is checked using its declared argument interface. Qualified expression
annotations retain their existing dictionary interface behavior.

The Figure12 fixture corpus and expected acceptances are unchanged. Its only
source change adds the new transparent declaration wrapper to free-name
traversal, mirrored by the direct host harness. The semantic pin was updated
only after an independent byte-for-byte review excluding that single branch;
all mutation controls remain enabled.

## Instantiating declaration-leading forall fields

A pattern field whose declaration begins with `forall` has a polymorphic
binding view. Each use gets ordinary instantiation evidence. Metadata retains
the exact declared target type, not merely the normalized graph view: evidence
first adapts the exact field type to that view and then applies the checked
instance computation. Leading unused quantifiers can be eliminated without
losing scope. Declared quantifier identities/kinds and datatype-parameter
identities are distinct, including under shadowing. Captured datatype type or
kind parameters remain shared; unknown ordinary fields are not generalized.

The target checker and frozen independent checker are unchanged. No term-level
coercion wrapper is inserted; positive tests compare erasure with source
computational syntax and check both serialized and in-memory targets.

## Completed verification

- Clean O0 and O2 GHC 9.14.1 builds, 105 raw shared modules each: complete.
- Integrated focused checks: previous 53 recursion cases, 41 new frontend
  compilation cases (including retained-residual rejection controls), nine AST/hygiene/
  extraction/query assertions, and existing planner/evidence controls pass.
- Parser/namespace suites and authenticated source smoke pass at O0 and O2.
- Faithful Figure12 direct gates pass at O0 and O2: 43 labels/41 distinct expressions,
  34 paper rows, 29 assumption controls, four prescribed principal-type
  controls and three annotation repairs; target/roundtrip/erasure checks pass.
- 40 provenance tests and 13 Figure12 data/mutation controls pass.
- Six exact direct-module and six exact saved/reloaded-crate fixtures pass with
  production/frozen/roundtrip/erasure checks; independently rerun.
- Independent final O2 review: 36 cases, comprising 23 positives checked by both
  checkers before/after serialization with erasure, nine rejection controls,
  and four deliberately retained residuals. An independent final O0 focused
  rerun also passed after revalidating its source and object identities.
  Both original reported field
  failures pass without added local annotations.
- The previous finite 79-program audit was rerun on new O2: the same 76 accepts
  and three expected higher-rank rejects. This extra rerun does not claim a
  separate frozen-checker pass or a completeness theorem.
- All 78 existing class actions pass on the final audited O2 compiler (exit 0,
  1096.30 seconds), with exact compiler/receipt/harness identities and unchanged
  before/after tracked source hashes.
- Three maintained terminating host-interpreter fixtures pass with exact stdout
  at O0 and O2: factorial, mutual recursion and dictionary recursion.

## Exact residuals, not repaired or hidden

1. Constructor adaptation for vacuous polymorphism remains incomplete:
   `data V = V (forall a. Int); V 1` rejects during target verification with
   `application type mismatch`. An explicitly declared polymorphic payload
   does not repair that constructor path either:
   `data V = V (forall a. Int); let payload : forall a. Int = 1 in case V payload of { V x -> x }`.
   Extraction from an assumed V value is repaired and checked. The field
   elimination fix does not claim that constructing all such values now works.
2. Unused quantifiers underneath arrow domains/results can still cause a
   declared-field/normalized-graph mismatch. Current type computations cannot
   silently cast arrow domains; these examples fail closed rather than weaken
   target checking or add unproved computational coercions.
3. Automatic opening is limited to syntactically declaration-leading forall.
   `Box a` remains monomorphic even when a polymorphic value is supplied by a
   scrutinee annotation; this is not inferred generalization of arbitrary data.
4. General recursive-inference limits remain: no unrestricted polymorphic
   recursion, arbitrary cyclic-data theorem, global/minimal qualified contexts,
   principality/completeness claim, or cyclic separately compiled crates.

Only focused GHC-host compilation, checking and interpretation are included.
No LLVM/GC installation, full native campaign, or unrelated loader/security work
is part of this repair validation.

## Reproduction and evidence identities

Build each optimization level using the already verified project-local GHC:

```sh
python3 tools/shared/build.py --ghc .toolchain/ghc-9.14.1/bin/ghc \
  --optimization 0 --build-dir .mlf-build/frontend-repairs-final-O0
python3 tools/shared/build.py --ghc .toolchain/ghc-9.14.1/bin/ghc \
  --optimization 2 --build-dir .mlf-build/frontend-repairs-final-O2
```

Run `bin/shared-frontend --recursive-inference` and `--frontend` from that build.
The maintained smoke wrapper authenticates its `source-smoke` executable and
receipt; `tools/shared/test_figure12_direct.py --build-receipt PATH --output DIR`
checks the unchanged Figure12 corpus. See `tests/recursive-inference/README.md`
for class and exact saved-crate harness invocations.

SHA-256 identities:

- O0 build receipt: `8cf59874ed57c6fc4f19a63be26cee1ea5bba391d7a22303550a2c3e6967e691`.
- O2 build receipt: `ec48926079458b736192c8e00a02f87a6b9e1b00c24076789b1621c4483d1787`.
- O0 compiler: `ffde48225edd26d028ff99727b47e64314cbc963582007e500e8bfbc0b75ecfc`.
- O2 compiler: `88d059287676318dedc1787b3dfeec54b4e6261230f2f8f5aaf693f91be233b0`.
- O0 focused executable: `101bc81d6efda84fd3068ec41a68b1a597798c74bff14ac74e515bc888601419`.
- O2 focused executable: `e2bfb44283c052d833a55184c875535f421208a89b10d7f2db43dfa5c990f996`.
- O0 Figure12 receipt: `6f5ab5e354cf4f1f8676ede071d928fd823ca7c91bec4c818fd5104e22801898`.
- O2 Figure12 receipt: `c37343c67810d7e327b4a38aca490833be579b8d3b0f626ed7c56569fd5dc625`.
- Class compatibility receipt: `1fd46c08687aa8f00866290631a1731ca880e1017cc9a1b6181f195204a1ae17`.
- Direct/saved-crate receipt: `3ee13441a850a94153b257f98ae85a8fef5bcc38e04da651ce110e7aacb48362`.

The class receipt records the parent checkpoint as Git HEAD because repairs
were built from a held uncommitted worktree; its actual source hashes, not that
parent HEAD alone, identify the executed implementation. Both build receipts
bind every compiled shared/host/configuration input. Subsequent edits before
commit are documentation only; those audited inputs remain unchanged.
