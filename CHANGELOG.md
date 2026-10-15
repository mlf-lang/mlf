# Changelog

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
