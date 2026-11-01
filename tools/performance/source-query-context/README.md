# Source-query shared context

This production slice changes persistence for source-group query caches in
`Bootstrap.CrateQuery` and `Bootstrap.CrateSession`. It is not a migration of
all compiler artifacts, a compression codec, or a claim of universal space or
speed improvements. The offline representation experiments are separate.

## Identity and representation

The semantic `MLF-SOURCE-CRATE-QUERY-6` key remains the complete, canonical
nine-field key, including its pooled scope table. The query filename still
uses the digest of that complete key. No dependency, selection, binding,
annotation, layout, or scope-table field is removed from query identity.

The new record is an exactly four-field `pack` value:

```
["MLF-QUERY-CACHE-3", contextDigest, compactKey, contextualObject]
```

`compactKey` is the canonical eight-field packing obtained by removing only
field 6 (zero-based index 5), the datatype context, from the full source key.
Restoring that field must reconstruct the exact expected nine-field key.
The referenced file, in the same cache directory, is
`context-<contextDigest>.mlfqc`. Its complete two-field contents are:

```
["MLF-SOURCE-QUERY-CONTEXT-1", encodedDatatypeContext]
```

The reference must be exactly 64 lowercase hexadecimal characters. It is a
full file SHA digest, not the shorter object/interface fingerprint.
`contextualObject` uses the existing `Separate` `MLFF-2` representation:
its interface omits the externally supplied datatype header, and its body
omits the repeated datatype-context wrapper. The raw object remains raw;
this does not substitute the finalized object for the cached object.

This reuses existing contextual-object decoding, scope pooling, and the
owned `SourceEncodings` datatype encoding pool. The new feature is persistent
sharing *between query records*, not a second implementation of those pools.

## Reading and semantic checks

A single new-format record read requires its one referenced context file.
The reader checks the reference spelling before constructing the path,
checks the context file's full digest against the reference, and requires
its complete bytes to equal the canonical carrier for the recomputed
expected context. The context encoded in the expected key must also agree
with the datatype arguments supplied by the current compilation.

Canonical compact packing and reconstruction of the complete expected key
are checked before accepting the contextual object. Existing `MLFF-2`
body fingerprint, parsing, canonical encoding, and independent body type
checking remain in force. `validateCached` still validates ownership,
parameters, declarations, schemes, and datatype context. Both source drivers
retain `Source.validatePreparedRaw` before accepting a hit. A matching SHA
alone is not sufficient admission.

A missing context file or readable but malformed/mismatched shared data is a
cache miss rather than a valid hit. Permission failures and other `readFile`
or `fileDigest` I/O exceptions are not caught and converted into cache misses.
The old CACHE-1/CACHE-2 reader remains available. Writers fall back to the
legacy encoder when the key is not the supported canonical source-v6 shape
or when both raw-object contexts do not agree with its context field.
Existing successful legacy hits are not eagerly rewritten: migration is
on new writes, and mixed old/new cache directories are supported.

## Publication and storage accounting

The source drivers retain their existing cache-directory lock. Under that
lock, a writer stages the complete context, computes its digest, and
publishes it before publishing the query record. An existing byte-identical
context is reused without replacing it or changing its modification time;
only the writer's own staging file is removed. A differing context file at
the same digest path is replaced with the verified staged contents before
the new query record is published.

This ordering is not an fsync/durable-transaction guarantee. Crash recovery,
non-cooperating writers, and hostile filesystem races have not acquired new
qualification merely from this format change. The fixed staging filename
relies on the existing cooperative cache lock.

There is no garbage collector in this slice. Crashes or later query changes
may leave unreferenced context blobs; legacy records and temporary files can
also remain. Report both:

* the complete reachable closure: query records plus every distinct context
  they reference, counted once; and
* actual retained directory storage, including old records, orphan contexts,
  temporary files, and allocation overhead.

Do not report only smaller `.mlfq` files as the total storage saving. Nor do
micro-codec timings establish compiler or end-to-end loading performance.

## Frozen source contracts

The `source-query-context` migration layer records exactly the two changed
owners in the existing 128-module registry (126 unchanged), after the
survivors layer. Its source deltas pin complete old/new SHA values and
require unique edits, an exact inverse, and a complete forward round trip.
Historical test-only source projections undo this layer before the older
survivors/C3/context layers. Their frozen manifests and semantic expectations
are not replaced by new expected answers.

A small explicit set of previously admitted complete owner hashes may be
replayed through historical adapters. This is not live-source admission:
the current registry and lock must contain both new owner hashes, and the
live inventory is compared in full. Production runtime code is not replaced
with a projected historical owner.

## Local verification and measured scope

The local production candidate now has these completed checks:

* New authenticated producer: 128 modules, 13 binaries, 18 build commands,
  and builtin generation passed.
* Strict compatibility controls: Patricia 36, A1 34, and validation-reuse 7
  tests, each normally and with Python `-O`: 154 successful checks.
* Revision-2 runtime controls: all 18 invocations passed, including helper
  coverage for CACHE-1/2/3, two poisoned raw/final cases, and both the Query
  driver and public Session path. Cold/warm reuse, one-value changes, missing
  contexts, malformed contexts, and corrupted query-record recovery passed.
* Maintained SourceSCC controls: the original 34 checks plus two literal
  checks, with all 29 expected stdout lines, passed.

Three earlier fixture failures and their evidence are retained: an initial
partial-pattern warning required totalizing the fixture, the runtime helper
used an invalid lowercase group name before correction to `RawGroup`, and
SourceSCC had a stale generic-Set/IntSet fixture interface. These were fixture
corrections, not silent deletion of failed controls or changed production
semantic expectations.

The production changes have not yet been pushed for hosted CI at this
snapshot. These local results are not hosted-CI, native-backend, full-corpus,
concurrency, crash-injection, permission-failure, or performance qualification.
The historical real-cache screen below is qualified separately from the
synthetic source-driver controls.

### Small synthetic storage example

`context-controls-r2/controls/receipt.json` records a two-group Query fixture.
Its self-contained legacy representation was constructed in memory and
semantically round-tripped: the two records total **239,567 UTF-8 bytes**.
The new complete reachable closure is **120,388 bytes**, including the
**119,092-byte shared context**, not merely the two smaller query records.
This is a representation comparison on this fixture, not a physical old-cache
baseline or a general corpus saving.

The new cache's complete retained file contents total **239,785 bytes**:
`query-key.new` alone retains **119,397 bytes** beyond the active closure.
Filesystem allocation overhead is separately reported by the harness. Thus
it would be wrong to describe the reachable-byte reduction as an approximately
50% reduction of the entire directory, or as evidence of faster I/O.

For one value change, both drivers reported exactly one inferred group and
one reused group. Each retained one nonempty unchanged record with its
identity preserved. The observed publication snapshots were:

| Driver | Newly added record bytes | Added/changed file bytes including scratch |
| --- | ---: | ---: |
| Query | 642 | 120,039 |
| Session | 5,771 | 129,123 |

These are snapshot differences, **not total bytes written**: transient staging
creation/deletion and repeated writes are not measured. The old query remains
retained; there is no GC. Read latency, write throughput, and whole-compilation
speedups cannot be inferred from these figures. Further real-population
storage and loading measurements must identify their inputs and count both
the reachable closure and all retained storage.

### Historical real-cache screen

A separate compiled fixture exercised the real production APIs on 12 retained
CACHE-1 records from the historical `14e03173` population, preserving all six
original cache-directory namespaces. Each record underwent one production
write and one new-format read. All 12 produced CACHE-3 (zero fallbacks), passed
canonical interface/object comparison, and reconstructed the original full
legacy wire bytes exactly. This is sample-specific byte round-trip evidence,
not a promise for every possible old object spelling.

The old records total **5,167,282 bytes**, retained unchanged. The complete new
reachable closure is:

| Component | Count | Logical bytes |
| --- | ---: | ---: |
| New query records | 12 | 2,905,711 |
| Shared contexts, counted within their original namespace | 7 | 1,109,437 |
| Complete reachable closure | 19 | 4,015,148 |

Reachable file allocation was **4,055,040 bytes**. All new cache file contents
also total 4,015,148 bytes: the lock files contain zero bytes and no orphan
content was observed. Directory allocation is included in the screen's
separate physical identity accounting, not silently treated as zero in a
whole-directory allocation claim.

This is about **22.30% less representation content** for these selected old
records and their complete new dependencies. It is not a current-corpus,
whole-workspace, or performance result. Because the originals were preserved,
old inputs plus new cache file contents occupy **9,182,430 logical bytes**;
no in-place migration or deletion saved that space during this experiment.

Expected owner, parameters, members, and datatypes for the API calls were
extracted from the old decoded objects. The screen did not reconstruct or
replay `Source.PreparedGroup` from source and does not independently certify
that the historical inputs match present source. Its scope is production
representation admission and round-trip behavior. Evidence is retained in
`real-cache-screen/run/receipt.json`; no timing from this one-shot screen is
presented as a compiler speedup.
