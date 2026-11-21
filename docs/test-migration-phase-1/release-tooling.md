# Phase 1 handoff for self-host, bootstrap, tooling and release

Baseline `720dd649627fbf8b19c7447493a4fdf6fd05eb39`. Status is **implemented, unverified** for the routes below. All commands on this page are for Phase 2. Run them from the relevant checkout and retain its original reports and the framework report directory together.

## Self-host and bootstrap

| Baseline route | Registered coverage and entry point |
| --- | --- |
| `compiler-tests self-host` and POSIX native qualification | `self-host-native` retains the isolated native rebuild, authenticates the candidate's cited build report and artifact, checks the Clang and optional native PGO identity, binds the fresh stage to the exact compiler and manager hashes, compares emitted LLVM, then compares native compiler bytes. The six observations are `self-host/posix/{candidate-provenance,native-toolchain,fresh-rebuild,producer-chain,llvm-fixed-point,binary-fixed-point}`. The original `candidate_artifact`, `native_pgo` and `fixed_point` values accompany the case event file and its receipt hash. The root campaign and the native-CI compatibility command retain their existing names. |
| macOS cold native seed, including the manual bootstrap timing job | `bootstrap-macos-native` records seed/toolchain identity, bridge completion, the fresh candidate build, native build-runner preparation, and the existing resource budget gate. The native shared bridge and preserved source-architecture-selected primitive route still use distinct cold timing directories. Separate controlled routes remain under `release-timed-async-bootstrap`, `release-async-bootstrap`, `release-shared-bootstrap-dispatch`, `release-shared-bootstrap-orchestration`, `release-native-manager-identity` and `release-shared-seed-provenance`. |
| Linux stage from independently produced portable LLVM | `bootstrap-linux-llvm` records portable seed checksum validation, native seed materialization and its type query, the manager transition, and the fresh candidate build. Portable LLVM input and the native target build remain separate. |
| Windows release build from the same class of portable LLVM input | `bootstrap-windows-llvm` records portable seed, linked native seed, manager transition and independent stage 1 and 2 results. `windows-release-qualification` validates both build receipts and artifacts, compares each of the two tools' LLVM, verifies the compiler/manager producer chain, records installed versions and consumes the original runtime, packages, parity and final provenance files. The Windows baseline compares LLVM for both tools and validates published binary hashes against each stage's receipt. POSIX retains its independent binary fixed-point check. |

Each stage that is meant to be fresh still builds in a separate cache. The existing shared candidate producers and read-only toolchain preparation still serve the downstream qualification jobs. The migration removes zero fresh compiler builds. Expect little change in self-host wall time and a small cost for evidence serialization and producer hashes. Compare provisioning, seed transport, stage 1 and 2 builds and compiler/cache hits separately. On macOS compare the timing report's compiler, link, and manager-process totals against the baseline from the same seed and record the full-job overhead separately.

On a POSIX checkout with the qualified native tools and their matching build report/cache, use the same native environment as the [qualification workflow](../../.github/workflows/native-qualification.yml):

```sh
python3 -B tools/testing/run.py self-host-native --list
python3 -B tools/testing/run.py self-host-native --report .mlf-build/phase2-self-host.json
# Negative control using an existing, deliberately unrelated build receipt.
MLF_BUILD_REPORT="$BAD_BUILD_REPORT" python3 -B tools/testing/run.py self-host-native --report .mlf-build/phase2-self-host-mismatch.json
```

On macOS arm64 and Linux x64, respectively, after the normal dependency and seed provisioning:

```sh
python3 -B tools/testing/run.py bootstrap-macos-native --report .mlf-build/phase2-mac-bootstrap.json -- .mlf-build/phase2-bootstrap-mac
python3 -B tools/testing/run.py bootstrap-linux-llvm --report .mlf-build/phase2-linux-bootstrap.json -- .mlf-build/portable-llvm .mlf-build/phase2-bootstrap-linux .mlf-build/phase2-linux-candidate
```

On native Windows PowerShell 7:

```powershell
python -B tools/testing/run.py bootstrap-windows-llvm --report .mlf-build/phase2-windows-bootstrap.json -- -Seed .mlf-build/portable-llvm -NativePrefix $env:MLF_NATIVE_PREFIX -Clang $env:MLF_CLANG -Output .mlf-build/phase2-windows-native
python -B tools/testing/run.py windows-release-qualification --report .mlf-build/phase2-windows-qualification.json -- -Stage1 .mlf-build/phase2-windows-native/stage1 -Stage2 .mlf-build/phase2-windows-native/stage2 -NativePrefix $env:MLF_NATIVE_PREFIX -Clang $env:MLF_CLANG -Output .mlf-build/phase2-windows-evidence
```

Re-run the Windows qualification command against a distinct fresh output with a mismatched stage directory from a different source revision. The provenance or fixed-point case should fail, with absent downstream cases visible and the original PowerShell failure status preserved. Verify that the fresh-root manager reports include the compiler and manager SHA fields used by the producer-chain cases, that the native qualification composite retains failure events, and that the new PowerShell parent/child Python route can resolve `pwsh` and `python` on the Windows image.

## Tooling, platform and release

| Baseline route | Registered coverage and entry point |
| --- | --- |
| `tools/release/check.sh` | The same compatibility command dispatches registry suites. `release-metadata` owns version, manifest versions, changelog, shell syntax, license and diff checks. Setup, the native and PR gates, package publishing controls with a mock remote, seed-fetch pin mutations, build receipt checks, shared-candidate transport and unit evidence each have their own cases, including failed invocations and controlled rejections. The [release registry](../../tools/release/test-suites.json) lists static IDs and Python/Node inventory sources. |
| `python3 tools/dev.py check-tools` | The developer command and process checks use their real unittest case IDs. The five original compiler-shape support scripts are separate registered suites on Linux and macOS. The existing developer supervisor still owns cancellation of its active suite. The new `--suite`, `--list`, and `--exact` options select registered cases. |
| CI policy and tooling controls | The Node workflow checks read the real workflow and resolve registered adapters to their actual argument prefixes. The partition recognizes one hosted routine leg and one targeted optimizer leg, and retains mutation controls for selection, artifacts, bounds and dispatch. Existing auth and Git-input controls keep their frozen reference bytes. Ordinary and optimized Python control invocations remain distinct. |
| Manual formatter compatibility workflow | `formatter-compatibility` preserves both pinned tools, one harness build per invocation, five positive/negative controls, unchanged-source validation, and one stable ID per discovered corpus path. Exact selection uses the same formatter/parser oracle and a fresh harness, and marks the original receipt as focused. |
| macOS dependency producer and consumer | `macos-dependencies-record` preserves the first runner's byte inventory. `macos-dependencies-verify` checks formula revision, closure, installed bytes and the C test for pinned LLVM, GMP and BDWGC. The independent second installation and C runtime are retained. |
| POSIX and Windows release rehearsal | The package scripts call `sdk-smoke-posix` or `sdk-smoke-windows`. The POSIX eight-case run covers the relocated install, versions, helper/type, module interpretation, LLVM link/run, package test, reinstall and conflicting-file protection. Windows retains its Unicode/spaced relocation, system-only initial PATH, version, helper, type, plan/lock/build/test/run checks and standalone native executable. Package artifacts retain their original smoke logs and verification payloads. Historical recovery checkouts that predate the dispatcher use their own source-bound smoke script. |
| Checked-package release workflow | `package-release-tests` registers the selected manifest's test target names and imports the package manager's fresh test rows, preserving per-target oracle results, recorded backends and process outcome. The release export, release-draft controls, tag checks and explicit publication stay separate operations. An empty optional test table still follows the workflow's existing no-tests branch. |

The old direct script jobs now resolve through the external dispatcher. The former implicit Node import of the native partition controls was removed, and the explicit partition suite executes it once. The release-package and SDK checks retain their existing independent installations/builds. The release check keeps the second unit-evidence run with jq 1.8.2 because it is a separate parser compatibility contract. Expected savings come mainly from formatter exact selection avoiding the rest of the file comparisons and from collecting each batched unittest suite's real results in one process. The new dispatcher adds startup and report writes to full tooling campaigns. Compare process launches, tool installation, fixture preparation and assertions separately before claiming a net speed change.

Local POSIX inspection and selected runs:

```sh
tools/release/check.sh
python3 -B tools/testing/run.py release-ci-policy --list
python3 -B tools/testing/run.py release-native-ci-partition --exact release/native-ci-partition/schedule --report .mlf-build/phase2-ci-schedule.json
python3 -B tools/testing/run.py release-macos-toolchain-workflow --list
python3 -B tools/testing/run.py release-build-receipts -- --executable .mlf-build/shared-ghc/bin/build-receipts --output .mlf-build/phase2-build-receipts
python3 -B tools/dev.py check-tools
python3 -B tools/dev.py check-tools --suite release-developer-process --list
python3 -B tools/testing/run.py release-setup-macos
python3 -B tools/testing/run.py release-unit-evidence
PATH="$PINNED_JQ_1_8_2_BIN:$PATH" python3 -B tools/testing/run.py release-unit-evidence
python3 -B tools/testing/run.py formatter-compatibility --list
python3 -B tools/testing/run.py formatter-compatibility --report .mlf-build/phase2-formatter.json -- --output .mlf-build/phase2-formatter
python3 -B tools/testing/run.py formatter-compatibility --exact formatter/control/parser-rejection --report .mlf-build/phase2-formatter-focused.json -- --output .mlf-build/phase2-formatter-focused
python3 -B tools/testing/run.py sdk-smoke-posix --report .mlf-build/phase2-posix-sdk-smoke.json -- "$POSIX_SDK_DIRECTORY"
python3 -B tools/testing/run.py package-release-tests --list -- --manifest "$PACKAGE_MANIFEST"
python3 -B tools/testing/run.py package-release-tests --report .mlf-build/phase2-package-release-tests.json -- --manifest "$PACKAGE_MANIFEST" --compiler "$MLF_COMPILER" --manager "$MLF_PACKAGE_MANAGER" --build-dir .mlf-build/phase2-package-release-tests
```

Independent macOS producer and consumer after normal pinned provisioning:

```sh
python3 -B tools/testing/run.py macos-dependencies-record --report .mlf-build/phase2-dependencies-producer.json
python3 -B tools/testing/run.py macos-dependencies-verify --report .mlf-build/phase2-dependencies-consumer.json -- .mlf-build/producer-dependencies
```

Windows SDK smoke from an already qualified, unpackaged Windows bundle:

```powershell
python -B tools/testing/run.py sdk-smoke-windows --report .mlf-build/phase2-windows-sdk-smoke.json -- -Package $env:WINDOWS_SDK_DIRECTORY -Clang $env:MLF_CLANG -Output .mlf-build/phase2-windows-sdk-smoke
```

Exercise these with the existing non-publishing `platform-release.yml` rehearsal by using `validation_only` and all three platform jobs. Compare the same route at the baseline using the registered command's underlying arguments. Check an interrupted batch, a tool with a deliberate nonzero exit, and a malformed/truncated event stream through the dispatcher. Compare partial suite reports against the original stdout, stderr and producer receipts before relying on the new evidence for qualification.

The exact case counts for dynamically discovered unittest, formatter-file and workflow-mutation inventories need Phase 2 enumeration. Batch and stage adapters keep their original combined invocation where members share state or required predecessors. The package manager writes a row only after the target succeeds. Its partial receipt retains previous targets and the process failure, while the interrupted target and following targets remain incomplete in the framework report. Confirm that Python process-group forwarding works with both the existing developer supervisor and the outer hard resource watchdogs, particularly on signals and termination during child startup. Each platform's executable behavior, freshness predicates and release consumer assumptions remain unverified.
