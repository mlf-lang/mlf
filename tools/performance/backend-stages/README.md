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

Before a large diagnostic, qualify the complete runner on the authored
`Smoke.hs` main crate with the same producer and fixed-dependency setup:

```sh
python3 -B tools/performance/backend-stages/smoke.py \
  --producer /path/to/producer \
  --producer-source /path/to/producer-checkout \
  --setup /path/to/compiler-shapes-setup/setup.json \
  --output /path/to/fresh-small-qualification
```

This compiles a fresh target crate, runs all diagnostic controls and byte
comparison, and builds/runs only the small emitted program with Clang `-O2`.
Its independently authored output is `backend λ` followed by `42`, each on a
line. This is a tooling/semantic qualification, not a compiler-generation or
performance comparison. Preserve the setup's workspace toolchain environment
(`PATH`, `LD_LIBRARY_PATH`, `LIBRARY_PATH`, `PKG_CONFIG_PATH` when applicable).

## Qualification on 2026-11-10

The OPAQUE probe and complete small-crate runner passed against authenticated
current-main producer `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`, GHC 9.14.1
ordinary O2, and Clang 19.1.7. All five target groups were inferred freshly.
The 26 nested-bottom and two total controls passed; ordinary and diagnostic
emission produced exactly the same 128,805 LLVM bytes. The resulting small
native executable produced the independently specified two output lines.

The largest sampled single-command process-tree RSS was 451,817,472 bytes
while linking the probe. Sampling can miss short peaks; the outer orchestration
row does not aggregate the separately guarded nested command groups. Every
command exited successfully and recorded no terminal live descendants. The
coordinated shared resource lock and producer lock were both checked released.
See [results.json](results.json) for the public qualification summary.
Original raw receipts remain local; the summary records their exact SHA-256
identities without publishing absolute paths or tool/object inventories.
This publication does not durably preserve the raw receipts. Their hashes
cannot restore their contents; if local evidence is lost, rerun `smoke.py`
and retain the newly identified qualification before relying on it.

This qualifies the diagnostic tooling only. The current full 90-module target
did not produce a checked artifact before the existing 600-second frontend
limit, so no complete-workload backend profile or performance improvement is
claimed. Production backend changes remain deferred until that input exists.
