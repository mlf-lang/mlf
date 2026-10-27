# Versions and releases

> Historical evidence notice: Raw files previously stored under
> `tools/profile/results/` were removed from this branch and its Git history.
> References to those files below describe historical evidence that is not
> available in this repository; retained summaries are not independent access
> to the original raw records.


`VERSION` is the toolchain's version. Native package manifests use the same
three-component version. Release tags are `vMAJOR.MINOR.PATCH`. Published tags and assets
must never be replaced; make a new patch release to correct a package.

Before 1.0, patch releases preserve documented behavior and minor releases may
change language or package interfaces. Version 0.1.1 is a developer preview.
It has no stability or cross-platform performance guarantee. Version 0.2.0
adds native Windows x64 and Linux x64 packages alongside macOS ARM64. Version
0.3.0 uses compact-GC for every native build and requires BDWGC; regenerate
LLVM/object files previously built with the removed standard layout.

## Install a release

The public release contains `mlf-VERSION-windows-x64.zip`,
`mlf-VERSION-macos-arm64.tar.gz`, `mlf-VERSION-linux-x64.tar.gz`, and one
`SHA256SUMS` file covering all three archives. Published assets and tags are
immutable. Download the archive matching the host and verify its checksum.

Windows users extract the complete ZIP and, in PowerShell 7, run:

```powershell
. ./mlf-0.3.0-windows-x64/Activate.ps1 -Clang C:/path/to/mingw/bin/clang.exe
emlf --version
mlfpkg --version
```

The ZIP includes native GMP, BDWGC, pkg-config, import libraries, headers and
the runtime DLLs. Native linking needs a MinGW-targeting Clang. PowerShell is
used by activation and build helpers; the compiler and manager are native `.exe`
files and do not require WSL, Cygwin or an MSYS shell.

Linux x64 builds target Ubuntu 24.04 (glibc 2.39). Install runtime dependencies
`libgmp10 libgc1`; native builds also need `clang libgmp-dev libgc-dev pkg-config`.
Extract the Linux tarball, run `./install.sh "$HOME/.local"`, and add
`$HOME/.local/bin` to `PATH`. The versioned installer checks file hashes,
supports repeat installation, and preserves unrelated commands.

For Apple Silicon on macOS 26+, use:

```sh
brew install gmp llvm pkg-config bdw-gc
mkdir mlf-download && cd mlf-download
gh release download v0.3.0 --repo mlf-lang/mlf \
  --pattern 'mlf-0.3.0-macos-arm64.tar.gz' --pattern SHA256SUMS
grep '  mlf-0.3.0-macos-arm64.tar.gz$' SHA256SUMS | shasum -a 256 -c -
tar -xzf mlf-0.3.0-macos-arm64.tar.gz
./mlf-0.3.0-macos-arm64/install.sh "$HOME/.local"
export PATH="$HOME/.local/bin:$PATH"
emlf --version
mlfpkg --version
emlf --type --expr '\x -> x'
```

The compiler and package manager do not need GHC, Cabal, or Python. GMP is a
dynamic dependency. Clang, GMP headers, and pkg-config are needed for native
linking; all native package builds also need BDWGC. The installer keeps
versioned directories, validates file checksums, and preserves unrelated commands.
Installed launchers provide `--version`; the validated native binaries remain
unchanged. Keep the whole package when using its `bin` directory directly.

## Prepare the next release

Every push to `main` automatically runs complete native test qualification and
the ten-workload Benchmark Game. SDK packaging and publishing happen only in
explicit release runs. See [the CI policy](ci.md) for the exact platform coverage,
immutable benchmark inputs and fail-closed performance gate.

For a release on all three platforms, update `VERSION`,
`libraries/mlf-foundation/Bootstrap/Version.emlf`, the toolchain manifests,
and `CHANGELOG.md`, then regenerate `mlf.lock` and commit the reviewed candidate.
After its complete qualification passes, create the immutable annotated version
tag. Dispatch **Native release** or **Cross-platform release** at that same tag,
passing it as `tag`. The workflow checks that its own source SHA is the tagged
commit, reruns complete qualification and Benchmark Game, then packages and
relocates all three SDKs before publishing. Existing tags/releases/assets are
never replaced; the workflow does not create tags. A change to
`.github/release-request.json` alone no longer triggers publication.

To qualify a CI change without publishing, push its feature branch and dispatch
**Cross-platform release** on that branch with `validation_only=true` and no
`tag` input:

```sh
gh workflow run platform-release.yml --repo mlf-lang/mlf \
  --ref YOUR_FEATURE_BRANCH -f validation_only=true
```

Validation checks out the dispatch's exact `github.sha`, runs every POSIX and
Windows qualification and all three package relocation checks, and verifies
the packaged commits. The publishing job is skipped. The final
`validation-summary` artifact records the source, run and archive hashes. This
mode never creates a release or changes a tag.

Linux bootstraps one candidate pair per run. macOS prepares its qualification
pair once. Each platform then builds the shared test libraries and port
executable once, and archives their actual content-addressed artifacts with the
unchanged producer reports and dependency receipts. Consumers authenticate the
artifact's workflow run, source and ZIP digest, then check its platform, absolute
workspace, compiler/manager, native toolchain, runtime and dependency hashes.
Ordinary package builds still validate artifact bytes and transitive crate
proofs; a source, flag, ABI or toolchain difference cannot authorize a cache hit.
No native outputs cross platform boundaries and no test execution verdict is
shared. All six groups execute independently against the same candidate pair,
and self-host uses a fresh cache for the next stage.

Port target preparation is divided into four native prerequisite jobs on each
platform: `StateTypes`, `SolverReuse`, `InferenceConformance`, and the other 22
fixtures. Each runs the original source inference, independent target typing,
serialization/erasure and transported-target checks in a fresh preparation.
Only genuine checked-target cache outputs and their original build reports are
transported. Their archives bind the source, platform, workspace, candidate,
checker, target bytes and check receipts. The final port group re-enters the
ordinary checked-artifact cache gates and executes all 25 native fixtures,
independent references and audit checks. Its evidence retains the prerequisite
reports as well as its own fresh execution verdict.

The macOS unit group and all four port preparation jobs obtain runners before
a small Ubuntu start barrier admits the other four qualification groups. The
barrier accepts started or completed jobs regardless of their verdicts, so every
group still executes independently; matrix ordering alone does not provide
runner priority. Each platform packages as soon as its own six groups finish.
Port preparation applies the host memory
collection allowance to `StateTypes`, `SolverReuse` and `InferenceConformance`,
records each fixture's policy in its build
identity, and retains all independent target checks. Other preparation and
native builds keep their ordinary collection policy. Small transports remain local because their
subsecond cost does not justify another artifact transfer.

For measurements, save the run and jobs REST responses and download the run's
logs, then run `node tools/release/measure-ci.mjs RUN.json JOBS.json LOG_DIRECTORY`.
The report separates runner and queue time, candidate/prerequisite builds,
execution, packaging and artifact work. It reports aggregate runner seconds
without OS billing multipliers; parallel build or queue durations must not be
subtracted directly from workflow wall time. Historical benchmark sources,
measurements, pins and thresholds remain separate and unchanged.

The **Native bootstrap timing** workflow also accepts `profile_port_only=true`,
`candidate_run` and the exact `candidate_source`. This diagnostic mode imports
the authenticated candidate and materializes its original port executable
through the ordinary cache gates. It measures fresh `SolverReuse` and
`InferenceConformance` preparations with collector settings 1, 2 and 4, records
elapsed time, peak resident memory and executable/target/check hashes, and
retains every independent preparation check. These measurements are not
qualification verdicts and are never reused by release gates. The default
timing mode still performs the original cold native bootstrap.

Qualification artifacts are downloaded individually, checked against their
recorded SHA-256 digest and workflow source, then extracted sequentially. This
also supports parity archives containing thousands of diagnostic files on
macOS hosts with a small open-file limit.

If qualification succeeds but macOS artifact extraction fails, the manual
**Recover qualified release packaging** workflow accepts the original run ID
and exact source commit. It requires successful jobs for all twelve POSIX
groups, Windows qualification/packaging and the Linux package. It preserves
those original binaries and reports, repeats all macOS package evidence and
relocation checks, then publishes the original qualified source with the
existing Linux and Windows archives. It does not certify the infrastructure
commit as a new compiler candidate or replace a published release.

The bootstrap starts with independently pinned macOS native tools. Checked
LLVM from the new macOS build is hashed and transported as a workflow artifact;
Linux and Windows compile it with their native C runtimes, then rebuild the
toolchain natively. No compiler inference/checking is bypassed. Linux and
macOS require all six native compiler groups and a fresh self-host fixed point.
Windows requires fresh compiler and manager LLVM fixed points, 7,086 independent
parity cases and 160 interpreter/native executions, compact-GC runtime tests,
22 native resolver checks, 29 native package integration cases, the separate
target-dependency/scheduler fixture, and SDK relocation and native executable
checks. Its internal POSIX `compiler-tests` transports and historical
performance gates are not claimed as Windows qualification. Each archive
retains the exact source/tool hashes and platform evidence.

The PR compiler smoke uses the separate `.github/smoke-seed.env` pin for
released compact-GC tools compatible with the current runtime. Its archive,
source commit and both executables are checked. `.github/seed.env` remains the
historical cold-bootstrap anchor for release qualification and comparisons.

The **Native release** manual entry delegates to the same three-platform
workflow, so it cannot publish a macOS-only release. Historical macOS previews
used the following sequence:

1. Update `VERSION`, the four toolchain manifests, and `CHANGELOG.md`.
2. Run `./mlfpkg lock`, review the lock changes, and commit the release candidate.
3. Create an annotated version tag and push it. Tags are never moved.
4. Run the **Native release** workflow at that exact tag, passing the same tag. It runs all six
   native groups independently, checks their compiler hashes and source snapshots,
   verifies a fresh self-host fixed point, tests relocation and installation,
   then uploads a new developer-preview release with SHA-256 checksums.

Pull requests and merge queues retain the six-check **PR gate**: metadata,
Linux source smoke, Linux native build-runner checks, Windows runtime checks,
Linux async completions and scope-aware async-language parity. Only verified
unrelated pull requests can omit the expensive parity steps; merge queues and
main/manual runs always execute them. Main/manual
runs retain direct macOS runner/supervisor and both async checks; the complete
package campaign also executes the static lifecycle cases.
Main pushes now run all six complete campaigns on Linux and macOS, Windows
native qualification and the complete ten-workload benchmark automatically.
`full_validation` and the compatible `self_host` CI inputs run the same complete
graph manually. These checks are distinct from SDK packaging; only release or
explicit release-rehearsal runs enable package/relocation steps. All primary
receipts, candidate/source identities and SDK gates remain required.
See [CI policy](ci.md) for the precise coverage and artifact contract.
When the code generator changes, an intermediate native generation is built
from the pinned seed before building the candidate tested by all six groups.
This lets the candidate and its fresh self-build use the same updated generator.
Bootstrap builds explicitly allow six hours; individual fixture limits remain
unchanged. Native release publication still requires every group to pass.
No workflow installs GHC. Compiler, parity and package qualification run in
native MLF on every supported platform. The Linux unit job uses Python only
for external process-tree timing and memory telemetry; it is not a compiler,
build system or test harness dependency. Seed
downloads check the selected published archive checksum and both
independently pinned native executable hashes. Full release/self-host bootstraps
retain the independently pinned v0.3.0 in `.github/seed.env`. Release jobs
read seed pins and verification/timing tools from the workflow's immutable
commit, so an older target tag cannot silently select its old seed. The checksum
file can also cover supplementary validation archives that are not downloaded
for bootstrapping. The [three-pair seed comparison](../tools/profile/results/2026-10-19-seed/README.md)
measured a 16.326% lower local median full bootstrap time; hosted timing remains
a separate measurement.

To diagnose bootstrap time without running tests or another compiler generation,
dispatch **Native bootstrap timing** (`gh workflow run bootstrap.yml --ref main`).
It runs one cold seed build on `macos-26`, with the usual compiler and Clang flags.
Each MLF and Clang invocation retains its full arguments, wall/user/system time,
peak RSS, page-fault counts, exit status, and raw `/usr/bin/time` output. The
artifact also includes the native `build-report.json`, command logs, cache
manifests, source/tool hashes, host details, and a summary. LLVM compilation and
linking remain one Clang command. The enclosing package-manager measurement
includes the child commands and must not be added to their totals. Ordinary CI
self-host and native-release bootstrap steps retain the same evidence, including
on failure; started commands without a result record were interrupted.

Current compiler builds resolve each crate together and infer declaration SCCs,
releasing their inference graphs between queries. Checked metadata, fragments,
dependency boundaries and the final linked xMLF remain mandatory. See
[crate compilation](crate-compilation.md) for the current contract and
[the migration ledger](crate-migration.md) for validation and performance evidence.

The earlier per-module compiler was measured in three local cold build pairs: sampled
aggregate RSS fell from a 9.99 GB median to 3.27 GB (maximum 3.28 GB), while
median full build time rose from 332.38s to 460.87s. The
[memory report](../tools/profile/results/2026-10-19-bootstrap-memory/README.md)
records the tradeoff and the limits of extrapolating to a hosted runner.
A subsequent cold build on the actual 7 GiB hosted runner passed in 995.59s,
at 2.73 GB maximum process RSS, reproducing both locally tested binaries exactly.

The timing helper defaults `MLF_BOOTSTRAP_MAX_RSS_BYTES` to `5500000000` and
fails before publishing candidate paths when a measured command exceeds that
budget. This is a per-command RSS high-water guard, not a hard heap cap or an
aggregate process-tree limit. `0` disables this resource gate for diagnostics.
Explicit caller settings are respected. Crate builds and older separate-module
seed builds keep the runtime's
`GC_FREE_SPACE_DIVISOR=1` policy; immutable older target tags that still request
source linking default to `4`, collecting more frequently. Successful bootstrap
steps pass that policy to subsequent CI steps. No maximum heap size is imposed.
The diagnostic seed comparison driver explicitly keeps divisor `1` and disables
the resource gate by default so historical comparisons retain their conditions
and all over-budget samples.

For local packaging, after all six groups pass on the same candidate:

```sh
tools/release/package.sh .mlf-build .mlf-build/release \
  /path/to/bdwgc/README.QUICK
```

This script refuses a dirty checkout, stale or missing sources, mismatched
compiler hashes, incomplete groups, altered primary logs, and a reused self-host
build. It packages the tested executables, runtime sources, third-party notices,
release metadata, and native evidence. `tools/release/smoke.sh` tests a relocated
install in a path with spaces, modules, interpreter/LLVM output equality, native
package tests, safe reinstall, and preservation of unrelated commands.

The first seed archive is assembled locally from the retained six-group native
validation. Its executables match `docs/native-tests-validation.json`; subsequent
releases use that published native seed. This establishes the initial bootstrap
anchor without introducing a GHC or Python dependency in CI.

The historical Haskell/Python release and benchmark launchers have been
removed. Use the [native benchmark runner](../tools/bench/README.md) for current
C/MLF performance comparisons. The native developer-preview workflow above
validates compiler correctness and self-hosting; performance remains a separate
gate. Pinned C/Rust/Haskell baseline sources remain available.
Existing benchmark reports retain their original source, binary, and host scope.

### Stable macOS qualification dependencies

All macOS stages of the cross-platform qualification use
`tools/release/setup-macos.sh` with the immutable Homebrew core revision in
`.github/macos-dependencies.env`. The script installs the pinned formula's
macOS 26 ARM64 bottles and their runtime dependency closure. It disables
mutable API/automatic-update resolution, uses its own clean formula checkout
while preserving the runner image's original tap, and reinstalls existing packages,
including matching versions, because a bottle rebuild can change bytes without
changing a package version. This setup is restricted to disposable GitHub-hosted
runners; it must not change a developer's Homebrew installation.

To update dependencies, review and update the core commit pin. The path-filtered
`Pinned macOS dependencies` workflow must then pass: it installs independently
on two hosted runners, compares every installed native dependency file, and
compiles and runs a small LLVM/GMP/BDWGC program. Shell fault tests run with
release metadata checks. Full qualification remains required evidence for the
compiler itself. Shared-candidate native input hashes and path checks stay
unchanged and still reject any mismatch.
