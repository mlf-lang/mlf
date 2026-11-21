# Test-framework migration Phase 1

The comparison baseline is `720dd649627fbf8b19c7447493a4fdf6fd05eb39`, the exact
`origin/main` head fetched before implementation. The original checkout's
local commits, index and files were preserved. The integrated candidate lives
on `codex/test-migration-phase-1` and is **implemented, unverified**. Phase 1
used source, manifest and diff inspection and derived the lockfiles from the
local package graph. No tests, executable discovery, builds, fault probes,
timings or CI ran.

| Subplan | Coverage mapping, entry points, savings and Phase 2 commands |
| --- | --- |
| 1 TupleList | [Core and libraries](core-library.md#tuplelist) |
| 2 Core | [Core and libraries](core-library.md#core) |
| 3 Figure 12 | [Language](language.md#figure-12) |
| 4 Parity corpus | [Language](language.md#parity-corpus) |
| 5 Backends | [Backends and native runtime](backend-native.md#5-backends) |
| 6 Port | [Backends and native runtime](backend-native.md#6-port) |
| 7 Regex and library cases | [Core and libraries](core-library.md#regex-and-int-set-unions) |
| 8 Framework and process contracts | [Framework, harness and packages](harness-packages.md#framework-and-process-contracts) |
| 9 Harness | [Framework, harness and packages](harness-packages.md#harness) |
| 10 Package integration and distribution | [Framework, harness and packages](harness-packages.md#package-integration-and-distribution) |
| 11 Self-host and bootstrap | [Release and tooling](release-tooling.md) |
| 12 Direct language tests and smoke | [Language](language.md#direct-language-and-smoke) |
| 13 Native runtime and async | [Backends and native runtime](backend-native.md#13-native-runtime-and-async) |
| 14 Tooling, platform and release | [Release and tooling](release-tooling.md) |
| 15 Benchmarks and performance gates | [Performance](performance.md) |

## Integrated entry points

- `tests/test-catalog.json` references the named external inventories. Native
  campaigns keep their existing package targets, family selectors and receipt
  paths. The campaign parent reads the framework case report alongside the
  legacy structural evidence and checks the Core partition union. Direct
  native suite binaries accept `--list`, `--exact` and `--report` where
  supplied by their registry.
- `python3 -B tools/testing/run.py SUITE -- [ORIGINAL ARGS]` dispatches a
  registered non-MLF producer. It keeps its stdout, stderr and exit code,
  retains incomplete JSONL events, and requires the actual case set to reconcile
  before a run can pass. `--list` uses a static or declared producer inventory.
  `--exact ID` is available where the producer supports selection. Approved
  skips and unsupported outcomes are explicit. Scripts with established
  reports retain those files and expose their independently checked results.
- Routine hosted checks share one GHC O0 build. This replaces three separately
  provisioned O0 smoke legs, dropping two GHC installations and producer builds
  per CI run. Routine TupleList semantics has one full hosted registry
  execution, plus its distinct interpreter/LLVM fixture. The hosted parity
  campaign batches source compilation and independent target checking while
  preserving runtime children. Backends build the instrumented interpreter
  and LLVM drivers with the same hosted producer to retain raw IO traces.
- The O2 profile retains optimizer and host-demand controls, the compiler
  shape comparison, and the relevant framework CLI controls. Native
  qualification and SDK and release rehearsals still bind their own binaries,
  seed routes and platform checks. The reviewed benchmark samples and
  thresholds stay unchanged.

## Phase 2 integration commands

Start from the exact local candidate commit. Set `P2` to an absolute scratch
directory, using separate output and cache directories on each revision. These
are Phase 2 commands.

```sh
git worktree add --detach "$P2/baseline" 720dd649627fbf8b19c7447493a4fdf6fd05eb39
python3 -B tools/testing/run.py --list
python3 -B tools/testing/run.py indexvec --list
python3 -B tools/testing/run.py indexvec --report "$P2/indexvec.json" -- \
  --compiler "$P2/ghc-O2/bin/emlf" --output "$P2/indexvec"
python3 -B tools/testing/run.py shared-host-adapter --report "$P2/shared-host.json" -- \
  "$(command -v ghc)" --output "$P2/shared-host"
python3 -B tools/testing/run.py recursive-saved-crate --report "$P2/saved-crate.json" -- \
  --compiler-build "$P2/ghc-O2" --build-dir "$P2/saved-crate"
python3 -B tools/testing/run.py python-shared-query-index --list
FIXTURE=SolverReuse GC_FREE_SPACE_DIVISOR=1 CANDIDATE_RUN="$QUALIFIED_RUN" SOURCE_COMMIT="$QUALIFIED_SHA" \
  python3 -B tools/testing/run.py port-preparation-profile --report "$P2/port-profile.json"
python3 -B tools/testing/run.py candidate-smoke-cli -- "$NATIVE_BIN/emlf" "$P2/native-candidate-cli"
python3 -B tools/testing/run.py candidate-smoke-packages -- \
  "$NATIVE_BIN/emlf" "$NATIVE_BIN/mlfpkg" "$P2/native-candidate-packages"
python3 -B tools/testing/check_manifest_snapshot.py --manifest mlf-package.json
python3 -B tools/testing/check_manifest_snapshot.py --manifest tests/mlf-package.json
python3 -B tools/testing/check_manifest_snapshot.py --manifest tests/shared/mlf-package.json
python3 -B tools/testing/check_manifest_snapshot.py --manifest testing/tools/mlf-package.json
./mlfpkg --locked plan
./mlfpkg --locked --manifest tests/mlf-package.json plan
```

Use the former commands and the same producer, arguments, resource watchdog and
independent fixture inputs when comparing specialized scripts. The O2 workflow
retains the exact bounds and selections for those scripts. Compare cold and
warm host build costs, process starts, per-stage wall time, aggregate runner
minutes and time to the last required PR check. The consolidated routine job
runs more distinct campaigns, so reduced aggregate build work and reduced PR
latency are separate hypotheses.

## Verification assumptions

- The native seed, GHC and the guest compiler still need to compile the new
  registries and dependencies. Verify producer authentication, receipt
  compatibility, lockfile acceptance and failure propagation on the claimed
  Linux, macOS and Windows hosts.
- Newly reported IDs need reconciliation with generated inventories, original
  aliases and the old backend, checked-target and release outputs. Use the
  commands and negative cases in the suite handoffs. The combined O0 job's
  wall time and memory use need measurement against its six-hour limit.
- Stateful package, harness and specialized tool checks still have observation
  groups that share an execution. Their original case logs and negative
  assertions stay in the underlying receipts. Arbitrary internal assertions
  in historical reference drivers do not acquire individual selectors.
- Native MLF reports and pre-bootstrap process statuses have different
  evidence sources. The legacy timing supervisor cannot certify descendant
  cleanup. Verify the owned process paths and their negative controls
  separately. Historical tagged package checkouts use their original manager
  entry when the Phase 1 adapter is unavailable in the tag.


## Remaining reporting limits

The checked-package manager currently writes a row only for a completed
target. Its adapter retains prior observations and the process failure, but
cannot give a failed or interrupted target a per-target verdict without a row.
Some optimizer and host compatibility adapters import verified cases from a
finished receipt. They do not have independent pre-run discovery or exact
selection where the underlying engine exposes neither.
