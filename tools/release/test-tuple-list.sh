#!/usr/bin/env bash
# Exercise the same sugar source through the selected compiler's interpreter
# and native backend. Use a compiler built from the checkout being validated.
set -euo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$root"
compiler=${1:-${MLF_COMPILER:?select a native compiler built from this checkout}}
build=${2:-"$root/.mlf-build/tuple-list-runtime"}
mkdir -p "$build"
source_file="$root/tests/fixtures/tuple-list-runtime.emlf"
expected="$root/tests/fixtures/tuple-list-runtime.stdout"
"$compiler" --run "$source_file" > "$build/interpreter.stdout"
cmp "$expected" "$build/interpreter.stdout"
"$compiler" --emit-llvm-gc "$source_file" > "$build/program.ll"
read -r -a gmp_cflags <<< "$(pkg-config --cflags gmp)"
read -r -a gmp_libs <<< "$(pkg-config --libs gmp)"
if [ -n "${MLF_GC_PREFIX:-}" ]; then
  gc_cflags=("-I$MLF_GC_PREFIX/include")
  gc_libs=("$MLF_GC_PREFIX/lib/libgc.a")
else
  read -r -a gc_cflags <<< "$(pkg-config --cflags bdw-gc)"
  read -r -a gc_libs <<< "$(pkg-config --libs bdw-gc)"
fi
stack=()
if [ "$(uname -s)" = Darwin ]; then stack=(-Wl,-stack_size,0x10000000); fi
"${CC:-clang}" -O2 -std=c11 ${gmp_cflags[@]+"${gmp_cflags[@]}"} ${gc_cflags[@]+"${gc_cflags[@]}"} \
  -c "$root/runtime/mlf_runtime.c" -o "$build/runtime.o"
"${CC:-clang}" -O2 -Wno-override-module "$build/program.ll" "$build/runtime.o" \
  ${gmp_libs[@]+"${gmp_libs[@]}"} ${gc_libs[@]+"${gc_libs[@]}"} -lm ${stack[@]+"${stack[@]}"} -o "$build/program"
"$build/program" > "$build/native.stdout"
cmp "$expected" "$build/native.stdout"
printf '%s\n' 'Tuple/list interpreter and native fixture passed (9 results each).'
