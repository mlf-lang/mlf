# Focused public `Graph.unify` regression fixture

`UnifyPublicApi.hs` is one standalone `Main`, authored against
`f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`. **It has not been compiled or run.**
Every expected result is an authored, statically reviewed expectation, not a
recording from either baseline or candidate. No production change, runtime
wrapper, automatic compilation entry point or new test framework is included.

## Coverage and observations

There are 23 ordered cases in `CASE-MAP.json`:

- 9 finite successes: empty/self equations, compact and negative dense IDs,
  sparse and signed-64-bit-extreme IDs, alias canonicalization/merging, and a
  higher-kinded application merge;
- 12 exact `Left` cases, including kind/constructor mismatch, a late missing
  endpoint preceding an earlier merge mismatch on both admission paths, rigid
  bottom instantiation, binding/structural cycles, root/arity errors, dense versus
  sparse validation error order, and invalid input preceding poisoned equations;
- an expected equation sentinel after valid input, plus an unused constructor
  name observed at successive demand boundaries.

Finite successes compare an authored expected graph against a complete logical
snapshot: ordered node identities; all tag, constructor-name, child, kind,
binder and flag fields; ordered aliases; and the fresh counter. That exact text
is emitted. Errors compare and emit the entire diagnostic string. Neither
comparison uses hashes or only acceptance, kinds or a lossy pretty-printer.
The snapshot does not assert identical internal `IntMap` tree shape.

The dense/signed/sparse/extreme examples assert the public `denseBounds`
precondition on their finite inputs. Such pre-observation is **not** added to
the partial-host cases. The extreme graph intentionally uses the public signed
64-bit domain without advancing the fresh counter; this tests `G.unify`, not
the stronger `Solver.prepare` fresh-ID admission contract.

For the unused-name case, the order is explicit: result `Either` WHNF, returned
`Graph` WHNF, fresh counter, then full graph rendering. Only the final observation
must raise the `unused-name` sentinel. The equation-poison controls likewise
observe the `Either` constructor, not a fully normalized result. Custom
exception constructors avoid unstable error call stacks. Async exceptions are
rethrown; this is not an async-equivalence test. The case action **and complete
PASS-payload rendering** share one synchronous exception boundary. Rendering is
not moved before the intended probes.

## Machine output

Each case emits one line, in CASE-MAP order:

```text
PASS<TAB>case-id<TAB><Haskell show String of actual observation>
```

A mismatch instead emits `FAIL` with a quoted single-line detail. Completion is
`SUMMARY<TAB>23<TAB>23` and exit status 0 only if all cases pass. On any failure
the summary records the lower success count and exit status is nonzero. Async
termination or output failure may prevent completion and must not be accepted.

For baseline/candidate comparison require all 23 case IDs, exactly once in the
declared order, no FAIL/unknown/extra rows, the exact success summary, both exit
codes zero and empty execution stderr. Compare **all actual payload bytes** and
the complete stdout, not the intersection of reported cases or just PASS labels.
No fabricated expected execution-output file is supplied.

## Small independent relink, using authenticated ordinary artifacts

Direct project imports are `Bootstrap.Graph`, `Bootstrap.Types`,
`Bootstrap.IntMap`, `MLF.Primitive` and `MLF.Host.Base`. Their static import closure
has 13 project modules, all present in the existing 94-module ordinary non-Main
closure. `IMPORT-INVENTORY.json` lists source pins and imports. This is a static
header scan, not a GHC dependency or typecheck proof. Standard imports need only
the already admitted packages; no additional package such as `filepath` is used.

Use the existing authenticated relink/guard machinery, not a new unbounded
`ghc --make` run:

1. Authenticate the selected producer, source/Graph pin, toolchain, flags,
   package database, object/interface pins and required C objects. For baseline
   use the actual frozen f9 ordinary producer, not a profiling mirror or the
   ENCODE candidate. For a later Graph candidate use its own completed producer
   and authentic dependencies, never silently borrow its Graph object from
   baseline.
2. Make a fresh isolated fixture work directory. Copy the authenticated non-Main
   interfaces/objects; do not modify producer files. The existing 94-module
   closure is sufficient and avoids inventing a new linker-closure oracle. A
   separately authenticated 13-module subset can be reviewed later but is not
   required. Exclude the producer's original `Main.o`/`Main.hi` and any second
   program main. Preserve the original host/supervisor C-object requirements.
3. Derive compiler flags from the authenticated ordinary producer. Preserve
   package/optimization/demand flags, including `-O2`, `-fpedantic-bottoms` and
   `-fno-state-hack`. Remove original source search/output paths; use only copied
   interfaces and fresh outputs. Compile only this fixture with one-shot `-c`,
   not `--make`. Keep imports' `-hidir` at the copied interfaces as required by
   the existing one-shot adapter, and direct Main's interface with explicit
   `-ohi` to its fresh Main directory. Do not weaken flags if compilation fails.
4. Link the new Main object with the authenticated copied non-Main objects and
   the original required C objects. Use the existing `-rtsopts=ignoreAll`
   ordinary control convention. Run this one executable with no arguments in
   the existing admitted time/resource/cleanup guard, and archive raw output,
   exit status, command, environment, input/output hashes and cleanup receipt.
5. Repeat with the exact same fixture bytes against the candidate producer;
   compare complete outputs under the rules above. If the first baseline run
   contradicts an authored expectation, stop and investigate the fixture or
   static reasoning. Do not relabel it as a candidate failure or silently bless
   the observed baseline as a new oracle.

Command **shape only**, with arrays populated from authenticated metadata by the
existing runner, is:

```sh
"$GHC" "${PRESERVED_FLAGS[@]}" -i -i"$COPIED_OBJECTS" \
  -odir "$NEW_MAIN" -hidir "$COPIED_OBJECTS" -ohi "$NEW_MAIN/Main.hi" \
  -c "$FIXTURE" -o "$NEW_MAIN/Main.o"
"$GHC" "${PRESERVED_FLAGS[@]}" -rtsopts=ignoreAll \
  "$NEW_MAIN/Main.o" "${AUTHENTICATED_NON_MAIN_OBJECTS[@]}" \
  "${AUTHENTICATED_C_OBJECTS[@]}" -o "$NEW_EXECUTABLE"
```

These commands have not been executed here and are not an admission or runner.
No production/solver code is compiled anew by this fixture's independent relink.

## Static review and limits

`STATIC-REVIEW.md` records the derivations and public/partial-value constraints.
The static receipt covers case inventory, source pins, import membership and
basic source structure only. It does **not** establish Haskell parsing, typing,
23 passing tests, producer authenticity, runtime equivalence or performance.
The fixture is a focused regression set, not a proof over all public graphs,
forged map trees, infinite values, async timing or retained memory. Additional
protected-variable raising/weakening/merge combinations remain deferred.
