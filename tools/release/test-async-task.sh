#!/usr/bin/env bash
# The same checked Task targets run on the current interpreter and LLVM runtime.
# No seed surrogate, timing-only oracle, or extracted native mock is accepted.
set -euo pipefail
test "$#" -eq 2 || { echo 'Usage: test-async-task.sh COMPILER OUTPUT-DIRECTORY' >&2; exit 2; }
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
. "$root/tools/testing/native-events.sh"
compiler=$(cd -- "$(dirname -- "$1")" && pwd)/$(basename -- "$1")
test -x "$compiler"
mkdir -p -- "$2"
output=$(cd -- "$2" && pwd)
printf '{"complete":false}\n' > "$output/result.json"
work=$(mktemp -d "$output/run.XXXXXXXX")
fixtures="$root/tests/async-task"
cd -- "$root"
case $(uname -s) in Linux) ulimit -s unlimited ;; Darwin) ;; *) echo 'Task language runner supports Linux and macOS.' >&2; exit 2 ;; esac
timeout_seconds=${MLF_ASYNC_COMMAND_TIMEOUT:-600}
case $timeout_seconds in ''|*[!0-9]*|0) echo 'MLF_ASYNC_COMMAND_TIMEOUT must be positive.' >&2; exit 2 ;; esac
source_compile_seconds=${MLF_ASYNC_SOURCE_COMPILE_TIMEOUT:-$timeout_seconds}
case $source_compile_seconds in ''|*[!0-9]*|0) echo 'MLF_ASYNC_SOURCE_COMPILE_TIMEOUT must be positive.' >&2; exit 2 ;; esac
command_pid= watchdog_pid=
labels=()
fail() { echo "Async.Task: $*; evidence: $work" >&2; exit 1; }
sha256() { shasum -a 256 "$1" | awk '{print $1}'; }
stop_jobs() { trap '' TERM INT; local pid; for pid in $(jobs -p); do kill "$pid" 2>/dev/null || true; done; wait 2>/dev/null || true; exit 0; }
cleanup() {
 if [ -n "$watchdog_pid" ]; then kill "$watchdog_pid" 2>/dev/null || true; fi
 if [ -n "$command_pid" ]; then kill "$command_pid" 2>/dev/null || true; fi
}
trap 'status=$?; cleanup; mlf_case_cleanup "$status"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
run() {
 local label=$1 status=0 limit=$timeout_seconds
 shift
 case $label in
  *.compile) limit=$source_compile_seconds ;;
  *.interpreter|*.llvm) if [ "$limit" -gt 45 ]; then limit=45; fi ;;
 esac
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
 test ! -e "$work/$label.timed-out" || { mlf_case_result timeout "$status"; fail "$label timed out"; }
 return "$status"
}
success() { local label=$1; run "$@" || fail "$label failed"; test ! -s "$work/$label.stderr" || fail "$label emitted diagnostics"; }
record_inputs() {
 local destination=$1 file
 printf '{}\n' > "$destination"
 for file in "$fixtures"/* "$root/tools/release/test-async-task.sh" "$root/tools/release/check_async_abi.py" "$root/tools/testing/native-events.sh" "$root/tests/async-process/fixture.c" \
  "$root/libraries/mlf-foundation/Bootstrap/Types.hs" "$root/libraries/mlf-foundation/Bootstrap/Std.hs" \
  "$root/libraries/mlf-async/Async/Task/Core.hs" "$root/libraries/mlf-async/Async/Task.hs" "$root/libraries/mlf-async/Async/Task/Internal.hs" \
  "$root/libraries/mlf-async/Async/Process.hs" "$root/libraries/mlf-async/Async/Process/Internal.hs" \
  "$root/runtime/mlf_runtime.c" "$root/runtime/mlf_runtime.h" "$root/runtime/mlf_completion.h" "$root"/runtime/mlf_process*; do
   jq --arg path "${file#"$root"/}" --arg hash "$(sha256 "$file")" '. + {($path):$hash}' "$destination" > "$destination.tmp"
   mv "$destination.tmp" "$destination"
 done
}
record_inputs "$work/inputs.json"
compiler_hash=$(sha256 "$compiler")
include_args=(-i "$root/libraries/mlf-foundation" -i "$root/libraries/mlf-async")
wanted=${MLF_TEST_EXACT:-}
unset MLF_ASYNC_CASE
source_rejections=0 cases=0 whitebox_cases=0
ran_interpreter=false ran_llvm=false
artifact_files=()

for kind in opaque-fiber opaque-task opaque-internal-fiber opaque-internal-task mixed-fiber; do
 mlf_case_selected "async-task/source-rejection/$kind" || continue
 mlf_case_start "async-task/source-rejection/$kind"
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
   grep -Ei 'type constructor mismatch|cannot unify|incompatible' "$work/$kind.stderr" >/dev/null || fail "$kind unrelated rejection"
   grep -F 'String' "$work/$kind.stderr" >/dev/null || fail "$kind missing String diagnostic"
   grep -F 'Int' "$work/$kind.stderr" >/dev/null || fail "$kind missing Int diagnostic" ;;
 esac
 mlf_case_result pass "$status"
 source_rejections=$((source_rejections + 1))
 echo "PASS $kind rejection"
done

case "$wanted" in ''|async-task/parity/*)
 clang=$(command -v clang)
 success fixture "$clang" -O2 -std=c11 -Wall -Wextra -Werror "$fixtures/fixture.c" -o "$work/fixture"
 export MLF_ASYNC_FIXTURE="$work/fixture"
 artifact_files+=("$work/fixture")
 ;; esac
emit_llvm=false
case "$wanted" in ''|async-task/parity/*/llvm/*)
 emit_llvm=true
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
 success runtime "$clang" -O2 -std=c11 -Wall -Wextra -Werror "${cflags[@]}" -c "$root/runtime/mlf_runtime.c" -o "$work/runtime.o"
 artifact_files+=("$work/runtime.o")
 ;; esac

# White-box tests import the committed Async.Task.Core module directly.

for suite in main processes wait-graph guards; do
 case "$wanted" in ''|async-task/parity/"$suite/"*) ;; *) continue ;; esac
 args=("${include_args[@]}")
 type_oracle=io-unit.type
 case $suite in
  main) entry=Main.emlf; oracle=suite.stdout ;;
  processes) entry=Processes.emlf; oracle=processes.stdout ;;
  wait-graph) entry=WaitGraph.emlf; oracle=wait-graph.stdout ;;
  guards) entry=Guards.emlf; oracle=guards.stdout; type_oracle=guards.type ;;
 esac
 oracle_file="$fixtures/$oracle"
 if [ -n "$wanted" ]; then
  export MLF_ASYNC_CASE="${wanted##*/}"
  oracle_file="$work/$suite.expected"
  grep -Fx "PASS $MLF_ASYNC_CASE" "$fixtures/$oracle" > "$oracle_file" || fail "unknown $suite case"
 fi
 success "$suite.compile" "$compiler" "${args[@]}" "$fixtures/$entry"
 artifact_files+=("$work/$suite.compile.stdout")
 success "$suite.check" "$compiler" --check "$work/$suite.compile.stdout"
 cmp "$fixtures/$type_oracle" "$work/$suite.check.stdout" || fail "$suite target type"
 if "$emit_llvm"; then
  success "$suite.emit" "$compiler" --xmlf-to-llvm-io-gc "$work/$suite.compile.stdout"
  python3 -B "$root/tools/release/check_async_abi.py" "$work/$suite.emit.stdout" >/dev/null || fail "$suite lacks async ABI guard"
  success "$suite.link" "$clang" -O2 -Wno-override-module -x ir "$work/$suite.emit.stdout" -x none "$work/runtime.o" "${libs[@]}" -o "$work/$suite.native"
  artifact_files+=("$work/$suite.emit.stdout" "$work/$suite.native")
 fi
 for backend in interpreter llvm; do
  prefix="async-task/parity/$suite/$backend"
  case "$wanted" in ''|"$prefix/"*) ;; *) continue ;; esac
  mkdir "$work/$suite.$backend"
  status=0
  export MLF_ASYNC_WORK="$work/$suite.$backend"
  if [ "$backend" = interpreter ]; then
   run "$suite.$backend" "$compiler" --run-xmlf "$work/$suite.compile.stdout" || status=$?
  else
   run "$suite.$backend" "$work/$suite.native" || status=$?
  fi
  mlf_report_labeled_output "$prefix" "$oracle_file" "$work/$suite.$backend.stdout" "$status" || fail "$suite.$backend differs from literal oracle"
  test "$status" -eq 0 && test ! -s "$work/$suite.$backend.stderr" || fail "$suite.$backend failed"
  if [ "$backend" = interpreter ]; then ran_interpreter=true; else ran_llvm=true; fi
  echo "PASS $suite $backend"
 done
 if [ -z "$wanted" ]; then
  cmp "$work/$suite.interpreter.stdout" "$work/$suite.llvm.stdout" || fail "$suite backend differences"
 fi
 suite_cases=$(grep -c '^PASS ' "$oracle_file")
 cases=$((cases + suite_cases))
 if [ "$suite" = wait-graph ]; then whitebox_cases=$suite_cases; fi
done
record_inputs "$work/inputs.final.json"
cmp "$work/inputs.json" "$work/inputs.final.json" || fail 'source changed during run'
test "$(sha256 "$compiler")" = "$compiler_hash" || fail 'compiler changed during run'
if [ -z "$wanted" ]; then
 test "${#labels[@]}" -eq 31 || fail 'command coverage changed'
 test "$cases:$whitebox_cases:$source_rejections" = 31:6:5 || fail 'case coverage changed'
fi
printf '{}\n' > "$work/artifacts.json"
for file in ${artifact_files[@]+"${artifact_files[@]}"}; do
 digest=$(sha256 "$file")
 jq --arg path "$(basename "$file")" --arg hash "$digest" '. + {($path):$hash}' "$work/artifacts.json" > "$work/artifacts.tmp"
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
jq -n --arg exact "${MLF_TEST_EXACT:-}" --arg compiler_sha256 "$compiler_hash" --arg work "$work" \
 --arg core_sha256 "$(sha256 "$root/libraries/mlf-async/Async/Task/Core.hs")" \
 --argjson cases "$cases" --argjson source_rejections "$source_rejections" --argjson whitebox_cases "$whitebox_cases" \
 --argjson interpreter "$ran_interpreter" --argjson llvm "$ran_llvm" \
 --slurpfile inputs "$work/inputs.json" --slurpfile observations "$work/observations.json" --slurpfile artifacts "$work/artifacts.json" \
 '{complete:($exact == ""),cases:$cases,source_rejections:$source_rejections,whitebox_cases:$whitebox_cases,
 backends:[if $interpreter then "interpreter" else empty end, if $llvm then "llvm" else empty end],
 compiler_sha256:$compiler_sha256,work:$work,whitebox_source_sha256:$core_sha256,whitebox_source:"libraries/mlf-async/Async/Task/Core.hs",
 inputs:$inputs[0],observations:$observations[0],artifacts:$artifacts[0]}' > "$output/result.tmp"
mv "$output/result.tmp" "$output/result.json"
if [ -z "${MLF_TEST_EXACT:-}" ]; then
 echo 'Async.Task language parity passed: 31 contracts (6 white-box), 5 source rejections.'
fi
