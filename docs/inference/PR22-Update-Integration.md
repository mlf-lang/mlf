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

## CI integration correction after the merged checkpoint

The published merge `a8c3f458b66bae4605e5bded5d5f79ded75461bf` was tested by
CI run 162 (`40136305106`). Its O2 direct, TupleList/framework and Figure12
checks passed. The next managed-fixture step rejected a C command which exited
successfully but emitted two GCC 13 fortified-libc `unused-result` warnings.
The O0 direct frontend command reached its 1200-second deadline. Neither result
is reclassified as a successful complete run. Metadata and the ordinary runtime
jobs passed; the opt-in native parity and full-main qualification were skipped.

The correction has three narrowly scoped compatibility changes:

- `SourceSCC.hs` uses `SSignature`, rather than the former overloaded `SAnn`
  convention, for a declaration whose dictionary dependency must be closed
  before the cache-compaction counterexample. The original upstream fixture and
  the corrected fixture both complete the same 29 assertions. The former
  unqualified expression coercion correctly produced a different dependency
  context; no cache validation or assertion was relaxed.
- Two POSIX supervisor writes store their `ssize_t` result before explicitly
  discarding it. The original single-write, best-effort close/exit behavior is
  unchanged. Fortified GCC controls reproduce the old warnings and compile the
  corrected code with empty stderr, including `-Werror=unused-result`. No warning
  suppression or successful-stderr exception was added.
- The test watchdog always terminates the original process group after its grace
  interval, even if the leader exited and a child redirected its streams.
  Final capture draining and leader reaping are bounded too. An escaped group
  is not signalled; retained pipes produce an explicitly incomplete cleanup
  record instead of an unbounded wait. Real-process controls cover inherited
  pipes, redirected streams, cancellation after leader exit and escaped pipes.
  The framework wrapper now uses this same watchdog and preserves its existing
  status, discovery, identity, count, report and expected-error assertions.

### Measured O0 cost and exact coverage partition

One unchanged Applicative-default workload was compiled and checked on pristine
upstream `8d953f9` and the merged compiler. Each produced exactly `Int`, passed
closed target checking and target serialization, and evaluated to `42` in the
host interpreter:

| Producer | Wall seconds | User CPU seconds |
| --- | ---: | ---: |
| Upstream O0 | 149.875 | 149.969 |
| Merged O0 | 174.594 | 174.746 |
| Merged O2 | 17.915 | 17.840 |

The observed merged overhead is 16.5% for this one workload. The O0/O2 ratio is
9.75, not a compiler-wide performance theorem. The upstream workload alone
exceeds the old 120-second semantics-mode budget. Extrapolating this ratio from
completed O2 stages suggests approximately 33 minutes for frontend, 32 minutes
for the two semantics modes, and 61/68 minutes for the default/framework suites.
These are planning estimates, not completed O0 measurements.

CI therefore partitions exactly the existing O0 coverage into three parallel
legs, while keeping O2's complete route and its limits unchanged:

| Matrix leg | Executed coverage | Heavy command caps |
| --- | --- | --- |
| O0 direct | suite-receipt helpers, source smoke, async lifecycle checks, frontend/recursion/field checks, both host semantics modes, Figure12 | frontend 2400 s; each semantics mode 1200 s |
| O0 default | shared framework semantic helper and all 305 default TupleList observations | default 4500 s |
| O0 framework | shared semantic helper, all 105 framework actions, discovery, exact selection, report and error controls | framework 4500 s |
| O2 all | all existing O2 routes, including managed evidence and guest checks | unchanged: frontend 1200 s; semantics 120 s each; framework 600 s each |

The duplicate raw no-argument TupleList invocation is removed. The default/all
framework gate still invokes the identical authenticated binary without
arguments, with the stronger count and terminal-marker oracle. No case is
removed. Partial framework receipts state the selected route and actual 305/0
or 0/105 counts; they do not claim the combined route passed.

Each leg has an independent, fail-closed 120-minute job deadline. The O0 direct
heavy caps total 4800 seconds; all its conservative helper ceilings total 8040
seconds, so the job deadline remains a stricter global bound, not a guarantee
that every command can simultaneously consume its maximum. The measured helper
costs were subsecond. The framework heavy caps each leave 45 minutes of the job
for setup and controls. Actual final elapsed times and any timeout are retained.

Each shard builds and authenticates its own producer. This deliberately adds
two O0 producer builds: current receipts bind absolute toolchain, dependency,
object and command-log paths, and no portable receipt-rebasing contract is
introduced here. Unique artifact names prevent shard overwrites. The existing
required `native` matrix dependency remains in `PR gate`, so a failed or skipped
matrix leg cannot count as success. Independent policy controls enforce the
four exact rows, coverage union, selectors, authentication, artifact names and
aggregate dependency, including mutation negatives.

Budgets are selected only after authenticating the producer's optimization
level. There is no CLI or environment switch that can relabel O2 as O0.
Explicit timeout overrides remain bounded by that authenticated level. Earlier
local 600/1200-second failures and the interrupted 900-second retry remain
separate incomplete attempts.

### Regenerated identities and validation boundary

The supervisor edit changes one authenticated host input and requires fresh
producer identities. The regenerated O2 receipt is
`bec63be1fdf146adf49f16e7cc415bf75621032e90a4930aa2f9ff86e3c9ab4e`.
All 226 Haskell object/interface hashes, all 108 shared sources and all 19
configuration inputs are identical to the previous merged O2 producer. The
new compiler executable is
`d5e8ce873133c93aefabe5f1dc4579edb08f2c900b16cb799c7a566cd83d299e`.
This mapping preserves the scope of earlier inference evidence without
mislabeling old executable runs as new ones. Rebuilt runtime/managed checks and
exact-head CI are separate required gates. The interrupted local O0 rebuild
is not a completed producer; final O0 coverage must be established by the new
CI legs or a complete authenticated local rerun.

### Further upstream update observed before publication

A fresh remote check on 2026-10-24 at 22:56 UTC found PR22 advanced from `8d953f9`
to `13ba7558e6711fcbabe5739ed312dfc0b23b7042`. Its two commits affect only the
framework host syntax and test execution budgets. The framework syntax is
already byte-identical to this branch. The budget change has the same
source-authenticated optimization intent but a serial 180-minute O0 job and
uniform 1800-second mode budget. The integration retains the independently
reviewed parallel/per-mode design above rather than stacking both mechanisms.
All four upstream budget-control methods are preserved with the corresponding
per-mode and four-row assertions, including every unknown/untyped optimization
negative. No inference or target-checker source changes are needed for this
additional merge.

On the regenerated O2 producer, the exact uninstrumented `SourceSCC` fixture
again passes all 29 upstream assertions (receipt
`19c4f0f17970c13cba85eab7e8761b7e8f115267cbd0063609e1a494847863ef`).
The regenerated managed fixture also completes all 17 raw, six parsed and
source-contract checks with strict empty successful stderr. The longer
framework rerun and final exact-head O0/O2 CI remain distinct completion gates.
