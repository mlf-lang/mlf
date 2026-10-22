# Pull request checks

The `CI` workflow runs on every pull request, merge queue group and push to
`main`. Its stable aggregate check is **PR gate**. It requires all of:

- **Release metadata**: version/manifest consistency, shell syntax, benchmark
  provenance, smoke-receipt failure regressions and checksum-pinned actionlint
  1.7.12 workflow validation.
- **Compiler source smoke**: five cases against the checkout compiler frontend
  and target checkers, interpreted by the verified published seed on macOS arm64.
- **Native Windows runtime**: compact-GC runtime, filesystem and reproducible
  object/executable checks on Windows.

The aggregate runs even when a prerequisite fails and requires all three jobs
to report `success`.
Failed, cancelled or skipped prerequisites cannot produce a passing gate.
There are no path filters on the required workflow. Manual dispatches retain
the optional self-host and Windows-only modes, plus `full_validation` for fresh
native builds and the complete package suite. Their skipped aggregate
is named **Manual CI summary**, so it cannot satisfy the required **PR gate**.

## Enforce before merging

Require **PR gate** from GitHub Actions in the branch protection rule or ruleset
for `main`. Enable the requirement for branches to be up to date, or use the
merge queue (`merge_group` is already supported). A workflow file cannot itself
configure repository branch protection.

## Required compiler source coverage

CI verifies the pinned v0.3.0 seed archive, executables and source commit. That
seed interprets `tests/PRQuickMain.emlf`, importing the checkout's
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

## Separate native and package validation

**Fresh native compiler smoke** and **Native package distribution** run after
the source check on pushes to `main`, or when a manual CI dispatch enables
`full_validation`. They do not run on ordinary pull requests or merge queue
groups and are not prerequisites of **PR gate**. Windows-only dispatches skip
both. Waiting for the source check prevents these slower macOS jobs from queuing
ahead of it within the same workflow run.

Fresh native builds first use `tools/release/bootstrap-manager.sh` to compile
the checkout manager from library crates with a seed-compatible manifest. This
bridge permits the published seed to bootstrap manifests with explicit target
dependency selections. The resulting manager uses the current C runtime,
checked lockfile and adjacent `mlf-build-runner` helper to build the checkout
`emlf` and `mlfpkg` targets. The native job then runs eight direct CLI cases:

- Two accepted programs with checked xMLF and literal expected types.
- Two source rejections with expected diagnostics.
- Three IO programs on the interpreter and compact-GC LLVM: signed/unbounded
  arithmetic, lazy branches/constructors/closures, and repeated input with
  Unicode. Each backend must match a checked-in literal output oracle.
- One malformed xMLF program rejected before effects by both execution paths.

Its local-package example runs on both backends in three states: a fresh build,
unchanged cache reuse, and a dependency implementation edit with changed output.
The last state must rebuild the dependency and both downstream crates. Mutation
uses a private copy; the checkout stays unchanged. Reports from all three states
are retained, and empty or incomplete reports cannot pass.

The package-distribution job verifies the published compiler pinned in
`.github/package-seed.env`, then builds the checkout `mlfpkg` and
`compiler-tests` executables with the checked lockfile. The campaign receives
that manager explicitly and runs 22 resolver checks, 29 package integration
cases, the target-dependency/scheduler fixture and 28 checked-release/distribution
cases. Completed cases must match
the reviewed structural inventory. The metadata job also runs eight publishing
regression checks without creating releases.

The workflow retains `package-distribution-evidence` on success or failure,
including build and verification reports, command diagnostics, coverage,
reviewed inventory and cache metadata. The package job has a 90-minute hard
limit. All 79 structured package cases, the separate target-dependency/scheduler
fixture and 22 native runner checks remain intact; this job runs separately from
the required checks.

## Run locally

On Apple Silicon macOS with GMP, jq and GitHub CLI:

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

That build can be repeated; ordinary source/tool fingerprints validate cache reuse.

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

The required **Compiler source smoke** job has a ten-minute hard limit, including
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
eight-minute command deadline and ten-minute job limit remain unchanged.

The fresh-native job uploads `pr-smoke-evidence`,
including build reports, command logs, output and completion receipts. Local evidence is under
`.mlf-build/pr-smoke/`; `result.json` records integer wall-clock seconds for tool
building and the complete command, plus tool and report SHA-256 fingerprints.
The fresh-native job retains a 60-minute hard failure bound.
