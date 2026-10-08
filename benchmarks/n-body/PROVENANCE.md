# n-body

The baseline revision is `40296663ed350d5fe4a6ab5e367bab61cb77c219` of the
Benchmarks Game repository. Original files, Git blob identities, URLs and SHA256
hashes are pinned in [the manifest](../manifest.json); the shared
[BSD license](../LICENSE.BenchmarksGame) applies.

- C: Christoph Bauer's `nbody-gcc-1`, unchanged.
- Rust: Rust Project Developers and TeXitoi's `nbody-rust-1`, unchanged.
- Haskell: Olof Kraigher and Don Stewart's `nbody-ghc-1`, with Ersin Er's GHC
  compatibility fix, unchanged. It uses `Foreign` to store 35 doubles, but the
  entire integration algorithm is Haskell code. Its memory API is not a foreign
  implementation of n-body. `-XBangPatterns` replaces the obsolete flag spelling
  suggested in its source comment.
- MLF: `mlf/main.emlf` stores the same seven fields per body in a contiguous
  35-cell `DoubleArray`. Initialization, momentum offset, all ten pair updates
  per step, position updates, and both energy calculations are MLF functions.

All four are scalar and single threaded. No fast-math flag is used. C and MLF
update all velocities before positions; Rust/Haskell move each body's position
after its remaining pairs, which gives the same integrator. Minor association
differences in distances, momentum and energy are retained from upstream.
MLF emits LLVM floating arithmetic and square root; array state is sequenced
through IO. Its boxed Double values, checked indexing and IO action allocation
remain measured overhead, unlike the baselines' direct mutable memory access.

The [official specification](https://benchmarksgame-team.pages.debian.net/benchmarksgame/description/nbody.html)
allows an absolute error of `1e-8`. The runner requires exactly two finite
energy values, compares against an independent Python scalar reference at every
checked input (including the timing input), and checks the pinned 1000-step
fixture. Zero and one step check initialization and the first integration step.
Reference execution is outside all measured intervals. Baselines read argv;
MLF reads stdin. Both parse/output costs stay in runtime samples.
