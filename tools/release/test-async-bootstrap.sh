#!/usr/bin/env bash
# Mock/control-only regression for the bootstrap orchestration. The fake tools
# below never compile or execute MLF; this is not language/runtime qualification.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/mlf-async-bootstrap-test.XXXXXXXX")
trap 'rm -rf "$work"' EXIT
project="$work/project"
mkdir -p "$project/scripts" "$project/bootstrap/seed-compat/Bootstrap" \
  "$project/libraries/mlf-interpreter/Bootstrap" "$project/package" "$project/runtime"
cp "$root/scripts/bootstrap-async.sh" "$project/scripts/"
printf '0.3.0\n' > "$project/VERSION"
printf 'compiler entry fixture\n' > "$project/bootstrap/Main.emlf"
printf 'manager entry fixture\n' > "$project/package/Main.emlf"
printf 'request = processSupervisor\n' > "$project/libraries/mlf-interpreter/Bootstrap/ProcessHost.emlf"
printf 'requires the stage-2 compiler\n' > "$project/bootstrap/seed-compat/Bootstrap/ProcessHost.emlf"
printf 'frozen runtime fixture\n' > "$project/runtime/mlf_runtime.c"
printf 'frozen runner fixture\n' > "$project/runtime/mlf_build_runner.c"
cp "$project/libraries/mlf-interpreter/Bootstrap/ProcessHost.emlf" "$work/native-host.expected"
cat > "$work/compiler" <<'COMPILER'
#!/bin/sh
# Simulated success for the exact-protocol capability check, not an MLF result.
printf '1\n'
COMPILER
cat > "$work/seed-manager" <<'MANAGER'
#!/bin/sh
set -eu
manifest= build= compiler= target=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --manifest) manifest=$2; shift 2 ;;
    --build-dir) build=$2; shift 2 ;;
    --compiler) compiler=$2; shift 2 ;;
    --target) target=$2; shift 2 ;;
    *) shift ;;
  esac
done
# Model the independently decoding released manager rejecting an extended
# compiler's builtin-prelude. The replacement manager retains that validation.
if [ "$0" = "$TEST_SEED_MANAGER" ] && [ "$compiler" != "$TEST_SEED_COMPILER" ]; then
  printf '%s\n' 'invalid generated crate dependency closure: unknown interface primitive' >&2
  exit 86
fi
printf '%s|%s|%s|%s\n' "$0" "$manifest" "$compiler" "$target" >> "$TEST_INVOCATIONS"
test -f "$manifest"
source=$(dirname -- "$manifest")
case "$target" in
  mlfpkg)
    test "$compiler" = "$TEST_SEED_COMPILER"
    test -f "$source/Main.emlf"
    grep -F '"mlf-package-core"' "$manifest" >/dev/null
    grep -F 'requires the stage-2 compiler' "$source/../libraries/mlf-interpreter/Bootstrap/ProcessHost.emlf" >/dev/null
    mkdir -p "$build/bin"
    cp "$TEST_SEED_MANAGER" "$build/bin/mlfpkg"
    ;;
  emlf)
    test -f "$source/bootstrap/Main.emlf"
    if [ "${build##*/}" = stage1 ]; then
      test "$compiler" = "$TEST_SEED_COMPILER"
      grep -F 'requires the stage-2 compiler' "$source/libraries/mlf-interpreter/Bootstrap/ProcessHost.emlf" >/dev/null
    else
      test "$0" != "$TEST_SEED_MANAGER"
      test "$compiler" != "$TEST_SEED_COMPILER"
      runner="$(dirname -- "$0")/mlf-build-runner"
      test -x "$runner"
      test "$("$runner" --protocol-version)" = 1
      cmp "$TEST_NATIVE_HOST" "$source/libraries/mlf-interpreter/Bootstrap/ProcessHost.emlf"
      if [ -n "${TEST_FAIL_STAGE2:-}" ]; then exit 77; fi
    fi
    mkdir -p "$build/bin"
    cp "$TEST_SEED_COMPILER" "$build/bin/emlf"
    ;;
  *) exit 87 ;;
esac
MANAGER
cat > "$work/clang" <<'CLANG'
#!/bin/sh
set -eu
output= source=
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) output=$2; shift 2 ;;
    */mlf_build_runner.c) source=$1; shift ;;
    *) shift ;;
  esac
done
# The helper must come from the frozen source, not the mutable working tree.
case "$source" in */source-*-stage1/runtime/mlf_build_runner.c) ;; *) exit 88 ;; esac
grep -Fx 'frozen runner fixture' "$source" >/dev/null
printf '%s\n' "$source" >> "$TEST_RUNNER_INPUTS"
cat > "$output" <<'RUNNER'
#!/bin/sh
test "$1" = --protocol-version
printf '1\n'
RUNNER
chmod +x "$output"
CLANG
chmod +x "$work/compiler" "$work/seed-manager" "$work/clang"
export TEST_SEED_MANAGER="$work/seed-manager" TEST_SEED_COMPILER="$work/compiler"
export TEST_NATIVE_HOST="$work/native-host.expected" TEST_INVOCATIONS="$work/invocations"
export TEST_RUNNER_INPUTS="$work/runner-inputs"
export MLF_COMPILER="$TEST_SEED_COMPILER" MLF_PACKAGE_MANAGER="$TEST_SEED_MANAGER"
export MLF_ASYNC_BOOTSTRAP_DIR="$work/build" CC="$work/clang"
: > "$TEST_INVOCATIONS"
: > "$TEST_RUNNER_INPUTS"
status=0
"$TEST_SEED_MANAGER" --compiler "$work/extended-compiler" > "$work/rejection.out" 2> "$work/rejection.err" || status=$?
test "$status" -eq 86
grep -F 'unknown interface primitive' "$work/rejection.err" >/dev/null
status=0
TEST_FAIL_STAGE2=1 "$project/scripts/bootstrap-async.sh" > "$work/first.out" 2> "$work/first.err" || status=$?
test "$status" -eq 77
"$project/scripts/bootstrap-async.sh" > "$work/retry.out" 2> "$work/retry.err"
"$project/scripts/bootstrap-async.sh" > "$work/repeat.out" 2> "$work/repeat.err"
test "$(wc -l < "$TEST_INVOCATIONS" | tr -d ' ')" -eq 9
for line in 1 2 3; do
  first=$(sed -n "${line}p" "$TEST_INVOCATIONS")
  test "$first" = "$(sed -n "$((line + 3))p" "$TEST_INVOCATIONS")"
  test "$first" = "$(sed -n "$((line + 6))p" "$TEST_INVOCATIONS")"
done
test "$(cut -d '|' -f 4 "$TEST_INVOCATIONS" | head -3 | tr '\n' ' ')" = 'emlf mlfpkg emlf '
test "$(sort -u "$TEST_RUNNER_INPUTS" | wc -l | tr -d ' ')" -eq 1
cmp "$TEST_NATIVE_HOST" "$project/libraries/mlf-interpreter/Bootstrap/ProcessHost.emlf"
test -s "$work/build/compilers.sha256"
test -s "$work/build/manager.sha256"
test -s "$work/build/source-identity.txt"
printf '%s\n' 'PASS mock/control bootstrap transition: manager replacement, stable retry, isolated bridge, frozen adjacent runner.'
printf '%s\n' 'This control test does not qualify MLF compilers, interpreter behavior, or native runtime parity.'
