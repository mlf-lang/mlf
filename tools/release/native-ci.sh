#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
group=${1:-smoke}
# Invalidate rerun evidence before argument checks or native environment setup.
# Whitelist groups before using their names in an output path.
case "$group" in
  source-smoke|pr-smoke|extended-pr-smoke)
    mkdir -p ".mlf-build/$group"
    printf '{"complete":false}\n' > ".mlf-build/$group/result.json"
    ;;
esac
test "$#" -le 1 || { printf '%s\n' 'Expected one test group.' >&2; exit 2; }
case "$group" in smoke|source-smoke|pr-smoke|extended-pr-smoke|unit|packages|self-host|parity|backends|port) ;; *) exit 2 ;; esac
test -z "${MLF_TEST_RUNTIME_PROFILE:-}" || test "$MLF_TEST_RUNTIME_PROFILE" = compact-gc || exit 2
evidence_group=$group
if [ "$group" = source-smoke ]; then
  # Interpreting sources does not build native code or discover development libraries.
  case "$(uname -s):$(uname -m)" in
    Darwin:arm64) ;;
    Linux:x86_64) ulimit -s unlimited ;;
    *) printf '%s\n' 'Unsupported native test host.' >&2; exit 2 ;;
  esac
else
  . tools/release/native-environment.sh
fi
if [ "$group" = packages ]; then
  command -v llvm-profdata >/dev/null || {
    printf '%s\n' 'Package PGO tests require llvm-profdata from the matching LLVM installation on PATH.' >&2
    exit 2
  }
  llvm-profdata --version
fi
if [ "$group" = port ]; then
  case "$(uname -s)" in
    Darwin) matrix_memory_bytes=$(sysctl -n hw.memsize) ;;
    Linux) matrix_memory_bytes=$(awk '/^MemTotal:/ {printf "%.0f\n", $2 * 1024}' /proc/meminfo) ;;
  esac
  if [ -z "${MLF_TEST_MATRIX_GC_DIVISOR:-}" ]; then
    # Native compiler workloads may need a larger collector allowance, before
    # accounting for its parent test process and the OS. Small CI hosts trade
    # extra collection work for a measured peak near 3.4 GB with divisor 4.
    if [ "$matrix_memory_bytes" -le 8589934592 ]; then
      export MLF_TEST_MATRIX_GC_DIVISOR=4
    else
      export MLF_TEST_MATRIX_GC_DIVISOR=1
    fi
  fi
  # Preparation holds several independently checked forms of large targets.
  # Apply the same host memory policy before those forms are constructed.
  case "$MLF_TEST_MATRIX_GC_DIVISOR" in 1|2|4) ;; *) exit 2 ;; esac
  export GC_FREE_SPACE_DIVISOR=$MLF_TEST_MATRIX_GC_DIVISOR
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
if [ "$group" = source-smoke ] || [ "$group" = pr-smoke ] || [ "$group" = extended-pr-smoke ]; then
  "tools/release/$group.sh"
elif [ "$group" = smoke ]; then
  "$MLF_COMPILER" --type --expr '\x -> x'
  ./mlfpkg --compiler "$MLF_COMPILER" --runtime "$PWD/runtime/mlf_runtime.c" --manifest examples/packages/mlf-package.json --timeout 21600 test
else
  case "$group" in unit|packages|self-host|parity|backends|port) ;; *) exit 2 ;; esac
  # Native test commands retain their primary logs for the release evidence.
  # Follow those same files while tests run so CI also shows suite progress.
  mkdir -p .mlf-build/tests ".mlf-build/compiler-tests/$evidence_group"
  logs=(".mlf-build/tests/$group.log")
  case "$group" in
    unit) suites='core figure12 harness test-framework regex' ;;
    packages) suites='packages' ;;
    backends|port) suites='compact-gc' ;;
    *) suites='' ;;
  esac
  for suite in $suites; do logs+=(".mlf-build/compiler-tests/$evidence_group/$suite.log"); done
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
  if [ "${MLF_CI_SHARED_CANDIDATE:-0}" = 1 ]; then
    tools/release/shared-candidate.sh verify
    ./mlfpkg --locked plan > .mlf-build/tests/source-plan.json
    # Keep the shared producer report intact while materializing the test-owned
    # campaign against the verified candidate and its authenticated cache.
    ./mlfpkg --compiler "$MLF_COMPILER" --runtime "$PWD/runtime/mlf_runtime.c" \
      --timeout 21600 --locked --build-dir "$PWD/.mlf-build/campaign-runner" \
      --cache-dir "$PWD/.mlf-build/cache" build --target compiler-tests
    rm -f .mlf-build/bin/compiler-tests
    cp .mlf-build/campaign-runner/bin/compiler-tests .mlf-build/bin/compiler-tests
    "$PWD/.mlf-build/bin/compiler-tests" "$group" \
      --manager "$MLF_PACKAGE_MANAGER" --compiler "$MLF_COMPILER" \
      --build-dir "$PWD/.mlf-build/compiler-tests/$evidence_group" \
      --cache-dir "$PWD/.mlf-build/cache" > ".mlf-build/tests/$group.log" 2>&1
    tools/release/shared-candidate.sh verify
  else
    ./mlfpkg --runtime "$PWD/runtime/mlf_runtime.c" --timeout 21600 --locked test --target "$group"
  fi
fi
