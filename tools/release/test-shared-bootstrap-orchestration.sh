#!/usr/bin/env bash
# Control-only regression. These mock tools do not qualify a compiler or runtime.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/mlf-shared-bootstrap.XXXXXXXX")
trap 'rm -rf "$work"' EXIT
project="$work/project with spaces"
frozen="$project/bootstrap/shared-haskell-v1-bridge"
mkdir -p "$project/scripts" "$project/libraries/example" "$project/runtime" "$frozen" "$work/archive/scripts"
cp "$root/scripts/bootstrap-shared.sh" "$project/scripts/"
printf 'shared source fixture\n' > "$project/libraries/example/Main.hs"
printf '{}\n' > "$project/libraries/example/mlf-package.json"
printf '{}\n' > "$project/mlf-package.json"
printf 'runtime fixture\n' > "$project/runtime/mlf_runtime.c"
printf 'helper fixture\n' > "$project/runtime/mlf_build_runner.c"
printf '0.3.0\n' > "$project/VERSION"
cat > "$project/shared-sources.json" <<'MANIFEST'
{"format":1,"source_syntax":"shared-haskell-v1","frontend_semantics":"test/2","builtin_interface":"test/3","primitive_abi":"test/95","modules":[{"module":"Main","path":"libraries/example/Main.hs"}]}
MANIFEST
cat > "$work/seed" <<'SEED'
#!/bin/sh
# MLF bootstrap control fixture (not a native tool).
# Any attempt to compile final shared sources with the released seed is a bug.
if [ "${TEST_SEED_GHC:-0}" = 1 ] && [ "$1" = --implementation-identity ]; then
  printf 'MLF/shared-haskell-v1 GHC\n'
  exit 0
fi
exit 89
SEED
cat > "$work/archive/compiler" <<'COMPILER'
#!/bin/sh
set -eu
case "$1" in
 --implementation-identity) printf 'MLF/shared-haskell-v1 native-MLF\n' ;;
 --run)
   case "$*" in *asyncResolveCompletion*) printf '41\n' ;; *) printf '1\n' ;; esac
   ;;
 *) exit 88 ;;
esac
COMPILER
cat > "$work/archive/manager" <<'MANAGER'
#!/bin/sh
set -eu
if [ "${1:-}" = --implementation-identity ]; then
  printf 'MLF/shared-haskell-v1 native-MLF\n'
  exit 0
fi
manifest= build= compiler= targets=
while [ "$#" -gt 0 ]; do
 case "$1" in
  --manifest) manifest=$2; shift 2 ;;
  --build-dir) build=$2; shift 2 ;;
  --compiler) compiler=$2; shift 2 ;;
  --target) targets="$targets $2"; shift 2 ;;
  *) shift ;;
 esac
done
test "$manifest" = "$TEST_PROJECT/mlf-package.json"
test "$compiler" = "$MLF_SHARED_BOOTSTRAP_DIR/bridge/stage2"
test "$targets" = ' emlf mlfpkg'
test -f "$TEST_PROJECT/libraries/example/Main.hs"
printf '%s\n' "$manifest|$compiler|$targets" >> "$TEST_CALLS"
if [ "${TEST_FAIL:-0}" = 1 ]; then exit 81; fi
mkdir -p "$build/bin"
cp "$compiler" "$build/bin/emlf"
cp "$0" "$build/bin/mlfpkg"
printf '{"complete":true,"implementation":"MLF","builds":[{"kind":"executable mlf-compiler:emlf"},{"kind":"executable mlf-compiler:mlfpkg"}]}\n' > "$build/build-report.json"
if [ "${TEST_MUTATE:-0}" = 1 ]; then printf 'changed during build\n' >> "$TEST_PROJECT/libraries/example/Main.hs"; fi
MANAGER
cat > "$work/archive/scripts/bootstrap-async.sh" <<'BRIDGE'
#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
test "$MLF_COMPILER" = "$TEST_SEED"
test "$MLF_PACKAGE_MANAGER" = "$TEST_SEED"
# The native path also fails closed if a child accidentally depends on GHC.
status=0
ghc > "$TEST_FORBIDDEN" 2>&1 || status=$?
test "$status" -eq 97
mkdir -p "$MLF_ASYNC_BOOTSTRAP_DIR/manager"
cp "$root/compiler" "$MLF_ASYNC_BOOTSTRAP_DIR/stage2"
cp "$root/manager" "$MLF_ASYNC_BOOTSTRAP_DIR/manager/mlfpkg"
printf '%s\n' "$MLF_ASYNC_BOOTSTRAP_DIR/manager/mlfpkg" > "$MLF_ASYNC_BOOTSTRAP_DIR/manager.path"
BRIDGE
cat > "$work/clang" <<'CLANG'
#!/bin/sh
set -eu
output=
while [ "$#" -gt 0 ]; do case "$1" in -o) output=$2; shift 2 ;; *) shift ;; esac; done
printf '#!/bin/sh\ntest "$1" = --protocol-version\nprintf "1\\n"\n' > "$output"
chmod +x "$output"
CLANG
chmod +x "$work/seed" "$work/clang" "$work/archive/compiler" "$work/archive/manager" "$work/archive/scripts/bootstrap-async.sh"
(cd "$work/archive"; shasum -a 256 compiler manager scripts/bootstrap-async.sh > bridge-inputs.sha256; tar -czf "$frozen/source.tar.gz" .)
(cd "$frozen"; shasum -a 256 source.tar.gz > source.tar.gz.sha256)
export TEST_PROJECT="$project" TEST_SEED="$work/seed" TEST_CALLS="$work/calls" TEST_FORBIDDEN="$work/forbidden"
export MLF_COMPILER="$TEST_SEED" MLF_PACKAGE_MANAGER="$TEST_SEED" CC="$work/clang"
export MLF_SHARED_BOOTSTRAP_DIR="$work/build with spaces"
export MLF_SHARED_BOOTSTRAP_CONTROL_ONLY=1
run="$project/scripts/bootstrap-shared.sh"
# Mock seeds are accepted only under explicit control mode, never as native evidence.
status=0
MLF_SHARED_BOOTSTRAP_CONTROL_ONLY=0 "$run" --verify-seed-only > "$work/reject-mock.log" 2>&1 || status=$?
test "$status" -eq 2
grep -F 'unsupported wrapper' "$work/reject-mock.log" >/dev/null
test ! -e "$TEST_CALLS"
"$run" --verify-seed-only > "$work/verify-only.log" 2>&1
jq -e '.complete == false and .phase == "seed-verified-only" and .control_only == true' "$MLF_SHARED_BOOTSTRAP_DIR/bootstrap.json" >/dev/null
test ! -e "$TEST_CALLS"
status=0
TEST_SEED_GHC=1 "$run" > "$work/ghc-seed.log" 2>&1 || status=$?
test "$status" -eq 2
jq -e '.complete == false and .phase == "verify-seed"' "$MLF_SHARED_BOOTSTRAP_DIR/bootstrap.json" >/dev/null
test ! -e "$TEST_CALLS"
"$run" > "$work/success.log" 2>&1
jq -e '.complete == true and .fixed_point_qualified == false and .typed_completion_capability == true and .control_only == true and .seed_tools.compiler.kind == "mock-control-fixture" and .route == "mock-control/frozen-legacy-bridge/shared-source-native"' "$MLF_SHARED_BOOTSTRAP_DIR/bootstrap.json" >/dev/null
test -x "$(cat "$MLF_SHARED_BOOTSTRAP_DIR/compiler.path")"
test -x "$(cat "$MLF_SHARED_BOOTSTRAP_DIR/manager.path")"
(cd /; shasum -a 256 -c "$MLF_SHARED_BOOTSTRAP_DIR/compilers.sha256" >/dev/null; shasum -a 256 -c "$MLF_SHARED_BOOTSTRAP_DIR/manager.sha256" >/dev/null)
grep -F 'Forbidden native bootstrap dependency:' "$TEST_FORBIDDEN" >/dev/null
status=0
TEST_FAIL=1 "$run" > "$work/failure.log" 2>&1 || status=$?
test "$status" -eq 81
jq -e '.complete == false and .phase == "current-shared-source" and .exit_code == 81' "$MLF_SHARED_BOOTSTRAP_DIR/bootstrap.json" >/dev/null
test ! -e "$MLF_SHARED_BOOTSTRAP_DIR/compiler.path" && test ! -e "$MLF_SHARED_BOOTSTRAP_DIR/manager.path"
"$run" > "$work/retry.log" 2>&1
jq -e '.complete == true' "$MLF_SHARED_BOOTSTRAP_DIR/bootstrap.json" >/dev/null
test "$(sort -u "$TEST_CALLS" | wc -l | tr -d ' ')" -eq 1
status=0
TEST_MUTATE=1 "$run" > "$work/mutation.log" 2>&1 || status=$?
test "$status" -ne 0
jq -e '.complete == false and .phase == "verify-receipts"' "$MLF_SHARED_BOOTSTRAP_DIR/bootstrap.json" >/dev/null
test ! -e "$MLF_SHARED_BOOTSTRAP_DIR/compiler.path" && test ! -e "$MLF_SHARED_BOOTSTRAP_DIR/manager.path"
printf '%s\n' 'PASS shared bootstrap control: seed isolation, native-only path, both tools, truthful receipt, retry invalidation, source mutation rejection.'
printf '%s\n' 'No real compiler, bridge build, native runtime or fixed point is qualified by this test.'
