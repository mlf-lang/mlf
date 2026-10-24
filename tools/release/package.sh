#!/usr/bin/env bash
# Assemble existing native test results; compilation and tests remain in MLF.
set -euo pipefail
root=${MLF_RELEASE_SOURCE_ROOT:-$(cd -- "$(dirname -- "$0")/../.." && pwd)}
root=$(cd -- "$root" && pwd)
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
parts='unit packages self-host parity backends port'
# Keep artifact directories distinct until every actual tool pair has been
# compared with the pair that passed native package-manager integration tests.
artifact_root=$build
test "$(find "$artifact_root" -mindepth 1 -maxdepth 1 | wc -l)" -eq 6
package_artifact="$artifact_root/native-$platform-packages"
for part in $parts; do
  artifact="$artifact_root/native-$platform-$part"
  test -f "$artifact/compiler-tests/$part/verification.json"
  for tool in emlf mlfpkg compiler-tests mlf-build-runner; do cmp "$package_artifact/bin/$tool" "$artifact/bin/$tool"; done
  cmp "$package_artifact/candidate-manifest.json" "$artifact/candidate-manifest.json"
  cmp "$package_artifact/campaign-runner/build-report.json" "$artifact/campaign-runner/build-report.json"
done
build="$artifact_root/assembled"
test ! -e "$build" || { printf '%s\n' 'Use new artifact staging directories.' >&2; exit 1; }
mkdir -p "$build/bin" "$build/compiler-tests"
cp "$package_artifact/bin/emlf" "$package_artifact/bin/mlfpkg" "$package_artifact/bin/compiler-tests" "$package_artifact/bin/mlf-build-runner" "$build/bin/"
chmod 755 "$build/bin/"*
for part in $parts; do
  cp -R "$artifact_root/native-$platform-$part/compiler-tests/$part" "$build/compiler-tests/"
done
compiler_hash=$(sha256 "$build/bin/emlf" | awk '{print $1}')
manager_hash=$(sha256 "$build/bin/mlfpkg" | awk '{print $1}')
runner_hash=$(sha256 "$build/bin/compiler-tests" | awk '{print $1}')
build_runner_hash=$(sha256 "$build/bin/mlf-build-runner" | awk '{print $1}')
test "$("$build/bin/mlf-build-runner" --protocol-version)" = 1
producer="$package_artifact/campaign-runner/build-report.json"
producer_hash=$(sha256 "$producer" | awk '{print $1}')
jq -se --arg compiler "$compiler_hash" --arg manager "$manager_hash" --arg runner "$runner_hash" \
  --arg helper "$build_runner_hash" --arg producer "$producer_hash" --arg source "$commit" '
  .[0] as $m | .[1] as $b |
  $m.format == 2 and $m.source == $source and
  $m.campaign_runner.report_sha256 == $producer and $m.campaign_runner.sha256 == $runner and
  $m.campaign_runner.compiler_sha256 == $compiler and $m.campaign_runner.manager_sha256 == $manager and
  $m.campaign_runner.build_runner_sha256 == $helper and
  $b.complete == true and $b.implementation == "MLF" and
  $b.toolchain.compiler == {path:($m.root + "/.mlf-build/bin/emlf"),sha256:$compiler} and
  $b.toolchain.manager == {path:($m.root + "/.mlf-build/bin/mlfpkg"),sha256:$manager} and
  [$b.builds[] | select(.kind == "executable mlf-compiler:compiler-tests") | .key] == [$m.campaign_runner.executable_key] and
  [$b."pending-publications"[] | select(.name == "compiler-tests" and .key == $m.campaign_runner.executable_key) | .files.program] == [$runner]
' "$package_artifact/candidate-manifest.json" "$producer" >/dev/null
base="$build/compiler-tests/unit/verification.json"
groups='unit packages self-host parity backends port'
for group in $groups; do
  report="$build/compiler-tests/$group/verification.json"
  jq -e --arg group "$group" --arg hash "$compiler_hash" --arg manager "$manager_hash" --arg runner "$runner_hash" --arg build_runner "$build_runner_hash" \
    '.complete == true and .implementation == "MLF" and .group == $group and .compiler_sha256 == $hash and .manager_sha256 == $manager and .runner_sha256 == $runner and .build_runner_sha256 == $build_runner' "$report" >/dev/null
  cmp <(jq -S .sources "$base") <(jq -S .sources "$report")
  while IFS=$'\t' read -r suite expected; do
    test "$(sha256 "$build/compiler-tests/$group/$suite.log" | awk '{print $1}')" = "$expected"
  done < <(jq -r '(.suites // {}) | to_entries[] | [.key,.value.log_sha256] | @tsv' "$report")
  case "$group" in
    unit) coverage_suites='harness core figure12 test-framework regex' ;;
    packages) coverage_suites='packages' ;;
    *) coverage_suites='' ;;
  esac
  if [ -n "$coverage_suites" ]; then
    inventory_hash=$(sha256 tests/golden/unit-inventory.json | awk '{print $1}')
    for suite in $coverage_suites; do
      expected=$(jq -er --arg suite "$suite" --arg inventory "$inventory_hash" \
        '.suites[$suite] | select(.coverage_inventory_sha256 == $inventory) | .coverage_report_sha256 | select(type == "string" and test("^[0-9a-f]{64}$"))' "$report")
      test "$(sha256 "$build/compiler-tests/$group/$suite.coverage.jsonl" | awk '{print $1}')" = "$expected"
    done
  fi
  case "$group" in
    backends|port)
      # Read the retained local report, never the producer workspace path.
      driver_report="$build/compiler-tests/$group/driver-build/build-report.json"
      driver_hash=$(sha256 "$driver_report" | awk '{print $1}')
      # Builder.manager identifies the executing campaign, not its nested CLI.
      jq -se --arg group "$group" --arg driver_hash "$driver_hash" '
    def digest: type == "string" and test("^[0-9a-f]{64}$");
    .[0] as $v | .[1] as $b |
    $v.group == $group and $v.driver_build.sha256 == $driver_hash and
    ($v.driver_build.sha256 | digest) and
    ($v.compiler_sha256 | digest) and ($v.runner_sha256 | digest) and
    all([$v.compiler,$v.runner,$b.cache_directory][]; type == "string" and startswith("/")) and
    $b.format == 1 and $b.complete == true and $b.implementation == "MLF" and
    $b.toolchain.compiler.path == $v.compiler and
    $b.toolchain.compiler.sha256 == $v.compiler_sha256 and
    $b.toolchain.manager.path == $v.runner and
    $b.toolchain.manager.sha256 == $v.runner_sha256 and
    ($b.builds | type == "array" and length > 0) and
    ($v.drivers | keys) == (if $group == "port" then ["LLVMDriver"] else ["LLVMDriver","RuntimeDriver"] end) and
    all($v.drivers | to_entries[];
      .key as $name | .value as $driver |
      $driver.frontend == "source" and
      ($driver.sha256 | digest) and ($driver.llvm_sha256 | digest) and
      ($driver.artifacts | keys) ==
        (if $name == "RuntimeDriver" then ["linked","llvm","object","runtime","trace"] else ["linked","llvm","object","runtime"] end) and
      all($driver.artifacts | to_entries[];
        .key as $stage | .value as $receipt |
        ($receipt | keys) == ["artifact_sha256","cached","directory","files","key","kind"] and
        ($receipt.key | digest) and ($receipt.artifact_sha256 | digest) and
        ($receipt.cached | type == "boolean") and
        $receipt.directory == ($b.cache_directory + "/" + $receipt.key) and
        $receipt.kind ==
          (if $stage == "llvm" then "source " + $name + " LLVM" elif $stage == "object" then "LLVM object" elif $stage == "linked" then "test driver native link" else "test driver C object" end) and
        any($b.builds[]; . == ($receipt | {kind,key,cached})) and
        ($receipt.files | keys) ==
          [if $stage == "llvm" then "program.ll" elif $stage == "object" then "program.o" elif $stage == "linked" then "program" else "object.o" end] and
        all($receipt.files[]; digest)) and
      $driver.artifacts.llvm.files["program.ll"] == $driver.llvm_sha256 and
      $driver.artifacts.linked.files.program == $driver.sha256)
      ' "$report" "$driver_report" >/dev/null
      ;;
  esac
  while IFS=$'\t' read -r abi expected; do
    test "$(sha256 "$build/compiler-tests/$group/$abi.log" | awk '{print $1}')" = "$expected"
  done < <(jq -r '(.matrices // {}) | to_entries[] | [.key,.value.log_sha256] | @tsv' "$report")
done
# Split-unit qualification binds all nine physical executables, not a made-up
# aggregate binary. Validate the retained build DAG and exact subreceipt union.
tools/release/verify-unit-evidence.sh "$build/compiler-tests/unit"
# Check every recorded source and detect newly added or removed inputs as well.
jq -r '.sources | to_entries[] | "\(.value)  \(.key)"' "$base" | sha256 -c - >/dev/null
cmp <(jq -r '.sources | keys[]' "$base" | LC_ALL=C sort) <(
  { find scripts runtime bootstrap package libraries examples benchmarks tests testing \
    -type d \( -name .mlf-build -o -name .git -o -name dist-newstyle -o -name __pycache__ \) -prune -o \
    -type f \( -path 'benchmarks/*' -o -name '*.hs' -o -name '*.emlf' -o -name '*.c' -o -name '*.h' -o -name '*.ps1' -o -name '*.sh' -o -name '*.expected' -o -name '*.json' -o -name '*.gz' \) -print
    printf '%s\n' mlfpkg mlf-package.json; } | LC_ALL=C sort
)
jq -e --arg hash "$compiler_hash" '.fixed_point.reused_candidate_build == false and .fixed_point.next_compiler_sha256 == $hash' "$build/compiler-tests/self-host/verification.json" >/dev/null
jq -e '.parity.cases == 7086 and .parity.source_compilations == 7075 and .parity.shared_source_cases == 11 and .parity.runtime_executions == 160' "$build/compiler-tests/parity/verification.json" >/dev/null
jq -e '(.matrices | keys) == ["compact-gc"] and all(.matrices[]; .backends == 2 and .rows == 583)' "$build/compiler-tests/backends/verification.json" >/dev/null
jq -e '.requested_profiles == ["compact-gc"] and (.matrices | keys) == ["compact-gc"] and all(.matrices[]; .backends == 1 and .backend_names == ["llvm"] and .rows == 25)' "$build/compiler-tests/port/verification.json" >/dev/null
mkdir -p "$output"
output=$(cd "$output" && pwd)
name="mlf-$version-$platform"
bundle="$output/$name"
mkdir -p "$bundle/bin" "$bundle/libexec" "$bundle/runtime" "$bundle/evidence" "$bundle/licenses"
cp "$build/bin/emlf" "$build/bin/mlfpkg" "$build/bin/mlf-build-runner" "$bundle/libexec/"
cp tools/release/command.sh "$bundle/bin/emlf"
cp tools/release/command.sh "$bundle/bin/mlfpkg"
cp tools/release/install.sh "$bundle/install.sh"
chmod 755 "$bundle/bin/"* "$bundle/libexec/"* "$bundle/install.sh"
cp runtime/*.c runtime/*.h "$bundle/runtime/"
cp VERSION LICENSE CHANGELOG.md "$bundle/"
printf '%s\n' "$commit" > "$bundle/COMMIT"
cp "$notice" "$bundle/licenses/BDWGC.txt"
mkdir -p "$bundle/evidence/campaign-runner"
cp "$producer" "$bundle/evidence/campaign-runner/build-report.json"
cp "$package_artifact/candidate-manifest.json" "$bundle/evidence/candidate-manifest.json"
cp runtime/khash.h "$bundle/licenses/khash.h"
for group in $groups; do
  mkdir -p "$bundle/evidence/$group"
  cp "$build/compiler-tests/$group/verification.json" "$bundle/evidence/$group/"
  case "$group" in
    backends|port)
      mkdir -p "$bundle/evidence/$group/driver-build"
      cp "$build/compiler-tests/$group/driver-build/build-report.json" "$bundle/evidence/$group/driver-build/"
      ;;
  esac
  while IFS= read -r log; do cp "$log" "$bundle/evidence/$group/"; done < <(find "$build/compiler-tests/$group" -maxdepth 1 -name '*.log' -type f)
done
for suite in harness core core-crates core-solver core-language core-modules figure12 test-framework regex; do
  cp "$build/compiler-tests/unit/$suite.coverage.jsonl" "$bundle/evidence/unit/"
done
for family in "$build/compiler-tests/unit/"*.families.jsonl; do cp "$family" "$bundle/evidence/unit/"; done
mkdir -p "$bundle/evidence/unit/builds"
while IFS= read -r report; do
  name=$(basename "$(dirname "$report")")
  cp "$report" "$bundle/evidence/unit/builds/$name.json"
done < <(find "$build/compiler-tests/unit" -path '*/suite-build-invocation-*/build-report.json' -type f)
cp tests/golden/unit-inventory.json "$bundle/evidence/unit/"
cp "$build/compiler-tests/packages/packages.coverage.jsonl" "$bundle/evidence/packages/"
cp tests/golden/unit-inventory.json "$bundle/evidence/packages/"
minimum_macos=""
build_glibc=""
if [ "$platform" = macos-arm64 ]; then
  minimum_macos=$(otool -l "$bundle/libexec/emlf" | awk '$1 == "minos" {print $2; exit}')
else
  build_glibc=$(getconf GNU_LIBC_VERSION)
fi
jq -n --arg version "$version" --arg commit "$commit" --arg compiler "$compiler_hash" --arg manager "$manager_hash" --arg runner "$runner_hash" --arg build_runner "$build_runner_hash" \
  --arg platform "$platform" --arg minos "$minimum_macos" --arg glibc "$build_glibc" \
  '{schema_version:1,version:$version,commit:$commit,platform:$platform,compiler_sha256:$compiler,manager_sha256:$manager,runner_sha256:$runner,build_runner_sha256:$build_runner,build_runner_protocol:1,test_implementation:"MLF",test_groups:["unit","packages","self-host","parity","backends","port"],port_profiles:["compact-gc"],performance_gate:"not rerun for this preview"} + (if $platform == "macos-arm64" then {minimum_macos:$minos} else {build_glibc:$glibc} end)' > "$bundle/release.json"
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
their primary logs, including the compact-GC native matrices. Historical
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
