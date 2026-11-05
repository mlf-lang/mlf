# PR 29 integration and measurement: 2026-11-04

The combined implementation is **20.1% faster cold**, **48.7% faster warm**, and
**47.9% faster after the fixed single-definition edit** than the pinned PR 29
baseline in this paired run. Both pairs improve at all three stages. Peak RSS and
query storage remain higher than the baseline.

This incorporates PR 36 (`5ee8f67a`) into the graph implementation originally
committed as `2f046d28`. It preserves the upstream source admission/publication
optimizations and adds the graph's transactional publication and checked open
artifacts. These measurements compare the **combined implementation** against
`3283899e8ab03af048a674ee41988e454dca813a`; they do not isolate the graph's effect
relative to PR 36. The pre-integration measurement remains in
[`publication-fix.md`](publication-fix.md) and
[`evidence-before-pr36-merge.json`](evidence-before-pr36-merge.json).

Before pushing, PR 29 advanced to `4f913c87` with an independent Int64 Core-check
correction. It was also merged normally. Only its test/analyzer and CI files
changed; all 135 shared-source, 33 host-input and 19 build-configuration pins were
reverified unchanged. Its ten focused tests passed in both normal and optimized
Python modes. The qualified compiler and measurements above are unchanged.

## Qualification and integration

The ordinary bootstrap build completed with GHC 9.14.1 and
`-O2 -fpedantic-bottoms -fno-state-hack`, using one GHC job. Its shared-module,
exhaustiveness, inferred-interface, shared-frontend and exact builtin-regeneration
gates passed. All 135 shared modules, build inputs and executables are pinned in
[`evidence.json`](evidence.json).

Baseline executable:
`e5a5121328468354d406fe8a30795f11874b952b60c2a79f0d835212f695aaea`.
Candidate executable:
`510db4dbc1b61cf24cc948d5e32e27629c63827c6a150b31441ebe575b45c26e`.

Integration also preserves the Windows host helper's calling convention: it
accepts one source and an exact destination file, while POSIX uses bounded
multi-source moves into the result directory. This run qualified macOS; it does
not claim Windows execution coverage.

The final compiler passed:

- All 20 real CLI source states and nine recovery cases, including partial result
  batches, previous-generation closure, concurrent writers, and paths with spaces.
- Source-query changes, red/green propagation, compiler/builtin namespaces,
  independently checked contracts/bodies and runtime results, and the actual
  lowered fallback.
- Actual `CrateSession.compileSpecFile` calls in one process: cold and warm failures,
  unpublished successful prerequisites, lock release on retry, retained generation,
  and byte-identical restored final artifacts.
- Old-cache migration, mixed legacy/open objects, cross-crate body/type changes,
  cross-executable formal loading, native literal compatibility, and relocation
  with query caches removed.
- Independent comparisons of all **505 raw versions** and all final interfaces,
  bodies and environments in each of the two baseline/candidate pairs.

The retained legacy Query API has a separate 29-command run, including all 63
frozen decoder differential cases and their exact assertions. Eleven old-format
Session commands are excluded explicitly with `--legacy-query-only`; the graph
CLI and same-process Session controls above exercise the replacement route.
The default historical 40-command mode remains available. CI runs both the new
graph controls and the selected legacy controls. This is not a claim that the
historical 40-command suite passed on the new graph CLI.

The provenance/manifest regression suite ran 86 tests: 82 passed and four were
skipped on macOS for `/proc`-dependent process cleanup. The regenerated lock passed
`mlfpkg --offline --locked plan`. These additional receipts and their scope are in
[`integration-checks.json`](integration-checks.json).

## Paired measurement

The Foundation harness used the baseline's 14 modules and the fixed order
**29, candidate, candidate, 29**. Source/spec/cache/builtin paths, GHC and compiler
flags were matched. Each arm starts with an empty query cache and an already
verified builtin; every stage uses a fresh process. OS page caches were not
flushed. Correctness controls finished before timing, and the phase profile ran
separately. The edit changes only `Bootstrap.Version.version` from `0.3.0` to
`0.3.1`. Every arm produced **504/0**, **0/504** and **1/503** inferred/reused groups.

Means contain two samples per arm. Positive wall change means slower.

| Stage | Baseline wall (s) | Combined wall (s) | Wall change | Baseline CPU (s) | Combined CPU (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Cold | 22.536 | 17.995 | -20.1% | 22.382 | 17.967 |
| Warm | 7.105 | 3.646 | -48.7% | 7.016 | 3.638 |
| Edit | 7.150 | 3.722 | -47.9% | 7.107 | 3.708 |

All wall samples in execution order:

| Arm | Cold (s) | Warm (s) | Edit (s) |
| --- | ---: | ---: | ---: |
| 0: 29 | 22.567 | 7.023 | 7.165 |
| 1: candidate | 18.114 | 3.577 | 3.773 |
| 2: candidate | 17.876 | 3.715 | 3.670 |
| 3: 29 | 22.505 | 7.187 | 7.136 |

| Stage | Baseline RSS samples (MiB) | Combined RSS samples (MiB) | Baseline retained cache (bytes) | Combined retained cache (bytes) |
| --- | --- | --- | ---: | ---: |
| Cold | 139.53, 129.45 | 151.61, 151.58 | 4,323,425 | 7,241,088 |
| Warm | 127.22, 127.30 | 129.53, 129.52 | 4,323,425 | 7,241,088 |
| Edit | 122.39, 122.44 | 137.59, 137.56 | 4,343,056 | 8,437,553 |

Mean cold peak RSS is **134.49 MiB for the baseline and
151.59 MiB for the combination**. The paired cold `.mlfco` is
1,234,082 bytes versus 1,004,044 bytes; `.mlfci` is
313,337 versus 313,381 bytes. Interface differences
include the format-specific object checksum; final semantic comparisons pass.

## Separate phase profile

| Stage | Graph/providers (ms) | Raw load/integrity (ms) | Infer/check (ms) | Finish (ms) | Formal output (ms) | Publish (ms) | End-to-end (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Cold | 1,020 | 0 | 14,911 | 680 | 470 | 364 | 17.994 |
| Warm | 1,179 | 562 | 1 | 661 | 477 | 191 | 3.596 |
| Edit | 1,263 | 619 | 89 | 696 | 482 | 198 | 3.871 |

The warm 1 ms infer-phase total is timer/bookkeeping overhead: the inferred group
count is zero. Normal warm raw loading performs no independent body checks;
source finishing and checks of newly created evidence adapters remain separate.
The baseline is uninstrumented, so these clocks do not isolate baseline/candidate
phase differences. Uninstrumented frontend/builtin/other work remains in the
end-to-end total.

The profile has 3,403 graph nodes. Reachable storage is 7,241,088 bytes cold/warm
and 7,241,087 after the edit; retained storage after the edit is 8,437,553 bytes.
Warm writes are zero bytes, with file content and mtimes unchanged. The edit
writes 1,196,612 bytes, including a new graph index and changed result payloads.
Active encoded raw is 5,632,090 bytes before the edit, alongside a 1,004,044-byte
final object. These byte sizes do not measure individual heap residency.

No disk GC is implemented: old generations and abandoned staging files can remain.
The observed RSS increase must not be attributed solely to delayed publication
without a heap-retainer study. Two samples per arm on this workload do not
establish a general speedup distribution or confidence interval.

## Evidence locations

The final full control runs and paired study completed without resumption.
Production/build pins, all 12 samples, all three profile samples and the completed
control records are retained in [`evidence.json`](evidence.json). Raw outputs are
under `/tmp/mlf-query-pr29-push-foundation`; the separate profile is
`/tmp/mlf-query-pr29-push-profile`. Final control directories are
`/tmp/mlf-query-pr29-push-cli with spaces`,
`/tmp/mlf-query-pr29-push-external-relocated`,
`/tmp/mlf-query-pr29-push-source`, and
`/private/tmp/mlf-query-pr29-push-legacy`.

The intermediate `1af64efe` merged binary's successful controls and timing run
remain under `/tmp/mlf-query-pr29-merge-*`. They were superseded by the Windows
transport correction and are not samples in this final result. The original
historical Session control failure is retained separately; it is not relabelled
as a passing 40-command run.
