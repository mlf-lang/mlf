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
