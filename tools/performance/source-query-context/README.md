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

## Normal-return query-key scratch cleanup

The follow-up cleanup is limited to the fixed `query-key.new` file owned by
these three already-locked entry paths: legacy `CrateQuery.compileGroups`,
`CrateQuery.compileSourceGroupsWithEncoding`, and
`CrateSession.compileSourceGroupsWithEncoding`. Each calls the shared
`cleanupQueryKey` helper before releasing its existing directory lock,
after a normal `Either` return. That includes an ordinary business `Left`
and a successful empty plan. No record, context blob, lock, or unrelated
`.new` file is collected.

The helper rejects a directory at the reserved scratch path rather than
removing it recursively; this also matters for the Windows host's remove
adapter. Otherwise it uses the existing argv-based host command adapter
to remove that exact normalized path. A cleanup failure turns an original
`Right` into `Left`, or appends the cleanup diagnostic to the original
business `Left`; it is not silently reported as success.

This is not a new exception-safe bracket: host I/O exceptions, panic,
cancellation, process termination, and crashes may bypass this normal tail.
It does not clean the separate Codegen scratch lifecycle or implement GC.
It adds one directory check and at most one remove command per invocation,
not per group, and does not eliminate the per-group full-key write/hash
work or measure cumulative I/O.

The lock remains a cooperative POSIX process record lock, not a mutex
between threads in one process. The directory must be trusted; this change
does not defend against non-cooperating replacement races. The POSIX tests
keep the original owner alive while an independent process probes release,
and check one same-cache two-process cold/warm pair. Their readiness marker
is a process-start barrier, not proof that both reached a kernel wait.
They do not establish Windows runtime, crash, hostile-directory, or
same-process-thread qualification.

The additional `query-key-scratch` frozen migration layer pins the complete
two-owner identities and unique forward/inverse edits above the unchanged
`source-query-context` layer. Existing registry, historical projection, and
negative controls remain strict.

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

## Initial production-slice verification and measured scope

The initial production slice had these completed local checks:

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

That initial production slice, including the one-file CI partition-control
repair, subsequently passed hosted CI run 41311660916 at exact PR head
`d6fe38c56fde162506700af40e031534c075e129` (CI 240). This is not hosted
qualification for a later cleanup commit. None of these observations alone
establishs native-backend, full-corpus, crash-injection, permission-failure,
or performance qualification. The historical real-cache screen below is
qualified separately from the synthetic source-driver controls.

### Local cleanup verification

A fresh revision-1 producer passed all 18 maintained build commands,
the 128-module shared profile, implementation identity, and builtin
regeneration. The first cleanup build was retained as a failure because its
new polymorphic helper omitted an explicit `forall` required by the shared
source profile; the revision only added that binder and updated exact
source/lock/migration pins. No qualification check was disabled.

The strict normal/`-O` suites passed **166 checks** (42 Patricia, 34 A1,
and 7 validation-reuse methods in each mode). The real source-context gate
then passed all five compile/link/control commands and **31 child
invocations**: the original 18 plus normal-business-failure, stale empty-plan,
directory-refusal, combined-error, five live-owner independent-lock probes,
and a cooperative two-process pair. All five probes succeeded while their
original owners remained alive waiting for an explicit acknowledgement.
The two cooperative invocations produced one cold 2/0 and one warm 0/2
report and identical final-object bytes.

The cold two-group cache snapshots now retain no `query-key.new`:

| Driver | Active query/context content | All retained file content | Full pathname allocation |
| --- | ---: | ---: | ---: |
| Query | 120,388 B | 120,474 B | 147,456 B |
| Session | 130,655 B | 130,741 B | 155,648 B |

The extra 86 content bytes are three deliberately seeded unrelated scratch
sentinels, preserved unchanged; the zero-byte lock and directory allocation
are included in the physical accounting. All 11 test-cache trees together
were also enumerated, including helper records, old records, and deliberately
rejected directories: 1,347,218 content bytes and 1,613,824 allocated bytes.
Build products and captures are separate evidence, not hidden cache savings.

On a one-value change each driver still inferred one group and reused one.
Only the new record was observed as an added/changed retained file: 642 bytes
for Query and 5,771 bytes for Session. This is **not total I/O**: full-key
scratch writes still occur during the invocation before cleanup. Old query
records remain; in the mixed-legacy Query control the retained old record
alone is 119,777 bytes. No orphan or legacy-record GC is claimed.

These are local Linux/GHC-host qualification results. The cleanup commit
requires its own hosted CI, and the larger controlled workload and reading
measurements are separate from these small controls.

### Historical two-group storage example (before scratch cleanup)

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

