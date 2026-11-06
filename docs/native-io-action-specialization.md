# Native IO action specialization

## Reproduced regression

The comparison starts from published PR25 `0a37ad0c81f826be67d83885cfb945c21342160d`
and main `4809f438b3b57ccbe0fa071e90c041f4df958e7c` on the same Linux machine.
Main's compiler is the authenticated `candidate-linux-x64` artifact from
[run 40136159647](https://github.com/mlf-lang/mlf/actions/runs/40136159647),
artifact 12580380357. This is an exact-source candidate, not a claim that its
entire qualification run succeeded. PR25 uses a fresh, authenticated GHC 9.14.1
O2 producer. Compiler-host execution speed is distinct from generated-program
runtime.

The restored four-language adapter does run `Optimize.optimize`, then
`StrictWrappers.optimize`, then LLVM code generation. Both it and the normal
native package builder compile LLVM and the matching runtime at Clang `-O2`.
`--emit-llvm` and `--emit-llvm-gc` are aliases. Neither optional PGO nor the
optional Darwin latency helper is a missing default stage.

The n-body inputs and algorithms are unchanged. The PR25 source needs only the
standard unit spelling migration `IO Unit` to `IO ()`. At 100,000 steps the
first matched three-sample comparison measured main at 0.01116 seconds and
unrepaired PR25 at 3.99169 seconds (medians, one warmup each, rotating sample
order, exact output oracle). These observations are not a platform-independent
speedup claim.

Main emits 16 numeric function definitions; unrepaired PR25 emits 5. The
optimized PR25 erasure already contains the correct `ioBind`, `ioReturn` and
array primitives. The lost information is not an unresolved class selector:
there are lazy lets around action operands and recursive continuations.
`Kernel.eligible` accepts a let only when its RHS is a scalar expression, so
these action-valued lets prevent otherwise eligible IO loops from becoming
native kernels.

The standard do migration intentionally routes discarded statements through
the overridable `(>>)` method. Its default introduces lazy argument bindings
when inlined. Main previously lowered discarded statements directly through
bind. The new frontend behavior is also present on the PR22 base; reverting
that behavior would break legitimate custom `(>>)` instances.

## Restricted repair

The backend exposes a let RHS only when all of these hold:

1. The cached free-use count in its body is exactly one.
2. The actual occurrence is in an action position established by the exact,
   fully applied `PIOBind` primitive with a syntactic continuation lambda.
3. The path does not cross an ordinary lambda, a recursive group, an unknown
   function call, a computed callee, or a partial primitive application.
4. Let RHSs, case subjects, conditions and ordinary primitive arguments reset
   action position. Conditional branches and let/case bodies preserve it.
   Thus a scalar operand under `writeIntArray` or `ioReturn` is not licensed.
5. The existing capture-avoiding substitution freshens copied binders.

There is no class-name, spelling, inferred-Monad-type or IO-instance heuristic.
A bind continuation is invoked once per execution of its action, not globally
once if an action is shared and executed repeatedly. The rewrite moves pure
construction of an IO action into its unique action use; it does not execute an
IO operation, demand an unused RHS, or move an effect ahead of a failed action.
It can reconstruct an action value across repeated executions. Ordinary
multi-use and scalar sharing boundaries remain unchanged.

The kernel eligibility/demand guards, primitive arities, target checker,
source inference and runtime are unchanged. This is not general single-use
substitution and not a shortcut for the type-inference solver.

## Validation

The durable focused driver is `tools/shared/test_io_action_sharing.py` and the
independently authored output/admission controls are
`tools/shared/test_io_action_sharing_controls.py`.

The driver uses authenticated producer modules without recompiling or changing
them. It compiles only its test Main and independent C transports. Source cases
pass the production and frozen target checkers, serialization/parse checks,
identical emitted LLVM before/after serialization, and original, serialized,
and optimized-erased interpreter executions. Raw shape checks exercise the
precise admission boundaries. No wall-clock threshold is a correctness oracle.

For an authenticated producer receipt:

```
python3 tools/shared/test_io_action_sharing_controls.py
python3 tools/shared/test_io_action_sharing.py \
  --build-receipt BUILD/receipt.json --output NEW_OUTPUT
```

To additionally compile and execute every emitted program natively, provide
Clang and a BDWGC prefix containing `include/` and `lib/libgc.a`:

```
python3 tools/shared/test_io_action_sharing.py \
  --build-receipt BUILD/receipt.json --output NEW_NATIVE_OUTPUT \
  --clang /path/to/clang --gc-prefix /path/to/bdw-gc
```

Interpreter/LLVM checks without that option are not native-execution evidence.
The benchmark comparison and final validation results are recorded separately;
a successful scratch IR experiment is not a release-qualified compiler.

## Ground-evidence sharing regression

A second regression is independent of IO-kernel eligibility. Qualified local
bindings are planned before their predicate argument types are solved. A local
String value such as `text = concatString "prefix" source` can consequently be
represented as a function of an `IsString String` dictionary, even though every
use supplies the same instance. Repeated applications recompute the value. In
regex-redux this reconstructs the cleaned input inside each pattern-counting
callback, instead of sharing the original cleanup.

The backend repairs this without changing type inference, instance selection,
or typed source/erasure equality. Before ordinary let inlining, it specializes a
nonrecursive let-bound lambda only if:

- There is at least one free use of the binding. Single-use wrappers must
  normalize immediately too, so enclosing shared values can see their arguments.
- Every occurrence is an exact, fully saturated call. Bare, partial and
  overapplied occurrences reject the transformation.
- Every call has precisely the same complete vector of variable identities.
- Every argument variable is free at the original binding boundary and is not
  the binding itself. Inner lambda, let, recursive and case binders therefore
  cannot escape their scope.

The original lazy binding is retained. Capture-avoiding substitution immediately
contracts its lambda parameters with that common vector of outer variables,
without demanding any argument or result. All accepted calls become references
to the binding. Immediate contraction is important: deferred beta applications
would let an enclosing small-lambda inliner duplicate the computation first. There is no
runtime cache, type/class-name heuristic, literal matching, or specialization
when evidence differs between calls. The transformation shares a pure result or
an IO action value; executing the same action twice still executes its effects
twice. Fresh-array, unused-bottom, and distinct-class-instance source cases are
included in the native semantic driver. Independent shape controls additionally
check binder identities, complete use accounting and free-variable preservation.

The expanded driver retains the original 19 IO shape checks and now runs 18
source cases through all three execution forms and, when requested, native
execution. A successful shape test alone does not establish runtime improvement;
matched full-program measurements remain a separate gate.

The separate `tools/shared/test_common_calls.py` gate runs 23 independent
checks: 20 shape/admission/identity checks plus three raw-term lazy semantics
checks in original, explicitly contracted, and fully optimized forms. Each
semantic check first requires that the specialization was admitted, preventing
a skipped rewrite from masquerading as a passing transformation test. This gate
is interpreted/structural evidence, distinct from the 18 native source cases.

## Final matched validation (2026-10-25)

The frozen final optimizer SHA256 is
`52599affb59dcc421c9cb62d39c98e3c92b88d480687f8ce625d1afa0344a610`.
Its authenticated GHC 9.14.1 O2 producer receipt is
`a1cd0a9c56bb5e437ea75beb6e2318ab5b3c663908715991b0cb79bd1c03518e`;
the emitted compiler executable SHA256 is
`759028e30fcf71299a452c450b19d9c9c3d0a8fc85522306492bf4f13f79bdee`.

On these exact compiler bytes, all 23 independent common-call checks passed.
The separate IO/source driver passed its 19 shapes, 18 source cases through
original/serialized/optimized-erased interpretation, production and independent
target checks, identical serialized LLVM, and all 18 native executables with
exact output/diagnostic checks. Immutable producer and test inputs were
reauthenticated afterward. The source/shape stage took 370.53 seconds under its
unchanged 600-second limit. Release metadata and the 17 harness mutation controls
passed. Broader O2 direct/frontend, default/framework, Figure12, managed-evidence
and field-layout gates passed on the preceding shared-value candidate; those
are explicitly **not** relabeled as exact-final validation. Exact-head O0/O2 CI
is a separate required follow-up. No full native/bootstrap corpus is claimed.

After all local CPU-heavy validation stopped, the original ten-workload suite
ran with MLF main, repaired MLF, C, Rust and GHC at its original input sizes.
All 50 combinations, 150 independent compilation samples and 150 rotating runtime
samples passed their output oracles and immutable input/product checks. One
excluded warmup preceded each binary; no workloads or timeouts were reduced.

Nine guest-runtime medians were between 0.971 and 1.060 times main. Examples:
n-body was 0.202193 versus 0.200748 seconds, reverse-complement 0.359643 versus
0.357809 seconds, and Mandelbrot 0.679782 versus 0.671563 seconds.
Regex-redux remains slower: 159.216416 versus main's 123.747441 seconds
(1.2866 times), while C took 0.440897 seconds. Thus the major regressions are
repaired, but complete runtime parity and removal of the longstanding large
MLF-versus-C regex gap are **not** established.

Compilation measurements compare a native CI-built main compiler with the GHC
O2 candidate producer, and are not a controlled compiler-host optimization
comparison. Cross-language runtimes also compare selected implementations, not
isolated language quality. No memory-performance conclusion is drawn.

The regex diagnosis uses exact primitive scan counts and optimizer-phase
inspection to establish that repeated input cleanup was removed. C helper
entry counts such as `mlf_thunk_new` are not total allocation counts, because
inline fast paths bypass them; they do not prove the remaining runtime cause.
