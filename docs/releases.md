# Versions and releases

`VERSION` is the toolchain's version. Native package manifests use the same
three-component version; the historical Haskell seed uses a trailing `.0` in
`mlf.cabal`. Release tags are `vMAJOR.MINOR.PATCH`. Published tags and assets
must never be replaced; make a new patch release to correct a package.

Before 1.0, patch releases preserve documented behavior and minor releases may
change language or package interfaces. Version 0.1.0 is a developer preview.
It has no stability or cross-platform performance guarantee.

## Install a release

The first binary package is for Apple Silicon and macOS 26+. Authenticate `gh`
with access to the private repository, then:

```sh
brew install gmp llvm pkg-config bdw-gc
mkdir mlf-download && cd mlf-download
gh release download v0.1.0 --repo mlf-lang/mlf \
  --pattern 'mlf-0.1.0-macos-arm64.tar.gz' --pattern SHA256SUMS
shasum -a 256 -c SHA256SUMS
tar -xzf mlf-0.1.0-macos-arm64.tar.gz
./mlf-0.1.0-macos-arm64/install.sh "$HOME/.local"
export PATH="$HOME/.local/bin:$PATH"
emlf --version
mlfpkg --version
emlf --type --expr '\x -> x'
```

The compiler and package manager do not need GHC, Cabal, or Python. GMP is a
dynamic dependency. Clang, GMP headers, and pkg-config are needed for native
linking; compiler-profile package builds also need BDWGC. The installer keeps
versioned directories, validates file checksums, and preserves unrelated commands.
Installed launchers provide `--version`; the validated native binaries remain
unchanged. Keep the whole package when using its `bin` directory directly.

## Prepare the next release

1. Update `VERSION`, the four toolchain manifests, `mlf.cabal`, and `CHANGELOG.md`.
2. Run `./mlfpkg lock`, review the lock changes, and commit the release candidate.
3. Create an annotated version tag and push it. Tags are never moved.
4. Run the **Native release** workflow on `main` with that tag. It runs all six
   native groups independently, checks their compiler hashes and source snapshots,
   verifies a fresh self-host fixed point, tests relocation and installation,
   then uploads a new developer-preview release with SHA-256 checksums.

CI on `main` and pull requests checks release metadata, builds the native
compiler and manager from the pinned seed in `.github/seed.env`, exercises
interpreter and LLVM with local packages, and checks a fresh self-host build.
The release workflow is manual because the full matrices are much more expensive.
No workflow installs GHC or invokes Python. Seed downloads check both published
archive checksums and the independently pinned native executable hashes.

For local packaging, after all six groups pass on the same candidate:

```sh
tools/release/package.sh .mlf-build .mlf-build/release \
  /path/to/bdwgc/README.QUICK
```

This script refuses a dirty checkout, stale or missing sources, mismatched
compiler hashes, incomplete groups, altered primary logs, and a reused self-host
build. It packages the tested executables, runtime sources, third-party notices,
release metadata, and native evidence. `tools/release/smoke.sh` tests a relocated
install in a path with spaces, modules, interpreter/LLVM output equality, native
package tests, safe reinstall, and preservation of unrelated commands.

The first seed archive is assembled locally from the retained six-group native
validation. Its executables match `docs/native-tests-validation.json`; subsequent
releases use that published native seed. This establishes the initial bootstrap
anchor without introducing a GHC or Python dependency in CI.

Historical `scripts/release.py` remains an optional Haskell-seed release gate.
It also reruns C/Rust/Haskell comparisons and enforces compilation <=5x C and
runtime <=2x C. The native developer-preview workflow above validates compiler
correctness and self-hosting; it does not claim to rerun that performance gate.
Existing benchmark reports retain their original source, binary, and host scope.
