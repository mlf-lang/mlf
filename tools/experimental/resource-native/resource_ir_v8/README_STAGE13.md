# Stage13: one closed monomorphic recursive function

This extends only the opt-in shared-source IR8 experiment. It does not change the
runtime ABI, allocator, default v7 route, default coarse placement or fault
policy. Existing ordinary compiler checking, source custody, full type-proof
replay and independent IR8 checking remain mandatory.

## Admitted syntax and limits

One retained recursive group is admitted in the whole fragment, containing one
explicitly annotated function. Its full arrow type must be closed and
monomorphic, and its definition must not capture any external term binding.
Self references are allowed only beneath the introduced function lambda.
Concrete types use the existing admitted type and nominal rules; no function
name or particular nominal family is special.

The ordinary compiler represents the tested annotation using a real application
of a typed passthrough lambda to the recursive lambda. The finite eligibility
check allows at most eight such outer applications. Each wrapper must be closed,
its body must be its own bound parameter, and the parameter/result types must be
the exact checked arrow. The spine must end at an actual lambda matching that
arrow. This test returns admission evidence, never a replacement expression.
Every wrapper remains an ordinary closure/application in the emitted program
and executes normally. There is no beta reduction, identity-specific runtime
path or special treatment of the shared generic function.

Aliases such as `f = f`, recursive data/value bindings, arbitrary or eager
function-valued wrapper applications, captured external values, generic-scope
or polymorphic recursion, mutual recursion, and a second independent or nested
recursive group remain rejected. Existing type/depth/work limits remain.

## Ownership and execution

The planner allocates a typed Repeat-arrow hole in the coarse knot home, retains
a ticket-free owner for self capture, constructs the complete RHS without demand,
and fills the original ticket-bearing hole once with the pending RHS root. It
does not fill directly with the inner lambda or bypass the annotation application.
Only then is the enclosing body constructed/evaluated. Source correspondence
records the exact binder, RHS/body, function/wrapper/self-use paths and
hole/retain/fill/drop instruction joins.

Hole, RHS wrappers and recursive closure use the same group. These internal
edges do not own group RC; normal group retirement clears the edges before
freeing any member. With `--data-groups`, knot RHS and callback construction stay
coarse, then ordinary placement resumes outside that region. No new Below proof
or cross-group knot assumption is invented.

Forcing the filled hole reaches and memoizes the closure through the ordinary
pending application. Recursive applications then use that same registered Code
and self capture through ordinary Force, not direct generated-C recursion or
unrolling. Existing execution fuel and activation/depth guards remain the
termination boundary; this feature does not prove arbitrary recursion terminates.

## Genuine source test

The authored `sumList : IntList -> Int` traverses Cons/Cons/Nil, adds a pending
21 used as both heads, and is called inside the original shared function's
complete Bool/Int use pair. The full ordinary checked capture is retained. Its
original pre-implementation `FRAGMENT` rejection is preserved separately from
later successful replay, not rewritten as an old success.

The first genuine coarse-O0 compilation and run returned Int42 with fault0 and
all seven memory categories balanced at zero. The source-bound observer checks
one hole, the pending RHS application, one memoized recursive closure/Code, three
actual calls and distinct selected factory nodes, one evaluation/memoization of
the shared 21, and the same generic body with both complete type views. IDs come
from actual source maps and event joins, not hardcoded binder hints.

Focused transport tests include malformed annotations/binders/wrappers, generic,
external-capture and second-group rejection, and full custody/proof replay of
the real capture. Planner tests independently check/emitted programs in both
placement modes, validate the knot ordering and preserve old nonrecursive
outputs. The native matrix completed all four coarse/groups by O0/O2
conditions, reusing the known completed first pair instead of running it again.
Complete O0/O2 reports match for each placement, and all 64 copied-report/plan/C
negative controls reject.

One fuel budget was fixed before the fault pair from the actual emitted coarse
entry and runtime tick rules: Fill consumes tick 15, and the following drop
attempts tick 16. At fuel 15, both actual runs report fault 4 with the newly
filled recursive internal cycle still live. Default retention reports 4,456 live
bytes. Explicit terminal destruction retires exactly those 4,456 bytes, with
equal per-category accounting and the same evaluation fault; it is not rollback
or successful evaluation. A copied-report control injecting the real
`close_group` event rejects any claim that an already closed knot group is live.
No fuel-threshold search or additional source capture was used for this pair.

Both placement modes additionally passed ASan/UBSan at O0, with complete reports
identical to ordinary execution; LeakSanitizer was disabled. Six previous SUM
and self-SUM programs were freshly replayed/checked/emitted under Stage13 with
exactly unchanged plans and generated files. Their native reports were retained
Stage12 results, not newly executed targets. This separately preserves the
previous ignored-tail test, which the sum-list traversal does not cover.

The final fresh portable source test also passed: one new ordinary compiler
capture and native Int42 run, followed by two fault calls on that same binary.
Its complete healthy native report equals the earlier coarse-O0 report. The
existing planner regression collection ran 72 tests: 71 passed and one
artifact-dependent placement test skipped; its five native fragments also ran.
The broad module collection passed 292 tests with three existing external-
artifact skips. These are local results; exact-head CI remains pending.
The workflow adds the new planner check and one fresh recursion source case,
for 23 fresh cases in total. It keeps the 60-minute source-job ceiling, all
per-process bounds and all previous jobs; the two extra fault calls reuse the
same compiled binary.

## Reproduce

From a checkout with the existing official GHC 9.14.1 installation and a C11
compiler, the portable source test creates a fresh input/build/output directory.
It runs one fresh ordinary CLI case, then uses that same native binary for the
two fixed fault policies; it does not repeat the compiler capture for each policy:

```sh
python3 -B tools/experimental/resource-native/tests/test_source_v8_monomorphic_recursion.py \
  --ghc /absolute/path/to/ghc --cc cc --output /absolute/new/recursion-results
```

Host planner checks:

```sh
python3 -B tools/experimental/resource-native/tests/test_planner_v8_monomorphic_recursion.py
```

No general MLF support, whole-GC replacement, early reclamation of traversal
allocations or advantage over Perceus is established. This stage adds bounded
recursive computation; it is not a new performance measurement.
