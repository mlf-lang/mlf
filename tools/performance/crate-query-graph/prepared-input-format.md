# Structural prepared query inputs (candidate)

The prepared SCC input currently flattens original and lowered members into two
text symbols. A candidate repair retains the existing `SourceKey` framing tree
and pools exact ordered evidence candidate scopes. This is not a blanket
atomization: annotation, pattern, type and metadata sub-encodings remain bounded
text atoms. The actual offending package-core SCC and field must be measured
before this candidate can be called a repair for that failure.

The input-only schema is `421 [429 [427 fields, 427 scopeTable]]`. A text atom
is `VText`; a framed field list is `427 children`; a scope reference is
`428 [VInt zeroBasedIndex]`. The table is sorted with the existing exact scope
comparator. Each row is the framed list of legacy candidate encodings. Fields
are original canonical members, lowered canonical members, and unchanged
prepared metadata, in that order. Order, duplicates, evidence roles, source
provenance, annotations and numeric bit patterns remain part of the input.
The independent decoder reconstructs old framed syntax and compares it with the
retained legacy text encoders.

The graph configuration adds `prepared-source-tree-1`, deliberately invalidating
old prepared-input hashes. This is not a claim that old and new wire hashes are
equal. `sourceQueryFormat`, source query text keys, checked-object schemas and
legacy readers remain unchanged. The existing transaction protocol remains:
an incompatible generation starts cold, and CURRENT changes only after
successful publication. All existing codec resource limits remain unchanged.

`PreparedInputChecks.hs` is included by the existing receipt-backed
`source_checks.py` gate. It includes syntax projection, binary roundtrip,
isolated semantic mutations, alpha-renaming, UTF-8 boundaries, oversized atom,
depth/work limits, and old/new configuration migration with failed replacement.
Existing graph, source, lowered, semantic-audit and publication controls remain
required. The fixture's existence does not mean it has passed.

## Diagnostic and recovery status

`prepared-input-diagnostic.patch` applies only to unmodified
`98540496cd5e94d2de87894486acdc9bb945fdac`. Build it as a separately identified
diagnostic overlay after preserving a normal baseline producer. It adds exact
SCC names and original/lowered/metadata UTF-8 byte counts only when the prepared
input provider fails. It does not raise codec limits. The 256 MiB byte counter
is diagnostic only; if that counter cannot represent a field, its error is
reported rather than an invented exact size. A failure outside this provider
will not gain this label and needs further localization.

The 2026-11-07 working environment was replaced before the dependency campaign
reached package-core. The retained conversation records a normal baseline O2
producer pass, foundation and language-core passes, and frontend still running
at the last observation. The original local receipts and binaries are absent.
No package-core field diagnostic or candidate compiler test completed in that
attempt. This reconstructed candidate contains no recreated success receipt.
Fresh ordinary producer builds, precise failure localization, cold/warm
package-core compilation and aggregate qualification are still required.

## Fresh failure reproduction after recovery

A fresh ordinary GHC 9.14.1 O2 producer at clean commit
`98540496cd5e94d2de87894486acdc9bb945fdac` passed its 135-module source and
builtin checks. Its seven dependency crates passed; `mlf-crates` took
1235.089 seconds. The subsequent package-core invocation failed after 51.313
seconds with exactly `binary symbol byte limit exceeded`, exit 1, no watchdog
resource-stop reason, and unchanged recorded inputs. This is a source failure,
not a successful package qualification.

A separately built, explicitly diagnostic producer then replayed the original
baseline spec's module, dependency and builtin fields unchanged, changing only
the query directory and CLI output prefix. Its log was:

    Prepared input SCC 225:Package.Command.run: binary symbol byte limit exceeded; original UTF-8 bytes=1258025; members UTF-8 bytes=18587643; metadata field UTF-8 bytes=4:31463:2602:305:35011

The offending field is the lowered `members` serialization: 18,587,643 UTF-8
bytes against the unchanged 16,777,216 single-symbol bound. Original syntax is
1,258,025 bytes; the four metadata atoms are 3,146, 260, 30 and 35,011 bytes.
The CLI applies `Modules.displayNames` to errors; `225:Package.Command.run` is
quoted verbatim rather than reverse-engineered as an internal packed name.
A prior diagnostic with relocated source paths had a different original-field
size, so it is not used for this exact-size claim.

The exact-source diagnostic exited 1 after 53.126 seconds, peak process-tree RSS
617,070,592 bytes, with no resource-stop reason and unchanged recorded inputs.
Original baseline failure receipt SHA256:
`65edfa247845d080cd70fc756476e42f86cc2c1e27bf5c61c3a64dce4888681c`.
Exact-source diagnostic receipt SHA256:
`c9729d21f7072eb00cfab36ce9d2ba7ffebf8b8e7fd089a198c1ac5d791d6b39`.
Exact-source diagnostic log SHA256:
`d9ed0c5671ab8d9d859f4a00bd5cbc5b6f63bfbd32978949f02b60da24cb81df`.
These observations localize the failure. They do not show that the candidate
passes, establish that repeated scopes are the sole contributor, or replace
fresh candidate dependency, cold/warm, recovery, native or bootstrap checks.

## Candidate focused validation

The recovered candidate's ordinary O2 producer and exact builtin verification
passed, and it was authenticated again after all focused commands. Three fresh
(non-resume) guarded commands passed:

- `source_checks.py`: 25.016 seconds, including the new prepared-input oracle,
  mutation/resource controls and migration case, plus existing source changes,
  lowered fallback, independent runtime/legacy comparisons and actual
  CrateSession failure/retry, lock release and publication retention.
- `verify.py`: 136.634 seconds, retaining the full query-graph fingerprint,
  cold/warm, ICH, semantic-audit, corruption, publication-failpoint and concurrent
  writer acceptance assertions.
- `test_source_context_cache.py --legacy-query-only`: 19.003 seconds, the
  maintained CI retained-legacy context/codec gate. The older paired
  `external_checks.py` requires its historical PR29 producer; the current
  baseline was not substituted for that producer.

Every command exited zero with no watchdog resource-stop reason. Producer
receipt SHA256: `cd26eabd8b86e5be6512993de958ca989cfba2d6694fbd0fa302b4f985c1f688`.
Source-control receipt SHA256:
`5e41954e9b5956ac6fa13599e359ac86d17dcb16e29ab2bcc0468565b35a069a`.
Graph guard receipt SHA256:
`0a1a6e692795ba554f11d3d0170da59e4cb602c75d4341283cc20ebaa61d6614`.
Legacy-control receipt SHA256:
`79b54af637f013f7d7aa29f6b755979a16c0c2a8b9948b203278a7c1a1c796de`.

These focused passes are not a completed package-core repair qualification.
A fresh full candidate dependency chain and actual package-core cold/warm runs
with identical final artifacts and verified reuse counts remain required.

## Fresh full candidate cold chain

The ordinary candidate producer compiled all eight manifest-derived library
crates into fresh artifact and query directories, without borrowing baseline
outputs. The maintained manager's actual offline plan was compared against all
88 source modules, hashes, crate identities and dependency ordering first.
This was not a native `--locked` workflow qualification.

All eight guarded commands exited zero, with no resource-stop reason, followed
by successful producer authentication and unchanged recorded inputs. The cold
inferred-group counts were foundation 504, language-core 74, frontend 634,
xmlf 173, inference 730, llvm 538, crates 1741 and package-core 343. Every report
had zero reused groups and every group had `cached=false`.

The crates stage took 1274.897 seconds with peak RSS 1,245,065,216 bytes.
Package-core took 58.954 seconds with peak RSS 507,179,008 bytes, within the
unchanged 900-second, 2-GiB RSS and 4-GiB address-space bounds. Campaign receipt
SHA256: `97c0f60d5b268547c67c03a40ee6d617f0f0773326feac8e3c061950da01997d`.
Package-core guard receipt SHA256:
`a2d642805488983fe2aef4ff5d3b569232292adc6593bf8a60b56b8a45110dc9`.
Cold interface SHA256:
`93f6728bab2e73330a5e1f792c55a39a2a6172b0e912e5e1b4177017f1fd7e66`.
Cold object SHA256:
`bb7a40f7b9c4b30bafe32c6ce839c33bf691b8a86a45c4939f272d5bc980b5e4`.

This confirms the repaired full cold source chain, not the remaining warm,
actual package recovery, native, bootstrap, async or aggregate merge gates.

## Actual package-core warm replay

A single warm invocation used the same authenticated ordinary O2 producer,
unchanged cold package-core spec and query directory, and a fresh artifact
prefix. The watchdog covered the entire campaign tree, including the reused
cache, under the unchanged 900-second / 2-GiB RSS / 4-GiB address-space /
256-MiB output limits. It passed in 23.450 seconds with peak RSS 321,335,296
bytes and no resource-stop reason.

The warm report had zero inferred groups and 343 reused groups; all group
cached flags were true. The semantic fingerprint and every group record
apart from its cached flag matched cold. Interface and object files were
compared byte-for-byte and were identical to the cold artifacts above.
All recorded cold inputs, specs, artifacts and receipts retained their hashes,
and producer authentication passed before and after the invocation.
Warm guard receipt SHA256:
`deadf9456c6283f16353ca1063163ed1d554354151f4f84f30326739417182ee`.
Warm comparison receipt SHA256:
`d0298ab863972bd6f5ed248206a919d447a7983a3f9bdb32d6c08e541cc15355`.

This completes the actual full cold source chain and package-core warm parity
check. It does not substitute for native, bootstrap, async or aggregate gates,
or claim an additional package-core publication-failure injection was run.
