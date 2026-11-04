# Controlled shared-source fragment experiment

The separate [source-only CLI](README_CLI.md) builds and runs this bounded route
from an actual module snapshot. The diagnostic capture itself remains
non-importable as native authority.

This opt-in experiment connects a freshly built ordinary source compiler to
independent shared-fragment replay, IR8 planning and the real Stage05 runtime.
It does not change the maintained export/2 frontend, v7 route or any default
entrypoint. It is not yet a general shared-polymorphic source bridge.

## Trust boundaries

1. `Main.hs` and `ResourceSharedExport.hs` build a standalone diagnostic producer
   against the repository's real compiler sources. It calls
   `MLF.ResourceModules.compileCaptured`, performs ordinary whole-source checking
   and checked outer-spine projection, then rechecks the retained and normalized
   terms. Normalization requires root-type alpha equality, ordinary erasure
   equality and unchanged declarations. It does not clone a shared RHS for each
   requested type or beta-reduce/in-line ordinary term bodies.
2. The result is explicitly `mlf-shared-source-capture/1`, with status
   `diagnostic-not-runtime-admission`. It is **not** the final
   `mlf-checked-module-export/3` format. Fields saying that checks passed are not
   independent authority to run arbitrary JSON.
3. `tests/validate_shared_capture.py` verifies completed captures against exact
   fixture bytes supplied by its caller. It independently replays module
   custody, projection, binder-origin joins and normalization. Authentication of
   the actual producer build and completed invocation remains the caller's job;
   reading a capture file cannot establish those facts by itself.
4. `module_shared_transport.py` derives/replays the bounded
   `mlf-shared-fragment-replay/1` fragment. `planner_v8.plan_fragment` freshly
   replays that input and produces a candidate IR8 program with correspondence
   rows. Its result still says `source_admitted=false` and
   `ordinary_K_checked=false`; this API is not an ordinary source checker.
5. The independent IR8 resource checker and public runtime emitter check the
   candidate before C generation. The native test compiles and links the seven
   production C translation units, generated packet/body pairs and the real test
   driver. It does not use dummy callbacks or an older runtime fallback.

The supported fragment is deliberately narrow: Int, Bool and arrows; complete
closed Int/Bool vectors at shared rank-1 callable uses; supported scalar
primitives and an Int conditional. Pending shared RHSs, captured callable views,
dead type parameters and curried callable values have separate regression
cases. Bare, partial or open shared uses, recursive/nested generic definitions,
unsupported proofs and higher-rank uses reject. Stage08 adds closed nominal
DATA, Stage10 adds scalar-field SUMs, and Stage11 adds exact self-family fields; none admits every
preserved declaration automatically.
[Stage13](../resource_ir_v8/README_STAGE13.md) adds one explicitly annotated,
closed monomorphic recursive function with no outside term captures, using the
existing typed hole/fill protocol. Generic, mutual and recursive value bindings
remain rejected. [Stage14](../resource_ir_v8/README_STAGE14.md) extends that
single concrete recursive function to closed scalar owners and complete lexical
shared views, preserving each capture's own Access/origin.
[Stage16](../resource_ir_v8/README_STAGE16.md) also accepts ordinary lexical
callables whose full arrow type contains only Int/Bool leaves and arrows. Pending
owners stay lazy; their eventual concrete closure or shared callable target is
not inferred from the type. Nominal-valued captures, bare Schemes and generic or
mutual recursion remain outside this slice. Historical stage sections retain
their earlier scope below.

## Stage08: closed DATA and callable fields

Only referenced declarations with no type parameters and exactly one constructor
are admitted. Each field is Int, Bool or an arrow built recursively from those
scalars. This permits closed curried/higher-order arrow fields, but no open types,
forall fields, nested nominal fields or recursive DATA. The bounds are 32
referenced nominal declarations and 32 fields per constructor. Zero-field DATA
is allowed. Exact nominal identities stay distinct even when all field types
are equal.

Ordinary function parameter/result types and case result types may mention an
admitted DATA type. Retained generic scopes and Scheme bodies may not contain
DATA atoms; Scheme instantiation vectors remain complete closed Int/Bool
vectors. A monomorphic DATA field can therefore carry a closed view of a shared
callable without making that DATA type a generic parameter.

The full declaration list remains in the source evidence. Unrelated compiler
dictionary declarations are neither deleted nor automatically admitted. Used
constructors must have their exact, saturated source application spine; case
analysis must match the exact owner, sole constructor, field arity and result
type. Unsaturated constructors with fields, extra constructor application and
wrong nominal identities reject rather than falling back to structural field
equality. A bare zero-field constructor is already saturated.

The planner keeps field payloads pending and delays the whole case. Projection
borrows a field, retains its owner, ends the loan and releases the container
handle. The full callable contract and actual Access/Env are preserved. This
ownership sequence is checked in IR and generated C. Runtime field/case/return,
memo and invocation events plus balanced owner/loan counters provide separate
observations; there is no individual event trace for every retain/end-borrow/drop.

With the default coarse placement, reclamation is group-based. In the Stage08
callable cases the same-home group closes **after** the extracted callable is invoked.
Releasing a container handle does not prove that its node was freed earlier,
nor did Stage08 establish lower peak memory or a performance gain. The separate
Stage09 opt-in strategy below changes placement, not the runtime or this default.

## Stage09: opt-in DATA group placement

The source CLI's explicit `--data-groups` flag selects
`plan_fragment(..., data_groups=True)`. Without it, the planner keeps the exact
coarse output, including its correspondence and work counters. There is no
automatic strategy selection. `planned.json` records `binding.mode` as
`data-groups-prototype` and adds the placement `group_map` only for the opt-in;
the default mode remains `coarse-owned`. CLI result and stdout fields are unchanged.

The prototype separates eligible allocations only when all of their supports
are proven strictly below the enclosing home. It uses the existing `new_below`
operation with live owner imports, releases each new builder, and releases case
captures that are no longer needed by the arm. This also places supporting
scalars, applications, capture-free closures and closed shared-RHS wrappers;
it is not just a different allocation call for the DATA node. Captured closures,
generic bodies, case thunks and conditional thunks remain coarse. If strict
support cannot be proved, allocation stays in the existing home.

This does not extend the admitted DATA or generic fragment. The node graph,
shared callable/body identities, complete type vectors, lazy field/case behavior
and full callable Access/Env contracts are preserved. The runtime, ABI and
default routes are unchanged.

Twelve local real-runtime comparisons used genuine capture replay, the seven
production C translation units, three sources, both coarse/opt-in plans and
both `-O0`/`-O2`. All returned 42 with seven balanced empty ledger categories.
For the two callable-field sources, DATA group closure and field-slot removal
preceded demand of the still-pending payload and its later call. Unlike the
Stage08 handle-order observation alone, this demonstrates earlier physical
container retirement in those finite runs.

The reported peak is the runtime's tracked allocation ledger, not process RSS:

- Shared callable field: 7,744 to 7,216 bytes.
- Curried callable field: 9,512 to 8,544 bytes.
- Scalar Box: **4,088 to 4,248 bytes**, a regression from the extra groups.

Both optimization levels gave those same counts. Total allocated bytes,
allocation counts and reference-count work increased in all three cases. This
is an experimental memory/overhead tradeoff, not an end-to-end timing result,
a general memory improvement, Perceus equivalence or full GC replacement.

Run the fresh source CLI suite separately with this strategy:

```sh
python3 -B tools/experimental/resource-native/tests/test_source_v8_nominal.py \
  --data-groups --ghc /absolute/path/to/ghc-9.14.1/bin/ghc --cc gcc \
  --output /tmp/ir8-source-data-groups-fresh
```

The fresh three-case opt-in CLI run passed locally on 2026-11-04: all 24 recorded
subprocesses returned zero, each native result was Int 42 with fault zero and
seven balanced empty ledger categories, and DATA retirement preceded later
field use. This is separate from the twelve comparisons; exact-commit CI is
still pending. CI retains both coarse and opt-in fresh source suites
separately, reuses the same GHC install and keeps the 60-minute job ceiling.

## Stage10: closed scalar-field SUMs

Referenced closed, parameter-free nominal declarations with 2 through 64
constructors are admitted as SUMs. Each variant has at most 32 fields, each
exactly Int or Bool. Nullary variants are valid. The combined referenced DATA
and SUM declaration limit remains 32. Stage10 itself excludes recursive types
and nested nominal fields; Stage11 below adds only exact self-family atoms.
Callable SUM fields, parameters and generic nominal scopes remain unsupported.
All declarations stay in the source evidence; unrelated compiler dictionaries
are not silently admitted or deleted. Exact nominal identity is preserved.

A SUM constructor must be saturated. Cases must be exhaustive, with one arm for
each exact declaration variant and an Int result. Source arm order may differ
from declaration order: both identities are retained, and each factory has its
own checked allocation Site. Every arm and its proof, type and captures are
checked, including unselected arms. A factory permits at most 32 external
captures and 32 field captures, 64 total; the enclosing case's capture union
also remains bounded by 64. Wildcards preserve the constructor payload but do
not invent a field binding or demand it.

The whole case is lazy. When selected, it creates only the chosen arm's thunk;
unselected factory code exists but its thunk is neither allocated nor entered.
Fields refer to the original pending payload. In particular, `sharedId` may
receive an Int-valued thunk before that argument is demanded. The observer
follows its later memo to the scalar result rather than assuming every argument
already has a scalar event.

SUM constructors and case thunks stay coarse even with `--data-groups`.
Eligible surrounding supports may use the Stage09 strategy; this does not
provide separate SUM-container reclamation. Existing DATA coarse/opt-in plans
and non-SUM defaults remain exact. There is no runtime, ABI, producer or CLI
change for this extension, and no new GC or performance claim.

The focused replay suite passed all 99 tests locally with its optional retained
SUM capture check enabled; the broader module run passed 251 of 254 tests with
three existing external-artifact skips. These capture replays are not fresh
source executions. Seventeen synthetic SUM planner tests pass, including variant/arm/Site joins,
selected-only factory structure, wildcard and numeric field positions,
32-external/32-field limits, complete shared-view pairs, invalid unselected
factory metadata and old complete-output goldens. They are not source-inference
evidence. Eight real-C conditions from genuine checked captures, Number/Empty
under coarse/groups and O0/O2, pass the SUM-specific observer with Int 42 and
seven balanced empty ledger categories. Number's field and external alias share
one original payload evaluation/memo; Empty allocates that payload but never
forces it. Only the selected factory is allocated/entered, and the shared RHS
is evaluated once with both complete Bool and Int views.

The first native pair succeeded but an older post-run observer assumed a ready
scalar Int argument and failed. Its actual output was retained and rechecked
with the lazy-aware observer; only the other seven pairs were newly executed.
The portable observer also accepts all eight reports and rejects 64 copied-report
negative controls. No runtime/source workaround was used.

The separate fresh two-source CLI suite passed locally on 2026-11-04. All
16 process records returned zero without cleanup errors; both complete native
reports equal their earlier coarse-O0 baselines. Number preserves the one
payload memo and deferred Int argument; Empty leaves the external payload
undemanded. Both return Int 42 with seven balanced empty ledger categories.

Two representative ASan/UBSan runs also passed with identical native reports:
Number/groups-O0 and Empty/coarse-O0. LeakSanitizer was disabled in this local
environment; this is not an all-combinations sanitizer or leak-detection claim.

To reproduce the fresh source suite:

```sh
python3 -B tools/experimental/resource-native/tests/test_source_v8_sum.py \
  --ghc /absolute/path/to/ghc-9.14.1/bin/ghc --cc gcc \
  --output /tmp/ir8-source-sum-fresh
```

It builds a fresh producer for each `number` and `empty` case, retaining the
source snapshot, capture/replay, plan, generated C, process records, native
report and `sum-observations.json`, plus top-level results or failure output.
Optional `--data-groups` selects the existing supporting-group strategy and
still requires coarse SUM placement. CI runs the two default-coarse source
cases separately from the earlier suites, preserving all earlier steps and
the 60-minute job ceiling. The retained-capture comparisons and fresh source
builds are separate evidence; exact-commit CI is still pending.

## Stage11: finite self-family SUM graphs

The only further field type is the selected SUM declaration's own exact
zero-argument nominal identity. For `IntList = Nil | Cons Int IntList`, metadata
contains the finite reference `%F<declaration-index>`, not an unfolded recursive
type. The declaration name, index and source address remain part of logical
identity; equal shapes never make two families interchangeable. Selection does
not recurse through declarations. The optional `nominal_sum.self_recursive`
marker is recomputed as policy `closed-self-atom/1` plus sorted original indices;
old scalar SUM and DATA evidence retains its exact prior shape and values.

All earlier bounds remain: at most 32 selected DATA/SUM declarations, 2–64 SUM
variants, 32 fields, 32 external plus 32 field factory captures (64 total), and
unchanged depth/work/metadata/runtime limits. Only finite lexical term graphs
are admitted. Type parameters, cross-family/mutual recursion, recursive DATA,
callable SUM fields, source `letrec` or recursive functions, and nominal types in
generic scopes or complete Scheme vectors remain excluded. This is neither
heap-cycle support nor general recursive MLF.

Nested exhaustive Int-result cases use the same selected-only arm factories.
Self fields retain exact nominal types and Down captures. A case does not force
stored fields while selecting its variant. SUM constructors and case thunks
remain coarse under both placement modes; eligible supports may use the existing
opt-in DATA strategy. Runtime, packet, IR checker, ABI and source producer code
are unchanged. The conditional's type-computation replay remains outer-first.

Two genuine source captures established the actual current-compiler shape before
this extension. Their producer checks succeeded, while the old scalar-only guard
rejected the self field before native execution. Those diagnostics are preserved.
The new complete replay passes source custody, projection, normalization and
resolver joins. The focused transport suite passes 117 tests, including both old
and new complete captures; the broader suite passes 269 of 272 with three existing
external-artifact skips. Seven new planner tests and 17 previous SUM tests pass,
including complete old-output goldens and malformed unselected factory checks.

Eight retained-capture C conditions, two sources under coarse/groups and O0/O2,
return Int 42 with fault 0 and seven balanced empty ledger categories. The nested
case stores one pending 21 node in both Cons heads and memoizes it once. The
wildcard-tail case retains a monomorphic ordinary application and its pending 123
argument without demanding either, entering its lambda, or constructing the
lambda's inner Cons/Nil. Only selected factories run, and one genuine shared RHS
serves complete Bool/Int views. O0/O2 complete reports match within each mode.
All eight reports pass the observer and 56 copied-report/plan negative controls.

The initial observer incorrectly treated an application's function handle as
its code field and expected a closure state of READY rather than CLOSURE. Five
actual successful target pairs were retained and rechecked after those two
observer-only corrections; only the remaining three pairs were newly executed.
No production change or rerun of those five targets was needed.

The fresh suite command is:

```sh
python3 -B tools/experimental/resource-native/tests/test_source_v8_recursive_sum.py \
  --ghc /absolute/path/to/ghc-9.14.1/bin/ghc --cc gcc \
  --output /tmp/ir8-source-recursive-sum-fresh
```

The new suite retains source snapshots, actual checked captures/replay, generated
C, process results, native reports and `recursive-sum-observations.json`. The
fresh default-coarse suite passed locally on 2026-11-04: all 16 process records
returned zero without cleanup errors, and both complete native reports match
their earlier coarse-O0 reports. This is a fresh producer/build/source result,
separate from replaying stored captures for the matrix.

Two representative ASan/UBSan conditions also passed with complete native
reports unchanged: nested/groups-O0 and lazy-tail/coarse-O0. LeakSanitizer was
disabled in this environment; this is not all-combinations or leak-detector
coverage. The old planner suite passed all 20 tests including five real native
fragments; placement passed 19 of 20 with its external-capture test skipped, and
all 42 CLI host tests passed. CI adds the new seven planner checks and two fresh
source cases, preserves earlier steps/process limits and the 60-minute ceiling,
and retains 22 fresh source cases in total. Exact-commit CI remains pending.

## Fragment and planner tests

From the repository root, with POSIX, Python 3.12 or newer and an existing C11
compiler:

```sh
python3 -B tools/experimental/resource-native/tests/test_module_shared_transport.py

python3 -B tools/experimental/resource-native/tests/test_planner_v8_placement.py

python3 -B tools/experimental/resource-native/tests/test_planner_v8_sum.py

python3 -B tools/experimental/resource-native/tests/test_planner_v8_recursive_sum.py

python3 -B tools/experimental/resource-native/tests/test_planner_v8_monomorphic_recursion.py

python3 -B tools/experimental/resource-native/tests/test_planner_v8_recursive_captures.py

python3 -B tools/experimental/resource-native/tests/test_planner_v8_callable_captures.py

CC=gcc IR8_PLANNER_NATIVE=1 \
IR8_PLANNER_NATIVE_OUTPUT=/tmp/ir8-planner-native-fresh \
python3 -B tools/experimental/resource-native/tests/test_planner_v8.py
```

The fragment suite now has 173 unittest cases, including five optional retained
capture tests. They use `IR8_SUM_CAPTURE_ROOT`,
`IR8_RECURSIVE_SUM_CAPTURE_ROOT`, `IR8_MONOMORPHIC_RECURSION_CAPTURE_ROOT`,
`IR8_RECURSIVE_CAPTURE_ROOT` and `IR8_RECURSIVE_CALLABLE_CAPTURE_ROOT`.
These five are skipped in CI, which separately runs fresh source suites.
The monomorphic-recursion planner suite has eight checks, including one optional
check using `IR8_MONOMORPHIC_RECURSION_CAPTURE_ROOT`. The recursive-captures
planner suite has 11 checks, with two optional checks using that variable and
`IR8_RECURSIVE_CAPTURES_ROOT`. The callable-captures planner suite also has 11
checks, with two optional checks using `IR8_RECURSIVE_CAPTURES_ROOT` for prior
Stage14 preservation and `IR8_CALLABLE_CAPTURES_ROOT` for the two Stage16 sources.
Note the distinct transport and planner environment-variable names. These
optional host checks do not build a new compiler or source target.
The original planner suite has 20 unittest
cases;
its final test runs five native fragment subcases: pending shared RHS, nested
view capture, a distinct dead-parameter vector, curried sharing and an unselected
arithmetic branch. Without `IR8_PLANNER_NATIVE=1`, that final test is skipped.
Set `CC` explicitly if `gcc-14` is not installed; the planner's default is
`gcc-14`. The retained native output directory must be new.

These tests use synthetic/raw fragments. They check replay, lowering and native
behavior, but do not claim genuine source inference or K-checker acceptance.
The CI fragment job sets the native opt-in and retains logs/generated programs.
It also runs the placement tests explicitly. Their optional historical-capture
test requires `IR8_PLACEMENT_CAPTURE_ROOT` and is skipped in CI; it is not
credited as a fresh source build or as part of the fresh three-case CLI run.

## Fresh controlled source-to-native test

This integration test requires **GHC 9.14.1**, Python 3.12 or newer and a C11
compiler. It checks GHC's numeric version and will not silently substitute a
different compiler version. With GHC already installed:

```sh
python3 -B tools/experimental/resource-native/tests/test_shared_source_native.py \
  --ghc /absolute/path/to/ghc-9.14.1/bin/ghc \
  --cc gcc \
  --output /tmp/ir8-shared-source-fresh
```

The output directory must not exist. The runner builds a fresh standalone
producer and captures repository-controlled source fixtures, then performs
exact-custody/replay checks, planning, public IR8 emission and real native runs.
Its positive cases are Int-first sharing, Bool-first sharing and a two-formal
curried `sharedConst`. An unused ordinary type error is a negative control and
must be rejected by the real source compiler before lowering/native execution.
No preserved compiler binary or historical capture replaces the fresh build.

Each full-runner invocation requires its own successful result. Earlier
individual captures, raw-fragment passes or a copied capture file are not a
substitute. Keep the complete output directory on failure and inspect the actual
exit status and logs; timeout, build failure or incomplete capture is not a
successful ordinary type rejection.

The separate CI source job uses the same official GHC 9.14.1 Debian 12 bindist
pattern as the main repository CI, with archive SHA256
`60f7ab75f28df892729fbaff3a54f58ee3ad7e731929f1b2f3eb0208f73de841`.
It installs into the runner's temporary directory, verifies the version and
retains setup/test output. It adds no new setup action and does not enable this
source route by default. Local users can use an existing official installation;
the Python test does not install GHC for them.

## Observations and limits

Separate controlled Int-first and Bool-first captures have passed real ordinary
checking, exact custody/projection and independent normalization replay. Each
then returned 42 through the real runtime with zero live ledger after completion,
retaining one shared node while observing opposite actual first-use orders.
Those are finite diagnostic integration results, not general source admission.
Before the Stage08 extension, the portable full runner passed locally on
2026-11-04: a fresh GHC 9.14.1 producer build, all three positive sources including curried
`sharedConst`, and the unused Bool/Int type-error negative control. Each positive
returned 42 with all seven ledger categories balanced and empty, preserving the
shared pending RHS, complete type vectors and the asserted demand/capture order.
The run took about 350 seconds without retries. This is a local test result;
subsequent CI results must be checked on their exact commit.

For Stage08, the focused 78 host checks passed. The broader module regression
ran 233 tests with 230 passes and three existing skips; the planner ran 20 with
19 passes and its native opt-in test skipped. Separate genuine scalar Box and
FnBox captures then compiled/linked with the real runtime and returned 42,
fault zero and an empty balanced ledger in all seven categories. FnBox events
showed the pending field application returning from the lazy case before its
coercion ran, one shared generic RHS/callable across Bool and Int, and memo reuse.
These observations do not substitute for the fresh three-case suite below.

```sh
python3 -B tools/experimental/resource-native/tests/test_source_v8_nominal.py \
  --ghc /absolute/path/to/ghc-9.14.1/bin/ghc --cc gcc \
  --output /tmp/ir8-source-nominal-fresh
```

The three cases are `scalar-box`, `shared-field` and `curried-field`. Each makes
a fresh public source CLI call and producer build. The curried case stores a
`Bool -> Int` field from sharedConst while preserving the full ordered
`[Bool, Int]` and `[Int, Bool]` use vectors. Results include actual source,
capture/replay, planned IR, generated C, native reports and
`nominal-observations.json` for each case, plus `results.json` or failure output.
The full three-case suite passed locally on 2026-11-04 without retries. Every
CLI, producer and native process returned zero; each case returned Int 42 with
all seven ledger categories balanced and empty. In the curried case, the lazy
case returned the pending field before it was memoized to the real curried
closure and invoked. The group closed later, after that call. The two complete
vectors used the same shared node and body. These are local observations, not
an exact-commit CI result or proof of earlier physical container reclamation.
CI appends this suite after the existing source suites and reuses their GHC install.

The initial explicit-`coerce` fixtures passed ordinary source inference and
`K.check`. The independent restricted fragment replay then rejected their
impredicative forall-valued argument. This is fragment/native non-admission, not
an ordinary compiler rejection of those source programs. That boundary is
preserved without weakening either ordinary checking or the fragment rules.

Still unqualified:

- A complete public source-admission/export/3 interface and the full
  polymorphism/representation/runtime-inventory correspondence join.
- Parameterized types, cross-family/mutual recursion, recursive DATA,
  callable-valued SUM storage, recursive source functions/generic programs, arbitrary
  imported libraries, higher-rank use and broader MLF.
- Complete independent observation of every Access/Env/Transport transition and
  positive/negative coverage of all 27 runtime guard families.
- Whole-program source/model/runtime equivalence, complete GC replacement,
  maximal resource bounds or a measured performance improvement.

See [Stage05](../resource_ir_v8/README_STAGE05.md) for the raw-IR runtime scope and
[Stage04](../resource_ir_v8/README_STAGE04.md) for the unchanged packet/static
layers. Source/compiler tests here remain explicit and separate from those jobs.
