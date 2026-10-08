# Native runtime dependencies

`khash.h` is the unmodified khash 0.2.8 header from Attractive Chaos's
[klib repository](https://github.com/attractivechaos/klib/blob/97a0fcb790b43b9e5da8994f4671021fec036f19/khash.h),
pinned to commit `97a0fcb790b43b9e5da8994f4671021fec036f19`. Its MIT license
and copyright notice are included in the header. The SHA-256 is pinned in
`benchmarks/manifest.json`. Both the native `IntTable` and the k-nucleotide C
baseline instantiate this same library; no workload algorithm lives in it.
Cabal packages the header beside `mlf_runtime.c` for installed compilers.

The reference interpreter uses Haskell `hashtables` 1.4.2. The benchmark's
Haskell k-nucleotide baseline uses that package and `hashable` 1.5.1.0.
Cabal resolves/builds them before measurement. The benchmark report records
Cabal source hashes, selected package units, transitive dependencies and
hashes of installed library archives/configurations. The runner never downloads
or builds dependencies during a sample.
