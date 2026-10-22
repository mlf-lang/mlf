# Typed completion representation gate

## Decision at the first checkpoint

The allocation/generalization gate **passes the focused source experiments**.
MLF can express an IO allocation action whose result has one fixed element type,
including a genuinely polymorphic function as that one element type. No change
to inference/generalization semantics is indicated by these experiments.

A **live native representation prototype also passes** one-shot, bounded queue,
forced-GC, lazy payload, owner invalidation and non-reentrant dispatch tests.
Neither result means `Task a`/`Fiber a` is implemented. The new opaque primitive
integration and interpreter/native equivalence gate remain pending at this
checkpoint. The shipped process API is monomorphic.

This is a positive feasibility result, not an impossibility claim and not a
soundness proof for an unimplemented scheduler. The next slice is real opaque
completion primitives plus a persistent interpreted IO store, followed by
mixed-type source execution on both backends.

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

Observed result: **1,314 checks, 133 callbacks passed**. This command uses the
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

`runtime/mlf_completion.h` is a header-only internal prototype. It adds no
public primitive IDs, compiler types, runtime value tags or library API.

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

## Concrete next primitive slice

The proposed narrow integration uses opaque `AsyncScope`, `Completion a` and
`AsyncSubscription`. Names below are proposed, not available in this checkpoint:

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
```

CPS allocation and observation supply typed fallback actions for full/closed
allocation or unavailable results. They need no unchecked conversion and fit
the existing maximum three-argument primitive ABI. A rejected subscription
retains its status but no callback. Direct enqueue avoids allocating a retained
result cell for every scheduler yield. Every queue belongs to an explicit scope,
so nested runs do not consume one another's work.

Proposed internal status numbers follow the prototype: 0 OK, 1 EMPTY,
2 ALREADY_RESOLVED, 3 CLOSED, 4 FULL, 5 WRONG_OWNER, 6 CONSUMED, 7 NO_MEMORY;
a guarded driver additionally needs 8 BUSY for reentrant stepping of one scope.
The eventual public library should turn these into named error/outcome values.

Producer operations must remain behind the public `Fiber a` abstraction.
Primitive names currently enter the compiler's global primitive catalogue, so
merely calling a source module `Internal` does not establish capability privacy.
An opaque fiber must hide its underlying completion. If public consumer
endpoints are exposed directly, add a distinct opaque resolver capability and
prove its allocation/signature rather than exposing a consumer-to-producer cast.

## Required integration and remaining gates

1. **Kinds, signatures and independent checking:** append primitive constructors
   in `libraries/mlf-foundation/Bootstrap/Types.emlf`; names/codes/signatures/
   arities in `libraries/mlf-language-core/Bootstrap/Primitive.emlf`; opaque
   kinds in `libraries/mlf-language-core/Bootstrap/Data.emlf`. The xMLF parser,
   checker and type machinery consume these shared tables. Add direct-target
   rejection tests for forged types, wrong type arguments and wrong kinds.
2. **Interpreter:** `libraries/mlf-interpreter/Bootstrap/Runtime.emlf` currently
   has a persistent `RSTStore` only for ST, while IO `runAction`/`perform` carries
   no arbitrary-value store. Add internal state-threaded IO execution holding
   completion scopes, lazy `Either String RValue` results, subscriptions and
   the ready queue. Preserve the existing external entry wrappers. IDs inside
   this checked interpreter are implementation handles, never a source-level
   conversion from Int to `Completion a`.
3. **Native runtime:** append opaque wrapper/action tags without renumbering
   the compact ABI in `runtime/mlf_runtime.c`; add arities, lazy action creation
   and IO-driver dispatch. Three-argument actions require a traced argument
   environment, as ST actions already use. Drain callbacks through the current
   IO continuation loop, with an explicit same-scope reentrancy guard and
   completion marker. Do not recursively call top-level `mlf_run`, which runs
   global cleanup on exit.
4. **LLVM/ABI/cache:** ordinary primitive lowering can use the generic arity
   paths, but update the ABI guard and cache version in
   `libraries/mlf-llvm/Bootstrap/LLVM.emlf`, the runtime header, and any primitive
   inventory tests. Verify old generated objects cannot silently use new IDs.
5. **Bootstrap:** `scripts/bootstrap-async.sh` already isolates the released-seed
   ProcessHost bridge. A state-threaded interpreter can represent completion
   values without calling new completion primitives in the host, preserving a
   released-seed build path. Any new native monotonic-time/sleep host operations
   for timers need an explicit compatible bridge, never fabricated timestamps.
6. **Actual parity:** execute mixed Int/String and polymorphic-function cells
   through the new public primitive signatures on both backends; repeat actions;
   check cancellation/close races, cold construction, late callbacks, bounded
   queue reuse, lazy values and forced collection. Re-run compile-negative and
   independent-target tests against the new opaque type rather than only the
   interface model. Resolve the imported alias diagnostic discrepancy.
7. **Task layer:** only then add fibers, the cooperative scheduler, scope failure,
   await/cancellation, cycle checks, timers and combinators. Task callbacks must
   stay on the coordinator and bounded queue admission must return explicit
   failure. Primitive storage proof alone does not establish these invariants.

The exact unfinished gate is **checked source-to-native/interpreter integration
of the new storage and guarded callback driver**, not a demonstrated type-system
limitation. The focused representation tests provide a concrete route forward.
