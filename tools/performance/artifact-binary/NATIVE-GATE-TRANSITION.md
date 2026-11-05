# Native artifact gate: bounded modular compilation

The native artifact gate keeps the complete original `RawBinaryShared.hs` fixture,
its exact reviewed 51-module source closure, both GHC fixtures and every existing
binary aggregate assertion. It builds a fresh native executable from current
source and the authenticated current compiler. It does not use an old executable,
an installed standard library, the separate restored 80-module fixture, or a
reduced transport-only test.

## Why the build route changed

CI252 at e996809a failed the monolithic `emlf --emit-llvm` command after 19.37s
with `emlf: out of memory`, before producing LLVM. The original address-space
limit was 6 GiB; sampled whole-process RSS peaked at 4,263,571,456 bytes. The
watchdog did not report a sampled RSS, disk or wall violation. Both GHC fixtures
and the current native runtime had compiled successfully, but the native link
and aggregate had not run.

A separate diagnostic relink kept the compiler source/objects unchanged and
fixed GHC RTS options to `-M3G -c -s`, preserving `-rtsopts=ignoreAll`. It reached
the unchanged 600s frontend wall limit without producing LLVM. Its original
producer was not replaced. This is a failed diagnostic, not a native pass.
The monolithic route's allocation failure and timeout remain unresolved.

A later attempt to put the current 51-module closure into a single crate reached
inference but failed the existing schema-7 open-package expanded-work limit.
The exact diagnostic was tag 430, 3,245 final fragments and 79,995,828 expanded
work against 67,108,864. Each per-body value and interface metadata had passed;
the aggregate object had not been written. The maintained test therefore uses
normal library boundaries instead of one oversized crate. This changes only
the test build plan: production object/query schemas, limits, public artifact
assertions, and on-demand dependency loading remain unchanged.

## Maintained route and evidence

The runner now derives the transitive source closure from the authenticated
shared manifest and actual fixture. It requires all 51 reviewed modules, verifies
module headers, rejects missing or unsafe source paths, and records each source's
bytes and SHA-256. It partitions this exact closure along the six existing
library owners: foundation (13 modules), language-core (4), frontend (10),
xmlf (6), inference (9), crates (8), then the original Main (1). It authenticates
each physical `mlf-package.json`, checks every module's owner/path, and derives
direct dependencies from actual imports, rejecting undeclared or cyclic edges.

Seven length-framed MLF-CRATE-1 specifications compile these source subsets in
dependency order. Each source is compiled once, each component has a fresh
inference cache, and the builtin path is shared entirely inside the guarded
output. The only dependency artifacts are interfaces just produced by prior
components in this run. No installed libraries or replacement Main are inputs.
The final crate-to-LLVM command receives only Main's interface; its formal
artifact dependency graph supplies the original complete closure.

The original authenticated `emlf` runs `--compile-crate` and then
`--crate-to-llvm`. Every component compilation must report every group inferred and zero
reused groups; the receipt retains each report and their sum. Fresh interface/object/query and builtin artifacts are required;
the complete generated crate/cache inventory is hashed and checked afterward.
The captured LLVM is consumed directly by the unchanged clang/runtime/GMP/GC
link, without duplicating IR or moving scratch outside the output budget.
All original raw-byte, wire, typed, public-pair, partial-write and distribution
checks remain mandatory on the same qualified GHC/native fixtures.

The source/module/spec admission and strict cold-query controls run in normal
and Python optimized modes. They do not substitute for actual compiler/native
execution. The current independent typed reader validates all 134 actual emitted
primitive roots (codes 0 through 133), including `PSTToIO`, and separately
rejects -1, 134 and 2147483647. Historical reader snapshots keep their own frozen
ABI bounds. The build receipt continues to authenticate the original producer.
The partition itself changes no compiler semantics, builtin keys, or object and
query budgets.

The independent pair reader requires the actual Session root to use schema 7
and the canonical builtin to retain schema 4. It checks open reference/owner
inventories, physical SHA and the complete normalized interface association.
Twenty mutations repair ordinary CRC and paired SHA before testing semantic
admission. Legacy exports explicitly use the existing closed projection with
its matching interface, require MLFCO-2 and preserve the complete checked linked
term. Portable bundle checks validate and link the full manifest closure using
the explicit supplied-interface API, so virtual release paths are never treated
as local filesystem paths. Missing, duplicated, stale and cyclic dependency
contexts remain negative controls, and unrelated available siblings are excluded.

## Resource scope

The CI gate keeps the 1800s overall deadline, per-process 6 GiB address-space,
5 GiB process-tree RSS, 3 GiB available-memory floor and 4 GiB free-disk floor.
All seven compile-crate commands share one 900s subdeadline, and crate-to-LLVM
has 300s; the compile allowance is not restarted for each library. Existing
compile/link and aggregate deadlines remain subordinate to the overall guard.

The aggregate output allowance is explicitly 640 MiB instead of the old 100 MiB.
This counts the fresh cache, both GHC builds, crate artifacts, LLVM, native
executable, controls and receipts in the same guarded tree. Historical same46
modular build output was 507,285,504 allocated bytes, including about 426 MiB of
inference cache. The complete old aggregate check tree added about 16.3 MiB;
two current GHC fixture builds are conservatively estimated at 34 MiB. This
supports a bounded 640 MiB trial with headroom; it is not proof that a new run
fits. The live guard must stop an overrun. The old output and timing observations
are retained as historical evidence, not rewritten as current measurements.

PR30's QUERY7 study reduced transient key bytes but reported identical retained
Foundation cache sizes. It does not establish a storage reduction for this
46-module native workload. The local shared workspace also remains subject to
its separate 16 GiB aggregate cap and process/lock admission protections.
