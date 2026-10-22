#!/usr/bin/env bash
# Execute the same checked Async.Process target through the candidate's real
# interpreter and the current LLVM runtime. A seed/stage-1 stub is not a pass.
set -euo pipefail
test "$#" -eq 2 || { printf '%s\n' 'Usage: test-async-process.sh COMPILER OUTPUT-DIRECTORY' >&2; exit 2; }
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
compiler=$(cd -- "$(dirname -- "$1")" && pwd)/$(basename -- "$1")
test -x "$compiler" || { printf '%s\n' 'Candidate compiler is not executable.' >&2; exit 2; }
mkdir -p -- "$2"
output=$(cd -- "$2" && pwd)
printf '{"complete":false}\n' > "$output/result.json"
work=$(mktemp -d "$output/run.XXXXXXXX")
fixtures="$root/tests/async-process"
clang=$(command -v clang)
command -v jq >/dev/null
command -v pkg-config >/dev/null
cd -- "$root"
case $(uname -s) in Linux) ulimit -s unlimited ;; Darwin) ;; *) printf '%s\n' 'This shell language-parity runner supports Linux and macOS.' >&2; exit 2 ;; esac
timeout_seconds=${MLF_ASYNC_COMMAND_TIMEOUT:-600}
case $timeout_seconds in ''|*[!0-9]*|0) printf '%s\n' 'MLF_ASYNC_COMMAND_TIMEOUT must be a positive number of seconds.' >&2; exit 2 ;; esac
started=$SECONDS
command_pid=
watchdog_pid=
command_labels=()
fail() { printf 'Async.Process: %s\n' "$*" >&2; exit 1; }
sha256() { shasum -a 256 "$1" | awk '{print $1}'; }
stop_sleep_jobs() {
  trap '' TERM INT
  local child_pid
  for child_pid in $(jobs -p); do kill "$child_pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
  exit 0
}
cleanup() {
  if [ -n "$watchdog_pid" ]; then kill "$watchdog_pid" 2>/dev/null || true; fi
  if [ -n "$command_pid" ]; then kill "$command_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
run() {
  local label=$1 status=0 limit=$timeout_seconds
  shift
  case $label in
    interpreter|llvm|panic.interpreter|panic.llvm|panic.*.reaped)
      if [ "$limit" -gt 60 ]; then limit=60; fi ;;
  esac
  command_labels+=("$label")
  "$@" < /dev/null > "$work/$label.stdout" 2> "$work/$label.stderr" &
  command_pid=$!
  (
    trap stop_sleep_jobs TERM INT
    sleep "$limit" &
    wait "$!" || exit 0
    printf 'Command exceeded %s seconds.\n' "$limit" > "$work/$label.timed-out"
    kill -TERM "$command_pid" 2>/dev/null || true
    sleep 2 &
    wait "$!" || exit 0
    kill -KILL "$command_pid" 2>/dev/null || true
  ) &
  watchdog_pid=$!
  wait "$command_pid" || status=$?
  command_pid=
  kill "$watchdog_pid" 2>/dev/null || true
  wait "$watchdog_pid" 2>/dev/null || true
  watchdog_pid=
  printf '%s\n' "$status" > "$work/$label.status"
  test ! -e "$work/$label.timed-out" || fail "$label timed out; see $work"
  return "$status"
}
success() {
  local label=$1
  run "$@" || fail "$label failed; see $work/$label.stderr"
  test ! -s "$work/$label.stderr" || fail "$label emitted unexpected diagnostics; see $work/$label.stderr"
}
include_args=(-i "$root/libraries/mlf-foundation" -i "$root/libraries/mlf-async")

record_inputs() {
  local destination=$1 file
  printf '{}\n' > "$destination"
  for file in "$fixtures"/* "$root/tools/release/test-async-process.sh" \
    "$root/libraries/mlf-foundation/Bootstrap/Types.emlf" "$root/libraries/mlf-foundation/Bootstrap/Std.emlf" \
    "$root/libraries/mlf-async/Async/Process.emlf" "$root/libraries/mlf-async/Async/Process/Internal.emlf" \
    "$root"/runtime/*; do
    test -f "$file" || continue
    jq --arg path "${file#"$root"/}" --arg hash "$(sha256 "$file")" '. + {($path):$hash}' "$destination" > "$destination.tmp"
    mv "$destination.tmp" "$destination"
  done
}
record_inputs "$work/inputs.json"
compiler_hash=$(sha256 "$compiler")

# An abstract exported type must not leak its data constructor. Check the
# rejected name as well as status so an unrelated parser/import failure fails.
for kind in handle scope; do
  label="opaque-$kind"
  status=0
  run "$label" "$compiler" "${include_args[@]}" "$fixtures/$label.emlf" || status=$?
  test "$status" -eq 1 || fail "$label returned $status, expected source rejection 1"
  test ! -s "$work/$label.stdout" || fail "$label produced a target"
  if [ "$kind" = handle ]; then constructor=ProcessHandle; else constructor=ProcessScope; fi
  grep -F "$constructor" "$work/$label.stderr" >/dev/null || fail "$label rejected for an unrelated reason"
  grep -Ei 'unknown|unbound|not (in scope|exported)|undefined|unresolved' "$work/$label.stderr" >/dev/null || fail "$label did not report inaccessible constructor"
  printf 'PASS opaque %s constructor\n' "$kind"
done

# GMP is conventional pkg-config discovery. Honor the repository's documented
# explicit collector prefix when one is selected by a native bootstrap.
read -r -a cflags <<< "$(pkg-config --cflags gmp)"
read -r -a libs <<< "$(pkg-config --libs gmp)"
if [ -n "${MLF_GC_PREFIX:-}" ]; then
  cflags+=("-I$MLF_GC_PREFIX/include")
  libs+=("$MLF_GC_PREFIX/lib/libgc.a")
else
  read -r -a gc_cflags <<< "$(pkg-config --cflags bdw-gc)"
  read -r -a gc_libs <<< "$(pkg-config --libs bdw-gc)"
  cflags+=("${gc_cflags[@]}")
  libs+=("${gc_libs[@]}")
fi
libs+=(-lm -lpthread)
if [ "$(uname -s)" = Linux ]; then libs+=(-ldl); fi
success fixture "$clang" -O2 -std=c11 -Wall -Wextra -Werror "$fixtures/fixture.c" -o "$work/fixture"
success runtime "$clang" -O2 -std=c11 -Wall -Wextra -Werror "${cflags[@]}" -c "$root/runtime/mlf_runtime.c" -o "$work/runtime.o"
success compile "$compiler" "${include_args[@]}" "$fixtures/Main.emlf"
success check "$compiler" --check "$work/compile.stdout"
cmp "$fixtures/io-unit.type" "$work/check.stdout" || fail 'checked target does not have type IO Unit'
success emit "$compiler" --xmlf-to-llvm-io-gc "$work/compile.stdout"
grep -F 'mlf_require_async_completion_v2_abi' "$work/emit.stdout" >/dev/null || fail 'native target lacks the current async primitive capability guard'
success link "$clang" -O2 -Wno-override-module -x ir "$work/emit.stdout" -x none "$work/runtime.o" "${libs[@]}" -o "$work/suite.native"
export MLF_ASYNC_FIXTURE="$work/fixture"
for backend in interpreter llvm; do
  mkdir -- "$work/$backend"
  export MLF_ASYNC_WORK="$work/$backend"
  if [ "$backend" = interpreter ]; then
    success "$backend" "$compiler" --run-xmlf "$work/compile.stdout"
  else
    success "$backend" "$work/suite.native"
  fi
  cmp "$fixtures/suite.stdout" "$work/$backend.stdout" || fail "$backend differs from the literal oracle"
  printf 'PASS %s: 13 Async.Process contracts\n' "$backend"
done
cmp "$work/interpreter.stdout" "$work/llvm.stdout" || fail 'backend observations differ'

# A panic bypasses the library's ordinary Either return. Interpreter error
# cleanup and native fail() cleanup are independent paths, so execute both.
success panic.compile "$compiler" "${include_args[@]}" "$fixtures/Panic.emlf"
success panic.check "$compiler" --check "$work/panic.compile.stdout"
cmp "$fixtures/io-unit.type" "$work/panic.check.stdout" || fail 'panic target does not have type IO Unit'
success panic.emit "$compiler" --xmlf-to-llvm-io-gc "$work/panic.compile.stdout"
success panic.link "$clang" -O2 -Wno-override-module -x ir "$work/panic.emit.stdout" -x none "$work/runtime.o" "${libs[@]}" -o "$work/panic.native"
for backend in interpreter llvm; do
  mkdir -- "$work/$backend-panic"
  export MLF_ASYNC_WORK="$work/$backend-panic"
  status=0
  if [ "$backend" = interpreter ]; then
    run "panic.$backend" "$compiler" --run-xmlf "$work/panic.compile.stdout" || status=$?
  else
    run "panic.$backend" "$work/panic.native" || status=$?
  fi
  test "$status" -eq 1 || fail "panic.$backend returned $status instead of error status 1"
  test ! -s "$work/panic.$backend.stdout" || fail "panic.$backend produced output before failure"
  grep -F 'async-scope-panic' "$work/panic.$backend.stderr" >/dev/null || fail "panic.$backend failed for an unrelated reason"
  success "panic.$backend.reaped" "$work/fixture" assert-gone "$MLF_ASYNC_WORK/panic.pid"
  printf 'PASS %s panic cancel-and-join\n' "$backend"
done

record_inputs "$work/inputs.final.json"
cmp "$work/inputs.json" "$work/inputs.final.json" || fail 'test inputs changed during execution'
test "$(sha256 "$compiler")" = "$compiler_hash" || fail 'compiler changed during execution'
printf '{}\n' > "$work/observations.json"
test "${#command_labels[@]}" -eq 18 || fail 'command coverage changed'
for label in "${command_labels[@]}"; do
  for suffix in stdout stderr status; do
    file="$work/$label.$suffix"
    jq --arg path "$(basename -- "$file")" --arg hash "$(sha256 "$file")" '. + {($path):$hash}' "$work/observations.json" > "$work/observations.tmp"
    mv "$work/observations.tmp" "$work/observations.json"
  done
done
jq -n --arg compiler_sha256 "$compiler_hash" --arg clang_sha256 "$(sha256 "$clang")" \
  --arg target_sha256 "$(sha256 "$work/compile.stdout")" --arg runtime_object_sha256 "$(sha256 "$work/runtime.o")" \
  --arg native_sha256 "$(sha256 "$work/suite.native")" --arg work "$work" \
  --argjson seconds "$((SECONDS - started))" --argjson timeout_seconds "$timeout_seconds" \
  --slurpfile inputs "$work/inputs.json" --slurpfile observations "$work/observations.json" \
  '{complete:true,cases:13,panic_cleanup_cases:1,source_rejections:2,backends:["interpreter","llvm"],
    compiler_sha256:$compiler_sha256,clang_sha256:$clang_sha256,target_sha256:$target_sha256,
    runtime_object_sha256:$runtime_object_sha256,native_sha256:$native_sha256,
    work:$work,seconds:$seconds,timeout_seconds:$timeout_seconds,
    inputs:$inputs[0],observations:$observations[0]}' > "$output/result.tmp"
mv "$output/result.tmp" "$output/result.json"
printf 'Async.Process language parity passed: 13 contracts, panic cleanup, 2 opaque-constructor rejections.\n'
