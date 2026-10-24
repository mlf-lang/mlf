# Cooperative typed tasks

`Async.Task` builds on `Async.Process` and the checked, typed completion-cell
runtime. A task is a cold description: constructing it does not execute it.
`spawn task` starts a new execution and returns an opaque `Fiber a`; repeated
`await` of that fiber observes the same retained outcome. Spawning the same task
again starts another execution. There is no detached spawn or unrestricted
`IO a -> Task a` operation.

The implementation is a single coordinator, not shared-memory parallel MLF
execution. It queues uniform `IO Unit` resumptions. Each `Fiber a` contains its
own typed completion endpoint, and no task ID is used to cast or retrieve a
typed result. IDs in the wait graph contain only dependency metadata. Both
registered Task modules hide the task, fiber, scope and resolver constructors.

## API

Import the module qualified, since `pure`, `bind`, and `runProcess` also have
prelude meanings:

```haskell
import qualified Async.Task as T

answer = T.run T.defaultOptions
  (T.bind (T.spawn (T.pure 41))
    (\fiber -> T.map (\value -> value + 1) (T.await fiber)))
```

The result is `IO (Outcome Int)`, where:

```haskell
data Outcome a = Succeeded a | Failed AsyncError | Cancelled CancelReason
data CancelReason = CancelReason Int String
```

`pure`, `map`, `bind` and `fail` construct tasks. `yield` queues a continuation.
`sleep milliseconds` registers a cancellable monotonic timer, including for zero
milliseconds. Negative durations and durations larger than 4,294,967,295 ms fail
explicitly. A sleeping or awaiting task consumes retained memory but no process
permit. Pure computation and arbitrary work in a continuation cannot be
preempted; a non-yielding continuation can delay all event and timer servicing.
A successful outcome does not imply deep evaluation of its returned value.

`run options task` creates the outer scope and executes all its work, joining
children before returning. `spawn task` uses the current scope implicitly.
Children belong to that scope, not individually to the fiber that spawned them.
Cancelling one consumer therefore does not cancel a shared prerequisite in the
same scope. Cancelling a non-root parent fiber also does not cancel its separately
spawned same-scope children; the owning scope still joins them. If a scope root
itself returns cancellation, including by awaiting a cancelled child, its group
requests sibling cancellation and joins before returning.

`withScope task` creates a nested group. It has its own failure state,
cancellation state, join count and wait graph, while sharing the outer
coordinator, invocation-wide live-fiber/completion/callback budgets and process
supervisor. Suspension and admission checks observe ancestor cancellation
synchronously, without waiting for its queued notification. Its caller is
suspended until the whole group has joined. A fiber may only be awaited or
cancelled within its owning scope. Escaped and cross-scope handles fail at
runtime. This is not a claim of compile-time non-escape.

`withTimeout milliseconds task` is a nested group with a total monotonic
deadline, including the time spent joining children after the body returns.
Expiry records `AsyncError 124`, cancels unfinished work and joins cleanup.
The duration bounds are the same as `sleep`. Expiry starts cancellation; cleanup
may take longer than the timeout. A timer and completion ready together are
processed in coordinator order, not a promised deterministic race order.

## Failure and cancellation

An unhandled child failure fails its owning scope, wakes suspended work and
requests sibling cancellation. `awaitOutcome fiber` returns an outcome as data
but does not undo this fail-fast policy. `await fiber` propagates failure or
cancellation. Expected recoverable errors should be ordinary `Either` results,
or captured inside the child before it is spawned:

```haskell
T.bind (T.spawn (T.capture recoverableTask)) T.await
```

`capture task` turns a recoverable task failure into a successful `Outcome`
value. It does not swallow external scope/fiber cancellation or an already
accepted failure of the surrounding scope. `capture (withScope task)` can
recover the nested group's failure after that group has joined its children.

`cancel fiber reason` requests cancellation idempotently. A completed fiber's
outcome remains unchanged. Queued work checks its cancellation before starting.
Suspended waits and timers unregister losing callbacks and resume once.
`cancelScope reason` requests cancellation of the current group. Task reason
codes are arbitrary MLF integers; the process backend uses a reserved bounded
reason code internally, preserving the Task reason separately.

Cancellation of a running process fiber requests termination and keeps the
fiber alive until the supervisor reports a terminal outcome. Consequently a
scope cannot finish while one of its managed processes remains unreaped.
The first cleanup diagnostic in each group is retained independently of its
primary failure and is attached as `CleanupFailed`, including inside a nested
task scope or when parent cancellation wins. This is bounded first-error
reporting, not an enumeration of every cleanup error from every sibling. The first accepted
terminal completion is never resurrected by a later success.

Self-await and dynamic wait cycles are checked before a wait edge is installed.
They report `AsyncError 109`. Invalid parameters use 101, a closed scope 103,
admission limits 104, and a wrong-scope fiber 105. Underlying process errors
retain the `Async.Process` codes. A scope with unfinished fibers and neither
runnable work nor live timers also fails explicitly rather than hanging.

## Limits and combinators

```haskell
Options retainedCells callbackReservations liveFibers processOptions
```

The defaults are 65,536 retained cells, 8,192 simultaneous callback/timer
reservations and 4,096 live fibers across the entire invocation, plus
`Async.Process.defaultOptions`. Every scope root counts as a live fiber,
including suspended outer roots. Waiting fibers retain their memory. Cells and completed results are retained until the
outer coordinator closes; this is a cumulative allocation bound, not merely a
bound on currently running tasks. Nested scopes share the live-fiber and
cell/callback budgets, so creating more scopes does not bypass it. Process concurrency, pending
submissions and retained process results have their own limits.

- `all width tasks` fails fast and returns successful values in input order.
- `collect width tasks` captures each child's recoverable failure before spawn
  and returns all outcomes in input order. External cancellation still propagates.
- `mapConcurrentlyN width function values` provides the same bounded fan-out for
  a mapped list.

Widths must be positive. These first combinators use bounded windows: they spawn
at most `width` child fibers, await that window and then feed the next one. They
do not eagerly create a fiber/callback for every input. A slow early window can
leave unused capacity; this implementation does not promise work-conserving
sliding-window throughput. Choose a width below the live-fiber bound, leaving
room for the root and other children. Logical dependency waits do not hold a
process permit, including with jobs=1.

## Process tasks and the build-engine boundary

`runProcess spec` yields a `ProcessOutcome`. Nonzero exit statuses are ordinary
data. `checkedProcess spec` deliberately turns unsuccessful exit, launch,
cancellation, timeout or cleanup outcomes into task failures. See
[`async-process.md`](async-process.md) for argument transport, file logs,
platform containment, deadlines and cleanup limitations.

A process task reserves its continuation before admitting a child. Shared
Task-side active/pending counters keep waiting processes in cancellable Task
resumptions, never in the native launch queue. Thus another supervisor pump
cannot launch a process after its Task cancellation has been accepted. Pending
processes count against the configured pending limit; an already active process
retains its permit until terminal reaping. A process total deadline starts when
its Task operation begins, includes ready/pending queue time, and passes only
the remaining duration to native submission. Running timeouts still begin at
launch. Each poll reuses its reservation and registers a two-millisecond timer
instead of busy spinning. Polls themselves use nonblocking supervisor calls.
Timer servicing and process cancellation are cooperative. An exceptional allocation/protocol
failure while a process already exists uses a synchronous cancel-and-join
fallback for that child rather than abandon its cleanup obligation; normal
quota rejection occurs before admission.

`tests/async-task/Processes.emlf` is also the executable synthetic integration
proof. One scenario discovers B from A's exit while an independent C remains
running behind a file gate. A second creates a dynamic diamond with one shared
prerequisite, discovers B/C from its result and D from theirs, and asserts the
same values and artifact bytes for jobs=1 and jobs=4. These are execution tests,
not an incremental query engine: no key deduplication, cache-validity logic,
fingerprinting or atomic build-artifact publication is implemented here.

## Qualification

On **2026-10-23**, the real Linux stage-2 compiler passed all **30 contracts on
both the checked interpreter and native LLVM**, plus all **5 source rejections**.
The six white-box cases are included in those 30. The completed receipt records
unchanged input hashes, checked `IO Unit` targets, literal output comparisons,
and compiler/runtime/artifact/observation hashes. No seed surrogate was used.
The evidence artifact is
`.mlf-build/async-production-bootstrap-20261023T0422Z/gates/task/result.json`,
with `complete: true`. Linux language qualification uses `ulimit -s unlimited`.
Independent checks with the same production compiler reproduced SIGSEGVs at an
8 MiB stack while checking, emitting, or interpreting larger Task targets, and
while checking deep non-async targets. Unlimited-stack checks pass; separately
compiled native yield, await and bind probes each completed 100,000 iterations
at 8 MiB. This is a known compiler-stack limitation, not evidence of a
Task-specific regression or a claim of universal scheduler stack safety.

- Compiler SHA-256: `435204ff829624ffebba7b3515c5b538bcd9548f7edc51d12e6b535451deff6a`.
- Qualification receipt SHA-256: `a8a4754f0fdfb6adb48556ede9e5bba4a61ad5ca1dab3be29ed63da050579bde`.

Run the real primitive-aware compiler through:

```sh
tools/release/test-async-task.sh /path/to/stage2 /path/to/evidence
```

The harness compiles and checks the targets once, runs those exact targets on
the current interpreter and LLVM runtime, compares literal output oracles, and
records source/compiler/observation hashes. It requires the completion-v2 ABI
guard. It has independent command watchdogs; the deliberately long sleeps must
be cancelled well before those watchdogs. Watchdog expiry is a failure, never a
successful timing assertion.

The current 31 contracts cover heterogeneous values and closures, repeated await,
queued/sleeping/waiting/completed cancellation, shared prerequisites, capture
versus fail-fast, nested groups, bounded input ordering, explicit limits,
monotonic deadlines including child joins, scope cancellation, jobs=1 logical
dependencies, escaped/wrong-scope rejection, cold construction, scope process
join, dynamic submission, process outcome distinctions, checked failures,
process cancellation/failure cleanup, queued cancellation, ancestor cancellation,
process queue limits, total deadlines including Task queue time and the dynamic
diamond. The added `Guards.emlf` contract checks ordered function and expression
guards around a spawned, sleeping task and its awaited result, including
unselected failing tasks and predicate panics. Its fixed expected output is
`PASS guards-task-selection`; it is additional coverage beyond the 30-contract
qualification record above. Six contracts are explicitly white-box: self-await,
two live mutually awaiting fibers, injected primary-plus-cleanup failures, delayed cleanup after
primary or parent cancellation (including recovery wrappers), and synchronous ancestor
stop visibility before its queued notification runs, and root cancellation
signalling and joining a suspended sibling. For those only, the
harness copies the scheduler source and removes its export restriction. The
production module and all three public-facing suites keep all constructors hidden.
Five compile-negative fixtures cover public/internal constructor access and
mixing a numeric fiber with a string consumer.

The separate packaged-consumer gate also passed on Linux on 2026-10-23:
`tools/release/test-async-package.sh COMPILER MANAGER OUTPUT-DIRECTORY` compiled
real `.mlfci` library interfaces, produced native output `42`, replayed an
unchanged build entirely from cache with an identical binary, and rejected six
constructor-access attempts plus one mixed-fiber misuse through the cached
interfaces. Its 12 commands completed in 201 seconds;
`.mlf-build/async-production-bootstrap-20261023T0422Z/gates/package/result.json`
records `complete: true`. This is package integration evidence in addition to,
not a replacement for, direct interpreter/native parity.

Primitive-level tests separately cover allocation type safety, callback roots,
GC retention, exactly-once resolution, runtime quotas and timer cancellation.
A seed-only type surrogate is useful during bootstrap but does not count as
Task execution or interpreter/native parity.

### Measured validation cost

Five additional executions of each already-built native suite passed their
literal oracles. On this shared Linux host, with `GC_FREE_SPACE_DIVISOR=8`,
monotonic whole-command wall times were:

| Native suite | Median | Observed range |
| --- | ---: | ---: |
| 13 public Task contracts | 18.514 ms | 16.946–18.735 ms |
| 11 process integration contracts | 182.010 ms | 180.072–186.548 ms |
| 6 white-box contracts | 2.002 ms | 1.993–2.778 ms |

These samples include program startup and, for the process suite, its OS child
fixtures. They are validation execution costs, not isolated no-op scheduling,
process-launch overhead, warm-completion throughput, cancellation-latency, CPU
or peak-RSS benchmarks. There is no universal performance threshold or
cross-platform speed claim.

### Milestones and remaining acceptance work

- **M0:** Generic completion/type safety and the interpreter/native primitive
  bridge have their own [qualified gate](async-typed-completion-gate.md).
- **M1–M2:** Static-runner extraction and the public dynamic process API retain
  separate [native and language gates](async-process.md#validation). The Task
  suite supplements them with real cancellation, joining and queue-deadline
  integration; it does not replace the platform lifecycle matrix.
- **M3–M4:** Typed Task/Fiber, scoped supervision, timers, ordered bounded
  combinators, fail-fast cleanup and shared limits passed the Linux gate above.
- **M5:** The synthetic dynamic-build proof passed, including identical values
  and artifact bytes with jobs=1 and jobs=4. A real incremental build-engine
  adapter, its shared-query policy and atomic publication remain separate work.

The Linux async gates do not replace the broader repository/compiler regression
groups. macOS and Windows MLF Task language parity must be established
separately. The scheduler
tests use deterministic queue/gate arrangements plus real monotonic timers and
real OS process fixtures; a fully injected fake-clock/fake-process model and
exhaustive race exploration are not supplied. Arbitrary coordinator death
during Task execution, independent hard deadline latency, optional
memory-reservation admission, graceful termination escalation and cancellation
at a future build adapter's atomic publication boundary are not claimed.
