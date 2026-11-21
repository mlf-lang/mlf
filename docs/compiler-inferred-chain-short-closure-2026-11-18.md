# Inferred chain: current growth and short-constructor closure

The private short-constructor closure change is **rejected**. No maintained compiler source, builtin, lock, ABI, wire format or test source changes in this investigation. The unsigned monomorphic `inferred_chain` remains unaccepted.

Evidence: `.mlf-build/inferred-chain-current-growth-20261118`. The preceding [retained colon-escape study](compiler-inferred-chain-prepared-structure-2026-11-18.md) and current producer are reauthenticated against 318 source pins and 35,268 evidence pins. The preceding turn made verified progress through a source change, retained memory reduction, regression and a new formal cohort. All previous dirty work is preserved.

## Fresh current-source attribution

Six new profiles, two each at N=0/256/1024, use the actual current source, late cost centres, unchanged F4 and a 0.1 ms tick. Query phase timers are disabled. Every interface/object/LLVM byte matches the current producer. Leaf-owned ticks and allocation reconcile to profile totals. Instrumented timing diagnoses ownership, not formal speed.

| Exclusive selected owner, N1024 minus N0 | Sampled ms | Allocated MB |
| --- | ---: | ---: |
| `unattributed / outside selected business modules` | 76.450 | 105.414 |
| `Bootstrap.OpenFragment / makePackage` | 19.400 | 69.986 |
| `Bootstrap.QueryGraph / encodeHashed1` | 13.600 | 54.276 |
| `Bootstrap.CrateGraph / $wpreparedValueCached` | 6.850 | 21.758 |
| `Bootstrap.CrateGraph / $wpreparedSyntax` | 4.250 | 18.211 |
| `Bootstrap.CrateArtifact / writeOpenObject` | 3.850 | 17.093 |
| `Bootstrap.CrateGraph / runGroupsWithOwner` | 6.650 | 14.376 |
| `Bootstrap.Dependency / $wresolvedGroupsWith` | 3.450 | 12.387 |

The outside-owner bucket includes 35.15 ms of GC and 9.35 ms of profiler overhead, plus actual frontend work. It is not one business hotspot. Inclusive `makePackage` is 20.65 ms / 74.665 MB, including its nested callees; do not add it to the exclusive owner. Inclusive query publication encoding is 9.50 ms / 37.597 MB, and package-metadata encoding is 3.80 ms / 16.291 MB. Within package planning, `planTasks` contributes 3.65 ms / 15.311 MB of own growth.

A possible typed-reference memo refinement was examined but not implemented: existing reference hashing already accounts for only 0.35 ms / 0.887 MB of growth. The current profiles instead support investigating temporary planner construction. Prior empty-node indexes, EncodeOne elision, shallow recursion, subtree memoization, owned probing, lookup/insert fusion, word writers, string framing and RTS variants were reviewed before selecting the new experiment.

## Private implementation and qualification

After all children have been visited and charged, the new `planClose` inspects one, two or three canonical child IDs directly on the reference stack. It computes the existing injective packed key. A hit resumes the planner without allocating the reversed child list and temporary `ENode`. A miss allocates the ordinary entry and performs the original node/edge-limit checks in their original order. Larger tags, large IDs, other arities and underflow use the original path. No new cache, mutable index, hash-only equality or resource allowance is introduced.

This differs from the earlier nullary and task-dispatch experiments: it only changes closure of already visited nonempty small nodes and uses the current exact packed index. It does not bypass subtree work or change canonical numbering.

Coherent `ghc --make` closures with Core lint qualify the actual candidate source. The independent pre-change codec is frozen beside it. Controls pass 9,240 synthetic closure-boundary comparisons (including tag/ID packing limits, misses/hits, physical-limit priority and underflow), cached-hit demand and counter checks, 5,364 complete table comparisons, 16,092 root-budget comparisons, 166 generic and 166 production-root wire comparisons, seven demand orders, ten targeted error priorities, twelve depth/frame controls and eight nullary groups. The synthetic boundary states isolate closure behavior; complete valid tables and wire encodings are checked separately.

Actual candidate objects also pass artifact constructor/admission/base64/source/typed-bound, declaration/cache, query-index and publication controls. All 42 timed compiles preserve exact interface/object/LLVM bytes and pass 126 native arithmetic outputs. All 12 memory compiles preserve the same bytes. Independently decoded query contents match while verifying each actual compiler executable hash in its configuration.

Native compiler self-bootstrap, installed CLI and the previously recorded native O0 codec/QuerySnapshotProbe gaps remain unqualified. This rejected private path is not put through a new full retained-source qualification.

## Fixed diagnostic screen

One warmup and six measured alternating pairs per size, with fresh output/query paths. Compiler-plus-Clang is a subprocess sum and excludes the formal worker boundary. No concurrent build, profile or memory workload ran during timing.

| N | Compiler before ms | Compiler candidate ms | Compiler + Clang before ms | Compiler + Clang candidate ms |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 130.806 | 133.002 | 272.940 | 276.903 |
| 256 | 167.530 | 167.483 | 299.447 | 301.757 |
| 1024 | 289.098 | 289.922 | 427.351 | 421.736 |

The N1024 compiler-only median increases by 0.823 ms. The lower total reflects the Clang component, not demonstrated compiler acceleration. No independent timing confirmation follows this result.

## Separate memory measurements

Three alternating instrumented pairs per N=0/1024 use the unchanged F4 policy plus RTS statistics. Their elapsed times are excluded from speed claims.

| N | Metric (bytes) | Before | Candidate |
| ---: | --- | ---: | ---: |
| 0 | Allocated heap | 266,634,880 | 266,004,648 |
| 0 | Maximum live heap | 1,484,136 | 1,529,608 |
| 0 | GC copied bytes | 12,867,360 | 13,249,824 |
| 0 | Peak child RSS | 33,062,912 | 33,046,528 |
| 1024 | Allocated heap | 843,049,352 | 838,374,944 |
| 1024 | Maximum live heap | 9,173,328 | 9,483,280 |
| 1024 | GC copied bytes | 89,908,696 | 92,086,064 |
| 1024 | Peak child RSS | 58,474,496 | 59,654,144 |

At N1024 allocation falls 4,674,408 bytes (0.554%), but sampled maximum live heap rises 309,952 bytes (3.379%) and GC copied bytes rise 2,177,368 bytes (2.422%). The additional dispatch and duplicated miss-handling logic are not justified by an allocation-only saving with no observed compiler acceleration.

## Current acceptance and next work

There is no new formal GHC cohort: the source is unchanged. The preceding seven-size, 32-pair cohort remains authoritative. MLF/GHC N1024 full-build medians are 479.306/703.387 ms; OLS slopes are 0.153700/0.158576 ms per function; finite-range fitted exponents are 0.969100/0.892459. Four of six original gates pass. The paired exponent difference interval [0.001738, 0.180822] is above zero, so exponent acceptance fails. Both fits are interior; no point is dropped, cohort pooled or acceptance condition weakened. Finite-range exponents are not asymptotic Big-O proofs.

Continue inferred_chain. Inspect current CrateGraph.runGroupsWithOwner and Dependency.observeSyntax caller paths for repeated source/dependency traversals after template reuse; do not repeat rejected codec/index/cache/RTS variants or unchanged formal cohorts.

No acceptance commit, push or transition to the next program shape occurs.
