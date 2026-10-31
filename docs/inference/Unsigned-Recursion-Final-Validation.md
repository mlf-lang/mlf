# Unsigned recursive inference: final validation

Historical recursion-checkpoint record. The subsequently authorized declaration-
signature and declared-field repairs, their separate validation and remaining
limits are recorded in [the frontend follow-up](Frontend-Signatures-and-Fields-Validation.md).

## Source and scope

- Isolated branch: `codex/unsigned-recursion-pr22-20261024`.
- Pinned original PR #22 head: `c0c5dddd11ed5775e2a3d5564cfeeef8383610a5`.
- Core inference commit: `221bc8a`; finite dictionary planner: `696a756`;
  qualified collector/materializer: `e31fe54`; legacy fixture/inventory repair:
  `d64659d`; maintained terminating runtime fixtures: `cf6b33f`.
- No publication, push, PR, merge, LLVM/GC installation, full native campaign,
  or unrelated loader/security work was performed.

Unsigned recursive uses share one unsolved dictionaryful type in their inference
SCC. Signed schemes remain fixed polymorphic interfaces; unsigned exports are
frozen only after solving, with outer frontier identity preserved. The target
retains the original recursive knot and checked xMLF evidence. The qualified
planner uses finite origin identities, lexical let abstraction and strictly
increasing frame finish ranks; complete dictionary argument types are solved by
the existing ordinary graph solver.

## Completed checks

1. Final clean GHC 9.14.1 builds at O0 and O2 compile all **105 raw shared
   modules**, audit actual inferred interfaces, and pass shared grammar/name
   resolution. Their receipts are complete and all current shared, host and
   configuration input hashes still match. Both builds were initiated at
   `e31fe54`; later changes affect legacy test fixtures/metadata and documents,
   not those audited inputs.
2. `shared-frontend --recursive-inference` passes at O0 and O2: **53 authored
   source cases**, eight finite-planner groups, recursive-knot checks,
   dependent-bound/higher-kind projection controls, and malformed recursive and
   generated dictionary-scope target controls. Positive cases prescribe types
   independently and use production plus frozen checkers before and after target
   serialization, with erasure comparison. Negative cases assert error phases.
3. Full direct `shared-frontend --frontend` passes at both optimization levels.
   An independent reviewer reran both final focused binaries successfully.
4. Authenticated source smoke passes at both levels: two positive sources, two
   inference rejections and one malformed target per run.
5. All **78 existing typeclass tests** pass through the **final audited O2**
   compiler/host interpreter (933.82 seconds, exit 0). The exact saved harness
   was recompiled and executed with final receipt/executable identities and a
   before/after source-hash guard; no recorded source changed. Its byte-identical
   maintained copy is `tests/recursive-inference/TypeclassCompatibility.emlf`.
   The earlier incremental O2 pass remains separate intermediate evidence, not
   the basis for this final class-compatibility claim.
6. Three maintained terminating programs execute with exact expected stdout at
   O0 and O2: factorial (`720`), mutual recursion (`42`), and generalized
   dictionary recursion (`42`). These use the host interpreter, not native code.
7. Forty Python provenance tests pass, including a final rerun. The corpus-size
   guard was deliberately updated from 103 to 105 and asserts both new module identities/paths. Frozen
   `IndependentCheck`, `IndependentType`, and `CompilerCore.finishCompilation`
   are byte-unchanged from the pinned base. `git diff --check` passes.

8. A further independent finite audit checks 79 scratch programs at O0/O2:
   76 accepted and three expected higher-rank boundary rejections, with matching
   results. Eight representatives pass serialized production checks at both
   levels. No separate frozen check was run on these extra samples. The audit
   found no new in-scope false negative. Separate probes identified an inherited
   polymorphic constructor-field revelation gap and a class-dependent signed-let
   acceptance inconsistency. A fresh pinned-base build reproduces the latter;
   neither issue is repaired by this recursive-inference patch. See
   `Unsigned-Recursion-Coverage-Audit.md` for paired controls and limits.

## Module/crate and discovery verification

The final O2 compiler completed live registry/catalog/golden discovery of all
**742 labels**, with unique IDs and actual retained family-list agreement.
Partition counts are 34/380/27/301. The exported canonical-query action including
the new compiler-hash salt inequality passed. All **six direct module cases**
then passed, including the qualified A/B export at Int and Bool and three
signed/instance/downstream-orphan scope rejections.

The same **six saved-crate cases** passed through the reproducible direct-GHC
harness `tests/recursive-inference/QualifiedCrateHost.hs`. It parses the exact
literal fixtures from `Tests/Modules.emlf`, preserves the original sources and
oracles, and calls `compileSources`, reloads saved `.mlfci`/`.mlfco`, links through
`linkObjects`, and checks production/frozen typing before and after serialization
with erasure comparison. The three rejections require the original reason
substring. `tests/recursive-inference/README.md` records step-by-step parity with
`Tests.Separate.compileSeparateProgram`; the maintained Python runner records
separate harness/input/binary/log hashes. This is not mislabeled as execution of
the legacy guest action or the 105-module build audit. An independent reviewer
also executed all six successfully.

The legacy nested-interpreter route completed discovery and all six direct
module cases, then spent its remaining time in the first saved-crate builtin
prelude compilation. After the exact host equivalents passed, only this
redundant run was intentionally interrupted: started 16:19:27 UTC, stopped
16:50:50 UTC, **exit 130, incomplete**. Its source is preserved as
`tests/recursive-inference/RecursiveModuleCompatibility.emlf` and its log/status
are retained. No guest saved-crate success is claimed. The route change closes
the same compile/save/reload/link/check validation goal without waiting for
nested-interpreter overhead.

The original divergent A/B source formerly rejected for a missing signature is
preserved exactly and now has independently prescribed `XBot`, checked through
both direct module and separately linked crate paths. It is never evaluated.

Discovery repairs are additive/semantic, not deletion: the first graph test had
already been added but its registry and legacy partition counts were stale;
two retained Readability successes still had old rejection labels in registry
metadata. These now align with the actual lists. The two new qualified module
checks bring the reviewed inventory from 740 to **742**. Discovery does not claim
all 742 Core actions ran.

## Recorded attempts and corrections

- The first integrated build exposed a mechanical misplaced type signature;
  corrected before final builds.
- A newly authored mutation helper sliced short names without checking length;
  corrected with explicit guards. The compiler implementation was unaffected.
- The first checking-only module run passed direct module checks, then its test
  helper attempted `/scratch` because `MLF_TEST_WORK` was unset. It failed on the
  read-only root filesystem. The retry uses an explicit project-local scratch
  and cache root; no filesystem permission change or installation was needed.
- A retry driver's direct reference to a private test helper was replaced by
  selection of its exported named test action. This was a harness resolution
  error, not an inference acceptance failure.
- The initial incremental O2 receipt was incomplete/stale after an integration
  fix. All 93 comparable non-`Main.o` object files match final O2, but that is
  supporting intermediate evidence, not a substitute for a complete receipt.
  The final authenticated 78-test rerun above closes this provenance gap.
- Earlier core-only validation, including the graph aggregate and crate-query
  recursion case, is preserved in `Unsigned-Recursion-Core-Validation.md`.

## Receipts and independently rerun binaries

- O0 build receipt SHA-256:
  `61f5e563d87a99903d597d936eb8eff9d479b9add611a3ba69a3072ea717bf2c`.
- O2 build receipt SHA-256:
  `9695921936609d8836d1eab655b385d310ca1ee102959000a0e0f7ad8d78d955`.
- O0 focused binary SHA-256:
  `0f802e00ce9bb1c25b2755650899587cb56d8e9d5de67e9d1ae963e469786bac`.
- O2 focused binary SHA-256:
  `90f81b71d67ac2dbe93106f2863a38f25a0c884c9627b594c1704fcd7d052d30`.
- O0 smoke result SHA-256:
  `2e5f3ef5e2da1b83a3131b2e95a7c48713b88eff76c5ec86366e7f518ac2816a`.
- O2 smoke result SHA-256:
  `7157a165cafdc7b629701daa6fe23fa2deb1700700ad92d3fe0e67e77144ed25`.

- Final 78-class compatibility evidence SHA-256:
  `dbd4202b7f34713c5ef066c8eb7924d969587c1a39f5d49827940f43e5a53f71`.
- Final O2 `emlf` executable SHA-256 (used for that run and the audit):
  `f515b8e034cb5a479551d30d41f99093dc296e23a3ea42eb3ba58945138aa064`.
- Separate saved-crate host evidence SHA-256:
  `0106f1941d02c751356c9305779d0541b2fa1ab5bddfbe3dac42afc0997cda44`.
- Saved-crate host binary SHA-256:
  `05e69429c6f826516df1575e9892f480fad56ca240eb607359c5ea88d16bdb17`.
- Exact-fixture host source SHA-256:
  `11319ce1a06e07c7cbf4ea1715e8f9f080cc67ae519bc85fdd2ff5cec3ea1bb3`.

Complete receipts are under `.mlf-build/qualified-final-O{0,2}/receipt.json`;
retained focused/compatibility logs are under `.toolchain/logs/qualified-*`.
The separate saved-crate evidence is
`.mlf-build/qualified-host-crate-audited/result.json`. Its clean forced rebuild
and six-case run completed in 54.34 seconds; only ordinary GHC host compilation
was used, with existing host runtime objects.
The final class run's separate evidence is
`.mlf-build/qualified-typeclasses-final/result.json`; it executed against held
source `afb67f5`. Later handoff changes are documentation and a byte-identical
harness copy, not compiler changes.
The official project-local GHC installation and its verified archive checksum
are recorded with the core validation; no further software was installed.

## Exact remaining limits

- This is ordinary recursive inference, not unrestricted polymorphic-recursion
  inference. Required higher-rank/rigid annotations and signed polymorphic
  recursion remain supported; incompatible shared recursive uses still reject.
- It does not claim arbitrary cyclic-data inference or program termination.
- Known source-inference gaps remain outside this patch: polymorphic pattern
  fields can require redundant local revelation despite a valid manually checked
  target; an explicitly signed ordinary higher-rank let can be rejected without
  classes yet accepted after adding an unused class. The latter was dynamically
  reproduced on pristine PR #22. Inherited does not mean correct; both are
  documented separately rather than hidden behind the successful SCC tests.
- Cyclic separately compiled crate dependencies remain unsupported; successful
  cross-module recursion here is within one crate's inference/build unit.
- Qualified contexts retain distinct origin slots even when later types happen
  to match. No minimal-context, global context-minimization or principal-
  completeness theorem is claimed. The finite planner can have worst-case
  exponential origin growth; it has no arbitrary iteration cutoff.
- Evidence uses full argument identity, kinds, scopes and the existing visible
  instance inventory. A sole instance does not default an unknown argument.
- The full native/LLVM/GC campaign and all 742 Core executions were not run.
