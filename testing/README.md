# MLF test library

`mlf-test` supplies a small case, assertion and runner API in ordinary MLF.
Its modules use only `Bootstrap.Types`, `Bootstrap.Std` and one another; they
do not import compiler inference, graph solving, target checking or package
orchestration. The package depends on `mlf-foundation` in
`libraries/mlf-foundation` for its shared container types and utilities.

```mlf
import Bootstrap.Types
import qualified Test.Assert as A
import qualified Test.Case as C
import qualified Test.Runner as R

cases = Cons (C.test "arithmetic/add" "addition" (Cons "fast" Nil) (do
  A.equal eqInt showInt "sum" 4 (2 + 2)
  A.assert (3 < 4) "ordering")) Nil

main = R.main cases
```

Declare `mlf-test` as a local package dependency and list the executable's
private modules in its manifest as usual. Registration is explicit. IDs use
letters, digits, `.`, `_`, `-` and `/`; names are human-readable descriptions.
The runner validates the entire inventory, including uniqueness, before it
selects or executes any case.

## Assertions and compatibility

`A.Test a` wraps `IO (Either Failure a)` and has a `Monad` instance. A failed
assertion short-circuits the current case; the runner records it and continues
with subsequent cases. `A.equal same display message expected actual` retains
both rendered values. `A.right display result` unwraps an `Either`, and
`A.liftIO action` embeds an IO operation.

`C.described group level inputs oracles purposes entry` adds separate namespaced
`group:NAME`, `level:NAME`, `input:NAME`, `oracle:NAME` and `purpose:NAME` tags.
It preserves the case's ID, name, action and existing tags, removing duplicates.
The generic library does not prescribe a vocabulary. The compiler repository
reviews its seven primary groups and metadata axes in
[`tests/test-catalog.json`](../tests/test-catalog.json).

`C.classified categories techniques entry` remains available for existing
`category:NAME` and `technique:NAME` tags. It preserves the same case identity
and action; adding metadata does not create another execution.

`C.toLegacy` adapts a case back to `Pair String (IO Unit)`, preserving its name
and exiting unsuccessfully on failure. `C.fromIO` adapts an existing named IO
action. It cannot recover a legacy action that calls `exitWith` or panics.
The core runner executes sequentially in one process. The optional
[`mlf-test-tools` package](tools/README.md) supplies `Test.Process` and the
`mlf-test` executable for per-case process isolation, monotonic timings and
timeouts, with separate results for assertions, crashes and protocol failures.

## Selection and reporting

The runner accepts `--list`, `--filter TEXT`, `--exact ID`, `--tag TAG`,
`--group NAME`, `--level NAME`, `--input NAME`, `--oracle NAME`, `--purpose NAME`,
`--category NAME`, `--technique NAME`,
`--format text|json`, and `--report FILE`. Filters match substrings of IDs or
names, exact selection matches IDs only, and tags match exactly. Repeated selectors are combined with
AND. Metadata options match the corresponding namespaced tags; they do not
change test actions or the selected/full scope. In this generic runner,
`--category` and `--technique` still match their legacy namespaces. The compiler
campaign catalog separately provides compatibility queries over its reviewed
metadata.
Listing never executes actions. Invalid arguments, duplicate/invalid IDs,
empty inventories and selections with no matches exit with status 2. Completed
runs exit 0 when all selected cases pass, or 1 when any assertion fails.

JSON output is a versioned JSON Lines protocol (`schema_version: 1`):

- Listing emits one `inventory` object containing the selected case descriptors.
- Execution emits `start` with the selected IDs, one `case` result per action,
  and a final `summary` with executed/passed/failed counts and `complete: true`.
- `total`, `selected` and `scope` distinguish full from partial inventories.
  `complete` means every selected action returned; it does not imply every
  registered case was selected, or that the assertions passed.
- A missing terminal summary means execution did not complete. Consumers must
  also check the process exit status and compare results against the selected IDs.

`--report FILE` saves JSON independently of action output, even in text mode.
Before execution it replaces any previous report with a `start` record; after
all selected actions return it writes their results and the terminal summary.
An interrupted run therefore leaves an incomplete report. JSON on stdout still
requires actions to reserve stdout for the runner, using stderr for diagnostics;
the runner does not capture arbitrary IO output. Coverage requirements belong
to a separately reviewed inventory, rather than being inferred solely from the
cases that happen to run.

## First migrated suite

`Tests.IntSetUnions` exposes `cases` to the runner and retains `suite` for Core.
Its original label, sorted-list oracle, size/balancing assertions and all 360
ordered stimuli / 276 distinct executions are preserved. Core has 684 registered
checks after the separately reviewed [duplicate consolidation](../tests/README.md);
the migrated IntSetUnions action is unchanged. The root `unit` group runs the framework's library and CLI
contract checks separately, outside that existing count. Framework sources are
included in the group's before/after source fingerprints.

With the native compiler and package manager configured as described in the
repository README:

```sh
./mlfpkg --manifest tests/mlf-package.json run int-set-unions -- --list
./mlfpkg --manifest tests/mlf-package.json run int-set-unions -- \
  --exact int-set/union-sorted-list --format json
./mlfpkg --manifest tests/mlf-package.json run int-set-unions -- \
  --group runtime-library --level component --input exhaustive \
  --oracle independent-reference --purpose conformance --format json
./mlfpkg --manifest tests/mlf-package.json run test-framework
MLF_TEST_HOST_SUPPORT=/absolute/path/to/host-support \
  ./mlfpkg --manifest tests/mlf-package.json test --target framework-cli
./mlfpkg --timeout 21600 test --target unit
```

`test-framework --probe --format json` deliberately runs failing assertions
around a passing case and exits 1. It exercises continuation and failure reports.
`test-framework --list-probe --list --format json` lists an action that would
panic if executed, to check the listing boundary.

Core, Harness, Backends and Port also expose their original IO actions through
the compiler campaign's case/family protocol: `--list-families` discovers IDs,
and `--families ID...` selects complete actions in registry order. This protocol
uses `Tests.Selection` and strict partial receipts; it is separate from the
generic `Test.Runner` case protocol above. See the
[compiler test selection guide](../tests/README.md) for batching, coverage
projections and full-campaign commands.

## Typed migration contracts (envelope v2)

The existing `Case` constructor, `Runner.Result`, CLI, and Runner JSONL schema
v1 remain compatible for one migration cycle; no removal date is set before
all existing consumers are migrated and reviewed. `Case.descriptor` is the
explicit v1-to-descriptor bridge and does not execute the case. `Runner.typedOutcome`
retains assertion failures, and `Assert.expect` checks typed observations.
The count-only `Runner.summaryJson` helper cannot authenticate identities;
`Runner.run` now uses `summaryJsonFor` to check the actual selected IDs as well.

- `Test.Descriptor` owns stable IDs, positive contract revisions, metadata,
  required/optional policy and expectations. Source hashes are not IDs.
- `Test.Registry` rejects duplicate, missing and unknown IDs without silently
  converting inventories to sets. Registry selection cannot be empty.
- `Test.Outcome` distinguishes assertions, expected rejection, crash, timeout,
  cancellation, protocol/infrastructure failures, unsupported and skip.
- `Test.Expectation` binds rejection to an exact phase, diagnostic code,
  nonzero exit code and independent verification. Expected signals likewise
  require an explicit phase/reason/signal. Deadline and interruption never pass.
  An expected child timeout must be validated as data by an adapter whose
  outer observation completes normally; it is not a timeout of that case.
- `Test.Evidence` validates typed version-2 envelopes against a trusted plan.
  Run/attempt and catalog/plan/source/tools/config/manifest/lock/runtime/
  dependencies/platform identities must match exactly. Source identity must
  include dirty-tree content. Start/terminal events are paired per ID, with
  duplicate, unknown and out-of-order events rejected. Sealing requires the
  exact selected terminal inventory and a finished cleanup operation.

`Evidence.assess` is pure: adapters must obtain actual input identities and read
raw artifacts to compute `RawEvidence`'s actual digest independently of the
recorded digest. Supplying two copies of an untrusted claimed hash does not
verify bytes. No raw payload or independent oracle is replaced by this envelope.
Legacy receipts missing identities or cleanup evidence cannot be promoted to
v2 qualification by filling in assumed values.

A plan explicitly declares `FullQualification` or `SelectedCoverage` intent.
An exact physical shard inventory is not a logical full universe. Reserved
`logical-scope:partial` and `qualification:ineligible` tags conservatively block
full scope or qualification respectively, including through the v1 bridge.

Completion, success and full selection are independent. A full failed run may
be complete; a partial successful run cannot qualify. Optional, explained
skip/unsupported observations may satisfy a development selection's policy,
but never make qualification eligible. Required skips, failed cleanup, stale
bindings, corrupt evidence and unfinished receipts cannot pass a gate.
Compiler-specific oracles remain outside the generic library. Focused controls
live in `Tests.TestFramework` under its existing reviewed coverage inventory.
