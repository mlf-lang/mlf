# Future host-output comparison contract

No real host output accompanies this source study. The Haskell fixture remains
uncompiled/unrun. The Python validator's tests create only explicitly marked
synthetic records in memory; they do not execute or approve a Haskell build.

## Complete observation stream

Each implemented case in `CASE-MAP.json` must emit one line in the listed order:

```text
PASS<TAB>case-id<TAB>shown-string-observation
```

The third field is an opaque single-line Haskell `show String` representation,
including its surrounding quotes. It can preserve encoded observation bytes
without a JSON dependency in the host fixture. The comparator does not parse or
normalize that representation: every variant must emit the exact same field.
Raw tabs/newlines belong in escaped form inside the shown string, not as extra
stream separators. Diagnostic output must not be inserted into this stream.
The validator checks only the surrounding-quote shape, not a complete Haskell
string grammar or each aggregated observation's internal coverage/hex syntax.
It cannot discover the same missing internal observation in all three outputs;
that obligation remains in the pinned fixture source and CASE-MAP review.

The last LF-terminated line must be `SUMMARY<TAB>N<TAB>N`, with N exactly equal
to the required case count. Missing, duplicated, unknown, reordered or failed
cases, extra lines, payload differences and partial summaries are rejected.
The tool never compares only an intersection of the three output case sets.

## Records, not authenticated execution receipts

After an independently authorized and actually completed ordinary host build,
a future caller may record each stream in a JSON object with these fields:

- `schema_version`: 1.
- `variant`: `baseline`, `delete-only` or `spine-only`.
- `fixture_sha256`, `case_map_sha256`: exact local source/map bytes used.
- `baseline_source_commit`: the pinned original revision.
- `openfragment_sha256`: the corresponding exact original or candidate bytes,
  as recorded in the existing patch checks.
- `build_kind`: `ordinary`, not profiled/instrumented/mixed.
- `shared_build_inputs_sha256`: the same common-input manifest digest for all
  three variants. That manifest should cover exact toolchain, flags, dependency
  and source inputs, excluding only the named alternative OpenFragment file.
- `evidence_kind`: `reported-host-output`; unit tests use the distinct value
  `synthetic-test-output` and cannot be mixed with reported outputs.
- `stdout` and `stdout_sha256`: the complete UTF-8 stream and its exact digest.

`validate_host_outputs.py` verifies consistency of these claimed fields and the
local fixture/map bytes. It **cannot authenticate** that a build happened,
that a reported manifest describes real inputs, or that the executable emitted
the supplied text. External build logs, source provenance and ordinary artifact
qualification remain separate evidence. A successful content comparison always
reports `actual_haskell_execution_established=false`,
`build_provenance_authenticated=false`, `artifact_equivalence_established=false`,
`performance_claim_established=false`, and `resume_authorized=false`.

No cleanup/lease authorization is obtained from these records. No run wrapper,
compiler invocation or CI workflow is created by this study.

## Pure validator check

From this directory, only the standard-library synthetic test suite runs:

```text
python3 -B -m unittest -v test_validate_host_outputs
```

The tests cover complete matching records, truncation, omitted/duplicate cases,
failure statuses, changed actual payload, wrong source variant, mismatched
fixture/map/build-input claims, duplicate JSON keys and mixed evidence kinds.
They are tests of the comparison utility, not successful compiler regressions.
