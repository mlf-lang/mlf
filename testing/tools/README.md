# Process-supervised MLF tests

`mlf-test-tools` is an optional package above the light `mlf-test` library. Its
`mlf-test` executable runs each selected case in a separate process, measures
monotonic elapsed time, stops timed-out process groups and continues after
assertion failures, crashes and timeouts. It uses the existing POSIX measurement
transport built from `tests/native/host_support.c`; it adds no runtime primitives.

```sh
./mlfpkg --manifest testing/tools/mlf-package.json build --target mlf-test
testing/tools/.mlf-build/bin/mlf-test \
  --host-tool /absolute/path/to/host-support \
  --work-dir .mlf-build/supervised-tests --report .mlf-build/supervised.jsonl \
  --timeout 60 --tag oracle --format json -- \
  /absolute/path/to/int-set-unions
```

`--work-dir` is required. The helper defaults to `MLF_TEST_HOST_SUPPORT` when
`--host-tool` is omitted. Timeouts are positive integer seconds (default 60,
maximum 2147483587). Arguments after `--` are the executable and fixed prefix
arguments; the supervisor appends the test protocol arguments. The executable
must support `Test.Runner`'s inventory, exact selection and report protocol.
Selectors, their AND semantics, and `--list` are shared with `Test.Runner`.
Listing queries the inventory but never executes test actions.

Each invocation allocates a fresh directory under the work directory, and each
case gets a numbered subdirectory. `MLF_TEST_CASE_WORK` points to that case's
directory. The original working directory is preserved so relative fixture
paths continue to work. Reports, stdout, stderr and measurement records remain
available there. Cases receive empty stdin. Concurrent invocations have separate
artifacts; an explicitly shared parent report path is locked until its writer
finishes.

JSON output and the saved report use `schema_version: 1` and `runner: "process"`.
The report contains `start`, one `case` row per selected ID, and a terminal
`summary`. Case statuses are `passed`, `failed`, `crashed`, `timed_out` or
`protocol_error`. Rows carry `wall_seconds`, `exit_code` and artifact paths.
Ordinary assertion failure requires a valid child report consistent with exit 1;
an incomplete child report with unsuccessful termination is a crash. Invalid or
missing measurement data always produces `protocol_error`, with null timing.
The summary's elapsed time is the sum of measured child durations, excluding
discovery and supervisor overhead; it is null if any measurement is invalid.

`complete: true` means every selected child was supervised. It does not mean all
tests passed. The supervisor exits 0 only when all cases pass, 1 when any selected
case is unsuccessful, and 2 for invalid arguments, discovery or selection. A
saved report is replaced before discovery and again with the selected start
record before cases execute, so an interrupted supervisor cannot retain an old
successful summary. Consumers must also check the actual exit status and IDs.

The pure `parse`, `parseInventory`, `parseMeasurement`, `validateChildReport`,
`classify`, `caseJson` and `summaryJson` functions are public for independent
contract and mutation tests. Inventory descriptors and child reports are checked
before their fields are used. No compiler oracle or compiler-specific test
coverage policy lives in this package.
