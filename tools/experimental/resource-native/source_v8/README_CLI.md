# Opt-in shared-source CLI

`run_source_v8.py` accepts source files, builds a fresh standalone source
producer, independently checks its captured proof and module evidence, lowers
the supported fragment to IR8, and compiles/runs the real native runtime.
It does not change `run_native.py`, export/2, v7 or any default compiler route.
It has no option to import a capture JSON file, cached receipt or prebuilt
producer binary.

From the repository root, using trusted GHC 9.14.1 and C11 compiler executables:

```sh
python3 -B tools/experimental/resource-native/run_source_v8.py \
  /absolute/project/main.emlf \
  --module-root /absolute/project \
  --ghc /absolute/ghc-9.14.1/bin/ghc --cc gcc \
  --output /absolute/new-run-directory
```

The entry must be a headerless legacy EMLF `.emlf` file with actual imports.
For example, `main.emlf` can contain:

```text
import SharedPoly
let i = sharedId 41 in let b = sharedId true in if b then addInt i 1 else 0
```

Place this beside it as `SharedPoly.emlf`:

```text
module SharedPoly (sharedId) where
sharedId : forall a. a -> a
sharedId x = x
```

The current fragment admits Int, Bool and arrows, supported scalar primitives,
Int conditionals and bounded rank-1 shared callable uses with complete closed
Int/Bool or exact registered parameter-free DATA/SUM atom vectors, plus
referenced closed DATA and scalar/self-field SUMs.
DATA fields are Int, Bool or recursively closed arrows over those scalars; exact
nominal identities are not merged by equal field layouts. It preserves the
shared RHS, ordinary pending applications,
actual checked type-computation witnesses and curried captures. Unsupported
proofs, open/partial shared uses, higher-rank or impredicative arguments,
parameterized types, mutual/cross-family recursion, nested DATA fields, callable
SUM fields and recursive generic definitions reject before native execution.
A SUM field may refer only to its own exact zero-argument family, besides Int/Bool. Ordinary function
types and DATA case results may mention admitted nominal types; SUM cases require
Int results. Retained generic principal code still cannot contain nominal atoms
or operations; complete closed use vectors may contain admitted nominal atoms.
All declarations remain evidence, without automatically
admitting unrelated compiler dictionaries.
[Stage13](../resource_ir_v8/README_STAGE13.md) also accepts one closed,
explicitly annotated monomorphic recursive function without outside term
captures. The exact annotation applications remain in the graph; generic,
mutual, value/alias and second-group recursion stay rejected. The CLI arguments,
default placement and fault policy are unchanged.
[Stage14](../resource_ir_v8/README_STAGE14.md) permits that recursive function
to capture closed Int/Bool owners and complete lexical shared views, retaining
their actual Access/origin. It does not admit arbitrary ordinary callable or
nominal captures, bare Schemes, partial vectors or additional recursive groups.
[Stage16](../resource_ir_v8/README_STAGE16.md) additionally permits ordinary
lexical callable captures with complete closed arrows over Int/Bool. Such owners
may remain pending and resolve to a concrete closure or a full shared callable
view without a new CLI option. [Stage18](../resource_ir_v8/README_STAGE18.md)
also admits ordinary owners of exact already-supported closed DATA/SUM types.
It preserves their pending annotations, complete Reference and capture support;
it does not reconstruct fields or views. [Stage20](../resource_ir_v8/README_STAGE20.md)
also permits ordinary recursive captures of full closed arrows containing exact
already-published DATA/SUM nominal leaves. It preserves each pending owner,
complete type, support and occurrence path without selecting another family.
[Stage21](../resource_ir_v8/README_STAGE21.md) extends complete shared type
arguments to exact registered parameter-free DATA/SUM atoms, preserving every
coordinate and the actual owner/view identity. It adds nominal beta only to the
shared diagnostic producer and independently derives `/2` only for a real nominal
beta step. Generic nominal principal code, arrow/open/parameterized arguments
and recursive generic definitions remain rejected. DATA field arrows still have
only Int/Bool leaves and SUM cases still return Int. No CLI flag or default changes.
The finite Stage21 local source/native checks pass; exact-commit CI is separate.
See the [fragment contract](README.md) for its limits.

For example, a closed callable field can use the same `SharedPoly.emlf` above:

```text
import SharedPoly
data FnBox = FnBox (Int -> Int);
let boxed = FnBox (sharedId : Int -> Int) in
let extracted = case boxed of { FnBox field -> field } in
if sharedId true then extracted 42 else 0
```

The field payload and whole case remain lazy. The case releases its container
handle after retaining the projected field and ending the loan. With default
coarse placement, the owning group may remain alive until after the field is
called; handle release alone is not early physical node deallocation.

## Experimental DATA group placement

Add `--data-groups` explicitly to try strict-support group placement:

```sh
python3 -B tools/experimental/resource-native/run_source_v8.py \
  /absolute/project/main.emlf --module-root /absolute/project \
  --ghc /absolute/ghc-9.14.1/bin/ghc --cc gcc \
  --data-groups --output /absolute/new-data-groups-run
```

The flag defaults to false and is forwarded to the planner, not the producer or
runtime. Without it, the complete coarse plan and CLI result fields are unchanged.
`planned.json` identifies the selected strategy in `binding.mode`: `coarse-owned`
or `data-groups-prototype`. The latter also records `binding.source_map.group_map`.
There is no automatic selection based on the source or a promised memory win.

Eligible allocations use separate groups only when their supports are proven
strictly below the current home; otherwise the planner falls back to that home.
Captured closures, generic internals, case and conditional thunks remain coarse.
The admitted fragment, lazy payloads, sharing, full callable contracts, Access/Env,
runtime ABI and fault policies do not change.

Finite real-C comparisons retired callable-field DATA containers before pending
payload demand and the later call. Peak tracked bytes fell from 7,744 to 7,216
for a shared callable field and from 9,512 to 8,544 for a curried field, but rose
from 4,088 to 4,248 for scalar Box. Total allocation and reference-count work
increased. These are ledger measurements, not RSS or elapsed-time improvements.
See the [Stage09 tradeoff and evidence](README.md#stage09-opt-in-data-group-placement).

## Scalar-field SUMs

Stage10 accepts 2–64 constructors with 0–32 Int/Bool fields each, no type
parameters or recursion, and exhaustive Int-result cases. The combined limit
is 32 referenced DATA/SUM declarations. Exact constructor/family identity and
source arm order are checked separately from declaration variant order. Every
arm is checked, but only the selected arm's lazy factory thunk is allocated and
entered. External and field capture limits are 32 each, 64 total per factory.

For example, beside the same `SharedPoly.emlf`:

```text
import SharedPoly
data Choice = Empty | Number Int;
let payload = addInt 20 1 in
let choice = Number payload in
case choice of {
  Empty -> if sharedId true then sharedId 42 else 0;
  Number n -> if sharedId true then sharedId (addInt n payload) else 0
}
```

The Number field and external `payload` alias must retain the same pending
computation, not an eager scalar or a cloned expression. Changing only
`Number payload` to `Empty` keeps the external payload allocation but leaves it
undemanded. SUM constructors and case thunks remain coarse under either CLI
placement mode; `--data-groups` may separate other eligible supports. This adds
no callable SUM support, runtime/ABI change or automatic strategy. Stage11 adds
only the exact self-family field subset below.
See the [bounded SUM contract and evidence](README.md#stage10-closed-scalar-field-sums).

## Finite self-family SUM graphs

Stage11 additionally admits fields equal to the same exact parameter-free SUM
family: for example, `data IntList = Nil | Cons Int IntList`. This is a finite
nominal atom in metadata, not recursive type expansion. All prior declaration,
variant, field, capture, depth and work limits stay unchanged. Cross-family and
mutual recursion, type parameters, callable SUM fields, source `letrec`, recursive
functions and nominal generic scopes/vectors remain unsupported.

Constructor graphs are finite ordinary terms. Nested exhaustive Int-result cases
retain per-arm identities and Down field captures. A wildcard tail remains an
actual stored pending computation, but is never forced merely by case selection.
SUM containers remain coarse in both modes; this is not cycle collection or an
early SUM reclamation strategy. See the [contract and evidence](README.md#stage11-finite-self-family-sum-graphs).

## Source and toolchain custody

- The output directory must be new, outside both the module root and this
  checkout, and must not traverse links. Failed output is retained.
- The complete module tree is bounded before any compiler launch: at most 32
  `.emlf` files including the entry, 1 MiB each, 8 MiB total, 1024 visited entries
  and depth 16. Links, special files, parent-path escapes and guest `.hs` files
  reject. Reads are capped.
- The producer reads an exclusive snapshot as its working directory and the
  exact entry bytes on stdin. Imports resolve within that snapshot. Missing
  imports fail there; no installed-library fallback is enabled. Compiler-built
  `Prelude` and `MLF.Primitive` definitions are part of the trusted compiler
  build, not copied guest sources.
- Both complete source inventories are checked again. The independently
  verified loaded subset must match copied bytes exactly. Unimported `.emlf`
  files are copied and mutation-checked, but are not claimed typechecked.
- Trust the selected checkout and compiler executables. The version check is
  not download authentication. These are cooperative filesystem consistency
  checks, not a hostile-filesystem or hostile-toolchain sandbox.

The intermediate `mlf-shared-source-capture/1` remains diagnostic. Local
acceptance comes from this fresh invocation followed by module custody,
projection, normalization/proof and resolver replay, fresh IR8 checking and
emission. Reading a JSON file with matching flags or hashes does not reproduce
that authority. This is not a complete export/3 interface.

## Results and fault policy

The CLI prints a short summary and retains `result.json`, the source snapshot,
command/stream results, replay output, planned IR8, generated C and native
report in the selected output directory. A completed native evaluation returns
0; a native fault returns 2. Preparation or compilation failure returns 1 and
retains diagnostics. Invalid CLI syntax is rejected before execution.

`--fuel` accepts 1 through 10000000; its default is 1000000. The default
`--failure-policy retain` uses `rt8_run`: a fault retains its diagnostic ledger
and is not reported as successful cleanup. Explicit
`--failure-policy destroy-terminal` uses the existing terminal-surrender API
and reports destruction separately, preserving the original fault and return
code. It does not retry evaluation. Healthy completion uses ordinary cleanup
under either policy.

Finite driver tests returned 42 with balanced empty ledgers under both policies.
With fuel 1, both reported the same FUEL fault and evaluation data; retain left
2608 bytes in three blocks, while explicit terminal destruction separately
retired exactly those allocations. Fourteen malformed-argument controls rejected
before runtime entry. These observations do not cover every fault family.

## Tests

Host-only parser, snapshot, loaded-subset and mutation tests:

```sh
python3 -B tools/experimental/resource-native/tests/test_source_v8_cli.py
```

The opt-in full suite makes eight fresh CLI calls, with no preserved producer
or capture replacing a new build:

```sh
python3 -B tools/experimental/resource-native/tests/test_source_v8_cli.py \
  --integration --ghc /absolute/ghc-9.14.1/bin/ghc --cc gcc \
  --output /absolute/new-cli-suite-directory
```

It covers an ordinary unused type error, a later unsupported-fragment rejection,
both Int/Bool demand orders, curried `sharedConst`, a renamed nested module with
an unused invalid source file, and the same admitted source with low fuel under
both fault policies. Both rejection cases must stop before native compilation.
Before Stage08, the full CLI suite passed locally on 2026-11-04: all eight cases
and 42 host checks. All four healthy programs returned 42 with balanced empty ledgers; the
two fault policies preserved identical evaluation data, and both rejected
programs stopped before native compilation. The nested-module case copied three
source files but loaded only two, leaving its invalid unused file explicitly
unchecked.

That complete run is retained unchanged. A subsequent version-query-only fix
adds `+RTS -xr32m -RTS` to GHC's numeric-version probe, controlling its virtual
address reservation while retaining the 1 GiB address-space and 10-second
limits. It changes neither compiler construction nor source/native behavior;
its targeted probe and host regressions are checked separately. The full eight
cases are not claimed rerun with that probe-only change. Exact-commit CI remains
a separate result.

Stage08 adds a separate three-case source suite:

```sh
python3 -B tools/experimental/resource-native/tests/test_source_v8_nominal.py \
  --ghc /absolute/ghc-9.14.1/bin/ghc --cc gcc \
  --output /absolute/new-nominal-suite-directory
```

It covers scalar Box, FnBox holding a sharedId view and FnBox holding a curried
sharedConst `Bool -> Int` view with both complete two-coordinate vectors.
All three calls use fresh builds/snapshots, the existing CLI and unchanged real
runtime. The complete three-case suite passed locally on 2026-11-04 without
retries: every CLI, producer and native process returned zero, each result was
Int 42, and all seven ledger categories were balanced and empty. This does not
claim exact-commit CI success or physical container deallocation before a field
call. The Box/FnBox observations and exact ownership/event distinctions are documented in
the [Stage08 fragment section](README.md#stage08-closed-data-and-callable-fields).

Stage09 runs those same three source cases through a separate fresh invocation:

```sh
python3 -B tools/experimental/resource-native/tests/test_source_v8_nominal.py \
  --data-groups --ghc /absolute/ghc-9.14.1/bin/ghc --cc gcc \
  --output /absolute/new-data-groups-suite-directory
```

The fresh opt-in suite passed locally on 2026-11-04: all three cases returned
Int 42 with fault zero, seven balanced empty ledger categories and DATA
retirement before later field use. All 24 recorded subprocesses returned zero.
The earlier O0/O2 comparisons are separate evidence, and exact-head CI remains
pending; these complete-build runs are not a performance benchmark.

Stage10's separate two-case fresh source suite is:

```sh
python3 -B tools/experimental/resource-native/tests/test_source_v8_sum.py \
  --ghc /absolute/ghc-9.14.1/bin/ghc --cc gcc \
  --output /absolute/new-sum-suite-directory
```

It retains per-case `sum-observations.json` alongside the normal CLI evidence;
`--data-groups` is optional. The fresh default two-case suite passed locally on
2026-11-04: all 16 process records returned zero without cleanup errors, both
native reports exactly matched the earlier coarse-O0 reports, and both returned
Int 42 with seven balanced empty ledger categories. Number shares one payload
memo and a deferred Int argument; Empty never demands the external payload.
The eight retained-capture native conditions are separate evidence, and
exact-head CI remains pending.

The separate Stage11 two-case fresh source suite is:

```sh
python3 -B tools/experimental/resource-native/tests/test_source_v8_recursive_sum.py \
  --ghc /absolute/ghc-9.14.1/bin/ghc --cc gcc \
  --output /absolute/new-recursive-sum-suite-directory
```

It writes `recursive-sum-observations.json` for `nested` and `lazy-tail`, including
copied-report negative controls. Optional `--data-groups` changes eligible
supporting placement, not SUM container placement. The fresh default suite passed
locally on 2026-11-04: all 16 process records returned zero, both native reports
exactly match their earlier coarse-O0 baselines, and both return Int 42 with
seven balanced empty ledgers. The new CI step uses default coarse placement and
retains earlier suites and limits; exact-commit CI is still pending.

Stage20 adds a separate two-case fresh-source suite for nominal-argument and
nominal-result callable captures:

```sh
python3 -B tools/experimental/resource-native/tests/test_source_v8_nominal_callable_captures.py \
  --ghc /absolute/ghc-9.14.1/bin/ghc --cc gcc \
  --output /absolute/new-nominal-callable-suite-directory
```

It uses default coarse placement and the unchanged CLI, retaining
`nominal-callable-observations.json` per case. The fresh two-case suite passed:
all 16 process records exited zero without cleanup errors, both results are
Int42 with seven balanced empty terminal ledgers, and complete native reports
match the original coarse-O0 reports including every work field. Its 50 report
and 12 structure controls reject; no additional fault pair was run. Exact-head
CI remains separate. See the [Stage20 scope and validation status](../resource_ir_v8/README_STAGE20.md).

The Stage21 inferred nominal shared-argument suite is:

```sh
python3 -B tools/experimental/resource-native/tests/test_source_v8_nominal_shared_arguments.py \
  --ghc /absolute/ghc-9.14.1/bin/ghc --cc gcc \
  --output /absolute/new-nominal-shared-suite-directory
```

It freshly builds identity and inferred curried-constant cases and retains
`nominal-shared-observations.json`. The earlier explicitly annotated curried
control is diagnostic only, not a replacement source. Both fresh cases pass,
with 16 clean process records and full native reports byte-for-byte equal to the
initial coarse/O0 reports, including every work field. The suite rejects
40 copied-report and 15 copied-structure controls. The eight-condition native
matrix, four ASan/UBSan conditions, nominal guards and fixed fuel-146
retain/terminal pair also pass locally. These nonrecursive fixtures exercise
26 applicable guards, not the Fill guard. See the
[Stage21 results and limits](../resource_ir_v8/README_STAGE21.md) for the retained
observer correction and exact scope. Exact-commit CI remains separate.

The Stage22 higher-order shared-function suite uses the same CLI contract:

```sh
python3 -B tools/experimental/resource-native/tests/test_source_v8_higher_order_shared.py \
  --ghc /absolute/ghc-9.14.1/bin/ghc --cc gcc \
  --output /absolute/new-higher-order-shared-directory
```

It tests `sharedApply` with ordinary callable term arguments, not arrow-valued
shared type coordinates. The default `--case all` runs both equal- and
opposite-coordinate sources. Both pass finite native/sanitizer checks and the
final fresh suite: 16 clean child records, identical checked capture bytes and
complete native reports equal to initial coarse/O0. Report controls are 26 for A
and 33 for B; structural controls are 10 and 13 per placement plan and fresh CLI,
not per optimization/sanitizer. Only A has fixed-fuel retain/terminal coverage.
See the [Stage22 scope and evidence](../resource_ir_v8/README_STAGE22.md).
The isolated 20-minute CI job preserves all existing jobs and limits; exact
Stage22 CI has not run.

This remains a bounded opt-in experiment. It does not establish arbitrary MLF
source support, general nominal or callable-SUM coverage, all runtime guards,
full GC replacement or a performance improvement.
