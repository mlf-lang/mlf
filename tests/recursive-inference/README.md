# Focused recursive-inference discovery

`RecursiveInventoryDiscovery.emlf` inspects the actual retained Modules,
Separate, Readability and CoreSolver test-list spines and labels. It compares
these with the registry/catalog and verifies all 746 Core labels against the
preserved golden inventory, including unique stable IDs and partition totals.
It **does not execute** any test action, fixture program, LLVM/native campaign,
or security campaign.

Run from the repository root with the current compiler and each shared source
root except `host/ghc` on its `-i` search path, for example:

```sh
emlf $(jq -r '.source_roots[] | select(. != "host/ghc") | "-i " + .' shared-sources.json) \
  --run tests/recursive-inference/RecursiveInventoryDiscovery.emlf
```

The direct GHC `shared-frontend --recursive-inference` executable separately
executes the 53 recursive source cases plus 41 declaration/field repair
compilation cases, nine provenance assertions, finite-origin planner checks,
and current plus frozen target/evidence checks. One new compilation case
explicitly preserves a known constructor-side rejection rather than claiming
that residual fixed. The discovery harness does not substitute
for those checks or claim that all 746 Core actions have been executed.

`runtime/*.emlf` are three terminating host-interpreter checks. Run each with
`emlf --run FILE` and compare exact stdout with its `.stdout` sibling. They
exercise factorial, a mutual recursive knot, and explicit inferred dictionary
arguments over repeated recursive calls. They are separate from the 746-case
Core inventory and require no LLVM/GC/native compilation.

## Exact saved-crate host compatibility

`QualifiedCrateHost.hs` reads the maintained literal fixture constructors from
`tests/Tests/Modules.emlf` at runtime. It fails closed if a selected fixture is
missing, duplicated, has a different shape, or uses an unsupported oracle. It
never substitutes a simpler source. Build and run it using an existing completed
shared build (and its already-installed GHC), from the repository root:

```sh
python3 tests/recursive-inference/run_saved_crate_host.py \
  --compiler-build .mlf-build/qualified-final-O2 \
  --build-dir .mlf-build/qualified-host-crate-audited
```

The driver verifies the existing receipt's shared/host/configuration inputs,
compiles the raw imported compiler modules in a separate object directory, and
records a separate `result.json` with exact fixture/harness/input/binary/log
hashes. It does not install software or claim to be the 105-module interface
build audit itself.

Parity with `Tests.Separate.compileSeparateProgram`:

1. Parse the same library/main strings with `loadModuleMap`, then `cleanSource`.
2. Use the same `test:crate` identity, `ImplicitPrelude`, `CrateSpec`, and
   `compileSources`; only isolated scratch/cache paths differ.
3. Reload `.mlfci` and `.mlfco` through `loadInterfaces` and `readObject`, then
   `linkObjects` with the original entry identity.
4. Keep prescribed `IO Unit` (the checking oracle, not stdout), `XBot`, or
   `XCon` results. Check production/frozen typing before and after serialization
   and compare erasures. Never evaluate the divergent fixture.
5. For the three rejection fixtures, require the original `Resolution` tag
   and original exact reason substring. This is stricter than the legacy
   separately linked test's any-error assertion.

Each selected fixture now also runs directly through `compileModules` before
the saved/reloaded crate path, preserving the same source, expected type or
error, both checkers, serialization and erasure checks.

The six selected labels are the defining-module-instance positive, three
signed-definition/instance-body/cyclic-orphan scope negatives, the exact
unsigned divergent cross-module cycle, and the qualified cross-module export
used at both Int and Bool. These are the same six direct-module and six
separately linked cases, not twelve new inventory IDs.

The 2026-10-24 nested-interpreter compatibility attempt completed discovery and
all six direct-module checks, but was deliberately interrupted (exit 130) while
compiling its first saved-crate builtin prelude, after this exact host route
passed. The host result is **not** represented as completion of that guest run.

`RecursiveModuleCompatibility.emlf` preserves the combined legacy route: live
inventory discovery, the exported canonical-query assertion, and the same six
module plus six crate actions. Run it with the same compiler source roots as
the discovery command, add `-i tests/recursive-inference`, and set
`MLF_TEST_WORK` to an existing writable project-local absolute directory. It
can be very slow because the compiler is interpreted while producing builtin
crate artifacts. This driver does not invoke program execution/native tests.

`TypeclassCompatibility.emlf` is the byte-identical maintained copy of the
five-line harness used for the final 78-action class compatibility run. Run it
with `emlf --run` and the shared source roots (excluding `host/ghc`) as above.
It selects the existing `Tests.Typeclasses.typeclassTests` list unchanged; it
adds no test IDs and does not invoke the native campaign.

## PR22 canonical-source integration

The ordered 739 → 742 recursion migration remains historical evidence, not a
regenerated baseline. The canonical-source integration explicitly migrates eight
more labels and retains four upstream-added do/surface controls, yielding 746
registered leaves: 34 solver + 384 language + 27 crates + 301 modules. The static
guard binds these exact changes to the frozen catalog, preserves all other
family/label ordering, and rejects retired IDs, dropped/moved/reordered additions,
source-body changes and oracle mutations.

Canonical list/tuple/unit syntax is applied only to implementation identifiers.
Nominal custom List/Maybe source tests retain their declarations and expected
types. Intended parenthesized expression annotations use `::`, while declaration,
forall and kind-syntax controls retain their original intended scope. The current
and frozen target checkers, prescribed type ASTs and erasure checks remain active.
The same-name do-local function and unsigned loop cases check Int and XBot without
executing their divergent targets; the same-name do-local value retains its
infinite-type rejection. The standalone unsigned source helper now checks the
original terminating source evaluates to 42; private instance-scope negatives
remain unchanged.
