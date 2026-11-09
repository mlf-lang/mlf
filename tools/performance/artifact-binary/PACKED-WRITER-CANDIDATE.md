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
the complete applicable validation against the unchanged reference.

## Separate complete readback observation, 2026-11-09

A new local R10 run exited successfully after 1336.771137865 seconds and
completed independent canonical wire and identity checks for all 8 cold-built
libraries (91 modules), using source
[fd067984](https://github.com/mlf-lang/mlf/commit/fd067984a2ea1e41f687a054ff9db12995b21b28)
and original cold driver `ceb275ea14bd8f8758856f9e83f93d49799ee218`.
The exact packed candidate SHA-256 was
`fa5daa6fd8072825268d2045f1980d0a4bd141e5c79d34f0c90008251860003f`,
identical to the published candidate. The source and golden oracle were unchanged.
Checks covered CURRENT, zero cold-build cache reuse, complete run/campaign
inputs, and final content-drift verification of 38,113 snapshots. The
13,756,701-byte result has SHA-256
`4251ff49e3fa98f4cf4834510c67bd0fc77197b925d58f62a00507cf5c3777c0`.

This is a separate local observation, not CI success or a reclassification of
earlier timeouts or failures. It covers this batch of artifacts, not general
semantic equivalence, performance, native A/B, fixed-point, checked-term, or
independent stderr qualification. No benchmark result is claimed.
