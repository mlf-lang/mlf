#!/usr/bin/env bash
# Build the checkout once, then exercise its compiler, manager and C runtime.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
test "$#" -eq 0
build="$PWD/.mlf-build/pr-smoke"
mkdir -p "$build"
# Clear the success receipt before any command can fail on a rerun.
printf '{"complete":false}\n' > "$build/result.json"
seed_compiler=${MLF_COMPILER:?verified native seed compiler required}
seed_manager=${MLF_PACKAGE_MANAGER:?verified native seed manager required}
started=$SECONDS
"$seed_manager" --compiler "$seed_compiler" --runtime "$PWD/runtime/mlf_runtime.c" \
  --timeout 1800 --locked --build-dir "$build/candidate" build 2>&1 | tee "$build/build.log"
jq -e '.complete == true and .implementation == "MLF"' "$build/candidate/build-report.json" >/dev/null
build_seconds=$((SECONDS - started))
export MLF_COMPILER="$build/candidate/bin/emlf"
export MLF_PACKAGE_MANAGER="$build/candidate/bin/mlfpkg"
test -x "$MLF_COMPILER" && test -x "$MLF_PACKAGE_MANAGER"
# Direct invocation avoids building another root generation just to run tests.
# The suite still compiles its tests and backend drivers with the new compiler.
"$MLF_PACKAGE_MANAGER" compiler-test pr-smoke --compiler "$MLF_COMPILER" \
  --build-dir "$build/tests" --cache-dir "$build/candidate/cache" 2>&1 | tee "$build/tests.log"
jq -e '.complete == true and .group == "pr-smoke"' "$build/tests/verification.json" >/dev/null
# Changing expected stdout also changes the executable key. Require misses for
# the dependency and downstream crates, whose keys do not contain test stdout.
jq -e '
  [.builds[] | select(.kind == "crate message/0.1.0/library" or
    .kind == "crate greeting/0.1.0/library" or
    .kind == "crate local-packages-example/0.1.0/target-test-hello")] |
  length == 3 and all(.[]; .cached == false)
' "$build/tests/package-smoke/build/build-report.json" >/dev/null
jq -n --arg commit "$(git rev-parse HEAD)" --argjson build_seconds "$build_seconds" \
  --argjson total_seconds "$((SECONDS - started))" \
  --arg compiler_sha256 "$(shasum -a 256 "$MLF_COMPILER" | awk '{print $1}')" \
  --arg manager_sha256 "$(shasum -a 256 "$MLF_PACKAGE_MANAGER" | awk '{print $1}')" \
  '{complete:true,commit:$commit,build_seconds:$build_seconds,total_seconds:$total_seconds,
    compiler_sha256:$compiler_sha256,manager_sha256:$manager_sha256}' > "$build/result.json"
cat "$build/result.json"
