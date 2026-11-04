# Stage21: complete nominal shared type arguments

**Local validation complete:** both inferred sources pass fresh checking,
independent replay and native execution. The finite native matrix, sanitizer,
nominal guard and fault-retention checks below also pass. Exact-commit CI remains
a separate pending result; these checks qualify only this bounded experiment.

The opt-in shared-source route now accepts complete type vectors whose entries
are Int/Bool or exact registered, parameter-free DATA/SUM atoms. Every coordinate
is retained, including unused coordinates. This extends source normalization,
replay/planning, host metadata, packet admission and real instantiation checks.
ABI, allocator, placement, fault defaults and work limits remain unchanged.
There is no general MLF, GC replacement, Perceus or performance claim.

## Source and proof boundary

The standalone shared producer has a local nominal type-beta rule. Legacy
`ResourceExport.closedArgument`/`closedApplyPrefix`, export/2, v7 and the default
compiler route are unchanged. Real whole-source K/kind checking remains
mandatory. A nominal substitution argument must be an exact zero-parameter
checked declaration atom, not an arrow, a name hint or a structurally similar
layout. The producer emits diagnostic evidence; it does not grant runtime
permission to arbitrary JSON.

Normalization uses `shared-rank1-callable/2` if and only if an actual direct
beta step uses an eligible nominal argument. Otherwise it retains `/1`, even
when ordinary shared uses have nominal arguments. Both implementations derive
that choice and the complete ordered certificate. False `/1` or `/2` claims
reject. Leftmost-outermost traversal, full-prefix substitution, raw witnesses,
root alpha equality, per-step/final ordinary erasure and declaration equality
remain required. Ordinary applications and annotation/coercion wrappers are not
beta-reduced, replaced or cloned.

Independent raw inference checks/selects supported declarations before nominal
normalization. Every nominal coordinate, including a dead one, is reconciled
with the exact canonical published declaration row afterward. Normalization and
use classification cannot select another family or unfold a type. Binder,
declaration, full-vector and occurrence identities remain exact; one generic RHS
is shared across its uses. Vector ordering is canonical for the actual atoms,
including escaped/Unicode names, rather than a shortened result-type key.

## Host, packet and runtime checks

A CLOSED type tag alone does not authorize an argument. Host declaration and
metadata verification require a registered intrinsic, DATA or SUM atom. Packet
and runtime nominal branches authenticate the exact Type, LEGACY ShapeBinding,
unscoped ShapeTyping, ShapeSpec and Representation; SUM also joins its exact
FamilyTyping/FamilySpec. Early Env checks do not replace later shape, field,
descriptor, Access or Transport checks. Source parameter-freedom is established
by source checking, not inferred from packet rows that lack source parameters.

Neutral generic origins, complete closed use environments, actual INSTANCE
capsules/activations, projected full types and Down/Access contracts remain
intact. Captured shared views carry their original full vector and owner;
nominal identity is not reconstructed from a result type. Generic principals
still admit only the existing intrinsic/rigid/Repeat-unknown-arrow forms.
Nominal operations or atoms in retained generic principal code remain rejected.

This does not add arrow-valued, open, foreign or parameterized type arguments,
partial/bare Scheme uses, generic/mutual/value recursion or broader field rules.
DATA field arrows remain scalar-only; callable/cross-family SUM fields and
recursive DATA remain excluded. SUM cases still return Int. Existing type,
vector, declaration, capture, depth and work bounds are unchanged.

## Genuine source cases and observations

Both inputs use real SharedPoly imports and inferred shared uses:

- Identity passes one original `IntList` owner with a pending head through the
  shared identity, then uses its head twice. The Bool and nominal uses retain
  one full shared definition.
- Curried constant uses both `[Bool, IntList]` and `[IntList, Bool]`. An ordinary
  consume closure retains the complete nominal view. The returned curried
  INSTANCE retains the actual first argument and is used after its creator
  returns. The unused nominal second argument remains an allocated pending
  application and stays unforced; allocation is not demand.

The original identity capture stopped at USE. The original inferred curried
capture stopped at DIRECT because the old producer retained its nominal beta
wrapper. A separately annotated control reached USE, but is diagnostic only and
cannot replace the inferred fixture. All three historical captures/refusals
remain unchanged. Newly built producers on the unchanged inferred inputs pass
full custody, original/resolver joins and independent normalization: identity
uses `/1` with two steps; curried-const uses `/2` with four steps. Four coarse/
groups host plans are checked and emitted. Native observations separately bind
these source identities to the original nominal owner, both complete vectors,
the captured upstream view and the returned curried children. The shared pending
bonus is evaluated once. Access evidence comes from exact metadata, stored slots
and guarded handoffs; there is no per-owner Access event trace or separately
observed frame-exit event.

## Completed local checks

- Existing bounded host suite: 475 passes. With retained artifacts supplied,
  the new metadata, source replay and planner suites pass 12, 16 and 10 tests.
  The CI-form run without optional artifacts passes all 12 metadata tests;
  source replay runs 16 tests with 13 passes and three skips; planning runs
  10 tests with eight passes and two skips.
- Existing transport: 206 tests, 199 passes and seven optional-artifact skips.
  Combined planners: 134 tests, 128 passes and six optional retained/native
  skips. Existing CLI host tests pass 42; the original 20-test planner suite
  passes, including its five native subcases. Skips are not executed checks.
- Legacy native O0 and O2 each pass 22 conditions, with complete reports and
  work fields equal to Stage19 and equal between optimizations.
- The new two-source, coarse/groups, O0/O2 matrix passes all eight conditions.
  Two initial compile/run pairs were reused and six pairs were new. Complete
  O0/O2 reports match, including work. Four O0 ASan/UBSan conditions also pass
  with LSan disabled and complete reports equal to their ordinary counterparts.
  Together these runs reject 240 copied-report and 90 copied-structure controls.
- Genuine generated SUM guards pass 33 copied-packet and six real-instantiation
  controls at each O0/O2; the synthetic DATA pair passes 21 plus six. Each
  healthy run returns Int42 with all seven live ledgers zero. For each nominal
  kind, five injected fault-8 cases retain the diagnostic allocation:
  5,624 bytes for SUM and 3,016 for DATA. Separate explicit terminal surrender
  retires exactly those bytes. These controls use known-valid references, not
  arbitrary pointer/race injection or exhaustive projection/capsule coverage.
- A fixed fuel-146 pair returns the expected exit 2/fault 4. Both preserve the
  same 214-event healthy prefix through the nominal child's creator return,
  with its captured owner still pending. Default retain leaves 78 live blocks /
  11,752 bytes; explicit terminal destruction retires exactly those 78 blocks /
  11,752 bytes across all seven categories. Six copied fault controls reject.
  Fuel was derived from the saved healthy trace, without a budget search or
  healthy rerun. This fixture has no recursive knot or Fill-retirement claim.
- The final fresh CLI suite passes both genuine sources with 16 clean child
  process records, all exit zero with empty stderr. Captures match the reviewed
  inputs/results: identity uses `/1` with two steps; inferred curried-constant
  uses `/2` with four ordered arguments, Bool, Int, Int and the actual nominal.
  Complete native reports are byte-for-byte equal to initial coarse/O0,
  including work totals 10,569,875 and 25,673,329. Its 40 copied-report and
  15 copied-structure controls reject. Build/capture durations are not runtime
  performance measurements.

Both source graphs exercise exactly 26 applicable guards, mask 117440511.
Neither graph has Hole/Fill, so Fill guard 24 is not exercised. The initial
identity observer incorrectly copied an all-27 expectation from an earlier
stage; its failed observation is retained. The corrected observer rechecked the
same successful report without rerunning the target or changing production
source. This was an observer expectation defect, not a runtime failure.

## Reproduce and CI

```sh
T=tools/experimental/resource-native/tests
python3 -B "$T/test_ir8_nominal_arguments.py"
python3 -B "$T/test_module_shared_nominal_arguments.py"
python3 -B "$T/test_planner_v8_shared_nominal_arguments.py"
python3 -B "$T/test_source_v8_nominal_shared_arguments.py" \
  --ghc /absolute/path/to/ghc-9.14.1 --cc cc \
  --output /absolute/new/nominal-shared-source-output
```

The fresh runner builds/captures both inferred sources and retains per-case
`nominal-shared-observations.json`. Historical captures are never substituted
for these fresh calls. Optional `IR8_NOMINAL_SHARED_ARGUMENTS_ROOT` enables
retained host controls; `IR8_NOMINAL_CALLABLE_CAPTURES_ROOT` enables prior Stage20
planner goldens. They are not fresh source qualification.

CI adds a separate 20-minute nominal-shared job with the same checksum-pinned
official GHC setup/dependencies. The existing 26-case/60-minute job and four-case/
20-minute nominal-capture job remain unchanged. The new job runs the two fresh
sources, then uses their curried SUM pair for focused guards and a separately
host-generated synthetic DATA pair for the other nominal kind. Each guard
invocation has a 300-second outer cap; synthetic preparation has 180 seconds.
Existing guard compile/run limits stay 60 seconds per process. The guard steps
make no additional source captures. No cap increase or dependency is introduced.
All evidence is kept
on failure. The overall job cap can still fail on slow runners; it is not a
worst-case completion guarantee. Exact-commit CI remains a separate result.
