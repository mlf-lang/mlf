# fasta

All three baselines are copied unchanged from Benchmarks Game revision
`40296663ed350d5fe4a6ab5e367bab61cb77c219`. The [manifest](../manifest.json)
records Git blob IDs, source URLs and SHA256 hashes. The shared
[BSD license](../LICENSE.BenchmarksGame) applies.

- C: Paul Hsieh's `fasta-gcc-1`, with cumulative Double probabilities,
  binary search and line-oriented stdio output.
- Rust: leonardo's `fasta-rust-4`, a sequential Double implementation using
  linear probability search and `BufWriter`. Unlike Rust #1 and #3, it does
  not scale the probabilities into integers. Its full output-sequence vectors
  are retained, so its peak memory includes them.
- Haskell: Roman Kashitsyn's `fasta-ghc-1`, with the same LCG and Double
  comparisons, explicit cumulative thresholds and ByteString line output.
  `-XBangPatterns -XOverloadedStrings` supply the syntax extensions required
  by the original source. ByteString ships with GHC; nothing is downloaded.
- MLF: `mlf/main.emlf` copies ALU bytes and constructs cumulative probabilities
  from the original distributions, then uses binary search. One `IntArray`
  seed continues across both random records. A reusable `ByteArray` holds up
  to 1024 lines, and `putBytes` writes each completed chunk.
  Loop counters are explicitly demanded by comparisons before their next
  iteration, allowing the compiler's ordinary strictness analysis to enter
  native loops without forcing unrelated lazy values.

The [official specification](https://benchmarksgame-team.pages.debian.net/benchmarksgame/description/fasta.html)
requires the naive LCG with a new update for each random nucleotide. All four
perform every update and lookup, preserve the seed between records, and print
the same three records of lengths 2n, 3n and 5n. No random sequence is cached,
probabilities are not scaled, and the runtime contains no FASTA helper.
Line buffering, linear versus binary selection, and retained output storage
are documented implementation differences; all output and flushing time counts.

Correctness is exact bytes, including headers, 60-column lines and trailing
newlines. The independent oracle constructs thresholds from exact decimal
fractions and compares integer cross-products instead of sharing floating
lookup code. It matches the pinned n=1000 fixture and every runtime input.
The driver checks zero length, single bases, line boundaries and output-buffer
boundaries. Both-backend tests include zero, one and the n=1000 fixture.
The oracle runs outside timing.
