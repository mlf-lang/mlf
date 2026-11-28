#!/usr/bin/env bash
# Exercise the same sugar source through the selected compiler's interpreter
# and native backend. Use a compiler built from the checkout being validated.
set -euo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$root"
. "$root/tools/testing/native-events.sh"
trap 'mlf_case_cleanup "$?"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
compiler=${1:-${MLF_COMPILER:?select a native compiler built from this checkout}}
compiler=$(command -v -- "$compiler")
build=${2:-"$root/.mlf-build/tuple-list-runtime"}
mkdir -p "$build"
source_file="$root/tests/fixtures/tuple-list-runtime.emlf"
expected="$root/tests/fixtures/tuple-list-runtime.stdout"
service=${MLF_TEST_COMPILATION_SERVICE:-"$(dirname -- "$compiler")/compiler-tests"}
cache=${MLF_TEST_COMPILATION_CACHE:-"$root/.mlf-build/cache"}
prepare=("$service" prepare-fixture --compiler "$compiler" --build-dir "$build"
  --cache-dir "$cache" --clang "${CC:-clang}")
if mlf_case_selected tuple-list-native/llvm; then
  "${prepare[@]}" checked "$source_file"
else
  # An interpreter-only selection needs no native tools and has no repeated
  # compilation to share with another backend.
  "$compiler" "$source_file" > "$build/program.xmlf"
fi
if mlf_case_selected tuple-list-native/interpreter; then
  mlf_case_start tuple-list-native/interpreter
  "$compiler" --run-xmlf "$build/program.xmlf" > "$build/interpreter.stdout"
  cmp "$expected" "$build/interpreter.stdout"
  mlf_case_result pass 0
fi
if mlf_case_selected tuple-list-native/llvm; then
  mlf_case_start tuple-list-native/llvm
  "${prepare[@]}" native "$source_file"
  "$build/program" > "$build/native.stdout"
  cmp "$expected" "$build/native.stdout"
  mlf_case_result pass 0
fi
if [ -z "${MLF_TEST_EXACT:-}" ]; then
  printf '%s\n' 'Tuple/list interpreter and native fixture passed (9 results each).'
fi
