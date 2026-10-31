# Restricted batched let substitution

A restricted owned optimizer records already-fresh-copied substitutions while unwinding contiguous nonrecursive lets and materializes the body once at a boundary. The checked standalone and fixed-library LLVM entry points use it; the public raw optimizer remains unchanged.

## Current decision

The fixed discovery window did **not** meet its advancement rule: both 2048-point whole-compilation reductions had to be at least 5%. The observed reductions were 3.14% and 5.07%. No confirmation window or additional performance samples were run. The structural mechanism is supported; a stable overall speedup is not claimed. After correctness qualification, the change is integrated as an engineering decision to meet the explicitly requested structural goal: remove repeated ancestor reconstruction on the admitted chains. This does not turn the failed 5% performance gate into a pass or establish a stable whole-compiler speedup.

## Algorithm and obligations

Admission requires a normalized syntactic lambda with the existing bounded `smallValue` property, exactly one free use, and a scoped sufficient witness that legacy common-call specialization would reject. Copies execute at the original inner-to-outer decision points. A separate `PendingBody` stores the original skeleton, direct identity-keyed already-copied replacements, exact capped root counts, and sufficient negative-call witnesses. It never presents stale child indices as current.

Each outer RHS is out of scope of eliminated inner binders; globally unique binder identities make recursive map expansion acyclic and capture-free. Materialization performs no Fresh operation or beta reduction. A missing witness or unsupported let first flushes the body, then uses the original rewrite logic. Existing nonvariable-argument witnesses survive leaf substitution; incomplete witness discovery only falls back. This is an output-sensitive improvement for admitted batches; map lookups/updates, use-index construction and fallback still have costs. It is not a claim that all compiler work is linear.

## Fixed ordinary discovery

Baseline is accepted `7bf7ac6d`; its complete source was frozen and built once independently. Both ordinary producers use GHC 9.14.1 O2 with the existing demand flags. Each workload has one predeclared ABBA/BAAB block, two samples per side. All 16 builds use the standard compiler-shapes worker, serial ordinary Clang O2, fresh target inference, fixed dependencies, exact checked-byte references and three closed-form executable-output checks. Both 2048 chain cases have 2051 fresh / 0 reused groups per run.

Values are descriptive geometric times; no confidence interval or portability claim.

| Input | Baseline seconds | Candidate seconds | Whole-run reduction | Checked-to-LLVM median A / B seconds |
|---|---:|---:|---:|---:|
| dependency_chain-2048 | 18.990 | 18.393 | 3.14% | 7.744 / 7.105 |
| flat_functions-512 | 3.843 | 3.837 | 0.16% | 0.764 / 0.778 |
| inferred_chain-2048 | 20.000 | 18.987 | 5.07% | 7.773 / 7.153 |
| higher_order_chain-128 | 0.937 | 0.983 | -4.92% | 0.455 / 0.481 |

The two non-chain guard cells were added before the first sample because full witness scans and materialization may penalize sparse admissions or repeated fallback. Neither triggered the predefined regression rule (slower by both more than 5% and more than 0.1 second). That limited screen does not prove absence of regressions elsewhere.

## Mechanism evidence

Both chain families gave the following demanded diagnostic events. All eight diagnostic LLVM outputs exactly matched ordinary baseline LLVM bytes.

| Generated functions | Admitted replacements | Nonempty batches | Materialization visits | Negative-witness visits | Remaining common-call visits | Remaining substitution visits |
|---:|---:|---:|---:|---:|---:|---:|
| 32 | 32 | 2: 1 + 31 | 292 | 706 | 133 | 6197 |
| 128 | 128 | 2: 1 + 127 | 1060 | 1474 | 133 | 6197 |
| 512 | 512 | 2: 1 + 511 | 4132 | 4546 | 133 | 6197 |
| 2048 | 2048 | 2: 1 + 2047 | 16420 | 16834 | 133 | 6197 |

At 2048 the prior diagnostic recorded 4,210,819 common-call visits, 6,321,202 substitution visits and 4,209,568 substitution parent rebuilds. The candidate has 133, 6,197 and 2,978 respectively. In this measured shape, materialization visits are `8N + 36` and witness visits `8N + 450`; the base skeleton contributes 42 visits. Remaining full pipeline work is outside this conclusion.

These counters come from private reversible instrumentation with CSE/full-laziness disabled. They count demanded source paths, not physical allocations or ordinary CPU time. Overlapping counters must not be summed as a time breakdown. Exact LLVM equality establishes output equality for these inputs, not identical demand across all possible partial values.

## Correctness and reproduction

O0 and O2 private controls compare the full frozen 7bf7ac6d optimizer with the candidate: exact trees, hints, Fresh seeds, independently recomputed per-node counts, witness implication, batches of sizes 2/16/128, explicit inner-before-outer numbering, fallback, public raw partial values and IO behavior. There are 400 generated inputs (ten shape templates at forty IDs/literals) and 18 authored IO source inputs. The witness success control establishes nonvacuity; it is not a mutation-sensitivity experiment.

The O2 driver initially failed before compiling because GHC needed local copied dependency interfaces. The failed attempt remains archived. The corrected O2 run completed twice before the runner was simplified to one execution; O0 ran once. Exact earlier runner snapshots match their receipt hashes, and production sources did not change between these qualifications.

The builtin preparation closure is unchanged, so no builtin regeneration was needed. The source admission is an additive three-owner layer after the existing sparse-contracts layer; all prior manifests and oracles remain pinned. Both checked LLVM callsites are included. The locked source snapshot was refreshed.

Raw evidence is under `.mlf-build/batch-replacement-20261101/`: `controls-o0-01`, `controls-o2-02`, `mechanism-01`, `baseline-producer`, `producer`, `discovery`, and their receipts. [Summary data](results-20261101.json) retains individual ordinary times, stage medians, diagnostic counters and source identities. `protocol.md` beside the raw evidence preserves the unexecuted confirmation schedule as well as the closed discovery rules.

Focused CI reproduction against an ordinary producer:

```sh
python3 -B tools/performance/batch-replacement/run.py \
  --producer .mlf-build/shared-ghc \
  --output .mlf-build/batch-replacement-20261101/ci-controls
```

The frozen oracle is loaded from its full Git revision and checked against its fixed SHA-256; a complete fetch is required. The new CI step records receipts, logs and private source copies.

## Integration qualification and decision

The final ordinary producer passed retained P1–P3, graph, Map-balance, validation, builtin, fixed native-library, standalone native-container, fingerprint, direct-entry and lazy-IO suites. The fixed-library gate covers O0/O2 native execution. All 18 IO source cases emitted through the checked owned optimizer and passed native execution; the fixture's direct interpreted optimized-erased leg still deliberately uses the legacy public optimizer. The actual `mlfpkg --locked plan` and manifest snapshot check passed. CI policy and its 34 mutation controls passed; the new frozen-optimizer suite is included in O2 CI.

The first native-IO attempt passed host semantics/emission, then failed C runtime compilation because the macOS GMP header path was missing. The failure and exact earlier wrapper are retained. Adding an explicit recorded GMP include path allowed the unchanged tests to complete in a fresh attempt; no compiler or runtime source changed. [Integration receipts and boundaries](integration-20261101.json) record both attempts, not just the successful one.

This adoption values the verified structural removal and the scoped ordinary observations. It does **not** relax or retrospectively pass the closed discovery criterion: the predeclared confirmation window remains unexecuted. Costs include roughly 200 lines of owned-path implementation, duplicated legacy/owned traversal scaffolding, witness discovery and whole-batch materialization. Sparse admission and unrelated inputs remain potential performance costs; the two ordinary guard cells and authored semantics cases cover only the tested scope. No allocation, disk saving, universal growth-class improvement, installed self-bootstrap or 711-group inference speedup is claimed.
