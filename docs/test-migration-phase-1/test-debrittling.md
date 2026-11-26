# Test de-brittling

This refactoring separates public behavior and immutable evidence from the
current implementation's spelling. Test IDs, independent expected results,
error status, coverage and provenance remain contracts. Private helper names,
local variable names, display labels, comments and YAML layout do not.

## Boundaries

| Area | Previous coupling | Executable or data contract |
| --- | --- | --- |
| Framework budget policy | AST call locations, local names and keyword spelling | Import the policy normally; execute the gate and inspect dispatched timeouts and its terminal receipt. |
| Guest framework controls | Search fixture source for particular imports and bindings | Execute the gate with bounded command fixtures; verify positive and negative results, prerequisites, publication and input integrity. Language semantics remain covered by the real compiler gate. |
| CI workflows | Exact YAML fragments, step display names and whole shell blocks | Parse YAML, inspect job dependencies and conditions, execute relevant shell blocks with recording tools, and inject failures. |
| Tuple/list migration | Hash the maintained implementation and extract current registrations with a regex | Authenticate the recorded cutover. Compare independent IDs with actual executable discovery and case reports. |
| Core migration | Search current dispatch source and compare every string literal with an older module | Preserve those checks on the immutable cutover; validate current public ID/name/family descriptors and case reports separately. |
| Benchmark runner | Search its source for option branches, mode fields and counts of optional-map helpers | Exercise the same option, dependency and report operations used by the real runner with independent inputs and expected values. |
| Installation relocation | Mark plain text executable and check whether a moved file exists | Launch the installed commands after relocation from a different working directory and compare their results. |
| Compact names | Slice production source between private function names | Import the production codec module; retain independent Unicode/boundary vectors and host, interpreter and native checks. |

## Historical evidence stays historical

The Tuple/list and Core migration audits retain their frozen baseline,
transcription checks, source hashes, independent oracle comparisons and negative
controls. The completed framework cutover is recorded at
`08d7d608c13e89cabad0c81bc494072dafc7c86a`. These audits read that Git object,
not a similarly named file in the working tree. They do not certify present-day
test execution.

The active Tuple/list contract still has 105 ordered IDs and records the
305 historical observations. The direct gate checks the actual binary's
discovery, default output, JSON case rows, terminal summary, exact selection and
error paths. Renaming a private registration helper therefore has no effect on
the identity contract.

Core has 746 ordinary actions and 13 substring-adapter observations. Its
independent descriptor contract includes the semantic ID, display name and
family for each observation. Checking a current implementation's legacy labels
alone would miss a semantic ID rename. The native unit gate checks discovery
and executed cases against these descriptors.

Every actual qualification continues to authenticate the producer, source
inputs and retained artifacts. Moving a historical source proof away from
current source text does not authorize stale binaries or modified evidence.

## What should still be exact

- Public case IDs, required family membership and coverage multiplicities.
- Fixed expected output, including binary bytes or significant whitespace.
- Exit status and error phase when they distinguish rejection from a crash or
  infrastructure failure.
- Frozen oracle, benchmark fixture and migration snapshot hashes.
- Build input identities and independently retained result hashes.
- Observable rollback, publication, process cleanup and failure propagation.
- Generated code properties that are the subject of a compiler test.

Do not turn any of these into a substring check, a count-only check, or an
expectation derived from the current implementation.

## Extending the tests

Use the normal command, import or public data interface whenever possible.
Control tests may replace expensive tools with small recording executables,
but the real gate should still parse its actual inputs, execute its control
flow, and validate its receipts.

For a removed source-shape assertion, identify which existing behavioral test
covers its purpose. Add a missing behavioral case before removing the assertion.
When choosing a representative refactoring check, use a change that previously
failed without changing behavior: rename a local, reorder an equivalent
predicate, rename a step display label, or reformat a mapping. Pair that with a
real defect such as a wrong timeout, missing prerequisite, changed semantic ID
or swallowed failure.

Do not add a parser for a convenient subset of another format merely to support
tests. The workflow controls use an explicitly pinned test-only YAML dependency;
tests themselves do not download dependencies.

The canonical suite names in `tools/release/test-suites.json` remain the entry
points for CI reports and exact selection. Discovery enumerates the maintained
test cases, so implementation-specific controls can be replaced without
inventing successful observations for the deleted cases.
