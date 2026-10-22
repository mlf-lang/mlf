# MLF test library

`mlf-test` supplies a small case, assertion and runner API in ordinary MLF.
Its modules use only `Bootstrap.Types`, `Bootstrap.Std` and one another; they
do not import compiler inference, graph solving, target checking or package
orchestration. The package currently depends on `mlf-bootstrap` for its shared
container types and utilities.

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

`C.toLegacy` adapts a case back to `Pair String (IO Unit)`, preserving its name
and exiting unsuccessfully on failure. `C.fromIO` adapts an existing named IO
action. It cannot recover a legacy action that calls `exitWith` or panics.
The core runner executes sequentially in one process. The optional
[`mlf-test-tools` package](tools/README.md) supplies `Test.Process` and the
`mlf-test` executable for per-case process isolation, monotonic timings and
timeouts, with separate results for assertions, crashes and protocol failures.

## Selection and reporting

The runner accepts `--list`, `--filter TEXT`, `--exact ID`, `--tag TAG`,
`--format text|json`, and `--report FILE`. Filters match substrings of IDs or
names, exact selection matches IDs only, and tags match exactly. Repeated selectors are combined with
AND. Listing never executes actions. Invalid arguments, duplicate/invalid IDs,
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
ordered stimuli / 276 distinct executions are preserved. Core retains its 686
registered checks. The root `unit` group runs the framework's library and CLI
contract checks separately, outside that existing count. Framework sources are
included in the group's before/after source fingerprints.

With the native compiler and package manager configured as described in the
repository README:

```sh
./mlfpkg --manifest tests/mlf-package.json run int-set-unions -- --list
./mlfpkg --manifest tests/mlf-package.json run int-set-unions -- \
  --exact int-set/union-sorted-list --format json
./mlfpkg --manifest tests/mlf-package.json run test-framework
MLF_TEST_HOST_SUPPORT=/absolute/path/to/host-support \
  ./mlfpkg --manifest tests/mlf-package.json test --target framework-cli
./mlfpkg --timeout 21600 test --target unit
```

`test-framework --probe --format json` deliberately runs failing assertions
around a passing case and exits 1. It exercises continuation and failure reports.
`test-framework --list-probe --list --format json` lists an action that would
panic if executed, to check the listing boundary.
