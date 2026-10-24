# Unsigned recursive inference: final validation

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
5. All **78 existing typeclass tests** pass through the host interpreter
   (1147.82 seconds). This compatibility run used the incremental O2 executable
   built from the same compiler implementation as the final audited build;
   it is not presented as a final-receipt-authenticated executable run. Its
   original receipt is incomplete/stale after an integration fix. A retained
   byte-hash comparison verifies all 93 comparable non-`Main.o` object files
   match the final O2 build, including `Bootstrap.Classes`; this supporting
   comparison is not a replacement for a completed build receipt.
6. Three maintained terminating programs execute with exact expected stdout at
   O0 and O2: factorial (`720`), mutual recursion (`42`), and generalized
   dictionary recursion (`42`). These use the host interpreter, not native code.
7. Forty Python provenance tests pass, including a final rerun. The corpus-size
   guard was deliberately updated from 103 to 105 and asserts both new module identities/paths. Frozen
   `IndependentCheck`, `IndependentType`, and `CompilerCore.finishCompilation`
   are byte-unchanged from the pinned base. `git diff --check` passes.

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
The official project-local GHC installation and its verified archive checksum
are recorded with the core validation; no further software was installed.

## Exact remaining limits

- This is ordinary recursive inference, not unrestricted polymorphic-recursion
  inference. Required higher-rank/rigid annotations and signed polymorphic
  recursion remain supported; incompatible shared recursive uses still reject.
- It does not claim arbitrary cyclic-data inference or program termination.
- Qualified contexts retain distinct origin slots even when later types happen
  to match. No minimal-context, global context-minimization or principal-
  completeness theorem is claimed. The finite planner can have worst-case
  exponential origin growth; it has no arbitrary iteration cutoff.
- Evidence uses full argument identity, kinds, scopes and the existing visible
  instance inventory. A sole instance does not default an unknown argument.
- The full native/LLVM/GC campaign and all 742 Core executions were not run.
