#!/usr/bin/env bash
# Exercise the candidate CLI directly, without compiling a test harness.
set -euo pipefail
test "$#" -eq 2 || { printf '%s\n' 'Usage: pr-smoke-cli.sh COMPILER OUTPUT-DIRECTORY' >&2; exit 2; }
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
script="$root/tools/release/pr-smoke-cli.sh"
mkdir -p "$2"
work=$(cd -- "$2" && pwd)
# A failed rerun must not leave a previous success receipt behind.
printf '{"complete":false}\n' > "$work/result.json"
compiler=$(cd -- "$(dirname -- "$1")" && pwd)/$(basename -- "$1")
test -x "$compiler"
cd -- "$root"
fixtures="$root/tests/pr-smoke"
clang=$(command -v clang)
command -v jq >/dev/null
command -v pkg-config >/dev/null
started=$SECONDS
timeout_seconds=60
command_pid=
watchdog_pid=
command_labels=()
cleanup() {
  if [ -n "$watchdog_pid" ]; then kill "$watchdog_pid" 2>/dev/null || true; fi
  if [ -n "$command_pid" ]; then kill "$command_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
sha256() { shasum -a 256 "$1" | awk '{print $1}'; }
fail() { printf 'PR smoke: %s\n' "$*" >&2; exit 1; }

# Each compiler, native program and Clang invocation has a wall-time bound.
# Keep status and diagnostics even for expected failures; timeouts never count
# as successful rejection tests.
run() {
  local label=$1 input=$2 status=0
  shift 2
  command_labels+=("$label")
  rm -f "$work/$label.timed-out"
  "$@" < "$input" > "$work/$label.stdout" 2> "$work/$label.stderr" &
  command_pid=$!
  (
    sleep_pid=
    trap 'if [ -n "$sleep_pid" ]; then kill "$sleep_pid" 2>/dev/null || true; fi; exit 0' TERM INT
    sleep "$timeout_seconds" & sleep_pid=$!
    wait "$sleep_pid" || exit 0
    printf 'Command exceeded %s seconds.\n' "$timeout_seconds" > "$work/$label.timed-out"
    kill -TERM "$command_pid" 2>/dev/null || true
    sleep 2 & sleep_pid=$!
    wait "$sleep_pid" || exit 0
    kill -KILL "$command_pid" 2>/dev/null || true
  ) &
  watchdog_pid=$!
  wait "$command_pid" || status=$?
  command_pid=
  kill "$watchdog_pid" 2>/dev/null || true
  wait "$watchdog_pid" 2>/dev/null || true
  watchdog_pid=
  printf '%s\n' "$status" > "$work/$label.status"
  test ! -e "$work/$label.timed-out" || fail "$label timed out"
  return "$status"
}
success() {
  local label=$1
  run "$@" || fail "$label failed; see $work/$label.stderr"
  test ! -s "$work/$label.stderr" || fail "$label wrote unexpected diagnostics"
}
rejection() {
  local label=$1 expected=$2 status=0
  shift 2
  run "$label" /dev/null "$@" || status=$?
  test "$status" -eq 1 || fail "$label returned $status instead of rejection status 1"
  test ! -s "$work/$label.stdout" || fail "$label produced output before rejecting"
  cmp "$expected" "$work/$label.stderr" || fail "$label rejected for the wrong reason"
}

for name in polymorphic-let impredicative-self-application; do
  success "$name.compile" /dev/null "$compiler" "$fixtures/$name.emlf"
  success "$name.check" /dev/null "$compiler" --check "$work/$name.compile.stdout"
  cmp "$fixtures/$name.type" "$work/$name.check.stdout" || fail "$name has the wrong checked target type"
  printf 'PASS accepted %s\n' "$name"
done
for name in monomorphic-mismatch invalid-universal-annotation; do
  rejection "$name.reject" "$fixtures/$name.stderr" "$compiler" "$fixtures/$name.emlf"
  printf 'PASS rejected %s\n' "$name"
done

# Build and reuse the checkout runtime, with the same compact collector ABI as
# the emitted LLVM. pkg-config supplies the installed GMP/BDWGC toolchain flags.
pkg_cflags=$(pkg-config --cflags gmp bdw-gc)
pkg_libs=$(pkg-config --libs gmp bdw-gc)
read -r -a cflags <<< "$pkg_cflags"
read -r -a libs <<< "$pkg_libs"
success runtime /dev/null "$clang" -O2 -std=c11 -Wall -Wextra -Werror \
  "${cflags[@]}" -c "$root/runtime/mlf_runtime.c" -o "$work/runtime.o"
for name in unbounded-integers lazy-closure-constructor repeated-unicode-input; do
  input=/dev/null
  if [ -f "$fixtures/$name.stdin" ]; then input="$fixtures/$name.stdin"; fi
  success "$name.compile" /dev/null "$compiler" "$fixtures/$name.emlf"
  success "$name.check" /dev/null "$compiler" --check "$work/$name.compile.stdout"
  cmp "$fixtures/io-unit.type" "$work/$name.check.stdout" || fail "$name is not checked IO Unit"
  success "$name.interpreter" "$input" "$compiler" --run-xmlf "$work/$name.compile.stdout"
  cmp "$fixtures/$name.stdout" "$work/$name.interpreter.stdout" || fail "$name interpreter output differs from its oracle"
  success "$name.emit" /dev/null "$compiler" --xmlf-to-llvm-io-gc "$work/$name.compile.stdout"
  success "$name.link" /dev/null "$clang" -O2 -Wno-override-module -x ir "$work/$name.emit.stdout" \
    -x none "$work/runtime.o" "${libs[@]}" -lm -o "$work/$name.native"
  success "$name.llvm" "$input" "$work/$name.native"
  cmp "$fixtures/$name.stdout" "$work/$name.llvm.stdout" || fail "$name LLVM output differs from its oracle"
  printf 'PASS interpreter+llvm %s\n' "$name"
done
rejection malformed.interpreter "$fixtures/malformed-before-effects.interpreter.stderr" \
  "$compiler" --run-xmlf "$fixtures/malformed-before-effects.xmlf"
rejection malformed.llvm "$fixtures/malformed-before-effects.llvm.stderr" \
  "$compiler" --xmlf-to-llvm-io-gc "$fixtures/malformed-before-effects.xmlf"
printf 'PASS malformed target before effects on interpreter+llvm\n'

# Hash every checked-in input and expected result, plus generated targets and
# per-command observations. Only the final atomic rename publishes success.
printf '{}\n' > "$work/fixtures.json"
for file in "$fixtures"/*; do
  jq --arg path "tests/pr-smoke/$(basename -- "$file")" --arg hash "$(sha256 "$file")" \
    '. + {($path):$hash}' "$work/fixtures.json" > "$work/fixtures.tmp"
  mv "$work/fixtures.tmp" "$work/fixtures.json"
done
printf '{}\n' > "$work/observations.json"
test "${#command_labels[@]}" -eq 27 || fail 'command coverage changed'
for label in "${command_labels[@]}"; do
  for suffix in stdout stderr status; do
    file="$work/$label.$suffix"
    jq --arg path "$(basename -- "$file")" --arg hash "$(sha256 "$file")" \
      '. + {($path):$hash}' "$work/observations.json" > "$work/observations.tmp"
    mv "$work/observations.tmp" "$work/observations.json"
  done
done
jq -n --arg compiler_sha256 "$(sha256 "$compiler")" --arg script_sha256 "$(sha256 "$script")" \
  --arg runtime_sha256 "$(sha256 "$root/runtime/mlf_runtime.c")" \
  --arg runtime_header_sha256 "$(sha256 "$root/runtime/mlf_runtime.h")" \
  --arg runtime_object_sha256 "$(sha256 "$work/runtime.o")" --arg clang_sha256 "$(sha256 "$clang")" \
  --argjson seconds "$((SECONDS - started))" --argjson timeout_seconds "$timeout_seconds" \
  --slurpfile fixtures "$work/fixtures.json" --slurpfile observations "$work/observations.json" \
  '{complete:true,compiler_sha256:$compiler_sha256,cases:8,accepted:2,rejected:2,runtime:3,
    invalid_target:1,backends:["interpreter","llvm"],seconds:$seconds,timeout_seconds:$timeout_seconds,
    script_sha256:$script_sha256,runtime_sha256:$runtime_sha256,runtime_header_sha256:$runtime_header_sha256,
    runtime_object_sha256:$runtime_object_sha256,clang_sha256:$clang_sha256,
    fixtures:$fixtures[0],observations:$observations[0]}' > "$work/result.tmp"
mv "$work/result.tmp" "$work/result.json"
printf 'PR compiler CLI smoke passed: 8 cases.\n'
