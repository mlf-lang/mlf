# Framework, harness and packages Phase 1 handoff

The comparison baseline is `720dd649627fbf8b19c7447493a4fdf6fd05eb39`. Phase 1 used source, manifest and diff inspection. All commands below are for Phase 2.

## Framework and process contracts

| Reviewed coverage observation | Shared registry action |
| --- | --- |
| `framework/contracts` | Assertion behavior, selector and result validation, case adaptation and metadata, typed expectations and receipt qualification |
| `framework/catalog-contracts` | Catalog classification, batch selection, Core partitions, independent inventory projection and family-selector receipt controls |
| `framework/coverage-validator` | Counted callback execution and independent structural coverage receipt mutations |
| `framework/cli-contracts` | Actual argument handling, independent int-set executable, tests-package working directory, passing and failing probes, stale report replacement, and process-supervisor contracts |

`test-framework --verify-cli WORK INT_SET_UNIONS` dispatches through all four cases. It retains the original coverage IDs and marker strings. Bare `test-framework` executes the pure cases, and `--list`, `--exact`, `--format` and `--report` use the shared runner. The explicit `--probe`, `--list-probe`, `--noisy-probe`, `--legacy-fail-probe`, `--supervise`, `--isolated-probe`, discovery-crash and forged-report routes still exercise real children. `testing/tools` retains all 22 indexed `lifecycle/*` controls and the existing native ownership and v1 process measurement adapters.

The int-set executable runs its oracle once in framework CLI validation. Three equivalent metadata selectors now query the same inventory and compare their selected IDs, labels and tags. The independent package-directory process still tests that directory and targets the catalog case. These changes remove three repeated oracle executions and two pure groups in the child while retaining the CLI checks. The direct hosted gate executes one full TupleList registry instead of both the default and opt-in suites. It records the actual v1 registry report from that execution, validates the default marker, and records independent CLI, purpose-built class/demand, and producer identity outcomes. The targeted `--suite controls` profile avoids the full registry on the optimized build. Measure physical int-set and TupleList run counts separately from fixture oracles, and use each process receipt's elapsed times to separate startup, active work and teardown.

```sh
leaf_build="$PWD/.mlf-build/phase2-leaves"
export MLF_TEST_WORK="$PWD/.mlf-build/phase2-framework"
mkdir -p "$MLF_TEST_WORK"
clang -O2 -std=c11 -Wall -Wextra -Werror tests/native/host_support.c -o "$MLF_TEST_WORK/host-support"
export MLF_TEST_HOST_SUPPORT="$MLF_TEST_WORK/host-support"
./mlfpkg --manifest tests/mlf-package.json --build-dir "$leaf_build" build --target test-framework --target int-set-unions
"$leaf_build/bin/test-framework" --list --format json
"$leaf_build/bin/test-framework" --exact framework/catalog-contracts --report "$MLF_TEST_WORK/catalog.jsonl"
"$leaf_build/bin/test-framework" --verify-cli "$MLF_TEST_WORK" "$leaf_build/bin/int-set-unions" --report "$MLF_TEST_WORK/framework.jsonl"
"$leaf_build/bin/test-framework" --legacy-fail-probe
"$leaf_build/bin/test-framework" --supervise --work-dir "$MLF_TEST_WORK/process" --report "$MLF_TEST_WORK/process.jsonl" --timeout 1 --format json -- "$leaf_build/bin/test-framework" --isolated-probe
"$leaf_build/bin/test-framework" --supervise --work-dir "$MLF_TEST_WORK/process" --report "$MLF_TEST_WORK/forged.jsonl" --format json -- "$leaf_build/bin/test-framework" --forged-report-probe
./mlfpkg --manifest testing/tools/mlf-package.json --build-dir "$PWD/.mlf-build/phase2-lifecycle" test --target lifecycle
python3 -B tools/shared/test_framework_controls.py
python3 -B tools/shared/build.py --bootstrap-only --optimization 0 --build-dir .mlf-build/phase2-framework-O0
python3 -B tools/testing/run.py framework-direct -- --build-receipt .mlf-build/phase2-framework-O0/receipt.json --output .mlf-build/phase2-framework-O0-results --suite all --suite-timeout 5400
python3 -B tools/shared/build.py --bootstrap-only --optimization 2 --build-dir .mlf-build/phase2-framework-O2
python3 -B tools/testing/run.py framework-direct -- --build-receipt .mlf-build/phase2-framework-O2/receipt.json --output .mlf-build/phase2-framework-O2-results --suite controls
```

Use separate invocations for negative commands because the legacy assertion, mixed supervised run and forged-success invocation each deliberately return 1. The full `--verify-cli` path covers the inventory crash, truncated report, timeout, stale report, classification and output retention checks. The lifecycle target checks rejected cleanup, unverified join, capability and ownership transitions. The POSIX v1 timing protocol continues to label cleanup evidence as unverified. Compare native ownership behavior with release qualification and retain platform-specific evidence.

## Harness

The 55 original `harness/*` families remain the dispatch IDs. Their 69 named observations plus regex-redux execution metrics still come from the validators that ran them and are checked against `tests/golden/unit-inventory.json`.

- `matrix-evidence` and `corpus-evidence` run the native matrix, port target and parity receipt checks from `Tests.BootstrapSuite` as recoverable assertions.
- `source-dependency-cache` and `native-driver-cache` retain the source-discovery and checked-driver rebuild controls, their isolated paths, and their child process evidence.
- `release-evidence`, `release-steps` and `release-installation` retain the independent release validator, clean gate environment, unsuccessful step, install and relocation observations. The pure evidence mutations form a recoverable case.
- `regex-redux-execution` retains independent native and interpreted output checks with seven native and two interpreted counted executions.
- Benchmark and ABI families retain the `test_*` observation labels and deterministic `harness/` slugs already in the catalog. Their `Tests.BenchmarkSuite.cases` entries are the single maintained registry inventory. The unused module-level benchmark, bootstrap and release dispatchers have been removed.

`harness --list-families` and `--families ID...` remain compatible. They dispatch to the same registry as `--list` and exact selection. Full qualification still requires an unfiltered invocation and matching observation and family sidecars. The loader shares one manifest and one evidence object across selected checks and skips reads for unrelated selections. Focused runs should reduce helper launches and scratch setup in proportion to the omitted families. The retained driver-cache builds and release cases use intentionally distinct states. There is no claimed full-campaign timing saving for those builds. Phase 2 should compare fixture reads, helper launches, native links and wall time per selected family and full harness run.

```sh
leaf_build="$PWD/.mlf-build/phase2-leaves"
./mlfpkg --manifest tests/mlf-package.json --build-dir "$leaf_build" build --target harness
"$leaf_build/bin/harness" --list-families
"$leaf_build/bin/harness" --list --format json
MLF_TEST_FAMILY_REPORT="$MLF_TEST_WORK/harness-focused-families.jsonl" MLF_TEST_COVERAGE_REPORT="$MLF_TEST_WORK/harness-focused-coverage.jsonl" "$leaf_build/bin/harness" --exact harness/matrix-evidence --report "$MLF_TEST_WORK/harness-focused.jsonl"
MLF_TEST_FAMILY_REPORT="$MLF_TEST_WORK/harness-full-families.jsonl" MLF_TEST_COVERAGE_REPORT="$MLF_TEST_WORK/harness-full-coverage.jsonl" "$leaf_build/bin/harness" --report "$MLF_TEST_WORK/harness-full.jsonl"
./mlfpkg run compiler-tests -- select --family harness/native-driver-cache --compiler "$MLF_COMPILER" --manager "$MLF_PACKAGE_MANAGER" --build-dir "$PWD/.mlf-build/phase2-harness-cache"
```

Use the campaign's provisioned `MLF_TEST_BINARY_FILES`, `MLF_TEST_ROOT`, `MLF_TEST_WORK`, `MLF_BOOTSTRAP_COMPILER`, package manager and collector for the full direct run. To verify invalid evidence reporting, corrupt a copy of `tests/golden/release-evidence.json` in a disposable candidate checkout and repeat `harness --exact harness/release-evidence --report "$MLF_TEST_WORK/damaged-evidence.jsonl"` from that checkout. Verify exit 1 and a failed case receipt.

## Package integration and distribution

The modes retain their independent inventory projections and keep `--integration` and `--releases`. They now select tagged registry cases. Unselected scenarios perform no fixture preparation.

| Baseline observations or controls | Shared registry action |
| --- | --- |
| 22 resolver observations named `test_packages.test_*` | One `packages/resolver/test_*` case each, with the original coverage IDs and observed command diagnostics |
| Dependency path semantics, action receipt isolation and publication recovery | `packages/dependency-paths`, `packages/build/isolated-action-results`, `packages/build/publication-recovery` |
| Local build, cache transitions, compiler and collector selection | `packages/build/local-cache` |
| Crate composition, incremental checking, LLVM and clean-build comparison | `packages/build/checked-crate` |
| Non-entry library rejection | `packages/build/non-entry-body` |
| PGO fingerprint, isolation and failure preservation | `packages/build/native-pgo` |
| Cross-output and shared artifact recovery | `packages/build/shared-cache` |
| Target-only dependency selection and separate scheduler controls | `packages/target-dependencies` and `packages/scheduler` |
| All 28 `checked release: …` observations | `packages/checked-distribution`, retaining the independent release, cold-offline, corrupted object, relocation and GitHub fixture assertions |

The 29 named build/cache observations and 22 resolver observations retain the original coverage labels. Scheduler serial, warm and concurrent phases retain their separate coordinator invocations and cache ownership, and its compiler outputs retain their existing receipts. The resolver now prepares shared immutable base and left sources once for cases that need them, including selected dependent cases. The package tree shared by an ordered cache sequence stays together. The release scenario retains stateful checkpoints in its compatibility receipt; it is selectable as one scenario. The expected focused saving is the cost of the omitted scenario builds. Full runs preserve the intentional compile, cold-cache, warm reuse, independent build, concurrent writer and failed publication operations. Compare resolver and build case wall time and count manager commands, fixture creation, cache misses and writes per state.

```sh
leaf_build="$PWD/.mlf-build/phase2-leaves"
export MLF_BOOTSTRAP_COMPILER="$MLF_COMPILER"
./mlfpkg --manifest tests/mlf-package.json --build-dir "$leaf_build" build --target packages
"$leaf_build/bin/packages" --list --format json
"$leaf_build/bin/packages" --integration --exact packages/resolver/test_diamond_and_canonical_symlink --report "$MLF_TEST_WORK/diamond.jsonl"
"$leaf_build/bin/packages" --integration --exact packages/resolver/test_package_cycle --report "$MLF_TEST_WORK/resolver-negative.jsonl"
MLF_TEST_COVERAGE_REPORT="$MLF_TEST_WORK/package-integration.jsonl" "$leaf_build/bin/packages" --integration --report "$MLF_TEST_WORK/package-runner-integration.jsonl"
MLF_TEST_COVERAGE_REPORT="$MLF_TEST_WORK/package-distribution.jsonl" "$leaf_build/bin/packages" --releases --report "$MLF_TEST_WORK/package-runner-distribution.jsonl"
./mlfpkg --locked test --target packages
```

Phase 2 must exercise compile-time inference and the checked dependency graph for the guest registry, reconcile named evidence and incomplete receipts, and confirm that resolver fixtures still support every selected prerequisite. Fatal native fixture or infrastructure errors terminate the containing scenario. The original named sidecars retain the completed observations and the interrupted run cannot earn full coverage. The report written by `--report` holds the structured registry results separately from stdout, which continues to carry consumed markers and diagnostics. Keep macOS, Linux and Windows setup and platform execution evidence separate.
