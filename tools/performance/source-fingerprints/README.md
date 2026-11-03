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

The wire stays at MLFBIN v1, schema 2. Local source records have two ordered
roots, the input SHA text followed by the raw query record. The same input
text occurs in the second root. Each SHA has 64 lowercase hexadecimal digits.

| Tag | Fields of the payload root | Result fingerprint |
|---|---|---|
| 302 | input SHA, result SHA, raw unit | canonical root 304 |
| 303 | context SHA, input SHA, result SHA, contextual header, body | canonical root 304 |
| 305 | input SHA, result SHA, raw unit | template of this addressed record |
| 306 | input SHA, result SHA, context SHA, contextual header, body | template of this addressed record |

The ordinary compiler writes 305/306. To hash the result, it encodes both
roots with 64 ASCII tildes in place of the result SHA. The SHA-256 covers the
complete canonical template, including its CRC and the input SHA. In these
layouts the result is symbol 1. Before patching the 64 bytes in the private
buffer, the writer proves the structural text node has a single incoming
edge from the result field and the new digest differs from every symbol.
It then computes the CRC over the finished bytes. This produces exactly the
bytes of an ordinary canonical encoding with the actual digest. If the
reserved spelling appears in the user's term, a digest equals another symbol,
or the template exceeds a limit, the writer uses the independently encoded
302/303 layout and its existing limit fallback.

The key material stays at v7. A compiler executable change changes the input
and normally causes a cold miss. Older compilers reject the new tags. Current
compilers retain the original checks for matching 300/301 full-key records and
302/303 records, including the original single-root representation. A 305/306
record must have the separate address root. An unsupported tag or damaged
record misses and is replaced after successful inference.

For 302/303 the SHA covers the bounded canonical root 304 with the expected
input and raw value. For 305/306 it covers the template described above. On verification
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
the input field in the payload. The 302/303 result ICH uses canonical root
304. For 305/306 the reader independently reconstructs the addressed template
from the admitted raw value when verifying the ICH. A forged prefix
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

## Addressed record experiment on PR 29

The baseline was `6927bfacedd141d7182cc53f5e7a99f1cd3c9411` and the implementation
was `000356d37e083bd7cad1443cadb1564bb6cd6363`. On the same 14 Foundation
modules, the ordinary CLI ran in fixed order 29, candidate, candidate, 29. Each
sequence used the same source paths and a fresh cache with a verified Prelude.
A separate experiment loaded all 504 physical candidate records before timing.
Both modes ran in one optimized GHC executable and validated the same payload
SHA on success. For the mismatch case each record was queried under the next
record's SHA. The order was full, early, early, full, twice per case.

| 504 preloaded records | Full decoder, wall / CPU s | Address gate, wall / CPU s |
|---|---:|---:|
| Matching address | 0.789 / 0.786 | 0.791 / 0.788 |
| Wrong address | 0.784 / 0.782 | 0.00309 / 0.00308 |

| Ordinary CLI | Wall s, base / candidate | CPU s, base / candidate | Peak RSS MiB, base / candidate |
|---|---:|---:|---:|
| Cold | 23.79 / 24.06 | 23.60 / 23.87 | 117.7 / 119.6 |
| Warm | 7.43 / 7.65 | 7.36 / 7.54 | 116.4 / 118.4 |
| Version edit | 7.45 / 7.72 | 7.40 / 7.62 | 121.5 / 122.6 |

The addressed reader avoided 99.6% of the wire time for these deliberately
misplaced records. In this end-to-end series the normal cold, warm and edited
compiles took 1.1%, 3.0% and 3.6% longer. The gate costs about 0.0024 s across
504 correct addresses in the isolated comparison. The ordinary timings include
all compilation stages and each compiler's selected ICH bucket.

Cold cache size was 4,322,919 / 4,323,425 B and after the edit it was
4,342,549 / 4,343,056 B. Inferred/reused counts were 504/0, 0/504 and 1/503.
Both matched pairs agreed on every final interface/object byte and on the
505 distinct raw headers/bodies and 83 physical datatype contexts. Every
candidate record in the experiment had the two-root layout. [All samples,
compiler identities and workload checks](early-address-results.json).

```sh
python3 tools/performance/foundation-query/compare.py --baseline-label 29 "$pr29/bin/emlf" "$candidate/bin/emlf" "$foundation" "$study"
python3 tools/performance/source-fingerprints/compare-decode.py --addresses "$candidate" "$candidate" "$study/1-candidate" "$wire"
```

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
