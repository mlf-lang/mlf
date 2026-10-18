#!/bin/bash
set -euo pipefail
# Usage: build.sh SEED SOURCE_ROOT OUTPUT_DIRECTORY
seed=$1
source_root=$2
out=$3
root=$(cd "$(dirname "$0")/../.." && pwd)
if [[ -e "$out/profile" || -e "$out/profile.ll" ]]; then
  echo 'Use a fresh profile build directory.' >&2
  exit 1
fi
mkdir -p "$out"
gc=${MLF_GC_PREFIX:-$root/dist-newstyle/bootstrap-deps/bdwgc-8.2.12-install}
stack=()
if [[ $(uname -s) == Darwin ]]; then stack=("-Wl,-stack_size,0x10000000"); fi
"$seed" -i "$source_root/bootstrap" -i "$root/tools/profile" --emit-llvm-gc "$root/tools/profile/Main.emlf" > "$out/profile.ll"
# shellcheck disable=SC2046
clang -O2 -std=c11 -DMLF_USE_BDWGC -DMLF_COMPACT_BDWGC -DMLF_GC_THRESHOLD=1048576 -I"$source_root/runtime" -I"$gc/include" $(pkg-config --cflags gmp) -c "$root/tools/profile/runtime.c" -o "$out/runtime.o"
# shellcheck disable=SC2046
clang -O2 -Wno-override-module "$out/profile.ll" "$out/runtime.o" $(pkg-config --libs gmp) "$gc/lib/libgc.a" -lm "${stack[@]}" -o "$out/profile"
