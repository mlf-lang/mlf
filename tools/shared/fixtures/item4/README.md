# Focused item-4 contracts

Run from the checkout with the pinned GHC 9.14.1. These fixtures are host-side
probes of the actual compiler modules, not copied implementations or full-corpus
qualification receipts. Each suite compiles into its own output directory.

```sh
python3 tools/shared/test_item4_contracts.py --suite artifact \
  --ghc "$GHC" --build-dir "$OUT/artifact"
python3 tools/shared/test_item4_contracts.py --suite builtin \
  --ghc "$GHC" --build-dir "$OUT/builtin"
python3 tools/shared/test_item4_contracts.py --suite query \
  --ghc "$GHC" --build-dir "$OUT/query"
python3 tools/shared/test_item4_contracts.py --suite interpreter \
  --ghc "$GHC" --build-dir "$OUT/interpreter"
python3 tools/shared/test_item4_contracts.py --suite host \
  --ghc "$GHC" --build-dir "$OUT/host"
python3 tools/shared/test_item4_contracts.py --suite native \
  --gc-prefix "$MLF_GC_PREFIX" --build-dir "$OUT/native"
```

The runner force-recompiles directly from source, records source and tool hashes,
logs commands and outputs, and invalidates a result if its compiled source
closure changed during execution. It stops a command at 1.5 GiB aggregate RSS,
below 3 GiB host available memory, or the configurable 300-second timeout.
Receipts describe the tested snapshot; later source changes require rerunning.
These focused receipts do not replace the stronger complete-toolchain and
package-closure provenance in `tools/shared/build.py`.

- `ArtifactIdentity.hs`: canonical type/constructor/field metadata, module and
  crate interfaces, checked objects, datatype pools, class method/superclass
  transport, stale interface rejection, overloaded-pattern method identities,
  and refutability-sensitive query-key inputs. The handcrafted MonadFail class
  tests only method/superclass transport; it does **not** assert full pinned
  HasCallStack signature equivalence.
- `BuiltinArtifact.hs`: actual builtin Prelude lowering and compilation,
  interface and pooled-object decoding, then linking the restored object.
- `QueryCache.hs`: actual cold inference of canonical lists, warm artifact-cache
  reuse and invalidation after a source-literal mutation.
- `InterpreterIO.hs`: twenty interpreter controls including lazy action/message
  demand, typed IO recovery, fatal panic exclusion and async dispatch reset.
- `HostIO.hs` and `NativeIO.c`: typed IO recovery, handler scope expiry, lazy
  results, nested async cleanup, Unicode scalar text and the wider Char domain.
  Native fatal-error controls run in separate subprocesses.
- `CoreIdentity.hs`: additive canonical registry and append-only primitive ABI
  metadata. This does not establish source inference by itself.

Native IO recovery here is the explicit userError/ioError channel. Operational
HostError failures and pure panic are not claimed to be catchable IO errors.
Standard patterned-do and call-stack evidence require their own frontend and
separate-compilation qualification; successful low-level IO tests alone do not
establish those language-level contracts.

Additional suites cover the managed-call-stack and patterned-do boundary:

- `source` / `SourceSemantics.hs`: actual MLF inference and interpreter checks,
  including overloaded string-pattern row ordering and distinct user types.
- `pattern-do` / `PatternDo.hs`: actual MLF constructor-family refutability,
  delayed lazy/as patterns, custom failure dispatch and hidden constructors.
- `managed` / `ManagedArtifacts.hs`: private evidence versus raw CallStack
  arrows, all source-span fields in keys, delayed-bind scope, intrinsic-reference
  hygiene, managed entity ownership and qualified public method metadata.
- `authority` / `ArtifactAuthority.hs`: source/module ownership checks, distinct
  user lookalikes, rejected private-layout and managed-class forgery, legitimate
  qualified reexports and complete hidden-constructor inventories.
- `separate` / `SeparateCrates.hs`: producer and consumer inferred separately
  against serialized/decoded metadata, then decoded objects linked and run.
  It exercises managed caller evidence, hidden-constructor failure dispatch and
  custom Eq/IsString instance visibility with ordered string-pattern fallback.
- `interpreter-stack`, `host-stack`, `native-stack`: lazy stack/message demand,
  Unicode frame fields, surrogate error messages and scoped failure contexts.

The LLVM runner is separate:

```sh
python3 tools/shared/test_item4_llvm.py --suite stack \
  --ghc "$GHC" --clang "$CLANG" --cc "$CC" \
  --gc-prefix "$MLF_GC_PREFIX" --build-dir "$OUT/llvm-stack"
```

It emits real LLVM for four stack/error modes, checks O0 and O2, and tests
bidirectional **synthetic** missing-ABI-symbol controls. These are not tests
against historical runtime binaries. Native/interpreter/GHC diagnostic text
is checked against each backend's contract, not claimed byte-identical across
backends. Neither this suite nor the explicit managed constraint claims the
whole GHC.Stack API, universal exception recovery, or full-corpus parity.

For repeated inference-heavy suites, `test_item4_optimized.py` supports an
independently measured O2 path with the same correctness flags. An initial run
force-rebuilds its compiler closure; a subsequent run accepts only a successful
seed with identical source, tool and option identities and unchanged object
hashes. It copies objects into a new output directory, always rebuilds Main,
and verifies every inherited object again after compilation and execution.
Explicit C inputs are copied before compilation because GHC otherwise writes
C objects beside their source files despite `-odir`.

```sh
python3 tools/shared/test_item4_optimized.py --suite pattern-do \
  --ghc "$GHC" --build-dir "$OUT/pattern-o2"
python3 tools/shared/test_item4_optimized.py --suite source \
  --ghc "$GHC" --build-dir "$OUT/source-o2" \
  --seed-receipt "$OUT/pattern-o2/receipt.json"
```

These remain focused fixture gates, not full producer qualification. Historical
receipts precede source fixes and must not be relabeled as current; isolated C
object hashes are available only in receipts that explicitly record them.
