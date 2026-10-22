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
[Windows guide](windows.md). The source launchers are
`mlfpkg.ps1` and `mlfpkg.cmd`; `scripts/bootstrap-package-windows.ps1` builds
the manager from an existing native MLF compiler. Windows supports `plan`,
`lock`, `build`, ordinary package `test`, and `run`, including `.exe` publication,
runtime DLLs, drive/UNC paths, and Unicode. Set `MLF_NATIVE_PREFIX` to the SDK
root when running a manager built outside that SDK, and `MLF_CLANG` to the
MinGW Clang executable. The unit/backend/port compiler-test transports below still
require POSIX. Windows release qualification uses the native package and parity
groups plus Windows runtime and relocation checks.

## Build and test this compiler

Provide a working native MLF compiler as the bootstrap seed, Clang, GMP with
`pkg-config` metadata, and a local BDWGC installation:

The seed must implement `--compile-crate`. An earlier native release can bridge
the migration by building the first generation with its matching earlier
`mlfpkg`; see [the seed transition](../README.md#build-and-run). Keep that tool
pair outside the output directory, then select the generated compiler and
manager for subsequent crate builds.

```sh
export MLF_COMPILER=/path/to/emlf
export MLF_GC_PREFIX=/path/to/bdwgc-install
./scripts/bootstrap-package.sh
export MLF_PACKAGE_MANAGER="$PWD/.mlf-build/package-manager/mlfpkg"
./mlfpkg --timeout 21600 --build-dir "$PWD/.mlf-build/native-stage1" build
export MLF_COMPILER="$PWD/.mlf-build/native-stage1/bin/emlf"
export MLF_PACKAGE_MANAGER="$PWD/.mlf-build/native-stage1/bin/mlfpkg"
./mlfpkg --timeout 21600 build
./.mlf-build/bin/emlf --help
./mlfpkg --timeout 21600 test
```

The first generation updates the native code generator; the second builds the
candidate with that generator. Keep the stage-1 input tools in their separate
directory when testing, so the candidate and its fresh self-build can reach the
same LLVM fixed point. See the [root build instructions](../README.md#build-and-run).

The manager automatically uses a complete `bdwgc-*-install` installation under
the root package's `.mlf-build/deps` when no prefix is selected.
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
The test package shares only its support modules; each executable's `modules`
map lists its own test-case dependencies. This keeps unrelated test cases out
of individual test builds while retaining the complete root test inventory.

The Haskell compiler and old Haskell/Python harnesses have been removed.
Shared C fixtures live in `tests/native/`. Expected parity types remain
immutable Haskell-seed oracle data; benchmark baselines are preserved. Exhaustive and seeded
input generators and independent Algorithm W execute in MLF. A frozen test
module checks target terms. Execution uses native interpreter and LLVM drivers
for the compact-GC layout.

The root manifest defines these selectable tests:

| Target | Validation |
| --- | --- |
| `unit` | Compiler unit suite, Figure 12 expectations, native benchmark/bootstrap/release harness tests |
| `packages` | Real compiler tests of local packages, cache invalidation, failures, and both backends |
| `self-host` | Rebuild the compiler with the newly built compiler and compare LLVM and the complete native binary for a fixed point |
| `parity` | Fresh independent corpus export and target checker; full acceptance/rejection and runtime parity |
| `backends` | Full interpreter/LLVM matrix with compact-GC |
| `port` | All compiler-port fixtures through native LLVM, with ported reference oracles |

For example, `./mlfpkg test --target unit --target packages` selects two groups.
Plain `test` runs every declared group. Every selected test command executes;
test-group results are not cached. Checked build artifacts and port preparation
can be shared, while the compact-GC layout and backend executions still run.
Commands, tool/source hashes, cache decisions, and test
results are recorded in `.mlf-build/build-report.json`; compiler groups also
write their detailed evidence under `.mlf-build/compiler-tests/`.
The full port matrix includes large graph programs running inside the native
interpreter. The timeout above allows the complete suite to finish while each
fixture keeps its original execution limit. See
[the verified native coverage](../tests/README.md).

Libraries and targets compile as crates through generated `.mlfci` metadata and
`.mlfco` checked fragments. Declaration SCC inference releases each solver graph
before the next query and persists normalized closed schemes. The final linker
independently checks consumed scheme/layout boundaries and the linked xMLF.
The `compiler` profile selects the compact BDWGC runtime and a 256 MiB stack on
Darwin. The old `link` values `separate` and `source` remain accepted manifest
spellings; both select crate compilation. New manifests can omit `link`.
See [crate compilation](crate-compilation.md) and
[the validation ledger](crate-migration.md). Older bootstrap memory reports
measure the retired per-module pipeline.
Compiler profiles use a 256 MiB stack on Darwin and Windows.

## Native profile-guided construction

Native PGO is optional and applies to one named root executable. Build an
instrumented target with `--pgo-generate TARGET`; train that executable with
`LLVM_PROFILE_FILE` set to a fresh raw profile for each run, merge those profiles
with the matching LLVM installation's `llvm-profdata`, then rebuild with
`--pgo-target TARGET --pgo-use FILE`. These global options precede `build`
or `test`. Clang keeps the ordinary O2 level, and incompatible-profile
warnings fail the build. The options profile the selected executable's LLVM
and C runtime; other targets keep their ordinary native inputs and caches.

The native cache records the profile's canonical path and SHA-256 along with
the actual Clang, source/LLVM, flags, runtime headers and libraries. Changing
profile contents invalidates the selected native stages; an unchanged profile
can reuse them. The manager rehashes the profile before completing a build,
including builds satisfied from cache. MLF inference and LLVM-emission keys
continue to use the actual MLF compiler identity.

For the compiler, the checked construction script builds both native tools,
trains on fifteen existing standalone language examples through stdin, and
independently repeats training, merging and native production. It requires
byte-identical profiles, LLVM, both objects and complete binaries. Benchmark
programs and Snake inputs do not participate:

```sh
export MLF_PACKAGE_MANAGER=/absolute/path/to/current/mlfpkg
scripts/build-compiler-pgo.sh /absolute/path/to/current/emlf \
  /absolute/path/to/llvm/bin/llvm-profdata \
  "$PWD/.mlf-build/compiler-pgo"
```

Use a fresh output directory and a native seed whose code generator has reached
a fixed point. The resulting tools are `build/bin/emlf` and `build/bin/mlfpkg`
under that directory. Preserve its profiles, build reports and `provenance.json`.
The script also requires Node.js for recording and checking construction
provenance. Package dependency, cache and compilation decisions remain in MLF.

When testing the resulting tools through the root manifest, use the same input
seed, build directory, `--pgo-target emlf` and `--pgo-use .../first.profdata`
so the command's required compiler keeps that native configuration. The
`self-host` group reads the candidate's checked artifact provenance and rebuilds
from a fresh directory with the same Clang and profile. It requires equal LLVM
and complete native bytes; independent profile reproduction and the full test
groups are separate checks. The package group exercises real Clang profiling
and therefore also requires `llvm-profdata` on PATH.
On Ubuntu, install both `clang` and `llvm` and put `$(llvm-config --bindir)`
on PATH so profiling and native compilation use the same LLVM installation.

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
duplicate package identities at different paths, and conflicting
module names are errors. This version permits one provider per module name in
the graph; it does not implement package-qualified imports or multiple versions
of the same package.

Modules within a crate may import one another cyclically. Library modules are public to direct dependencies. Function/type visibility
still follows MLF module export lists. Importing a transitive dependency directly
requires adding it to `dependencies`. `Prelude` is built in and cannot be
redefined. Module names in manifests use ASCII Haskell-style names, such as
`Geometry.Point`. Source files, including symlink targets, must stay within their
declaring package. Local dependency paths can point outside the root package.

Executables and native tests can declare private `modules` using the same map,
and accept `link` (`separate` or `source`), `profile` (`compact-gc`, the default, or compatibility alias `compiler`),
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
expansion. `{root}`, `{build}`, `{cache}`, and `{bin:NAME}` are supported; each
binary placeholder must be listed in `requires`. A nonzero exit fails the test.
Only the selected root package's tests execute; dependency test hooks are not
run implicitly. As with running a local program, command tests execute the code
in the package you selected.

## Caching and locks

Builds use explicit crate source inventories. Ambient source directories cannot
satisfy undeclared imports. Libraries compile in crate dependency order;
modules within a crate resolve together without a compilation order. Downstream
inference reads metadata only. Final linking checks the implementation objects.

The outer artifact cache records source content, dependency metadata/objects,
compiler and build-tool identities, runtime sources, native library fingerprints,
and options. `--cache-dir DIR` shares these verified artifacts between build
directories; its default is `BUILD/cache`. Reports and command logs remain in
each build directory, and `cache_directory` records the resolved store. Each
artifact key has a process lock, so concurrent producers publish one complete
artifact. Persistent inference queries live under
`CACHE/.queries/<crate>/<compiler-sha>/`: their keys record resolved syntax and
consumed semantic schemes/layouts, excluding upstream implementation hashes.
The implicit prelude also lives in this store, so deleting a producing build
directory does not remove a shared library's checked dependencies.
Reports distinguish outer artifact hits from actual checked query reuse.
The main build report contains counters, semantic fingerprints and group counts;
its `query_report` paths retain complete per-SCC detail. Each crate artifact also
stores a checked `unit.query-summary.json`, so an outer hit does not parse the
detailed report again. JSON transport scans by scalar offsets and joins string
runs without repeatedly copying the remaining input.
Each crate also records `unit.validation.json`. Its checked/reused object counts
distinguish independent root validation from SHA-verified dependency receipt
reuse; outer hits report no new object checks. Metadata graph and semantic
contract validation still precede dependency reuse.
New `.mlfco` objects pool repeated datatype declarations while retaining separate
interface and implementation contexts and independent fragment checking.
Inference cache entries can obtain identical contexts from their full semantic
key. These encodings reduce repeated artifact text without changing exported
schemes or weakening validation; see [crate compilation](crate-compilation.md).
Cached bytes are checked before reuse. A build directory has a process lock.
Failed compilation does not replace an existing working executable, and
incomplete artifacts are not published.

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
`runProcess`. The checked interpreter and the compact-GC runtime implement
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
