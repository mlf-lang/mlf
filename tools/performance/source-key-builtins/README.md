# Builtin identity in source query keys

A source query caches the checked provisional xMLF object for one value SCC.
Both source drivers hash the running executable and pass that identity into
each key. Datatype validation in inference and in the raw xMLF checker starts
with the ordered `Data.builtinDeclarations` and extends its maps with the user
declarations. The empty environment derives its constructor and datatype maps
from the same list. Source v7 reads the very same value.

## Wire contract

The first of the nine length-framed key fields now represents the exact builtin
declarations. The short literal `MLF-SOURCE-CRATE-QUERY-7` denotes one frozen
ordered list in CrateQuery. Its definition is independent of Data's live
builders. Before selecting it, `sourceFormatFor` checks the entire live list
with SourceEquality.eqDataDecl, including declaration variants, names, binder
kinds, constructor order and recursive field structure. The independently
generated schema-1 dictionary fixture is 9,609 bytes and its SHA-256 is
`8769bc0f30eed0ef497f2b414239f9c8facc1dde749de6dcd7251da1a495224f`.
The runtime uses structural equality. The golden pins the meaning of the
short tag in the regression suite.

A different list automatically takes the escape form, a length-framed pair of
the v7 label and the complete list of literal declarations. The escape starts
with a decimal length and the short tag starts with a letter. Constructor
variants have distinct tags and every ordered child is length framed.
Equal format fields therefore denote equal builtin declarations, even when
two callers use the same compiler identity. The escape can be larger. To give
a future builtin set another short spelling, allocate a new dictionary tag.

The compiler SHA stays in its own field. The user datatype field contains the
original ordered, canonical encodings of exactly the required declarations.
Members and original syntax, dependency types, prepared metadata, observed
contracts and ordered evidence scopes retain their v6 encodings. Shared binary
records retain the format field and compiler identity. Only the user datatype
field is projected into the bounded context carrier. Reconstruction compares
the complete key before raw admission, even on a verified context-window hit.
The existing raw checks, PreparedRaw validation and group finalization still
run on their original paths. The ordinary lowered QUERY-4 key keeps its
previous full datatype encoding.

## Cache transition

V6 and v7 full keys have separate addresses. A v6-only cache incurs a cold
source compile. Existing records remain on disk and identical user context
carriers can be shared. There is no in-place rewrite or cache collection.
An old or foreign record at a current address fails key comparison and the
driver infers that group again. The MLFBIN schemas, raw checksums, file and
graph limits, eight-entry read window, locking and atomic publication are
unchanged. Legacy text record containers still go through their original
checked decoders and must contain the complete expected key to hit. The cache
uses its existing cooperative, trusted-directory model.

## Measurement

[Protocol and fixed order](PROTOCOL.md). Run the following with Python in its
normal assertion-enabled mode. The baseline argument must be a locally fetched
PR head. The two implementations of the source driver are selected in the
study wrapper, leaving one actual executable hash in every key. The wrapper
calls the same CrateSession.compileSpecFile as the emlf compile-crate command.
The before-edit control used the baseline-only options to both scripts.

```sh
python3 tools/performance/source-key-builtins/build-study.py "$pr_head" .mlf-build/key-build
python3 tools/performance/source-key-builtins/run-study.py .mlf-build/key-build/study .mlf-build/key-paired
python3 tools/performance/source-key-builtins/audit-study.py .mlf-build/key-paired
python3 tools/performance/source-key-builtins/test-migration.py .mlf-build/key-build/study .mlf-build/key-migration
python3 tools/performance/source-key-builtins/test-builtin.py .mlf-build/key-mutation
```

## Foundation results

PR #29 head `e60629747bf36e17864918c31a012d37487b2c9c`, base
`c5928b5be73cd78d194405e734aa012415570e1a`. Local Apple M1 Max, 32 GiB,
macOS 26.6.2, GHC 9.14.1. [All samples, executable and artifact hashes](results-20261103.json).

| Stage | Inferred / reused | v6 wall s | v7 wall s | Mean change | Mean peak RSS MiB, v6 / v7 |
| --- | --- | --- | --- | ---: | ---: |
| Cold | 504 / 0 | 36.064, 35.550 | 35.997, 35.667 | +0.07% | 198.15 / 198.20 |
| Warm | 0 / 504 | 24.343, 24.094 | 22.910, 22.074 | −7.13% | 197.85 / 197.92 |
| Edit | 1 / 503 | 24.296, 25.368 | 22.412, 22.139 | −10.30% | 197.92 / 197.98 |

The independently reconstructed UTF-8 keys total **90,257,074 B** for v6
and **30,251,590 B** for v7, a reduction of **60,005,484 B (66.48%)**. The builtin list accounts for
60,004,224 B and shorter decimal field lengths account for 1,260 B. All
504 filenames in each source state match the SHA of their respective complete
key. Reinserting the independently encoded builtin prefix restores the
corresponding v6 user context, with every other semantic field unchanged.
The earlier 91,214,196-byte observation used a different run. Source paths
participate in these keys. Only the two arms of this paired run are compared.

The original and edited states each matched across all 504 raw headers, bodies
and referenced context files. Final artifact bytes also matched directly. The
original interface/object were 313,390 / 1,234,135 B. After the edit they were
313,390 / 1,234,136 B. Both complete cold/warm query directories occupied
32,267,309 B, and both edited directories occupied 32,449,865 B including
the retained old record. Each held 83 binary context files.

| Phase, seconds over all groups | Cold v6 / v7 | Warm v6 / v7 | Edit v6 / v7 |
| --- | ---: | ---: | ---: |
| Demand the strict key | 0.361 / 0.356 | 0.342 / 0.327 | 0.350 / 0.311 |
| Encode and write the forced key | 0.101 / 0.109 | 0.152 / 0.121 | 0.132 / 0.135 |
| Read staged key and compute SHA-256 | 0.064 / 0.035 | 0.094 / 0.049 | 0.082 / 0.049 |
| Read record/context through checked raw admission | 0 / 0 | 11.676 / 10.683 | 12.185 / 10.154 |
| PreparedRaw admission | 0 / 0 | 0.000221 / 0.000194 | 0.000238 / 0.000204 |

The before-edit plain/probe v6 times were 37.744/37.610 s cold, 25.681/26.581 s
warm and 25.900/25.882 s edited. Corresponding query reports, cache files and
formal outputs agreed byte for byte before and after instrumentation. The
combined-executable probes also reproduced their respective plain outputs.

Key forcing can demand lazily prepared inputs. The raw-read interval includes
bounded record/graph decoding, context reads and hashes, reconstruction,
comparison and raw checks. Its timing covers that combined operation.
There is one probe sample per phase and two plain samples per version. These
measure this Foundation source-cache workload. They do not qualify either the
46-module or 80-module native compiler workload.

The [warm-read follow-up](warm/README.md) splits cache acquisition, decoding, key checks, xMLF validation, finalization and output on the same 504-group workload.

## Correctness controls

* The mutation control compiles Data twice at GHC -O0. The second build adds a
  constructor to MLFLegacyUnit in the actual inference environment. The driver
  deliberately passes the same 64-character compiler identity to both. Each
  misses once and hits its own record. Planting the foreign record at the
  current address in either direction triggers reinference and restores the
  original bytes. Both subsequently hit. This exercises the literal escape
  and the short tag with identical source, dependency and user datatype fields.
* The same-binary Session migration control starts v7 on a v6-only cache, then
  places a genuine v6 record and a v7 record for a different literal at the
  correct current filename. Each repairs exactly the affected group, as does
  truncation. The resulting complete artifacts match the original, and the
  repaired record hits. The production emlf CLI also matched the study's
  output on a cold compile and subsequent warm read.
* The authenticated GHC -O2 producer and its 40-command Query/Session suite
  passed, including changed imported type, user layout, observed scope,
  substituted compiler/builtin identity, missing/corrupt contexts, fresh and
  reused context windows, and rejection of a finalized or evidence-poisoned
  object as raw. SourceSCC, QueryEncoding (54 checks), and the binary
  admission and error-priority fixtures passed. The frozen datatype,
  contract and sparse-contract checks expand v6 expectations through the
  exact dictionary prefix before comparing the new keys. Both -O0 and -O2
  passed 5,155 datatype, 2,682 contract and 163 sparse-contract checks each.
  The source registry/provenance tests and benchmark transition also passed.
* The integrated P123 suite stopped in P2 at `empty/write/.mlfco`. Its
  frozen writer emits text and the default writer emits MLFBIN. Rebuilding
  P2 from an archive of the exact PR #29 head reproduced the same error.
  The P3 query fixture ran separately and passed all 929 comparisons.
