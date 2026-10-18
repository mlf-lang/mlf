# Versions and releases

`VERSION` is the toolchain's version. Native package manifests use the same
three-component version; the historical Haskell seed uses a trailing `.0` in
`mlf.cabal`. Release tags are `vMAJOR.MINOR.PATCH`. Published tags and assets
must never be replaced; make a new patch release to correct a package.

Before 1.0, patch releases preserve documented behavior and minor releases may
change language or package interfaces. Version 0.1.1 is a developer preview.
It has no stability or cross-platform performance guarantee.

## Install a release

The first binary package is for Apple Silicon and macOS 26+. Authenticate `gh`
with access to the private repository, then:

```sh
brew install gmp llvm pkg-config bdw-gc
mkdir mlf-download && cd mlf-download
gh release download v0.1.1 --repo mlf-lang/mlf \
  --pattern 'mlf-0.1.1-macos-arm64.tar.gz' --pattern SHA256SUMS
shasum -a 256 -c SHA256SUMS
tar -xzf mlf-0.1.1-macos-arm64.tar.gz
./mlf-0.1.1-macos-arm64/install.sh "$HOME/.local"
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

CI on `main` and pull requests checks release metadata, downloads the pinned
native seed in `.github/seed.env`, and builds checkout example packages on both
interpreter and LLVM. This fast check verifies installation and local package
integration; it does not rebuild or validate modified compiler implementations.
Dispatch **CI** with `self_host` enabled for a fresh compiler build and fixed
point, or **Native release** for all six compiler groups. These full checks are
manual because compilation on hosted M1 runners can exceed 30 minutes per stage.
When the code generator changes, an intermediate native generation is built
from the pinned seed before building the candidate tested by all six groups.
This lets the candidate and its fresh self-build use the same updated generator.
Bootstrap builds explicitly allow six hours; individual fixture limits remain
unchanged. Native release publication still requires every group to pass.
No workflow installs GHC or invokes Python. Seed downloads check both published
archive checksums and the independently pinned native executable hashes.

To diagnose bootstrap time without running tests or another compiler generation,
dispatch **Native bootstrap timing** (`gh workflow run bootstrap.yml --ref main`).
It runs one cold seed build on `macos-26`, with the usual compiler and Clang flags.
Each MLF and Clang invocation retains its full arguments, wall/user/system time,
peak RSS, page-fault counts, exit status, and raw `/usr/bin/time` output. The
artifact also includes the native `build-report.json`, command logs, cache
manifests, source/tool hashes, host details, and a summary. LLVM compilation and
linking remain one Clang command. The enclosing package-manager measurement
includes the child commands and must not be added to their totals. Ordinary CI
self-host and native-release bootstrap steps retain the same evidence, including
on failure; started commands without a result record were interrupted.

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
