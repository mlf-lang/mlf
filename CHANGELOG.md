# Changelog

## Unreleased

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
