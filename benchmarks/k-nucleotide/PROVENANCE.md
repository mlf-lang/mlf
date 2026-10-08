# k-nucleotide

Sources are extracted from Benchmarks Game revision
`40296663ed350d5fe4a6ab5e367bab61cb77c219`. Upstream files, exact patches,
HTML Git blob IDs, URLs and SHA-256 hashes are in the [manifest](../manifest.json).
The shared [BSD license](../LICENSE.BenchmarksGame) applies to baseline sources.
The [official description](https://benchmarksgame-team.pages.debian.net/benchmarksgame/description/knucleotide.html)
requires library hash tables and complete counts for all requested lengths.

- C: Jeremy Zerfas's `knucleotide-gcc-1`, using the pinned khash library also
  shipped with the MLF runtime. Remove OpenMP dispatch, retain every original
  rolling-key counting pass and its hash function. Bound initial key reads
  for inputs shorter than a query and initialize empty output buffers. Use
  `100.0` in frequency calculation so the multiplication rounds in binary64
  rather than binary32 before printing three decimals.
- Rust: Renat Galimov's `knucleotide-rust-1`. Replace thread creation/joining
  with sequential calls to the unchanged standard `HashMap<Vec<u8>,usize>`
  counting function. Add the required lexical tie-break when sorting equal
  frequencies. Every full table is retained as in the original. No external
  crates, custom hash table or native workload helper is used.
- Haskell: cahu ette's `knucleotide-ghc-2`. Remove parallel strategies and use
  one worker with stride one; preserve packing, `hashtables` counting,
  frequency calculation and ordering. Dependencies `hashtables` 1.4.2 and
  `hashable` 1.5.1.0 are built by Cabal before measurement. Exact library units,
  source hashes and installed archive hashes are included in each report.
- MLF: reads records line by line and extracts THREE into geometrically
  growing byte storage, decoding each input base once. For k=1,2,3,4,6,12,18
  it maintains a rolling base-4 key for every overlapping window, masks off
  the outgoing digit with `andInt`, reads its count and writes the increment to a
  fresh `IntTable`. The table starts at the library's default small capacity.
  The compiler fuses adjacent count reads and updates into one runtime call;
  the old count remains an immutable snapshot. The runtime uses khash lookup
  for existing keys and insertion for misses. All parsing, key formation,
  loops and formatting are MLF. Lengths 1 and 2 are sorted by descending
  counts then ascending keys; the other tables are queried only after the
  complete counting pass. A separate untimed instrumentation test verifies
  writes and distinct insertions for each of the seven tables.

The representations differ: C and MLF have rolling integer keys, Haskell packs
integer keys from each window, and Rust stores byte-vector keys. Their memory
and lookup costs are part of this practical implementation comparison.
All are sequential; no count is replaced by a direct pattern search.

`--size` is FASTA n; every language receives identical bytes on stdin. The
n=1000 input and output are pinned upstream fixtures. Generation and the
independent Python byte-slice/Counter oracle run outside timing. Outputs are
checked for exact keys, order, separators, three decimal places and all five
query counts. Frequencies use exact rational counts in the oracle. Only at an
exact decimal halfway value are both adjacent rounded numbers accepted:
standard C and Haskell formatting can choose different neighbours after
binary64 evaluation (for example 30.1375). All other frequencies have one
accepted value; this is not a blanket numeric tolerance. Small checks include absent long
queries, ties and overlapping windows; the exact measured input is checked
before timing and after every runtime sample.
