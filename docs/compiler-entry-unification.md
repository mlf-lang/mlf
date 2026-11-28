# Compiling source and package roots

`emlf` accepts a file, an expression, or standard input. `mlfpkg build` obtains its
roots from the package manifest. Both use the crate compiler to prepare declaration
groups, infer their contracts, and produce checked xMLF. The input determines the
root's namespace and dependencies. The requested output determines how to use the
checked result.

There is one production source compilation engine, with several input adapters.
File, expression, stdin, caller-owned AST, package, and installed-library inputs
all reach the crate declaration graph. Native executables have two ways to
supply a dependency's implementation: compose its checked IR or link its native
object. Compiling available source prepares a checked crate for those consumers;
it is not another inference or native-linking pipeline.

| Invocation | Root and dependencies | Result |
| --- | --- | --- |
| `emlf --type Main.emlf` | File and imports resolved from the entry directory and the ordered `-i` roots | Inferred source type |
| `emlf Main.emlf` | Same source root | Closed, checked xMLF |
| `emlf --run --expr 'printInt 42'` | Expression with the selected Prelude policy | Interpreted IO |
| `emlf --emit-llvm Main.emlf` | Same source root | LLVM IR for a closed program |
| `emlf Main.emlf -o main` | File and the installed compiler's authenticated library and runtime | Native executable |
| `mlfpkg build --target NAME` | Manifest target, private modules, and declared library dependencies | Package target and build receipts |
| `Bootstrap.Compiler.compile*` | Caller-owned source, modules, expression AST, or program AST | An IO action returning a checked crate compilation or a phased error |

A saved xMLF file can enter the backend directly. For example,
`emlf --xmlf-to-llvm term.xmlf` parses and checks the target before emitting LLVM.
`emlf --help tools` lists the other stage entry points.

## Root and inference boundaries

An implicit crate covers the file's resolved module closure. An import establishes
a namespace relationship. The declaration dependency graph determines which
bindings must be inferred together, including mutually recursive bindings across
modules when the language permits them. A script contributes its top-level
declarations and one entry for the result expression. Each declaration group
can be checked separately. Bindings inside an expression retain their lexical
scope and generalization boundaries. The compiler retains the source names
needed to print the inferred type and report errors.

A manifest defines a separately compiled library or target. Its root can see its
private modules, the package's own library, and its selected direct dependencies.
Upstream interfaces supply checked contracts, module exports, nominal types,
classes and instance visibility. The implementation objects supply checked
fragments when the program is linked. Changing how the scheduler runs the jobs
preserves these package boundaries.

The group engine records dependencies on source and imported contracts. It
checks the inferred type and elaborated target before admitting a new fragment.
The root adapter closes checked fragments for printing, interpreting, or
ordinary LLVM emission. Native code generation can keep selected values as
typed parameters supplied by native crate objects.

`Bootstrap.Compiler` lives in `mlf-crates` and delegates its public APIs to
`SourceCrate.compileClosed` and `CrateSession`. Its result exposes the checked
term and rendered source type. It no longer supplies a whole-program
`presolution`; a declaration-group build has several independent inference
results. Solver inspection uses the explicit frontend and solver APIs.
`Bootstrap.SourceFrontend` owns source normalization, class lowering, and
diagnostic rendering. `CompilerCore` remains the lower inference/checking
kernel used by crate groups and builtin preparation.

[Public source and AST API](../libraries/mlf-crates/Bootstrap/Compiler.hs) ·
[Source root adapter](../libraries/mlf-crates/Bootstrap/SourceCrate.hs) ·
[crate session](../libraries/mlf-crates/Bootstrap/CrateSession.hs) ·
[group inference](../libraries/mlf-crates/Bootstrap/CrateGraph.hs)

## Lifetime of compiled results

| Input | Storage and reuse |
| --- | --- |
| File through the CLI | The compiler stores declaration-group queries under `.mlf-build/cache/source-roots/` in the working directory. Repeated builds can reuse checked groups whose inputs and dependencies still match. |
| Expression or stdin | The query graph and pending results live in the invocation. |
| `Bootstrap.Compiler` API | The same crate session uses in-memory query storage, including file and AST requests. |
| Package | `mlfpkg` uses the package build cache and publishes `.mlfci` interfaces and `.mlfco` implementation objects for independently compiled units. |

Set `MLF_SOURCE_CACHE_DIR` to choose a different cache directory. A relative
path is resolved from the working directory. If the compiler cannot create or
lock the default cache, it uses an in-memory session. An explicitly configured
cache must be usable.

For example, run `emlf --type Main.emlf`, edit a declaration, and invoke the same
command from the same directory. The compiler resolves the current input and
rechecks affected groups. A native build can use that group cache while still
emitting user LLVM and compiling and linking a fresh executable. Its
`--build-dir` selects the directory for that invocation's IR, object, process
logs, and receipt.

The package scheduler can read an admitted crate from disk or pass a freshly
compiled root directly to LLVM emission. A build plan can retain dependency
objects across multiple compilations. These paths share the checks for the
declared interfaces, object contents, and builtin Prelude. The backend test
drivers are package targets with their own runtime and link requirements.

[Query storage](../libraries/mlf-crates/Bootstrap/QueryGraph.hs) ·
[package scheduler](../libraries/mlf-package-core/Package/Scheduler.hs) ·
[backend driver targets](../bootstrap/mlf-package.json)

## Choosing dependency implementations

For a native executable the builder chooses an implementation for each crate.
It prefers a compatible native object, then checked xMLF, and compiles source
when it needs a checked implementation. The program can use several native
objects and checked IR in the same link. Type checking uses the crate
interfaces in every case.

| Choice | Inputs and work |
| --- | --- |
| `native` | The builder checks the object digest, compiler and target identity, ABI, constructor layout, and typed exports. Clang links the selected object into the executable. |
| `ir` | The compiler combines checked implementations from `.mlfco` objects or authenticated embedded crate data with the user root before LLVM optimization and machine-code generation. |
| `source` | The compiler checks source declarations and creates the crate's checked implementation. An eligible source library can also produce a native object for later links. |

A dependency with no reachable implementation can appear as `unused`; its interface can still participate in checking.

An IR-only dependency remains usable beside a native dependency. A change to a
library body invalidates its native object even when its interface still allows
consumers to reuse their checked declarations. Whole-program profile-guided builds select checked IR so the optimizer sees
the instrumented program. The package release format
distributes pinned `.mlfci` and `.mlfco` files. The package manager admits
native objects produced for its own toolchain and target.

Each generic native library exports a typed function that accepts the checked
values it imports and returns its exports. The root applies that function once
and shares the result. A native library can therefore use values supplied by
another native library or by checked IR without generating a second copy of the
dependency. The ABI fixes the export order and boxed representation. User
constructor tags derive from qualified names, with collisions checked across
the full target. Both package libraries and installed libraries use
`MLF-NATIVE-CRATE-1` contracts and the `mlf-crate-boxed/1` ABI. Both invoke
`NativeCrate.emitLibrary` to produce objects and
`CrateNativeCommand.emitDependencies` to select providers, compose checked
fallbacks, emit the root, and revalidate selected objects.

Each decision appears on stderr with the dependency identity, mode and reason.
For example, `dependency demo/1.0/library: source (compiled package sources)`
reports preparation of that library. The executable's link decision for the
same library can subsequently say `native`. The package build report's
`dependency_modes` rows distinguish the check and link stages. A direct
`emlf -o` build also saves its decisions in `receipt.json`.

```sh
./mlfpkg build --target app 2>build.log
rg '^dependency ' build.log
jq '.dependency_modes' .mlf-build/build-report.json
```

The package manager records the native compiler handoff in `native-plan.json`
and `native-target.json`. A build tool can use the same stage with an
independently pinned plan:

```sh
emlf --crate-to-native-llvm "$ROOT_INTERFACE" \
  --native-dependencies "$PLAN" --native-plan-sha256 "$PLAN_SHA256" \
  --native-target "$TARGET" --native-report "$REPORT" >program.ll
```

The plan binds the target, dependency interfaces, typed contract, and machine
object digests. An optional checked implementation has its own path and digest.
A selected native dependency can link with its `.mlfco` absent. If the object is
unusable, the compiler loads a pinned checked fallback on demand or identifies
the reachable dependency that lacks an implementation. The report lists the
objects to pass to the native linker.

This optional `.mlfco` applies to the pinned compiler handoff above. Ordinary
`mlfpkg build` still prepares and hashes the checked dependency closure before
selecting native objects, so that preparation requires each dependency's
`.mlfci` and `.mlfco`. Release v1 continues to distribute both files.

The interpreter and standalone xMLF or LLVM output require a closed program.
These commands select checked IR and source implementations. They print their
result on stdout, so a command such as `emlf Main.emlf >main.xmlf` can be used
without filtering compiler diagnostics.

The installed compiler obtains its providers from an authenticated
`MLF-NATIVE-INSTALLATION-1` inventory instead of a package plan on disk. The
inventory can contain multiple native crates and crates that require checked
IR. Its embedded checked libraries retain their interfaces and exact `.mlfco`
images. A requested body is decoded and admitted by the ordinary crate object
reader, preserving open declaration fragments without a legacy closed-spine
conversion or a second independently supplied AST. Source search roots take precedence over
installation defaults. A missing, damaged, or incompatible provider object can
fall back independently to checked IR. Creating the executable still requires
the authenticated runtime, native toolchain, and link inputs.

The direct executable receipt uses `MLF-NATIVE-PROGRAM-BUILD-3`.
`native_providers` records the selected dependency identities, object paths, and
digests; `link_objects` records those objects and the runtime actually linked.
`runtime_reused`, `dependency_modes`, and `fallback_reason` describe the actual
build. There is no separate fixed-library ABI, emitter, or reuse count.

[Native crate ABI](../libraries/mlf-llvm/Bootstrap/LLVM/Library.hs) ·
[package artifact admission](../libraries/mlf-package-core/Package/NativeArtifact.hs) ·
[installed compiler](../tools/shared/prepared-build.md)
