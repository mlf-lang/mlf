#!/usr/bin/env bash
# Source from the repository root before native builds and tests.
case "$(uname -s):$(uname -m)" in
  Darwin:arm64)
    export MLF_GC_PREFIX=${MLF_GC_PREFIX:-"$(brew --prefix bdw-gc)"}
    llvm_prefix=$(brew --prefix llvm)
    export PATH="$llvm_prefix/bin:$PATH"
    ;;
  Linux:x86_64)
    # Linux defaults to a small stack. Native compiler recursion and child
    # compiler tests inherit the job's unrestricted stack allowance.
    ulimit -s unlimited
    # Package discovery tests also exercise an explicit collector prefix.
    # Debian installs its archive in a multiarch directory; expose the same
    # include/lib layout used by explicit local installations on every host.
    if [ -z "${MLF_GC_PREFIX:-}" ]; then
      gc_include=$(pkg-config --variable=includedir bdw-gc)
      gc_library=$(pkg-config --variable=libdir bdw-gc)/libgc.a
      test -d "$gc_include/gc"
      test -f "$gc_include/gc.h"
      test -f "$gc_library"
      export MLF_GC_PREFIX="$PWD/.mlf-build/native-dependencies/bdw-gc"
      mkdir -p "$MLF_GC_PREFIX/include" "$MLF_GC_PREFIX/lib"
      # Keep the fingerprinted header tree limited to the collector itself.
      cp -R "$gc_include/gc" "$MLF_GC_PREFIX/include/"
      cp "$gc_include/gc.h" "$MLF_GC_PREFIX/include/"
      ln -sfn "$gc_library" "$MLF_GC_PREFIX/lib/libgc.a"
    fi
    ;;
  *) printf '%s\n' 'Unsupported native test host.' >&2; exit 2 ;;
esac
