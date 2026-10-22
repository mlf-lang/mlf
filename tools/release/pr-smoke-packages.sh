#!/usr/bin/env bash
# Exercise the candidate package manager without building a compiler-test runner.
set -euo pipefail
if [ "$#" -ne 3 ]; then
  printf 'Usage: %s COMPILER MANAGER OUTPUT_DIR\n' "$0" >&2
  exit 2
fi
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
mkdir -p -- "$3"
output=$(cd -- "$3" && pwd)
# A failed rerun must never leave the preceding successful receipt in place.
printf '{"complete":false}\n' > "$output/result.json"
compiler=$(cd -- "$(dirname -- "$1")" && printf '%s/%s\n' "$PWD" "$(basename -- "$1")")
manager=$(cd -- "$(dirname -- "$2")" && printf '%s/%s\n' "$PWD" "$(basename -- "$2")")
test -x "$compiler" && test -x "$manager"
cd -- "$root"
sha256() { shasum -a 256 "$1" | awk '{print $1}'; }
compiler_sha256=$(sha256 "$compiler")
manager_sha256=$(sha256 "$manager")
build_runner=${MLF_BUILD_RUNNER:-"$(dirname -- "$manager")/mlf-build-runner"}
build_runner=$(cd -- "$(dirname -- "$build_runner")" && printf '%s/%s\n' "$PWD" "$(basename -- "$build_runner")")
test -x "$build_runner"
test "$("$build_runner" --protocol-version)" = 1
build_runner_sha256=$(sha256 "$build_runner")
export MLF_BUILD_RUNNER="$build_runner"
runtime_sha256=$(sha256 "$root/runtime/mlf_runtime.c")
started=$SECONDS

# Every invocation starts with a private empty cache, including local reruns.
# Only generated files inside this freshly created directory are modified.
work=$(mktemp -d "$output/work.XXXXXXXX")
app="$work/app"
build="$work/build"
cp -R "$root/examples/packages" "$app"
rm -rf -- "$app/.mlf-build"
for stage in initial cached changed; do
  for suffix in log log.stderr build-report.json expected interpreter.stdout interpreter.stderr llvm.stdout llvm.stderr; do
    rm -f -- "$output/$stage.$suffix"
  done
done

run_stage() {
  local stage=$1 expected=$2 status=0 backend
  jq -e --arg expected "$expected" '.tests.hello.stdout == $expected' "$app/mlf-package.json" >/dev/null
  printf '%s' "$expected" > "$output/$stage.expected"
  "$manager" --manifest "$app/mlf-package.json" --compiler "$compiler" \
    --runtime "$root/runtime/mlf_runtime.c" --build-dir "$build" \
    --jobs 2 --timeout 120 test --target hello > "$output/$stage.log" 2> "$output/$stage.log.stderr" || status=$?
  if [ -f "$build/build-report.json" ]; then
    cp "$build/build-report.json" "$output/$stage.build-report.json"
  fi
  if [ "$status" -ne 0 ]; then
    cat "$output/$stage.log" "$output/$stage.log.stderr" >&2
    return "$status"
  fi
  jq -e --arg compiler "$compiler_sha256" --arg manager "$manager_sha256" --arg runner "$build_runner_sha256" '
    .format == 1 and .complete == true and .implementation == "MLF" and
    .toolchain.compiler.sha256 == $compiler and .toolchain.manager.sha256 == $manager and
    (.scheduler | type == "array" and length == 1) and
    .scheduler[0].helper.sha256 == $runner and
    (.scheduler_results | type == "array" and length == 1) and
    (.scheduler_results[0] | .complete == true and .exit_code == 0 and .jobs == 2 and
      .maximum_parallel_jobs > 0 and .maximum_parallel_jobs <= 2 and
      all(.tasks[]; .state == "succeeded" and .exit_code == 0)) and
    .scheduler[0].invocation_id == .scheduler_results[0].invocation_id and
    .scheduler[0].plan_digest == .scheduler_results[0].plan_digest and
    (.builds | type == "array" and length > 0) and
    (.tests | type == "array" and length == 1 and
      all(.[]; .name == "hello" and .passed == true and .backends == ["interpreter","llvm"]))
  ' "$output/$stage.build-report.json" >/dev/null
  for backend in interpreter llvm; do
    cp "$build/tests/hello/$backend.stdout" "$output/$stage.$backend.stdout"
    cp "$build/tests/hello/$backend.stderr" "$output/$stage.$backend.stderr"
    cmp "$output/$stage.expected" "$output/$stage.$backend.stdout"
    test ! -s "$output/$stage.$backend.stderr"
  done
}

run_stage initial $'Hello, local packages!\n'
jq -e 'all(.builds[]; .cached == false)' "$output/initial.build-report.json" >/dev/null
run_stage cached $'Hello, local packages!\n'
jq -e 'all(.builds[]; .cached == true)' "$output/cached.build-report.json" >/dev/null

source="$app/message/Message.emlf"
test "$(grep -Fxc 'render (Message text) = text' "$source")" -eq 1
sed 's/^render (Message text) = text$/render (Message text) = text ++ " updated"/' \
  "$source" > "$source.new"
mv "$source.new" "$source"
jq '.tests.hello.stdout = "Hello, local packages! updated\n"' \
  "$app/mlf-package.json" > "$app/mlf-package.json.new"
mv "$app/mlf-package.json.new" "$app/mlf-package.json"
run_stage changed $'Hello, local packages! updated\n'
jq -e '
  [.builds[] | select(.kind == "executable local-packages-example:test-hello")] as $targets |
  ($targets | length) == 1 and all($targets[]; .cached == false) and
  # Test stdout also affects the executable key. These crate keys provide
  # independent evidence that the transitive implementation edit invalidated it.
  ([.builds[] | select(.kind == "crate message/0.1.0/library" or
    .kind == "crate greeting/0.1.0/library" or
    .kind == "crate local-packages-example/0.1.0/target-test-hello")] as $rows |
    ($rows | map(.kind) | sort) == ["crate greeting/0.1.0/library",
      "crate local-packages-example/0.1.0/target-test-hello", "crate message/0.1.0/library"] and
    all($rows[]; .cached == false))
' "$output/changed.build-report.json" >/dev/null

test "$(sha256 "$compiler")" = "$compiler_sha256"
test "$(sha256 "$manager")" = "$manager_sha256"
test "$(sha256 "$build_runner")" = "$build_runner_sha256"
test "$(sha256 "$root/runtime/mlf_runtime.c")" = "$runtime_sha256"
stages='{}'
for stage in initial cached changed; do
  stages=$(jq --arg stage "$stage" \
    --arg report "$(sha256 "$output/$stage.build-report.json")" \
    --arg log "$(sha256 "$output/$stage.log")" \
    --arg stderr "$(sha256 "$output/$stage.log.stderr")" \
    --arg stdout "$(sha256 "$output/$stage.expected")" \
    '. + {($stage): {build_report_sha256:$report,log_sha256:$log,stderr_sha256:$stderr,stdout_sha256:$stdout}}' <<< "$stages")
done
jq -n --arg compiler "$compiler" --arg compiler_sha256 "$compiler_sha256" \
  --arg manager "$manager" --arg manager_sha256 "$manager_sha256" \
  --arg build_runner "$build_runner" --arg build_runner_sha256 "$build_runner_sha256" \
  --arg runtime_sha256 "$runtime_sha256" --arg helper_sha256 "$(sha256 "$root/tools/release/pr-smoke-packages.sh")" \
  --arg work "$work" --argjson elapsed "$((SECONDS - started))" --argjson stages "$stages" \
  '{complete:true,cases:3,backends:["interpreter","llvm"],
    compiler:$compiler,compiler_sha256:$compiler_sha256,manager:$manager,manager_sha256:$manager_sha256,
    build_runner:$build_runner,build_runner_sha256:$build_runner_sha256,build_runner_protocol:1,jobs:2,
    runtime_sha256:$runtime_sha256,helper_sha256:$helper_sha256,
    work_directory:$work,total_seconds:$elapsed,stages:$stages}' > "$output/result.json.new"
mv "$output/result.json.new" "$output/result.json"
printf '3 PR smoke package checks on interpreter and LLVM; 0 failures\n'
