# Native artifact gate: bounded modular compilation

The native artifact gate keeps the complete original `RawBinaryShared.hs` fixture,
its exact reviewed 46-module source closure, both GHC fixtures and every existing
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

## Maintained route and evidence

The runner now derives the transitive source closure from the authenticated
shared manifest and actual fixture. It requires all 46 reviewed modules, verifies
module headers, rejects missing or unsafe source paths, and records each source's
bytes and SHA-256. The length-framed MLF-CRATE-1 specification uses the same Main,
fresh inference-cache and builtin paths entirely inside the guarded output.
There are no dependency artifacts or previously installed library inputs.

The original authenticated `emlf` runs `--compile-crate` and then
`--crate-to-llvm`. The first command must report every group inferred and zero
reused groups. Fresh interface/object/query and builtin artifacts are required;
the complete generated crate/cache inventory is hashed and checked afterward.
The captured LLVM is consumed directly by the unchanged clang/runtime/GMP/GC
link, without duplicating IR or moving scratch outside the output budget.
All original raw-byte, wire, typed, public-pair, partial-write and distribution
checks remain mandatory on the same qualified GHC/native fixtures.

The source/module/spec admission and strict cold-query controls run in normal
and Python optimized modes. They do not substitute for actual compiler/native
execution. The build receipt continues to authenticate the original producer;
no production compiler semantics or builtin-key optimization changes are part
of this migration.

## Resource scope

The CI gate keeps the 1800s overall deadline, per-process 6 GiB address-space,
5 GiB process-tree RSS, 3 GiB available-memory floor and 4 GiB free-disk floor.
Modular compile-crate has a 900s subdeadline and crate-to-LLVM has 300s. Existing
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
