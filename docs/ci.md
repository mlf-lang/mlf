# Pull request checks

The `CI` workflow runs on every pull request, merge queue group and push to
`main`. Its stable aggregate check is **PR gate**. It requires all of:

- **Release metadata**: version/manifest consistency, shell syntax, benchmark
  provenance and checksum-pinned actionlint 1.7.12 workflow validation.
- **Native compiler smoke**: a checkout compiler/manager build followed by eight
  direct CLI cases and three package/cache states on macOS arm64.
- **Native Windows runtime**: compact-GC runtime, filesystem and reproducible
  object/executable checks on Windows.

The aggregate runs even when a prerequisite fails and accepts only `success`.
Failed, cancelled or skipped prerequisites cannot produce a passing gate.
There are no path filters on the required workflow. Manual dispatches retain
the existing optional self-host and Windows-only modes. Their skipped aggregate
is named **Manual CI summary**, so it cannot satisfy the required **PR gate**.

## Enforce before merging

Require **PR gate** from GitHub Actions in the branch protection rule or ruleset
for `main`. Enable the requirement for branches to be up to date, or use the
merge queue (`merge_group` is already supported). A workflow file cannot itself
configure repository branch protection.

## Required native smoke coverage

The pinned v0.3.0 seed is only a bootstrap input. CI verifies its archive,
executables and source commit, then builds only the checkout `emlf` and `mlfpkg`
targets with the current C runtime and checked lockfile. The smoke scripts invoke
these new binaries directly, avoiding a second compiler-library build, native
test executables and backend drivers.

Eight fixed CLI cases exercise:

- Two accepted programs: polymorphic let and self-application, compiled to xMLF
  and checked against literal expected types.
- Two rejected source programs, each requiring its expected diagnostic.
- Three IO programs on the interpreter and compact-GC LLVM: signed/unbounded
  arithmetic, lazy branches/constructors/closures, and repeated input with
  Unicode. Each backend must match a checked-in literal output oracle.
- One malformed xMLF program rejected before effects by both execution paths.

The local-package example runs on both backends in three states: a fresh build,
unchanged cache reuse, and a dependency implementation edit with changed output.
The last state must rebuild the dependency and both downstream crates. Mutation
uses a private copy; the checkout stays unchanged. Reports from all three states
are retained, and empty or incomplete reports cannot pass.

This is a small integration gate. It does not run the full Figure 12 corpus,
frozen independent target checker, framework/process contracts, or full backend
and state-mutation matrices. Those checks remain in the extended campaign and
full release groups; their test cases and evidence validation are unchanged.

## Run locally

On Apple Silicon macOS with LLVM, GMP, BDWGC, pkg-config, jq and GitHub CLI:

```sh
tools/release/fetch-seed.sh .mlf-build/pr-seed .github/smoke-seed.env
export MLF_COMPILER="$PWD/.mlf-build/pr-seed/mlf-0.3.0-macos-arm64/libexec/emlf"
export MLF_PACKAGE_MANAGER="$PWD/.mlf-build/pr-seed/mlf-0.3.0-macos-arm64/libexec/mlfpkg"
tools/release/native-ci.sh pr-smoke
```

Use an unused seed-download directory. The smoke build can be repeated; ordinary
source/tool fingerprints validate cache reuse. Each invocation clears its success
receipt before building. GHC, Cabal and Python are blocked on the native CI path.

For the previous, broader smoke campaign, use the same seed environment and run:

```sh
tools/release/native-ci.sh extended-pr-smoke
```

It retains the native `compiler-tests` runner, framework and process probes,
focused `int-set-unions` suite, all Figure 12 regressions, four frozen independent
checker controls, 12 backend fixtures and three package/cache states. Its evidence
is separate under `.mlf-build/extended-pr-smoke/`. The six full root groups and
release qualification are unchanged.

## Timing and evidence

In CI run [39768304978](https://github.com/mlf-lang/mlf/actions/runs/39768304978),
the earlier native job took 37m39s: the checkout tools took 17m51s, the smoke
executable took about 15 minutes, and two backend drivers took about three
minutes. The test assertions and package cases took less than a minute. The
smaller gate removes those auxiliary builds; cutting only the fixture count
would save little. Cold runs still need to build the checkout tools, so a target
near 20 minutes is an estimate until measured on the hosted runner.

The workflow uploads `pr-smoke-evidence` on success or failure, including build
reports, command logs, output and completion receipts. Local evidence is under
`.mlf-build/pr-smoke/`; `result.json` records integer wall-clock seconds for tool
building and the complete command, plus tool and report SHA-256 fingerprints.
The native job retains a 60-minute hard failure bound.
