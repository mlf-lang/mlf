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
