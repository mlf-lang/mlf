#!/usr/bin/env bash
# Assemble existing native test results; compilation and tests remain in MLF.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$root"
build=${1:?usage: package.sh BUILD_DIRECTORY OUTPUT_DIRECTORY BDWGC_NOTICE}
output=${2:?output directory required}
notice=${3:?BDWGC copyright notice required}
build=$(cd "$build" && pwd)
test ! -e "$output" || { printf '%s\n' 'Use a new output directory.' >&2; exit 1; }
test -z "$(git status --porcelain)" || { printf '%s\n' 'Commit changes before packaging.' >&2; exit 1; }
tools/release/check.sh
case "$(uname -s):$(uname -m)" in
  Darwin:arm64) platform=macos-arm64 ;;
  Linux:x86_64) platform=linux-x64 ;;
  *) printf '%s\n' 'Supported POSIX release hosts: macOS ARM64 and Linux x64.' >&2; exit 1 ;;
esac
sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"; else shasum -a 256 "$@"; fi; }
version=$(cat VERSION)
commit=$(git rev-parse HEAD)
parts='unit packages self-host parity backends port-standard port-compact-gc'
# Keep artifact directories distinct until every actual tool pair has been
# compared with the pair that passed native package-manager integration tests.
artifact_root=$build
test "$(find "$artifact_root" -mindepth 1 -maxdepth 1 | wc -l)" -eq 7
package_artifact="$artifact_root/native-$platform-packages"
for part in $parts; do
  artifact="$artifact_root/native-$platform-$part"
  test -f "$artifact/compiler-tests/$part/verification.json"
  for tool in emlf mlfpkg; do cmp "$package_artifact/bin/$tool" "$artifact/bin/$tool"; done
done
build="$artifact_root/assembled"
test ! -e "$build" || { printf '%s\n' 'Use new artifact staging directories.' >&2; exit 1; }
mkdir -p "$build/bin" "$build/compiler-tests"
cp "$package_artifact/bin/emlf" "$package_artifact/bin/mlfpkg" "$build/bin/"
chmod 755 "$build/bin/"*
for part in $parts; do
  cp -R "$artifact_root/native-$platform-$part/compiler-tests/$part" "$build/compiler-tests/"
done
compiler_hash=$(sha256 "$build/bin/emlf" | awk '{print $1}')
manager_hash=$(sha256 "$build/bin/mlfpkg" | awk '{print $1}')
bash tools/release/merge-port-profiles.sh "$build" "$compiler_hash" "$manager_hash"
base="$build/compiler-tests/unit/verification.json"
groups='unit packages self-host parity backends port'
for group in $groups; do
  report="$build/compiler-tests/$group/verification.json"
  jq -e --arg group "$group" --arg hash "$compiler_hash" --arg manager "$manager_hash" \
    '.complete == true and .implementation == "MLF" and .group == $group and .compiler_sha256 == $hash and .manager_sha256 == $manager' "$report" >/dev/null
  cmp <(jq -S .sources "$base") <(jq -S .sources "$report")
  while IFS=$'\t' read -r suite expected; do
    test "$(sha256 "$build/compiler-tests/$group/$suite.log" | awk '{print $1}')" = "$expected"
  done < <(jq -r '(.suites // {}) | to_entries[] | [.key,.value.log_sha256] | @tsv' "$report")
  while IFS=$'\t' read -r abi expected; do
    test "$(sha256 "$build/compiler-tests/$group/$abi.log" | awk '{print $1}')" = "$expected"
  done < <(jq -r '(.matrices // {}) | to_entries[] | [.key,.value.log_sha256] | @tsv' "$report")
done
# Check every recorded source and detect newly added or removed inputs as well.
jq -r '.sources | to_entries[] | "\(.value)  \(.key)"' "$base" | sha256 -c >/dev/null
cmp <(jq -r '.sources | keys[]' "$base" | LC_ALL=C sort) <(
  { find src app test scripts runtime bootstrap package examples benchmarks tests \
    -type d \( -name .mlf-build -o -name .git -o -name dist-newstyle -o -name __pycache__ \) -prune -o \
    -type f \( -path 'benchmarks/*' -o -name '*.hs' -o -name '*.emlf' -o -name '*.c' -o -name '*.h' -o -name '*.py' -o -name '*.sh' -o -name '*.expected' -o -name '*.json' -o -name '*.gz' \) -print
    printf '%s\n' mlfpkg mlf-package.json; } | LC_ALL=C sort
)
jq -e --arg hash "$compiler_hash" '.fixed_point.reused_candidate_build == false and .fixed_point.next_compiler_sha256 == $hash' "$build/compiler-tests/self-host/verification.json" >/dev/null
jq -e '.parity.cases >= 7086 and .parity.runtime_executions >= 160' "$build/compiler-tests/parity/verification.json" >/dev/null
jq -e '(.matrices | keys) == ["compact-gc","standard"] and all(.matrices[]; .backends == 2 and .rows >= 546)' "$build/compiler-tests/backends/verification.json" >/dev/null
jq -e '.requested_profiles == ["standard","compact-gc"] and (.matrices | keys) == ["compact-gc","standard"] and all(.matrices[]; .backends == 2 and .rows == 26)' "$build/compiler-tests/port/verification.json" >/dev/null
mkdir -p "$output"
output=$(cd "$output" && pwd)
name="mlf-$version-$platform"
bundle="$output/$name"
mkdir -p "$bundle/bin" "$bundle/libexec" "$bundle/runtime" "$bundle/evidence" "$bundle/licenses"
cp "$build/bin/emlf" "$build/bin/mlfpkg" "$bundle/libexec/"
cp tools/release/command.sh "$bundle/bin/emlf"
cp tools/release/command.sh "$bundle/bin/mlfpkg"
cp tools/release/install.sh "$bundle/install.sh"
chmod 755 "$bundle/bin/"* "$bundle/libexec/"* "$bundle/install.sh"
cp runtime/*.c runtime/*.h "$bundle/runtime/"
cp VERSION LICENSE CHANGELOG.md "$bundle/"
printf '%s\n' "$commit" > "$bundle/COMMIT"
cp "$notice" "$bundle/licenses/BDWGC.txt"
cp runtime/khash.h "$bundle/licenses/khash.h"
for group in $groups port-standard port-compact-gc; do
  mkdir -p "$bundle/evidence/$group"
  cp "$build/compiler-tests/$group/verification.json" "$bundle/evidence/$group/"
  while IFS= read -r log; do cp "$log" "$bundle/evidence/$group/"; done < <(find "$build/compiler-tests/$group" -maxdepth 1 -name '*.log' -type f)
done
minimum_macos=""
build_glibc=""
if [ "$platform" = macos-arm64 ]; then
  minimum_macos=$(otool -l "$bundle/libexec/emlf" | awk '$1 == "minos" {print $2; exit}')
else
  build_glibc=$(getconf GNU_LIBC_VERSION)
fi
jq -n --arg version "$version" --arg commit "$commit" --arg compiler "$compiler_hash" --arg manager "$manager_hash" \
  --arg platform "$platform" --arg minos "$minimum_macos" --arg glibc "$build_glibc" \
  '{schema_version:1,version:$version,commit:$commit,platform:$platform,compiler_sha256:$compiler,manager_sha256:$manager,test_implementation:"MLF",test_groups:["unit","packages","self-host","parity","backends","port"],port_profiles:["standard","compact-gc"],performance_gate:"not rerun for this preview"} + (if $platform == "macos-arm64" then {minimum_macos:$minos} else {build_glibc:$glibc} end)' > "$bundle/release.json"
if [ "$platform" = macos-arm64 ]; then
cat > "$bundle/README.md" <<'README'
# MLF native developer preview

This archive supports Apple Silicon on macOS 26 or later. The native executables
use Homebrew GMP at /opt/homebrew/opt/gmp. Install GMP with `brew install gmp`.
Native linking and package builds additionally need Clang, pkg-config, and BDWGC:
`brew install llvm pkg-config bdw-gc`.
README
else
cat > "$bundle/README.md" <<'README'
# MLF native developer preview

This archive supports Linux x64 with glibc, built on Ubuntu 24.04. Install the
native runtimes with `sudo apt-get install libgmp10 libgc1`. Native linking and package
builds additionally need Clang, pkg-config, GMP headers, and BDWGC:
`sudo apt-get install clang pkg-config libgmp-dev libgc-dev`.
release.json records the build host's glibc version; musl systems are unsupported.
The launchers raise this command's stack limit for native compiler recursion.
README
fi
cat >> "$bundle/README.md" <<'README'

From this directory: `./install.sh "$HOME/.local"`, then add `$HOME/.local/bin`
to PATH. The installer keeps versioned packages under PREFIX/lib/mlf and refuses
to replace unrelated commands. Run `emlf --version` and `mlfpkg --version`.

The bin directory also works directly on PATH, provided this archive's directory
structure stays intact. Do not copy the executables alone: native compilation
needs the bundled runtime sources. No GHC, Cabal, or Python is required.

release.json identifies the exact commit and executable hashes. CHECKSUMS covers
all bundled files. evidence/ contains all six compiler qualification reports,
their primary logs, and both original native port profile reports. Historical
absolute paths in those reports identify the
validation run; they are not runtime dependencies. The raw native executables
are unchanged from validation; installed shell launchers add --version support.

MLF sources use BSD-3-Clause; bundled khash and BDWGC notices are in licenses/.
GMP is a separately installed dependency under its own license.
README
# CHECKSUMS is explicitly excluded from the input list.
# shellcheck disable=SC2094
(cd "$bundle" && find . -type f ! -name CHECKSUMS | LC_ALL=C sort | while IFS= read -r file; do sha256 "$file"; done > CHECKSUMS)
tools/release/smoke.sh "$bundle" | tee "$output/smoke.log"
COPYFILE_DISABLE=1 tar -czf "$output/$name.tar.gz" -C "$output" "$name"
(cd "$output" && sha256 "$name.tar.gz" > SHA256SUMS)
printf 'Release package: %s/%s.tar.gz\n' "$output" "$name"
