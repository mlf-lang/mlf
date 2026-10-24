# Ordinary recursive inference implementation plan

Status: ordinary recursive SCC inference and the subsequent lexical qualified-interface phase are implemented and locally validated. Final audited O0/O2 builds, focused source/target tests, frontend checks and bounded module/saved-crate compatibility pass. See `Unsigned-Recursion-Final-Validation.md` for exact evidence and the interrupted legacy guest route; this is not a full native campaign or a principal-completeness proof. Base PR22 c0c5dddd11ed5775e2a3d5564cfeeef8383610a5. The Chinese report records the intended scope; this document records the core representation and invariants.

## Staging

The first code change adds `RecursiveMode = InferRecursive | CheckRecursive SAnnotation` and carries it through source/core AST traversals. That representation commit kept Surface fail-closed. The subsequent core patch enables unsigned recursion with shared constraints, frozen exports and checked evidence. Signed source behavior and existing rejection tests are not changed in that representation commit.

## Candidate graph region

For one unsigned inference SCC C, create one GGen G under the surrounding expression gen. Allocate one flexible shared root r_i under G per member. The root of G is a private structural arrow spine whose leaves are exactly the r_i (for a singleton, GArr r_1 r_1). There is no fresh bottom terminator: it would add an unconstrained generalized variable. Every spine node and member root is bound directly by G. Member roots have kind *. No type node is ever bound under a scaffold, and no source constraint mentions its ID. Therefore every scaffold is inert and rigid after normalization; it cannot enter the flexible group telescope. Export traversal starts from member roots and never reaches scaffolds. These invariants are tested across spine permutations. The spine is never used as a source term type, never instantiated, never unified with a member root, and never emitted as xMLF.

This uses the existing one-root graph invariant while making normalization's root reachability see every member. All r_i remain ordinary graph type nodes. Do not globally rigidify r_i: a member root can also occur in a peer's type, and the peer may need to quantify that variable. Root-specific rigidity belongs to each exported single-root scheme, not the original shared graph.

Each recursive occurrence is a new binding kind carrying the target name, shared r_i and future export G_i. During inference it generates equality to r_i exactly like Mono, with no instantiation edge from G_i. Its typed skeleton retains an evidence-only reference to G_i -> r_i; that edge is not a solver work item. Once the group finishes, elaboration can prove that edge from the exported scheme under the group telescope.

RHS terms are built under G. Their internal ordinary constraints are processed first, and the RHS scheme is constrained to its shared r_i through the existing instance relation. No G-node is unified as though it were a type. Signed members are available via their fixed interfaces; unsigned sub-SCC order comes from the unsigned-only dependency graph. Acyclic unsigned members use singleton regions while retaining their names in the original runtime knot.

### Risks requiring review

The synthetic spine adds structural parents. Show that it changes only the intended group region/dominance and reachability, not inertness, rebinding permissions, allowed solutions or member kinds. Check both sparse and dense paths. If neutrality cannot be demonstrated, use explicit multi-root region support rather than disabling invariants.

## Solver boundary

The generation state already owns graph, pending equalities and pending instance edges. Add an explicit flush operation that prepares a Solver, unifies pending equalities, propagates dependency-ordered pending instances, calls Solver.finish to validate graph and indexes, then retains the resulting graph with empty pending work. It must NOT normalize the whole graph while surrounding constraints are incomplete.

An unsigned group's RHSs and root constraints are all flushed before its exports are published and before generating/solving signed RHS checks or the continuation that can use those exports. Nested groups can flush accumulated constraints only if all prior scheme dependencies are ready. Later external constraints must still flow through shared environment frontier nodes. This eager solve schedule needs tests against the old final solve on nonrecursive programs and explicit graph-level order checks; a flush is not a license to solve a forward-dependent edge.

## Per-member export schemes

For each solved r_i, create a separate export G_i under the surrounding expression gen. Copy the selected member's generalized internal graph domain as determined by the solved G ownership, preserve nested binder structure/flags/kinds, and bind the copied root to G_i. Rebind nodes directly owned by G to the copied root, as ordinary scheme expansion does. External frontier references retain their original representatives; do not copy/generalize them. Preserve an origin-to-copy mapping and validate the new graph.

Graph.materializeExport takes the selected scope G, source r_i, reserved export identity and surrounding GGen. Unlike ordinary expansion, it copies only internal nodes and never replaces the frontier with fresh bottoms. If the selected root itself is outer-owned, the export directly references it and allocates no copies. Reserved GGen identities are installed atomically only once their exports are ready. The old group remains for RHS and recursive-use evidence, while subsequent source instantiation uses only the finished G_i.

All exports must exist before any signed RHS is checked. New solver preparation after node additions must rebuild indexes; never mutate Graph while retaining stale Solver.scopeIndex or structural/binding indexes.

## Evidence and normalization

After all source constraints finish, ordinary graph normalization runs over the group with full spine reachability and over every independent single-root export. Read the group telescope A from G, and the exact public signature Sigma_i from G_i. A may include a member root that is flexible in the shared region but rigid as the root of its own exported view; these identities must not be conflated.

For each unsigned RHS, elaborate under the whole group telescope (fresh, provenance-mapped target binders). Prove the RHS -> shared r_i edge and all evidence-only recursive occurrence edges in that scope. Abstract A. Construct a checked projection that drops variables not retained by the export, including any root-specific inert alias, using XOuter/XElim/XThen and capture-avoiding substitution. The existing checked instance prover adapts quantifier order/renaming to the exact normalized Sigma_i. Its recursive replacement callback folds the dependency-ordered group bounds for the actual target scope: a dropped binder receives its bound after all prior capture-avoiding substitutions, never stale graph readback. This matters when a peer-only bound depends on an earlier dropped variable. The final RHS must match Sigma_i by the unchanged independent checker, not only an informal equivalence.

Final XLetRec still contains the original value binders and one original RHS each. No synthetic spine, duplicate value computation, additional value alias or erased wrapper reaches the target. Signed-only groups retain the existing evidence path.

## Review and proof obligations

- Group anchors cannot impose new constraints or rigidification; every source/shared root is valid under all graph checks.
- Export internal copying is principal, environment-frontier identity is preserved, and no old body constraint remains capable of mutating exported generalized internals.
- Whole-group and per-member normalization/readback agree up to the explicitly checked type-only projection, including root aliases and independent quantifier ordering.
- Nested SCC flush order is sound in arbitrary surrounding incomplete expressions, including class evidence and annotations.
- Signed-aware scheduling and class dictionary interfaces have focused end-to-end regressions in the later phase; arbitrary-program correctness still requires the stated invariants, not only examples.
- Current/frozen target checking, source-erasure equality and prescribed result types remain mandatory. GHC 9.14.1 was installed locally from the official checksum-verified bindist after approval. Focused O0/O2 tests pass; exact validation evidence is recorded separately.

## Qualified recursion: boundary of the core-only milestone

The later qualified-interface implementation is documented in
[Qualified-Recursion-Implementation-Plan.md](Qualified-Recursion-Implementation-Plan.md).
The following records the earlier core milestone, not the latest branch capability.

Unsigned class-free recursion and unsigned recursion with wants resolved from existing concrete instances or captured givens are implemented. Distinct `Inspect Int` and `Inspect Bool` wants are tested independently. Newly generalized recursive dictionary interfaces are not implemented in this core milestone; a function requiring `forall a. Inspect a => a -> Bool` still needs an explicit recursive signature. Signed class-constrained recursion keeps its existing checking path.

The next phase must retain finite predicate origin identities, full solved type arguments, lexical let/given scopes and evidence dependencies. A fixed point over raw wanted-occurrence lists or class names is not acceptable. Passing a single SCC-wide dictionary list to every binding also needs a principality/ambiguity argument: recursive references under local let boundaries may abstract predicates rather than exporting them from the caller. This is a design obligation, not a completed feature.
