# Inferred-chain empty-constructor follow-up, 2026-11-17

The empty-constructor prototype is rejected. It preserves complete planning tables, exact bytes, admission, demand order and cache behavior, but does not improve the large-size compiler time; its small allocation saving accompanies higher live heap and RSS. The maintained compiler is unchanged by this follow-up, and the unsigned monomorphic `inferred_chain` shape remains unaccepted.

Evidence directory: `.mlf-build/inferred-chain-empty-tasks-20261117`. The authenticated ordinary baseline is the retained package-reference producer from [the previous study](compiler-inferred-chain-references-2026-11-17.md). This task does not commit or push, advance the shape, change the acceptance gates, or repeat an unchanged-source GHC cohort.

## Fresh attribution

Six current-source GHC-hosted profiles cover two runs each at N=0/256/1024 with query timers disabled. All six interface/object/LLVM outputs exactly equal the ordinary producer. Caller-owned leaf ticks and allocation reconcile to the profile totals. Instrumented timing is attribution only, not an acceptance measurement.

| Growth owner, N1024 minus N0 | Sampled ms | Allocated MB |
| --- | ---: | ---: |
| `unattributed / outside selected business modules` | 74.050 | 105.417 |
| `Bootstrap.OpenFragment / makePackage` | 21.200 | 75.446 |
| `Bootstrap.QueryGraph / encodeHashed1` | 14.200 | 57.630 |
| `Bootstrap.CrateGraph / $wpreparedValueCached` | 5.900 | 21.758 |
| `Bootstrap.CrateGraph / $wpreparedSyntax` | 4.450 | 18.211 |
| `Bootstrap.CrateArtifact / writeOpenObject` | 4.350 | 18.158 |
| `Bootstrap.CrateGraph / runGroupsWithOwner` | 6.900 | 14.376 |
| `Bootstrap.Dependency / $wresolvedGroupsWith` | 3.550 | 12.387 |

The outside-owner bucket includes GC and profiler overhead as well as frontend work; it is not a single compiler hotspot. `Parsec.pSatisfyState` accounts for 16.953 MB of allocation growth there. That worker is already optimized in the retained compiler: any further frontend experiment must first distinguish itself from the earlier rejected parser-dispatch/error-construction experiments.

An independent decoder counts occurrences by propagating root multiplicity over each persisted document DAG:

| N | Documents | Expanded values | Empty constructors | Singleton constructors |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 6 | 457 | 56 | 61 |
| 256 | 8 | 22853 | 2370 | 3405 |
| 1024 | 8 | 89669 | 9282 | 13389 |

These counts cover persisted object/interface/query documents only. They exclude temporary hash-only inputs and are not estimates of milliseconds or bytes allocated.

## Candidate and validation

The private Bitstream shadow does two related changes: after the original depth/work/tag checks, an empty `VNode` is interned directly instead of allocating empty-child and close tasks; empty constructor keys use their own per-plan exact tag-to-node index. All nonempty key routing, root work charges, node IDs and wire formats remain unchanged. The index is bounded by distinct empty tags within the existing plan. This does not change asymptotic complexity of the entire compiler.

This differs from the previously rejected arity/tag-major key layout, but that earlier negative result remains relevant. No global cache, hash-only equality, broader resource limit, new format or compiler primitive is introduced. The combined candidate is evaluated as one variant; this experiment does not isolate each component.

The frozen oracle is the current maintained Bitstream, independently compiled next to the candidate. Validation passes 5,364 complete table cases, 16,092 root-budget cases, 166 generic and 166 production-root wire cases, seven demand-order cases, ten targeted error priorities, twelve deep/frame controls and eight nullary groups. Explicit nullary tags span 0 through 2,147,483,647, including the packed-key eligibility boundary.

The actual candidate objects also pass constructor/admission/base64/source-admission/typed-bound controls, declaration-query controls, and query-index pure/publication controls. All 42 timed compiles and 12 instrumented-memory compiles preserve exact interface/object/LLVM bytes. All 126 native results from the timed runs match the independent arithmetic oracle. These focused checks do not newly qualify native self-bootstrap, the installed CLI, or previously outstanding native O0 codec/QuerySnapshotProbe paths.

## Fixed diagnostic screen

One warmup and six measured alternating pairs at each size. Timed compiler and Clang subprocess sums are diagnostic; they are not the full-worker acceptance boundary. No extra confirmation was run after this failed large-size screen.

| N | Compiler before (s) | Compiler candidate (s) | Compiler + Clang before (s) | Compiler + Clang candidate (s) |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 0.135059208 | 0.133004938 | 0.282140083 | 0.271327375 |
| 256 | 0.177099000 | 0.170956105 | 0.316038541 | 0.305691355 |
| 1024 | 0.299394104 | 0.304763187 | 0.440211395 | 0.443431812 |

## Separate memory experiment

Three alternating instrumented pairs per size; these times are excluded from the speed screen. Values are medians. Bytes allocated are cumulative allocation, maximum residency is sampled live heap, and child RSS is an operating-system peak; they measure different things.

| N | Variant | Allocated bytes | Maximum live heap bytes | Peak child RSS bytes |
| ---: | --- | ---: | ---: | ---: |
| 0 | before | 269,574,568 | 1,422,720 | 33,964,032 |
| 0 | nullary-index | 269,526,584 | 1,438,304 | 34,013,184 |
| 1024 | before | 861,194,848 | 11,228,072 | 61,685,760 |
| 1024 | nullary-index | 859,183,424 | 12,468,992 | 62,603,264 |

At N1024 the allocation saving is 2,011,424 bytes (0.234%), while live heap increases by 1,240,920 bytes (11.05%) and RSS by 917,504 bytes. The extra private index and changed collection behavior are not justified by these results. The shadow remains in ignored diagnostic storage; it is not adopted.

## Current GHC status and next work

The previous current-source formal cohort remains authoritative: 32 alternating pairs at N=0/32/64/128/256/512/1024 on `crate-fused-v1`. MLF remains faster at every positive size, but the growth gates still fail. No new formal fit is derived from this three-point diagnostic screen.

| Formal metric | MLF | GHC |
| --- | ---: | ---: |
| OLS ms/function | 0.154628934 | 0.152832382 |
| Endpoint ms/function | 0.159122925 | 0.158078450 |
| Offset-power fitted p | 1.090405880 | 1.069607640 |

Finite-size fitted exponents are not a proof of asymptotic complexity. Retain the original pointwise, slope, exponent and paired confidence requirements. Remain on `inferred_chain`; inspect the fresh caller/allocation evidence for avoidable construction before considering another candidate. Any frontend follow-up must audit the earlier rejected parser variants first. Do not rerun an unchanged formal cohort hoping for a favorable sample.

## Evidence receipts

| Receipt | SHA-256 |
| --- | --- |
| `baseline-check.json` | `ef9432405b5e6802c6ab3aca21ae8b072b5a7ee42ab909471d876a4043b96376` |
| `profile-current/receipt.json` | `d544330b756b4f44e82a53e313e994d78cd2149804b3898917c23b8573dc4237` |
| `analysis.json` | `77735024dc6dcf9b56edb7f4896cd815d98dd14e343d11821e716ff6342aa204` |
| `scalar-counts.json` | `62b6f86affc639d6e5b052b6a14d3417a68f540350970a21f74b1858edae9e2b` |
| `nullary-plan.json` | `46578f230861c079a52356f0449552b713a123d8b6cefaf6868afd417174dfbc` |
| `nullary-index/receipt.json` | `88ed941e51c2ebd1d463987e3faf5a28fdb9731d28bff8e3f779c6f5380fb17f` |
| `nullary-index-controls/receipt.json` | `a7b499dc3c68780998ff7fce02bf27b4159f5b3a5bb92f18540f291de43d7765` |
| `nullary-index-screen/receipt.json` | `b47e6cd198a729ba2e076ab560c7743dd130684b597c1a652b8b46dd9ca541dd` |
| `nullary-index-memory/receipt.json` | `8df26b516153808037b1e9f72160b09248fb362eb7c45bacf00f49b0966dcbea` |
