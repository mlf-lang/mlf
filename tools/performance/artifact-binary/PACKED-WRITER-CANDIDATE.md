# Experimental packed reference writer

`packed_writer_candidate.py` is an opt-in, standalone candidate for the
fixture writer in `tools/shared/artifact_binary_reference.py`. Only `Writer`
differs. The reader, bounds, schema checks, canonical rules and CRC checks
remain identical. The repository reference is unchanged and is the independent
comparison oracle; no reference module is monkeypatched. Nothing selects this
candidate automatically.

The candidate packs least-significant-bit-first writes into a bytearray.
Explicit `.bits` access materializes the original mutable list interface and
permanently falls back to list behavior, including alias mutation and assignment.
`bytes()` returns an immutable snapshot and does not prevent subsequent writes.

Run the tiny, stdlib-only differential controls from the repository root:

```sh
python3 -B tools/performance/artifact-binary/test_packed_writer_candidate.py
python3 -B -O tools/performance/artifact-binary/test_packed_writer_candidate.py
```

The 13 controls pin both implementations and compare bit offsets, boundary
values, zero-width writes, varuints, invalid ranges and retained state, list
compatibility, all fixture kinds, DAGs, malformed documents, parser mutations,
and an independent aggregate-integer oracle. Non-writer source and reader
limits must remain identical. The pinned reference deliberately requires review
if the underlying reference changes.

These are focused synthetic controls, not a compiler test, a complete cold
readback, a native qualification, or a performance claim. Before adopting this
candidate in any validation path, independently review the integration and run
the complete applicable validation against the unchanged reference. No benchmark
or native validation result is attached to this tools-only change.
