# Integrating the updated PR #22 into recursive inference

## Exact inputs and direction

- Recursive-inference branch before this merge: `2ea93adf6d8c76857e0d202a033e9bfee191e444`.
- First fetched PR #22 update: `7c8e9d7e337eac597ab294a13c49c0dd67a26802`.
- Subsequent requested refresh: `8d953f90762ed2d1dd22fcdb7928ca71ac294893`.
- Common ancestor: `c0c5dddd11ed5775e2a3d5564cfeeef8383610a5`.
- Direction: PR #22 into PR #25, preserving both histories with sequential two-parent merges. Neither PR #22 nor its base is changed.

The first upstream update contains ten commits touching 309 files. Git initially reported 28 conflicted files. A fresh remote check found four further commits affecting ten files; the second merge had seven conflicts (four generated locks, frontend assertions and two metadata guards). The earlier successful CI run 155 belongs to the pre-merge recursive-inference head; it is not evidence for the merged implementation.

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

### Subsequent intrinsic-visibility and historical-tree update

The additional Module change separates compiler-only `$MLF.Intrinsics.*` reach from source-visible instance methods while preserving ordinary qualified imports. Its exact upstream implementation is retained. Frontend controls now assert call-site labels and spans, canonical unit syntax and refutable-pattern failure hooks, alongside the recursive acceptance controls. Historical tuple and runtime validation use the immutable published tree `7efa13e6a64c0445ebcf891c4e15694321a43780` (the tree of `6f58cf488eb6c0cb5bc56341e788eb9243683917`); original local commit identities remain provenance, not unavailable retrieval dependencies. No historical source hash or ABI assertion is weakened.

### Tests, inventory and build wiring

The original reviewed `739 -> 742` migration remains protected. The upstream cutover requires eight explicit label/identity migrations and retains four newly authored controls, giving `742 -> 746`: 34 solver, 384 language, 27 crate and 301 module leaves. Historical inventory evidence is not rewritten. Static guards compare the explicit ordered delta against registry, catalog and golden inventory and retain adversarial ownership/source mutations. Discovery is not execution of all 746 actions.

Same-name recursive functions and the unsigned alias cycle are tested only for their prescribed types (`Int` and bottom); divergent targets are not evaluated. A same-name recursive value with an infinite type remains a negative control. Nominal user-defined `List`, `Maybe` and `Unit` tests remain nominal where intended; implementation identities and standard builtin-unit assertions use canonical syntax. Expression annotation strings use `::` where `:` now denotes the canonical list constructor.

Four adjacent do-notation controls now supply their already-prescribed concrete `Maybe` result context without changing the tested body or oracle. Without that context, `return` alone has a generic `Monad m => m a` type; the current final-expression dictionary-closing policy does not select `Maybe` merely because an instance exists. The exact same-name recursive-value negative instead rejects a cyclic type, and remains unchanged apart from its observed diagnostic.

Figure12 retains all 43 labels, 41 expressions, four prescribed type ASTs, three annotation repairs, IDs, order and acceptance bits. Its reviewed changes are canonical collection spelling and the existing `SSignature` traversal. Both the maintained and direct harness retain the same semantic controls. The shared manifest contains 108 modules: the prior 105 plus Standalone, SourceInference and EvidenceBoundary. Target-private checker paths follow their upstream relocation.

The direct frontend wrapper retains exact exit/stdout/stderr checks and process-tree cleanup. Its frontend-only budget is configurable (default 1200 seconds); the previous 120-second bound was shorter than the measured 157-second passing recursive submode. The two other frontend modes retain their original 120-second limits. The new O2-only recursive-managed gate checks ordered ordinary/managed arguments, copied scopes, source contracts and cold/warm parity, using authenticated producer objects and both target checkers.

## Validation status at the merged O2 checkpoint

The latest merged producer is GHC 9.14.1, `-O2`, with demand-preserving flags. Its receipt SHA-256 is `e2dcc170dd7878b90e9b9eb6ca38b08088a378639940450f9567b1076e9ffced`; all 108 shared inputs, 31 host inputs, 19 configuration inputs, 226 object/interface hashes and 12 executable outputs are authenticated. The compiler SHA-256 is `7f90eee161159ebf020b9fed28a4d3ffd49e1bf1f53338fac867a7078478ef1a`.

Completed on these merged bytes:

- Full strict direct wrapper: async controls, frontend/recursive/declaration/field checks, both maintained semantics modes and receipt controls. Frontend took 206.98 seconds; the other modes took 106.65 and 88.40 seconds. Exact stdout, empty successful stderr and exit status remain required.
- Independent recursive-only rerun: all three prescribed banners, exit 0 in 170.04 seconds, authenticated before and after.
- Recursive managed-evidence gate: 17 raw controls, six parsed-source controls, exact source-group interfaces and fresh cold/warm parity. Production and independent target checks, target serialization/erasure and all object/source identities pass. Receipt: `8c7a4a929fb9b17e88e419a417dd79262908b0d0fe10204425d7ce70a38e0a0b`.
- Six exact direct-module fixtures and six save/reload/link crate fixtures, including scope rejections and ordinary/qualified cross-module exports. Both target checkers, serialization and erasure pass; divergent targets are not evaluated. Receipt: `3b6d2d699174d8305e871790c578df23a684865070f591fe554b7566c64e61e7`.
- Exact maintained Figure12 execution, 13 decoder/pin controls, 45 provenance controls, the ordered 746-leaf guard and its mutation controls, release metadata/shell checks, and authenticated source smoke.
- Six genuine offline package locks and their `--offline --locked plan` checks. Lock generation changed none of the producer's 158 source/configuration inputs; lock files are not in that compiled input set.

The fresh `-O0` producer's final shared-source self-check and the broader TupleList/framework wrapper are still pending at this checkpoint. The earlier 300-second TupleList attempt timed out after 292 observations, not a pass; the current run uses the existing 600-second suite budget. The earlier 7c8 O0 attempt was interrupted with exit 130 when the requested newer upstream update arrived, and is not counted as passed. The new managed fixture's first run correctly rejected a successful compile with a partial-function warning; a total-pattern correction passed in a fresh output directory without relaxing stderr checking.

No pre-merge or intermediate receipt is relabelled as evidence for this latest source. Exact-head CI follows publication; pending checks are not described as completed.

## Scope retained

This merge does not claim unrestricted polymorphic recursion, arbitrary cyclic-data inference, a principal-completeness/minimal-context theorem, or a full native/LLVM/GC campaign. Previously documented field-revelation and vacuous-polymorphism residuals remain explicit. Upstream native/bootstrap tooling is preserved as source; adding that tooling does not mean its expensive campaigns were executed here.
