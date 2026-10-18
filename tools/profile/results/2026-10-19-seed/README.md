# Published native seed comparison — 2026-10-19

Switching from the published v0.1.0 seed to v0.1.1 reduced median **complete
cold bootstrap time by 16.326418%** on this host: 362.97s to 303.71s. Each
bootstrap builds both `emlf` and `mlfpkg` from the identical clean v0.1.1 source
commit `c6033e67601c197cc91d19a0c3a3db4fbdaa1435`. These are stock release seeds,
not the separately measured PGO compiler.

| Measurement (seconds) | v0.1.0 samples | Median | v0.1.1 samples | Median |
| --- | --- | ---: | --- | ---: |
| Complete native build | 444.12, 361.15, 362.97 | 362.97 | 306.91, 303.71, 282.75 | 303.71 |
| MLF source through LLVM emission | 416.97, 336.36, 338.40 | 338.40 | 269.08, 266.36, 247.38 | 266.36 |
| Runtime C compilation | 0.95, 0.86, 0.84 | 0.86 | 0.90, 0.90, 0.84 | 0.90 |
| Clang LLVM compilation and linking | 19.75, 17.89, 17.85 | 17.89 | 31.27, 30.64, 28.80 | 30.64 |

The old total range is 361.15–444.12s (MAD 1.82s); the new range is
282.75–306.91s (MAD 3.20s). The first old sample is retained. Every new sample
is faster than every old sample. MLF time decreased by 21.288416%; Clang LLVM
compilation/linking increased by 71.268865%, partly offsetting the gain. Phase
medians need not sum to the median enclosing duration. The remaining duration
includes package orchestration and timing-wrapper overhead. Child commands are
serial; the enclosing package-manager row already includes them.

Three pairs ran in order old/new, new/old, old/new, without concurrent builds
or tests. Each sample had a new cache/output directory, fresh runtime objects,
MLF emission and Clang `-O2` compilation/linking. No build-cache hit was accepted.
The two published archives and their bundled files passed checksums; both seed
executable identities were verified. The new seed also passed a fresh native
example-package test on both backends before the measurements.

All three repetitions within each seed produced identical LLVM for each target.
Old and new seed LLVM differs, as expected from the changed code generator;
one representative of each target/variant is retained, with every sample's
hash. All six resulting compilers emitted identical standard LLVM for the n-body
validation input. All three new-seed builds reproduced the exact published
v0.1.1 compiler and package-manager binary hashes, so they reached the release's
binary fixed point. This is a build comparison, not a new runtime benchmark gate.

The host is Apple M1 Max with 32 GiB RAM, macOS 26.6.2, Clang 23.1.3, GMP 6.3.0
and Homebrew BDWGC 8.2.12. The compiler source, seeds, tools, libraries,
environment, host details, all raw `/usr/bin/time` output, full command arguments,
phase summaries and native package build reports are retained here. Timing
resolution is 0.01s. `context.json`, `summary.json`, `audit.json` and `SHA256SUMS`
bind the reports to those identities; `drivers/` preserves the measured scripts.

## Hosted CI scope

These measurements establish a local improvement, not a measured reduction of
the historical hour-long hosted bootstrap. The original Actions logs still do
not separate that run's MLF and Clang time. Both local seeds also have substantial
MLF memory demand: old peaks were 9.942, 8.824, 9.306 GiB; new peaks were 9.604,
9.119, 9.069 GiB. GitHub documents **7 GB RAM** for the standard `macos-26` runner
in its [runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
Memory pressure is therefore a plausible contributor to hosted slowness, not a
confirmed diagnosis of that historical run. Upgrading the seed does not establish
that the build fits the hosted runner's RAM. Keep the CI phase/RSS evidence.

## Reproduce

Download the main macOS ARM64 archive and SHA256SUMS from each immutable release,
verify the selected archive entry and its bundle CHECKSUMS, and unpack them.
Use a clean v0.1.1 source checkout and a fresh output directory:

```sh
export PATH="/absolute/path/to/llvm/bin:$PATH"
export MLF_GC_PREFIX="/absolute/path/to/bdw-gc"
tools/profile/seed-pairs.sh \
  /absolute/path/to/mlf-0.1.0-macos-arm64 \
  /absolute/path/to/mlf-0.1.1-macos-arm64 \
  /absolute/path/to/clean-v0.1.1-source \
  /absolute/path/to/fresh-seed-pairs
```

Use the current script and its sibling `tools/release` timing scripts from main;
the frozen target source remains v0.1.1. Builds and validation use native MLF
compilers and package managers; no GHC, Cabal or Python is invoked. The historical
source-to-LLVM PGO comparison has a different input/binary scope and boundary.
