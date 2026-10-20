#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
group=${1:-smoke}
profile=${2:-${MLF_TEST_RUNTIME_PROFILE:-}}
test "$#" -le 2 || { printf '%s\n' 'Expected a group and optional port profile.' >&2; exit 2; }
case "$group" in smoke|unit|packages|self-host|parity|backends|port) ;; *) exit 2 ;; esac
if [ "$group" = port ]; then
  case "$profile" in ''|standard|compact-gc) ;; *) printf '%s\n' 'Invalid port runtime profile.' >&2; exit 2 ;; esac
  export MLF_TEST_RUNTIME_PROFILE="$profile"
else
  test -z "$profile" || { printf '%s\n' 'Runtime profiles are only supported for port tests.' >&2; exit 2; }
fi
evidence_group=$group
if [ -n "$profile" ]; then evidence_group="port-$profile"; fi
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
if [ "$group" = port ]; then
  case "$(uname -s)" in
    Darwin) matrix_memory_bytes=$(sysctl -n hw.memsize) ;;
    Linux) matrix_memory_bytes=$(awk '/^MemTotal:/ {printf "%.0f\n", $2 * 1024}' /proc/meminfo) ;;
  esac
  if [ -z "${MLF_TEST_MATRIX_GC_DIVISOR:-}" ]; then
    # The interpreted solver probe peaks near 6.5 GB with divisor 1, before
    # accounting for its parent test process and the OS. Small CI hosts trade
    # extra collection work for a measured peak near 3.4 GB with divisor 4.
    if [ "$matrix_memory_bytes" -le 8589934592 ]; then
      export MLF_TEST_MATRIX_GC_DIVISOR=4
    else
      export MLF_TEST_MATRIX_GC_DIVISOR=1
    fi
  fi
  printf 'Port matrix host memory: %s bytes; GC free-space divisor: %s\n' "$matrix_memory_bytes" "$MLF_TEST_MATRIX_GC_DIVISOR"
fi
mkdir -p .mlf-build/forbidden-tools
for command_name in ghc ghc-pkg runghc runhaskell cabal python python3; do
  cat > ".mlf-build/forbidden-tools/$command_name" <<'SH'
#!/bin/sh
printf 'Forbidden build dependency: %s\n' "$0" >&2
exit 97
SH
  chmod 755 ".mlf-build/forbidden-tools/$command_name"
done
export PATH="$PWD/.mlf-build/forbidden-tools:$PATH"
if [ "$group" = smoke ]; then
  "$MLF_COMPILER" --type --expr '\x -> x'
  ./mlfpkg --compiler "$MLF_COMPILER" --runtime "$PWD/runtime/mlf_runtime.c" --manifest examples/packages/mlf-package.json --timeout 21600 test
else
  case "$group" in unit|packages|self-host|parity|backends|port) ;; *) exit 2 ;; esac
  # Native test commands retain their primary logs for the release evidence.
  # Follow those same files while tests run so CI also shows suite progress.
  mkdir -p .mlf-build/tests ".mlf-build/compiler-tests/$evidence_group"
  logs=(".mlf-build/tests/$group.log")
  case "$group" in
    unit) suites='core figure12 harness' ;;
    packages) suites='packages' ;;
    backends) suites='standard compact-gc' ;;
    port) suites=${profile:-'standard compact-gc'} ;;
    *) suites='' ;;
  esac
  for suite in $suites; do logs+=(".mlf-build/compiler-tests/$evidence_group/$suite.log"); done
  if [ "$group" = port ]; then
    # These three bounded fixture outputs expose progress inside expensive
    # interpreted compiler workloads. The native supervisor truncates them
    # before each run; following the same files does not change validation.
    for suite in $suites; do
      matrix=".mlf-build/compiler-tests/$evidence_group/matrix-$suite"
      mkdir -p "$matrix"
      for index in 14 19 23; do logs+=("$matrix/case-$index-interpreter.stdout"); done
    done
  fi
  touch "${logs[@]}"
  tail -n +1 -f "${logs[@]}" &
  log_pid=$!
  finish_logs() {
    status=$?
    trap - EXIT
    kill "$log_pid" 2>/dev/null || true
    wait "$log_pid" 2>/dev/null || true
    exit "$status"
  }
  trap finish_logs EXIT
  ./mlfpkg --runtime "$PWD/runtime/mlf_runtime.c" --timeout 21600 --locked test --target "$group"
fi
