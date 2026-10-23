#!/usr/bin/env bash
# Qualify real checked-crate imports, native execution, opacity, and cache replay.
# This does not replace the direct interpreter/native Task and Process suites.
set -euo pipefail
test "$#" -eq 3 || { echo 'Usage: test-async-package.sh COMPILER MANAGER OUTPUT-DIRECTORY' >&2; exit 2; }
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
compiler=$(cd -- "$(dirname -- "$1")" && pwd)/$(basename -- "$1")
manager=$(cd -- "$(dirname -- "$2")" && pwd)/$(basename -- "$2")
runner="$(dirname -- "$manager")/mlf-build-runner"
for tool in "$compiler" "$manager" "$runner"; do
 test -x "$tool" || { echo "Required executable unavailable: $tool" >&2; exit 2; }
done
command -v jq >/dev/null
command -v shasum >/dev/null
clang=$(command -v clang)
mkdir -p -- "$3"
output=$(cd -- "$3" && pwd)
printf '{"complete":false}\n' > "$output/result.json"
work=$(mktemp -d "$output/run.XXXXXXXX")
source="$work/source"
mkdir -p "$source/libraries" "$source/tests" "$source/tools/release"
cd -- "$root"
case $(uname -s) in Linux) ulimit -s unlimited ;; Darwin) ;; *) echo 'Package gate supports Linux and macOS.' >&2; exit 2 ;; esac
GC_FREE_SPACE_DIVISOR=${GC_FREE_SPACE_DIVISOR:-8}
export GC_FREE_SPACE_DIVISOR
timeout_seconds=${MLF_ASYNC_COMMAND_TIMEOUT:-1800}
case $timeout_seconds in ''|*[!0-9]*|0) echo 'MLF_ASYNC_COMMAND_TIMEOUT must be positive.' >&2; exit 2 ;; esac
started=$SECONDS
command_pid= watchdog_pid=
labels=()
fail() { echo "Async package: $*; evidence: $work" >&2; exit 1; }
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
 case $label in *.native|protocol) if [ "$limit" -gt 30 ]; then limit=30; fi ;; esac
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
record_inputs() {
 local base=$1 destination=$2 file
 printf '{}\n' > "$destination"
 while IFS= read -r file; do
  jq --arg path "$file" --arg hash "$(sha256 "$base/$file")" '. + {($path):$hash}' "$destination" > "$destination.tmp"
  mv "$destination.tmp" "$destination"
 done < <(cd "$base"; find libraries/mlf-foundation libraries/mlf-async runtime tests/async-package tools/release/test-async-package.sh -type f | LC_ALL=C sort)
}
record_inputs "$root" "$work/inputs.json"
cp -R "$root/libraries/mlf-foundation" "$root/libraries/mlf-async" "$source/libraries/"
cp -R "$root/runtime" "$source/runtime"
cp -R "$root/tests/async-package" "$source/tests/async-package"
cp "$root/tools/release/test-async-package.sh" "$source/tools/release/"
record_inputs "$source" "$work/snapshot.json"
cmp "$work/inputs.json" "$work/snapshot.json" || fail 'source changed while copying'
compiler_hash=$(sha256 "$compiler")
manager_hash=$(sha256 "$manager")
runner_hash=$(sha256 "$runner")
clang_hash=$(sha256 "$clang")
run protocol "$runner" --protocol-version || fail 'runner protocol query failed'
test "$(cat "$work/protocol.stdout")" = 1 && test ! -s "$work/protocol.stderr" || fail 'runner protocol mismatch'
args=(--manifest "$source/tests/async-package/mlf-package.json" --compiler "$compiler" --runtime "$source/runtime/mlf_runtime.c" --clang "$clang" --timeout "$timeout_seconds" --jobs 1 --build-dir "$work/build" --cache-dir "$work/cache")
if [ -n "${MLF_GC_PREFIX:-}" ]; then args+=(--gc-prefix "$MLF_GC_PREFIX"); fi
for phase in initial cached; do
 run "$phase.build" "$manager" "${args[@]}" build --target answer || fail "$phase package build failed"
 cp "$work/build/build-report.json" "$work/$phase.build-report.json"
 jq -e '.complete == true and (.builds|length > 0)' "$work/$phase.build-report.json" >/dev/null || fail "$phase incomplete build report"
 if [ "$phase" = initial ]; then
  jq -e 'all(.builds[]; .cached == false) and any(.builds[]; .kind | startswith("crate mlf-async/")) and any(.commands[]; .argv | index("--compile-crate") != null)' "$work/$phase.build-report.json" >/dev/null || fail 'initial build did not compile fresh checked library crates'
  binary_hash=$(sha256 "$work/build/bin/answer")
 else
  jq -e 'all(.builds[]; .cached == true)' "$work/$phase.build-report.json" >/dev/null || fail 'unchanged build missed cache'
  test "$(sha256 "$work/build/bin/answer")" = "$binary_hash" || fail 'cache replay changed binary'
 fi
 run "$phase.native" "$work/build/bin/answer" || fail "$phase native consumer failed"
 test ! -s "$work/$phase.native.stderr" || fail "$phase native consumer emitted diagnostics"
 cmp "$source/tests/async-package/suite.stdout" "$work/$phase.native.stdout" || fail "$phase consumer differs from literal oracle"
 echo "PASS packaged async consumer: $phase native execution"
done
async_key=$(jq -er '.builds[] | select(.kind | startswith("crate mlf-async/")) | .key' "$work/initial.build-report.json")
interface="$work/cache/$async_key/unit.mlfci"
test -s "$interface" || fail 'compiled async interface missing'
for kind in opaque-fiber opaque-task opaque-internal-fiber opaque-internal-task opaque-handle opaque-scope mixed-fiber; do
 status=0
 run "$kind" "$manager" "${args[@]}" build --target "$kind" || status=$?
 test "$status" -eq 1 || fail "$kind expected rejection 1, got $status"
 test ! -e "$work/build/bin/$kind" || fail "$kind published a rejected executable"
 cp "$work/build/build-report.json" "$work/$kind.build-report.json"
 case $kind in
  mixed-fiber)
   grep -Ei 'type constructor mismatch|cannot unify|incompatible' "$work/$kind.stderr" >/dev/null || fail "$kind unrelated rejection"
   grep -F 'String' "$work/$kind.stderr" >/dev/null || fail "$kind lacks String diagnostic"
   grep -F 'Int' "$work/$kind.stderr" >/dev/null || fail "$kind lacks Int diagnostic" ;;
  *)
   case $kind in *fiber) constructor=Fiber ;; *task) constructor=Task ;; *handle) constructor=ProcessHandle ;; *scope) constructor=ProcessScope ;; esac
   grep -F "$constructor" "$work/$kind.stderr" >/dev/null || fail "$kind unrelated rejection"
   grep -Ei 'unknown|unbound|not (in scope|exported)|undefined|unresolved' "$work/$kind.stderr" >/dev/null || fail "$kind missing inaccessible-constructor diagnostic" ;;
 esac
 # Require the rejection to have consumed the already-compiled async library.
 jq -e '.complete == false and any(.builds[]; (.kind | startswith("crate mlf-async/")) and .cached == true)' "$work/$kind.build-report.json" >/dev/null || fail "$kind did not validate cached package interface"
 echo "PASS packaged $kind rejection"
done
record_inputs "$source" "$work/snapshot.final.json"
record_inputs "$root" "$work/inputs.final.json"
cmp "$work/snapshot.json" "$work/snapshot.final.json" || fail 'frozen inputs changed'
cmp "$work/inputs.json" "$work/inputs.final.json" || fail 'checkout inputs changed'
test "$(sha256 "$compiler")" = "$compiler_hash" || fail 'compiler changed'
test "$(sha256 "$manager")" = "$manager_hash" || fail 'manager changed'
test "$(sha256 "$runner")" = "$runner_hash" || fail 'runner changed'
test "$(sha256 "$clang")" = "$clang_hash" || fail 'clang changed'
test "${#labels[@]}" -eq 12 || fail 'command coverage changed'
printf '{}\n' > "$work/observations.json"
for label in "${labels[@]}"; do
 for suffix in stdout stderr status; do
  file="$work/$label.$suffix"
  jq --arg path "$(basename "$file")" --arg hash "$(sha256 "$file")" '. + {($path):$hash}' "$work/observations.json" > "$work/observations.tmp"
  mv "$work/observations.tmp" "$work/observations.json"
 done
done
printf '{}\n' > "$work/reports.json"
for file in "$work/"*.build-report.json; do
 jq --arg path "$(basename "$file")" --arg hash "$(sha256 "$file")" '. + {($path):$hash}' "$work/reports.json" > "$work/reports.tmp"
 mv "$work/reports.tmp" "$work/reports.json"
done
jq -n --arg work "$work" --arg compiler_sha256 "$compiler_hash" --arg manager_sha256 "$manager_hash" \
 --arg runner_sha256 "$runner_hash" --arg clang_sha256 "$clang_hash" --arg native_sha256 "$binary_hash" \
 --arg async_interface_sha256 "$(sha256 "$interface")" --arg async_crate_key "$async_key" \
 --argjson seconds "$((SECONDS-started))" --argjson timeout_seconds "$timeout_seconds" \
 --slurpfile inputs "$work/inputs.json" --slurpfile observations "$work/observations.json" --slurpfile reports "$work/reports.json" \
 '{complete:true,backend:"llvm",native_executions:2,cache_replay:true,opaque_rejections:6,type_rejections:1,commands:12,
 work:$work,compiler_sha256:$compiler_sha256,manager_sha256:$manager_sha256,runner_sha256:$runner_sha256,
 clang_sha256:$clang_sha256,native_sha256:$native_sha256,async_interface_sha256:$async_interface_sha256,
 async_crate_key:$async_crate_key,seconds:$seconds,timeout_seconds:$timeout_seconds,
 inputs:$inputs[0],observations:$observations[0],reports:$reports[0]}' > "$output/result.tmp"
mv "$output/result.tmp" "$output/result.json"
echo 'Async package gate passed: native checked-crate consumer, exact cache replay, 6 opaque and 1 typed rejections.'
