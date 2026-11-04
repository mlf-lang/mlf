# Stage16: ordinary callable captures in recursive functions

The opt-in source route can now capture an ordinary lexical callable owner in
its existing single monomorphic recursive function. The owner may still be a
pending application. Its eventual value may be a concrete closure or a shared
generic callable with a complete instantiated view. This is a source replay and
planner extension; runtime C/H, packet ABI, allocator, CLI flags and defaults are
unchanged from Stage15.

## Bounded contract

An ordinary callable capture has a root arrow whose entire type contains only
arrows and the exact Int/Bool leaves. Full nested arrow contracts are checked,
not collapsed to arity or result type. Open variables, forall types, nominal
leaves and bare Schemes are rejected. Existing limits remain: one concrete
singleton recursive function, its bounded original annotation-wrapper spine,
and at most 64 actual captures including self when used.

Only a nonempty callable inventory selects the new
`closed-scalar-callable-shared-view-captures/1` policy and adds sorted callable
rows containing the original binder, complete type and exact occurrence paths.
Scalar/shared-view-only evidence keeps the old policy and object shape exactly.
Every external RHS occurrence must be classified, and ordinary scalar/callable
owners and complete lexical shared-view pairs form disjoint inventories.

The planner reconciles those rows with its independently computed free owners,
then carries the existing `Reference`, complete type and strict-support fact
unchanged. It does not force the capture, predict Code, reconstruct shared type
arguments from an arrow type, introduce Below facts or rebrand a target as E0.
All ordinary annotation applications remain real graph nodes. Hole/Fill and
publication use the existing checked machinery.

The recursive host is concrete; captured values keep their actual Node/Access
and origin. Handoff events identify owners but do not expose every restored
Access row. The tests combine original proof/type replay, metadata, Code/capture
slots, actual acquisition events and runtime guards. They do not claim a new
per-owner Access trace.

## Two genuine sources

Both sources define IntList, a pending bonus 21 and a recursive function called
first on Nil, then on Cons/Cons/Nil. The final result is 42.

- `pending-step`: the captured `step : Int -> Int` remains an annotation
  application around an actual lambda. That lambda captures bonus and the full
  shared Int view, and computes `sharedId (addInt x bonus)`. Recursion captures
  only the ordinary step owner, not a fabricated direct shared-view row.
- `view-alias`: the annotation application wraps the genuine sharedId<Int> use,
  without a local step lambda. Recursion captures bonus and that ordinary step
  owner. The complete shared-use proof remains at its original outer location.

Actual runtime joins establish one recursive closure with Nil/Cons/Cons/Nil
invocations, one step demand/memo, one bonus evaluation/memo, and the same original
shared node/body invoked at Bool/Int/Int. Initial Nil completes before step or
bonus demand and Int invocation. Allocation and view acquisition may happen
before demand; these are not confused with evaluation.

The two step targets are observed, not inferred from their arrow types. The
first resolves to the actual concrete closure. The alias resolves to the shared
body while preserving its neutral origin and complete Int view.

## Alias publication order and preserved failure

The first alias native target returned 42 with zero live objects, but the original
observer incorrectly required an outer application's memo publication to follow
the bonus memo. The actual Force implementation validates its pending chain in
reverse, then publishes from first to last, and only afterward releases pins.

The corrected observer checks the source wrapper's raw return of bonus, bonus
demand, construction of one READY scalar 21, ordered application/wrapper/bonus
publication of that same scalar, exact pins/depth, and the consumer Force result.
It does not allow pending-node memo targets or simply remove the ordering check.
The ordinary lambda case retains its original stronger ordering assertion.

The old observer, failed matrix and all completed targets are preserved. A new
continuation revalidated all five known pairs before launching only the three
missing alias conditions. No successful target was rerun to hide the failure.

## Local validation

All eight case/placement/optimization conditions pass, with complete O0/O2 reports
identical in each case and placement mode. Across them, 240 copied-report and
72 copied-structure controls reject altered contracts, targets, views, callbacks,
demand/publication ordering, guard caps and memory accounting.

A single coarse fuel 24 pair was selected from the actual entry's tick schedule
before launch: Fill is tick 24; the next drop attempts 25. Both real faults retain
the filled live recursive cycle at fault 4. Default retain leaves 5,568 bytes;
explicit terminal destruction retires exactly those bytes with identical
per-category accounting and the same fault. This is not rollback. No threshold
search was performed.

The final combined planner suite passes all 94 tests with no skips, including five
older native fragments. The transport suite's final broad regression passes 325
with three pre-existing artifact-dependent skips. Both original captures pass
full diagnostic custody/projection/normalization replay. Ten prior source-program
conditions were freshly replayed/checked/emitted with exact plans, reports and
four generated files. Their Stage15 native reports were reused, not relaunched;
all 13 production C/H files and the public driver remain exact.

Four O0 ASan/UBSan conditions pass with LSan disabled. All eight compile/run
records complete with exit 0, empty stderr and no cleanup errors. Complete
reports equal the ordinary baselines without excluding work fields; 120 copied
report and 36 structural controls also pass.

The final portable suite builds two fresh ordinary producers and runs both
source cases through the CLI and native runtime. Both return Int42 with seven
terminal ledgers at zero. Their full reports equal the earlier coarse O0
reports. All 16 recorded outer/build/capture/compile/run processes finish with
exit 0 and no cleanup errors; 60 report and 18 structural controls pass. The
outer source calls take 122.24 and 111.80 seconds, including compiler work, and
are not runtime measurements. No extra fault pair is run by this suite.

The work cap remains 67,108,864. The pending-lambda case consumes 65,683,773 coarse
and 64,818,289 with groups; the alias consumes 55,301,804 and 54,810,515. The first
case remains close to the cap. No work fields are ignored, limits enlarged or
large/deep-recursion claim made. Requested peak bytes are 22,792/21,464 and
20,800/19,856 respectively, not RSS. These source tests are not benchmarks.

## Reproduce

```sh
T=tools/experimental/resource-native/tests
python3 -B "$T/test_module_shared_transport.py"
python3 -B "$T/test_planner_v8_callable_captures.py"
python3 -B "$T/test_source_v8_callable_captures.py" \
  --ghc /absolute/path/to/ghc-9.14.1 --cc cc \
  --output /absolute/new/callable-source-output
```

The portable source runner performs exactly two fresh coarse CLI cases, without
another fault pair. Historical-capture environment variables enable optional
host replay tests; the source runner obtains fresh evidence independently.
CI keeps all prior steps and limits, adding this planner suite and two source
cases for 26 total fresh cases under the existing 60-minute source-job limit.
The prior 22-case run took 47m16s; that is budget evidence, not a guarantee for the
expanded job. Exact-head CI remains necessary after publication.

Generic/mutual recursion, arbitrary nominal-valued captures, a general MLF source
bridge, complete GC replacement and superiority to Perceus remain unqualified.
