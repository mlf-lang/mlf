# CI: pull requests, main and releases

Test classification is recorded separately in
[`tests/test-catalog.json`](../tests/test-catalog.json). Its seven primary groups
are `language`, `code-generation`, `runtime-library`, `packages-build`,
`distribution`, `bootstrap` and `test-infrastructure`. Test level, inputs,
oracles and purposes are separate discovery/selection axes. The catalog selects
complete cases or families within Core, Harness, Backends and Port, batching
them by execution unit. The existing smoke commands and six full qualification
campaigns retain their selection boundaries and full evidence requirements.
Focused catalog selections produce partial reports and cannot stand in for a
complete qualification campaign. The extended framework receipt includes a
fourth, separately reviewed catalog-contract checkpoint, including selection
and evidence-mutation checks. The
[selection guide](../tests/README.md) and
[pre-merge family validation record](test-family-selection-validation.json)
describe the protocol and its verified historical scope. Fresh checks after
integrating the split libraries and parallel-build changes are recorded in the
[PR integration validation record](test-family-pr-integration-validation.json).
`smoke`, `full`, `stress` and `release` remain
execution-profile concepts; this workflow owns its actual CI selections.

The `CI` workflow runs on every pull request, merge queue group and push to
`main`. Its stable aggregate check is **PR gate**. It requires all of:

- **Release metadata**: version/manifest consistency, shell syntax, benchmark
  provenance, smoke-receipt failure regressions and checksum-pinned actionlint
  1.7.12 workflow validation.
- **Compiler source smoke**: five cases against the checkout compiler frontend
  and target checkers, interpreted by the verified published seed on Linux x64.
- **Native Windows runtime**: compact-GC runtime, filesystem and reproducible
  object/executable checks, plus 22 native build-runner lifecycle cases on Windows.
- **Native build runner**: all 22 scheduler and process-lifecycle cases on Linux.

The aggregate runs even when a prerequisite fails and requires all four
prerequisites to report `success`. Required jobs use Linux or Windows, so the
smaller macOS runner pool cannot queue the merge gate.
Failed, cancelled or skipped prerequisites cannot produce a passing gate.
There are no path filters on the required workflow. Manual dispatches retain
the Windows-only mode; either `full_validation` or the compatible `self_host`
input runs complete qualification, including Benchmark Game. Their skipped aggregate
is named **Manual CI summary**, so it cannot satisfy the required **PR gate**.

## Enforce before merging

Require **PR gate** from GitHub Actions in the branch protection rule or ruleset
for `main`. Enable the requirement for branches to be up to date, or use the
merge queue (`merge_group` is already supported). A workflow file cannot itself
configure repository branch protection.

## Required compiler source coverage

CI verifies the Linux x64 v0.3.0 seed archive, executables and source commit
from `.github/smoke-seed-linux.env`. Existing macOS jobs retain their separate
pin and the historical bootstrap default is unchanged. That seed interprets `tests/PRQuickMain.emlf`, importing the checkout's
`Bootstrap.Compiler`, current xMLF checker and frozen independent checker through
the split library search roots. It does not build new compiler, package-manager
or campaign executables.

Five fixed cases exercise:

- Two accepted programs: polymorphic let and self-application, compiled to xMLF
  with literal expected types. Serialized targets must pass both checkers and
  preserve erasure.
- Two rejected source programs, each requiring its exact inference-phase
  diagnostic.
- One malformed xMLF program rejected by both target checkers.

The required job therefore tests current frontend and target-checking sources.
It does not establish that the checkout builds native tools or that its current
LLVM backend and POSIX runtime execute programs correctly. Those checks, fresh
native package tests, the full Figure 12 corpus, framework/process contracts and
complete backend/state matrices remain in the separate jobs and full campaigns
below. The required Windows job still exercises the checkout's Windows runtime.

The separate required build-runner job compiles the C scheduler and fixtures
with strict warnings on Ubuntu 24.04. It checks bounded scheduling, protocol
validation, deadlines, cancellation and descendant cleanup. These process
checks do not require bootstrapping the compiler or package manager.

macOS still executes these same 22 lifecycle cases through `buildRunnerTests`
in the complete `packages` campaign on main/manual full CI and release
qualification. All six full campaigns and the native macOS builds are retained; this moves the required
pre-merge execution to Linux rather than treating a skipped macOS check as a pass.

## Automatic complete qualification on main

Every push to `main` invokes `native-qualification.yml` with `build_packages=false`.
It runs independently of the small PR gate, using read-only repository and Actions
permissions. Pull requests and merge queue groups keep the fast gate above.
Manual `CI` with `full_validation=true` exercises this exact complete graph on a
feature branch without creating SDK archives or publishing anything.

- Linux x64 and macOS ARM64 each execute all six full campaigns: `unit`,
  `packages`, `parity`, `backends`, `port` and `self-host`.
- The four checked port-preparation shards remain prerequisites of each port
  campaign. Native candidates, producer reports and original dependency receipts
  keep the existing source/platform/toolchain authentication and release gates.
- macOS also retains the eight direct CLI cases and three package/cache states,
  now using its already-built final candidate instead of another tool build.
- Windows retains its native fixed point, independent 7,086-case parity corpus,
  160 runtime executions, 52 package cases, compact-GC runtime checks and 22
  build-runner lifecycle cases. The six POSIX internal campaigns are not claimed
  as Windows coverage.
- A separate fresh macOS runner executes the complete ten-workload Benchmark
  Game. No other builds or benchmark measurements run on that runner during
  measurement. Other workflow jobs run on different hosted machines.

The benchmark compares C, the exact authenticated candidate and the immutable
v0.3.0 compiler in `.github/benchmark-baseline-macos.env`. The baseline archive,
source commit and both binaries are independently hash-pinned. LLVM, LLD, GMP,
BDWGC, pkg-config and PCRE2 10.49 come from the immutable Homebrew core/bottle
closure in `.github/macos-dependencies.env`. Adding benchmark dependencies does
not relax the shared candidate's byte-for-byte native-input checks.

The native MLF runner executes every independent correctness size and all
unchanged default inputs, seven samples per workload, fresh objects/binaries,
checked runtime warm-ups and alternating compiler order. Both MLF variants use
the same generic LLVM/linker backend; C retains its manifest flags. Explicit
arguments enforce **3x C compilation and 2x C runtime**. No workload filtering,
threshold relaxation or `continue-on-error` is allowed. A known regex-redux
performance failure stays a failed gate. Historical nine-workload reports do
not establish that the new complete ten-workload gate passes.

`benchmark-game-macos-arm64` retains results, raw outputs, executables, LLVM and
object hashes, commands, per-stage wall/CPU time and RSS, baseline/candidate and
native-dependency identities, OS/hardware context and helper configurations for
30 days, even on failure. The final report verifier rejects missing workloads,
changed inputs, missing samples/telemetry and inconsistent performance verdicts.
The always-running **Complete qualification gate** rejects failed, cancelled,
skipped, missing or pending prerequisite jobs. **PR gate** alone is not evidence
of a successful main qualification.

## Release-only SDK packaging and publication

The explicit release entrypoint calls the same graph with `build_packages=true`.
Only then do macOS/Linux packaging and Windows packaging/relocation execute.
Every existing six-campaign receipt check, candidate-identity check, SDK relocation
check and Windows source/dependency check stays in place. Publication depends on
the whole qualification graph, including the benchmark and package results.
Only the release wrapper grants `contents:write`.

Changing `.github/release-request.json` no longer publishes from a main push.
Dispatch **Native release** or **Cross-platform release** at the existing immutable
version tag and pass that same tag. The tag must resolve to the workflow's exact
SHA so artifact provenance cannot silently refer to a different source. A manual
`platform-release.yml` run with `validation_only=true` is an explicit release
rehearsal: it builds and relocates all SDKs but never publishes or creates tags.
Main CI already supersedes older runs on the same branch, including its complete
qualification workflow. Release rehearsals also cancel older rehearsals on the
same branch, even across different commits; other branches remain independent.
Actual releases are serialized by immutable tag and do not cancel an active
release. The reusable qualification workflow has no separate concurrency group,
so it cannot collide with its caller. Cancellation is not instantaneous: bounded
summary and diagnostic-upload steps may finish while workers clean up.
See [release instructions](releases.md). No branch-protection settings are changed.

## Run locally

On Linux x64 with GMP, jq and GitHub CLI, run the same source check as PR CI:

```sh
tools/release/fetch-seed.sh .mlf-build/pr-seed-linux .github/smoke-seed-linux.env
export MLF_COMPILER="$PWD/.mlf-build/pr-seed-linux/mlf-0.3.0-linux-x64/libexec/emlf"
export MLF_PACKAGE_MANAGER="$PWD/.mlf-build/pr-seed-linux/mlf-0.3.0-linux-x64/libexec/mlfpkg"
tools/release/native-ci.sh source-smoke
```

The existing Apple Silicon macOS local check remains available:

```sh
tools/release/fetch-seed.sh .mlf-build/pr-seed .github/smoke-seed.env
export MLF_COMPILER="$PWD/.mlf-build/pr-seed/mlf-0.3.0-macos-arm64/libexec/emlf"
export MLF_PACKAGE_MANAGER="$PWD/.mlf-build/pr-seed/mlf-0.3.0-macos-arm64/libexec/mlfpkg"
tools/release/native-ci.sh source-smoke
```

Use an unused seed-download directory. Each smoke invocation clears its success
receipt before argument, runtime-profile or native environment validation,
including when a smoke helper is invoked directly. Fifteen isolated regression
checks cover these early failures and missing seeds across all three smoke groups.
One further check verifies that the source wrapper needs no native build
dependencies and still blocks forbidden tools:

```sh
tools/release/test-smoke-receipts.sh
tools/release/test-source-smoke-diagnostics.sh
tools/release/test-pr-smoke-cli-watchdog.sh
```

Four additional supervision checks exercise successful completion, failed
optional memory probes and timeouts before and after harness progress, including
cancellation between launching a watchdog sleep and recording its PID. Watchers
terminate and reap their owned background jobs even in that launch window. Two
CLI supervision checks exercise cancellation while launching the initial and
grace-period watchdog sleeps, preventing orphan children from keeping the CLI
output pipe open. The release metadata check runs these regressions too.
GHC, Cabal and Python are blocked on the native CI path.

To build fresh checkout tools and run the eight CLI and three package checks,
also install LLVM, BDWGC and pkg-config:

```sh
tools/release/native-ci.sh pr-smoke
```

Each full smoke invocation requires a fresh manager bootstrap directory. Before
repeating it, move the previous `.mlf-build/pr-smoke/` directory aside or use a
clean worktree. The three package checks verify cache reuse within the invocation.

For the previous, broader smoke campaign, use the same seed environment and run:

```sh
tools/release/native-ci.sh extended-pr-smoke
```

It retains the native `compiler-tests` runner, framework and process probes,
focused `int-set-unions` suite, all Figure 12 regressions, four frozen independent
checker controls, 12 backend fixtures and three package/cache states. Its evidence
is separate under `.mlf-build/extended-pr-smoke/`. Its checkout manager builds
the explicit test targets with the shared checked cache; the campaign receives
that manager through `--manager` and records the native helper separately. The
six full root groups and release qualification are unchanged.

## Timing and evidence

The required **Compiler source smoke** job has a twenty-minute hard limit, including
dependency setup, seed verification and evidence upload. It installs only GMP;
interpreting the harness does not need LLVM, BDWGC development files or pkg-config.
The collector uses `GC_FREE_SPACE_DIVISOR=2`. A local run passed in 115 seconds
(67 user CPU seconds) with a 4.27 GB peak resident set. Divisor 4 used about
100 user CPU seconds and 3.1 GB on the same host. These runs support trading
some memory for less collection work within the hosted runner's 7 GiB capacity.
Hosted timing is recorded in each run's evidence; the job limit is a failure
bound, not a promised duration.

In CI run [39804551882](https://github.com/mlf-lang/mlf/actions/runs/39804551882),
the required source-smoke command passed in **4m47s** (287 seconds), and its
complete job took about **5m38s**, including setup and evidence upload. Release
metadata, Native Windows runtime and the aggregate PR gate also passed. The
[source evidence artifact](https://github.com/mlf-lang/mlf/actions/runs/39804551882/artifacts/12437892242)
records the tested merge commit and source/seed/output fingerprints.

A later [run 39816731269](https://github.com/mlf-lang/mlf/actions/runs/39816731269)
reached the 480-second command deadline before producing case output, with the
same compiler sources, seed and runner image. Host, process and case-progress
logs were added afterward to distinguish future slowdowns; the successful run
alone does not establish a stable hosted duration. The instrumented
[run 39832295778](https://github.com/mlf-lang/mlf/actions/runs/39832295778)
also timed out before the first case: the seed accumulated over seven minutes
of CPU time, sampled RSS reached 3 GB, and no host swap activity was recorded.
Both timeouts used divisor 4. This motivated divisor 2 without increasing the
command deadline or reducing case coverage. The source job in
[run 39834466286](https://github.com/mlf-lang/mlf/actions/runs/39834466286/job/120018993499)
passed all five cases in **5m30s** (330 seconds) at divisor 2 with identical output
hashes. That run's metadata check exposed the watchdog cleanup race, now covered
by the deterministic supervision regression above.

Later source checks on [main run 39865876405](https://github.com/mlf-lang/mlf/actions/runs/39865876405)
and [PR run 39881997979](https://github.com/mlf-lang/mlf/actions/runs/39881997979)
reached the same 480-second deadline before harness progress at divisor 2. The
PR smoke import closure and script were byte-identical to main. Both seeds
accumulated over seven minutes of CPU time; the retained host logs show heavy
memory compression without swap. The command budget was raised to 900 seconds
for a controlled complete startup measurement, with a twenty-minute job limit
for setup and evidence upload. The subsequent [hosted run 39884741365](https://github.com/mlf-lang/mlf/actions/runs/39884741365)
completed all five cases in 454 seconds on PR #10's pre-integration tree. This
single run finished within the previous 480-second budget; the larger bound is
headroom for startup variability, not a measured speedup or an integrated-tree
qualification result.

In CI run [39798088020](https://github.com/mlf-lang/mlf/actions/runs/39798088020),
the fresh-native smoke command completed in **16m49s** (1,009 seconds): checkout
tool building took **16m17s** (977 seconds), and the remaining smoke checks and
evidence recording took **32 seconds**. In the earlier
[run 39768304978](https://github.com/mlf-lang/mlf/actions/runs/39768304978), the
command took 36m42s and the native job took 37m39s. That campaign built a smoke
executable and two backend drivers; the smaller native suite removes those auxiliary
builds. Fresh native runs remain dominated by building the checkout tools, which
is why they run separately from the required source check.

These are individual hosted observations at different source revisions, not a
controlled benchmark. The 16m49s run predates integration of package-distribution
support. It is not a timing measurement of the new required source check or of
the complete native and package validation jobs.

The source job uploads `source-smoke-evidence` on success or failure: source,
tool and output hashes, logs, emitted targets and its completion receipt under
`.mlf-build/source-smoke/`. `host.log` records CPU and memory capacity;
`process.log` samples the seed's elapsed time, CPU time/utilization and RSS every
30 seconds, while `memory.log` records host load, swap and paging counters.
`progress.log` records which case the interpreted harness is running.
Its absence means the harness has not reached the first case. Timeouts print the
last recorded stage (or its absence) and leave the receipt incomplete. The
command deadline is 900 seconds, within the twenty-minute job limit. This bounded
startup measurement preserves all five cases, source/seed/output hashes and
watchdog cleanup.

The former fresh-native job is now covered by the complete candidate build and
the direct CLI/package checks in `candidate-macos-arm64-diagnostics`. Local
`pr-smoke` remains available and retains its original reports. The timings above
are historical observations, not measurements of the new complete graph.

The required Linux build-runner job has a ten-minute limit and retains its log,
task plans and results in `build-runner-evidence-ubuntu-24.04`. macOS lifecycle
logs remain in the full package campaign evidence. Windows retains its task
plans and results alongside the runtime verification report. Full qualification artifacts retain their original build reports, primary
verification receipts, coverage and diagnostics. Bootstrap timing artifacts
record the seed generation; benchmark samples record separate wall/CPU/RSS data.
