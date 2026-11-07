# Authenticated GHC-origin native bootstrap

This is the first Linux-only staging slice. It is not a release qualification,
not evidence of native A or B execution, and not a replacement CI pass.
The origin is an authenticated GHC 9.14.1 compiler **and manager** pair, followed
by native A and native B. The released-MLF origin is not required by this route.
Old seed inputs, failed attempts, and benchmark baselines remain untouched.

## Separate source and driver checkpoints

`tools/shared/bootstrap_ghc_native.py` accepts an explicit `--source-root`.
The GHC producer stays at its original absolute location. Its production modules,
configuration, builtin/prepared-library evidence, toolchain and outputs must still
pass `test_direct.authenticate_build(..., source_root)` without receipt rewriting.
`--checkpoint` pins that exact clean production checkout. `--driver-checkpoint`
pins the separate, clean checkout containing this driver and its validators.
Both roots and source checkpoints are immutable across a resume. When the roots
are identical, the driver checkpoint defaults to the source checkpoint.

Harness-only changes do not authenticate changed production modules. A changed
production input still requires a producer from the supported build route.
Neither copying producer receipts nor changing their path/hash fields is supported.
Producer reauthentication executes the original source root's pinned verifier bytes
at their original paths, including builtin/prepared/native-install helpers. It does
not relocate `verification_driver`, load timestamp-selected bytecode, or register
local helper modules in `sys.modules`.

## Required prerequisites (implemented, not yet actually collected)

The driver requires an independently pinned producer receipt, foundational gate,
and six-root plan receipt. `tools/shared/collect_ghc_native_prerequisites.py` implements the maintained
collector and strict read-back verifier. Its real execution and independent review
are still required before scheduling any native window. Existing campaigns are not
silently converted into these receipts.

- Six roots are `root` (`.`), `tests`, `testing-tools` (`testing/tools`), `async`
  (`libraries/mlf-async`), `tests-shared` (`tests/shared`), and `async-fixtures`
  (`tests/async-package`). Each needs genuine bounded no-change lock validation and locked
  plan commands, original command/log evidence, unchanged before/after lock hashes,
  and exact manifest/package/source hashes. The validation command is honestly
  recorded as `lock-validation` / `validate-no-change`, not as an executed lock
  writer. Stale or changed lock bytes stop admission before any compiler call.
- The foundational gate includes foundation, async, language-core and frontend.
  Its `inventory` must exactly equal `foundational_inventory(source_root)`: each
  crate's manifest path/hash and module-name-to-source-path/hash map. Counts are
  derived per package, not a magic total. On source c34996e these are 14+5+4+10=33.
  All required inputs must also be present in `inputs`; every result is cold
  (`reused_groups=0`). Successful old eight-library reports lack async and use a
  different schema. They remain supporting observations, not this prerequisite.
- The integrated strict verifier revalidates raw crate specs, query reports,
  original bounded commands, dependencies, complete artifact inventories, admission
  bindings and the final seal. Old summary-only receipts are rejected. The compiler
  calls are real cold `--compile-crate` operations, not native A/B qualification.

## Natural boundaries and truthful completion

Default mode remains authenticated dry-run. It never builds a helper or compiler.
Actual execution requires `--execute`, a release/reference note, exact clean
checkpoints and an explicit whole-window/output/workspace budget.

- `--execute --stop-after runner` authenticates native toolchain inputs and builds
  and tests only the scheduling helper. The legacy `--prepare-runner` is an alias
  for this boundary and now requires the same execution admission.
- `--execute --stop-after A` builds and verifies the native compiler and manager A,
  including their post-build native identities. This is the default execution stop.
- `--execute --stop-after B` additionally builds B from A, verifies both artifacts,
  native inputs and identities, and compares compiler **and manager** LLVM, object
  and binary hashes. Only all six equalities plus the unchanged native-input
  signature permit final compiler/manager pointer publication.

At runner/A boundaries, `status=paused`, `boundary_complete=true`, and the completed
stages are explicit in `stage_complete`. Overall `complete=false` and
`fixed_point_qualified=false` remain explicit. No public compiler/manager pointers
exist until B qualifies. Each boundary has an exclusively created immutable JSON
checkpoint. The evolving receipt retains its checkpoint path and hash.

Resume the same output with `--resume-sha256 <previous-receipt-sha256>`. The receipt
hash must be supplied out of band. The original checkpoint, every input/path
binding, command log and bounded receipt, environment, helper and any A artifacts
are revalidated. A's full stage verifier runs again before B. Completed commands
are not replayed. A resume must explicitly select B after A. Every output node must be a real
owned directory or singly linked regular file: symlinks, hardlinks and special
files are rejected, including unreferenced future sidecars and ancestors. The full
boundary inventory is pinned, so newly added files also reject admission. JSON and
pointer sidecars use exclusive creation rather than truncating an existing alias. Changing resource
windows for the next phase is recorded separately and does not change the source,
producer, environment or per-action command contract.

Rejected admission does not overwrite the original receipt. Failure after
execution begins records `status=failed`, `boundary_complete=false`,
`complete=false`, `fixed_point_qualified=false`, and preserves reports and outputs.
Failed/partial stages are **not resumable in this slice**. Do not retry them as a
new cold build without first reviewing their resource evidence.

## Isolation and resource controls

Every output namespace is canonical, initially empty, and owned by this attempt.
An exclusive invocation lock prevents concurrent writers. A hard-killed driver may
leave its lock: do not remove it until the owner and retained attempt are reviewed.
A and B caches remain separate and cold. HOME and TMPDIR are private subdirectories.
Ambient compiler, cache, loader and home overrides are not inherited. Recovered
Clang installations needing a non-system loader directory must select it with
repeatable `--loader-dir`; all files and symlink bindings in those directories are
pinned and checked again. Do not pass an unreviewed ambient `LD_LIBRARY_PATH`.

`--seconds` is the manager's per-action timeout, **not** the whole bootstrap budget.
`--window-seconds` sets an independent Linux alarm for the entire invocation and
bounds each remaining command. Cancellation tears down the watchdog and its
tracked descendants. Resource receipts retain failures, never synthetic success.

The watchdog monitors the entire output (`--output-root`), including prior stages
and caches, rather than only its command log. It also monitors allocated bytes of
`--workspace-root`, counting hardlinked inodes once. Defaults require at least
8 GiB free disk, 3 GiB host available memory, and 512 MiB reserved checkpoint space
inside the whole-workspace limit (default 16 GiB). The command subtree has explicit
RSS and per-process address-space limits. A separate whole-driver monitor includes
Python orchestration and observed descendants in its RSS budget, applies a Python
address-space soft limit, and checks resources throughout validation and after
receipt/checkpoint/pointer writes. Its recorded observations are sampling evidence,
not an OS allocation reservation. Native command and parent teardown both retain
PID/start identities and a bounded drain result; surviving owned processes prevent
success. The executed `nice` path is absolute and is the same file that was pinned.
Output/workspace caps are checked before
launch and after fast exits, as well as during commands. Filesystem failures other
than ordinary disappearing children fail closed.

## Proposed first native window, not authorization

After the collector has produced and independently validated real prerequisites,
the first proposed command is the following template. Every placeholder must be a
verified path/hash; the source and driver roots intentionally differ:

```sh
python3 -B <driver-root>/tools/shared/bootstrap_ghc_native.py \
  --source-root <original-package-root> --checkpoint <reviewed-production-checkpoint> \
  --driver-checkpoint <reviewed-driver-commit> \
  --producer-receipt <original-producer-receipt> --producer-sha256 <producer-hash> \
  --frontend-receipt <real-four-library-gate> --frontend-sha256 <gate-hash> \
  --plans-dir <real-six-root-plans> --plans-sha256 <plans-receipt-hash> \
  --clang <reviewed-clang> --gc-prefix <reviewed-gc> --loader-dir <reviewed-loader-directory> \
  --output <new-output-namespace> --execute --stop-after runner \
  --release-note <approved-window-reference> --seconds 21600 --window-seconds 120 \
  --max-output-mib 32 --workspace-root <whole-shared-workspace> \
  --workspace-limit-mib 16384 --checkpoint-reserve-mib 512 --disk-free-mib 8192 \
  --rss-mib 4096 --address-space-mib 8192
```

The next separately admitted observation may resume through A with a 3600-second
whole window and a 1024-MiB cumulative output cap, retaining all other pinned
inputs and using the new receipt digest. This is an observation budget, not a
completion estimate: a prior Crates-only GHC observation took about 1275 seconds,
and other dependencies, LLVM and linking remain. B gets a fresh resource review
based on measured A output. No native command was executed to validate this slice.

## Remaining adoption work

1. Independently review the maintained prerequisite collector, resolve stale locks
   in a reviewed source checkpoint, and run the six-root and four-library evidence
   collection. Static inspection of c34996e found five stale locks; only the root
   lock matches. No lock was rewritten or manager command executed in this slice.
2. Review this Linux staging implementation and resource feasibility before actual
   runner, A, then B windows. Keep failed evidence and do not publish incomplete pairs.
3. If partial A reuse is needed, define an additional evidence model: immutable
   per-attempt reports, authenticated original successful worker/context/artifact
   provenance, and normal-manager cache hits linked back to their first cold
   execution. Do not remove `cached=false` checks or rewrite failed reports.
4. Keep the existing macOS-first CI topology until a separately reviewed Darwin
   GHC/SDK/dylib/resource/A/B implementation has actually passed. Linux portable LLVM
   is not already a proved Linux-to-macOS materializer. No workflow is redirected here.
5. Require every existing one of the 14 qualification jobs, language/backend/async/
   completion/process/package checks, platform qualification and performance gates.
   Direct GHC binaries remain invalid for native-only consumers. Preserve performance
   baseline seed fetching where it is a comparison input rather than bootstrap origin.

## Source-only validation

`python3 -B tools/shared/test_bootstrap_ghc_native.py` and its `-O` variant test
stage/receipt/path/artifact rejection and mock orchestration. Watchdog controls
run only small Python/file/process tests. These are harness controls, not native
bootstrap evidence. The production shared manifest and module inventory are
unchanged by this slice, so no source-contract transition is claimed or needed.
