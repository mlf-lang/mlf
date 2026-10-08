# fannkuch-redux

The baseline revision is `40296663ed350d5fe4a6ab5e367bab61cb77c219` of the
Benchmarks Game repository. Original sources, exact adaptation patches, Git blob
identities, URLs and SHA256 hashes are pinned in [the manifest](../manifest.json).
The shared [BSD license](../LICENSE.BenchmarksGame) applies.

- C: `fannkuchredux-gcc-1`, Joseph Piché's C version of Oleg Mazurov and Isaac
  Gouy's program, unchanged. It uses three indexed integer arrays, incremental
  prefix rotations, full prefix reversal, alternating checksum and maximum flips.
- Rust: `fannkuchredux-rust-2`, Rust Project Developers and TeXitoi. Replace only
  the four-thread dispatcher with one `work` call over the full permutation
  range and remove the thread import. Keep its fixed 16-slot arrays, factoradic
  starting-position setup and incremental generator. This also makes n=1 and
  n=2 well defined, whereas the original partition size would be zero.
- Haskell: `fannkuchredux-ghc-4`, by Branimir Maksimovic, Bryan O'Sullivan,
  Gabriel Gonzalez and Artem Pelenitsyn. Retain its single-threaded control flow,
  count array, flips and checksum. Replace the external vector storage API with
  contiguous unboxed `IOUArray Int Int` storage from GHC's boot `array` package.
  Reads/writes remain unchecked as upstream; small copy/reversal adapters replace
  the vector library operations. This avoids fetching packages and preserves
  indexed mutable storage. Initialization now zeros the scratch array once.
- MLF: `mlf/main.emlf` uses three `IntArray` values with the same incremental
  generator and an explicit element-copy and prefix-reversal loop. The runtime
  provides only general array accesses and arithmetic; all workload logic is MLF.
  As in binary-trees, integer equality explicitly forces the checksum/maximum
  before the next IO action, avoiding an unbounded chain of lazy accumulators.

These are comparable scalar algorithms, not identical optimized code: C uses
zero-based values; the other three use one-based values; Rust copies fixed-size
arrays; Haskell skips the zero-flip identity permutation; MLF checks every access
and supports arbitrary-precision elements. GHC's storage adapter may optimize
differently from vector, and MLF's IO sequencing/boxing costs are included.
The selected bounded inputs fit all baseline machine integer representations.

The [official specification](https://benchmarksgame-team.pages.debian.net/benchmarksgame/description/fannkuchredux.html)
requires all n! permutations, checksum and maximum flips. Correctness uses the
pinned n=7 output plus a separate Python oracle which reconstructs **each**
permutation by factoradic unranking, rather than sharing the incremental
generator. This oracle runs outside timing for every input, including the runtime
input. Whitespace is the only normalization. All baselines take n on argv; MLF
reads stdin, with parsing and output included in runtime timing.
