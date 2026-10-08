# mandelbrot

Sources come from Benchmarks Game revision
`40296663ed350d5fe4a6ab5e367bab61cb77c219`. Original files, exact patches,
Git blob IDs, URLs and SHA256 hashes are retained in the [manifest](../manifest.json).
The shared [BSD license](../LICENSE.BenchmarksGame) applies.

- C: Greg Buchholz's `mandelbrot-gcc-2`, the scalar sequential implementation.
  The only change makes the packed byte accumulator unsigned, avoiding signed
  left-shift behavior on platforms where plain `char` is signed.
- Rust: Matt Watson and TeXitoi's `mandelbrot-rust-1`. The patch replaces the
  thread dispatcher with sequential row traversal and handles a final partial
  output byte with zero padding. It retains the upstream eight scalar lanes,
  early escape mask, coordinate vectors and complete image storage. There are
  no SIMD intrinsics, architecture-specific types or external crates; compiler
  auto-vectorization is allowed for every baseline.
- Haskell: `mandelbrot-ghc-2` by Spencer Janssen, Trevor McCort, Christophe
  Poucet, Don Stewart and Tim Newsham. The patch runs the original scalar row
  generator sequentially, begins at byte zero (the upstream dispatcher started
  at one), rounds row storage upward for partial bytes, and frees each row
  after writing it. The scalar `fractal`, `loop_x` and `next_x` functions are
  unchanged. Foreign memory only stores output; all pixel iteration is Haskell.
- MLF: `mlf/main.emlf` computes each scalar orbit for at most 50 steps,
  stores its numeric state in a six-element DoubleArray, and packs bits into
  one reusable ByteArray row. Doubling and adding a bit perform ordinary
  byte packing; the runtime provides only checked storage and raw slice output.

All implementations are sequential and calculate every pixel. Rust keeps
updating escaped lanes until all eight have escaped; the scalar versions
stop each pixel individually. Rust stores the whole bitmap; Haskell and MLF
store rows. Rust/Haskell precompute `2/n` for coordinates, while C/MLF divide
`2*x` and `2*y` by n. These source differences remain visible in the comparison.

The [official specification](https://benchmarksgame-team.pages.debian.net/benchmarksgame/description/mandelbrot.html)
supplies the n=200 binary PBM fixture. Correctness compares exact bytes with
an independent Python complex-number recurrence at every checked input,
including the timing input: dimensions, raster, MSB-first packing and zero
row padding must all match. Sizes 1, 2, 7, 8 and 9 exercise small and partial
rows. No whitespace normalization or floating tolerance is applied to a bitmap.
