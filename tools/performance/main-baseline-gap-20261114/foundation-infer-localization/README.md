# Foundation infer localization (diagnostic-only)

This small diagnostic patch targets baseline main `fc300bc9fdc389b585cbef0630fc8915d53e89c5`. It changes only `Bootstrap.CrateGraph` and `Bootstrap.QueryGraph`, leaving baseline IntRank and the pure solver/checker implementations unchanged. Compiler C is a separately identified ordinary GHC 9.14.1 build, not a replacement for historical A or B.

## Workload and observed baseline

Use the normal `mlf-foundation/0.3.0/library` manifest boundary: 15 baseline modules, 211763 source bytes, NoEntry, a previously validated read-only builtin dependency and a fresh query cache. This is not the earlier 90-module monolithic checked-crate diagnostic or a full package/native build.

The original A reference completed in 26.057009766 s, with wait4 maxRSS 142244 KiB and 532 fresh groups / 539 members / 14 value owners. Its original six profile buckets were graph 1210, load 1, infer 22531, finish 226, output 783 and publish 400 ms. Their sum is 25151 ms; the signed CLI residual is 906.009766 ms. The infer interval is about 86.5% of this one instrumented target wall time, not a causal CPU attribution.

## Minimal added observations

`MLF_QUERY_PROFILE=1` retains the original six counters and adds:

- `infer_compile_open_ms`: compileOpenGroup* and naturally demanded checked compilation, not an isolated solver timer.
- `infer_canonical_ms`: canonicalOpen.
- `infer_validate_prepared_ms`: prepared-owner/root/slot validation; other checker work remains in compile-open.
- `infer_record_ms`: raw InferScc record IO.
- `infer_record_encode_ms` and `infer_record_digest_ms`: nested encoding and digest IO intervals inside record.

The patch observes the Either constructors already selected by existing binds. It does not deep-force successful payloads, bypass checks or change deterministic artifact schemas. Deferred AST construction may be forced by encoding; digest-string validation and lazy session/map updates may occur later. Added IO boundaries and GHC optimization can shift where work is observed.

**Do not add all twelve counters.** Infer includes its immediate children; record includes encode and digest. Report the three signed unclassified residuals separately. Integer-ms rounding and instrumentation overhead can produce negative residuals. These buckets are instrumented wall time, not exclusive CPU costs, a full ledger or natural causal attribution.

## Actual single-C result

The sole C target completed successfully: 25.159405473 s wall, 25.193538 s CPU (24.924526 user + 0.269012 system), wait4 maxRSS 137064 KiB; whole diagnostic phase 42.786176385 s. Raw CI/CO, the original ordered 532 fresh groups / 539 members / 14 value owners, and the complete query report all matched the saved A reference. Input postchecks, cleanup and lock reacquisition passed. Independent actual-run review verified all 1,670 evidence files, raw/reference comparisons, bucket arithmetic and preservation checks. Exact raw evidence was privately archived and fully read back before publication.

| Instrumented wall bucket | ms |
| --- | ---: |
| graph | 1168 |
| load | 1 |
| infer (inclusive) | 21810 |
| finish | 226 |
| output | 821 |
| publish | 376 |
| infer: compile-open | 20378 |
| infer: canonical | 273 |
| infer: prepared validation | 3 |
| infer: raw record (inclusive) | 1149 |
| record: encode | 1121 |
| record: digest | 22 |

The signed residuals are CLI 757.405473 ms, infer 7 ms and record 6 ms. Within this instrumented observation, compile-open accounts for about 93.4% of infer. Encoding/hash is not the dominant observed interval; the next localization priority is the natural constraint-generation/solve/checking pipeline inside compile-open. That bucket is not a pure solver measurement, and deferred work can cross the labels.

The fixed contract was one target (180 s cap, 300 s phase, unchanged 4 GiB per-process address-space limit), with no retries or extra samples. Compiler diagnostic overlays were not workload source inputs. Do not interpret the difference between the separately instrumented A and C wall times as an optimization gain.

No A/B speedup, stable performance or merge conclusion is supported: performance samples are **zero**. Native generation and fixed-point work remain paused. The earlier 90-module monolithic **A** diagnostic exited 251 under its unchanged memory limit; it is not a candidate B regression and remains INCONCLUSIVE; its actual peak memory was not recorded.

`diagnostic.patch` uses repository-relative paths. No private runners, local machine paths, raw binaries or private storage references are included.
