#!/bin/bash
set -euo pipefail
# Usage: build-names.sh SEED SOURCE_ROOT PROFILE_DIRECTORY
# Run after build.sh, with the same source tree and Main/Force driver.
seed=$1
source_root=$2
out=$3
root=$(cd "$(dirname "$0")/../.." && pwd)
gc=${MLF_GC_PREFIX:-$root/dist-newstyle/bootstrap-deps/bdwgc-8.2.12-install}
stack=()
if [[ $(uname -s) == Darwin ]]; then stack=("-Wl,-stack_size,0x10000000"); fi
mkdir -p "$out/names"
# Preserve display hints without changing identities or optimizer decisions.
# The generated module is diagnostic-only; production optimization is unchanged.
sed \
  -e 's/module Bootstrap.LLVM.Optimize where/module NamedOptimize where/' \
  -e '/^freshName = /a\
freshLike : XName -> Fresh XName\
freshLike (XName old hint) = Fresh (\\seed -> Pair (XName seed hint) (seed + 1))\
' \
  -e 's/renamed <- freshName/renamed <- freshLike n/g' \
  -e 's/names <- traverseFresh (\\ignored -> freshName) ds/names <- traverseFresh (\\entry -> case entry of Pair n body -> freshLike n) ds/' \
  -e 's/names <- traverseFresh (\\ignored -> freshName) (X.patternNames pattern)/names <- traverseFresh freshLike (X.patternNames pattern)/' \
  -e 's/specialized <- freshName/specialized <- freshLike name/' \
  "$source_root/bootstrap/Bootstrap/LLVM/Optimize.emlf" > "$out/names/NamedOptimize.emlf"
"$seed" -i "$source_root/bootstrap" -i "$out/names" --emit-llvm-gc "$root/tools/profile/Workers.emlf" > "$out/names/workers.ll"
# shellcheck disable=SC2046
clang -O2 -Wno-override-module "$out/names/workers.ll" "$out/runtime.o" $(pkg-config --libs gmp) "$gc/lib/libgc.a" -lm "${stack[@]}" -o "$out/names/workers"
"$out/names/workers" "$root/tools/profile/Main.emlf" "$source_root/bootstrap" > "$out/names/identities.tsv"
"$seed" -i "$source_root/bootstrap" --emit-llvm-gc "$root/tools/profile/ModuleNames.emlf" > "$out/names/modules.ll"
# shellcheck disable=SC2046
clang -O2 -Wno-override-module "$out/names/modules.ll" "$out/runtime.o" $(pkg-config --libs gmp) "$gc/lib/libgc.a" -lm "${stack[@]}" -o "$out/names/modules"
"$out/names/modules" "$root/tools/profile/Main.emlf" "$source_root/bootstrap" > "$out/names/modules.tsv"
awk 'NR == FNR { names[$1] = $2; next }
  { hint = ($2 in names) ? names[$2] : $2; gsub(/[^A-Za-z0-9_.]/, "_", hint); print $1 "\t" hint }' \
  "$out/names/modules.tsv" "$out/names/identities.tsv" > "$out/workers.tsv"
awk -f "$root/tools/profile/name-workers.awk" "$out/workers.tsv" "$out/profile.ll" > "$out/named.ll"
# shellcheck disable=SC2046
clang -O2 -Wno-override-module "$out/named.ll" "$out/runtime.o" $(pkg-config --libs gmp) "$gc/lib/libgc.a" -lm "${stack[@]}" -o "$out/named-profile"
