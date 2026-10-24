# Shared-source bootstrap and CI launch integration

The maintained `.hs` sources are never sent to the released 0.3.0 parser. Native
and direct-GHC qualification are separate routes; neither route translates or
rewrites implementation source during a normal build.

## Native route

`scripts/bootstrap-shared.sh` verifies the committed frozen archive and its
per-file input manifest. It runs that archive's legacy bootstrap script with the
verified released compiler and manager. The resulting native bridge compiler and
matching manager build `emlf` and `mlfpkg` together from the current, exact source
paths. A fresh adjacent build runner is compiled from the current C source.

The launcher checks the implementation identity and process/typed-completion
capabilities. It records the source syntax, frontend semantics, builtin interface,
primitive ABI, raw source paths/hashes, seed/bridge/final tool hashes, and genuine
aggregate native build-report hash. Inputs are checked again after the build.
A failed run writes an incomplete receipt and removes published tool pointers;
a successful retry may reuse only the content-addressed bridge and compiler caches.
`bootstrap.json` explicitly leaves `fixed_point_qualified` false.

The existing async dispatch keeps its `stage2`, `manager.path`, compiler hashes
and capability outputs. `compiler.path` gives other release launchers the matching
shared-aware compiler rather than leaving them pointed at the released seed.
`bootstrap-manager.sh` uses this transition for old seeds. Already shared-aware
native portable-LLVM candidates can build the current manager directly. GHC tools
are explicitly rejected by the native release route. The native bootstrap also
places failing GHC/Cabal/Python sentinels first on its child command search path.

Linux, cold timed bootstrap, ordinary/extended PR smoke and checked-package
release consume the compiler pointer. Timed bootstrap retains its original seed
context and records the subsequent compiler separately. Its existing enclosing
manager-bootstrap measurement includes the entire frozen-bridge transition.
Normal candidate builds still require `--locked`; the new lock must be generated
and validated by the qualified shared-aware tools after source edits stop.

## Direct-GHC source smoke

The `native` job identifier is retained for the existing aggregate PR gate, while
its displayed name explicitly identifies GHC and the optimization level. Separate
O0 and O2 jobs install the official GHC 9.14.1 Debian 12 x86-64 bindist, pinned by
SHA-256 `60f7ab75f28df892729fbaff3a54f58ee3ad7e731929f1b2f3eb0208f73de841`.
The hash matches the previously installed, verified bindist used by the local
qualification environment and its GHCup metadata.

Ordered steps build the committed module inventory with `tools/shared/build.py`,
run the actual shared receipt helper executable, and then run the maintained
`MLF.Tests.PRQuickMain` executable. `source-smoke.sh` accepts it only with a
complete direct-build receipt containing the current manifest identity, every
shared module's actual resolved path/hash, host-input hashes and executable hash.
A stale binary, modified input, wrong source resolution or incomplete build is
rejected before the executable runs. This result is labelled
`direct-GHC-checkout-source`. Its receipt and source snapshots are retained.

The compatible-compiler interpreted smoke path remains available. It rejects the
released seed before interpretation when the shared inventory is present.
`native-ci.sh` rejects a direct runner or GHC-produced compiler so this fast path
cannot accidentally count as no-GHC native qualification.

The separate native async-language job still starts with the published native
seed and performs the entire frozen bridge and same-source native transition.
The workflows retain nested bootstrap reports, source/tool hashes, commands,
capabilities, direct-build receipts and failed-stage evidence. Timeout caps have
been expanded for the new work; they are execution limits, not measured promises.

## Baseline reconciliation

The source-smoke block of main commit `5999f937` was inspected read-only in the
existing `mlf-pr11-main21-sync` checkout. It matches this migration's inherited
source-smoke ordering: released-seed fetch, suite-receipt regression, then seed
interpretation. The updated workflow preserves the receipt regression but moves
it after a genuine current-source direct build. No unrelated main changes were
cherry-picked or copied by this integration.

## Evidence and remaining gates

Shell syntax, actionlint and the existing PR aggregate/workflow policy tests
passed after this integration. Existing legacy async bootstrap, source-smoke
watchdog/diagnostics, smoke receipt invalidation and shared dispatch mock tests
remain passing. New mock tests cover the frozen-bridge control sequence, no-GHC
sentinel, both final tool outputs, retries, source mutation rejection and direct
build receipt binding. These tests never compile or execute MLF.

The native archive refresh, released-seed bridge build, final native tool build,
regenerated lock validation, complete guest/async/TupleList campaigns and native
fixed point still require actual execution and source-bound passing evidence.
Likewise, wiring the GHC O0/O2 jobs does not establish that those whole-source
builds or tests pass. No heavy native or GHC build was run as part of this launcher
integration. This document does not establish merge readiness.

## Seed executable provenance

The bootstrap receipt now binds the actual native seed executable, not only a
shell launcher. The exact audited 0.3.0 launcher is recognized by its SHA-256;
other shell wrappers are rejected without execution. Official bundle paths and
direct `libexec` paths bind the complete bundle inventory, checksums and release
metadata. Both inputs must belong to the same verified release bundle; an
unbundled ELF/Mach-O executable is not proof of native-MLF producer identity and
is rejected, including a standalone GHC-produced package manager. Undeclared files, symlinks, unsafe checksum paths, modified payloads and
metadata disagreement fail closed. All recorded input bytes are checked again
before a successful bootstrap receipt is published.

`--verify-seed-only` exercises these input checks without building the bridge or
publishing tool pointers. It writes `complete: false`, with phase
`seed-verified-only`. This verifies consistency and records provenance; acquiring
the bundle from the authenticated official release and checking its external
release checksum remains the caller's responsibility. It is not a compiler
correctness or native bootstrap qualification.

Control tests must explicitly set `MLF_SHARED_BOOTSTRAP_CONTROL_ONLY=1` and mark
their shell fixtures. Their receipts carry `control_only: true` and a distinct
`mock-control/...` route, rather than claiming a released-native-seed run.

Run the provenance regression with an already verified bundle:

```sh
tools/release/test-shared-seed-provenance.sh /absolute/path/to/release-bundle
```

The regression copies the bundle into an owned temporary directory before
mutation checks; it never modifies the supplied bundle. It covers launcher and
direct-native inputs, undeclared files, changed payloads, symlinks, parent-path
traversal, inconsistent metadata and rejection without executing an unknown
wrapper. The orchestration regression separately covers control-only labeling,
seed-only non-completion, retries and source mutation rejection.

### Shared-aware local tools and timed callers

A qualified locally built shared-aware native compiler can bypass the released
bridge. This route requires both compiler and manager to answer
`--implementation-identity` with `MLF/shared-haskell-v1 native-MLF`; GHC or unknown
manager identities are rejected before a build. Rebuild an older manager with
`scripts/bootstrap-package.sh` using the qualified native compiler if it lacks
that query. The new manager entry point uses the same host-specific primitive
as the compiler, so a GHC-produced manager answers `MLF/shared-haskell-v1 GHC`.
Final outputs of the frozen bridge transition are checked for both identities.
These identity strings enforce the supported host route; they are not signatures
or cryptographic publisher authentication. Qualified input-tool evidence is
still required, and mutable bundle manifests alone do not establish origin.

The cold timed bootstrap now passes the actual seed compiler to manager-bootstrap
for shared-source checkouts instead of its generated timing wrapper. The complete
bridge transition remains measured by the enclosing `manager-bootstrap`
`time-command.sh` invocation and its RSS supervisor. Per-seed-compiler nested
measurements are no longer claimed for that transition. Subsequent candidate
builds retain compiler/linker wrappers using the newly produced compiler.
Legacy non-shared checkouts retain their earlier compiler-wrapper behavior.

`test-timed-shared-seed.sh` exercises the maintained timed-bootstrap and
bootstrap-manager callers through actual seed-only verification, with mocked
Darwin host probes/timing driver, then stops before compilation. It is not a
macOS run or performance qualification. `test-native-manager-identity.sh` checks
GHC/unknown rejection and explicit local-native-pair acceptance; passing an
actual GHC manager as its optional argument adds that real executable check.
