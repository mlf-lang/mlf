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
| Tuple/list migration | Hash current sources, mix historical metadata into the active inventory, and run cutover replay before current controls | Compare independent public IDs with actual executable discovery and case reports. Archive the cutover audit in its recorded Git tree. |
| Core migration | Search current dispatch source and compare every string literal with an older module | Validate current public ID/name/family descriptors and case reports; retain the old transcription proof in Git. |
| Benchmark runner | Search its source for option branches, mode fields and counts of optional-map helpers | Exercise the same option, dependency and report operations used by the real runner with independent inputs and expected values. |
| Installation relocation | Mark plain text executable and check whether a moved file exists | Launch the installed commands after relocation from a different working directory and compare their results. |
| Compact names | Slice production source between private function names | Import the production codec module; retain independent Unicode/boundary vectors and host, interpreter and native checks. |
| Current performance controls | Admit every current source through a growing chain of historical commit, tree and SHA-256 transitions | Authenticate the actual producer and its inputs; execute current code against fixed, independent reference implementations. |
| Figure12 direct checks | Reverse exact edits to five maintained test/helper files before extracting expectations | Load the independent pre-migration reference corpus; execute the existing GHC harness against the authenticated current producer. |
| Workflow resource policy | Repeat each timeout, memory limit and artifact glob in a second configuration | Check positive, compatible resource bounds, required execution and failure propagation; allow ordinary policy tuning. |

## Routine qualification does not extend source history

The retired source-successor chain from `tools/performance/artifact-binary/`
is archived at `496dcae024cae1a93096d9bdb9d6b93e57359dc0`. See the
[retirement guide](../testing-history-retirement.md) for its scope and the
maintained runner and fixture entry points. Adding a module,
renaming a private helper, or changing source layout must not require appending
another commit/tree/parent triple or repinning the chain implementation.

The distinctions are concrete:

- `benchmark-provenance` still checks the benchmark manifest, actual pinned
  workload inputs, and all patch reconstructions with `patch` followed by
  `cmp`. It no longer replays transition, reconciliation or predecessor suites.
- `patricia-integrated` still authenticates the selected producer, checks its
  actual source/object inventory, executes the retained finite controls, and
  rejects inputs changed during the run. Its legacy writer and validation
  reference are fixed fixtures with recorded origins, rather than inverses of
  the current compiler source. The current binary writer controls still run.
- `python-patricia-adapters` exercises the actual runtime preparation entry
  points. It no longer transplants historical Python assertions into a new
  source-successor object.
- The maintained C4/F1 controls retain actual result-parser, process and
  receipt checks. Their checks requiring today's Map/host source to be the
  endpoint of a historical chain have been removed.
- The immutable UTF-8 migration audit and its `source_contract.py` chain are
  retired. `llvm-unicode-memory` directly compiles current `MLF.Host.Base`,
  the ordinary `LegacyBase.hs` reference and independent Unicode controls at
  O0/O2, with this run's input identities and no Git-history dependency.
- Figure12 reference data comes from `720dd649627fbf8b19c7447493a4fdf6fd05eb39`.
  Its cases, signatures, expected types and repairs were compared with the
  old decoder at `171717ad` before removing that decoder. Native Figure12 tests
  continue to execute their maintained implementation independently.

These changes do not remove build/cache input identities, benchmark workload
pins, independent expected outputs, or receipt integrity. An old measurement
continues to identify its original input and producer; a new run records its
own inputs. No source hash is evidence that a behavioral test ran or passed.

### Directly compiled Patricia controls

The maintained controls under `tools/performance/patricia/controls/` compile
directly. Independent old algorithms live under `oracles/` or retain their
existing fixed fixture locations. Ordinary control files are hashed as inputs
to each run, without a fixed source pin that must change whenever the test is
edited. Independent frozen algorithms retain their recorded identities.

Preparation now copies those files. It no longer replaces integer annotations,
imports, test labels, scope assertions or writer bodies, and no longer writes
reversible diffs or a migration ledger. The small `runtime_sources.py` helper
also creates a private view of the current session by replacing its module/export
declaration while preserving its body. Export-list formatting, order and ordinary
comments are accepted; GHC still compiles the resulting module. Current producer
authentication and before/after input and object checks remain in force.

Fingerprint O0, O2 and actual Separate checks use ordinary Python functions and
direct Haskell inputs. No old Python driver is parsed, modified or executed.
C3's consumers use the same preparation helper; their maintained control sources
are no longer pinned to a historical SHA. Their separately fixed baseline owners
remain independent references.

The two obsolete source-adapter suites `python-validation-reuse` and
`python-artifact-binary-p2-writer-bridge` have left the active registry. Their
historical contracts can be reviewed in the recorded checkout. Current
`patricia-integrated --suite validation` still executes boundary and private-export
checks, and `--suite p123` still executes both the retained writer reference and
the actual binary writer. Preparation itself is covered by runtime adapter tests.

The obsolete integrated `map-balance` variant has also been retired. Its demand
for complete historical tree shape after every mutation conflicts with the
already recorded step-21 shape difference. The existing `map-policy` CI entry
retains the historical comparison and independently checks current contents,
balance, cached counts and demand behavior. This cleanup does not change Map
implementation or update old expected shapes to match candidate output.

### Inspecting the dated source audit

The old source-transition scripts, manifests and historical preparation tools
have left the current tree and registries. Their complete retirement snapshot
is `496dcae024cae1a93096d9bdb9d6b93e57359dc0`. Follow the
[historical reproduction instructions](../testing-history-retirement.md#inspect-or-reproduce-an-old-record)
when reviewing one of those records, using that campaign's recorded revision,
toolchain and inputs.

Current execution uses the [direct runner](../../tools/shared/run_direct.py),
[Map policy fixtures](../../tools/performance/map-policy/README.md), and
[Patricia controls and oracles](../../tools/performance/patricia/README.md).
These paths do not prepare or authenticate old PR objects.

### Follow-up acceptance

This table records the earlier de-brittling follow-up, including audits that
have since been retired. Current retirement validation is recorded in the
[retirement guide](../testing-history-retirement.md#validation-of-this-retirement).
A passed preparation or policy check is not a claim that native compiler
execution ran.

| Outcome | Evidence | State |
| --- | --- | --- |
| Current Patricia preparation does not require a Git/source-successor chain | Five runtime adapter controls, including current-source edits in a tree without `.git`, normal and Python `-O` | Passed |
| Independent references preserve the established inputs | 36 graph/P123/validation inputs and three fingerprint inputs are byte-identical to the previous preparation; two maintained controls only lose an extra final blank line. Figure12 semantic data matches its original decoder | Passed; one-time conversion comparison |
| Benchmark input integrity remains checked | `benchmark-provenance`: 22 cases, including 19 executed patch reconstructions; existing manifest pins unchanged | Passed |
| Existing input and receipt checks remain active | Modular artifact controls: 45; C4 controls: 27; F1 controls: 36 | Passed |
| Workflow policy permits ordinary tuning and rejects real control-flow defects | Native partition: 14 cases (12 policy checks plus two upstream qualification-evidence transport checks); general CI policy: seven cases | Passed |
| Figure12 has stable semantic identities without source-spelling pins | 11 data controls, normal and Python `-O`; 92 existing direct case IDs | Passed |
| Historical UTF-8 audit stays bound to its recorded fixture | Three fixture controls, normal and Python `-O`; removed from pre-build CI | Passed |
| Source package snapshots remain consistent | Static local lock audit: 12 packages and 137 source hashes; no lock rewrite | Passed, static only |
| Tuple/list current behavior is independent of migration history | 33 Python gate controls, including a source archive without history and an added case; all 105 actual cases and CLI/report checks under GHC O0 and O2 | Passed |
| Tuple/list interpreter semantics remain covered | Existing interpreter fixture: nine actual results compared with its fixed stdout | Passed; LLVM branch not run in this follow-up |
| Current Patricia behavior remains covered | Fresh GHC 9.14.1 O2 producer; all 19 integrated checks across P123, graph, validation and builtin | Passed |
| Fingerprint preparation no longer modifies a historical Python AST | 15 Python controls in normal and `-O`; actual O0, O2 and Separate Core stages | Passed |
| Private module views tolerate source layout while retaining body bytes | Five header controls in normal and `-O`; actual C3 four-group and full-compiler eight-group execution | Passed |
| Retired Map shape admission has a valid current replacement | Existing `map-policy` O0/O2 runs: historical witness, current contents/balance/count and demand controls | Passed; obsolete integrated shape-equivalence entry removed |
| Compiled Unicode and Figure12 behavior remains valid | Their existing native/GHC routes remain available | Not run in this follow-up |

The complete old source-history traversal was not qualified here. Its optional
historical replay remains separate from this cleanup's acceptance criteria.

The host producers were built through the ordinary GHC 9.14.1 build entry point
at O0 and O2, including source/profile and builtin verification. The first O2
Tuple/list attempt used the watchdog's default 1 GiB address-space bound and
stopped with `out of memory`; the rerun with CI's 6 GiB bound passed. The old
integrated Map shape assertion failed before retirement, as predicted by the
existing step-21 witness. Neither failed attempt is recorded as a passing check.
No compiler runtime or performance speedup is claimed by this harness cleanup.

## Historical evidence stays historical

The retired Tuple/list and Core migration audits, frozen baselines,
transcription checks and negative controls are preserved in Git at
`496dcae024cae1a93096d9bdb9d6b93e57359dc0`. The completed framework cutover is
recorded at `08d7d608c13e89cabad0c81bc494072dafc7c86a`. Those historical records
do not certify present-day test execution.

The active Tuple/list contract currently has 105 ordered IDs. It contains no
source hashes or hard-coded count: the direct gate derives counts from those
independent IDs and checks the actual binary's discovery, default output, JSON
case rows, terminal summary, exact selection and error paths. Renaming a private
registration helper therefore has no effect on the identity contract.

The old cutover metadata and 305 historical observations are available only in
the archived migration contract. `framework-direct` checks the
[active Tuple/list contract](../../tools/testing/tuple-list-active-contract.json);
the old migration and inventory audits are no longer registered. Current gate
controls run without the audit files or `.git`, and accept an independently
supplied new case without changing any historical count.

Core has 746 ordinary actions and 13 substring-adapter observations. Its
independent descriptor contract includes the semantic ID, display name and
family for each observation. Checking a current implementation's legacy labels
alone would miss a semantic ID rename. `release-core-registry-controls` checks
the [descriptor contract](../../tests/golden/core-registry-contract.json) against
the current catalog without historical rename rules. The native unit gate
checks discovery and executed cases against these descriptors.

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

The active suite names in `tools/release/test-suites.json` remain the entry
points for CI reports and exact selection. Discovery enumerates the maintained
test cases, so implementation-specific controls can be replaced without
inventing successful observations for the deleted cases.
