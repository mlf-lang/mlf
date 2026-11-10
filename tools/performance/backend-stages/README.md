# Checked-to-LLVM diagnostic stages

This probe links the **unchanged authenticated ordinary O2 producer objects**.
It compiles only its diagnostic `Main` and the normal C transport files, and
never builds native A/B generations or runs a self-host fixed point.

It separates these forced boundaries:

1. Load the transitive interfaces and objects, link checked terms, then traverse
   the complete checked term, types, computations and declarations.
2. Construct and force the constructor table.
3. Erase the checked term.
4. Run the production owned-term optimizer.
5. Run the production strict-wrapper/representation optimizer.
6. Run the production code generator and force every output string.
7. Write the exact LLVM chunks through the production String IO primitive.

Each pure boundary has a second traversal of the already evaluated result.
The checkpoint uses the pinned GHC 9.14 `OPAQUE` boundary to prevent inlining,
specialization and worker/wrapper transformation from exposing the pure
traversal at its calling sites. String visitors force the host representation
and scalar length, not a scan of every byte or the lazy scalar-offset index.
The final raw-byte comparison is a separate output check.
The visitors have no catch-all alternative for compiler datatypes, compile
with exhaustive-pattern errors, and are checked with 26 nested-bottom and two
total-value controls. The private constructor-table policy is reproduced in
this diagnostic only; no successful result is accepted unless the complete
emitted LLVM is **byte-identical to a fresh ordinary compiler invocation**.
The first boundary deliberately combines decode/link/forcing rather than
claiming that an outer `Right` means a lazy decoded object was fully forced.

## Interpretation

These are diagnostic intervals, **not ordinary compilation latency, exclusive
costs, optimization speedup evidence, or a sum of ordinary phase costs**.
Traversals, retention of intermediate values, and changed evaluation order
perturb allocation and GC. The second traversal is a useful control, not a
quantity to blindly subtract. `generate` includes worker/kernel analysis.
The ordinary emission is an equivalence control, not a timing baseline.
A performance claim still needs a separate predeclared ordinary comparison.

## Run

Use a current authenticated `tools/shared/build.py --bootstrap-only` O2
producer and a checked crate for that exact implementation. Do not run during
another worker's timing window.

```sh
python3 -B tools/performance/backend-stages/test_runner.py
python3 -B tools/performance/backend-stages/run.py \
  --producer /path/to/producer \
  --producer-source /path/to/producer-checkout \
  --checked-interface /path/to/unit.mlfci \
  --output /path/to/fresh-backend-diagnostic
```

The runner authenticates the producer, compares this checkout's production
source/configuration bytes, freezes the complete transitive interface/object
inventory, and checks those inputs again after execution. It reuses the
existing bounded process runner: 600 seconds, 5 GiB sampled process-tree RSS,
6 GiB per-process address space where supported, 5 GiB disk and 3 GiB available
host-memory floors. No limit is raised. A serial lock next to the shared
producer guards other runs of this tool; coordinate with other harnesses too.

`receipt.json` records completion, source/tool/object pins, raw command logs,
phase intervals and output equality. A failed command, missing or reordered
marker, changed input or different LLVM fails closed. Source paths containing
newlines are explicitly rejected. Fast Python tests validate bookkeeping only;
they do **not** substitute for compiling/running the probe and LLVM comparison.
