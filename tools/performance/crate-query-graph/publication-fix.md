# Query publication correction: 2026-11-04

The corrected implementation is **11.4% faster cold**, **36.6% faster warm**, and
**35.7% faster after the fixed single-definition edit** than PR 29 in the new
paired run. Both cold pairs improve. Peak RSS and query storage remain higher
than PR 29. These measurements are separate from the initial implementation run.

## Change

`QueryGraph.record` now retains the immutable encoded bytes that were hashed,
allowing the expanded `W.Value` tree to be released. Publication writes those
bytes directly. The graph index likewise reuses its first encoding.

After successful formal outputs, missing or corrupt results are written to
`staging/` in the cache directory. Renames into `results/` are batched, with at most
64 source paths and a conservative 32 KiB UTF-8 argument budget per subprocess.
Existing valid results keep their bytes and modification times. The index and
`CURRENT` pointer are published only after all required results are ready.
A stopped partial batch leaves the previous generation readable. No result
format, inference rule, or body-check admission policy changes.

## Controls

The ordinary O2 build passed the shared-module, exhaustiveness, inferred-interface,
shared-frontend and exact builtin-regeneration gates. GHC is 9.14.1 with
`-O2 -fpedantic-bottoms -fno-state-hack`, matching the baseline build.

Candidate executable: `6bf5655ed4ae34b1e6e83c35096a10f6949a6d521938f1db0be8870b9a4758f7`.
Baseline: PR 29 `3283899e8ab03af048a674ee41988e454dca813a`, executable
`e5a5121328468354d406fe8a30795f11874b952b60c2a79f0d835212f695aaea`.

All 20 CLI source states and all nine recovery cases passed. Source-query and
actual lowered-fallback checks, cross-executable formal loading, legacy-cache
migration, cross-crate invalidation, and relocation without query caches passed.
The full CLI run used a path containing spaces. Publication controls add 96
distinct definitions and stop after only some result batches have moved; the
old graph and its entire referenced result set must still validate.
Both measurement pairs independently matched all 505 raw versions and every final
interface, body and datatype environment against PR 29.

The original failure fixture could fail while parsing blank lines, before reaching
its intended output/publication boundary. The fixture now filters empty lines,
requires the output/publication diagnostic, and checks that staging and partial
movement actually occurred. The final full run completed without resumption.

## Paired measurement

The unchanged Foundation harness used the baseline 14 modules and the order
**29, candidate, candidate, 29**, with identical input/spec/cache/builtin paths
within the study. Each arm starts with an empty query cache and verified installed
builtin; every stage uses a new process. OS page caches were not flushed.
Correctness controls finished before timed runs. Means contain two samples per arm;
this small sample does not establish a workload-wide confidence interval.

| Stage | Inferred/reused | PR 29 wall (s) | Corrected wall (s) | Wall change | PR 29 CPU (s) | Corrected CPU (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Cold | 504/0 | 22.360 | 19.804 | -11.4% | 22.236 | 19.772 |
| Warm | 0/504 | 7.049 | 4.467 | -36.6% | 6.982 | 4.453 |
| Edit | 1/503 | 7.110 | 4.574 | -35.7% | 7.078 | 4.561 |

All wall samples in execution order:

| Arm | Cold (s) | Warm (s) | Edit (s) |
| --- | ---: | ---: | ---: |
| 0: 29 | 22.358 | 7.172 | 7.143 |
| 1: candidate | 19.842 | 4.427 | 4.617 |
| 2: candidate | 19.767 | 4.508 | 4.531 |
| 3: 29 | 22.361 | 6.926 | 7.077 |

| Stage | PR 29 RSS samples (MiB) | Corrected RSS samples (MiB) | PR 29 cache (bytes) | Corrected cache (bytes) |
| --- | --- | --- | ---: | ---: |
| Cold | 133.48, 133.47 | 159.98, 158.89 | 4,323,425 | 7,241,088 |
| Warm | 124.16, 124.25 | 131.75, 131.97 | 4,323,425 | 7,241,088 |
| Edit | 124.27, 123.27 | 135.70, 134.89 | 4,343,056 | 8,437,553 |

Mean cold peak RSS is **133.48 MiB for PR 29 and 159.44 MiB for the correction**.
The initial implementation measured 202.43 MiB in its earlier run; that is a
separate measurement, not another sample in the current paired mean. The output
format and its byte sizes are unchanged by this publication correction. Old
generations and unreachable staging files are still retained; no disk GC is added.

## Separate phase measurement

| Stage | Graph/providers (ms) | Raw load (ms) | Infer/check (ms) | Finish (ms) | Formal output (ms) | Publish (ms) | End-to-end (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Cold | 1,297 | 1 | 16,123 | 756 | 577 | 394 | 19.943 |
| Warm | 1,474 | 735 | 0 | 729 | 587 | 221 | 4.542 |
| Edit | 1,500 | 760 | 97 | 745 | 560 | 218 | 4.656 |

Cold publication measured **394 ms**, compared with **3,010 ms** in the initial
implementation's separate profile. These phase runs are not pooled into ABBA.
Warm cache writes remain **zero bytes**, verified by content and modification time.
The cold graph still has 3,403 nodes and 7,241,088 reachable bytes. Removing duplicate
encoding and per-result subprocesses does not remove dependency-graph storage.
RSS is a process peak, not a per-type heap-retainer or GC-time measurement.

## Evidence

Current qualification, controls, samples and independent artifact comparisons are
pinned in [`evidence.json`](evidence.json). Initial measurements are preserved in
[`evidence-before-publication-fix.json`](evidence-before-publication-fix.json).
Use the commands in [`README.md`](README.md) to reproduce with fresh directories.

Final study: `/tmp/mlf-query-publication-foundation`.
Separate profile: `/tmp/mlf-query-publication-profile`.
Full CLI controls: `/tmp/mlf-query-publication-acceptance-2 with spaces`.
Source controls: `/tmp/mlf-query-publication-source`.
External controls: `/tmp/mlf-query-publication-external-2-relocated`.
