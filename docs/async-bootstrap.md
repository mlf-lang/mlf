# Bootstrapping the process utility

The released v0.3.0 seed does not recognize primitive 82 (`processSupervisor`)
or the typed completion/timer primitives 83–94.
Do not build the final compiler directly with that seed and claim async support.
Use the explicit two-stage transition on POSIX:

```sh
export MLF_COMPILER=/absolute/path/to/released-seed/libexec/emlf
export MLF_PACKAGE_MANAGER=/absolute/path/to/released-seed/libexec/mlfpkg
export MLF_GC_PREFIX=/absolute/path/to/bdwgc
scripts/bootstrap-async.sh
export MLF_COMPILER="$PWD/.mlf-build/async-bootstrap/stage2"
export MLF_PACKAGE_MANAGER="$(cat "$PWD/.mlf-build/async-bootstrap/manager.path")"
```

The script requires Clang, GMP, BDWGC, pkg-config and `shasum`.
`MLF_ASYNC_BOOTSTRAP_DIR` and `CC` override output directory/compiler. It uses
crate builds instead of monolithic emission to bound compiler memory. A fresh
source snapshot and minimal seed-schema manifest isolate compatibility changes
from the working tree; the snapshot and build reports remain as evidence.
Snapshots have content-addressed names and separate stage-1/stage-2 source
trees. Retrying with unchanged input reuses those paths and completed crate
artifacts. The script rejects source changes detected while copying a snapshot.
It defaults `GC_FREE_SPACE_DIVISOR` to 8 to collect more frequently on smaller
bootstrap hosts, while honoring an explicitly selected value.

Stage 1 uses the ordinary source catalogue and native backend, with only
`Bootstrap.ProcessHost` replaced in that snapshot by `bootstrap/seed-compat`. Its interpreter
returns an explicit unsupported error for the new primitive. Before stage 2,
the released compiler and manager also build a matching `mlfpkg` from the
snapshot. The released manager cannot decode the stage-1 prelude's new
primitive inventory, so it cannot validate stage-2 dependency closures. The
matching manager retains those validation checks and uses a protocol-1 native
build runner compiled from the same snapshot. Stage 2 is built
from the unchanged native snapshot and uses the actual in-process supervisor. The script
checks the stage-2 interpreter's protocol capability before reporting success.
Keep the shim out of normal builds and release packages' module search paths.
The temporary manifest omits per-executable dependency fields unsupported by
the released manager; it changes no production package metadata.
Use the matching manager for subsequent package builds with the new compiler;
switching back to the released manager would reintroduce the interface mismatch.

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

On 2026-10-23, the exact production bootstrap completed on Linux from the
released v0.3.0 seed with a fresh output and cache. Its stage-2 compiler and
matching manager then passed the typed completion, Process, Task and
checked-package gates. The stage-2 SHA-256 is
`435204ff829624ffebba7b3515c5b538bcd9548f7edc51d12e6b535451deff6a`.
This qualifies the Linux bootstrap path; other platforms and broader compiler
regressions are reported separately. The completed receipt is
`.mlf-build/async-production-bootstrap-20261023T0422Z/qualification.json`.

See [the public API and lifetime contract](async-process.md),
[the primitive transport specification](../bootstrap/RUNTIME.txt), and
`tools/release/test-async-process.sh` for checked-interpreter/native fixtures.
