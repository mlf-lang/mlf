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

Implementation and measurements are in progress. No performance improvement
or full qualification pass is claimed yet.
