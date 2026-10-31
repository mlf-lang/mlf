# PR25 opt-in resource/native integration — experimental

This is an isolated trial based on PR25 commit
`7bf7ac6db5e3db2daff2e0a1c249e68ae0db2d0c`, not a change to its remote branch.
The actual shared `MLF.Entry.Emlf` CLI has one new opt-in command:

```
emlf [--no-prelude] --emit-resource-json [FILE | --expr SOURCE | -]
```

It parses the real surface source, rejects named modules/imports for this bounded
single-input experiment, and calls the unchanged
`Prepared.compileSourceWithImports`. Only the opaque `Prepared.checkedTerm`
result reaches `MLF.ResourceExport`. The existing inference, evidence,
elaboration, independent ordinary checking and source-erasure checks are not
bypassed or relaxed. This is **not** the older direct-xMLF parser adapter.
No ordinary CLI defaults/help/native-LLVM choices are changed. The hidden
experimental flag is documented here rather than advertised as a production
backend. Default implicit Prelude behavior is preserved; `--no-prelude` is an
explicit choice, not an invisible compiler fallback.

## Reproduce with installed tools

From repository root, with the already installed official GHC9.14.1 and GCC:

The minimal builder also records GHC's actual inferred interfaces for every
resolved shared module and applies the unchanged upstream literal-overloading
audit. The exporter explicitly fixes its two error channels to `Either String`;
an inferred host `IsString`, `Num` or `Fractional` constraint is not admitted.
Missing, stale or rehashed overloaded interface evidence fails preflight.

```sh
python tools/experimental/resource-native/build_compiler.py \
  --ghc /absolute/path/to/ghc-9.14.1 \
  --build-dir /absolute/path/to/a-new-empty-build-directory
python tools/experimental/resource-native/run_native.py --no-prelude \
  --fine --borrow tools/experimental/resource-native/fixtures/unsigned_ring.emlf \
  > /tmp/pr25-resource-native.json
```

The second **single pipeline command** feeds an immutable source snapshot into
that freshly built real compiler, validates its checked-artifact transport,
automatically plans groups/ownership, independently checks the resource IR,
generates actual C callbacks, compiles/links the accepted C runtime and executes
the target. It also separately executes the checked Python IR reference and
requires matching ordered observations/common counters. Output includes source,
compiler, IR, generated C, compiler flags, executable and native runtime hashes.
The compiler is built from the repository's upstream module inventory, not old
vendored compiler sources. No tool download, native standard-library build,
package cache workload, or benchmark is involved.

Use `--profile sanitized` for ASan+UBSan (`detect_leaks=0`, **no LSan claim**).
`--coarse`/`--fine` and `--owned`/`--borrow` are independent; default is
**coarse-owned**, not a claim that experimental fine grouping is always cheaper.
`--build-parent /tmp/name` keeps generated files outside the source tree.
All C-runtime/checker sources and their historical acceptance receipts are local
to this directory; no previous scratch sibling is needed to execute the target.
The historical receipts accept those exact reused components, **not** this new
PR25 compiler integration; its independent review is separate.

## Admitted boundary

**This first trial supports the actual legacy eMLF standalone source frontend,
not the full PR25 package backend.** Marked shared-Haskell `.hs` programs require
named modules and are therefore outside this standalone-only target, as are
module/import graphs. The exporter implementation itself is a shared-Haskell
compiler module; that does not imply target support for all shared-Haskell input.

Closed standalone surface programs whose actual checked elaboration fits:
- builtin `()`, closed monomorphic arrows and single-constructor nominal records;
- saturated constructors, explicit finite cases, typed or inferred `let rec`;
- ordinary lets, concrete monomorphic lambdas/applications; final result `()`;
- lazy recursive knots, including genuine constructor/closure capture cycles.

The ordinary compiler may admit far more than the resource target. For example
`let id x = x in id ()` has a polymorphic runtime annotation and is rejected;
`let f : () -> () = \x -> x in f ()` supplies a concrete binding representation.
The target does **not** silently specialize polymorphism or erase integer data.
Scalars (including arbitrary-precision source Int), sums, parameterized records,
partial constructors, default patterns, effects/FFI/IO and unresolved or abstract
representations reject at their actual stage. Named modules/imports reject before
loading additional files; import provenance is not claimed from one entry hash.
A user datatype named `Unit` remains a distinct nominal identity, not builtin `()`.

Whole syntactic `let rec` blocks conservatively share a knot group; this is not
minimal SCC inference. Holes are all born before lazy RHS construction and raw
fill; cases/applications stay delayed. Productive constructor cycles are different
from `let rec b : () = b in b`, which produces terminal `BUSY`, not successful
cleanup. Fine groups are born only when complete retained support is provably
strictly below the invocation home; otherwise the planner visibly falls back.
The borrow optimization removes temporary operand owner pairs only; published
heap slots always own their targets. It does not lend stack references into heap
fields, infer Once, or avoid the owning promotion needed for case field loans.

## Limits and evidence interpretation

- The compiler host is GHC and may use its GC. The **generated language target**
  uses C malloc/free group ownership, not the GHC runtime, Python execution,
  tracing GC or a cycle collector. The target's complete managed-byte ledger
  includes runtime metadata, handles, slots and diagnostic headers; it excludes
  libc allocator overhead, stack, static descriptors and process RSS.
- The native profile retains diagnostics/counters even with trace disabled.
  This is not an uninstrumented performance benchmark. Unit-only work can be
  eliminated by other compilers, so no speed ratio or overall Perceus superiority
  claim follows from these programs.
- Fine grouping can release real demanded cyclic groups while later work occurs,
  but often increases group/RC/allocation overhead. Borrowing saves inc/dec pairs
  at fixed placement; current loan and owner wrappers have equal malloc size.
- Source is limited to64KiB, transport has finite size/depth bounds, generated
  C bodies to512 pointer cells, GCC reported frames to4096 bytes, tested soft
  stack8192KiB and Force/activation depth128. Unsupported/oversized cases reject;
  these are platform-tested guards, not a C stack-sandbox theorem.
- Build receipts bind exact source inventories and actual observed commands and
  binaries for reproducibility in a cooperative workspace. They are not signed
  compiler attestations against an attacker forging every build output or racing
  filesystem changes. Python module loading uses checked captured source bytes rather than pyc;
  MLF source-module imports are unsupported here.
- Only the focused documented tests are claimed. Full package/self-hosting,
  LLVM/BDWGC, platform and large benchmark campaigns have not been rerun.

The PR25 upstream `mlfpkg lock` regenerates the intentionally changed root source
metadata. Ordinary compiler libraries/checked artifacts remain unchanged.

## Focused validation commands

```
python -m unittest discover -s tools/experimental/resource-native/tests -v
python tools/experimental/resource-native/test_integration.py \
  --build-parent /tmp/pr25-resource-tests --output /tmp/pr25-resource-tests.json
python tools/experimental/resource-native/test_default_cli.py \
  --baseline /absolute/path/to/fresh-pinned-PR25-emlf \
  --output /tmp/pr25-default-cli.json
```

The author suite currently covers7 ordinary Unit programs and1 genuine blackhole
in all4 ownership/group modes (32 native executions),4 rejection controls and3
additional ASan+UBSan builds;25 flag-absent CLI results match the separately
rebuilt pinned baseline byte-for-byte. Six preflight mutations reject, including
changed transport/codegen sentinels that must never execute. The current shared
source parser/name resolver also accepts all129 manifest modules. These counts
are focused evidence only; independent source/order/alias checks are separate.

The comparison baseline is reproducible without copying an edited checkout:

```
python tools/experimental/resource-native/build_baseline.py \
  --ghc /absolute/path/to/ghc-9.14.1 \
  --directory /absolute/path/to/a-new-empty-baseline-directory
```

This extracts the exact pinned git object into a new directory, builds only its
original `emlf` closure, and records the archive, source inputs, commands, binary
and before/after verification in `receipt.json`. The result is `build/emlf` for
the default-CLI test above. It never checks out another branch over the trial.

Independent PR25 cost checks reinforce that this is opt-in, not a cost policy:
fine+borrow peak requested heap bytes worsen in19 of24 accepted Unit cases,
improve in4 and tie in1. A repeated15-knot source improves peak50320→25768
bytes, but total allocated bytes rise177920→214904 and RC updates rise
1022→1469 in each direction. At the same fine placement, borrowing reduces
1529→1469 increments/decrements (60 pairs), with no malloc-byte saving. Neither
these counters nor Unit-only output establish a speed advantage.
