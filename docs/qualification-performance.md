# Qualification performance work

This change starts from main `e7da00f201bfb66bf6e26d59e56184dd37a83abd`,
after #7 and #10. Their optimizations are already in the baseline.

## Required changes

- Build the private `compiler-tests` campaign runner once with the final
  candidate compiler and manager. Transfer its unchanged producer report,
  executable artifact key, dependency closure and binary hashes. Consumers
  fail closed on source, platform, root, toolchain or artifact mismatch and
  execute fresh campaigns without rebuilding the runner.
- Split Core's expensive compilation closure into independently compilable
  targets. Preserve logical family IDs, exact coverage and full-campaign
  evidence. Batch unit targets into one build DAG and execute tests serially.
- Expose bounded build parallelism, defaulting to one. Enable two only where
  measured concurrent process-tree memory plus headroom fits the runner.
  In particular, the 7 GiB macOS runner stays at one without such evidence.

## Validation and measurement plan

Compare the merged baseline, runner reuse, split unit with jobs=1, and jobs=2
with the same native compiler, manager, native helper, toolchain and GC policy.
Keep cold and warm artifact stores separate. Retain every build invocation,
measure process-tree peak RSS and observed scheduler parallelism, and use at
least three alternating paired samples where feasible. Report all samples,
median/range, aggregate task work and the critical path separately. A single
or noisy run is not evidence of a speedup.

The six campaigns, 25 Port fixtures, Windows qualification, SDK packaging and
fresh self-host fixed point remain required. The previous validation waiver
applied to merging #7/#10 only. This draft is not ready to merge until the new
implementation has its own validation and independent review.

## Results

Implemented:

- Candidate manifest format 2 carries the final-compiler campaign producer
  report, original publication key and file hashes, full native artifact store
  closure, and exact source/platform/root/native-tool identities. Both producer
  export and consumer import/verification validate the original artifact and
  publication receipts; merely hashing changed files at export is insufficient.
- Consumers verify the shared runner before and after executing their own
  campaign. They never invoke a local runner build and never import a campaign
  execution verdict. The package aggregator compares producer proofs across
  all six groups.
- Core has four physical targets: `core-crates`, `core-solver`, `core-language`
  and `core-modules`. The legacy `core` CLI remains available. Full unit builds
  nine physical targets in one DAG and executes them sequentially. Partial
  child reports stay partial; the logical full `core` result is formed from
  validated actual completion events, then checked against the unchanged full
  inventory. Packaging hashes all nine binaries and the retained build report.
- `MLF_TEST_BUILD_JOBS` accepts 1 or 2. CI remains at 1 pending measured memory
  and timing evidence. The shell admission policy currently permits 2 only on
  Linux hosts with at least 14 GiB RAM; that check alone is not a memory proof.
- Every nested suite invocation retains its unmodified build report and records
  its hash, command, target set, exit code and requested parallelism.

Validation so far:

- 16 transport/provenance fault-injection checks pass, including pre-export
  mutation of both published/cache bytes, missing dependency proof, stale
  compiler/source, root/platform/toolchain drift and no-rebuild execution.
- 11 split-unit evidence checks pass, including all physical binaries, missing
  receipts/targets, duplicated targets, false full scope and consistently
  rehashed child/aggregate inventory corruption.
- 10 bounded-parallelism policy checks and three process-tree sampler tests pass.
- Shell/release checks and Actionlint pass. Independent source review confirms
  all 18 moved Core declarations/helpers are byte-for-byte unchanged. Static
  plans preserve 34 families, 684 execution IDs and exact aliases/metrics, and
  exclude the unrelated Core registries from each physical compile closure.

These are structural and contract checks, not a full native qualification.
Native runner/unit execution, paired performance evidence, macOS/Windows and
full SDK qualification remain in progress. No performance improvement or full
qualification pass is claimed yet.
