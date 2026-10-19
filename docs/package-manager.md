# Local package manager (format 1)

`mlfpkg` builds MLF packages and runs their tests without invoking Cabal. It is
written in MLF under `package/`. JSON parsing, local dependency resolution,
content-addressed caching, compilation, linking, and test orchestration all run
in the native MLF executable. The source-tree `mlfpkg` is a thin shell launcher;
it never invokes a Python package-manager implementation. Parsing, inference,
checked xMLF linking, and LLVM generation use the selected MLF compiler. It uses only local dependencies
and installed tools. It never downloads a compiler or a dependency.

On Windows, use native `mlfpkg.exe` with `mlf-host.exe`, native `pkg-config`,
MinGW Clang and the GMP/BDWGC SDK described in the
[Windows guide](windows.md#package-manager). The source launchers are
`mlfpkg.ps1` and `mlfpkg.cmd`; `scripts/bootstrap-package-windows.ps1` builds
the manager from an existing native MLF compiler. Windows supports `plan`,
`lock`, `build`, ordinary package `test`, and `run`, including `.exe` publication,
runtime DLLs, drive/UNC paths, and Unicode. Set `MLF_NATIVE_PREFIX` to the SDK
root when running a manager built outside that SDK, and `MLF_CLANG` to the
MinGW Clang executable. The six internal compiler-test groups below still
require their POSIX transports; they are not Windows release qualification.

## Build and test this compiler

Provide a working native MLF compiler as the bootstrap seed, Clang, GMP with
`pkg-config` metadata, and a local BDWGC installation:

```sh
export MLF_COMPILER=/path/to/emlf
export MLF_GC_PREFIX=/path/to/bdwgc-install
./scripts/bootstrap-package.sh
./mlfpkg build
./.mlf-build/bin/emlf --help
./mlfpkg --timeout 21600 test
```

The manager automatically uses a complete `bdwgc-*-install` installation under
the root package's `dist-newstyle/bootstrap-deps` when no prefix is selected.
`--gc-prefix` overrides `MLF_GC_PREFIX`; the selected prefix is also inherited by
test commands and nested builds. Multiple local installations require an explicit
selection. Otherwise it uses `bdw-gc.pc` on `PKG_CONFIG_PATH`.
The one-time bootstrap script still needs `MLF_GC_PREFIX` or `bdw-gc.pc`.
`--compiler`, `--gc-prefix`, `--runtime`,
`--clang`, and `--pkg-config` can select explicit tools. Global options precede
the command. The build needs neither GHC nor Cabal; it compiles
`bootstrap/Main.emlf` and `package/Main.emlf` against the local `mlf-bootstrap`
and `mlf-package-tools` packages. The one-time shell bootstrap only compiles and
links the manager; it has no manifest or dependency logic. Its seed must support
the host IO primitives listed below. Rerun the bootstrap script after changing
manager sources, or select the newly built `.mlf-build/bin/mlfpkg` through
`MLF_PACKAGE_MANAGER`. That environment variable selects an already-built manager.

When building the `mlf-compiler` checkout without `--compiler` or `MLF_COMPILER`,
the manager first uses `bin/emlf` in the selected build directory, then
`.mlf-build/bin/emlf` and `.mlf-build/mlf-native/bin/emlf` in the checkout, before
searching `PATH`. Explicit compiler selections take precedence. Other packages
default to `emlf` on `PATH`.

Compiler tests are written in MLF under `tests/` and built as the local
`mlf-tests` package. The root commands use the selected native compiler and MLF
package manager. GHC, Cabal, and Python are not test prerequisites. Clang builds
the retained C ABI probes and binary/process transports. The probes retain
their low-level ABI checks; MLF runs them and checks their status, output,
error modes, and allocation accounting.

The original Haskell and Python files remain as migration references. Expected
parity types remain immutable Haskell-seed oracle data. Exhaustive and seeded
input generators and independent Algorithm W execute in MLF. A frozen test
module checks target terms. Execution uses native interpreter and LLVM drivers
for both runtime layouts.

The root manifest defines these selectable tests:

| Target | Validation |
| --- | --- |
| `unit` | Compiler unit suite, Figure 12 expectations, native benchmark/bootstrap/release harness tests |
| `packages` | Real compiler tests of local packages, cache invalidation, failures, and both backends |
| `self-host` | Rebuild the compiler with the newly built compiler and compare LLVM for a fixed point |
| `parity` | Fresh independent corpus export and target checker; full acceptance/rejection and runtime parity |
| `backends` | Full interpreter/LLVM matrix for both standard and compact GC layouts |
| `port` | All compiler-port fixtures on native interpreter/LLVM backends, with ported reference oracles |

For example, `./mlfpkg test --target unit --target packages` selects two groups.
Plain `test` runs every declared group. Tests are always executed; successful
results are not cached. Commands, tool/source hashes, cache decisions, and test
results are recorded in `.mlf-build/build-report.json`; compiler groups also
write their detailed evidence under `.mlf-build/compiler-tests/`.
The full port matrix includes large graph programs running inside the native
interpreter. The timeout above allows the complete suite to finish while each
fixture keeps its original execution limit. See
[the verified native coverage](../tests/README.md).

The compiler executable explicitly uses `"link": "separate"` and
`"profile": "compiler"`. Per-module inference releases each graph before the
next process; checked objects and interfaces are validated again when linked.
This lowers cold bootstrap memory while retaining independent xMLF checking,
inferred-type agreement, source-erasure checks, and module boundaries. The
package-manager executable keeps `"link": "source"`. See the
[bootstrap memory measurements](../tools/profile/results/2026-10-19-bootstrap-memory/README.md)
for the measured memory/time tradeoff. The compiler profile retains the existing
pipeline and compact BDWGC runtime. Ordinary packages default to separate
`.mlfi`/`.mlfo` compilation. Test executables use separate compilation and interface/object files. Compiler
profiles use a 256 MiB stack on Darwin and Windows; native test drivers also use
it on Darwin. Interface
fingerprints force their accumulators at each scalar to bound deferred
arithmetic in large serialized objects.


## Local packages

The complete example in `examples/packages` has a three-package dependency
chain: application → greeting → message. It uses an algebraic datatype and
`do` notation.

```sh
./mlfpkg --manifest examples/packages/mlf-package.json plan
./mlfpkg --manifest examples/packages/mlf-package.json build
./mlfpkg --manifest examples/packages/mlf-package.json test
./mlfpkg --manifest examples/packages/mlf-package.json run hello
```

Each package has `mlf-package.json`:

```json
{
  "format": 1,
  "name": "application",
  "version": "0.1.0",
  "dependencies": {"greeting": {"path": "../greeting"}},
  "executables": {"hello": {"main": "Main.emlf"}},
  "tests": {
    "hello": {"main": "Main.emlf", "stdout": "Hello!\n"}
  }
}
```

A library lists its modules explicitly:

```json
{
  "format": 1,
  "name": "greeting",
  "version": "0.1.0",
  "library": {"modules": {"Greeting": "src/Greeting.emlf"}}
}
```

Dependency paths resolve relative to the declaring manifest, not the current
directory. Dependency keys must equal the dependency's declared package name.
Diamond dependencies at the same canonical path are built once. Package cycles,
module cycles, duplicate package identities at different paths, and conflicting
module names are errors. This version permits one provider per module name in
the graph; it does not implement package-qualified imports or multiple versions
of the same package.

Library modules are public to direct dependencies. Function/type visibility
still follows MLF module export lists. Importing a transitive dependency directly
requires adding it to `dependencies`. `Prelude` is built in and cannot be
redefined. Module names in manifests use ASCII Haskell-style names, such as
`Geometry.Point`. Source files, including symlink targets, must stay within their
declaring package. Local dependency paths can point outside the root package.

Executables and native tests can declare private `modules` using the same map,
and accept `link` (`separate` or `source`), `profile` (`standard` or `compiler`),
and `no-prelude` (boolean). `no-prelude` applies to the complete target build.
Native tests require `stdout` and optionally accept `stdin` and `arguments`.
They execute through both the interpreter and LLVM and assert the prescribed
output. `run TARGET -- ARG...` passes arguments to the native executable.

Command tests are useful for an existing oracle or test harness:

```json
{
  "requires": ["hello", "check"],
  "command": ["{bin:check}", "{bin:hello}"]
}
```

Commands run from the package directory as argument arrays, without shell
expansion. `{root}`, `{build}`, `{python}`, and `{bin:NAME}` are supported; each
binary placeholder must be listed in `requires`. A nonzero exit fails the test.
Only the selected root package's tests execute; dependency test hooks are not
run implicitly. As with running a local program, command tests execute the code
in the package you selected.

## Caching and locks

Builds use isolated source/import snapshots. Ambient source directories cannot
satisfy undeclared imports. Libraries compile in dependency order, consumers read
interfaces, and final linking checks the matching objects. Whole-program mode
uses the same resolved source graph. Both routes retain the compiler's checks.

Cache keys include source content, transitive interfaces/objects, compiler and
build-tool identities, runtime sources, native library fingerprints, and build
options. Cached artifact bytes are rehashed before reuse. Implementation changes
conservatively invalidate dependents, including when the public type is
unchanged. A build directory has a process lock. Failed compilation does not
replace an existing working executable, and incomplete artifacts are not cached.

`./mlfpkg lock` writes `mlf.lock`, recording local paths relative to the root,
versions, manifest hashes, and declared source hashes. `./mlfpkg --locked build`
or `test` refuses changes until you review them and run `lock` again. The lock
does not fetch or restore source files. Unlocked builds use current local source;
they do not silently rewrite a checked-in lock. `plan` resolves and validates
without executing compilers or test commands.

Artifacts default to `.mlf-build` beside the selected manifest; `--build-dir`
chooses another directory. This first version supports POSIX hosts, local source
packages, executable/library builds, and tests. Registry publishing, remote
dependencies, dependency version solving, installation, cross compilation,
and native object-per-module linking are outside format 1. `--timeout` accepts
positive integer seconds and applies to build commands and test processes.
A timed-out process group is killed and returns status 124.

## Host IO primitives

The language now provides `getEnv`, `setEnv`, `unsetEnv`, `directoryExists`,
`listDirectory`, `fileDigest`, `acquireFileLock`, `releaseFileLock`, and
`runProcess`. The checked interpreter and both native runtime layouts implement
them. `fileDigest` streams arbitrary binary files and returns lowercase SHA-256.
Directory listing returns NUL-terminated names; `Package.OS.entries` sorts them.
Locks use POSIX advisory file locks, are released on process exit, and do not
survive exec.

`runProcess cwd specification : IO Int` is a low-level argv API. The specification
is NUL-terminated fields: timeout seconds, stdin path, stdout path, stderr path,
executable, and its arguments. Empty paths inherit the respective streams;
matching nonempty stdout/stderr paths merge the streams. `Package.OS.exec`
constructs this representation, rejects NUL in arguments, and preserves spaces,
newlines, Unicode, and shell metacharacters literally. Child processes inherit
the environment. No shell parses the command. General filesystem utilities
(`mkdir`, `cp`, `mv`, `rm`) are executed through this argv API.
