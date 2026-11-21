# Repository Guidelines

## Project Layout

MLF and GHC share `.hs` sources in `libraries/mlf-*/`. CLI entry points are
`bootstrap/MLF/Entry/Emlf.hs` (compiler) and `package/MLF/Entry/Mlfpkg.hs`
(package manager). `host/ghc/` holds GHC adapters and `runtime/` the C runtime.
Find programs in `examples/`, suites and fixtures in `tests/`, `mlf-test` in
`testing/`, and inference references in `papers/`.

## Build and Run

Native builds require Clang/LLVM, GMP, `pkg-config`, and BDWGC. From the root,
use matching stage-1 `MLF_COMPILER` and `MLF_PACKAGE_MANAGER` tools and set
`MLF_GC_PREFIX` to BDWGC’s prefix. [Native bootstrap](README.md#build-and-run)

- `./mlfpkg --locked build` builds native tools. Run `./mlfpkg lock` after
  intentional source or manifest edits.
- `.mlf-build/bin/emlf --run examples/modules/Main.emlf` checks imports, printing `25`.
- `python3 tools/shared/build.py --typecheck-only --build-dir .mlf-build/ghc-typecheck`
  typechecks with GHC 9.14.1.

## Coding Conventions

Read callers and tests. Reuse types and helpers. Preserve CLI exit status,
error phase, and other behavior outside the request.

Shared modules use two-space nesting. Align sibling declarations and `do`
statements. Types and modules use `UpperCamelCase`, functions `lowerCamelCase`.
Mark shared modules `-- mlf:syntax shared-haskell-v1` and register them in
their package manifest, `shared-sources.json`, and `mlf-shared.cabal`.
CI compares parse trees after Ormolu formatting. [Formatter check](docs/shared-source/Formatter-Compatibility.md)

## Testing Guidelines

`./mlfpkg --timeout 21600 test --target unit` runs unit tests. Use
`--target backends` for interpreter/LLVM coverage. Omit `--target unit` for all tests.

Cover untested regressions. Assign stable `mlf-test` IDs like
`int-set/union-sorted-list`. Register private modules in importing targets’
`modules` maps (`tests/mlf-package.json`). Derive expectations independently
and explain `tests/golden/` inventory changes. [Test coverage](tests/README.md)

## Compiler Performance

1. Profile the original workload. Extract the smallest program that reproduces
   the bottleneck.
2. Add the shape and its independent output oracle to
   `tools/performance/compiler-shapes/generate.py`. Register the family in
   `matrix.json`. Run `bench.py` with `--family` and `--size`. If feedback
   is slow, profile and reduce the example again.
3. Optimize MLF until checks pass and median compilation wall time beats GHC’s on
   identical source (`mlf_over_ghc < 1`). Only then reprofile the parent
   workload. Repeat until end-to-end timings confirm the original slowdown is
   gone. [Compiler-shapes harness](tools/performance/compiler-shapes/README.md#running-it)

## Commits and Pull Requests

Use imperative subjects (`Fix macOS toolchain dependency provenance`), optionally
scoped (`fix(ci):`). Write self-contained PRs and final reports covering the problem, change,
commands, results, assumptions, and outstanding checks. [PR template](.github/PULL_REQUEST_TEMPLATE.md)

## Agent Coordination

Resolve reversible choices from nearby code. Verify behavior through its normal
entry point. Ask before expanding scope, before irreversible actions, or when
blocked on input.
