# Crate query graph implementation and comparison with PR 29

The publication correction improves cold compilation by **11.4%**, warm compilation
by **36.6%**, and the fixed single-definition edit by **35.7%** against PR 29 in
a fresh paired run. Peak RSS and query storage remain higher than PR 29. See
[`publication-fix.md`](publication-fix.md) for the correction and current results;
full source/build pins and samples are in [`evidence.json`](evidence.json).
The initial implementation's slower cold-build measurements are retained below.

The baseline is exactly `3283899e8ab03af048a674ee41988e454dca813a`.
The candidate adds a persistent per-crate dependency graph, checked open SCC
bodies, shared Binding/Datatype results, ordered Scope dependencies and stable
Evidence results. The source crate CLI publishes the graph only after every SCC
finishes and `.mlfco`, `.mlfci` and `.queries` have been written successfully.
The design and format boundaries are documented in
[`docs/crate-query-graph.md`](../../../docs/crate-query-graph.md).

Normal raw and formal-object loads check encoding, checksums, references and
compatibility; they reuse the existing body-check receipt. Source finalization
still runs, and a changed evidence adapter is checked. `-Zincremental-verify-ich`
rehashes the decoded raw result. `MLF_QUERY_SEMANTIC_AUDIT=1` separately runs the
body checker. A final assembled program is still checked at the linking boundary.
The old prepared-native literal ABI has an explicit closed-object adapter.

Query cache compatibility includes the complete executable SHA and the actual
builtin dictionary. Formal artifacts instead use their shared artifact/checker
ABI and actual builtin dictionary: emlf and its package/library-generation tools
are different executables and must be able to read each other's formal output.
Changes to the checked-artifact rules require a `packageFormat` version change.

The publication correction queues the immutable encoded bytes used for each
result's SHA, allowing the expanded wire trees to be released. Index publication
also reuses its first encoding. Missing results are staged after successful crate
output, then renamed in batches bounded by 64 paths and a 32 KiB argument budget.
Only the final `CURRENT` switch makes the new generation visible. Good existing
results keep their bytes and modification times. The disk format is unchanged.

## Reproduce

Build the pinned baseline and candidate in separate checkouts, using GHC 9.14.1
and the ordinary build driver in each checkout:

```sh
python3 tools/shared/build.py --optimization 2 --bootstrap-only --build-dir .mlf-build/producer
```

The driver uses `-O2 -fpedantic-bottoms -fno-state-hack`, one GHC job, an inferred
interface audit, the shared-source frontend check, and exact builtin regeneration.
The changed builtin literal differs from the baseline only in its generated
nongenerated-source identity; its semantic content is unchanged.

From the candidate checkout, supply the two qualified emlf paths, the candidate
build receipt, and new output directories:

```sh
python3 tools/performance/crate-query-graph/verify.py "$query_candidate" "$query_acceptance"
python3 tools/performance/crate-query-graph/external_checks.py \
  "$query_baseline" "$query_candidate" "$query_external"
python3 tools/performance/crate-query-graph/source_checks.py \
  "$query_candidate_receipt" "$query_source_checks" \
  --interface "${query_external}-relocated/client.mlfci"
env -u MLF_QUERY_PROFILE -u MLF_QUERY_SEMANTIC_AUDIT -u MLF_QUERY_FAILPOINT \
  python3 tools/performance/foundation-query/compare.py \
  "$query_baseline" --baseline-label 29 "$query_candidate" \
  "$query_baseline_checkout/libraries/mlf-foundation" "$query_study"
python3 tools/performance/crate-query-graph/compare_outputs.py \
  "$query_study/0-29" "$query_study/1-candidate"
python3 tools/performance/crate-query-graph/compare_outputs.py \
  "$query_study/3-29" "$query_study/2-candidate"
python3 tools/performance/crate-query-graph/profile.py \
  "$query_candidate" "$query_baseline_checkout/libraries/mlf-foundation" \
  "$query_study/builtin-candidate" "$query_profile"
```

`external_checks.py` moves its complete output directory to `OUTPUT-relocated`
and deletes the query caches before its final load, so success cannot depend on
the original dependency paths or incremental storage. The separate source-test
executable also loads these CLI-produced objects and exercises native-library
admission/literal generation.

## Correctness controls

`verify.py` runs 20 source states through the actual crate CLI. They cover body,
type, protection, datatype field, constructor ownership, evidence insertion,
removal and order, recursive dictionaries, and recursive SCC split/merge changes. Each state compares
incremental and clean raw SHA values and byte-identical final interfaces/objects;
warm, ICH and semantic-audit runs must agree. It independently reads the wire
format, verifies the graph and payload SHA values, and checks dependency closure
and acyclicity. Formal objects are linked with the query cache removed.

Recovery controls cover missing/corrupt raw and shared results, checksum-correct
dangling graph edges, source failure, output failure, five publication failpoints,
resumption from the previous generation, and corrupt formal objects. Warm runs
must preserve every cache file's bytes and modification time. Two concurrent
writers must serialize into one cold and one fully warm compilation.
The publication controls require the actual failpoint diagnostic, and add 96
distinct definitions to interrupt a publication with some result batches moved
and others still staged. The previous graph and every reachable result must
remain readable. The latest full CLI run also uses a directory containing spaces.

One control deliberately forges a checksum-consistent *trusted* raw receipt with
a type-incorrect body. Normal loading and ICH must reuse it, while final program
checking rejects it and explicit semantic audit repairs it. This tests the
separation of checks; it is not a claim of protection against a malicious writer
to the trusted cache directory.

`SourceChecks.hs` exercises the new source-query API directly. It compares final
bodies and complete contracts with the old source driver, checks resulting bodies
independently, and interprets concrete class/evidence results. It also checks
incremental/clean changes, renamed receipts, red/green propagation, dependency
read order, cycles, compiler namespaces, and actual builtin-dictionary identity.
An actual `SSourceDefinition` marker must select the whole lowered fallback;
that route also uses the graph and is checked against the legacy driver and
an independent runtime result. Both CLI branches share the final publication
transaction; the lowered route retains its existing conservative protection.
`external_checks.py` covers old-cache migration without modifying old files,
mixed old/new object formats, cross-crate body reuse/type invalidation, and
relocation without caches.

## Measurement protocol

The unchanged Foundation harness runs **29, candidate, candidate, 29**, with the
same absolute source/spec/cache/builtin paths and the baseline's 14 source modules.
Each arm starts with an empty query cache and a verified installed builtin. Each
stage starts a fresh compiler process. The fixed edit changes only
`Bootstrap.Version.version` from `0.3.0` to `0.3.1`. Required inference/reuse counts
are **504/0**, **0/504**, and **1/503**. OS page caches are not flushed.

Every sample is retained, including CPU, peak RSS and logical cache bytes. The
independent comparison checks 505 raw versions and every final body, type,
datatype environment and interface. Between the old and new formats it ignores
only the format-specific object checksum in the interface, alpha-normalizes
closed types/datatype parameters, and flattens associative xMLF computation
composition. It does not ignore body operations, names, literals or contracts.

The instrumented run is separate from ABBA. Its millisecond clocks distinguish
graph/provider bookkeeping, raw loading/integrity checks, inference/checking,
source finish/evidence/checking, formal output, and graph publication. Frontend,
installed-builtin admission, and other uninstrumented time remain in end-to-end
time. These are candidate-only clocks; the pinned baseline is unmodified.
They are phase totals, not a per-node allocation or heap-retainer profile.

The graph retains old immutable generations/results; no disk GC is implemented.
Report current reachable bytes separately from retained total bytes. Delayed
publication keeps raw payloads alongside finalized objects until commit, so peak
RSS must be assessed alongside speed. Encoded raw/final byte counts do not measure
their individual heap residency.

## Initial measured result: 2026-11-04, before the publication correction

This initial measurement is retained in
[`evidence-before-publication-fix.json`](evidence-before-publication-fix.json).
The later correction's measurements are reported separately below. The original
failure controls could stop on a fixture's blank-line parsing error before the
intended output/publication failure. The corrected controls require diagnostic
and staged-file evidence that those boundaries are actually reached.

GHC 9.14.1, identical O2/demand flags, baseline executable
`e5a5121328468354d406fe8a30795f11874b952b60c2a79f0d835212f695aaea`, candidate
`8ec61c304e4fad361cb69e33ab68cdc109b53db0185933128af8ab27bc19e1eb`.
Both ordinary builds, all 20 CLI states, source changes, actual copied-definition
fallback, cross-executable formal loading and prepared-native compatibility passed.
Both comparison pairs independently matched all 505 raw versions and final
interfaces/bodies/environments. The source controls additionally check executable
runtime results; format equality alone is not their semantic oracle.

Wall/CPU figures below are the arithmetic means of the two samples per arm.
Positive wall change means slower.

| Stage | Inferred/reused | PR 29 wall (s) | Candidate wall (s) | Wall change | PR 29 CPU (s) | Candidate CPU (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Cold | 504/0 | 23.273 | 24.613 | +5.8% | 23.060 | 23.967 |
| Warm | 0/504 | 7.522 | 4.970 | -33.9% | 7.340 | 4.872 |
| Edit | 1/503 | 7.543 | 5.179 | -31.3% | 7.366 | 5.147 |

All wall samples, in execution order:

| Arm | Cold (s) | Warm (s) | Edit (s) |
| --- | ---: | ---: | ---: |
| 0: PR 29 | 23.378 | 7.682 | 7.870 |
| 1: candidate | 25.578 | 5.182 | 5.191 |
| 2: candidate | 23.649 | 4.758 | 5.167 |
| 3: PR 29 | 23.168 | 7.361 | 7.217 |

Cold is slower in both pairs. These two pairs do not establish a general workload
distribution or confidence interval. Earlier exploratory runs preceded the final
formal-compatibility/lowered-route changes and are not included in these means.

| Stage | PR 29 peak RSS samples (MiB) | Candidate peak RSS samples (MiB) | PR 29 retained cache (bytes) | Candidate retained cache (bytes) |
| --- | --- | --- | ---: | ---: |
| Cold | 129.77, 119.47 | 201.80, 203.06 | 4,323,425 | 7,241,088 |
| Warm | 126.38, 126.28 | 162.88, 162.84 | 4,323,425 | 7,241,088 |
| Edit | 122.50, 122.38 | 162.92, 162.95 | 4,343,056 | 8,437,553 |

Cold mean peak RSS rises from 124.62 to 202.43 MiB. The final cold `.mlfco`
shrinks from 1,234,081 to 1,004,044 bytes (**18.6%**); `.mlfci` changes from
313,336 to 313,380 bytes because of its object checksum. The graph and per-result
references outweigh those savings in query storage. Keeping old generations adds
space after an edit, rather than copying all old raw results into new files.

The separate instrumented candidate run reports:

| Stage | Graph/providers (ms) | Raw load/integrity (ms) | Infer/check (ms) | Finish/evidence/check (ms) | Formal output (ms) | Graph publish (ms) | End-to-end (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Cold | 1,371 | 2 | 16,906 | 780 | 553 | 3,010 | 23.448 |
| Warm | 1,564 | 759 | 0 | 777 | 590 | 252 | 4.772 |
| Edit | 1,636 | 793 | 80 | 800 | 581 | 418 | 5.152 |

Warm raw loading runs zero independent body checks. Finish includes checking any
new evidence adapter; it is separate from raw loading. Approximately 0.83 s per
run lies outside these clocks. The baseline has no matching phase instrumentation,
so these numbers do not assign the entire regression to one baseline/candidate
phase difference.

The instrumented graph has 3,403 nodes. Cold/warm reachable storage is 7,241,088
bytes; after the edit it is 7,241,087 bytes, while retained storage is 8,437,553
bytes. Warm cache writes are **zero bytes**, checked by content and mtime. The edit
writes 1,196,612 bytes, including the new whole graph index and changed results;
it does not rewrite every raw payload. Active encoded raw totals 5,632,090 bytes
before the edit, alongside the 1,004,044-byte final object. These encoded sizes
are not heap measurements. The observed cold RSS increase is material; no claim
is made that delayed raw/final coexistence is free or that it alone explains all
of the increase.

Completed raw logs/caches remain under `/tmp/mlf-query-foundation-complete`;
the separate profile is `/tmp/mlf-query-profile-complete`. The initial qualification
and control receipts are pinned in `evidence-before-publication-fix.json`. The CLI control resumed its last
case after correcting a fixture's mistaken source/fallback expectation; completed
cases used the same binary, and the failed attempt is retained. The actual copied
fallback is exercised separately and explicitly asserts that routing decision.
