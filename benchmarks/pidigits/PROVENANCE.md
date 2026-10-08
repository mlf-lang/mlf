# pidigits

Sources use Benchmarks Game revision `40296663ed350d5fe4a6ab5e367bab61cb77c219`,
with original sources, Git blob IDs, hashes, and exact patches in the manifest.
The shared [BSD license](../LICENSE.BenchmarksGame) applies to the baselines.

- C: Mr Ledrug's `pidigits-gcc-1`. Add the missing partial output row and
  release GMP storage at exit; retain the spigot arithmetic unchanged.
- Rust: TeXitoi's `pidigits-rust-1`, derived from the same C algorithm. Replace
  Linux/x86-only C type aliases with `std::os::raw` and the obsolete unsafe
  `uninitialized` pattern with `MaybeUninit`. No Cargo packages are needed.
- Haskell: `pidigits-ghc-6`, by Bryan O'Sullivan, Eugene Kirpichov, and
  W. Gordon Goodsman. Unchanged source; the three-integer spigot state matches
  C/Rust, including the early unsafe-digit guard and both extractions.
- MLF: the same recurrence in `mlf/main.emlf`, using `mulInt`, `quotInt`,
  `remInt`, recursion, and prelude IO. Digits accumulate into output rows;
  every extracted digit is calculated, including both extract(3)/extract(4).

All implementations are single threaded and use arbitrary-precision arithmetic.
C/Rust mutate GMP buffers, MLF uses immutable GMP-backed integers, and GHC
uses its Integer implementation. GMP calls implement individual arithmetic
operations, never the core spigot loop. These allocation and library differences
remain part of the comparison. Final partial-row whitespace differs harmlessly.

The [official specification](https://benchmarksgame-team.pages.debian.net/benchmarksgame/description/pidigits.html)
requires the sequential spigot. Correctness uses its pinned 30-digit fixture
and an independent fixed-point Machin formula oracle, including partial rows.
Input is a positive digit count, passed by argv to baselines and stdin to MLF;
input parsing and output are included in runtime timing.
