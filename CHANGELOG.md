# Changelog

## Unreleased

- Add ordered Boolean guards on binding right-hand sides and braced guard
  expressions, with a required final `otherwise` fallback. Lower guards to
  existing conditionals, preserving lazy branch selection, type checking,
  pattern scope, and ordinary `if` syntax.
- Add structured asynchronous process scopes and cold, typed cooperative
  tasks/fibers in the separate `mlf-async` library. Share native process
  containment with the compatible static build runner; add traced completion
  cells, timers, bounded fan-out, cancellation and interpreter/native parity
  gates. CPU-parallel work remains isolated in child processes. The explicit
  two-stage bootstrap builds the primitive-aware compiler and matching package
  manager; released tools cannot directly execute the new async primitives.

- Add tuple and list expression, pattern and type sugar, including datatype
  fields and right-associative list cons. Lower to in-scope `Pair`, `Triple`,
  `Quad`, `List`, `Cons` and `Nil` without new runtime representations. Preserve
  closed single-colon annotations and add explicit `::` annotations; document
  the constructor-tail ambiguity and the initial two-to-four tuple arity limit.
- Add a separate `tuple-list` root test target with fixed parser expectations,
  frozen target-checker validation, module-scope and lazy interpreter checks.
  The POSIX `tuple-list-native` target also checks nine interpreter/native
  fixture results through a freshly built compiler.
- Add portable MLF regular expressions and regex-redux, completing coverage of
  all ten current Benchmarks Game workloads. Pin sequential C/Rust/Haskell
  baselines and their regex dependencies, and check exact output with an
  independent oracle and native/interpreter regressions. Historical performance
  results cover nine workloads; regex-redux performance is not yet qualified.

## 0.3.0 — 2026-10-22

- Use compact-GC as the sole native LLVM/runtime layout. Remove the standard
  object header, pooled allocator and IO-boundary collector. All native builds
  require BDWGC; explicit `standard` package profiles are rejected and old
  standard LLVM/object files must be regenerated. Preserve `-gc` CLI aliases.
- Share verified library and test artifacts, remove exact duplicate executions,
  reduce oversized matrices and drop the outer port interpreter pass. Preserve
  independent references, semantic regressions, GC debug/audit coverage,
  575 backend rows and 25 native port fixtures.
- Consolidate CI and release qualification on one compact-GC profile, including
  native SDK linking and Windows collector DLL deployment. Use the collector
  import library for Windows native parity links, matching ordinary package
  builds and avoiding unresolved static pthread dependencies.
- Reduce optional LLVM backend compilation overhead through a generic lite
  pipeline while retaining input/output verification and O1 register allocation.
  Nine pinned workloads pass unchanged compilation/runtime limits; n-body
  compilation is close to the 3x C limit. Retain historical measurements and pins.
- Record complete native test timings and ignore local compiler/debugger outputs,
  system files and release workflow scratch files.

## 0.2.0 — 2026-10-20

- Compile libraries and targets as crates with cycle-tolerant module namespaces,
  declaration/SCC inference, persistent checked semantic queries, generated
  `.mlfci`/`.mlfco` artifacts, and cached LLVM/native build stages. Preserve MLF's
  principal polymorphism and existing closed-signature recursion rule. Retire
  the per-module compiler and linker commands.
- Remove the Haskell compiler, Cabal project, and retired Haskell/Python test,
  bootstrap, release, and benchmark launchers. Native MLF package builds and
  all six native test groups are the supported workflow.
- Consolidate shared C fixtures under `tests/native/`, move local BDWGC
  discovery to `.mlf-build/deps`, and remove Python command placeholders.
- Preserve pinned cross-language benchmark baselines, Snake, frozen oracle
  data, and archived measurements; update build, test, and release docs.

- Add native Windows and Linux developer previews alongside macOS ARM64.

- Add native Windows x64 compiler and package manager executables, Win32
  process jobs and locks, UTF-8 paths and arguments, and Win64 GMP conversions.
- Support package planning, local dependency locks, cached builds, interpreter
  and LLVM tests, and executable publication on Windows with native libraries.
- Accept drive-rooted and UNC crate paths, preserve their cache locations, and
  share native Windows filesystem command translation between compiler queries
  and package builds. Keep relative crate paths invalid.
- Support deep content-addressed cache paths on Windows without machine-wide
  long-path settings. Exercise Unicode files, atomic replacement, links,
  redirects, locks and cleanup past MAX_PATH under both runtime layouts.
- Validate Windows drive-rooted and UNC dependency receipts so unchanged crate
  builds reuse their checked artifacts while retaining exact-file hash guards.
- Emit Windows COFF objects and PE executables without wall-clock timestamps,
  preserving byte-identical clean/incremental builds and native link cache reuse.
- Reduce compiler bootstrap memory through checked separate compilation,
  preserving independent checking and module boundaries.
- Add native `--version` reporting and platform-specific release packages,
  checksums, installation and relocation checks for Windows, macOS and Linux.
- Retain platform-specific validation evidence. Windows compiler qualification
  uses the independent 7,086-case parity corpus, both runtime layouts, native
  self-builds and package integration tests; its internal POSIX compiler-test
  transports and historical performance gates are not claimed as Windows tests.
- Consolidate 17 repeated unit cases into the dual-backend port tests,
  merge runtime smoke into the full runtime fixture, and share the unchanged
  68 ST inputs. Preserve all independent reference and execution-path coverage.
- Run Windows package and parity qualification through the native MLF harness,
  including 18 resolver checks, 26 package integration cases, and 7,086 parity
  cases. Preserve the frozen type/rejection oracles and both runtime backends.
- Build test executables from their actual module dependencies, with a small
  shared support library, so port and package qualification do not first compile
  unrelated test cases. Preserve every active module and execution assertion.
- Avoid rebuilding primitive type signatures just to obtain runtime arities.
  Check all 82 arities against their unchanged type signatures.
- Evaluate directly applied primitives without constructing intermediate partial
  applications. Preserve lazy arguments, partial application, error order and
  function-valued results, with interpreter and LLVM regression checks.
- Record matrix collection policy and use more frequent port collection on
  release-test hosts with at most 8 GiB RAM. Keep the faster default policy on
  larger hosts and preserve both runtime layouts and all fixture limits.

## 0.1.1 — 2026-10-18

Compiler performance and native development improvements.

- Reduce graph solver allocation and repeated index/projection work while
  preserving independent xMLF verification, inferred types, source erasure,
  module boundaries, and opaque checked witnesses.
- Improve compact runtime allocation, thunk forcing, strict unary wrappers,
  and LLVM emission; add focused native regression coverage.
- Add reproducible native compiler profiling, compiler-only PGO tooling,
  streaming compilation, and configurable per-workload benchmark limits.
- Verify all nine Benchmarks Game workloads with seven samples against an
  explicit 3× C compilation / 2× C runtime gate. Every workload passes,
  including each observed MLF maximum divided by the C minimum. These results
  identify the exact locally tested PGO compiler, backend configuration,
  sources, and toolchain; they do not measure the release archive's binary.
- Retain raw reports, all experimental samples, LLVM equality checks, all six
  native test groups, and frozen-source self-compilation measurements. Ordinary
  self-compilation improves from 257.289087s to 181.955334s median on that host.
- Rewrite the README build/run instructions for the native compiler and
  package manager, and update native self-compilation profiling documentation.
- Separate quick package integration CI from manually requested compiler
  self-hosting; allow long hosted-runner bootstrap stages without changing
  individual test fixture limits.
- Use current Node 24 GitHub Actions, pinned to reviewed commit hashes.

## 0.1.0 — 2026-10-15

First developer preview of the self-hosted MLF toolchain.

- MLF inference, checked xMLF elaboration, interpreter, and LLVM backend.
- Algebraic data types, multiparameter classes, IO, `do` notation, layout,
  recursive declarations, infix syntax, and nested patterns.
- Modules, separate compilation, `.mlfi` interfaces, and `.mlfo` objects.
- Native `mlfpkg`, local dependencies, content-based caching, and lock files.
- Compiler tests ported to MLF with independent oracles and retained coverage.
- All six native test groups passed on macOS ARM64, including 7,086 parity
  cases, both execution backends and runtime layouts, and a fresh compiler
  fixed point. GHC, Cabal, and Python were blocked during that validation.
- A relocatable macOS 26+ ARM64 archive with compiler, package manager,
  runtime sources, installer, checksums, and validation records.

The package manager supports local dependencies; remote registries and version
solving are not implemented. Other operating systems and architectures have
no prebuilt release in this preview. Historical C performance comparisons are
retained under `benchmarks/results`; this release does not claim new performance
measurements for its exact compiler binary.
