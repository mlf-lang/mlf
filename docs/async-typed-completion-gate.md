# Typed completion representation gate

## Current decision

The allocation/generalization experiments pass, and the actual opaque primitive
implementation is now present. Primitive IDs 83–94 cover typed completions,
scoped resumptions and cancellable monotonic timers. Compiler kind/signature
and module tables, independent target checking, native ABI/cache guards and a
persistent interpreted IO store are updated together.

Verified locally so far:

- The updated interpreter module and its complete import graph typecheck with
  the released seed, using the explicit stage-1 host bridge.
- The real native representation passes **1,330 checks and 133 callbacks**,
  including deterministic timer ordering, bounds, cancellation and root removal.
- A separate **real native primitive/IO-driver integration test passes 20 checks
  and 5 callbacks**, with forced GC, large integers, String captures, reused cold
  allocation, duplicate resolution, non-reentrant dispatch and timer wait/cancel.

The complete new source/native/interpreter parity runner is
`tests/fixtures/async-completion/check.sh`. Its execution against the bootstrapped
stage-2 compiler is still pending at this checkpoint. Native C integration and
source typechecking do not substitute for this remaining gate. The original
four-positive/ten-negative type-only experiments remain recorded below as
historical evidence; they are not the actual primitive suite.

## Reproduction and provenance

Experiments used the official Linux `emlf 0.3.0` binary:

- Release source commit: `ad299fa17296945ca0cf34d6fc4ac35dc5eb0924`
- Binary SHA-256, verified against the extracted release's CHECKSUMS:
  `064e9ee2d5e9a8df38a8d3a56c0595e8aa7757a41d63c46e818c4cd24af0d3a6`
- Source checkout baseline: `696f596a95fe5f5d3fae4c2aa5567fd791a16b25`,
  with the process-utility changes under development in the same worktree.

From the repository root:

```sh
EMLF="$PWD/.mlf-build/seed-linux/mlf-0.3.0-linux-x64/libexec/emlf" \
  tests/fixtures/async-gate/check.sh
```

Observed result: **4 accepted interface fixtures, 10 rejected fixtures, one
accepted deliberately wrong-contract counterexample, and 2 executable
interpreter probes**. Every accepted fixture is emitted as xMLF and checked
again with `--check`. The counterexample is never executed.

The two executable probes were also emitted with the same seed's `--emit-llvm`
and linked against its released runtime with Clang 19, GMP and BDWGC. Their
native output exactly matches the checked-in `.expected` files.

Build the separate live native representation proof against the current runtime:

```sh
clang -O2 -std=c11 -Wall -Wextra -Werror \
  -I "$MLF_GC_PREFIX/include" tests/native/completion_cell_tests.c \
  runtime/mlf_runtime.c "$MLF_GC_PREFIX/lib/libgc.a" -lgmp -lm \
  -o /tmp/completion-cell-tests
/tmp/completion-cell-tests
```

Observed result: **1,330 checks, 133 callbacks passed**. This command uses the
normal compact-BDWGC runtime, including real `MlfValue` closures and payloads.

## What the type experiments establish

The hypothetical allocation interface is:

```text
newCompletion : forall a. IO (Completion a)
resolve       : forall a. Completion a -> a -> IO Unit
observe       : forall a. Completion a -> IO a
```

`Gate.CompletionInterface` is explicitly a **type-only model**. Its allocator
is `panic`, its invariant representation is hidden by the module export list,
and none of its clients is executed. It is not a fake mutable implementation.
It allows real inference/elaboration/independent-check experiments without
claiming a new runtime primitive already exists.

The compiler accepts consistent Int use, aliasing at the same type, two
separate executions of one generalized allocation action at Int and String,
and a cell whose fixed payload is `forall a. a -> a`. Generated xMLF fixes a
consistent bind parameter to `Completion Int`.

It rejects resolving the same cell with Int and observing String, an Int-only
function observed at String, alias widening, explicitly generalizing the bound
cell, and overwriting a polymorphic-function cell with an Int-only function.
One-shotness alone would not prevent these attacks: the mixed-value attack
needs only one write.

**Known diagnostic gap:** the imported explicit polymorphic let-alias attack
fails closed with `Elaboration: unbound type variable ...` on the release seed.
Its inline equivalent fails earlier with `Inference: cannot raise a protected
type variable`. The fixture runner records this specific alternative; it does
not count an arbitrary parsing or module-loading failure as a typing success.
This must be investigated in the real primitive gate. No executable xMLF is
produced for that rejected program.

The deliberately wrong signature is:

```text
newCompletion : IO (forall a. Completion a)
```

With an explicitly polymorphic bind parameter, MLF accepts resolving that
returned cell at Int and observing it at String. This is the **wrong contract**,
not a compiler soundness counterexample: no inhabiting mutable implementation
is supplied. It demonstrates exactly why the allocation action may generalize
but an allocated cell must not. Executing a reused allocation action must also
allocate a fresh cell each time; cold action construction must not allocate or
memoize a shared result cell.

## Why ST is useful evidence but cannot be reused as IO storage

`STArray s a` is opaque and region-indexed. `runST` requires a state action
polymorphic in its region; IO cannot execute ST actions. The negative fixtures
reject directly binding ST allocation in IO, escaping an array, escaping a
reader closure, and embedding an ST read in an IO callback.

The executable `st-one-shot.emlf` implements real generic one-shot storage
inside one ST region, resolves separate Int/String cells, rejects a duplicate
resolution, and observes the retained integer twice. Both backends print:

```text
41
ready
41
1
0
```

This validates the nearby generic mutable representation and sequencing model.
It does not create a bridge from ST to IO. A scheduler that interacts with child
processes needs an IO-owned store or a new effect-aware interpreter state.

`cps-heterogeneous-queue.emlf` separately runs Int and String tasks through one
homogeneous queue of `IO Unit` resumptions. Each resumption captures its own
typed continuation; no ID-to-value conversion or unchecked universal value is
used. It proves a small CPS representation, not suspension, fibers, scopes,
timers or a full scheduler.

## Live native storage and ownership proof

`runtime/mlf_completion.h` is the private header-only representation used by the
real primitive driver. The additional `tests/native/async_completion_primitives.c`
test exercises IDs 83–94 through one ordinary `mlf_run` invocation.

- Scope, cells and subscriptions are scanned BDWGC allocations. Stored results
  and captured continuations are ordinary lazy `MlfValue *` roots.
- Each cell transitions from pending to resolved at most once. Resolution
  commits its result before enqueueing callbacks and allocates nothing.
- Callback capacity is reserved at registration, including unresolved waiters,
  ready callbacks and dequeued-but-unconsumed callbacks. Resolution therefore
  cannot fail midway because a ready queue became full.
- Retained cell capacity is bounded separately. Completed cells retain their
  outcomes until scope closure; repeated observation returns the same value.
- Registration after resolution enqueues a callback. Registration and
  resolution never run user code. A coordinator explicitly dequeues and takes
  the callback, then runs its ordinary MLF IO application.
- Taking a callback is its execution-start boundary. The coordinator must
  invoke it immediately, without interleaving scope closure. Already executing
  IO is not preempted. Full runtime integration needs a guarded driver enforcing
  this sequencing rather than relying on callers to do it.
- Unsubscribe removes pending, ready or claimed work and clears its roots.
  Consumed nodes are unlinked, so a bounded queue does not retain an unbounded
  history of callbacks.
- Idempotent scope closure clears results and pending/ready/claimed callback
  roots. Stale and wrong-owner operations fail. Reachable cells are never
  manually freed; a cell's owner pointer also prevents identity reuse while
  that handle is reachable.
- There are no native worker threads and no callback execution from a foreign
  thread. This prototype is deliberately single-coordinator, not thread-safe.

The test forces collection before and during dispatch, retains a large GMP
integer and String with captured closures, verifies lazy poison is never forced,
checks duplicate completion, queue bounds, FIFO registration, late registration,
claimed-callback cancellation, root clearing, owner mismatch, stale handles,
and callback-driven resolution without reentrant invocation.

It checks roots are explicitly cleared; it does **not** assert deterministic
collection timing or finalizer behavior under a conservative collector.

## Implemented primitive slice

The narrow integration uses opaque `AsyncScope`, `Completion a` and
`AsyncSubscription`. Its implemented signatures are:

```text
asyncScopeNew             : Int -> Int -> IO AsyncScope
asyncScopeClose           : AsyncScope -> IO Unit
asyncNewCompletion        : forall a b. AsyncScope -> (Completion a -> IO b) -> IO b -> IO b
asyncResolveCompletion    : forall a. Completion a -> a -> IO Int
asyncReadCompletion       : forall a b. Completion a -> (a -> IO b) -> IO b -> IO b
asyncSubscribeCompletion  : forall a. Completion a -> (a -> IO Unit) -> IO AsyncSubscription
asyncSubscriptionStatus   : AsyncSubscription -> IO Int
asyncCancelSubscription   : AsyncSubscription -> IO Int
asyncStep                 : AsyncScope -> IO Int
asyncEnqueue              : AsyncScope -> IO Unit -> IO AsyncSubscription
asyncDelay                : AsyncScope -> Int -> IO Unit -> IO AsyncSubscription
asyncWait                 : AsyncScope -> Int -> IO Int
```

CPS allocation and observation supply typed fallback actions for full/closed
allocation or unavailable results. They need no unchecked conversion and fit
the existing maximum three-argument primitive ABI. A rejected subscription
retains its status but no callback. Direct enqueue avoids allocating a retained
result cell for every scheduler yield. Every queue belongs to an explicit scope,
so nested runs do not consume one another's work.

Internal status numbers follow the representation: 0 OK, 1 EMPTY,
2 ALREADY_RESOLVED, 3 CLOSED, 4 FULL, 5 WRONG_OWNER, 6 CONSUMED, 7 NO_MEMORY;
the guarded driver returns 8 BUSY for reentrant stepping/waiting of one scope.
The eventual public library should turn these into named error/outcome values.

Producer operations must remain behind the public `Fiber a` abstraction.
Primitive names currently enter the compiler's global primitive catalogue, so
merely calling a source module `Internal` does not establish capability privacy.
An opaque fiber must hide its underlying completion. If public consumer
endpoints are exposed directly, add a distinct opaque resolver capability and
prove its allocation/signature rather than exposing a consumer-to-producer cast.

## Integration inventory and remaining gates

1. **Kinds, signatures and independent checking:** primitive constructors,
   names/codes/signatures/arities, opaque kinds and `Bootstrap.Module` builtin
   names are wired. New source negatives and direct-target forged-type,
   wrong-argument and wrong-kind negatives are in `async-completion`. The new
   runner requires rejection in the expected phase and checks invalid target
   rejection by checking, execution and LLVM emission.
2. **Interpreter:** IO binds now thread a persistent `RAsyncStore`. It retains
   lazy `Either String RValue` payloads and ordinary resume closures. Cancellation
   removes registrations, closure drops all cell/ticket roots, and closed scopes
   are deleted. A missing previously-issued scope ID means CLOSED, so repeated
   scope creation/closure does not grow a tombstone map. IDs remain internal;
   no source-level Int-to-typed-value operation exists.
3. **Native runtime:** appended opaque wrapper/action tags retain compact ABI
   numbering. Three-argument actions have a traced argument environment. The
   existing IO continuation loop dispatches callbacks and clears the same-scope
   reentrancy guard through a completion continuation, without recursive
   `mlf_run`. A BUSY step/wait leaves timer and ready ordering unchanged.
4. **Timers:** delay registration is nonblocking and reserves normal callback
   quota. The timer queue is sorted by monotonic deadline, stable for ties.
   Cancellation unlinks timers and clears roots. Step/wait mature due timers
   after existing ready work. Wait runs no user code; -1 waits for the earliest
   timer, 0 polls, and nonnegative bounded waits stop at their limit. It returns
   EMPTY immediately with no ready work or timers. Each host pause is at most
   1000 ms and never later than the nearest deadline. The interpreted clock/pause
   bridge transfers metadata only, using process transport 82. Precision is
   milliseconds, not a preemption or hard real-time guarantee.
5. **LLVM/ABI/cache:** generated entries require
   `mlf_require_async_completion_v2_abi`; cache keys include `completion-v2`.
   The released compact ABI and primitive-82 guard remain for bootstrap inputs.
6. **Remaining evidence:** run the real stage-2 source suite, compare both
   interpreter entry paths with native output, and qualify the higher-level
   Task/Fiber structured lifecycle independently. The current C proofs cannot
   establish inference safety or whole-Task cancellation on their own.
