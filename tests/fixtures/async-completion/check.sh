#!/usr/bin/env bash
# Actual opaque primitive gate: inference/checker and interpreted/native effects.
# A seed shim, timed-out process, stale receipt or changed input never passes.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
fixtures="$root/tests/fixtures/async-completion"
compiler=$(command -v "${EMLF:-emlf}")
compiler=$(cd -- "$(dirname -- "$compiler")" && pwd)/$(basename -- "$compiler")
cc=$(command -v "${CC:-clang}")
output=${MLF_ASYNC_COMPLETION_BUILD_DIR:-"$root/.mlf-build/async-completion-gate"}
mkdir -p "$output"
output=$(cd -- "$output" && pwd)
printf '{"complete":false}\n' > "$output/result.json"
work=$(mktemp -d "$output/run.XXXXXXXX")
command -v jq >/dev/null
command -v pkg-config >/dev/null
cd -- "$root"
case $(uname -s) in Linux) ulimit -s unlimited ;; Darwin) ;; *) echo 'Completion shell parity supports Linux and macOS.' >&2; exit 2 ;; esac
timeout_seconds=${MLF_ASYNC_COMMAND_TIMEOUT:-600}
case $timeout_seconds in ''|*[!0-9]*|0) echo 'MLF_ASYNC_COMMAND_TIMEOUT must be positive.' >&2; exit 2 ;; esac
export GC_FREE_SPACE_DIVISOR=${GC_FREE_SPACE_DIVISOR:-8}
export GC_INITIAL_HEAP_SIZE=${GC_INITIAL_HEAP_SIZE:-1048576}
started=$SECONDS
command_pid= watchdog_pid=
labels=()
fail() { echo "Typed completion: $*; evidence: $work" >&2; exit 1; }
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
  case $label in *.interpreter|*.target-interpreter|*.native|*.execute|capability) if [ "$limit" -gt 45 ]; then limit=45; fi ;; esac
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
success() {
  local label=$1
  run "$@" || fail "$label failed"
  test ! -s "$work/$label.stderr" || fail "$label emitted diagnostics"
}
record_inputs() {
  local destination=$1 file
  printf '{}\n' > "$destination"
  while IFS= read -r file; do
    jq --arg path "${file#"$root"/}" --arg hash "$(sha256 "$file")" '. + {($path):$hash}' "$destination" > "$destination.tmp"
    mv "$destination.tmp" "$destination"
  done < <({ find "$fixtures" "$root/runtime" -type f; printf '%s\n' \
    "$root/tests/native/completion_cell_tests.c" "$root/tests/native/async_completion_primitives.c" \
    "$root/libraries/mlf-foundation/Bootstrap/Types.hs" \
    "$root/libraries/mlf-language-core/Bootstrap/Data.hs" "$root/libraries/mlf-language-core/Bootstrap/Primitive.hs" \
    "$root/libraries/mlf-frontend/Bootstrap/Module.hs" \
    "$root/libraries/mlf-interpreter/Bootstrap/Runtime.hs" "$root/libraries/mlf-interpreter/Bootstrap/ProcessHost.hs" \
    "$root/libraries/mlf-llvm/Bootstrap/LLVM.hs"; } | LC_ALL=C sort)
}
record_inputs "$work/inputs.json"
compiler_hash=$(sha256 "$compiler")
cc_hash=$(sha256 "$cc")
printf 'IO Unit\n' > "$work/io-unit.type"
success capability "$compiler" --run --expr 'do { reply <- processSupervisor "MLF-PROCESS-1\0version\0"; printInt (stringCodeAt reply 2) }'
test "$(cat "$work/capability.stdout")" = 49 || fail 'real stage-2 host bridge required'
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
success runtime "$cc" -O2 -std=c11 -Wall -Wextra -Werror "${cflags[@]}" -c "$root/runtime/mlf_runtime.c" -o "$work/runtime.o"
for native in completion_cell_tests async_completion_primitives; do
  success "$native.link" "$cc" -O2 -std=c11 -Wall -Wextra -Werror "${cflags[@]}" "$root/tests/native/$native.c" "$work/runtime.o" "${libs[@]}" -o "$work/$native"
  success "$native.execute" "$work/$native"
  cat "$work/$native.execute.stdout"
done
runtime=0
for source in "$fixtures"/runtime/*.emlf; do
  name=$(basename "$source" .emlf)
  success "$name.compile" "$compiler" -i "$fixtures" "$source"
  success "$name.check" "$compiler" --check "$work/$name.compile.stdout"
  cmp "$work/io-unit.type" "$work/$name.check.stdout" || fail "$name is not IO Unit"
  success "$name.interpreter" "$compiler" -i "$fixtures" --run "$source"
  success "$name.target-interpreter" "$compiler" --run-xmlf "$work/$name.compile.stdout"
  cmp "$fixtures/runtime/$name.expected" "$work/$name.interpreter.stdout" || fail "$name source interpreter differs"
  cmp "$fixtures/runtime/$name.expected" "$work/$name.target-interpreter.stdout" || fail "$name target interpreter differs"
  success "$name.emit" "$compiler" --xmlf-to-llvm-io-gc "$work/$name.compile.stdout"
  grep -F 'mlf_require_async_completion_v2_abi' "$work/$name.emit.stdout" >/dev/null || fail "$name lacks current ABI guard"
  success "$name.link" "$cc" -O2 -Wno-override-module -x ir "$work/$name.emit.stdout" -x none "$work/runtime.o" "${libs[@]}" -o "$work/$name.native"
  success "$name.native" "$work/$name.native"
  cmp "$fixtures/runtime/$name.expected" "$work/$name.native.stdout" || fail "$name native differs"
  runtime=$((runtime + 1))
  echo "PASS $name source/target interpreter and native"
done
negative=0
for source in "$fixtures"/negative/*.emlf; do
  name=$(basename "$source" .emlf)
  label="negative-$name"
  status=0
  run "$label" "$compiler" -i "$fixtures" "$source" || status=$?
  test "$status" -eq 1 || fail "$name expected source rejection 1, got $status"
  test ! -s "$work/$label.stdout" || fail "$name produced target output"
  case "$name" in
    forge-*) expected='(cannot redefine|primitive type)' ;;
    wrong-kind) expected='(kind|arity)' ;;
    generalize-allocated) expected='^Inference: cannot raise a protected type variable' ;;
    *) expected='^Inference:' ;;
  esac
  grep -Eq "$expected" "$work/$label.stderr" || fail "$name wrong rejection phase"
  negative=$((negative + 1))
done
targets=0
for source in "$fixtures"/target-negative/*.xmlf; do
  name=$(basename "$source" .xmlf)
  for mode in check run-xmlf xmlf-to-llvm; do
    label="target-$name-$mode"
    status=0
    run "$label" "$compiler" "--$mode" "$source" || status=$?
    test "$status" -eq 1 || fail "$mode $name expected target rejection 1, got $status"
    test ! -s "$work/$label.stdout" || fail "$name produced effects/output"
    grep -Eiq '(type|kind|primitive|constructor|argument)' "$work/$label.stderr" || fail "$name unrelated target rejection"
    if grep -Eiq '(expected .* at|parse error|unknown primitive)' "$work/$label.stderr"; then fail "$name failed before checking"; fi
  done
  targets=$((targets + 1))
done
record_inputs "$work/inputs.final.json"
cmp "$work/inputs.json" "$work/inputs.final.json" || fail 'inputs changed during run'
test "$(sha256 "$compiler")" = "$compiler_hash" || fail 'compiler changed during run'
test "$(sha256 "$cc")" = "$cc_hash" || fail 'C compiler changed during run'
printf '{}\n' > "$work/observations.json"
for label in "${labels[@]}"; do
  for suffix in stdout stderr status; do
    file="$work/$label.$suffix"
    jq --arg path "$(basename "$file")" --arg hash "$(sha256 "$file")" '. + {($path):$hash}' "$work/observations.json" > "$work/observations.tmp"
    mv "$work/observations.tmp" "$work/observations.json"
  done
done
jq -n --arg compiler_sha256 "$compiler_hash" --arg clang_sha256 "$cc_hash" \
  --arg runtime_object_sha256 "$(sha256 "$work/runtime.o")" --arg work "$work" \
  --argjson source_native_fixtures "$runtime" --argjson source_rejections "$negative" --argjson target_rejections "$targets" \
  --argjson commands "${#labels[@]}" --argjson seconds "$((SECONDS - started))" --argjson timeout_seconds "$timeout_seconds" \
  --slurpfile inputs "$work/inputs.json" --slurpfile observations "$work/observations.json" \
  '{complete:true,source_native_fixtures:$source_native_fixtures,source_rejections:$source_rejections,
    target_rejections:$target_rejections,target_rejection_entrypoints:3,native_proofs:2,
    backends:["source-interpreter","target-interpreter","llvm"],commands:$commands,
    compiler_sha256:$compiler_sha256,clang_sha256:$clang_sha256,runtime_object_sha256:$runtime_object_sha256,
    work:$work,seconds:$seconds,timeout_seconds:$timeout_seconds,inputs:$inputs[0],observations:$observations[0]}' > "$output/result.tmp"
mv "$output/result.tmp" "$output/result.json"
printf 'Typed completion primitives: %s source/native parity fixtures, %s source negatives, %s independent target negatives passed.\n' "$runtime" "$negative" "$targets" | tee "$output/result.txt"
