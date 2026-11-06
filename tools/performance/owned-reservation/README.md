# Owned source context and name reservations

The requested environment-view and declaration-scan optimizations were implemented and tested in two successive candidates. **Neither met its fixed discovery advancement rule.** No confirmation window or additional samples were started to obtain a favorable result. After reviewing this negative discovery decision, the user explicitly authorized integrating the final combined candidate as a structural improvement on 2026-11-01. This later engineering decision does not change the experimental thresholds or establish a stable speedup.

The first candidate added two ordinal declaration indexes and incremental overload/protection maps; its 512-point time reductions were 0.97% and -0.56% ([archived report](../owned-source-context/README.md)). This second candidate also caches `plan.used ∪ current contract keys`. Every group starts from the original fresh counter and this seed, then reserves local/body/candidate names and fixed method keys plus unshadowed method targets in the original location. Method targets are not accumulated in the persistent seed: shadowing can remove a target from the effective environment. The same finalized delta updates contracts, encodings, views and reserved contract keys after successful finalization/cache saving.

The public structural preparation, lowering and encoding entry points remain unchanged in behavior. The new contexts are valid only for their synchronized finite parsed-file plan and checked predecessor map. Startup copied-definition searches and other compiler work remain. This is not a claim that all quadratic work was removed.

## Fixed second experiment

Baseline: accepted `48275901cd7b760cc8dd000ed54898a23a494a87`. Candidate: the frozen source identities in `.mlf-build/owned-reservation-20261101/producer/receipt.json` and `frozen-candidate/`. The candidate includes the earlier unaccepted sparse selectors and view/index changes; the measurements do not isolate their contributions.

Two chain families, **32/128/512/2048** generated functions, one predeclared ABBA/BAAB block per cell: two samples per MLF version, **32 fresh builds total**. Two GHC reference builds per cell ran separately afterward in the same session. All use the standard `compiler-shapes` generator/worker. MLF uses the ordinary GHC 9.14.1 O2 bootstrap producer and serial ordinary Clang O2; target code is compiled fresh to an executable and only fixed dependencies are reused. This is `crate-bootstrap-v1`, not the installed `emlf SOURCE -o` endpoint. GHC is not a paired noise correction.

Seconds below are the median of two observations (their midpoint).

| Chain / compiler | 32 | 128 | 512 | 2048 |
|---|---:|---:|---:|---:|
| Annotated / baseline MLF | 0.993 | 1.565 | 4.216 | 22.612 |
| Annotated / candidate MLF | 0.993 | 1.484 | 4.179 | 22.368 |
| Annotated / GHC | 0.632 | 0.732 | 0.974 | 3.577 |
| Inferred / baseline MLF | 1.068 | 1.634 | 4.621 | 23.177 |
| Inferred / candidate MLF | 1.022 | 1.637 | 4.576 | 22.798 |
| Inferred / GHC | 0.636 | 0.668 | 1.133 | 3.292 |

The 2048-point descriptive geometric whole-run reductions are **1.08% / 1.60%**, below the predeclared 5% advancement rule. The 512→2048 whole-run incremental slope drops only about **1.13% / 1.80%**. These sparse, noisy observations do not establish a changed growth curve or a complexity-class improvement. No confidence interval is assigned.

The frontend's 2048 medians are 13.496→13.019s and 13.811→13.497s. Checked-to-LLVM costs about **8.3–8.6s at 2048**, versus about **1.0s at 512**; Clang is about 0.69s at 2048. This localizes substantial growth to work outside the optimized source-group loop, but does not identify the specific cause within linking, optimization and emission.

[Stage-by-stage curves](growth-20261101.png) · [Exact samples and receipt identities](results-20261101.json)

## Validation and limits

- O0 and O2 each passed **162 targeted controls**, including complete prepared keys, ordinal ordering, overwritten/empty deltas, support/unsigned/annotated/recursive successes, shadowed method targets, unused-name collisions, reset counters, and full Fresh result/count/used-set comparisons.
- Complete frozen `CrateQuery`, `SourceInference`, and `Classes` sources from the accepted baseline are retained. The original frozen files are unchanged. The runner creates a reversible private source-oracle copy that imports frozen Classes, rather than computing expectations through the candidate lowerer.
- All 32 MLF builds had the expected ordered fresh groups, zero target reuse, raw checked-byte equality with independent references, and three closed-form executable-output checks. The new 2048 references each contain **2051 fresh / 0 reused** groups. All 16 GHC executables passed the same output oracles.
- Ordinary O2 source build and exact builtin regeneration passed. The controls ran before the final canonical builtin source-identity refresh; every other control input pin remains unchanged. The generator verified that only the embedded identity changed, and the subsequent ordinary build verified the exact final canonical source. This boundary is recorded in `qualification.json`.
- Metadata adapter tests passed: 18 normal Python, the same 18 under `-O`, and 34 A1 tests. Independent read-only semantic review found no blocking defect.
- At discovery closeout, no full retained oracle sweep, new native installation, 711-group confirmation, or performance holdout was launched after the discovery failed. All failures and prior unsuccessful candidates remain archived. The later integration checks below are separate from that closed experiment.

The integration decision values avoiding repeated construction and growing full-map scans, while retaining the complete structural route for public partial-value behavior. The observed small time reductions are supporting exploratory evidence only. The tradeoff is additional persistent indexes and synchronization invariants; no net allocation, peak-memory, or disk-space reduction has been measured. Cache-file reads and writes are unchanged. Integration qualification is recorded separately below, without extending or relabeling either discovery cohort.

## Integration qualification, 2026-11-01

The unchanged ordinary candidate passed the retained P1–P3, graph, map-balance, validation, builtin, file-cache, standalone native-container, fingerprint and direct-entry suites. The actual locked package plan and manifest check passed using the authenticated ordinary GHC producer; no new installed-native toolchain or full self-bootstrap is claimed.

One additional real compiler task passed **711 fresh / 0 reused**, with both checked artifacts compared directly as raw bytes against the independent reference. This was correctness qualification, not a new performance sample or confirmation cohort. No performance holdout was added. The new 162-control frozen-path suite is now included in O2 CI and its receipts/captures are archived; the existing O0/O2 control results above remain their own evidence. Workflow policy and all 34 CI mutation controls passed locally.

The serial run preserved the 5 GiB free-disk floor and the existing macOS guard's sampled process-tree RSS checks. That guard cannot enforce an address-space limit on macOS. The initial Linux-only watchdog failed on missing `/proc/meminfo` before launching a test; that failed attempt is retained, not counted as a pass.

[Integration record](integration-20261101.json) binds the production identities, commands and result receipts under `.mlf-build/owned-context-integration-20261101/`. It records the subsequent adoption decision separately from the unchanged historical discovery result files.

## Follow-up mechanism evidence

A separate diagnostic used the ordinary checked-link and `prepareChecked` pipeline through a reversible export-only copy of the LLVM module. It repeated the original synchronous demand transfer solely to count rounds, and compared the entire resulting worker inventory with the original analyzer. At dependency-chain sizes 128, 512 and 2048, all three had **48 workers, 3 demand rounds and 4031 summed worker-body node visits**. The complete lowered trees still contain **5329 / 7633 / 16849 nodes**, respectively; the worker subgraph alone is constant. These are mechanism counts, not extra performance samples. They rule out increasing final demand-fixed-point rounds as the explanation for this chain family's scaling; worker counts alone do not describe the size or processing cost of the whole program.

The next unproven hypotheses are earlier in LLVM optimization: `commonCalls` and `substituteUsed` may repeatedly descend a lengthening positive-use path as the chain is inlined; alias elimination may copy a whole remaining suffix. Existing use counts prune zero-use subtrees, so it would be incorrect to call every traversal a full-tree scan. Actual visit/depth/copy counts are needed before changing inlining, sharing, fresh identities or demand order. The current data do not attribute the whole 8.5 seconds to either hypothesis.

Mechanism sources/receipts are under `.mlf-build/owned-reservation-20261101/demand-mechanism*` and `lowered-shape-mechanism*`; the ordinary measurement runner and guards were unchanged. The original two discovery cohorts are never pooled with this one.
