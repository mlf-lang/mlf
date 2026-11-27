# Builtin identity in source query keys

A source query caches the checked provisional xMLF object for one value SCC.
Both source drivers hash the running executable and pass that identity into
each key. Datatype validation in inference and in the raw xMLF checker starts
with the ordered `Data.builtinDeclarations` and extends its maps with the user
declarations. The empty environment derives its constructor and datatype maps
from the same list. Source v7 reads the very same value.

## Frozen query oracle interface

`frozen_query.py` retains the fixed named-only `FrozenCrateQuery` inputs used
by the datatype-context and sparse-contract controls. It reads only the
`SExpr` and `SPattern` constructor interface from the maintained
`Bootstrap.Types` source. Comments, formatting and unrelated type declarations
do not select a new hash whitelist entry. Recognized indexed/dictionary forms
receive explicit rejection branches in every frozen traversal; unknown or
incompatible constructor signatures fail preparation. The old named algorithm
and its independent output expectations remain unchanged. Only the fixed
oracle file has an integrity digest.

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

## Per-group cache keys

The retained per-group query API compares complete keys. V6 and v7 full keys have separate addresses. A v6-only cache incurs a cold
source compile. Existing records remain on disk and identical user context
carriers can be shared. There is no in-place rewrite or cache collection.
An old or foreign record at a current address fails key comparison and the
driver infers that group again. The MLFBIN schemas, raw checksums, file and
graph limits, eight-entry read window, locking and atomic publication are
unchanged. Text source-cache records and unaddressed 300/301 records trigger reinference.
Their replacements carry the current input and result fingerprints. The cache
uses its existing cooperative, trusted-directory model.

## Current checks

Run the registered `source-context-cache` suite against a current optimized
GHC build to exercise cold inference, warm reuse, key mismatches, corruption
repair and lock handling for the per-group API. The `query-graph-acceptance`
suite checks the compiler CLI's current generation and publication path.

```sh
python3 -B tools/testing/run.py source-context-cache --list
python3 -B tools/testing/run.py source-context-cache -- --build-receipt .mlf-build/shared-ghc/receipt.json --output .mlf-build/source-context-cache
python3 -B tools/testing/run.py query-graph-acceptance -- .mlf-build/shared-ghc/bin/emlf .mlf-build/query-graph-acceptance
```

The builtin mutation control holds the compiler identity fixed across two
different builtin declarations, plants each foreign record under the other's
address, and checks that both caches repair and subsequently hit.

```sh
python3 tools/performance/source-key-builtins/test-builtin.py .mlf-build/key-mutation
```

## Historical v6 to v7 measurements

PR #29 measured cold, warm and single-edit compilations of the 14-module
Foundation package using a modified executable that contained both versions
of the query driver. The [study report](https://github.com/mlf-lang/mlf/blob/0704d216b8cf6d887d3737efa30a2eae3c152f0a/tools/performance/source-key-builtins/README.md#foundation-results)
includes the results, [protocol](https://github.com/mlf-lang/mlf/blob/0704d216b8cf6d887d3737efa30a2eae3c152f0a/tools/performance/source-key-builtins/PROTOCOL.md),
[raw measurements](https://github.com/mlf-lang/mlf/blob/0704d216b8cf6d887d3737efa30a2eae3c152f0a/tools/performance/source-key-builtins/results-20261103.json)
and [reproduction scripts](https://github.com/mlf-lang/mlf/tree/0704d216b8cf6d887d3737efa30a2eae3c152f0a/tools/performance/source-key-builtins).
