# Offline artifact representation prototype

This is the first, **experimental/offline** step toward smaller compiler
artifacts. It shares exact context and query-key components instead of storing
each expanded value repeatedly. It does not change the compiler's cache format,
invalidate caches, relax a checker, or perform a production migration.

Python 3.10 or newer and its standard library are sufficient. No compiler,
third-party package, compression library, network connection, or private fixture
is needed for the synthetic tests.

The current implementation and allocation accounting are qualified on the tested
POSIX/Linux environment. Allocation reports use `stat.st_blocks`, which is not
portable to every Python platform. Windows execution and allocation accounting
are not qualified: standard-library-only does not imply demonstrated Windows
support. Logical file bytes and allocated filesystem bytes are separate metrics.

## Run the controls

Choose a new output directory whose parent exists; the command deliberately
refuses to reuse an existing directory. All generated fixtures remain there.

```sh
python3 -I -B tools/experimental/artifact-representation/test_representation.py \
  --output-dir "$PWD/tmp/artifact-representation-tests-new"
```

The suite contains 41 codec controls and nine small sequential CLI controls.
The CLI controls invoke the same Python interpreter with `-I -B` and a ten-second
per-command timeout. Python `-O` is explicitly refused for the test entrypoint:
an assertion-free test run must not be reported as a pass. Codec validation uses
explicit checks, not assertions.

All 41 codec controls and nine CLI controls passed in the isolated local
qualification recorded in `VALIDATION.json`. This is separate from the historical
artifact measurement below; neither result is a compiler semantic-checker run.

## Try existing query files

The input must be canonical writer output using `MLF-QUERY-CACHE-1`,
`MLF-SOURCE-CRATE-QUERY-6`, `MLFI-4`, and `MLFO-1`. The files are read-only inputs;
the output is a **new offline bundle**, not a replacement compiler cache.

```sh
python3 -I -B tools/experimental/artifact-representation/cli.py pack \
  --output-dir ./new-component-bundle input-a.mlfq input-b.mlfq

python3 -I -B tools/experimental/artifact-representation/cli.py verify \
  ./new-component-bundle

python3 -I -B tools/experimental/artifact-representation/cli.py restore \
  ./new-component-bundle input-a.mlfq --output-file ./restored-a.mlfq
```

`pack --whole-fields` provides the simpler whole-field-sharing baseline.
`restore --stdout` emits only the original bytes. Output files and bundles must
not already exist. Duplicate input basenames and symlink-traversing inputs are
refused. The small-corpus CLI admits at most 64 records and 16 MiB of total input;
the codec reserves at most 12 MiB of bundle writes per process. These bounds are
intentional prototype limits, not proposed production size limits.

`pack` reopens its output and compares each restored record with the original
bytes. `verify` checks every record's original length/SHA and the complete
reachable storage. Neither command runs the MLF semantic checker.

## What is shared

All nine key fields, all eight interface fields, and all four raw-object fields
remain present in the representation. The component strategy additionally splits
the known member, binding, datatype-declaration, source-contract and evidence-scope
lists into exact text components. It does not infer AST equivalence, rename
symbols, discard contracts, or merge binders from different scopes.

The actual metadata context can be shared with the term prefix only after an
exact prefix comparison. A mismatching context rejects migration; it is never
silently repaired. `RAW_BODY` and `RAW_OBJECT` are distinct node kinds. There is
no conversion to final fragments and no assumption that raw and final bodies
are identical. This is not another implementation of the existing `MLFCO-2`
datatype pool.

## Experimental wire format

Each bundle has exactly three data files:

* `objects.pack`: unique node payloads, ordered by content identity.
* `objects.index`: eight-byte `MLFREP1\0` magic, little-endian 32-bit node count,
  then 65-byte `<32sQQQQB` rows: identity, byte offset, stored byte count, decoded
  UTF-8 byte count, Unicode scalar count, and node kind.
* `manifest.json`: explicit storage version and raw-only semantic scope,
  pack/index hashes, and named roots with original byte lengths and SHA-256s.

Node kinds are `TEXT`, `FRAME`, `CONCAT`, `RAW_BODY`, `RAW_OBJECT`, and `QUERY`.
Text payloads contain exact UTF-8 bytes. Reference payloads contain a
little-endian 32-bit count followed by 32-byte child identities. `FRAME`,
`RAW_OBJECT` and `QUERY` restore scalar-length-prefixed legacy fields; `CONCAT`
restores the exact context followed by its raw body.

Identity is SHA-256 over a versioned domain, node kind, and payload. This is a
**storage representation identity**, not a new compiler ABI or query-key hash.
Different strategies may have different node roots while retaining the same
`legacy_sha256`. A hash provides integrity, not provenance authentication or a
proof that a program is well typed.

The reader rejects unknown versions/kinds, bad hashes or offsets, dangling
references, invalid expansion lengths, excessive depth/size, and inappropriate
raw-node structure. Complete-bundle accounting rejects unreachable nodes rather
than hiding them from the reported size. Index entries, references, the manifest,
and all payloads count toward the total; there is no external dictionary.

Old framing counts Unicode scalars, not UTF-8 bytes. Non-BMP characters,
combining characters and NUL are preserved without normalization. The prototype
accepts only canonical decimal lengths; leading-zero lengths are explicitly
unsupported rather than silently rewritten. Source-level numeric encodings,
float-bit tokens, annotations, signatures and evidence remain opaque exact bytes.

## Initial measurement, not a performance claim

A fixed historical sample of 12 complete query files included six worker-median
files and six non-ASCII files. It contained 5,167,282 bytes. Both strategies
round-tripped every input byte-for-byte, and the original 41 codec controls passed.

| Representation | Pack | Index | Manifest | Complete reachable bytes | Reduction |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original files | — | — | — | 5,167,282 | — |
| Whole fields | 3,516,527 | 12,167 | 3,454 | 3,532,148 | 31.64% |
| List components | 2,146,709 | 31,862 | 3,457 | 2,182,028 | 57.77% |

No compression was used. The sample's 956 datatype-declaration references used
116 unique components; 448 predecessor-binding references used 79 components,
and 560 source-contract references used 79. All 12 raw bodies remained separate.
See `RESULTS.json` for sample input hashes and the exact reference-code identity.
The generated multi-megabyte artifacts are intentionally not committed.

These are small historical-sample results, not estimates for the entire compiler
corpus or executions of the current PR head. The corpus came from `14e03173`;
schema inspection at `7bf7ac6d` supported the format bridge, not a rerun. The
historical fixtures are not required by the self-contained synthetic tests.

## Explicit limits and next steps

* This is not the MLF parser/checker. Restored data must still pass all existing
  key, ownership, context, layout, fingerprint and independent-checker checks.
* The implementation initializes by hashing the whole pack and validating all
  nodes, then restores complete records. An index does **not** mean this version
  has proven lazy-load, compiler-time, cold-cache, or RSS improvements.
* Content identities survive insertion, but the original `Builder.write` still
  writes a full new bundle. The explicit one-level overlay experiment below adds
  base-plus-delta sharing; it does not silently change that baseline API.
  Concurrent writers, fsync/crash safety, leases, GC and in-place pack compaction
  remain unimplemented.
* Publishing the manifest last gives an offline incomplete-write boundary, not a
  production transaction protocol. Concurrent hostile filesystem mutation and
  authenticity are outside this prototype's guarantees.
* Tiny graph-cycle/expansion controls use adversarial in-memory node providers;
  they do not claim to forge SHA-256 cyclic files.
* A production path needs an independent MLF encoding/decoding oracle, larger
  fixed reachable closures, compatible byte IO or textual references, and
  separate semantic, incremental-lifecycle and load-performance qualification.

The immediate deliverable is a reviewable reference representation and test
suite. No production artifacts should be rewritten with it.

## One-level incremental storage and read diagnostics

`overlay.py` adds an explicit, immutable **base + delta + new manifest** operation.
Its version is distinct from the self-contained baseline version. The caller
supplies the base directory; manifests cannot choose arbitrary paths or create
recursive base chains. A new manifest embeds the base pack/index identities and
the complete new set of roots. Duplicate identities across layers, missing or
incorrect bases, and dangling cross-layer references reject.

The fresh overlay reader requires exactly five files: the base pack/index and
the delta pack/index/manifest. Its audited reads do not use the old base manifest
or a preloaded baseline reader. Preserving access to both old and new snapshots
additionally retains the original manifest. Complete physical-closure accounting
counts the **entire** immutable base files, including nodes no longer reachable
from the current snapshot.

### Small, self-contained controls

```sh
python3 -I -B tools/experimental/artifact-representation/test_overlay.py \
  --output-dir "$PWD/tmp/artifact-overlay-tests-new"
```

These controls create only two small synthetic base records. They check fresh
overlay dependencies, exact old/new/rewritten snapshots, physical accounting and
six negative overlay boundaries. Wrapper controls exercise only `measure.py
--help` and rejection of an unpinned base. They **do not rerun** the historical
twenty-observation read experiment. Like the original suite, the entrypoint
refuses Python `-O` and existing output directories.

All **25 controls passed** in a separate isolated local qualification; see
`OVERLAY-VALIDATION.json` for source identities, boundaries and the bounded-run
receipt digest. This qualification did not repeat the historical measurements.

### Fixed historical update result

The measured experiment changes only one record's key field `[2]` to another
deterministic compiler-identity string. This is a **synthetic single-record
storage/identity exercise**, not a real compiler upgrade. In production, changing
compiler identity may invalidate every query. The synthetic modified record is
not claimed to have passed the MLF semantic checker.

The one changed record introduced three nodes and reused 188. All eleven other
records stayed exact; the old snapshot, updated snapshot, and independently
written compact snapshot each restored all twelve records byte-for-byte. Six
negative controls and all twenty diagnostic read observations passed.

| Quantity | Logical file bytes |
| --- | ---: |
| New delta pack + index + manifest | **4,330** |
| Full rewrite of the updated snapshot | **2,182,157** |
| Current overlay snapshot's complete physical file closure | **2,182,901** |
| Both old and new snapshots pinned | **2,186,358** |

The delta comprises 488 payload bytes, 207 index bytes and a 3,635-byte manifest.
It creates about **99.80% fewer logical file bytes than this full-rewrite
control**. This does not mean the complete snapshot occupies 4,330 bytes, nor
does it measure filesystem journal traffic, durable writes, or a real compiler's
incremental workload.

Two old nodes become unreachable from the new roots: 424 payload bytes and 130
index-entry bytes remain in the immutable base. Those are **not reclaimed disk
space**. The separate full-rewrite control contains only current reachable nodes;
no original pack was modified, compacted in place, or deleted.

### Read behavior and remaining bottleneck

Five fixed interleaved observations were made for each layout/read mode. No OS
cache flush or compiler execution occurred. Initialization includes hashing each
whole pack and then checking every node, so it reads the payload roughly twice:

| Layout / mode | Initialization logical reads | Restoration logical reads |
| --- | ---: | ---: |
| Baseline / one fixed record | 4,328,737 B | 367,800 B |
| Baseline / all twelve | 4,328,737 B | 4,967,953 B |
| Overlay / one fixed record | 4,330,098 B | 367,800 B |
| Overlay / all twelve | 4,330,098 B | 4,967,953 B |

These counters are actual bytes returned to Python, **not physical disk IO**.
The index allows node seeks, but the current constructor still pays the full-pack
integrity cost even for a single requested record. Reducing that repeated work
requires a separate validated-loading design, not merely claiming random access.

Observed baseline medians were about 21.09 ms total for one record and 90.30 ms
for all records; overlay medians were about 25.26 ms and 85.05 ms. The mixed
direction and small run do **not** establish a speed improvement or regression.
Initialization/restoration samples and ranges are retained separately in
`READ-UPDATE-RESULTS.json`; this is neither cold/warm-cache qualification nor a
compiler performance result.

### Reproduction wrapper

`read_update_experiment.py` preserves the measured experiment implementation.
`measure.py` is an opt-in wrapper that accepts only the exact three baseline
file hashes recorded in `READ-UPDATE-RESULTS.json` and verifies the implementation
hashes. The multi-megabyte baseline is not committed.

```sh
python3 -I -B tools/experimental/artifact-representation/measure.py \
  --base-dir /path/to/the-exact-component-lists-bundle \
  --output-dir ./new-read-update-experiment --run-fixed-experiment
```

The published historical measurement was executed once through a separately
resource-guarded driver. The new wrapper is not evidence of a second performance
run; only its help/error behavior is covered by the tiny portable controls.
Running the opt-in command requires an appropriately bounded, coordinated
environment and creates new diagnostic artifacts; it never updates a compiler
cache in place.
