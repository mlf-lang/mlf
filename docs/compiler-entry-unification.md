# Compiling source and package roots

`emlf` accepts a file, an expression, or standard input. `mlfpkg build` obtains its
roots from the package manifest. Both use the crate compiler to prepare declaration
groups, infer their contracts, and produce checked xMLF. The input determines the
root's namespace and dependencies. The requested output determines how to use the
checked result.

| Invocation | Root and dependencies | Result |
| --- | --- | --- |
| `emlf --type Main.emlf` | File and imports resolved from the entry directory and the ordered `-i` roots | Inferred source type |
| `emlf Main.emlf` | Same source root | Closed, checked xMLF |
| `emlf --run --expr 'printInt 42'` | Expression with the selected Prelude policy | Interpreted IO |
| `emlf --emit-llvm Main.emlf` | Same source root | LLVM IR for a closed program |
| `emlf Main.emlf -o main` | File and the installed compiler's authenticated library and runtime | Native executable |
| `mlfpkg build --target NAME` | Manifest target, private modules, and declared library dependencies | Package target and build receipts |

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
typed parameters supplied by the installed object.

[Source root adapter](../libraries/mlf-crates/Bootstrap/SourceCrate.hs) ·
[crate session](../libraries/mlf-crates/Bootstrap/CrateSession.hs) ·
[group inference](../libraries/mlf-crates/Bootstrap/CrateGraph.hs)

## Lifetime of compiled results

| Input | Storage and reuse |
| --- | --- |
| File | The compiler stores declaration-group queries under `.mlf-build/cache/source-roots/` in the working directory. Repeated builds can reuse checked groups whose inputs and dependencies still match. |
| Expression or stdin | The query graph and pending results live in the invocation. |
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

## Installed native dependencies

The installed compiler binds a checked standard-library interface to its export
slots, constructor layout, ABI, and pinned native objects. The source loader
honors explicit search roots before installation defaults. For an admitted
installation, the compiler projects the checked root onto the exact exports it
uses. It can materialize selected checked builtin definitions in the root and
reference other exports through the installation's typed ABI. Clang compiles the
user IR and links the installed library and runtime objects. The build receipt
records how many native slots and inline builtins the root used. If a source
override or an incompatible native layout requires closed-program emission,
`fallback_reason` records the reason and the compiler emits from the checked
root. A missing or corrupt native installation is a build error.

The package manifest accepts source packages and checked releases. Each carries
its own crate identity and export contracts. The compiler installation has its
own fixed identity. Equal module names or matching source text alone cannot
authorize substituting its machine code for a package dependency.

[Installed compiler and native ABI](../tools/shared/prepared-build.md) ·
[package dependencies and checked releases](package-manager.md#local-packages)
