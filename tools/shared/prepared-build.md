# Default compiler installation

The public shared build installs the complete explicit `mlf-foundation` package
inventory with implicit Prelude support and its native runtime by default:

```
python3 tools/shared/build.py --build-dir FRESH_INSTALL
FRESH_INSTALL/bin/emlf USER.emlf -o program
```

`--native-config CONFIG.json` selects an explicit native toolchain; otherwise
Clang and the GMP/BDWGC development packages are discovered through `pkg-config`.
Public installations default to GHC `-O2`; explicit `--bootstrap-only` and
`--typecheck-only` development builds default to `-O0`. An explicit
`--optimization 0` or `--optimization 2` is honored on either route. Fixed library and
runtime objects always use ordinary Clang `-O2`. Fresh user programs are inferred,
checked, emitted and compiled on every invocation, with one ordinary Clang `-O2`
job. Default source roots belong to the installation; explicit user roots retain
ordinary resolution semantics rather than being relabeled as installed sources.

Selected small builtin methods and dictionaries retain their checked definitions
inside the fresh user compilation so ordinary optimization can specialize numeric
and IO loops. These definitions come from the verified fixed builtin object and
are composed with the independently checked fresh root; they are not cached user
code. Remaining selected
standard-library exports and the runtime use the installed native objects.
Per-program receipts distinguish `builtin_inline_count`, `native_export_count`,
and `fixed_runtime_reused`, so builtin unfolding is not reported as a native export
reuse count. `builtin_inline_count` counts referenced builtin import keys that
were substituted, not unused bindings removed from a prefix.

Each program compilation retains a fresh hidden `.emlf-<output>-N` directory
beside its output, containing LLVM, objects, logs, and the receipt.
`--build-dir FRESH_DIRECTORY` selects an explicit fresh location instead.

`FRESH_INSTALL/bin` and `FRESH_INSTALL/receipt.json` are the public output paths.
The canonical owned sources live in `FRESH_INSTALL/sources`; run source-bound
qualification tools from that tree. The internal final build uses explicit
`--bootstrap-only` to avoid recursively preparing another standard library.
Direct-source CI and bootstrap development also select `--bootstrap-only`;
`--typecheck-only` remains a low-level check, not an installation.

Run the maintained native and installed-frontend controls against that exact
producer. The frontend option is required here: it checks implicit Prelude,
partial installed imports, new user datatypes, instance visibility, exact source
admission, and explicit-source precedence using fresh fixtures. The same gate
checks the boxed cross-object ABI and lazy fields at Clang `-O0` and `-O2`.

```
PYTHONDONTWRITEBYTECODE=1 python3 -B FRESH_INSTALL/sources/tools/shared/test_native_library.py \
  --build-receipt FRESH_INSTALL/receipt.json --output FRESH_CONTROLS \
  --clang clang --gc-prefix /path/to/bdw-gc \
  --frontend-source-root FRESH_INSTALL/sources/libraries/mlf-foundation
```

Use the owned script and disable Python bytecode writes so the immutable source
inventory stays unchanged. This gate links independent fixtures against the
authenticated compiler objects; it never rebuilds compiler modules. The O2 CI
shard runs both the bootstrap gate and this public default-installation gate.

This qualified installation currently binds its fixed absolute prefix and
source roots. Keep its native assets and evidence at that prefix. Copying only
its binary into an unrelated release bundle is unsupported; this change does
not silently relocate or publish the native release package.

# Explicit fixed-library builds

`build_prepared.py` builds a GHC `-O2` compiler using the ordinary shared
builder and a freshly generated fixed-library registry. Specify a library
manifest with an explicit module inventory and one or more `--module` roots:

```
python3 tools/shared/build_prepared.py \
  --library-manifest PATH/TO/mlf-package.json --module MODULE \
  --ghc /path/to/ghc --cc /path/to/cc \
  --output .mlf-build/prepared-install
```

The output must be new. Keep it outside the checkout or inside its ignored
`.mlf-build` directory. The library manifest and sources must belong to the
checkout. The full tracked and nonignored source inventory is copied into
`OUTPUT/sources`, preserving bytes and file modes. Missing files and symlinks
are rejected. Only the canonical `bootstrap/MLF/PreparedLibraryData.hs` is
replaced. Build products stay outside that source tree.

The wrapper stages the complete nongenerated input identity, compiles the
producer, generates fixed-library artifacts, rebuilds the producer with fresh
objects and query storage, and compares exact regenerated output bytes at the
same paths. It then invokes the owned tree's normal `tools/shared/build.py`.
The result is `OUTPUT/compiler/bin/emlf`; its authenticated build receipt is
`OUTPUT/compiler/receipt.json`.

Source lexical paths default to the original absolute manifest directory.
`--lexical-root` preserves an explicitly supplied ordinary loader prefix,
including dot segments. Select the prefix used by subsequent compiler calls.
Neither the registry nor dependency paths are relocatable. Keep the owned job
and its evidence together. Preparation caches no user program, and runtime
admission retains the ordinary source, dependency, builtin and target checks.

Both normal `build.py` and `test_direct.py` verify prepared evidence. A
populated registry without a complete owned inventory, frozen identity and
successful independent regeneration is rejected even if builtin verification
passes. The exact committed empty registry still supports ordinary builds.
This is locally authenticated build evidence, not a third-party signature or a
claim of native-host qualification. Run the ordinary direct and target tests
against the resulting compiler before making performance or correctness claims.

Fast controls: `python3 tools/shared/test_prepared_verification.py`.

For a fixed native installation, add `--native-config CONFIG.json`. This is an
installation step: no user program is supplied. The config contains `clang`,
`runtime_flags` (joined `-I...`/`-D...` arguments), and `link_args` (absolute
library files and optional `-lm`). Use explicit GMP and GC library filenames so
link dependency identities are unambiguous. The installer compiles the checked
fixed library and runtime using ordinary Clang `-O2`, independently rebuilds its
GHC producer and both native objects, and compares same-path output bytes before
sealing `MLF.PreparedNativeData`. The final compiler still goes through the full
normal GHC build, shared syntax/signature checks and builtin/prepared gates.

The native manifest records the typed exports and constructor layout, exact
object and link-library hashes, target layout, Clang identity and link arguments.
The compiler's native mode authenticates the sealed manifest and its fixed input
files; callers cannot select another manifest. A fresh user program is compiled
and optimized on every invocation. The generic native program driver uses one
ordinary Clang `-O2` job for that fresh program, then links installed fixed
objects. Installation costs and per-program costs are distinct and must be
reported separately. The standalone LLVM mode remains available.

This is local reproducible-build evidence, not a signing authority: modifying
all verifier source, compiler source and receipts coherently is outside this
local trust model. Arbitrary user manifests, changed native objects, incomplete
producer records, missing independent output comparisons, and a populated native
registry without its owned build evidence are rejected.

For an explicitly prepared legacy installation, the optional Python diagnostic
driver also builds a fresh user program. Normal default installations use
`INSTALL/bin/emlf USER.emlf -o program` directly; no Python helper is required.
The legacy driver command is:

```
python3 tools/shared/build_native_program.py \
  --compiler INSTALL/compiler/bin/emlf --source USER.emlf \
  -i /exact/installed/library/source/root --output program \
  --build-dir FRESH_BUILD_DIRECTORY
```

The driver obtains authenticated installation information, emits the fresh user
LLVM module, invokes exactly one ordinary Clang `-O2` compilation, and links the
installed objects. Measure the entire driver invocation to include metadata,
file validation, fresh frontend/emission, compilation, linking and publication.

The complete typed native metadata stays in installation evidence. The installed
compiler seals a small `runtime-contract.json` projection containing identities,
ABI/target fields, objects, tool and link inputs. Independent regeneration
compares both files; the normal verifier re-derives the compact projection from
the authenticated full manifest. Per-program validation hashes the sealed
compact contract and native/link files without repeatedly rendering the fixed
library's full type metadata.
