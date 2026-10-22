#!/usr/bin/env bash
# The same checked Task targets run on the current interpreter and LLVM runtime.
# No seed surrogate, timing-only oracle, or extracted native mock is accepted.
set -euo pipefail
test "$#" -eq 2 || { echo 'Usage: test-async-task.sh COMPILER OUTPUT-DIRECTORY' >&2; exit 2; }
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
compiler=$(cd -- "$(dirname -- "$1")" && pwd)/$(basename -- "$1")
test -x "$compiler"
mkdir -p -- "$2"
output=$(cd -- "$2" && pwd)
printf '{"complete":false}\n' > "$output/result.json"
work=$(mktemp -d "$output/run.XXXXXXXX")
fixtures="$root/tests/async-task"
clang=$(command -v clang)
cd -- "$root"
case $(uname -s) in Linux) ulimit -s unlimited ;; Darwin) ;; *) echo 'Task language runner supports Linux and macOS.' >&2; exit 2 ;; esac
timeout_seconds=${MLF_ASYNC_COMMAND_TIMEOUT:-600}
case $timeout_seconds in ''|*[!0-9]*|0) echo 'MLF_ASYNC_COMMAND_TIMEOUT must be positive.' >&2; exit 2 ;; esac
command_pid= watchdog_pid=
labels=()
fail() { echo "Async.Task: $*; evidence: $work" >&2; exit 1; }
sha256() { shasum -a 256 "$1" | awk '{print $1}'; }
stop_jobs() { trap '' TERM INT; local pid; for pid in $(jobs -p); do kill "$pid" 2>/dev/null || true; done; wait 2>/dev/null || true; exit 0; }
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
 case $label in *.interpreter|*.llvm) if [ "$limit" -gt 45 ]; then limit=45; fi ;; esac
 labels+=("$label")
 "$@" < /dev/null > "$work/$label.stdout" 2> "$work/$label.stderr" &
 command_pid=$!
 (
  trap stop_jobs TERM INT
  sleep "$limit" & wait "$!" || exit 0
  echo "Exceeded $limit seconds" > "$work/$label.timed-out"
  kill -TERM "$command_pid" 2>/dev/null || true
  sleep 2 & wait "$!" || exit 0
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
success() { local label=$1; run "$@" || fail "$label failed"; test ! -s "$work/$label.stderr" || fail "$label emitted diagnostics"; }
record_inputs() {
 local destination=$1 file
 printf '{}\n' > "$destination"
 for file in "$fixtures"/* "$root/tools/release/test-async-task.sh" "$root/tests/async-process/fixture.c" \
  "$root/libraries/mlf-foundation/Bootstrap/Types.emlf" "$root/libraries/mlf-foundation/Bootstrap/Std.emlf" \
  "$root/libraries/mlf-async/Async/Task.emlf" "$root/libraries/mlf-async/Async/Task/Internal.emlf" \
  "$root/libraries/mlf-async/Async/Process.emlf" "$root/libraries/mlf-async/Async/Process/Internal.emlf" \
  "$root/runtime/mlf_runtime.c" "$root/runtime/mlf_runtime.h" "$root/runtime/mlf_completion.h" "$root"/runtime/mlf_process*; do
   jq --arg path "${file#"$root"/}" --arg hash "$(sha256 "$file")" '. + {($path):$hash}' "$destination" > "$destination.tmp"
   mv "$destination.tmp" "$destination"
 done
}
record_inputs "$work/inputs.json"
compiler_hash=$(sha256 "$compiler")
include_args=(-i "$root/libraries/mlf-foundation" -i "$root/libraries/mlf-async")

for kind in opaque-fiber opaque-task opaque-internal-fiber opaque-internal-task mixed-fiber; do
 status=0
 run "$kind" "$compiler" "${include_args[@]}" "$fixtures/$kind.emlf" || status=$?
 test "$status" -eq 1 || fail "$kind expected rejection, got $status"
 test ! -s "$work/$kind.stdout" || fail "$kind emitted target"
 case $kind in
  opaque-*)
   case $kind in *fiber) constructor=Fiber ;; *) constructor=Task ;; esac
   grep -F "$constructor" "$work/$kind.stderr" >/dev/null || fail "$kind unrelated rejection"
   grep -Ei 'unknown|unbound|not (in scope|exported)|undefined|unresolved' "$work/$kind.stderr" >/dev/null || fail "$kind constructor diagnostic absent" ;;
  mixed-fiber)
   grep -Ei 'inference|type|unif|incompatible' "$work/$kind.stderr" >/dev/null || fail "$kind unrelated rejection" ;;
 esac
 echo "PASS $kind rejection"
done

read -r -a cflags <<< "$(pkg-config --cflags gmp)"
read -r -a libs <<< "$(pkg-config --libs gmp)"
if [ -n "${MLF_GC_PREFIX:-}" ]; then
 cflags+=("-I$MLF_GC_PREFIX/include"); libs+=("$MLF_GC_PREFIX/lib/libgc.a")
else
 read -r -a gc_cflags <<< "$(pkg-config --cflags bdw-gc)"
 read -r -a gc_libs <<< "$(pkg-config --libs bdw-gc)"
 cflags+=("${gc_cflags[@]}"); libs+=("${gc_libs[@]}")
fi
libs+=(-lm -lpthread)
if [ "$(uname -s)" = Linux ]; then libs+=(-ldl); fi
success fixture "$clang" -O2 -std=c11 -Wall -Wextra -Werror "$fixtures/fixture.c" -o "$work/fixture"
success runtime "$clang" -O2 -std=c11 -Wall -Wextra -Werror "${cflags[@]}" -c "$root/runtime/mlf_runtime.c" -o "$work/runtime.o"

# This overlay changes only the export header for white-box scheduler tests.
# It is never packaged or used for the public API and process integration tests.
mkdir -p "$work/whitebox/Async/Task"
awk 'BEGIN { header=1; print "module Async.Task.Internal where" } header { if ($0 ~ /where$/) header=0; next } { print }' \
 "$root/libraries/mlf-async/Async/Task/Internal.emlf" > "$work/whitebox/Async/Task/Internal.emlf"

export MLF_ASYNC_FIXTURE="$work/fixture"
for suite in main processes wait-graph; do
 args=("${include_args[@]}")
 case $suite in
  main) entry=Main.emlf; oracle=suite.stdout ;;
  processes) entry=Processes.emlf; oracle=processes.stdout ;;
  wait-graph) entry=WaitGraph.emlf; oracle=wait-graph.stdout; args=(-i "$work/whitebox" "${include_args[@]}") ;;
 esac
 success "$suite.compile" "$compiler" "${args[@]}" "$fixtures/$entry"
 success "$suite.check" "$compiler" --check "$work/$suite.compile.stdout"
 cmp "$fixtures/io-unit.type" "$work/$suite.check.stdout" || fail "$suite target type"
 success "$suite.emit" "$compiler" --xmlf-to-llvm-io-gc "$work/$suite.compile.stdout"
 grep -F 'mlf_require_async_completion_v2_abi' "$work/$suite.emit.stdout" >/dev/null || fail "$suite lacks async ABI guard"
 success "$suite.link" "$clang" -O2 -Wno-override-module -x ir "$work/$suite.emit.stdout" -x none "$work/runtime.o" "${libs[@]}" -o "$work/$suite.native"
 for backend in interpreter llvm; do
  mkdir "$work/$suite.$backend"
  export MLF_ASYNC_WORK="$work/$suite.$backend"
  if [ "$backend" = interpreter ]; then
   success "$suite.$backend" "$compiler" --run-xmlf "$work/$suite.compile.stdout"
  else
   success "$suite.$backend" "$work/$suite.native"
  fi
  cmp "$fixtures/$oracle" "$work/$suite.$backend.stdout" || fail "$suite.$backend differs from literal oracle"
  echo "PASS $suite $backend"
 done
 cmp "$work/$suite.interpreter.stdout" "$work/$suite.llvm.stdout" || fail "$suite backend differences"
done
record_inputs "$work/inputs.final.json"
cmp "$work/inputs.json" "$work/inputs.final.json" || fail 'source changed during run'
test "$(sha256 "$compiler")" = "$compiler_hash" || fail 'compiler changed during run'
test "${#labels[@]}" -eq 25 || fail 'command coverage changed'
printf '{}\n' > "$work/artifacts.json"
for file in "$work/runtime.o" "$work/fixture" "$work/"*.native "$work/"*.compile.stdout "$work/"*.emit.stdout; do
 jq --arg path "$(basename "$file")" --arg hash "$(sha256 "$file")" '. + {($path):$hash}' "$work/artifacts.json" > "$work/artifacts.tmp"
 mv "$work/artifacts.tmp" "$work/artifacts.json"
done
printf '{}\n' > "$work/observations.json"
for label in "${labels[@]}"; do
 for suffix in stdout stderr status; do
  file="$work/$label.$suffix"
  jq --arg path "$(basename "$file")" --arg hash "$(sha256 "$file")" '. + {($path):$hash}' "$work/observations.json" > "$work/observations.tmp"
  mv "$work/observations.tmp" "$work/observations.json"
 done
done
jq -n --arg compiler_sha256 "$compiler_hash" --arg work "$work" \
 --arg overlay_sha256 "$(sha256 "$work/whitebox/Async/Task/Internal.emlf")" \
 --slurpfile inputs "$work/inputs.json" --slurpfile observations "$work/observations.json" --slurpfile artifacts "$work/artifacts.json" \
 '{complete:true,cases:29,source_rejections:5,backends:["interpreter","llvm"],whitebox_cases:5,
 compiler_sha256:$compiler_sha256,work:$work,whitebox_source_sha256:$overlay_sha256,
 inputs:$inputs[0],observations:$observations[0],artifacts:$artifacts[0]}' > "$output/result.tmp"
mv "$output/result.tmp" "$output/result.json"
echo 'Async.Task language parity passed: 29 contracts (5 white-box), 5 source rejections.'
