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
| n-body | `nbody-gcc-1`, `nbody-rust-1`, GHC #1–2 | Implemented with C/Rust/GHC #1 unchanged. MLF now has `Double`, arithmetic, square root, fixed decimal formatting and mutable `DoubleArray`; all five bodies use contiguous numeric storage. Haskell's foreign-memory API only stores data; its integration algorithm remains Haskell. See [provenance](n-body/PROVENANCE.md). |
| spectral-norm | `spectralnorm-gcc-1`, Rust #1–3, `spectralnorm-ghc-2` | Implemented with C #1 and GHC #2 unchanged, Rust #3 dispatched sequentially with an odd-element tail, and MLF DoubleArray loops. The independent oracle materializes a dense matrix and uses accurate sums. See [provenance](spectral-norm/PROVENANCE.md). |
| mandelbrot | C #1–2, `mandelbrot-rust-1`, GHC #1–2 | Implemented with scalar C #2, sequential Rust #1's eight scalar lanes and sequential GHC #2. Partial rows and zero padding are supported. MLF interleaves two scalar orbits in recursive Double arguments, with ByteArray rows and ordinary arithmetic for bit packing. Exact PBM bytes are independently checked. See [provenance](mandelbrot/PROVENANCE.md). |
| fannkuch-redux | `fannkuchredux-gcc-1`, `fannkuchredux-rust-2`, GHC #1–6 | Implemented with C #1, Rust #2's full range dispatched to one worker, and GHC #4 using an unboxed array storage adapter. MLF has indexed mutable `IntArray`, multiplication and quotient/remainder. All four use incremental array permutations and full prefix flips, rather than a list representation. See [provenance](fannkuch-redux/PROVENANCE.md). |
| pidigits | `pidigits-gcc-1`, `pidigits-rust-1`, GHC #1–6 | Implemented with C #1, Rust #1 and GHC #6's matching three-integer sequential spigot recurrence. MLF's multiplication and quotient use GMP for large values; both extract(3) and extract(4) are performed. FFI only implements individual arithmetic operations. See [provenance](pidigits/PROVENANCE.md). |
| fasta | `fasta-gcc-1`, Rust #1, #3–4, `fasta-ghc-1` | Implemented with C #1, Rust #4 and GHC #1 unchanged. MLF uses cumulative Double probabilities, the required fresh LCG update for every base, indexed ByteArray storage and buffered raw output. Rust #1/#3 scale probabilities and were not selected. See [provenance](fasta/PROVENANCE.md). |
| reverse-complement | `revcomp-rust-1` plus the description | Deferred. Mutable byte indexing and raw output now exist; bulk byte input and practical record parsing remain absent. The inspected Rust version uses Rayon and explicit SIMD, so comparable sequential baselines still need investigation. |

Capability evidence is the exhaustive primitive set in `src/MLF/Primitive.hs`,
the parser/ADT examples, and the interpreter/native runtime implementations.
`Int` is unbounded; `Double` is IEEE binary64; `IntArray`, `DoubleArray` and
`ByteArray` provide indexed, bounds-checked mutation through IO. Strings can
be copied into fresh UTF-8 byte arrays; `putBytes` outputs exact checked slices.
We have not replaced missing operations with
unary arithmetic, list indexing in numeric kernels, a foreign helper doing
the workload, or hardcoded answers. All seven implemented workloads enter
summary ratios. Deferred candidates
are not treated as zero-time or skipped rows.

Next candidates include reverse-complement and k-nucleotide, after byte input,
record parsing and suitable indexed lookup structures are available. Sequential
source selection and independent oracles remain prerequisites for each addition.
The new workloads exercise integer-to-Double conversion in native regions,
byte loads/stores, raw output and partial byte packing. Current measurements and the per-workload
compile/runtime limits are recorded in [RESULTS.md](RESULTS.md); workload
completion alone is not evidence of performance parity on other inputs or
machines.
