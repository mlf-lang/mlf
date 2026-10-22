# Pull request checks

The `CI` workflow runs on every pull request, merge queue group and push to
`main`. Its stable aggregate check is **PR gate**. It requires all of:

- **Release metadata**: version/manifest consistency, shell syntax, benchmark
  provenance and checksum-pinned actionlint 1.7.12 workflow validation.
- **Native compiler smoke**: a checkout compiler/manager/campaign build followed by the
  bounded native MLF suite below on macOS arm64.
- **Native Windows runtime**: compact-GC runtime, filesystem and reproducible
  object/executable checks on Windows.

The aggregate runs even when a prerequisite fails and accepts only `success`.
Failed, cancelled or skipped prerequisites cannot produce a passing gate.
There are no path filters on the required workflow. Manual dispatches retain
the existing optional self-host and Windows-only modes. Their skipped aggregate
is named **Manual CI summary**, so it cannot satisfy the required **PR gate**.

## Enforce before merging

After the workflow has reported **PR gate**, add that exact check from GitHub
Actions to the required status checks for `main` in its branch protection rule
or branch ruleset. Enable the requirement for branches to be up to date, or use
the merge queue (`merge_group` is already supported). A workflow file cannot
itself configure repository branch protection; merging this change alone does
not make its checks mandatory.

## Native smoke coverage

The pinned v0.3.0 seed is only a bootstrap input. CI verifies its archive and both
executables and source commit, then builds the checkout compiler, manager and
test-owned `compiler-tests` executable with the current C runtime and checked
lockfile. That executable runs `pr-smoke` with the resulting compiler and an
explicit `--manager` pointing to the resulting manager. The ordinary six root groups are unchanged;
smoke is an explicit additional group and is not duplicated in a full root test.

The suite reuses existing assertions and fixtures:

- Framework assertion, case-selection and report contracts, the fixed coverage
  validator, and the `int-set-unions` suite through the full runner CLI probes.
  Process supervision probes cover crashes, timeouts, isolated work directories,
  captured output and rejected incomplete or contradictory child reports. The
  framework's three completed checkpoints must match the reviewed inventory.
- Figure 12: all 43 regression labels, 41 distinct executions and 36 controls,
  with expected rejection phases/reasons and checked xMLF round trips.
- Four frozen independent target-checker controls: identity, polymorphic let,
  IO and rejection of an ill-typed application.
- Exactly 12 selected backend fixtures on interpreter and compact-GC LLVM:
  input/output order, unbounded integers, unused-branch laziness, repeated IO,
  constructors, captured mutual recursion, partial-application laziness,
  Unicode/NUL, two state-mutation cases and rejection before effects. Each keeps
  its explicit output/event oracle in addition to backend agreement.
- The local-package example on both backends in three states: fresh build,
  unchanged cache reuse and a dependency implementation edit with changed output.
  Mutation uses a private copy; the checkout stays unchanged.

Missing or duplicate fixture labels, unexpected arguments, wrong matrix counts,
missing structural framework evidence, missing summaries, failed commands,
source/tool changes and incomplete package
reports fail the suite. The full parity corpus, full backend/port matrices and
fresh self-host fixed point remain part of release qualification.

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

The workflow uploads `pr-smoke-evidence` on success or failure, including build
and verification reports, framework coverage and its reviewed inventory, suite
logs, backend statuses and output. Detailed process-probe reports and logs are
also retained on failure; successful probes clean up their scratch directories.
Local evidence is
under `.mlf-build/pr-smoke/`; `result.json` records integer wall-clock seconds
for tool building and the complete command, plus compiler, manager, campaign,
framework and coverage fingerprints. The native job has a 45-minute hard
limit; this is a failure bound, not a promised runtime.
