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
test "$(uname -s):$(uname -m)" = Darwin:arm64
version=$(cat VERSION)
commit=$(git rev-parse HEAD)
compiler_hash=$(shasum -a 256 "$build/bin/emlf" | awk '{print $1}')
manager_hash=$(shasum -a 256 "$build/bin/mlfpkg" | awk '{print $1}')
base="$build/compiler-tests/unit/verification.json"
groups='unit packages self-host parity backends port'
for group in $groups; do
  report="$build/compiler-tests/$group/verification.json"
  jq -e --arg group "$group" --arg hash "$compiler_hash" \
    '.complete == true and .implementation == "MLF" and .group == $group and .compiler_sha256 == $hash' "$report" >/dev/null
  cmp <(jq -S .sources "$base") <(jq -S .sources "$report")
  while IFS=$'\t' read -r suite expected; do
    test "$(shasum -a 256 "$build/compiler-tests/$group/$suite.log" | awk '{print $1}')" = "$expected"
  done < <(jq -r '(.suites // {}) | to_entries[] | [.key,.value.log_sha256] | @tsv' "$report")
  while IFS=$'\t' read -r abi expected; do
    test "$(shasum -a 256 "$build/compiler-tests/$group/$abi.log" | awk '{print $1}')" = "$expected"
  done < <(jq -r '(.matrices // {}) | to_entries[] | [.key,.value.log_sha256] | @tsv' "$report")
done
# Check every recorded source and detect newly added or removed inputs as well.
jq -r '.sources | to_entries[] | "\(.value)  \(.key)"' "$base" | shasum -a 256 -c >/dev/null
cmp <(jq -r '.sources | keys[]' "$base" | LC_ALL=C sort) <(
  { find scripts runtime bootstrap package examples benchmarks tests \
    -type d \( -name .mlf-build -o -name .git -o -name dist-newstyle -o -name __pycache__ \) -prune -o \
    -type f \( -name '*.hs' -o -name '*.emlf' -o -name '*.c' -o -name '*.h' -o -name '*.sh' -o -name '*.expected' -o -name '*.json' -o -name '*.gz' \) -print
    printf '%s\n' mlfpkg mlf-package.json; } | LC_ALL=C sort
)
jq -e --arg hash "$compiler_hash" '.fixed_point.reused_candidate_build == false and .fixed_point.next_compiler_sha256 == $hash' "$build/compiler-tests/self-host/verification.json" >/dev/null
jq -e '.parity.cases >= 7086 and .parity.runtime_executions >= 160' "$build/compiler-tests/parity/verification.json" >/dev/null
jq -e '(.matrices | keys) == ["compact-gc","standard"] and all(.matrices[]; .backends == 2 and .rows >= 546)' "$build/compiler-tests/backends/verification.json" >/dev/null
jq -e '(.matrices | keys) == ["compact-gc","standard"] and all(.matrices[]; .backends == 2 and .rows >= 26)' "$build/compiler-tests/port/verification.json" >/dev/null
mkdir -p "$output"
output=$(cd "$output" && pwd)
name="mlf-$version-macos-arm64"
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
for group in $groups; do
  mkdir -p "$bundle/evidence/$group"
  cp "$build/compiler-tests/$group/verification.json" "$bundle/evidence/$group/"
  while IFS= read -r log; do cp "$log" "$bundle/evidence/$group/"; done < <(find "$build/compiler-tests/$group" -maxdepth 1 -name '*.log' -type f)
done
jq -n --arg version "$version" --arg commit "$commit" --arg compiler "$compiler_hash" --arg manager "$manager_hash" \
  --arg minos "$(otool -l "$bundle/libexec/emlf" | awk '$1 == "minos" {print $2; exit}')" \
  '{schema_version:1,version:$version,commit:$commit,platform:"macos-arm64",minimum_macos:$minos,compiler_sha256:$compiler,manager_sha256:$manager,test_implementation:"MLF",test_groups:["unit","packages","self-host","parity","backends","port"],performance_gate:"not rerun for this preview"}' > "$bundle/release.json"
cat > "$bundle/README.md" <<'README'
# MLF native developer preview

This archive supports Apple Silicon on macOS 26 or later. The native executables
use Homebrew GMP at /opt/homebrew/opt/gmp. Install GMP with `brew install gmp`.
Native linking and package builds additionally need Clang, pkg-config, and BDWGC:
`brew install llvm pkg-config bdw-gc`.

From this directory: `./install.sh "$HOME/.local"`, then add `$HOME/.local/bin`
to PATH. The installer keeps versioned packages under PREFIX/lib/mlf and refuses
to replace unrelated commands. Run `emlf --version` and `mlfpkg --version`.

The bin directory also works directly on PATH, provided this archive's directory
structure stays intact. Do not copy the executables alone: native compilation
needs the bundled runtime sources. No GHC, Cabal, or Python is required.

release.json identifies the exact commit and executable hashes. CHECKSUMS covers
all bundled files. evidence/ contains all six native compiler test reports and
their primary logs. Historical absolute paths in those reports identify the
validation run; they are not runtime dependencies. The raw native executables
are unchanged from validation; installed shell launchers add --version support.

MLF sources use BSD-3-Clause; bundled khash and BDWGC notices are in licenses/.
GMP is a separately installed dependency under its own license.
README
# CHECKSUMS is explicitly excluded from the input list.
# shellcheck disable=SC2094
(cd "$bundle" && find . -type f ! -name CHECKSUMS | LC_ALL=C sort | while IFS= read -r file; do shasum -a 256 "$file"; done > CHECKSUMS)
tools/release/smoke.sh "$bundle" | tee "$output/smoke.log"
COPYFILE_DISABLE=1 tar -czf "$output/$name.tar.gz" -C "$output" "$name"
(cd "$output" && shasum -a 256 "$name.tar.gz" > SHA256SUMS)
printf 'Release package: %s/%s.tar.gz\n' "$output" "$name"
