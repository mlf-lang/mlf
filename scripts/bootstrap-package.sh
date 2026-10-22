#!/bin/sh
# Build the MLF package manager from an MLF compiler seed. No package logic
# lives here: this only invokes the compiler and native linker once.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
build=${MLF_PACKAGE_BOOTSTRAP_DIR:-"$root/.mlf-build/package-manager"}
mkdir -p "$build"
compiler=${MLF_COMPILER:-emlf}
cc=${CC:-clang}
if [ -n "${MLF_GC_PREFIX:-}" ]; then
  gc_cflags="-I$MLF_GC_PREFIX/include"
  gc_libs="$MLF_GC_PREFIX/lib/libgc.a"
else
  gc_cflags=$(pkg-config --cflags bdw-gc)
  gc_libs=$(pkg-config --libs bdw-gc)
fi
"$compiler" -i bootstrap -i package --emit-llvm-gc package/Main.emlf > "$build/mlfpkg.ll.new"
mv "$build/mlfpkg.ll.new" "$build/mlfpkg.ll"
# pkg-config supplies compiler flags; the ordinary manifest-driven build uses
# the MLF argv parser and supports spaces in all explicit tool/source paths.
# This seed-only launcher requires a GC prefix without whitespace.
# shellcheck disable=SC2046,SC2086
"$cc" -O2 -std=c11 \
  $(pkg-config --cflags gmp) $gc_cflags -c runtime/mlf_runtime.c -o "$build/runtime.o"
stack=""
if [ "$(uname -s)" = Darwin ]; then stack="-Wl,-stack_size,0x10000000"; fi
# shellcheck disable=SC2046,SC2086
"$cc" -O2 -Wno-override-module "$build/mlfpkg.ll" "$build/runtime.o" \
  $(pkg-config --libs gmp) $gc_libs -lm $stack -o "$build/mlfpkg.new"
mv "$build/mlfpkg.new" "$build/mlfpkg"
printf '%s\n' "$build/mlfpkg"
