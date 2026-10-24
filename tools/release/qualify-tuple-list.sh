#!/usr/bin/env bash
# Supplemental full-native gate; deliberately separate from the nine-unit receipt.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
out="$PWD/.mlf-build/tuple-list-qualification"
mkdir -p "$out"
printf '{"complete":false}\n' > "$out/verification.json"
test "$#" = 0
test "${MLF_CI_SHARED_CANDIDATE:-0}" = 1
export MLF_COMPILER="$PWD/.mlf-build/bin/emlf"
export MLF_PACKAGE_MANAGER="$PWD/.mlf-build/bin/mlfpkg"
export MLF_BUILD_RUNNER="$PWD/.mlf-build/bin/mlf-build-runner"
sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"; else shasum -a 256 "$@"; fi; }
digest() { sha256 "$1" | awk '{print $1}'; }
git diff --quiet HEAD --
tools/release/shared-candidate.sh verify
. tools/release/native-environment.sh
. tools/release/qualification-jobs.sh
# A fresh invocation cannot inherit any previous successful executable/stdout.
run=$(mktemp -d "$out/run-XXXXXXXX")
cp .mlf-build/shared-candidate/manifest.json "$run/candidate-manifest.json"
printf '%s\n' 'mlfpkg --locked --compiler <authenticated-emlf> --runtime runtime/mlf_runtime.c --timeout 21600 --jobs <bounded> --cache-dir .mlf-build/cache --build-dir <run>/build build --target tuple-list' '<run>/build/bin/tuple-list' 'bash tools/release/test-tuple-list.sh <authenticated-emlf> <run>/runtime' > "$run/commands.log"
for tool in emlf mlfpkg mlf-build-runner compiler-tests; do
  sha256 ".mlf-build/bin/$tool"
done > "$run/tools.before.sha256"
git ls-files -z | xargs -0 sh -c 'if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"; else shasum -a 256 "$@"; fi' sh > "$run/source.before.sha256"
./mlfpkg --locked --compiler "$MLF_COMPILER" --runtime "$PWD/runtime/mlf_runtime.c" \
  --timeout 21600 --jobs "$MLF_TEST_BUILD_JOBS" --cache-dir "$PWD/.mlf-build/cache" \
  --build-dir "$run/build" build --target tuple-list > "$run/build.log" 2>&1
binary="$run/build/bin/tuple-list"
test -f "$binary" && test ! -L "$binary"
binary_hash=$(digest "$binary")
jq -e --arg compiler "$MLF_COMPILER" --arg ch "$(digest "$MLF_COMPILER")" \
  --arg manager "$MLF_PACKAGE_MANAGER" --arg mh "$(digest "$MLF_PACKAGE_MANAGER")" \
  --arg helper "$MLF_BUILD_RUNNER" --arg hh "$(digest "$MLF_BUILD_RUNNER")" --arg binary "$binary_hash" '
  .format == 1 and .complete == true and .implementation == "MLF" and
  .toolchain.compiler == {path:$compiler,sha256:$ch} and
  .toolchain.manager == {path:$manager,sha256:$mh} and
  (.scheduler | length) == 1 and (.scheduler_results | length) == 1 and
  .scheduler[0].helper == {path:$helper,sha256:$hh} and
  .scheduler_results[0].complete == true and .scheduler_results[0].exit_code == 0 and
  .scheduler[0].invocation_id == .scheduler_results[0].invocation_id and
  ([."pending-publications"[] | select(.name == "tuple-list") | .files.program] == [$binary])
' "$run/build/build-report.json" > "$run/build-verified.log"
"$binary" > "$run/harness.log" 2>&1
grep -Fx 'Tuple/list focused checks passed.' "$run/harness.log"
bash tools/release/test-tuple-list.sh "$MLF_COMPILER" "$run/runtime" > "$run/runtime.log" 2>&1
# Verify immutable inputs after both execution paths, not merely before builds.
for tool in emlf mlfpkg mlf-build-runner compiler-tests; do sha256 ".mlf-build/bin/$tool"; done > "$run/tools.after.sha256"
git ls-files -z | xargs -0 sh -c 'if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"; else shasum -a 256 "$@"; fi' sh > "$run/source.after.sha256"
cmp "$run/tools.before.sha256" "$run/tools.after.sha256"
cmp "$run/source.before.sha256" "$run/source.after.sha256"
test "$(digest "$binary")" = "$binary_hash"
git diff --quiet HEAD --
tools/release/shared-candidate.sh verify
# Retained bytes and a separate receipt never broaden the ordinary unit claim.
(cd "$run"; find . -type f ! -name artifacts.sha256 -print | LC_ALL=C sort | while IFS= read -r file; do sha256 "$file"; done) > "$run/artifacts.sha256"
jq -n --arg source "$(git rev-parse HEAD)" --arg run "$(basename "$run")" \
  --arg artifacts "$(digest "$run/artifacts.sha256")" --arg binary "$binary_hash" \
  --arg tree "$(git rev-parse HEAD^{tree})" --arg lock "$(digest mlf.lock)" \
  --arg candidate "$(digest "$run/candidate-manifest.json")" --arg inputs "$(digest "$run/source.before.sha256")" \
  '{format:1,complete:true,scope:"supplemental-tuple-list",source:$source,run:$run,
    source_tree:$tree,lock_sha256:$lock,candidate_manifest_sha256:$candidate,source_inventory_sha256:$inputs,
    targets:["tuple-list","tuple-list-native"],harness_sha256:$binary,artifacts_sha256:$artifacts,
    harness_exit_code:0,native_fixture_exit_code:0,inputs_unchanged:true}' > "$out/verification.json"
