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
Int/Bool vectors. It preserves the shared RHS, ordinary pending applications,
actual checked type-computation witnesses and curried captures. Unsupported
proofs, open/partial shared uses, higher-rank or impredicative arguments, nominal
operations and recursive generic definitions reject before native execution.
See the [fragment contract](README.md) for its limits.

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
The full CLI suite passed locally on 2026-11-04: all eight cases and 42 host
checks. All four healthy programs returned 42 with balanced empty ledgers; the
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

This remains a bounded opt-in experiment. It does not establish arbitrary MLF
source support, nominal/callable-SUM coverage, all runtime guards, full GC
replacement or a performance improvement.
