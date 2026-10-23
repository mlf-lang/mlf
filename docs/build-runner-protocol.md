# Native build runner protocol

`mlf-build-runner` executes a dependency graph supplied by the package manager.
The package manager owns resolution, action identities, caching, validation,
artifact publication, and report composition. The helper owns process readiness,
concurrency, deadlines, cleanup, and measurements.

## Commands

- `mlf-build-runner --protocol-version` prints `1` and a newline.
- `mlf-build-runner --new-invocation-id` prints 32 bytes from the operating system
  random generator as 64 lowercase hexadecimal characters and a newline.
- `mlf-build-runner PLAN RESULT` reads a plan file and atomically publishes its
  result document to `RESULT`.

An invocation must have a fresh random ID. It is execution metadata, never part
of an artifact cache key. Callers must discard previous result files before a
new execution and validate both the process exit and the complete result.

## Plan version 1

The file contains UTF-8 fields, each terminated by a NUL byte, including the last
field. Numbers are unsigned decimal integers. There is no shell parsing.

| Field | Meaning |
| --- | --- |
| `MLF_BUILD_PLAN` | Protocol magic |
| `1` | Protocol version |
| invocation ID | Nonempty execution identity |
| jobs | Maximum simultaneous actions, between 1 and 100,000 |
| task count | Number of following task records, between 0 and 100,000 |

Each task record contains these fields in order:

1. Nonempty, unique task ID.
2. Positive deadline in seconds, at most 2,147,483,647, measured from launch.
3. Dependency count, followed by that many task IDs.
4. Working directory; empty inherits the runner's directory.
5. Standard input path, standard output path, standard error path.
6. Argument count, followed by that many argument fields, starting with the
   executable. The count is between 1 and 65,536.

Empty stream paths inherit the corresponding stream. Relative stream paths are
relative to the task working directory. Equal nonempty output and error paths
share one descriptor, so one stream does not truncate the other. Empty arguments,
spaces, quotes, backslashes, newlines, and Unicode are preserved.

Dependencies may refer forward or backward in the record order. Unknown,
duplicate, self, or cyclic dependencies are invalid. The entire plan is validated
before any command starts or any task stream is opened. Files larger than
256 MiB, invalid UTF-8, unsupported versions, trailing fields, and truncated
records are rejected.

## Result version 1

The JSON object contains:

- `protocol_version`: `1`.
- `invocation_id`: the plan's invocation ID.
- `plan_digest`: SHA-256 of the exact input file bytes, as 64 lowercase hex digits.
- `complete`: `true` once every task has a terminal result, including failed runs.
- `exit_code`: zero only if every task succeeded.
- `jobs`, `maximum_parallel_jobs`, and `wall_seconds`.
- `aggregate_peak_rss_bytes` and `memory_sample_interval_seconds`.
- `tasks`: exactly one record per input task, in input order.

Each task record contains `id`, `state`, `exit_code`, `pid`, `started_seconds`,
`finished_seconds`, `wall_seconds`, `cpu_seconds`, `peak_rss_bytes`, and
`aggregate_peak_rss_bytes`. Times are measured against the invocation start.
Unlaunched tasks have zero PID and timing fields.

| State | Meaning |
| --- | --- |
| `succeeded` | Worker exited zero; its remaining descendants were stopped |
| `failed` | Worker or launch failed, or its deadline expired |
| `cancelled` | Active or independent queued action stopped after failure/cancellation |
| `blocked` | A predecessor failed, was cancelled, or was itself blocked |

A failed task stops new launches immediately after the failure is observed. All
active lifetimes are terminated and their workers reaped before result publication. Independent
ready work is launched whenever capacity becomes available; dependency levels do
not form barriers.

The process exits zero only for a complete successful invocation. Invalid plans
exit 64 without a complete result. Deadline failures use 124, cancelled actions
use 125, launch failures use 126, and missing executables use 127. Failure to
publish a result exits 74. A nonzero process exit, absent/malformed result,
incomplete task set, mismatched invocation ID/digest, non-success task state, or
nonzero task exit must never be accepted as successful, even if an earlier result
file exists.

## Process lifetimes and measurements

On POSIX, each worker owns a session. A separate guardian watches a pipe whose
only writer is the runner. Closing that pipe, including through runner SIGKILL,
stops the worker session. Session membership also covers older seed runtimes
that create new process groups for their children, and remains valid after
reparenting. Linux guardians additionally act as child subreapers. The runner
monitors its coordinator and cancels when that parent dies. Current runtimes
preserve the verified worker scope for nested process calls. Programs must not
deliberately escape their build lifetime by creating a new session.

On Windows, each worker starts suspended, is assigned to a job with
`KILL_ON_JOB_CLOSE`, and is then resumed. The runner owns the noninherited job
handle. Runner death closes the handle and stops the entire job hierarchy;
coordinator death is detected through a retained process handle. Unicode argv
uses native wide-character APIs and Microsoft CRT argument quoting.

`aggregate_peak_rss_bytes` is the largest observed sum of resident memory across
live action processes and descendants, sampled every 50 ms. Per-task aggregate
peaks are tracked separately. Samples can miss short peaks, and summing RSS counts
shared pages once per process. `peak_rss_bytes` reports the worker's native
high-water measurement separately. These measurements do not include coordinator
or runner overhead and are not a claim of exact physical memory usage.

The native integration driver is built from `tests/native/build_runner_tests.c`
and invoked as `build-runner-tests RUNNER FIXTURE SCRATCH`, where `FIXTURE` is
built from `tests/native/build_runner_fixture.c`. The active package test group
runs its 22 synchronization, lifecycle, argument, and protocol checks.
