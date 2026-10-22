# Bootstrapping the process utility

The released v0.3.0 seed does not recognize primitive 82 (`processSupervisor`).
Do not build the final compiler directly with that seed and claim async support.
Use the explicit two-stage transition on POSIX:

```sh
export MLF_COMPILER=/absolute/path/to/released-seed/libexec/emlf
export MLF_PACKAGE_MANAGER=/absolute/path/to/released-seed/libexec/mlfpkg
export MLF_GC_PREFIX=/absolute/path/to/bdwgc
scripts/bootstrap-async.sh
export MLF_COMPILER="$PWD/.mlf-build/async-bootstrap/stage2"
```

The script requires Clang, GMP, BDWGC and pkg-config.
`MLF_ASYNC_BOOTSTRAP_DIR` and `CC` override output directory/compiler. It uses
crate builds instead of monolithic emission to bound compiler memory. A fresh
source snapshot and minimal seed-schema manifest isolate compatibility changes
from the working tree; the snapshot and build reports remain as evidence.

Stage 1 uses the ordinary source catalogue and native backend, with only
`Bootstrap.ProcessHost` replaced in that snapshot by `bootstrap/seed-compat`. Its interpreter
returns an explicit unsupported error for the new primitive. Stage 2 is built
with the real host source restored and uses the actual in-process supervisor. The script
checks the stage-2 interpreter's protocol capability before reporting success.
Keep the shim out of normal builds and release packages' module search paths.
The temporary manifest omits per-executable dependency fields unsupported by
the released manager; it changes no production package metadata.

The compiler emits a new runtime ABI guard. Linking new output with an old
runtime fails rather than indexing past the old primitive table. Old seed
output retains the old compact guard and still links with the new runtime.
The runtime includes the supervisor implementation directly, so existing
single-runtime-object build and package paths remain usable.

The existing static runner remains available to released-seed package-manager
workflows. The new `mlf-async` package is separate from compiler/package-manager
runtime dependencies. A new seed must be qualified before removing this
transition path. POSIX stage-2 qualification does not establish Windows
bootstrap qualification; that remains part of platform validation.

See [the public API and lifetime contract](async-process.md),
[the primitive transport specification](../bootstrap/RUNTIME.txt), and
`tools/release/test-async-process.sh` for checked-interpreter/native fixtures.
