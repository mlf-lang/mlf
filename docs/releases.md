# Versions and releases

`VERSION` is the toolchain's version. Native package manifests use the same
three-component version. Release tags are `vMAJOR.MINOR.PATCH`. Published tags and assets
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

1. Update `VERSION`, the four toolchain manifests and `CHANGELOG.md`.
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
No workflow installs GHC or invokes Python. Seed downloads check the selected published archive checksum and both
independently pinned native executable hashes. CI now pins v0.1.1. Release jobs
read seed pins and verification/timing tools from the workflow's immutable
commit, so an older target tag cannot silently select its old seed. The checksum
file can also cover supplementary validation archives that are not downloaded
for bootstrapping. The [three-pair seed comparison](../tools/profile/results/2026-10-19-seed/README.md)
measured a 16.326% lower local median full bootstrap time; hosted timing remains
a separate measurement.

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

Current compiler builds resolve each crate together and infer declaration SCCs,
releasing their inference graphs between queries. Checked metadata, fragments,
dependency boundaries and the final linked xMLF remain mandatory. See
[crate compilation](crate-compilation.md) for the current contract and
[the migration ledger](crate-migration.md) for validation and performance evidence.

The earlier per-module compiler was measured in three local cold build pairs: sampled
aggregate RSS fell from a 9.99 GB median to 3.27 GB (maximum 3.28 GB), while
median full build time rose from 332.38s to 460.87s. The
[memory report](../tools/profile/results/2026-10-19-bootstrap-memory/README.md)
records the tradeoff and the limits of extrapolating to a hosted runner.
A subsequent cold build on the actual 7 GiB hosted runner passed in 995.59s,
at 2.73 GB maximum process RSS, reproducing both locally tested binaries exactly.

The timing helper defaults `MLF_BOOTSTRAP_MAX_RSS_BYTES` to `5500000000` and
fails before publishing candidate paths when a measured command exceeds that
budget. This is a per-command RSS high-water guard, not a hard heap cap or an
aggregate process-tree limit. `0` disables this resource gate for diagnostics.
Explicit caller settings are respected. Crate builds and older separate-module
seed builds keep the runtime's
`GC_FREE_SPACE_DIVISOR=1` policy; immutable older target tags that still request
source linking default to `4`, collecting more frequently. Successful bootstrap
steps pass that policy to subsequent CI steps. No maximum heap size is imposed.
The diagnostic seed comparison driver explicitly keeps divisor `1` and disables
the resource gate by default so historical comparisons retain their conditions
and all over-budget samples.

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

The historical Haskell/Python release and benchmark launchers have been
removed. Use the [native benchmark runner](../tools/bench/README.md) for current
C/MLF performance comparisons. The native developer-preview workflow above
validates compiler correctness and self-hosting; performance remains a separate
gate. Pinned C/Rust/Haskell baseline sources remain available.
Existing benchmark reports retain their original source, binary, and host scope.
