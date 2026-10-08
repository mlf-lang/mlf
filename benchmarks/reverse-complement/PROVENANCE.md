# reverse-complement

Sources are extracted from Benchmarks Game revision
`40296663ed350d5fe4a6ab5e367bab61cb77c219`. Exact upstream files, adaptation
patches, HTML Git blob IDs, URLs and SHA-256 hashes are retained in the
[manifest](../manifest.json). The shared [BSD license](../LICENSE.BenchmarksGame)
applies to the baseline sources. The workload is specified in the
[official description](https://benchmarksgame-team.pages.debian.net/benchmarksgame/description/revcomp.html).

- C: Bob W's `revcomp-gcc-4`. Retains the scalar complement table, reverse
  buffer growth and output formatting. The patch replaces subtraction of
  unrelated allocation pointers and out-of-allocation pointer arithmetic with
  offsets computed before `realloc`, and frees the two buffers at exit.
- Rust: `revcomp-rust-2` by the Rust Project Developers, Cristi Cobzarenco,
  TeXitoi and Matt Brubeck. Only Rayon dispatch is replaced with sequential
  calls. The complement table, growable input, opposing chunks and scalar
  reverse/swap loops remain. There are no external crates or SIMD intrinsics.
- Haskell: Louis Wasserman's `revcomp-ghc-4`, with GHC fixes by Artem Pelenitsyn.
  The original fixed-size reader handled only one header per 82-byte block:
  multiple short records corrupted headers. The adapter uses buffered
  ByteString lines, then the original geometric `Buf` growth and in-place
  reverse/complement loop. It carries relocated buffers forward, frees the
  final buffer, and completes lowercase W/S/N mappings. Foreign memory only
  stores bytes; reversal remains Haskell code.
- MLF: grows a `ByteArray` record from 1024 bytes as each raw line arrives,
  using a source-language copy loop. A lookup table handles all upper/lower
  IUPAC codes. It reverses every sequence into reusable 60-column output
  chunks, filling one output row at a time. Record state is carried directly
  in recursive arguments. The compiler recognizes eligible byte-copy loops
  and uses a guarded LLVM memory intrinsic; overlapping or invalid ranges
  retain scalar semantics. Header text and record order are preserved. No size query, native
  reverse-complement helper, explicit vector code or parallel worker is used.

Every language receives identical FASTA bytes on stdin; `--size` means the
FASTA generator's n, not input byte count. Generation and validation happen
outside timing; reading, growth, transformation and writing are included.
The generated n=1000 input must match the pinned upstream input byte for byte.
The independent oracle uses Python byte translation and slicing, and checks
exact headers, case, bases, wrapping and final newlines against the pinned
output. Both MLF backends additionally check empty records, every ambiguity
code, mixed case, long records and a final unterminated sequence.
