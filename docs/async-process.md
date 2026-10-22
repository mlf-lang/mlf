# Structured asynchronous processes

`libraries/mlf-async` provides `Async.Process`: dynamic subprocess execution
owned by a lexical IO scope. It is independent of package resolution, query
identity, dependency caches, and artifact publication. The coordinator is one
MLF thread; CPU-parallel work runs in isolated OS processes.

This is the process increment of the async utility. It does not expose generic
`Task a` or `Fiber a`, execute arbitrary MLF functions on threads, or make a
blocking IO operation cooperative. The typed completion work and its evidence
are described in [the representation gate](async-typed-completion-gate.md).

## API

Import `Async.Process` and `Bootstrap.Types`. Errors use the existing
`Either AsyncError a`; a subprocess's nonzero exit is an ordinary outcome.

- `withProcessScope options body` creates a scope, invokes its IO callback, and
  joins its children before returning. A callback `Left` cancels and joins the
  children. Cleanup failure is retained alongside an existing primary error.
- `submit scope spec` copies the request and returns an opaque handle. It can
  launch immediately if capacity is available, or enqueue without blocking for
  a free process permit. Later requests need not be declared in advance.
- `poll scope` returns the next event if one is available.
- `waitNext scope wait` waits for and consumes one completion event.
- `awaitProcess scope handle` waits for one outcome. Repeated await returns the
  same outcome; it neither repeats execution nor consumes the completion event.
- `awaitWithin scope handle wait` also bounds the wait. A wait timeout does not
  cancel its child.
- `cancel scope handle reason` accepts cancellation and joins that child.
- `requestCancel scope handle reason` accepts cancellation without waiting for
  cleanup. Keep polling or awaiting the handle; its terminal outcome is not
  published until cleanup completes. Cooperative task schedulers use this form.
- `cancelScope scope reason` stops admission, cancels queued and running work,
  and joins cleanup. Outcomes remain inspectable until scope closure.

`ScopeOptions jobs maxPending maxRetained` bounds running processes, queued
submissions, and the total accepted handles retained for repeated await.
Limits are per scope; nested or independent scopes do not share a global
process budget. `defaultOptions` is `ScopeOptions 4 64 1024`. A full queue or exhausted retained
capacity returns an error; submission never waits while holding capacity a
child needs. Completed outcomes are not silently evicted. Scope IDs are never
reused during a coordinator process's lifetime.

A `ProcessHandle` carries scope and generation identity internally. Both types
hide their constructors. Handles can escape as ordinary values, but any use
after scope closure or with another scope is rejected at runtime. There is no
claim of compile-time scope non-escape.

## Process specifications and outcomes

`command executable arguments stdoutFile stderrFile` is the common constructor.
Arguments exclude `argv[0]` in this helper and remain separate strings; no shell
parsing occurs. Supply a shell explicitly if that is what the command requires.
Stdout and stderr log paths are required by the MLF API, so large output does
not accumulate in coordinator memory. Equal paths share one descriptor. Log
files have no imposed disk-size limit; manage retention and disk capacity as
part of the calling application's policy.

The full `ProcessSpec` also accepts a working directory, stdin path, inherited
or replacement environment, running timeout, and total timeout. Relative
stream paths are relative to the child's directory. Timeout values are
milliseconds; zero disables the corresponding deadline. The total timeout
includes time in the queue; the running timeout begins on launch.

The outcome constructors distinguish:

- `Exited code cleanupError`, including nonzero exit codes
- `LaunchFailed platformError cleanupError`
- `Cancelled reason cleanupError`
- `TimedOut cleanupError`

The cleanup field is zero on success. A launch failure is distinct from a
program deliberately exiting 126 or 127. Cancellation accepted for unfinished
work cannot later become a successful exit. A terminal result already committed
before cancellation remains unchanged. Each completion event is delivered at
most once, independent of repeated await.

## Servicing and cleanup guarantees

Supervisor calls service admissions, process completion, and monotonic timers
for every live scope, including while awaiting a child in another scope.
Arbitrary MLF computation between calls can delay that servicing. There is no
preemption or hard deadline-latency guarantee. Expiry starts cancellation;
cleanup may extend the time before the call returns.

On POSIX, every worker has a session and a guardian whose control pipe is owned
only by the coordinator. Coordinator death, including SIGKILL, closes that pipe
and triggers containment cleanup. Linux guardians additionally reap orphaned
descendants as subreapers. Processes must not deliberately escape containment
with `setsid`. On Windows, suspended launch and a noninherited
`KILL_ON_JOB_CLOSE` Job Object preserve ownership before the child can execute.
This does not claim universal containment of intentionally detached descendants.

Normal scope exit joins all work. Explicit scope failure and cancellation
cancel then join. Native shutdown also closes outstanding scopes. Output uses
files rather than undrained capture pipes, avoiding the wait-before-drain
problem for large stdout and stderr. The native API bounds aggregate copied
submission metadata and retained outcomes separately from child resources.

Subprocess cancellation uses forceful OS termination (SIGKILL containment
cleanup on POSIX, Job Object termination on Windows). It does not currently
offer a graceful signal/timeout escalation phase. Cooperative cancellation of
MLF tasks is a separate scheduler contract.

## Compatibility

The static `mlf-build-runner` version-1 DAG protocol remains available. It uses
the same extracted launch, poll, cancellation, containment, and measurement
backend as dynamic scopes. Its fail-fast build policy remains in the adapter;
it is not imposed on ordinary `Async.Process` nonzero exits.

The dynamic native protocol is versioned separately and rejects unsupported
requests. New primitive-bearing compiler output uses an explicit runtime ABI
guard. A released seed cannot interpret the new primitive; the bootstrap bridge
must be used and its limitations kept visible until the new compiler is built.
See `bootstrap/RUNTIME.txt` for the primitive contract and bootstrap details.

## Validation

`tests/native/build_runner_tests.c` retains the original 22 static protocol and
lifecycle scenarios. `tests/native/process_supervisor_tests.c` covers dynamic
admission, single-job progress, queue and retention limits, environment/argv
ownership, repeated await and event delivery, launch failures, cancellation,
deadlines, logs, and forced owner death. The same native suite is required on
Linux, macOS, and Windows CI.

Run the MLF-level suite with
`tools/release/test-async-process.sh COMPILER OUTPUT-DIRECTORY` after qualifying
the stage-2 compiler with `scripts/bootstrap-async.sh`. It exercises the public
API through the checked interpreter and native runtime with literal
expectations. Output must be a fresh directory. The
compile-positive and compile-negative completion fixtures are separate from
runtime/callback/GC qualification; passing them is not proof of a generic task
scheduler.

A future build-query adapter must own deduplication, shared prerequisites,
cache validity, and atomic artifact publication. Cancelling one consumer must
not cancel a shared prerequisite still needed by another consumer. This process
library intentionally provides no build-query cache or publication operations.
