#!/usr/bin/env bash
# Compile one POSIX probe family and run its original bounded scenarios.
set -euo pipefail
test "$#" -eq 2 || { echo 'Usage: native-probes.sh build-tools|async-runtime OUTPUT' >&2; exit 2; }
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
group=$1
mkdir -p "$2"
output=$(cd -- "$2" && pwd)
cd "$root"
clang=${CC:-clang}
flags=(-O2 -std=c11 -Wall -Wextra -Werror)
shasum -a 256 "$(command -v "$clang")" > "$output/binaries.sha256"

compile() {
  local destination="$output/$1"
  shift
  "$clang" "${flags[@]}" "$@" -o "$destination"
  shasum -a 256 "$destination" >> "$output/binaries.sha256"
}

case "$group" in
  build-tools)
    compile build-runner-fixture tests/native/build_runner_fixture.c
    case ${MLF_TEST_EXACT:-} in
      ''|native-build-runner/*)
        compile mlf-build-runner runtime/mlf_build_runner.c
        compile build-runner-tests tests/native/build_runner_tests.c
        "$output/build-runner-tests" "$output/mlf-build-runner" "$output/build-runner-fixture" "$output/evidence" 2>&1 | tee "$output/build-runner.log"
        if [ -z "${MLF_TEST_EXACT:-}" ]; then grep -q '22 native build runner tests passed' "$output/build-runner.log"; fi
        ;;
    esac
    case ${MLF_TEST_EXACT:-} in
      ''|native-process-supervisor/*)
        compile process-supervisor-tests tests/native/process_supervisor_tests.c runtime/mlf_process_supervisor.c
        "$output/process-supervisor-tests" "$output/build-runner-fixture" "$output/process-evidence" 2>&1 | tee "$output/process-supervisor.log"
        grep -q 'native process supervisor tests passed' "$output/process-supervisor.log"
        ;;
    esac
    ;;
  async-runtime)
    read -r -a cflags <<< "$(pkg-config --cflags bdw-gc gmp)"
    read -r -a libs <<< "$(pkg-config --libs bdw-gc gmp)"
    compile runtime.o "${cflags[@]}" -c runtime/mlf_runtime.c
    for name in completion_cell_tests async_completion_primitives; do
      case "$name" in
        completion_cell_tests) prefix=native-completion-cells; message=representation ;;
        async_completion_primitives) prefix=native-completion-primitives; message=primitives ;;
      esac
      case ${MLF_TEST_EXACT:-} in ''|"$prefix/"*) ;; *) continue ;; esac
      compile "$name" "${cflags[@]}" "tests/native/$name.c" "$output/runtime.o" "${libs[@]}" -lm
      "$output/$name" 2>&1 | tee "$output/$name.log"
      grep -q "Native completion $message: .* checks, .* callbacks passed" "$output/$name.log"
    done
    ;;
  *) exit 2 ;;
esac
