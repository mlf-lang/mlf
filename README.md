# eMLF → xMLF → LLVM

> Historical evidence notice: Raw files previously stored under
> `tools/profile/results/` were removed from this branch and its Git history.
> References to those files below describe historical evidence that is not
> available in this repository; retained summaries are not independent access
> to the original raw records.


A standalone compiler for the core eMLF language in Boris Yakobowski's
*Graphical types and constraints — second-order polymorphism and inference*
(2008), using the supplied [thesis text](papers/these-finale-english.txt).
It performs graph-based MLF inference and emits explicit, independently
type-checked xMLF.
An interpreter runs checked `IO` programs with console input and output.
An LLVM backend compiles checked xMLF to native functions, with a
small C runtime for lazy evaluation, algebraic data, and IO.

## Install

Native developer-preview releases are published at
[mlf-lang/mlf](https://github.com/mlf-lang/mlf/releases). Version 0.2.0 adds
Windows x64 and Linux x64 alongside Apple Silicon on macOS 26+.
See [installation and releases](docs/releases.md) for platform dependencies,
checksums, installation and validation coverage.

## Build and run

For native Windows `.exe` tools, see the [Windows bootstrap](docs/windows.md).
It builds the compiler and package manager, supports `plan`, `lock`, `build`,
package `test` and `run`, and checks the independent compiler parity corpus.
Windows uses the PowerShell bootstrap and `mlfpkg.ps1` or `mlfpkg.cmd` launchers.
The shell commands and six compiler test groups below describe the POSIX path.

Run these commands from the repository root. You need a working native MLF
compiler as the seed, Clang/LLVM, GMP development files, `pkg-config`, and a
local BDWGC installation. An installed [native release](docs/releases.md) can
supply the seed. The compiler and package manager are written in MLF; this
build and test path needs no GHC, Cabal, or Python.

This shared-source checkout has two native bootstrap routes. For a released
0.3.0 seed, keep the complete verified release bundle intact and select its
matching compiler and manager. The old seed cannot parse the new `.hs` sources;
the committed frozen bridge performs that transition without GHC:

```sh
export MLF_COMPILER=/absolute/path/to/verified-release/bin/emlf
export MLF_PACKAGE_MANAGER=/absolute/path/to/verified-release/bin/mlfpkg
export MLF_GC_PREFIX=/absolute/path/to/bdwgc-install
./scripts/bootstrap-shared.sh
export MLF_COMPILER="$PWD/.mlf-build/shared-bootstrap/stage2"
export MLF_PACKAGE_MANAGER="$(cat .mlf-build/shared-bootstrap/manager.path)"
./mlfpkg --compiler "$MLF_COMPILER" --timeout 21600 \
  --build-dir "$PWD/.mlf-build/native-stage1" build

export MLF_COMPILER="$PWD/.mlf-build/native-stage1/bin/emlf"
export MLF_PACKAGE_MANAGER="$PWD/.mlf-build/native-stage1/bin/mlfpkg"
./mlfpkg --compiler "$MLF_COMPILER" --timeout 21600 build
export EMLF_BIN="$PWD/.mlf-build/bin/emlf"
"$EMLF_BIN" --type examples/choose-id.emlf
printf 'Ada\n' | "$EMLF_BIN" --run examples/io-hello.emlf
"$EMLF_BIN" --run examples/modules/Main.emlf
```

For a qualified locally built shared-aware native compiler, its
`--implementation-identity` must report `MLF/shared-haskell-v1 native-MLF`.
`scripts/bootstrap-package.sh` can build a matching native manager directly;
that manager must report the same host identity before it is used by the native
manager-bootstrap route. These local shared-aware pairs do not require release
bundle layout. Identity strings distinguish supported producer paths; they are
not cryptographic publisher authentication. See the
[bootstrap contract](docs/shared-source/Bootstrap-and-CI.md).

The released bridge produces a current compiler and matching package manager.
The following native generations qualify the code generator and produce
`.mlf-build/bin/emlf` and `.mlf-build/bin/mlfpkg`. Keep the stage-1 tools selected
as the package manager's inputs, in their separate directory, when rebuilding or
testing the repository. Use `EMLF_BIN` to run the candidate compiler. Global package-manager
options go before `build`, `test`, or `run`; `--build-dir DIR` selects the output
directory. `--jobs N` bounds concurrent build actions; the initial default is 1.
For example, `./mlfpkg --jobs 4 build --target emlf` builds the compiler with
at most four active actions. Arbitrary test commands still run serially.

The bootstrap also builds `mlf-build-runner` beside the manager. Keep that helper
with the manager when moving native tools. The compiler and package libraries
now live under `libraries/mlf-*/`, with one manifest per library and unchanged
`Bootstrap.*` / `Package.*` names. `bootstrap/` and `package/` retain entry
points and compiler drivers. The root targets explicitly select their library
dependencies, so `emlf` does not wait for developer tooling. Rebuild the manager
with the current bootstrap script before using these manifests with an older
installed manager. See the [package manager guide](docs/package-manager.md) for
the ten-library layout, dependency selection, and scheduling evidence.

The separate [async utility](docs/async-task.md) provides cold typed tasks,
cooperative fibers, scoped cancellation, timers and bounded combinators.
[Async.Process](docs/async-process.md) supplies dynamic subprocess scopes and
isolated CPU-parallel work. The single MLF coordinator uses opaque typed
completions; it does not run MLF inference on shared-memory worker threads.
The [bootstrap and qualification](docs/async-bootstrap.md) distinguish the
released seed from a compiler with the new checked primitives.

The package manager compiles each library and executable as a crate. Modules
inside a crate are namespaces and may import one another cyclically. Value
declarations are inferred in dependency SCCs, with closed schemes and checked
xMLF fragments cached independently. Generated `.mlfci` metadata lets downstream
crates infer without upstream source or implementation objects. The final linker
checks selected imported schemes, nominal layouts, and the closed linked program.
Inferred-type agreement and source-erasure checks remain enabled for every
new inference query.

See the [crate migration ledger](docs/crate-migration.md) for accepted measurements
and the [validation record](docs/crate-validation.json) for all six native groups,
fresh self-hosting and the exact source/tool configuration. The [earlier bootstrap memory report](tools/profile/results/2026-10-19-bootstrap-memory/README.md)
describes the previous per-module pipeline; its results are historical.

Run all six native test groups, or select groups for development:

```sh
./mlfpkg --compiler "$MLF_COMPILER" --timeout 21600 test
./mlfpkg --compiler "$MLF_COMPILER" --timeout 21600 test \
  --target unit --target packages
```

The groups are `unit`, `packages`, `self-host`, `parity`, `backends`, and `port`.
They include a fresh self-host LLVM fixed point and interpreter/LLVM execution
in the backend group under the compact-GC layout. Port runs all
25 compiler-library probes through compact-GC LLVM, with independent
references and checked targets. It no longer interprets those complete probes;
focused interpreter tests remain. The full gate includes source preparation and
fresh self-hosting and needs the longer timeout above. See the
[test matrix cleanup and timings](docs/test-matrix-cleanup.md).
The retained local full-suite verification used 32 GiB RAM.
Build reports are written to `.mlf-build/build-report.json`, with detailed
compiler-test evidence under `.mlf-build/compiler-tests/`.

Package resolution, caching, builds, tests, and independent reference programs
run in MLF. Clang builds the C runtime, ABI probes, and process transports.
The verified 2026-10-18 toolchain used Apple Silicon macOS 26.6.2,
Clang/LLVM 23.1.3, GMP 6.3.0, and BDWGC 8.2.12. See the
[package manager guide](docs/package-manager.md) for prerequisites and local
dependencies, [native test coverage](tests/README.md), and the
[historical verification report](tools/profile/RESULTS.md).

The executable also accepts standard input and `--expr '...source...'`.
`--type` prints only the inferred source type, including class constraints.
A failed parse, module resolution, inference, dictionary resolution,
elaboration, or verification
exits unsuccessfully and identifies the failing phase.

The default output is xMLF source, preceded by a comment containing its type.
Compile and independently check a file with the native executable:

```sh
"$EMLF_BIN" examples/choose-id.emlf > .mlf-build/choose-id.xmlf
"$EMLF_BIN" --check .mlf-build/choose-id.xmlf
```

`--check` parses the xMLF and runs the target checker; it does not call the
source inference engine. All identifiers in this output carry explicit IDs,
for example `x_12` and `a27`. These distinguish source shadowing and graph
sharing; the numbers have no type-theoretic significance.

## Compiler written in MLF

[`bootstrap/Main.emlf`](bootstrap/Main.emlf) implements the compiler in MLF,
including modules, classes, graph inference, checked elaboration, the xMLF
checker, interpreter, and LLVM backend. The native package manager rebuilds it
using an existing MLF compiler and checks self-hosting through a fresh LLVM
fixed point. The independent checking modules and reference algorithms execute
as MLF programs; frozen Haskell-seed expectations remain parity oracle data.

```sh
./mlfpkg --compiler "$MLF_COMPILER" --timeout 21600 test \
  --target self-host --target parity
```

All native builds use the compact BDWGC runtime for long pure compilation
phases. For reproducible PGO construction with profile-aware native caches, see
[the package build instructions](docs/package-manager.md#native-profile-guided-construction).
For two native generations and historical compiler-only PGO, see
[native self-compilation profiling](tools/profile/README.md). That historical frozen
source comparison measured **181.955 s versus 257.289 s**, a **29.280%** median
reduction; the raw measurements and exact compiler hashes are linked there.

The [native release workflow](docs/releases.md) requires all six native groups,
a fresh self-host fixed point, and relocation/installation checks before
packaging the tested executables. It records the build host and native library
dependencies. Every push to `main` now runs complete native qualification and all ten
Benchmark Game workloads with **3× C compilation / 2× C runtime** gates; SDK
packaging remains release-only. The historical [performance report](benchmarks/RESULTS.md)
covers nine workloads and does not prove that the complete ten-workload gate
passes. Failed correctness or performance checks remain failures.

The Haskell compiler, Cabal project, and old Haskell/Python test and build
harnesses have been removed. Native MLF is the supported build and test path.
Pinned C/Rust/Haskell benchmark sources, the independent Snake baseline,
golden oracle data, and archived measurements remain available. Compiler-level
classification measurements, which compile identical generated sources with GHC
and MLF instead of pinned applications, live in the
[compiler shape benchmark](tools/performance/compiler-shapes/README.md).

## Native compilation with LLVM

An installed compiler builds an executable directly and automatically reuses
its fixed standard library and runtime:

```sh
"$EMLF_BIN" examples/snake.emlf -o .mlf-build/snake
.mlf-build/snake
```

Each invocation freshly checks and compiles the user program, runs one ordinary
Clang `-O2` job, and links the installed objects. `--compile SOURCE -o OUTPUT`
is an equivalent spelling. By default, a fresh hidden `.emlf-<output>-N`
directory beside the output retains the IR, object, process logs and
`receipt.json`, including selected standard-library exports and any fallback
reason. `--build-dir FRESH_DIRECTORY` selects an explicit fresh location instead. Explicit module search roots take precedence
over installed standard-library roots. Changed library sources use the ordinary
checked compilation path. See [standard compiler installation](tools/shared/prepared-build.md).

The standalone LLVM commands remain available for explicit linking:

Compile a saved xMLF program to LLVM IR, then link it with the runtime:

```sh
"$EMLF_BIN" examples/snake.emlf > .mlf-build/snake.xmlf
"$EMLF_BIN" --xmlf-to-llvm .mlf-build/snake.xmlf > .mlf-build/snake.ll
MLF_RUNTIME="$("$EMLF_BIN" --llvm-runtime)"
clang -O2 -std=c11 .mlf-build/snake.ll "$MLF_RUNTIME" \
  $(pkg-config --cflags --libs gmp bdw-gc) -lm -o .mlf-build/snake
.mlf-build/snake
```

`--xmlf-to-llvm` independently checks the input before erasing type evidence;
it does not rerun source inference. It also accepts standard input. To compile
eMLF directly through the same checked xMLF boundary, use
`emlf --emit-llvm examples/snake.emlf` or `emlf --emit-llvm --expr 'printInt 42'`.
Both commands write only LLVM IR to standard output. `--no-prelude` also
applies to `--emit-llvm`.

For a manifest-driven native executable, the package manager builds, links,
and runs the selected target:

```sh
./mlfpkg --compiler "$EMLF_BIN" \
  --manifest examples/packages/mlf-package.json run hello
```

Declare your own executable in `mlf-package.json`; see the
[package format and examples](docs/package-manager.md#local-packages).
Normal builds use Clang `-O2` and content-addressed caches with source/tool
fingerprints. The [native benchmark runner](tools/bench/README.md) instead
creates fresh runtime and LLVM objects for every sample and times the complete
build, including linking. Its optional LLVM/linker configuration is also usable
with `./mlfpkg --clang /absolute/path/to/clang-mlf build`.

The generated module contains native closure and case functions, `mlf_entry`,
and `main`. It supports the complete current xMLF term syntax, including
recursive dictionaries, polymorphism after checked erasure, lazy constructor
fields, and IO. An `IO a` entry executes the action and discards its result;
a pure entry evaluates to weak head normal form without printing a value.
Known saturated functions use native workers, with conservative demand
analysis to avoid unnecessary thunks. Partial applications and lazy fields
retain their call-by-need behavior. Small integers and nullary constructors
use tagged immediate values; unary/binary data has inline fields.
`Int` uses signed 64-bit arithmetic; GMP supports the separate unbounded
`Integer` type. Strings use length-delimited
UTF-8, including embedded NULs. Invalid Unicode scalar literals are rejected.

The runtime memoizes pure thunks and executes shared IO actions afresh on
each bind. All native programs use compact BDWGC allocation and collection during
pure evaluation. Pointer-bearing values, environments and arrays are traced;
GMP limbs use atomic collector allocations. The runtime requires a 64-bit ABI.
Both default LLVM commands and their `-gc` aliases emit this single ABI; link
GMP, BDWGC and libm. Old standard-layout LLVM/object files must be regenerated.
See [the migration record](docs/compact-only.md) for dependencies and validation.

The native `backends` group runs every backend behavior test through both the
xMLF interpreter and LLVM native code, using compact-GC. It compares
results, ordered read/write events, write boundaries, and unused input.
It includes all 16 standalone examples, the multi-file module example,
IO and Prelude behavior,
and all seven Snake sessions and eleven rule checks against independently
retained expectations. A coverage audit fails if
either backend is missing from any execution case.
Run the shared backend and compiler-port suites:

```sh
./mlfpkg --compiler "$MLF_COMPILER" --timeout 21600 test \
  --target backends --target port
```

The shared suite requires POSIX process support and the native toolchain;
missing dependencies fail the suite. Run frontend tests and Figure 12 cases
with the `unit` target shown under Build and run.
See [`docs/llvm-backend.txt`](docs/llvm-backend.txt) for the lowering and runtime
boundaries. The [Snake benchmark](docs/snake-llvm-compilation-performance.txt)
reports xMLF emission, LLVM IR emission, and complete native builds separately.

## Source language

The grammar below shows explicit separators; indentation can supply the
braces and semicolons described under Layout.

```text
program ::= (declaration ";")* e
          | (declaration ";")* value-declaration [";"]
declaration ::= data-declaration | class-declaration | instance-declaration
              | value-declaration
value-declaration ::= [x ":" annotation ";"] x pattern-atom ... [":" annotation] rhs
rhs ::= = e | ("|" e = e)* "|" otherwise = e
binding-block ::= value-declaration | { value-declaration; ... }

e ::= x | integer | double | string | true | false | ()
    | \pattern-atom ... -> e
    | e e | let [rec] binding-block in e | (e : annotation)
    | if e then e else e | e operator e | -e | +e
    | if { ("|" e -> e;)* "|" otherwise -> e [;] }
    | Constructor | case e of { pattern -> e; ... }
    | do { statement; ...; e }
    | (e, e [, e [, e]]) | [e, ...] | e : e | (e :: annotation)

statement ::= pattern <- e | e | let [rec] binding-block

data-declaration ::= data TypeName parameter ... = Constructor field ... | ...
parameter ::= a | (a : kind)
kind ::= * | kind -> kind
pattern ::= Constructor pattern-atom ... | pattern-atom | pattern : pattern
pattern-atom ::= x | _ | Constructor | integer | string | true | false | ()
               | (pattern) | (x : annotation)
               | (pattern, pattern [, pattern [, pattern]]) | [pattern, ...]

class-declaration ::= class [context =>] ClassName parameter ... where { method : type; ... }
instance-declaration ::= instance [forall parameter ... .] [context =>]
                         ClassName type-atom ... where { value-declaration; ... }
context ::= ClassName type-atom ... | (ClassName type-atom ..., ...)
type-atom ::= a | Constructor | (type) | (type, type [, type [, type]]) | [type]

annotation ::= type | exists a ... . type

type ::= a | bot | type -> type | type type
       | forall a ... . type
       | forall (a : kind) ... . type
       | forall (a >= type) ... . type
       | forall (a = type) ... . type
       | context => type
```

Use parentheses to group expressions and types. `\x y -> e`, `λx. e`,
`forall (a > type). type`, and `let x : annotation = e in e` are also accepted.
`forall a.` abbreviates `forall (a >= bot).`. Type constructor names start
with an uppercase letter. Annotations must be closed except for their explicit
existentials, whose values are inferred. Comments use `--` or nested `{- -}`.

The source includes lambda, application, nonrecursive let, expression and
parameter annotations, integer/Double/Boolean/string literals, algebraic data types, and
type classes with multiple and higher-kinded parameters, `do` blocks,
function equations, nested patterns, typed recursive bindings, layout,
conditionals, fixed-precedence infix operators, and named modules with imports.
Module-free core programs also allow abstract constructor types in annotations;
named modules resolve type names through their declarations and imports.
Instance methods can be recursive through their dictionaries.
The interpreter evaluates erased
xMLF with lazy bindings and executes explicit IO actions. xMLF type computations are
compilation evidence; erasure removes them.

### Modules and imports

Files can declare a module and its public interface:

```haskell
-- Geometry/Point.emlf
module Geometry.Point (Point(..), move, distanceSquared) where

data Point = Point Int Int

move dx dy (Point x y) = Point (x + dx) (y + dy)
square x = x * x
distanceSquared (Point x y) = square x + square y
```

```haskell
-- Main.emlf
module Main (main) where

import Geometry.Point (Point(..))
import qualified Geometry.Point as Point (move, distanceSquared)

main = do
  let destination = Point.move 3 4 (Point 0 0)
  printInt (Point.distanceSquared destination)
```

Run the complete [example](examples/modules/Main.emlf) with
`"$EMLF_BIN" --run examples/modules/Main.emlf`; it prints `25`.
The same entry works with `--type`, xMLF emission, and `--emit-llvm`.

Import/export forms follow the names-and-interfaces model in
[Haskell 2010, Chapter 5](https://www.haskell.org/onlinereport/haskell2010/haskellch5.html):

| Form | Effect |
| --- | --- |
| `module A where` | Exports all local declarations. Imported names stay private. |
| `module A (f, T, C(method)) where` | Exports `f`, abstract datatype `T`, and class `C` with one method. |
| `T(..)` / `T(MkT)` | Includes all visible constructors / selected constructors; the same forms select class methods. |
| `import A` | Imports exported names both unqualified and as `A.name`. |
| `import A (f, T(..))` | Imports only those names. |
| `import A hiding (f)` | Excludes `f` from both unqualified and qualified access. |
| `import qualified A as B` | Exposes names only as `B.name`. |
| `import A as B` | Exposes names unqualified and as `B.name`. |
| `module A (module B) where` | Re-exports names available both unqualified and through `B`, which may be an import alias. |
| `import A ()` | Imports no names, but still imports instances transitively. |

Imports precede declarations. A named module contains declarations only;
the entry evaluates its local `main`, or an imported `main` when there is no
local one. Library modules need no `main`. Headerless scripts may also use
imports and keep their existing final-expression syntax.
Qualified names work in expressions, annotations, data fields, class constraints,
instance heads, and constructor patterns.

Unexported helpers, types, and constructors cannot be accessed even through a
qualified name. Distinct modules may reuse private names safely. Repeated imports
of the same original declaration are harmless; two different declarations with
the same name make an unqualified use ambiguous. Use qualification or `hiding`
to resolve a conflict, including conflicts with a top-level local definition.
Lambda, pattern, and local-let binders shadow imported values normally.

Instances follow the transitive import graph independently of export lists.
Instance bodies can use module-level helpers. Each signed value and instance
is checked using the instances visible in its defining module; importing it
alongside another instance does not retroactively change that scope.
Overlapping instances remain an error.

Each module implicitly imports the built-in `Prelude`. Any explicit
`import Prelude`, including `qualified` or `()`, suppresses that implicit import
for that file. For example, `import Prelude hiding (return)` permits a local
`return`. Prelude exports the existing primitives, builtin types, `Monad`,
and its `IO` instance. `--no-prelude` disables implicit class imports across the
graph; explicit Prelude imports still work, and files without one retain the
existing primitive fallback. Literals, unit syntax, fixed operators, and `if`
remain built-in syntax.

The loader maps `Foo.Bar` to `Foo/Bar.emlf`. It searches beside the entry,
then each `-i` directory in order, then the entry's inferred hierarchy root
and the current directory; the first matching file wins. An imported file
must declare the requested module name. Put search options before the command:

```sh
"$EMLF_BIN" -i src -i vendor --run app/Main.emlf
"$EMLF_BIN" -isrc --emit-llvm app/Main.emlf > program.ll
```

For API users, `parseModule` preserves declarations and imports.
`compileFile searchRoots path` loads a graph from disk; `compileModules sources
path input` is pure and takes a `Map moduleName (filePath, sourceText)`.
Both have `WithPrelude` variants, and `compileSourceWithImports` loads imports
for an entry supplied as text. `compile` remains pure: it accepts standalone
modules and builtin Prelude imports, but external imports require one of those
graph-loading APIs. `parseProgram` and `compileProgram` remain the closed-program
APIs used by existing clients.

The source commands resolve all reachable modules as one crate. Package builds
also persist generated crate metadata and checked implementation fragments:

```sh
./mlfpkg --manifest examples/packages/mlf-package.json build
./mlfpkg --manifest examples/packages/mlf-package.json plan
```

`plan` shows the crate DAG and each crate's modules. A library is one crate;
each executable or native test is another crate depending on its package's
library and direct dependency libraries. Module import cycles within a crate are
valid. Crate dependency cycles are rejected with their dependency chain.

The compiler's low-level package-driver protocol is
`emlf --compile-crate SPEC -o PREFIX`. It writes `.mlfci` semantic metadata,
`.mlfco` checked implementation fragments, and a `.queries` reuse report.
`--show-crate`, `--link-crate`, `--run-crate`, and `--crate-to-llvm[-gc]` consume
`.mlfci` paths. See the [artifact and cache contract](docs/crate-compilation.md)
for the specification format and validation boundaries.

Names retain their defining crate, module, namespace and role. The linker
freshens local binders, verifies actual consumed schemes and datatype layouts,
and independently checks the final program. Changed dependency implementations
can be linked without re-inferring unchanged consumers. Changed consumed schemes
or layouts invalidate the affected queries; unrelated declarations remain reusable.
The shared built-in Prelude is a generated compiler artifact with one identity.

Import cycles do not make all declarations recursive. Only actual value SCCs
share recursive inference assumptions. Unsigned ordinary recursion is inferred
across modules within one crate; signed members remain fixed polymorphic
interfaces. Acyclic values retain ordinary generalization and first-class
polymorphism. Cyclic dependencies between separately compiled crates remain
unsupported. User-defined operator
imports remain unsupported.

### Function declarations and expressions

Top-level values and functions use aligned or semicolon-separated declarations. A file
without a final expression evaluates its `main` binding:

```haskell
scale : Int -> Int -> Int
scale x y = x * 4 + y

main = do
  let result = scale 10 2
  if result == 42 then putStrLn "forty-two" else printInt result
```

A separate signature must immediately precede its definition. You can also
write an inline signature, such as `scale x y : Int -> Int -> Int = x * 4 + y`;
it annotates the whole function. Parameters may have annotations, for example
`apply (f : forall a. a -> a) = f f`. Function parameters also work in local
bindings (`let inc x = x + 1 in inc 41`), `do` declarations
(`do { let inc x = x + 1; printInt (inc 41) }`), and instance methods.

Declaration signatures retain their own checking mode independently of class
declarations, so a known higher-rank argument interface can guide the function
body. An annotation on an expression, such as `(value : Type)`, remains an
expression coercion rather than silently becoming a declaration signature.

Top-level values can refer forward to other values. The compiler orders
dependencies and generalizes acyclic definitions as ordinary `let` bindings;
ordinary recursive groups are inferred as described below. In module-free scripts,
class and instance declarations retain their separate scope. A final expression can select a
result instead of `main`: `inc x = x + 1; inc 41`.

Functions may have multiple contiguous equations with the same number of
parameters. They are tried in source order. Constructor patterns can nest;
parenthesize a constructor application used as a parameter:

```haskell
data List a = Nil | Cons a (List a)

second (Cons _ (Cons x _)) = x
second _ = 0

main = printInt (second (Cons 10 (Cons 42 Nil)))
```

Patterns also work in lambdas, `case`, `do` bindings, and instance methods.
Integer, string, and Boolean literal patterns are supported. Use a fallback
variable or `_` for integer and string matches, and cover both Boolean values
or provide a fallback. Matches must be exhaustive. Pattern variables are
distinct within an equation and scope only over its body. Wildcards leave
their values lazy; matching tests each equation's required arguments from
left to right. Nested patterns lower to flat, independently checked xMLF cases.

### Layout

Align top-level declarations at the same indentation. After `do`, `of`, or
`where`, the first item establishes the block's indentation. Items at that
column are separated implicitly; a dedent closes the block. More deeply
indented lines continue the current item. Strings and comments do not affect
layout, and parse errors retain the original source positions.

```haskell
move direction (Position x y) =
  case direction of
    North -> Position x (y - 1)
    South -> Position x (y + 1)
    West -> Position (x - 1) y
    East -> Position (x + 1) y
```

A `let` or `let rec` followed by a newline introduces an aligned group of
local declarations, ending at `in` or the next `do` statement. Inline
`let x = value in body` and `do { let x = value; action }` remain available.
Explicit braces and semicolons can be mixed with layout; use braces for
multiple declarations on one line. Parentheses suspend surrounding layout,
while an implicit block opened inside parentheses still follows indentation.

### Recursive bindings

Ordinary self-recursive and mutually recursive top-level definitions do not
need whole-binding signatures. Unsigned uses share one unsolved type within
their inference component; the solved exports are generalized afterward,
without generalizing captured environmental types:

```haskell
factorial 0 = 1
factorial n = n * factorial (n - 1)

main = printInt (factorial 6)
```

An ordinary local `let` keeps its nonrecursive meaning. Use `let rec` for
local recursion, including inside `do`:

```haskell
main = do
  let rec
    countdown 0 = putStrLn "done"
    countdown n = do
      printInt n
      countdown (n - 1)
  countdown 3
```

Local groups also infer unsigned ordinary recursion, including qualified
(class-constrained) interfaces. Signed and unsigned members can coexist. A
signature such as `forall (m : * -> *) a. Monad m => Int -> m a -> m a` supplies
a fixed interface: its body is checked against that scheme, and recursive
uses can instantiate it independently. Free annotation variables and
existential signatures are not closed recursive interfaces.

Recursive polymorphic instantiation still needs an appropriate declared
interface; this is not unrestricted polymorphic-recursion inference. A local
higher-rank parameter annotation can suffice without annotating the whole
recursive binding. The compiler emits checked xMLF evidence while preserving
the recursive value knot. See the [design and validation record](docs/inference/Unsigned-Recursion-Final-Validation.md)
for exact inference limits and focused host-versus-native validation scope.

### Conditionals and operators

`if condition then yes else no` requires a `Bool` condition and compatible
branch types. It evaluates only the selected branch, including when the
branches are IO actions. An `else` belongs to the nearest unmatched `if`.
Use parentheses to pass a conditional as a function argument.

Guarded right-hand sides avoid repeating nested conditionals:

```haskell
sign n
  | n < 0 = -1
  | n == 0 = 0
  | otherwise = 1

main = printInt (sign (-5))
```

Each `|` starts a branch; function guards use `=` and need no semicolons
between branches. They work on top-level bindings, local `let`/`let rec`
bindings, `do`-local bindings, and instance methods. Existing signature and
recursion rules still apply. A binding without parameters can use guards too.

The expression form uses explicit braces, semicolon-separated branches, and
`->`, like `case`. Its braces are required, even across lines:

```haskell
printInt (if { | score >= 90 -> 3; | score >= 70 -> 2; | otherwise -> 1 })
```

Conditions have type `Bool` and are tested in source order. The first true
condition selects its result; later conditions and all unselected results are
not evaluated. Each reached condition occurs once in the nested conditional
translation. Results follow ordinary lazy evaluation, and an IO result executes
only when sequenced. All results, including the fallback, must have compatible
types and are checked even if an earlier condition is literally `true`.

Every guard block requires exactly one final `otherwise` branch, including a
block whose Boolean conditions appear exhaustive. An `otherwise`-only block
is allowed. There is no implicit error, unit result, or fallthrough to another
function equation. Function argument patterns select the equation first; its
guard block is total within that equation. Existing pattern coverage and
unreachable-equation checks still apply: a fallback within `f (Just x)` does
not cover `f Nothing`. Pattern-bound variables are available in that equation's
conditions and results, and cannot escape into another equation.

`otherwise` is contextual syntax only when bare and immediately followed by
the branch's `=` or `->`. It cannot be shadowed in that position. Elsewhere it
remains an ordinary identifier; use `(otherwise)` to test an existing Boolean
variable with that name. Guards do not introduce bindings, pattern guards
(`p <- e`), comma-separated qualifiers, or guarded `case` alternatives. Use
`&&`, `let`, or `case` inside a condition when needed. Both guard forms lower
to the same primitive conditional as ordinary `if`, preserving its type rules
and resistance to shadowing of `ifThenElse`.

Operators have the following precedence, from highest to lowest:

| Operators | Associativity | Meaning |
| --- | --- | --- |
| Function application | Left | `f x y` |
| Prefix `-`, `+` | Prefix | Negation and unary plus |
| `*`, `/`, `%` | Left | Integer multiplication, quotient, remainder |
| `+`, `-` | Left | Integer addition, subtraction |
| `++`, `:` | Right | String concatenation, list cons |
| `==`, `/=`, `<`, `<=`, `>`, `>=` | None | Integer comparisons |
| `&&` | Right | Short-circuit Boolean conjunction |
| `\|\|` | Right | Short-circuit Boolean disjunction |

For example, `f x * 4 + y` means `(f x * 4) + y`, and
`x < 0 || x >= width && enabled` means `x < 0 || (x >= width && enabled)`.
Comparisons cannot be chained: write `x < y && y < z`. An expression annotation
binds below the operators, so `x + 1 : Int` annotates the sum.
The annotation/cons distinction for `:` is described below; `::` always
introduces an annotation.

Arithmetic and comparisons use signed 64-bit `Int`
primitives. `/` truncates toward zero and `%` has the dividend's sign.
They are not overloaded: use `addDouble`, `ltDouble`, or `eqString` for other
types. Signed `Double` literals such as `-2.5e-2` remain supported; negating a
`Double` variable uses `subDouble 0.0 x`. Operators and `if` lower to primitive
identities, so local names such as `addInt` or `ifThenElse` cannot capture them.
Explicit calls to those names still follow ordinary lexical scoping.

Signs now participate in expression syntax: `f -1` and `f - 1` both mean
subtraction. Parenthesize negative arguments as `f (-1)` or `f (-2.5)`.
`--` still begins a comment; write `x - (-1)` or `x - -1` for subtraction of a
negative value. The words `if`, `then`, `else`, and `rec` are reserved.

For example, this retains the MLF instance bound, rather than specializing the
identity function to a monotype:

```haskell
let choose = (\x y -> x) : forall a. a -> a -> a in
let id = \x -> x in
choose id
```

Its inferred type, up to names of bound variables, is
`forall (b >= forall a. a -> a). b -> b`.
The annotation gives `choose` the type used in the thesis: the unannotated
constant function `\x y -> x` has a more general type.

Annotated self-application is accepted:

```haskell
\(f : forall a. a -> a) -> f f
```

Its type is `forall (b >= forall a. a -> a). (forall a. a -> a) -> b`.
Unannotated `\f -> f f` is rejected. Existential annotations are supported, for
example [`examples/partial-annotation.emlf`](examples/partial-annotation.emlf).

## Algebraic data types

Put datatype declarations before the expression; use aligned lines or explicit
semicolons:

```haskell
data Maybe a = Nothing | Just a;

let fromMaybe = \default value ->
  case value of {
    Nothing -> default;
    Just x -> x
  }
in fromMaybe 0 (Just 42)
```

This program has type `Int`. Constructors are ordinary curried values, so
`Just` has type `forall a. a -> Maybe a` and can be passed to functions,
partially applied, or let-bound. Datatype and constructor names start with an
uppercase letter; type parameters and term variables start with a lowercase
letter. Declared names are unique throughout the program. `Int`, `Bool`,
`String`, `Unit`, and `IO` are built-in types. `True`, `False`, and `Unit`
retain their primitive meanings. `Unit` and its constructor are supplied by
the language; omit a separate `data Unit = Unit` declaration.

Declarations may be recursive or mutually recursive:

```haskell
data List a = Nil | Cons a (List a);
data Tree a = Leaf a | Branch (Tree a) (Tree a);
```

Fields contain type parameters, primitive types, declared types, functions,
and explicitly polymorphic types. Parenthesize a field containing type
application, an arrow, or a quantifier, as in `Cons a (List a)`, `Fn (a -> b)`,
or `Poly (forall a. a -> a)`. Parameters default to kind `*`; write an explicit
kind for a higher-kinded parameter:

```haskell
data Wrap (f : * -> *) a = Wrap (f a);
```

Declarations require at least one constructor. GADTs, existential fields,
records, and deriving are not implemented.

Cases use layout or explicit braces and semicolons. A constructor pattern must
have exactly its fields; use `_` to ignore a field. Cases must cover every
constructor or provide a wildcard or variable fallback. A variable alternative
binds the whole scrutinee. Constructor patterns may nest, for example
`Pair (Just x) (Cons y rest)`. Different data types in the same pattern position,
duplicate variables, and non-exhaustive matches are rejected.

MLF can instantiate datatype parameters with polymorphic types:

```haskell
data Box a = Box a;
let boxed = Box (\x -> x) : Box (forall a. a -> a) in
case boxed of {
  Box f -> let number = f 42 in f true
}
```

Ordinary unknown pattern fields are not implicitly generalized. When the
scrutinee already supplies an exact polymorphic parameter interface, as above,
each field use can instantiate that interface. Captured outer type variables
remain shared. A field whose declaration itself begins with `forall` also
supplies an interface and is instantiated automatically at each use:

```haskell
data Poly = Poly (forall a. a -> a);
case Poly (\x -> x) of { Poly f -> let number = f 42 in f true }
```

Fresh source datatypes and class signatures are validated before unused
quantifiers are removed consistently from their inference and emitted layouts.
Checked imported layouts are not rewritten. See
[source field normalization](docs/inference/Source-Field-Normalization.md)
for the exact known-interface boundary, validation and remaining cases.
See [`maybe.emlf`](examples/maybe.emlf),
[`recursive-data.emlf`](examples/recursive-data.emlf), and
[`polymorphic-data.emlf`](examples/polymorphic-data.emlf).

Algebraic data is an extension to the thesis's core xMLF calculus. Generated
output carries the declarations, explicit type arguments for constructor
primitives (`construct Just(Int)`), and the result type of each case. The
independent checker validates declarations, field substitution, pattern scope,
coverage, and all branch result types. Erasure retains constructor tags and
case structure while removing declarations and type arguments.

## Standard prelude

Every compiler entry point imports a small standard prelude from
[`Bootstrap.Prelude`](libraries/mlf-frontend/Bootstrap/Prelude.emlf). It supplies this class, its `IO` instance,
and an instance for local state, `Monad (ST s)`:

```haskell
class Monad (m : * -> *) where {
  return : forall a. a -> m a;
  bind : forall a b. m a -> (a -> m b) -> m b
};

instance Monad IO where {
  return = ioReturn;
  bind = ioBind
};
```

Programs can use `Monad` constraints, declare instances for their own types,
and sequence IO with `do` without repeating those declarations. For example:

```haskell
let twice : forall (m : * -> *) a. Monad m => m a -> m a =
  \action -> do { action; value <- action; return value }
in twice (putStrLn "Hello!")
```

`return` and `bind` are overloaded class methods. A standalone `return 42`
does not determine a monad: write `return 42 : IO Int` or `ioReturn 42` when
IO is intended. Dictionary resolution does not guess a type from the available
instances. `ioReturn`, `ioBind`, and the IO-specific `pure` alias remain
available as primitive operations.

In module-free scripts, ordinary lexical bindings and locally declared class
methods shadow imported method names. A source declaration
named `Monad` replaces the imported class and its associated instances,
allowing the custom hierarchy in `monad-maybe.emlf`. Duplicate instances for
the imported class are rejected by the normal overlap check. Named modules use
the explicit import rules above: hide an imported class or method before
reusing its unqualified name at the top level.

To disable the implicit prelude, put `--no-prelude` before other CLI options:

```sh
"$EMLF_BIN" --no-prelude --type --expr 'return 42'
```

The library exposes `compileWithPrelude`, `compileExprWithPrelude`, and
`compileProgramWithPrelude`, each taking `ImplicitPrelude` or
`NoImplicitPrelude` as its first argument. The existing `compile`,
`compileExpr`, and `compileProgram` functions enable the prelude by default.
Disabling it keeps the built-in types and primitives, including the earlier
IO-specific `return`/`bind` fallback aliases. Parsing and low-level constraint
generation alone do not import the prelude.

Unused prelude declarations are omitted using lexical name and class-reference
analysis. Programs that do not use the prelude retain their previous graphs
and xMLF. Imported
dictionaries undergo the same validation and independent target checks as
user-defined instances; they are not trusted, unchecked runtime dictionaries.

## Type classes

Classes have one or more parameters, each optionally with an explicit kind,
and named method signatures. Instances implement every method. The following
adds a `Maybe` instance to the prelude's `Monad` class:

```haskell
data Maybe a = Nothing | Just a;

instance Monad Maybe where {
  return = Just;
  bind = \value f -> case value of {
    Nothing -> Nothing;
    Just x -> f x
  }
};

let roundTrip : forall (m : * -> *) a. Monad m => m a -> m a =
  \value -> bind value (\x -> return x)
in roundTrip (Just 42)
```

The result is `Maybe Int`. [`monad-maybe.emlf`](examples/monad-maybe.emlf)
contains the full `Functor` → `Applicative` → `Monad` superclass hierarchy,
including a generic function that uses `pure` from an inherited constraint.
Method type variables other than the class parameters are implicitly
universally quantified at kind `*`; explicit `forall` is also accepted.

Use `C a b => ...` or `(C a b, D b) => ...` after a signature's quantifiers.
In constraints and instance heads, parenthesize each argument that contains
type application, as in `Convert (Box a) (Box b)`.
Constraints on ordinary let-bound functions are inferred from their method
uses; each use of the function gets its own dictionary arguments. Explicit
qualified signatures check their bodies polymorphically and make the given
dictionaries available to method calls. Dictionary resolution uses the
inferred types; it does not choose an instance to guess an unknown type.
An unconstrained bare method therefore needs a type or qualified signature.

Instances can have contexts and can use partially applied type constructors,
such as `instance Functor (Either e) where { ... }`. For example:

```haskell
instance Inspect a => Inspect (List a) where { ... };
```

See the complete recursive example in
[`contextual-instance.emlf`](examples/contextual-instance.emlf). Context
predicates must be structurally smaller than the instance head and use only
its variables, counting all arguments together. Single-parameter instance
heads start with a named type constructor; multiparameter heads also allow
variable arguments, including repeated variables such as `Convert a a`. Overlapping
instances, cyclic superclass hierarchies, missing or extra methods, ill-kinded
applications, and unresolved dictionaries are rejected. Declaration order
does not affect instance selection. Class methods share a global namespace;
ordinary local bindings may shadow them.

The implementation translates classes to nominal dictionary datatypes with
polymorphic method fields, and translates constraints to explicit dictionary
arguments. Superclasses are dictionary fields. Instance builders and selectors
use typed recursive xMLF bindings, whose declarations and bodies are checked
by the independent target checker. The erasure check compares against this
dictionary translation. These extensions are additional to the thesis's core
calculus; the compiler checks types, not the algebraic laws of a class.

For example, a class can relate an input type to an output type:

```haskell
class Convert a b where {
  convert : a -> b
};

instance Convert Int Bool where {
  convert = \value -> true
};

convert 42 : Bool
```

Instance selection checks the whole argument list. `Convert Int Bool` and
`Convert Int Int` are distinct instances. There are no functional dependencies
or defaulting: `convert 42` alone leaves its output type undetermined and is
rejected. Supply a result annotation or a qualified signature. Every class
parameter must appear in each method's type; ambiguous methods are rejected.
[`multiparameter.emlf`](examples/multiparameter.emlf) also demonstrates a
recursive instance with a multiparameter constraint.

Default methods, functional dependencies, associated types, bounded method
quantifiers, and constraints nested inside method signatures are not implemented.

## Do notation

Use layout, or explicit braces and semicolons as with `case`:

```haskell
do
  value <- action
  let saved = value
  anotherAction
  return saved
```

`value <- action` translates to `bind action (\value -> ...)`. A statement
without `<-` also uses `bind` and discards its result. `_ <- action` discards
the result explicitly. Local `let` statements are nonrecursive, support
annotations, and generalize like ordinary lets; `let rec` introduces a typed
recursive group. A block must end with an
expression; that expression is used directly, without inserting `return`.
Nested blocks and an optional trailing semicolon are accepted.

`bind` is the function in lexical scope, normally the prelude's `Monad` method.
With `--no-prelude`, its built-in fallback is IO-specific. This lets
`do` work with the existing class machinery or an ordinary local `bind`
function. The translation generates fresh temporary names so discarded results
and pattern matching cannot capture user variables. Nested constructor patterns
are supported when exhaustive, for example `Pair x (Pair y z) <- action` for a
single-constructor `Pair` datatype. Refutable patterns require an explicit
`case`; there is no implicit `MonadFail` operation.

[`monad-state-do.emlf`](examples/monad-state-do.emlf) defines
`class Monad m => MonadState s (m : * -> *)` and a `State s` instance. Its
generic `replace` function uses `get`, `put`, and `do` under a single
`MonadState s m` constraint; `bind` and `return` are obtained from the `Monad`
superclass. The complete program compiles to `Pair Int Int`.

## Local mutable state

`ST s a` describes a local computation producing `a`; `STArray s a` is an opaque
array whose elements can have any type. Both types have kind `* -> * -> *`.
`runST : forall a. (forall s. ST s a) -> a` runs an action with a fresh state
scope. Its nested quantifier prevents an array, usable state action, or mutating
closure from escaping that scope. There is no conversion between `ST` and `IO`.

```haskell
answer : forall s. ST s Int
answer = do
  cells <- newSTArray 2 0
  writeSTArray cells 1 42
  readSTArray cells 1

main = printInt (runST answer)
```

Use the explicit `forall s` action signature with `do`, as above. The current
dictionary inference does not infer that scope for an inline `runST (do ...)`.
Direct `stReturn` and `stBind` operations also work without the implicit prelude.

| Operation | Type |
| --- | --- |
| `stReturn` | `forall s a. a -> ST s a` |
| `stBind` | `forall s a b. ST s a -> (a -> ST s b) -> ST s b` |
| `newSTArray` | `forall s a. Int -> a -> ST s (STArray s a)` |
| `readSTArray` | `forall s a. STArray s a -> Int -> ST s a` |
| `writeSTArray` | `forall s a. STArray s a -> Int -> a -> ST s Unit` |
| `lengthSTArray` | `forall s a. STArray s a -> ST s Int` |

Elements remain lazy and shared. A read captures the value stored when that
action executes; later writes do not change the captured value. Reusing an
action repeats its operations. Empty arrays are allowed, and sizes and
zero-based indices are checked. `runST` demands its final result only to weak
head normal form, preserving lazy constructor fields.

## IO and execution

`IO` is an opaque type of kind `* -> *`. An `IO a` value describes an action
that produces an `a`; creating or returning an action does not execute it.
The following complete program has type `IO Unit`:

```haskell
do {
  putStr "What is your name? ";
  name <- getLine;
  putStrLn (concatString "Hello, " name)
}
```

Run it with `"$EMLF_BIN" --run examples/io-hello.emlf`. Ordinary
compilation, `--type`, and `--check` perform no program IO. `--run` checks the
generated target before executing its final action; the action's result is
discarded. The entry point must have type `IO a` (possibly universally
quantified). Runtime IO errors, including EOF, are reported on standard error
and cause a nonzero exit. Console output is flushed before the next action.

| Operation | Type |
| --- | --- |
| `ioReturn` | `forall a. a -> IO a` |
| `ioBind` | `forall a b. IO a -> (a -> IO b) -> IO b` |
| `getLine` | `IO String` |
| `putStr` | `String -> IO Unit` |
| `putStrLn` | `String -> IO Unit` |
| `printInt` | `Int -> IO Unit` |
| `concatString` | `String -> String -> String` |
| `showInt` | `Int -> String` |
| `addInt`, `subInt`, `mulInt`, `quotInt`, `remInt`, `andInt` | `Int -> Int -> Int` |
| `readInt` | `String -> Int` |
| `eqInt`, `ltInt` | `Int -> Int -> Bool` |
| `addDouble`, `subDouble`, `mulDouble`, `divDouble` | `Double -> Double -> Double` |
| `sqrtDouble` | `Double -> Double` |
| `eqDouble`, `ltDouble` | `Double -> Double -> Bool` |
| `intToDouble` | `Int -> Double` |
| `formatDouble` | `Int -> Double -> String` |
| `newIntArray` | `Int -> Int -> IO IntArray` |
| `readIntArray` | `IntArray -> Int -> IO Int` |
| `writeIntArray` | `IntArray -> Int -> Int -> IO Unit` |
| `lengthIntArray` | `IntArray -> IO Int` |
| `newDoubleArray` | `Int -> Double -> IO DoubleArray` |
| `readDoubleArray` | `DoubleArray -> Int -> IO Double` |
| `writeDoubleArray` | `DoubleArray -> Int -> Double -> IO Unit` |
| `lengthDoubleArray` | `DoubleArray -> IO Int` |
| `newByteArray` | `Int -> Int -> IO ByteArray` |
| `readByteArray` | `ByteArray -> Int -> IO Int` |
| `writeByteArray` | `ByteArray -> Int -> Int -> IO Unit` |
| `lengthByteArray` | `ByteArray -> IO Int` |
| `byteArrayFromString` | `String -> IO ByteArray` |
| `putBytes` | `ByteArray -> Int -> Int -> IO Unit` |
| `getByteLine` | `IO ByteArray` |
| `newIntTable` | `IO IntTable` |
| `readIntTable` | `IntTable -> Int -> IO Int` |
| `writeIntTable` | `IntTable -> Int -> Int -> IO Unit` |
| `eqString` | `String -> String -> Bool` |
| `ifThenElse` | `forall a. Bool -> a -> a -> a` |

`Int` follows Haskell `Int64`: literals, decimal `readInt`, addition,
subtraction, multiplication and negation wrap modulo 2^64, interpreted as
signed two's complement. Its range is -9223372036854775808 through
9223372036854775807. `ltInt` is strict
less-than. `quotInt` truncates toward zero, `remInt` has the dividend's sign,
and division by zero fails at runtime. The minimum value divided by -1 raises
`integer division overflow`; its remainder with -1 is zero. `andInt`, `orInt` and
`xorInt` operate on 64 bits. `readInt` accepts an optional sign and
one or more ASCII decimal digits, with no whitespace or trailing characters.
String equality is case-sensitive. `ifThenElse condition yes no`
evaluates only the selected branch; it also works with functions, datatypes,
and IO actions. Selecting an IO action does not execute it until it is sequenced.

For unbounded arithmetic, use the separate `Integer` type and explicit
`intToInteger`, `integerToInt`, `addInteger`, `subInteger`, `mulInteger`,
`quotInteger`, `remInteger`, `eqInteger`, `ltInteger`, `showInteger`,
`readInteger` and `integerToDouble` primitives. Conversion back to `Int`
wraps. Ordinary numeric operators remain specific to `Int`.

`Double` is IEEE binary64, distinct from `Int`: use `1.0`, `-2.5`, or `3e2`
and convert integers explicitly with `intToDouble`. Literals must be finite;
arithmetic can produce infinities or NaN with ordinary IEEE comparisons.
`formatDouble places value` writes fixed decimals (0–17 places), rounding to
nearest with ties to even and preserving negative zero. Non-finite results
format as `Infinity`, `-Infinity`, or `NaN`.

`IntArray` and `DoubleArray` are opaque mutable arrays with zero-based indices.
Allocation initializes every cell; reads, writes and lengths run through IO.
Writes force the stored numeric value, bounds are checked, and reusing a read
action reads the current cell again. Empty arrays are allowed. For example:

```haskell
do {
  a <- newDoubleArray 3 0.0;
  writeDoubleArray a 1 (sqrtDouble 2.0);
  x <- readDoubleArray a 1;
  putStrLn (formatDouble 9 x)
}
```

Both backends implement these operations. The LLVM backend emits floating
arithmetic directly and stores Double array elements unboxed; Int array cells
store signed 64-bit values. See [numeric semantics](docs/numeric-arrays.txt).

`ByteArray` stores unsigned bytes. Reads return `Int`; writes and initial
values must be between 0 and 255. `byteArrayFromString` allocates a fresh
mutable copy of a string's UTF-8 bytes, including embedded NULs. `putBytes
buffer offset count` writes and flushes that exact slice without text encoding.
Offsets and counts are checked before output. This supports reusable output
buffers and binary formats such as Mandelbrot's PBM bitmap on both backends.

`getByteLine` reads raw bytes through LF, preserving the newline and invalid
UTF-8; EOF returns an empty fresh array. A blank line contains one LF byte.
`IntTable` is a mutable library hash table with signed 64-bit integer keys and
values. Missing keys read as zero; writes insert or replace. Reads return
snapshots, and each execution of `newIntTable` creates a fresh table.
These operations are available in both backends.

The standard prelude connects `return` and `bind` to these operations through
its `Monad IO` instance. `pure` is an IO-specific alias for `ioReturn` in this
minimal prelude. Local bindings and source class methods take precedence.

[`monad-io.emlf`](examples/monad-io.emlf) uses the imported class and instance
in a generic `twice` function with `do`. Running it prints the greeting twice.
Programs that define their own `Monad` class can provide their own IO instance
using `ioReturn` and `ioBind`.

Strings use double quotes, Unicode characters, and Haskell-style escapes such
as `\n`, `\t`, `\"`, and `\\`. `()` is an alias for the `Unit` constructor
in expressions and patterns, and for the `Unit` type in annotations.

### Tuple and list syntax

Tuple and list notation is sugar for ordinary algebraic datatypes. The names
must be declared or imported into unqualified scope; the implicit Prelude does
not supply them. Existing constructor declarations and their lazy evaluation,
type checking, module visibility and pattern coverage rules still apply.

```haskell
data Pair a b = Pair a b
data List a = Nil | Cons a (List a)

first : forall a b. (a, b) -> a
first (x, _) = x

sum : [Int] -> Int
sum [] = 0
sum (x : xs) = x + sum xs

main = printInt (first (sum [10, 20, 12], true))
```

`(x, y)`, `(x, y, z)` and `(w, x, y, z)` mean applications of `Pair`,
`Triple` and `Quad`, respectively. Their type and pattern forms use the same
names. `(x)` remains grouping and `()` remains `Unit`. This initial version
supports two through four components; larger tuples, tuple sections and trailing
commas are rejected. It does not add singleton tuples or tuple-constructor
sections such as `(,)`.

`[]` means `Nil`; `[x, y]` means `Cons x (Cons y Nil)`. A list type `[A]`
means `List A`. List and tuple types also work in datatype fields, for example
`data Batch a = Batch [a] (a, a)`. List patterns have exact length; `(x : xs)`
matches a nonempty list and binds its tail. Cons patterns associate right and
bind less tightly than constructor application. Parenthesize cons patterns in
function or lambda parameters. Nested patterns and do-bind patterns use the
same ordinary pattern compiler. List comprehensions and ranges are outside this
version's scope and have explicit rejection diagnostics.

MLF already uses `:` for annotations. To preserve valid existing annotations,
an expression's single colon retains that meaning when its complete right side
is syntactically a closed type (including explicit existential variables), or
contains type-only syntax such as an arrow, `forall`, a constraint or `bot`.
Otherwise it is cons. Thus `x : xs` is cons, `1 : 2 : []` associates right,
and `1 + 2 : []` means `(1 + 2) : []`. But `x : Nil` retains its historical
annotation meaning, even if a constructor named `Nil` exists; use `x : []` or
`Cons x Nil` for that tail. Similarly, use explicit `Cons` when a constructor
tail also spells a closed type. This decision uses syntax, never inferred types
or constructor lookup.

Use `expression :: annotation` to request an annotation explicitly. Both `:`
and `::` work in value signatures, inline signatures, class method signatures
and parenthesized variable annotations. Kind signatures retain `:`. For
parenthesized patterns the same legacy annotation rule applies to a variable;
`(x : Int)` is an annotated parameter and `(x : xs)` is a cons pattern.
Unparenthesized case and do-bind patterns interpret `:` as cons. Expression
annotations bind below every infix operator, so `1 : [] :: [Int]` annotates the
whole list. `++` remains string concatenation; it is not list append.

Use a file or `--expr` when the program reads interactive input:

```sh
"$EMLF_BIN" --run --expr 'do { printInt 42; putStrLn "done" }'
"$EMLF_BIN" examples/io-hello.emlf > hello.xmlf
"$EMLF_BIN" --run-xmlf hello.xmlf
```

`--run-xmlf` parses and independently checks emitted xMLF before running it.
Without a file, `--run` and `--run-xmlf` consume standard input as source, so
that input stream is unavailable for subsequent `getLine` actions.

The library entry point is `Bootstrap.Runtime.runTerm`, with an `IOBackend` providing
`readLine`, `writeText` and `writeBytes :: ByteString -> IO ()`. It requires an IO entry, as does
`Bootstrap.LLVM.emitLLVMIO`. `Bootstrap.Runtime.runProgram` and `Bootstrap.LLVM.emitLLVM` also
accept pure programs, evaluating them to weak head normal form and discarding
the result. Tests observe action order and failure behavior through both
backends. The runtime keeps data fields, arguments, lets,
and recursive dictionaries lazy, while `ioBind` executes actions in order.
Reusing an action executes it again. There is no pure operation that extracts
a value from `IO`; concurrency and language-level exception handling are not
implemented.

## Snake example

[`examples/snake.emlf`](examples/snake.emlf) is a complete turn-based terminal
Snake game written in the source language:

```sh
"$EMLF_BIN" --run examples/snake.emlf
```

This larger example takes longer to compile than the small examples. To play
again without recompiling, save the xMLF once and run that file:

```sh
"$EMLF_BIN" examples/snake.emlf > snake.xmlf
"$EMLF_BIN" --run-xmlf snake.xmlf
```

Type `w`, `a`, `s`, or `d`, then press Enter to move up, left, down, or right.
Enter alone continues in the current direction; `q` quits. Reverse turns are
ignored, and invalid commands leave the game unchanged. The game prints a new
12-by-8 board after each move: `@` is the head, `o` the body, and `*` the food.
Each meal grows the snake and adds one point. Hitting a wall or the body ends
the game; filling the board wins. Moving into the old tail's square is legal
when the tail leaves on that turn. Food placement is deterministic, choosing
the first free square from the top left. Input uses `getLine`, so the game waits
for a command on every turn.

The example uses layout, function equations, nested patterns, `if` expressions,
and infix operators,
with ADTs for positions, directions, commands, a nonempty snake,
game state, and outcomes. The standard prelude's `Monad IO` instance supplies
`bind` and `return` to the `do` blocks for drawing, input, and the game loop.
Typed recursive functions implement the list helpers and game loop, and local
`let rec` groups implement the food scan and row renderer. The example needs
no `Rec` datatype, explicit fixed-point function, braces, or semicolons.
Movement and food placement are pure functions; only the interface uses IO.

### Native Haskell baseline

[`examples/SnakeBaseline.hs`](examples/SnakeBaseline.hs) implements the same
game with Haskell ADTs, standard lists and `Maybe`, ordinary recursion, and
the standard `IO` monad with `do`. It uses `Int64` to match eMLF's fixed-width
`Int`, and preserves the rules, deterministic food search, prompts, board
format, and flushing after each write. Only the `base` package is needed.

This optional comparison uses GHC. The native test suite instead executes the
independent MLF port in `tests/Tests/SnakeBaseline.emlf`. To build the baseline:

```sh
mkdir -p .mlf-build/snake-baseline
ghc -O2 -Wall -Werror -main-is SnakeBaseline examples/SnakeBaseline.hs \
  -outputdir .mlf-build/snake-baseline \
  -o .mlf-build/snake-baseline/snake-haskell
./.mlf-build/snake-baseline/snake-haskell
```

For compilation timing, add `-fforce-recomp` to avoid an up-to-date build being
skipped. The default `emlf` command produces verified xMLF, which `--run-xmlf`
parses, checks, and interprets on each invocation. `--emit-llvm` followed by
Clang produces a linked native executable. The benchmark below reports each
output separately alongside the GHC native build.

The native `backends` group checks all seven scripted game transcripts against
the independent MLF game and frozen expectations on the xMLF interpreter and
LLVM native code. It also checks eleven pure-rule outcomes, including the
departing tail and full-board win.

## Compiler performance

See [Int64 and Patricia collection qualification](docs/int64-patricia-qualification.md)
for this numeric/collection migration, its retained correctness controls, and
the measured compilation and runtime results, including unmet performance targets.

See [C4 prepared-transaction integration and validation](docs/performance/c4-local-transaction.md)
and [performance-optimization research workflow and literature](docs/performance/optimization-workflow-research.md).
The latter is a set of future recommendations, not an activated measurement
protocol or a claim of new performance results.

Graph validation uses indexed scratch tables for densely numbered graphs,
numbers the binding tree once, and checks kinds, scope, and structural cycles
in one traversal. Rebind uses a memoized dependency traversal and depth-based
lowest common ancestors. Sparse external identities retain the map-based
implementation. `Bootstrap.Graph.Solver` maintains reverse edges and applies this
checked unifier to the affected type component, preserving structural parents,
binding descendants, generalization scopes, and original identities. This
avoids repeatedly traversing unrelated definitions. Local projections compress
unary runs of empty generalization scopes while retaining every type-binding LCA.
The immutable generalization tree is indexed once with DFS intervals and
binary ancestors; component projection and expansion reuse this index instead
of walking deep scope chains for each equation. Expansion shares kind queries
over each structural DAG and checks identity capacity against the actual copy
size, avoiding a whole-graph count per instance. Unification reuses kinds across
merges that preserve them. The tests retain an independent uncached expansion;
updates touch only changed nodes and reverse edges. Closed ground instances
can graft a fresh ground structure or check an existing ground substitution
without copying and unifying the surrounding graph. General instances retain
the full expansion path. Full graph and index checks bracket inference, and
differential tests compare both paths against the original solver. Target
computation checking validates each public environment once, retaining kind
checks on every recursive source/result type as it extends that environment.

Elaboration caches datatype metadata and constructs `Inst-Refl` for
alpha-equivalent edges. For other edges it first tries structural
correspondence between existing source and target nodes, accepting only an
independently checked xMLF computation with the exact target type. Failed
candidates retain expansion, frontier solving, and identity-based evidence
construction. The compiler still checks graph invariants, unification
permissions, target typing, and source erasure.

The native backend lowers eligible first-order numeric IO functions to direct,
bounds-checked array loops with unboxed Double intermediates and recursive
arguments. Specialized workers preserve proven integer ranges, while checked
machine multiplication/division retain the full Int64 runtime fallback. A non-forcing argument
guard preserves the lazy fallback; actions remain repeatable. GMP
arithmetic for explicit `Integer` values reads immutable operands directly and collection also accounts for
large-integer limb storage. Allocating byte/array/table IO uses explicitly
rooted native calls. Adjacent table count updates fuse, and guarded copy loops
use LLVM memory intrinsics. See [backend design](docs/llvm-backend.txt).

The native compiler builds with Clang `-O2` and the compact BDWGC runtime.
[Compiler-only PGO](tools/profile/README.md#compiler-only-profile-guided-optimization)
trains on frozen compiler sources, without benchmark programs or inputs.
The [2026-10-18 verification](tools/profile/RESULTS.md) passed all six native
test groups and the seven-sample **3× C compilation / 2× C runtime** gate for
every one of the nine workloads. Compilation includes fresh runtime C, LLVM
compilation, and linking; exact-executable runtime warm-up is applied equally
to C and MLF. Every observed maximum MLF time divided by the corresponding
minimum C time also remained below its limit.

The later [crate migration acceptance](docs/crate-validation.json) uses reproducible
O2 profiling of the compiler and runtime, trained only on fifteen existing language
examples. Its fresh six-group validation and full nine-workload, three-sample
median gates pass the same 3x compilation / 2x runtime limits. See the
[construction instructions](docs/package-manager.md#native-profile-guided-construction)
and [acceptance ledger](docs/crate-migration.md) for this configuration and its
separate frozen build measurements.

Use the [native benchmark guide](tools/bench/README.md) to build the runner and
configure the generic LLVM/linker backend used by that performance result.
Its final arguments explicitly select the per-workload limits:

```sh
MLF_BENCH_STREAM_LINK=1 MLF_BENCH_STREAM_LLVM=1 \
MLF_BENCH_MLF_CLANG="$PWD/.mlf-build/backend-ready-link/clang-mlf" \
  .mlf-build/native-bench-driver/bin/bench \
  /absolute/path/to/optimized/emlf /absolute/path/to/baseline/emlf \
  "$PWD/.mlf-build/native-bench-results" 7 /absolute/path/to/clang 3 2
```

The configuration, runner, and compilers must be built first, and the output
directory must be new. Run measured jobs alone. The
[results](benchmarks/RESULTS.md) retain raw samples, medians, variation, source
and toolchain hashes; [self-compilation profiling](tools/profile/README.md)
reports the separate frozen-source comparison and diagnostic timing boundaries.

### Compiler shape classification benchmark

The [compiler shape benchmark](tools/performance/compiler-shapes/README.md)
answers a different question from the C/MLF Benchmark Game above. It compiles the
same generated shared-Haskell program with GHC and with MLF for ten program shapes
at sizes 8, 32 and 128, and reports where compile time goes per shape instead of
gating pinned application workloads. One entry point drives the whole benchmark:

```sh
python3 -B tools/performance/compiler-shapes/bench.py list
python3 -B tools/performance/compiler-shapes/bench.py all \
  --workdir .mlf-build/compiler-shapes --cohort default-20261031 \
  --producer .mlf-build/shared-ghc --build-builtin
```

`--family` and `--size` filter the matrix, `--matrix smoke` is the 18-compilation
check that ordinary pull requests run, and `analyze.py` writes `summary.json`,
`summary.csv`, `samples.csv` and a human `summary.md`. The measured endpoint is the
bootstrap crate route (`--compile-crate`, then `--crate-to-llvm-gc`, then Clang
`-O2`), not the installed `emlf SOURCE -o` driver; the setup, plan and report state
that endpoint, and the analyzer refuses cohorts that differ in endpoint, toolchain,
host or repeat count. The runner contract in [tools/bench](tools/bench/README.md)
is unchanged.

The current cohort (2026-10-31, `b81f9b0a`) completed the full 31-cell, 186-compilation
matrix with no failures: MLF was slower in all 30 shaped cells, with ratios from
2.28 to 5.03 and a mean that rises from 2.57 at n=8 to 3.19 at n=128. The minimal
program alone costs 1.133 s versus 0.445 s for GHC, and the group-heavy families
grow with their fresh target-group count. Three repetitions describe spread on one
host; they are not a confidence interval, and no universal speed claim follows.

### Preserved benchmark baselines

The pinned C, Rust, and Haskell implementations under [benchmarks/](benchmarks/)
and [the independent Snake game](examples/SnakeBaseline.hs) remain unchanged,
along with their provenance, fixtures, and archived measurements. The historical
Cabal/Python benchmark launcher has been retired. Use the
[native benchmark runner](tools/bench/README.md) for current C/MLF comparisons;
it builds through the MLF package manager. Haskell and Rust baseline builds are
optional comparisons outside the compiler build and test dependencies. Historical
reports retain the exact commands and toolchain identities used for those runs.

## Implementation and thesis correspondence

| Stage | Implementation | Thesis |
| --- | --- | --- |
| Parse and resolve source binders | `Bootstrap.Parser`, `Bootstrap.Constraint` | §9.4 |
| Embed annotation types and desugar annotations to coercions | `Bootstrap.Constraint` | §8.2.2, §12.3.2 |
| First-order unification, then `Rebind` and permission checks | `Bootstrap.Graph.unify` | Figures 7.3.1–7.3.2 |
| Expand schemes with frontier equations and binding/flag reset | `Bootstrap.Graph.expand` | §10.1 |
| Solve equalities, then instance edges in dependency order | `Bootstrap.Constraint.solve` | Figure 12.1.1 |
| Normalize the presolution for translation | `Bootstrap.Graph.normalize` | §15.2.6–15.2.8 |
| Translate types in leftmost-lowermost order | `Bootstrap.Elaborate` | §15.2.7, Figure 15.3.2 |
| Generate computations and elaborate terms | `Bootstrap.Elaborate` | §15.3.2–15.3.10, §15.4.1 |
| Independently check xMLF | `Bootstrap.X.Check` | Figures 14.2.6 and 14.2.8 |

As recommended by §15.3.10, elaboration happens **after** inference. Reflexive
instance edges use `Inst-Refl`; other edges are re-expanded from the final
presolution. The unifier's map from copied nodes to their destinations supplies
identity-based evidence.
The elaborator introduces target quantifiers in dependency order and consumes
source bounds at their mapped destinations. This groups graft/raise/merge/
weakening operations as discussed in §15.4.1, and explicitly witnesses
quantifier reordering; it does not implement a literal one-operation-at-a-time
trace of Figure 15.3.4.

The implementation uses the modular normalization of §15.2.8: all inert nodes
are weakened, rigid bounds are inlined, and existential nodes do not introduce
spurious type abstractions. The let constraint uses §15.2.6's extra enclosing
scope, so the type abstractions needed by the bound expression remain in scope.
Syntactic source alias bounds are normalized during graph embedding (§15.6.2).

The target checker uses only alpha-equivalence. It checks all eight type
computations, including the `Inst-Hyp` bound premise; it intentionally does not
use the unchecked type-computation function in Figure 14.2.7. It allows lexical
quantification within types and prevents variable capture by computation and
term binders. It provides no rule to instantiate under an arrow or constructor.

Every successful compilation checks both:

1. The xMLF term has the type extracted from the normalized presolution.
2. Erasing its types and computations gives exactly the resolved source term
   after annotation desugaring (§15.3.14).

The MLF API is `Bootstrap.Compiler.compile : String -> String -> Either
CompileError Compilation`. Use `compileProgram` for an `SProgram` AST containing
declarations, or `compileExpr` for an expression without declarations. Use
`Bootstrap.Parser.parseProgram` for closed programs, or `parseModule` with the
module-aware APIs described above for imports. A `Compilation`
contains `inferredType` (the explicit target type), `sourceType` (the source
display with class constraints), `compiledTerm`, and the normalized `presolution`.
The checker and xMLF parser can be used independently of the compiler.

This is a reference implementation using persistent maps, explicit graph
validation, and simple least-common-ancestor queries. It does not implement the
linear-time data structures discussed in §7.5, and rigid-bound inlining can
duplicate types, as discussed in §15.4.
Permission calculations are cached per immutable graph, and binding-tree
reconstruction uses a dependency queue while retaining every validation check.

## Validation

The native `unit` group exercises the eight computation rules and their failure
cases, capture-avoiding substitution, alpha-equivalence, rigid/skolem checks, graph
domination, expansion reset, let scopes, `choose id`, `g g`, arbitrary-rank
annotations, existentials, and the source examples. Generated xMLF is printed,
parsed again, and checked in the targeted and annotation tests.

The datatype regressions cover constructors, recursive declarations, matching,
polymorphic type arguments, invalid declarations and patterns, and independently
constructed invalid target terms. Every successful source regression also
prints, reparses, and checks its generated xMLF.

The class regressions cover higher kinds, polymorphic methods, generic
qualified functions, superclass dictionaries, recursive contextual instances,
instance overlap and termination, lexical shadowing, and invalid independently
constructed target bindings and type computations. Successful cases also
round-trip through the standalone xMLF parser and checker.

Multiparameter regressions check joint instance matching, repeated parameters,
simultaneous substitution, parameter kinds and arity, ambiguity, and superclass
projections that reorder or drop parameters. Do-notation tests check statement
order, lexical scope, fresh temporary names, local polymorphism, constructor
patterns, invalid blocks, and integration with `MonadState`.

Native execution tests share `tests/Tests/Backends.emlf`;
fixtures cannot select just one backend. Each matrix row must complete on
both the interpreter and LLVM, with the same outcome, ordered IO trace, and
remaining input. Frontend-only type and rejection assertions run once.

IO tests run printed-and-reparsed target programs through both backends.
They cover console traces, repeated actions, lazy unused actions, recursive
dictionary methods, polymorphic `Monad IO` functions, EOF and backend errors,
and representative monad-law traces. Invalid target programs are rejected
before effects, and forged IO constructors, types, or primitive signatures are
rejected independently of inference.

Prelude tests cover automatic IO dictionaries, generic functions at IO and
user-defined monads, superclass and instance contexts, lexical and class
shadowing, explicit opt-out through every compiler API, ambiguity, instance
overlap, and the unchanged output of programs that do not use the prelude.

Snake tests execute the actual example through both generated and
printed/reparsed xMLF on each backend. Scripted sessions check the rendered boards, WASD input,
quit, invalid commands, growth, reverse turns, and wall/body collisions.
Additional checks call the example's pure rules to cover all four walls,
the departing tail, food occupancy, and the full-board win.

An independent Algorithm W implementation in `tests/Tests/Oracle.emlf` checks the
unannotated-language typability correspondence of Theorem 12.3.1. The corpus
contains all 1,712 closed terms through AST size 6 plus 5,000 deterministic
larger terms, including both accepted and rejected programs. Another corpus
contains 126 typed annotation programs over polymorphic and nested types.
These tests do not substitute the inference engine for its own oracle, and
elaboration/verification failures are never treated as legitimate rejections.

The Figure 12 suite within the native `unit` group tests examples from the
**MLF column** of Figure 12 in
[A Quick Look at Impredicativity](https://simon.peytonjones.org/assets/pdfs/impredicativity.pdf).
It covers all 34 rows and 43 expressions, using the paper's library signatures
and checking printed/reparsed xMLF for every accepted expression. **All 43
regression cases pass; 42/43 outcomes agree with the paper.** A8 (`choose id auto'`)
expects rejection for the explicit signature
`forall b. (forall a. a -> a) -> b -> b`, matching the authors' `camlf` reference
prototype. Its test requires an inference failure with the protected-variable
raising diagnostic. The paper's acceptance claim is stored separately and the
suite reports the discrepancy; a passing suite does not mean full table
agreement. See [the reference comparison](docs/figure12-a8-reference.txt).

```sh
./mlfpkg --compiler "$MLF_COMPILER" --timeout 21600 test --target unit
```

See [the test report](docs/figure12-results.txt) for the encoding, type checks,
and [a closed A8 reproduction](tests/fixtures/figure12-a8.emlf). Passing this
table is a finite conformance check, not a proof of theoretical completeness.
