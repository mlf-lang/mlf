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

The wire stays at MLFBIN v1, schema 2. New local records have two ordered
roots, the input SHA text followed by the raw query record. The input text is
interned with the corresponding field of the second root. Its payload tag 302 is
`[input SHA, result SHA, raw unit]`. Tag 303 is
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

## Rejecting a misplaced record before graph decoding

The root count in the validated 80-byte header distinguishes the addressed
layout from previous single-root queries. Canonical first-use order puts the
first root at symbol zero. Its length byte is 64, followed by the 64 ASCII
bytes of the input SHA. Both source drivers compare these bytes against the
independently computed cache address before CRC, symbol decoding or node
allocation. The file is acquired once under the existing byte limit. A
normal absent-file miss still uses the initial address lookup.

On a matching prefix the same byte snapshot goes through CRC, canonical graph
validation and checked raw admission. The first root must be the same text as
the input field of the 302/303 payload. The result ICH still covers the input
and raw value using the existing canonical single root 304. A forged prefix
cannot turn a differently addressed payload into a hit. With a damaged body,
a wrong address can now be reported before a CRC failure. A matching address
preserves the full integrity checks and their errors.

Old single-root 302/303 records use their checked reader, including strict ICH
mode. Older exact-key and text records retain their existing migration rules.
Earlier compilers safely reject two-root queries. The extra address root counts
toward expanded work and file size. If it alone would exceed either cap, the
writer tries the single-root fingerprint record under the same limits. Invalid
payloads and publication failures still propagate to the caller. Source keys
stay at v7 and the separately shared datatype context format is unchanged.

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
The addressed layout additionally peeks at the first symbol (at most 65 bytes)
before the combined scan. This does not make a single-pass claim about graph
traversal, the entire disk pipeline or invalid input.

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

## Foundation results

Apple M1 Max, macOS 26.6.2, GHC 9.14.1. The implementation commit was
`86d158adedc33eb4d1c1f29084b720aa6441b7f7`. Each row compares the
arithmetic means of two runs per arm in its own ABBA series. [All samples,
identities and artifact hashes](results.json) include both successful and
unfavorable observations.

| Baseline | State | Wall s, baseline / candidate | Change | CPU s, baseline / candidate | Peak RSS MiB, baseline / candidate |
|---|---|---:|---:|---:|---:|
| PR 32 | Cold | 26.37 / 25.17 | −4.6% | 25.82 / 24.56 | 122.0 / 122.0 |
| PR 32 | Warm | 9.96 / 7.92 | −20.5% | 9.50 / 7.73 | 127.7 / 115.6 |
| PR 32 | Version edit | 9.72 / 7.84 | −19.3% | 9.48 / 7.76 | 117.8 / 125.8 |
| PR 25 | Cold | 26.54 / 25.07 | −5.5% | 25.98 / 24.35 | 177.4 / 125.4 |
| PR 25 | Warm | 10.57 / 7.59 | −28.1% | 9.93 / 7.55 | 177.7 / 116.8 |
| PR 25 | Version edit | 10.30 / 7.77 | −24.5% | 9.98 / 7.68 | 177.6 / 121.9 |

Both pairs won in each end-to-end row. The cold query cache's logical size
was 32,228,073 B on PR 32 and 4,322,919 B on the candidate. After the edit
it was 32,410,629 / 4,342,549 B. PR 25's cold and edited caches in the
separate series were 104,205,148 B and 104,562,014 B. These are fresh
cache measurements; existing unreachable records are not garbage collected.
Every stage had the required inference/reuse counts. Final interface and
object bytes matched PR 32 for both source states. In each candidate run
the independent reader matched all 505 distinct raw headers and bodies,
83 physical datatype contexts and the expected complete-input SHA.

The scan experiment used the same 504 candidate files in both readers. All
2,862,221 symbol-section bytes were eligible. Mean CPU for decoding was
0.8315 s before and 0.7968 s after (−4.2%). Mean wall was 0.8445 / 0.8533 s
(+1.0%); this isolated comparison did not establish a wall-time win. The
end-to-end table includes the change in key representation and the new ICH.
It does not time key construction, pure disk I/O or encoding independently.

In the separate warm audit, the default bucket selected 17 of 504 groups.
Mean wall was 7.876 s sampled and 8.855 s for verifying all 504 (+0.979 s,
+12.4%). All four runs reused every group and reproduced the cold artifacts.

## Reproduction

Use verify-built producer directories and a fresh output directory. The
Foundation argument is the libraries/mlf-foundation directory from PR 25.

```sh
python3 tools/performance/foundation-query/compare.py --baseline-label 32 "$pr32/bin/emlf" "$candidate/bin/emlf" "$foundation" "$study"
python3 tools/performance/source-fingerprints/compare-decode.py "$pr32" "$candidate" "$study/1-candidate" "$wire"
python3 tools/performance/source-fingerprints/verify-cost.py "$candidate/bin/emlf" "$study" "$audit"
python3 tools/performance/foundation-query/check-raw.py "$study/0-32" "$study/1-candidate" "$pr32/bin/emlf" "$candidate/bin/emlf"
python3 tools/shared/test_source_fingerprints.py "$candidate/bin/emlf" "$controls"
```

The CLI control tests a stale, independently typed body of the same name and
type under an edited input, a valid CRC with a wrong ICH, a wrong-address
record, truncation, sampled/full repair and a subsequent warm hit. The GHC
binary corpus includes exact wire round trips and negatives across the
symbol-size and count thresholds, ASCII/Unicode and CRC boundaries. Separate
producer-bound Query/Session controls cover legacy records, scope, dependency
types, datatype layout, raw evidence, resource protection, and scratch/lock
behavior. The builtin control changes actual builtin declarations under a fixed
compiler identity, then varies only the compiler identity.
