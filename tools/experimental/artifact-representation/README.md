# Offline artifact representation prototype

This is the first, **experimental/offline** step toward smaller compiler
artifacts. It shares exact context and query-key components instead of storing
each expanded value repeatedly. It does not change the compiler's cache format,
invalidate caches, relax a checker, or perform a production migration.

Python 3.10 or newer and its standard library are sufficient. No compiler,
third-party package, compression library, network connection, or private fixture
is needed for the synthetic tests.

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
* Content identities survive insertion, but this baseline writes a full new
  bundle. Cross-build physical sharing, incremental overlays, concurrent writers,
  fsync/crash safety, leases, GC and pack compaction are not implemented here.
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
