# r21: canonicalize / dense / sparse source-demand split

Diagnostic source only, based on frozen
`f9bdb40a659bfdff4cbb782d438afbb0417dd2e1` plus the complete r17 overlay.
No production optimization, GHC compilation, profiling run, guard, lock or
benchmark is executed or authorized by this package. The leaf-reuse candidate
is not its baseline. Historical runtime admissions/results are not copied.

## Exactly three additional prefixes

`R17-TO-R21.patch` is the complete Haskell delta, only in
`libraries/mlf-inference/Bootstrap/Graph.hs`:

| f9 line | New label | Existing expression |
| --- | --- | --- |
| 1261 | `SOLVER_UNIFY_CANONICALIZE` | lazy `(canonicalize skeleton)` argument |
| 1476 | `SOLVER_UNIFY_REBIND_SPARSE` | sparse arm `rebindSparse old skeleton` |
| 1477 | `SOLVER_UNIFY_REBIND_DENSE` | dense arm `rebindDense old skeleton low high` |

No parentheses, binds, strictness primitives, validation, branch condition, ST
action or expression order are changed. Canonicalize is not forced before
rebinding. The original REBIND and LOCAL_UNIFY prefixes remain. SCC insertion
can nevertheless affect GHC optimization, allocation, sharing, residency and
asynchronous behavior; textual inversion is not an operational-equivalence proof.

All **38 original edits** are retained as exact ordered prefixes of each file's
edit list. Combined inventory: **41 edits, 14 fine sites, 13 fine labels**;
the original 24 coarse labels and 97 files / 95-module union / 94 Emlf / 60
generator closure remain exact. `r16_fine` schema/key is retained with extension
`rebind-subphases-r21`; counts and expected sites are extended, not relaxed.
Unique anchors, exact byte/line spans and hashes are in `insertion-map.json`.

Static preview proofs:

1. Strip the three new tokens to recover the exact r17 mirror.
2. Strip all fourteen fine tokens to recover the exact original coarse mirror.
3. Apply the unchanged original inverse to recover every pinned f9 byte.

`preview-mirror` passes the original exact inventory/manifest/patch/inverse
verifier. It is not an admitted runtime directory. Parent spans are recomputed
to include nested child tokens, without changing their original RHS boundaries.

## Mutually exclusive readout, no inherited-total addition

The original raw parser and nearest-fine-after-deepest-coarse algorithm remain.
Each raw stack node's **self** allocation/ticks goes to exactly one matrix cell.
Coarse boundaries reset fine context; all other coarse contexts remain visible.
Every coarse row and site row conserves alloc/ticks/nodes; global allocation and
ticks agree with the original strict parser. Inherited allocation is never added.

`rebind_family_cells` is only the matrix subset for these four labels:

- CANONICALIZE (C);
- REBIND_DENSE (D);
- REBIND_SPARSE (S);
- original REBIND, now the residual cell.

`rebind_family_by_coarse` sums this disjoint subset. The existing
`local_unify_family_by_coarse` now rolls up eight labels, including all four
above plus the other three unify children and LOCAL_UNIFY residual. Both are
parallel presentations, **not extra allocations to add to the matrix**.
No equality to r17 family bytes is assumed. Canonicalize may retain a creation
stack outside either forcing route; neither its route nor call counts are
invented from entries, allocation size or ancestry missing from the raw stack.
The family is a label grouping, not a proof that every observed rebind call has
a LOCAL_UNIFY ancestor: these helpers are public. Preserve the raw stack/site
evidence for escaped demand and calls from other contexts instead of discarding
them to fit a presumed private API boundary.

All fourteen sites must be declared with reviewed label/module/source extent;
unknown labels, CAF centres, wrong paths/spans and missing declarations reject.
A declared but unobserved sparse route is valid and stays in `unobserved_sites`.
Absent matrix cells are not fabricated as observed zero-allocation executions.
Actual GHC declaration behavior remains to be tested, never synthetically repaired.

## What is unchanged and what was tested

`REUSE-MANIFEST.json` checks the original 24 r13 files, including controller,
guard, oracles, coarse reader, runtime pins, fixtures and original test modules.
`R17-REUSE-MANIFEST.json` records all 28 implementation files: exactly four
change (`insertion-map.json`, `fine_profile.py`, and the two overlay/fine tests).
`R17-IMPLEMENTATION.diff` is their complete diff. No count gate, resource limit,
unit-byte control, source-value/deferred-demand control, provenance requirement,
three-artifact raw comparison or final cleanup gate is removed.

The lightweight suite has **38 static/synthetic tests**: all original 32 method
names retained, plus six covering the exact plan/new inverse and C/D/S/residual
partition, nested coarse reset, escaped canonicalize and unobserved/invalid
new-site declarations. Actual run details are in `tests/new-static-tests.json`.
These are not Haskell passes, a full protocol test receipt or stage admission.
The original 185 protocol tests are preserved but not executed in this source
task, because they include subprocess/guard/lock work.

```sh
PYTHON="$(readlink -f /usr/bin/python3)"
cd "$PACKAGE/implementation"
ASTRA_FROZEN_SOURCE="$F9_SOURCE" "$PYTHON" -B -m unittest -v \
  test_solver_overlay test_fine_profile
```

## Coordinator gates before any actual run

Independent review and a fresh full current-code test inventory are required.
The original controller derives edit counts from the reviewed map; no controller
modification is necessary. Prepare a new absent work root from f9, then bind its
actual plan, source, original f9 ordinary producer, toolchain, environment and
authorized physical locks/epoch. Neither a historical epoch nor this static
preview certifies resource availability or cleanup.

Retain the separate BUILD 600s → QUALIFY 180s → PROBE-CONTROLS 420s →
TARGET-QUALIFICATION 420s → ATTRIBUTION 240s admissions and all original gates.
The existing real 54-case direct and 23-case public-unify fixture source/contracts
remain available separately; this package does not claim they have run on the
new SCC mirror or silently add them to the original controller's pass counts.

After the five real stages and cleanup, use the unchanged fine CLI interface
with authenticated raw-profile, qualified coarse-summary, mirror-manifest and
toolchain hashes. The reader checks raw totals, exact source declarations and
the original byte-unit evidence, but cannot itself establish actual execution,
rerun a byte control, certify cleanup or grant resume authority. Source-demand
allocation is not ordinary exclusive CPU, peak live heap or available savings.

## Public export and latest source-test status

This export contains the complete 28-file implementation/fixture closure, exact
coarse/r16/r17 maps, source proof, reviewed plan and both diffs. It intentionally
omits the 97 copied preview sources, runtime environment, admissions, leases and
private logs. `source-manifest.json` hashes the public files; it is not the local
full-workspace manifest and is not an execution receipt.

After the authoring pass described above, the coordinator independently ran the
complete **223 Python tests (185 original + 38 fine/overlay), all passed**;
10.099 seconds coordinator wall, 9.906 seconds reported by unittest. The exact
current-code binding is summarized in `TEST-STATUS.json`. This later source-test
result does not imply the new Haskell mirror has compiled or produced a real
profile, nor authorize any stage.

To reconstruct the omitted static preview from an exact f9 checkout, set
`F9_SOURCE` and `PACKAGE` to the local absolute paths, then use the unchanged
pure source-mirror tool (no compiler is launched):

```sh
PYTHON="$(readlink -f /usr/bin/python3)"
"$PYTHON" -B "$PACKAGE/implementation/mirror.py" \
  "$F9_SOURCE" "$PACKAGE/preview-mirror"
"$PYTHON" -B "$PACKAGE/implementation/mirror.py" \
  "$F9_SOURCE" "$PACKAGE/preview-mirror" --verify
```

The destination must initially be absent. Then the 38-test command above can
verify every byte/span/inverse. This does not replace the fresh full protocol
receipt, independent review and individual runtime admissions.
