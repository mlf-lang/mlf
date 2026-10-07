# Workload selection

Sources inspected at Benchmarks Game revision
`40296663ed350d5fe4a6ab5e367bab61cb77c219`. Names below refer to
`public/program/<name>.html` in the
[pinned repository](https://salsa.debian.org/benchmarksgame-team/benchmarksgame/-/tree/40296663ed350d5fe4a6ab5e367bab61cb77c219/public/program).
The corresponding official `public/description/*.html` specifies the work.
Inspection covered source algorithms and dependencies, not leaderboard ranks.

| Candidate | Representative sources inspected | Decision / missing MLF features |
| --- | --- | --- |
| binary-trees | `binarytrees-gcc-1`, Rust #1–5, GHC #1, #2, #4 (parallel imports in #3–7) | Implemented. Recursion, ADTs, integer addition/comparison and IO are enough. Necessary baseline adaptations and MLF strictness are documented in [PROVENANCE.md](binary-trees/PROVENANCE.md). |
| n-body | `nbody-gcc-1`, `nbody-rust-1`, `nbody-ghc-1` | Deferred. Double precision arithmetic, multiplication/division and square root are absent. C/Rust update a five-body array; Haskell uses explicit foreign-memory storage but implements the algorithm in Haskell. Mutable storage would help preserve the representation; fixed-size ADTs could also represent the five bodies once floating point exists. |
| spectral-norm | `spectralnorm-gcc-1`, `spectralnorm-rust-1`, `spectralnorm-ghc-2` | Deferred. Requires Double arithmetic, division/sqrt, indexed numeric arrays and repeated matrix-vector operations. Rust #1 also spawns threads and works on pairs of elements, so it would not be selected unchanged. Replacing all array accesses with linked-list traversal would change the cost model substantially. |
| mandelbrot | `mandelbrot-gcc-1`, `mandelbrot-rust-1`, `mandelbrot-ghc-1` | Deferred. No floating point, byte/bit operations, binary output or indexed buffers. C #1 uses pthreads and explicit vector types; Rust #1 uses threads and vector-shaped computations. Future selection must find sequential scalar versions; Haskell #1 uses complex Double, vectors and ByteString. |
| fannkuch-redux | `fannkuchredux-gcc-1`, `fannkuchredux-rust-2`, `fannkuchredux-ghc-1` | Deferred for this comparable corpus. C and Rust use indexed mutable permutation/count arrays; Rust also partitions work across threads and uses division/modulo. MLF lacks arrays/mutation and these integer primitives. Haskell #1 shows a list-based version is possible, but it changes allocation/data-structure strategy and contains hand-unrolled small flips. A pure MLF list rendition is expressible, but does not establish a comparable array benchmark. |
| pidigits | `pidigits-gcc-1`, `pidigits-rust-1`, `pidigits-ghc-1` | Promising next addition. MLF already has arbitrary-precision integers, but lacks multiply and quotient/remainder needed by the spigot algorithm. Existing C/Rust use GMP arithmetic; Haskell uses Integer arithmetic. Select matching spigot algorithms and avoid an FFI implementation of the whole workload. |
| fasta | `fasta-gcc-1`, `fasta-rust-1`, `fasta-ghc-1` | Deferred. LCG multiplication/modulo, probability arithmetic, character/byte indexing and buffered output are absent. |
| reverse-complement | `revcomp-rust-1` plus the description | Deferred. MLF strings support concat/equality but no indexing, slicing or byte buffers. The inspected Rust version also uses Rayon and explicit SIMD. |

Capability evidence is the exhaustive primitive set in `src/MLF/Primitive.hs`,
the parser/ADT examples, and the interpreter/native runtime implementations.
`Int` is unbounded, strings are opaque UTF-8 values, and the current language
has no float or array type. We have not replaced missing operations with
unary arithmetic, list indexing in numeric kernels, a foreign helper doing
the workload, or hardcoded answers. Only binary-trees is included in summary
ratios; unsupported candidates are not treated as zero-time or skipped rows.

Suggested order: add integer multiplication and quotient/remainder, then
pidigits; add Double arithmetic/sqrt and n-body; add mutable numeric arrays
and then spectral-norm or fannkuch-redux. A second workload should follow the
same four-language correctness-first path before entering the manifest.
