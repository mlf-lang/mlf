# Test migration subplans

Use these work packages with the [roadmap](test-migration-roadmap.md). Assign their Phase 1 changes to subagents in parallel. Agree on ownership of shared manifests, dispatchers, and workflow files before editing them. Complete the code, default switches, duplicate removal, adapters, and CI edits together. During Phase 1 use source, contracts, and existing evidence only. Defer all test and benchmark execution, including discovery commands and baseline runs, to Phase 2.

For the handoff, record the baseline revision, expected case mapping, changed entry points, and commands to verify each change. In Phase 2 run those commands against the pre-cutover revision and integrated candidate under comparable conditions. Fix discrepancies, rerun affected checks, and record the final results and speed comparisons in the integration PR.

## TupleList

**Phase 1.** Map the 305 legacy observations to the 105 framework IDs. Preserve the grouped arity case covering expression, type and pattern parsing for arities 2–64 and compilation at six boundaries under both syntax profiles. Share one lazy compilation result per type/runtime pair while keeping all fourteen IDs selectable. Switch the no-argument entry to the registry, preserve the release success line and CLI/report options, and remove the live legacy module and duplicate CI runs. [Active contract](../tools/testing/tuple-list-active-contract.json)

**Phase 2.** Run the full hosted -O0 suite. Exercise type, runtime and grouped-arity failures, and verify discovery and exact selection. Measure compile calls across the seven pairs in one process and separate arity parsing time from compilation time. Run the interpreter/LLVM fixture with the hosted compiler and exercise the release-candidate qualification path.

## Core

**Phase 1.** Cut over all four partitions and the compatibility executable to the same registry. Map registered actions, aliases, generated-loop counts and thirteen substring observations to the reviewed inventory. Preserve full, family, exact and resume selectors where supported. Batch recoverable assertions in-process and retain supervised children for actions that can terminate the process. Wire the parent to validate the union of all partitions. [Core runner](../tests/Tests/CoreRunner.emlf) and [partition contract](../tests/README.md)

**Phase 2.** Compare exact partition membership and full aggregate coverage. Verify a recoverable failure allows later cases to run and interruption leaves incomplete evidence. Measure process starts and build closure for one selected family and a full campaign.

## Figure 12

**Phase 1.** Register paper row labels, source expressions, expected types or rejections and supplementary controls, including the documented A8 discrepancy. Preserve sharing of 43 expression labels across 41 executions. Consolidate direct CI, PR smoke and unit invocations only when the producer, selection and checks coincide. [Suite](../tests/Tests/Figure12Suite.emlf)

**Phase 2.** Compare labels, phases, independently checked targets and controls. Measure compile calls and full-suite time. Introduce a wrong expected type and verify the report identifies its row.

## Parity corpus

**Phase 1.** Configure routine CLI parity to use the GHC-hosted compiler and report its build identity. Export stable corpus IDs and expected acceptance, rejection, type and runtime outcomes through the batched driver. Preserve the frozen corpus, independent target checker, sharing for repeated sources, and selection of a single input. [Campaign](../tests/Tests/CompilerTests.hs)

**Phase 2.** Reconcile the 7,086 prescribed cases, 7,075 baseline source compilations and 80 runtime rows on both backends. Measure distinct compilations and process launches. Verify a mismatched type, missing row and interrupted batch each prevent a full pass.

## Backends

**Phase 1.** Wire routine CI to build the matrix harness and interpreter and LLVM drivers with the hosted toolchain. Declare the package-manager and build-runner dependencies. Register backend families and coordinates, expected status, IO events, remaining input and diagnostics. Share preparation for identical inputs and retain separate execution results. [Suite](../tests/Tests/BackendSuite.emlf)

**Phase 2.** Compare the hosted and baseline paths against the same independent expectations in focused and full campaigns. Compare fixture and row inventories, then inject one wrong output and one backend failure. Verify the failed row remains visible when its counterpart passes. Time preparation, LLVM emission/linking and child execution separately.

## Port

**Phase 1.** Register port fixtures with their reference programs, checked-target round trips, outputs and required execution paths. Retain independent references and bind reused preparation to input identities. [Suite](../tests/Tests/PortSuite.emlf)

**Phase 2.** Compare all 25 baseline fixtures, reference results and target evidence. Change a producer input to exercise invalidation. Count preparations, reference builds and links on cold and warm runs. Compare campaign time with preparation and execution time.

## Regex and library cases

**Phase 1.** Migrate the regex suite’s 56 reported actions and generated invalid-pattern checks. Register the existing int-set-unions cases and map their use by Core. Reuse immutable inputs within a suite and retain distinct oracle and CLI-selection checks. [Regex entry](../tests/RegexMain.emlf) and [int-set entry](../tests/IntSetUnionsMain.emlf)

**Phase 2.** Compare regex outputs, rejection counts and int-set inputs. Run exact selection, a full suite and a failing expectation. Verify CLI selection and measure corpus construction and repeated execution.

## Framework and process contracts

**Phase 1.** Register assertion, CLI, fixture, catalog and lifecycle checks, including separately invocable failing probes. Batch pure validation probes. Preserve real processes and independent directories for race, crash, timeout and cleanup cases. [Framework entry](../tests/TestFrameworkMain.emlf) and [process tools](../testing/tools/README.md)

**Phase 2.** Exercise assertion failure, crash, timeout, missing and stale reports, and cleanup failure. Verify the parent receives the correct status and partial scope. Verify ownership and join evidence for release qualification. Measure supervised startup and teardown costs.

## Harness

**Phase 1.** Register the 55 baseline harness families and their named observations. Link source-cache, native-driver, benchmark and release checks to their validators. Load evidence for the selected families, share identical helper builds, and isolate scratch state for failure and recovery. [Harness entry](../tests/HarnessMain.emlf)

**Phase 2.** Reconcile the 69 baseline observations. Exercise invalid evidence and single-family selection. Verify only the full invocation claims full coverage. Measure fixture construction, helper startup and execution for selected and full runs.

## Package integration and distribution

**Phase 1.** Register resolver, build/cache and scheduler scenarios separately from checked-package release scenarios. Preserve both mode selectors. Reuse immutable inputs and retain fresh roots for cold-cache tests, distinct writers for concurrent publication and isolated files for recovery. [Package entry](../tests/PackagesMain.emlf)

**Phase 2.** Compare the 51 baseline integration actions and 28 distribution actions, including cache transitions, resolver rejections and damaged-release failures. Run the package target and time fixture trees, dependencies and cache setup for warm and intentionally cold scenarios.

## Self-host and bootstrap

**Phase 1.** Register the fresh native compiler rebuild, stage identities and fixed-point comparisons for supported seed routes. Bind each candidate to its producer. Keep the isolated store and fresh compiler build, and reuse provisioned dependencies where the test permits it. [Bootstrap and CI contract](shared-source/Bootstrap-and-CI.md)

**Phase 2.** Verify exact expected artifacts and provenance through native qualification. Execute a mismatched-stage negative control. Measure provisioning, discovery, stage builds, cache state and aggregate runner-minutes separately.

## Direct language tests and smoke workflows

**Phase 1.** Map CI commands outside the root catalog to their source input, oracle, producer and optimization dependency. Include frontend, recursion, source smoke, shared-host and guest framework checks. Register unique assertions and assign identical executions to one owner. Preserve a selectable PR smoke profile and targeted optimizer/host-specific checks. [CI workflow](../.github/workflows/ci.yml)

**Phase 2.** Exercise a source rejection, malformed target and host-specific failure. Verify each profile reports its actual selection. Measure setup, time to first failure and PR critical-path time.

## Native runtime and async

**Phase 1.** Register C runtime probes, async scheduling/completion cases and shell-driven native fixtures. Preserve binary identity, platform, exit status and traces. This subplan owns the tuple-list-native backend fixture. Reuse identical binaries and preserve independent processes and resource scopes for signals, cancellation, races and cleanup. [Native fixtures](../tests/native) and [async CI policy](ci-async-policy.md)

**Phase 2.** Compare native results and traces on required platforms. Exercise timeout, cancellation, unexpected termination, interruption and real cleanup. Verify the reported statuses and measure harness builds and startup overhead.

## Tooling, platform and release

**Phase 1.** Register maintained Python, JavaScript, shell, PowerShell and other tooling suites, including manual workflows, formatter compatibility, developer commands and Windows checks. Trace nested calls and discovery in source. Import inventories or results for independently reported cases. Use native batching and share compatible read-only setup while preserving installation, relocation, bootstrap and corruption scenarios.

**Phase 2.** Verify case identity and status for a failing script, missing output and truncated report. Exercise affected platforms through existing release rehearsals. Time tool installation, fixture preparation and execution separately. Publishing remains an explicit release operation. [Release guide](releases.md)

## Benchmarks and performance gates

**Phase 1.** Register compiler-shape and application correctness checks separately from sampled comparisons. Preserve workloads, compiler identities, baselines, samples and thresholds. Deduplicate build and correctness invocations with matching producers, inputs, settings and expected results. Keep setup outside sample windows. [Compiler shapes](../tools/performance/compiler-shapes/README.md) and [application runner](../tools/bench/README.md)

**Phase 2.** Reproduce incorrect-output and threshold failures using the existing controls. Compare retained samples and measurement metadata. Report orchestration and fixture/setup costs separately from workload timings.
