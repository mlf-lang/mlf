# Inlining traversal and alias-copy diagnostic

This is a separate GHC diagnostic build of pinned production code. It does not
change compiler modules, expose unchecked production entry points, or measure
ordinary compiler performance. The ordinary producer is authenticated before
and after the run. Its object files are copied into a fresh, separate directory;
only private module names are compiled there.

`instrument.py` requires exact SHA-256 identities for `LLVM/Optimize.hs` and
`LLVM.hs`. It applies uniquely anchored substitutions, records every before and
after block, and reverses the entire edit sequence to recover the original bytes
before compiling. The only change to private LLVM is its module name and the
Optimize import. The checked-link/prepare/lower/codegen path remains unchanged.

The diagnostic records events on the actual demanded production paths:

* `commonCalls` and `substituteUsed`: external roots, recursive node visits,
  zero-use pruning, positive-use visits, recursion depth sum and maximum.
* `substituteUsed.rebuild_parent`: a positive-use non-variable branch invokes
  the existing child rewrite/reconstruction path.
* `identities`, `indexUses`, `passRaw`, `passUsed`, `contractCommonCalls`,
  `singleUseIOPath`, `singleUseBranchPath`: roots, visits, recursion depths.
* `useApplications`: roots and visits along each inspected application spine.
* `copy.<origin>`: roots, node visits/depths, the selected constructor branch,
  fresh ordinary/pattern binders, and rebuilt alternative wrappers. Origins
  distinguish alias elimination, substitution, initial uniqueness, final
  numbering, projections, recursive rewrites, and higher-order specialization.

A root counts a demanded externally initiated traversal; recursive calls do not
increment roots. Depth starts at zero for each root. `visits / roots` describes
mean work per traversal; maximum depth describes the deepest visited path, not
the maximum stack size or full size of untouched subtrees. Each visited copy
node selects exactly one branch: `variable_lookup`, `reuse_leaf`, or one of
`rebuild_abs/app/let/rec/case`. The latter five count logical structural output
construction branches. Variable lookups can return existing replacement values;
leaves can be shared. Fresh binder events and alternative wrappers are separate.
These counters **are not physical heap allocations** and exclude map/list/tuple
allocations and GHC optimizer decisions. Do not report their sum as allocated
nodes or bytes.

Counters never compute an AST size, inspect extra source branches, or force a
map that the original function did not inspect. Each monadic counter wraps the
existing `Fresh` state transition, so shared partially applied actions still
count their demanded executions. Pure counters wrap the original result thunk.
The helper uses `NOINLINE` and diagnostic compilation disables CSE and full
laziness. Nevertheless instrumentation perturbs optimization and runtime cost;
only mechanism counts, not diagnostic timings, are interpreted.

The fixed controls run twice in fresh processes and must produce identical
counts. Zero-use controls put bottoms in term/children/substitution value to
prove pruning does not evaluate them. Positive recursive controls check a
common-call path with a pruned sibling, then a substitution through that path
which copies a lambda and freshens its binder. They compare ordinary results
and fresh seeds and require exact event counts, branch totals, and depths.
The alias control checks exact optimized
structure and the fresh-name seed against ordinary production `identities`,
plus four copied nodes, two reconstructed structural nodes, one fresh binder,
and the expected depths. The runner requires branch totals to equal visits and
rejects any executed unclassified copy origin.

Each of the annotated (`dependency_chain`) and inferred (`inferred_chain`)
checked dependency chains at 32, 128, 512 and 2048 is emitted once through the
ordinary and once through the diagnostic path. Counters reset after ordinary
emission and are read only after the diagnostic UTF-8 output handle closes,
fully consuming all output bytes. The runner requires byte-for-byte equal LLVM
and records its SHA-256. It does not add an AST forcing/size traversal. Existing
checked references are pinned inputs; this experiment does not measure source
inference or regenerate those references.

Run only after the source integration has completed and the diagnostic source
has been reviewed:

```sh
python3 -B tools/performance/inline-traversals/run.py \
  --output .mlf-build/inline-traversals-20261101/run-01
```

The output must be a fresh child of that dedicated scratch directory. The
existing serial guard enforces per-command 600-second, sampled RSS, disk, and
available-memory limits. Every command is saved in the receipt, with `complete`
remaining false on any failure. Source artifacts, checked references and
the complete checked dependency closure are pinned. The source parser follows
the exact `MLFCI-5` length framing solely to discover dependency paths; ordinary
production code still validates checksums, object bindings, and checked terms.
The ordinary producer's complete object inventory must exactly match its
authenticated receipt before copying, with no unexpected files; C objects and
the actual authentication helper are pinned too. `counts.json` contains the eight complete
measurements; `reversible-transformations.json` records the exact edits.
The first guarded execution completed successfully on 2026-11-01; all eight
ordinary/diagnostic outputs were byte-equal and both control processes matched.
See [RESULTS.md](RESULTS.md) for counts, growth, and the limits of interpretation.

Source admission, reversibility, counts, and byte equality use explicit
`ValueError` checks, so `python -O` cannot disable them. The lightweight control
below checks corrupted source, tampered reverse edits, invalid count totals,
missing target counters, differing output bytes, unexpected producer objects,
and complete/cyclic dependency discovery under both normal Python and `-O`:

```sh
python3 -B tools/performance/inline-traversals/test_admission.py
```
