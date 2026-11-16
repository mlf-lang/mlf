# Prepared-projection validation counterexample

**Confirmed in the finite O0/O2 fixture.** This is a hand-constructed test of whether `prepare` success is sufficient to certify every later prepared fallback projection as valid. It is not a production fix, an optimization, or evidence of a reachable user-program bug. Actual Constraint-generated reachability remains unproved.

The ten-node, all-Flexible graph is literal in `tests/Main.hs`. With source 4 and target 2, the observed trace has successful `prepare` and `solverUnify []`, failed ground shortcuts, copies 5/6/7 → 10/11/12, and both prepared fallback gates selected. Its projected local node 6 is bound to node 1, which does not structurally contain it. Local validation, local unification and `instantiateClosedPrepared` each returned exactly:

```text
a type binder must structurally contain its node
```

The complete expected transcript is a literal, not an error obtained from another runtime path. The isolated storage snapshot also captured and reconstructed the projected graph successfully. **Storage admission is not structural graph validity.** The observed trace refutes the unrestricted prepare-sufficiency premise, not the compiler's full generated-constraint contract.

The original snapshot prototype and its 49 finite records are retained unchanged; one new record gives **50 records / 150 sidecars per optimization level**. Each record saves `.actual` and `.expected` before assertion and writes `.result` only after equality. The unchanged 67-byte success marker is in `tests/expected.stdout`. The prototype stores vector cells and rebuilds fresh maps, rather than returning a saved Graph.

## Scope

Main is pinned to `fc300bc9fdc389b585cbef0630fc8915d53e89c5`. No production module is changed. Both fresh ordinary GHC 9.14.1 builds had 16 home modules: 14 unchanged baseline modules plus the prototype and fixture. Both fixtures exited successfully with the exact 67-byte stdout and empty stderr. All 150 sidecars matched across O0/O2, and the 147 sidecars for the old 49 records also matched the earlier snapshot run at both levels. The new 735-byte transcript exactly matched its fixed literal. The independent actual audit verified all 408 saved files (26,678,968 bytes), source identities, resource limits and cleanup. `results/focused.json` records these finite results and evidence hashes, not a performance sample.

Admission uses real `IntMap.valid` and adds strict payload demand. It is a narrower research domain, not arbitrary raw/partial Graph equivalence. `LocalRank` is opaque but not generative per layout; the graph rendering comparator is only justified for these fixed hand values. Snapshot isolation, exact errors and ordinary solver comparisons in this finite corpus do not establish general solver correctness, native behavior, allocation savings or speedup. No validation-removal proposal is included.

## Reproduce from the pinned repository root

Place this directory at `tools/performance/main-baseline-gap-20261114/prepared-projection-validation-counterexample`. Use ordinary GHC **9.14.1**, a C11 compiler and its matching installed `base`, `array`, `bytestring`, `text`, `containers`, and `directory` packages. The following repository-relative recipe has passed shell syntax checking only; it has not itself been run at these public paths. The actual focused experiment used the same source identities and compiler-option pattern in separately controlled fresh paths, with resource supervision. This manual recipe is not that supervisor. Use a fresh output directory; it is not a whole-compiler or native build.

```sh
set -eu
unset GHCRTS GHC_ENVIRONMENT
BUNDLE=tools/performance/main-baseline-gap-20261114/prepared-projection-validation-counterexample
OUT=.prepared-projection-counterexample-work
test ! -e "$OUT"
mkdir -p "$OUT/c" "$OUT/bin"
cc -O2 -std=c11 -Iruntime -c host/ghc/cbits/host.c -o "$OUT/c/host.o"
cc -O2 -std=c11 -Iruntime -c runtime/mlf_process_supervisor.c -o "$OUT/c/supervisor.o"
for opt in 0 2; do
  mkdir -p "$OUT/o$opt" "$OUT/stubs$opt" "$OUT/work$opt"
  ghc --make -j1 -fforce-recomp -XHaskell2010 "-O$opt" \
    -fpedantic-bottoms -fno-state-hack \
    -Werror=incomplete-patterns -Werror=incomplete-uni-patterns \
    -package-env - -clear-package-db -global-package-db -no-user-package-db \
    -hide-all-packages -rtsopts=ignoreAll \
    -i "-i$BUNDLE/tests" "-i$BUNDLE" \
    -ilibraries/mlf-foundation -ilibraries/mlf-inference -ihost/ghc \
    -odir "$OUT/o$opt" -hidir "$OUT/o$opt" -stubdir "$OUT/stubs$opt" \
    -package base -package array -package bytestring -package text \
    -package containers -package directory \
    "$BUNDLE/tests/Main.hs" "$OUT/c/host.o" "$OUT/c/supervisor.o" \
    -o "$OUT/bin/semantic-o$opt"
  (cd "$OUT/work$opt"; "../bin/semantic-o$opt") \
    > "$OUT/run$opt.stdout" 2> "$OUT/run$opt.stderr"
  cmp "$BUNDLE/tests/expected.stdout" "$OUT/run$opt.stdout"
  test ! -s "$OUT/run$opt.stderr"
done
```

After a successful run, each work directory should contain exactly the 50 `.actual`, 50 `.expected`, and 50 `.result` files; every actual must match its expected, every result must be `PASS` plus LF, and corresponding O0/O2 evidence should match. A failure is evidence to retain, not permission to change the literal or skip a check. The completed bounded experiment has no automatic producer, benchmark, native or production follow-up.
