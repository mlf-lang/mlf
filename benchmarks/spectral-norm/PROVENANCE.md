# spectral-norm

Sources are pinned at Benchmarks Game revision
`40296663ed350d5fe4a6ab5e367bab61cb77c219`. The [manifest](../manifest.json)
records original Git blob IDs, URLs, build sources and SHA256 hashes;
the shared [BSD license](../LICENSE.BenchmarksGame) applies.

- C: Sebastien Loisel's `spectralnorm-gcc-1`, unchanged. It computes matrix
  entries on demand and accumulates scalar matrix-vector products in arrays.
- Rust: Rust Project Developers, TeXitoi and Tung Duong's `spectralnorm-rust-3`.
  The documented patch replaces the thread dispatcher with one call over the
  full output and handles the final single element at odd sizes. It retains
  the two scalar accumulators and `div_and_add` helper; there are no explicit
  SIMD types/intrinsics, external crates, or unsafe thread aliases in the build.
- Haskell: Greg Buchholz's `spectralnorm-ghc-2`, unchanged, using the boot
  `array` package's unboxed arrays and scalar matrix entries.
- MLF: `mlf/main.emlf` implements separate matrix-entry, A-times-vector,
  transpose-times-vector and A-transpose-A functions. All 40 matrix-vector
  products execute; mutable arrays hold vectors, and each row's sum is carried
  in a scalar recursive argument and stored once after its final element.

All programs are sequential, start from ones, perform 20 applications of
A-transpose-A, and compute the same final norm estimate. Rust divides by the
denominator and sums two lanes; C/Haskell/MLF multiply by its reciprocal.
Haskell/MLF calculate the denominator in Double, which is exact over the
supported sizes. Rust/C use bounded machine integers. These association and
storage differences are retained and documented rather than rewriting baselines.

The [official specification](https://benchmarksgame-team.pages.debian.net/benchmarksgame/description/spectralnorm.html)
requires the matrix-free power method and supplies the pinned n=100 fixture.
An independent Python reference materializes the matrix and uses `math.fsum`
for products; every checked input, including the timing input, must yield
exactly one finite number within absolute error `1e-8`. Sizes 1, 2 and 3 cover
the smallest matrix and Rust's odd tail. The reference runs outside timing.
