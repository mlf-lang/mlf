# Source query fingerprints

The input identity is SHA-256 of the exact UTF-8 serialization of the full
canonical v7 inference key. Both source SCC drivers already compute this SHA
under the cache lock for the .mlfq address. The new records compare their
stored fingerprint with that independently computed value. The full syntax,
observed dependency types and contracts, ordered evidence scopes, compiler
identity and datatype/builtin dictionary or literal escape still enter that
serialization. The lookup still constructs and hashes the complete input.

The local cache assumes a trusted directory and cooperating writers. Distinct
canonical inputs with a genuine SHA-256 collision can compare equal. A
fingerprint or CRC does not attest to the producer of an externally supplied
record. Use a fresh private cache for untrusted input caches.

## Format and checks

The wire stays at MLFBIN v1, schema 2. Root 302 is
`[input SHA, result SHA, raw unit]`. Root 303 is
`[context SHA, input SHA, result SHA, contextual header, body]`. Each SHA is
64 lowercase hexadecimal characters. The format discriminators are separate
from old exact-key roots 300/301. The source **key material version** stays at
v7 so existing producers' input descriptions can be independently replayed.
Old compilers reject the new roots. Current compilers on their default path
can use an old, matching record only through its original full-key and object
checks. A compiler executable change changes the input and normally produces a
cold miss. Unknown or damaged records miss and are replaced through the normal
atomic writer after successful inference.

On publication the result SHA covers a domain-separated canonical MLFBIN
encoding (schema 2, root 304) of the expected input SHA and the raw value.
For a shared result its fields are the context SHA, contextual interface and
body. For an inline result the field is the complete raw unit. On verification
the reader re-encodes the **admitted object** under the same bounds and compares
the SHA with the stored result. This checks the decoded value, not just the
integrity of the on-disk byte buffer. A mismatch discards the record and
reinfers the group. The resource/graph gates, wire CRC, actual datatype
carrier checks, metadata and term checksums, xMLF checker and PreparedRaw
checks still apply to every hit.

`emlf -Zincremental-verify-ich --compile-crate SPEC -o PREFIX` rechecks all
loaded **source SCC** values. Source records without a result fingerprint are
recomputed and upgraded in this mode. Default sampling is reproducible: an
input whose SHA starts with 00 through 07 is selected (1/32 under uniform
hashing). An unchanged input stays in the same bucket on later runs. The
option is outside the key, so switching it on audits the existing cache.
A genuinely colliding input SHA can still reuse the old result under full
verification when that value rehashes to its stored ICH.
Context blobs, formal interface/object files and lowered-only QUERY4 have
their own checks.

## End-to-end protocol (fixed before measurement)

Compare PR #32 at 84f60997350ee0e0de46d13e2efb17de78248a57 to the
candidate, using GHC 9.14.1 with the same producer build flags (-O2,
-fpedantic-bottoms, -fno-state-hack). PR #29 is c0fffea2b4175797157ed81676d349541724a0b2,
based on c5928b5be73cd78d194405e734aa012415570e1a. The Foundation inputs
are the 14 modules at the PR #25 head. Use foundation-query/compare.py
--baseline-label 32, fixed order baseline, candidate, candidate, baseline.
Each arm gets a separately seeded verified Prelude, same absolute source
paths and a new query cache. Time an ordinary cold build, warm read, and the
single Version edit. Retain every observation, require 504/0, 0/504 and 1/503
inferred/reused, and compare final bytes. Additionally compare all raw bodies
and headers, rebuild the candidate input SHA from the old full fields with
only the compiler identity changed, compare carrier bytes, and independently
compute each candidate result SHA. Record wall, CPU, RSS and logical cache
bytes. Report a speed win only when both matched pairs win and the mean is
at least 2% lower. Run the full-verify audit separately, outside this
default-policy series. This workload does not measure the native module gate.

## Combining scans

For a valid bounded symbol section the MLFBIN reader consumes each length and
UTF-8 byte once, accumulating CRC32, validating scalar encoding and interning
the decoded strings. It continues CRC over node/root bytes (including padding)
and admits node tables only after CRC matches. This fast path allows at most
64 KiB of symbol data and 1,024 symbols before the CRC gate. Files smaller than
1 KiB, files with supplied text hints, larger sections and declined parses use
the original checksum-first path. Corruption keeps its old diagnostic priority.
This does not make a single-pass claim about graph traversal, the entire disk
pipeline or invalid input.

The isolated scan comparison uses the same 504 physical Foundation records
from one candidate cold sequence, both GHC producer builds, with bytes loaded
before the timer. Time CRC, symbol decoding and bounded/validated graph
construction through forcing its root. Run fresh processes in fixed order
baseline, candidate, candidate, baseline twice. Report every wall and CPU time;
do not infer whole-compile speed from this narrower interval.

For comparison to the earlier user-facing target, run a separate 25,
candidate, candidate, 25 series after the PR 32 study, with the same
compare.py protocol and the same 14 source files. Use a fresh directory so
both arms in that series see identical paths and cache state. Apply the same
two-pair, 2% rule. PR 25 has an older artifact ABI. Compare the outcomes in
each pair and validate outputs within each ABI; the full cross-version raw
byte comparison is for PR 32 versus the candidate. For full-verify cost
replay the warm PR 32 study's candidate snapshot afresh in fixed order
sample, full, full, sample.
