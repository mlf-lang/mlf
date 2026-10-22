# regex-redux

The upstream programs and n=1000 input/output are extracted from Benchmarks
Game revision `40296663ed350d5fe4a6ab5e367bab61cb77c219`. The
[manifest](../manifest.json) records original HTML Git blob IDs, immutable URLs,
extracted-source SHA-256 pins and patches that reconstruct every build source.
The shared [BSD license](../LICENSE.BenchmarksGame) applies to these programs.
The [official specification](https://benchmarksgame-team.pages.debian.net/benchmarksgame/description/regexredux.html)
requires real regular-expression operations, one pattern at a time.

- C: Jeremy Zerfas and Zoltan Herczeg's `regexredux-gcc-5`, using PCRE2 10.49
  with JIT. Remove the five OpenMP pragmas; preserve the original regex
  compilation, match loops, growing buffers, replacements, and output.
- Rust: Tom Kaitchuck and Andre Bogus's `regexredux-rust-5`. Replace the
  crossbeam scope and worker with sequential calls to the original counting
  and replacement functions; remove the unused crossbeam dependency. Use
  `regex` 1.12.2, with every transitive version and source checksum pinned in
  `rust/Cargo.lock`. Matching uses the library's byte regex API.
- Haskell: Jaro Reinders's `regexredux-ghc-3`, adapted from the same C program.
  Remove `forkIO`, `forkOn` and MVar coordination, executing each original
  counting/replacement loop sequentially. Keep PCRE2 10.49 calls and storable
  vector buffers. The FFI implements individual regex-library operations;
  the input, match iteration, copying, counting and formatting remain Haskell.
  `haskell/regex-redux.cabal` pins vector 0.13.2.0 and PCRE2 10.49;
  `haskell/cabal.project.freeze` pins the dependency plan for GHC 9.14.1 at the
  recorded Hackage index state.
- MLF: the workload calls the reusable `Bootstrap.Regex` library and performs
  every cleanup, counting and replacement pass in MLF. It has no PCRE2 or
  other foreign regex dependency. The manifest records its imported library
  sources for input-integrity checks.

All four implementations are sequential. The nine pattern counts inspect the
cleaned sequence; each of the five replacement passes consumes the previous
pass's output. The FASTA cleanup preserves the original `>.*\n|\n` expression
(Rust spells the equivalent byte pattern `>[^\n]*\n|\n`). Matching is case
sensitive and non-overlapping. The input length includes every input byte;
output includes all nine ordered pattern/count lines, a blank separator and
three lengths. These bytes are checked exactly, including the final newline.

The default input is FASTA n=1,000,000 (10,000,000 sequence bytes), matching the
suite's representative k-nucleotide size. The official n=5,000,000 performance
input is supported as the maximum; changing the input must not be presented as
a performance comparison at the official size. Correctness includes FASTA
n=1,7,31,1000 and the pinned upstream n=1000 input/output. The package oracle
uses independent scanners rather than the measured regex library.

## Reproducing baseline builds

From the repository root, with PCRE2 10.49 available through `pkg-config`:

```sh
pkg-config --exact-version=10.49 libpcre2-8
clang -O3 benchmarks/regex-redux/c/main.c \
  $(pkg-config --cflags --libs libpcre2-8) -o /tmp/regex-redux-c
cargo build --locked --release \
  --manifest-path benchmarks/regex-redux/rust/Cargo.toml \
  --target-dir /tmp/regex-redux-rust
(cd benchmarks/regex-redux/haskell && \
  cabal build --jobs=1 --builddir=/tmp/regex-redux-haskell exe:regex-redux)
```

Use `cabal list-bin --builddir=/tmp/regex-redux-haskell exe:regex-redux` from
that Haskell directory to locate its executable. Feed each executable
`benchmarks/regex-redux/input-1000.txt` and compare its complete stdout with
`benchmarks/regex-redux/expected-1000.txt`. Cargo and Cabal dependency setup
occurs outside source-compilation measurements. The native benchmark runner
compares C and MLF and records the actual PCRE2 version, flags and installed
library/header hashes; it rejects a version that differs from the manifest pin.
