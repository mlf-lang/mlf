#!/bin/sh
# Build the MLF package manager from an MLF compiler seed. No package logic
# lives here: this only invokes the compiler and native linker once.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
build=${MLF_PACKAGE_BOOTSTRAP_DIR:-"$root/.mlf-build/package-manager"}
mkdir -p "$build"
compiler=${MLF_COMPILER:-emlf}
entry=package/Main.emlf
if [ -f "$root/shared-sources.json" ]; then
  identity=$("$compiler" --implementation-identity 2>/dev/null) || identity=
  case "$identity" in
    'MLF/shared-haskell-v1 native-MLF'|'MLF/shared-haskell-v1 GHC') ;;
    *) printf '%s\n' 'Shared package sources need a shared-aware compiler. First run MLF_COMPILER=/path/to/released/emlf MLF_PACKAGE_MANAGER=/path/to/released/mlfpkg scripts/bootstrap-shared.sh, then set MLF_COMPILER to its stage2 compiler.' >&2; exit 2 ;;
  esac
  entry=package/MLF/Entry/Mlfpkg.hs
fi
cc=${CC:-clang}
if [ -n "${MLF_GC_PREFIX:-}" ]; then
  gc_cflags="-I$MLF_GC_PREFIX/include"
  gc_libs="$MLF_GC_PREFIX/lib/libgc.a"
else
  gc_cflags=$(pkg-config --cflags bdw-gc)
  gc_libs=$(pkg-config --libs bdw-gc)
fi
"$cc" -O2 -std=c11 -Wall -Wextra -Werror runtime/mlf_build_runner.c -o "$build/mlf-build-runner.new"
test "$("$build/mlf-build-runner.new" --protocol-version)" = 1
mv "$build/mlf-build-runner.new" "$build/mlf-build-runner"
set --
for library in "$root"/libraries/*; do set -- "$@" -i "$library"; done
"$compiler" "$@" --emit-llvm-gc "$entry" > "$build/mlfpkg.ll.new"
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
