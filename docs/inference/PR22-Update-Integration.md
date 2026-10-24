# Integrating the updated PR #22 into recursive inference

## Exact inputs and direction

- Recursive-inference branch before this merge: `2ea93adf6d8c76857e0d202a033e9bfee191e444`.
- Updated PR #22 branch: `7c8e9d7e337eac597ab294a13c49c0dd67a26802`.
- Common ancestor: `c0c5dddd11ed5775e2a3d5564cfeeef8383610a5`.
- Direction: PR #22 into PR #25, preserving both histories with a two-parent merge. Neither PR #22 nor its base is changed.

The upstream update contains ten commits touching 309 files. Git initially reported 28 conflicted files. The earlier successful CI run 155 belongs to the pre-merge recursive-inference head; it is not evidence for the merged implementation.

## Resolution ledger

### Canonical collections and core evidence

Upstream replaces implementation `List`, `Nil`, `Cons`, tuple wrappers and `Unit` with canonical Haskell collection, tuple and unit syntax. The projection changes code tokens only, not strings, comments or character literals. Independent comparison establishes that upstream Graph, Graph.Solver, Elaborate, CompilerCore, X.Check and the relocated independent checkers have no algorithm changes beyond this projection. The recursive graph-region, captured-frontier, frozen-export and declared-field evidence algorithms are retained.

Constraint additionally retains upstream's six explicit phase-boundary guards: source-definition provenance, call-site provenance and shared-pattern bindings must have been consumed before constraint generation/validation. No target checker is relaxed. The independent checker files move to `tests/shared/Tests`; they are canonically projected, not byte-identical to their pre-merge paths.

### Source declarations and frontend traversals

The merged AST preserves upstream source locations, copied-definition markers and shared-pattern forms alongside explicit `RecursiveMode`, `SSignature` and declared-field metadata. Parser, surface lowering, dependency analysis, module resolution, standalone rewriting, hygiene, source extraction and cache encoding retain declaration-signature provenance separately from expression coercions. Newly generated prelude recursive definitions carry explicit checked modes. The new Standalone and SourceInference paths traverse the added forms rather than silently bypassing them.

### Managed evidence and recursive dictionaries

The finite ordinary dictionary-demand planner remains authoritative for unsigned recursion. Each explicit qualified use records an ordered argument sequence containing either an ordinary seed identity or a synthesized managed-evidence expression. Only ordinary predicates enter the finite demand graph. Rendering resolves ordinary identities and interleaves managed arguments in their original positions; `HasCallStack` is never generalized as an ordinary class wanted.

Call-site wrappers select the source location. Copied-definition boundaries clear inherited managed scope before a checked definition installs its own givens. Explicit declaration signatures remain checking interfaces. A managed expression-signature use consumes its managed argument at the use site, so it must not subsequently advertise that argument as an exported calling convention.

### Checked source-group interfaces

The new source scheduler's fallback lowers the actual lexical binding/SCC structure, including unsigned singleton and mutual recursion. One solved plan supplies both the lowered term and each requested top-level export's ordinary slot order. The extractor walks only the top-level continuation spine, not nested same-name bindings. Explicit source-issued interfaces use the same provenance/consumption rules as local binding registration. No dictionary-arrow inspection or class-name-set fixed point reconstructs the interface.

Recursive groups remain ineligible for the upstream nonrecursive evidence-compaction authority. Explicit retained qualified expression interfaces also use the unchanged-boundary path. Existing candidate scopes, checked predecessor protection, cache identity and signed sealing remain in force.

### Tests, inventory and build wiring

The original reviewed `739 -> 742` migration remains protected. The upstream cutover requires eight explicit label/identity migrations and retains four newly authored controls, giving `742 -> 746`: 34 solver, 384 language, 27 crate and 301 module leaves. Historical inventory evidence is not rewritten. Static guards compare the explicit ordered delta against registry, catalog and golden inventory and retain adversarial ownership/source mutations. Discovery is not execution of all 746 actions.

Same-name recursive functions and the unsigned alias cycle are tested only for their prescribed types (`Int` and bottom); divergent targets are not evaluated. A same-name recursive value with an infinite type remains a negative control. Nominal user-defined `List`, `Maybe` and `Unit` tests remain nominal where intended; implementation identities and standard builtin-unit assertions use canonical syntax. Expression annotation strings use `::` where `:` now denotes the canonical list constructor.

Figure12 retains all 43 labels, 41 expressions, four prescribed type ASTs, three annotation repairs, IDs, order and acceptance bits. Its reviewed changes are canonical collection spelling and the existing `SSignature` traversal. Both the maintained and direct harness retain the same semantic controls. The shared manifest contains 108 modules: the prior 105 plus Standalone, SourceInference and EvidenceBoundary. Target-private checker paths follow their upstream relocation.

## Validation status

Validation of the merged source is in progress. Static inventory/mutation checks, 13 Figure12 decoder controls, 42 provenance controls and focused exhaustive GHC typechecking have passed. Final producer receipts, focused merged execution, genuine package locks and exact-head CI will be recorded before publication. No pre-merge receipt is relabelled as a merged-source result.

## Scope retained

This merge does not claim unrestricted polymorphic recursion, arbitrary cyclic-data inference, a principal-completeness/minimal-context theorem, or a full native/LLVM/GC campaign. Previously documented field-revelation and vacuous-polymorphism residuals remain explicit. Upstream native/bootstrap tooling is preserved as source; adding that tooling does not mean its expensive campaigns were executed here.
