#!/bin/sh
# Standalone C runtime fixtures. Does not build or execute the MLF compiler.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
cc=${CC:-cc}
command -v "$cc" >/dev/null
command -v timeout >/dev/null
case "$(uname -s):$(uname -m)" in
    Linux:x86_64|Linux:aarch64) ;;
    *) echo 'This standalone test recipe currently requires 64-bit Linux.' >&2; exit 2 ;;
esac
case ${OPT_LEVEL:-2} in
    0|2) optimization="-O${OPT_LEVEL:-2}" ;;
    *) echo 'OPT_LEVEL must be 0 or 2.' >&2; exit 2 ;;
esac
set -- -std=c11 "$optimization" -Wall -Wextra -Werror -pedantic
case ${SANITIZE:-none} in
    none) ;;
    undefined) set -- "$@" -fsanitize=undefined -fno-sanitize-recover=all ;;
    address,undefined) set -- "$@" -fsanitize=address,undefined -fno-sanitize-recover=all ;;
    *) echo 'SANITIZE must be none, undefined, or address,undefined.' >&2; exit 2 ;;
esac
build=$(mktemp -d "${TMPDIR:-/tmp}/mlf-nogc-runtime.XXXXXXXX")
printf 'Runtime fixture artifacts: %s\n' "$build"
bounded() { timeout -k 2 30 "$@"; }
cd "$root"
runtime=runtime/mlf_nogc_entry.c
fixtures=tests/native/nogc/runtime
support=tests/native/nogc/support
bounded "$cc" "$@" -c "$fixtures/abi_contract.c" -o "$build/abi.o"
bounded "$cc" "$@" "$runtime" "$support/disabled_profile_main.c" -o "$build/disabled"
bounded "$build/disabled"
echo 'PASS default-disabled refusal'
# This fixed profile is for these tiny C fixtures only. It is not an approved
# production profile or a generated-code/worker-stack qualification.
set -- "$@" -DMLF_NG0_PROFILE_QUALIFIED=1 -DMLF_NG0_CAPACITY_CEILING=65536 -DMLF_NG0_DEPTH_CEILING=128
for suite in runtime_contract allocation_faults compact_thunks concurrent_busy; do
    case $suite in
        allocation_faults)
            bounded "$cc" "$@" -fno-builtin-malloc -fno-builtin-free \
                "$runtime" "$fixtures/$suite.c" "$support/${suite}_main.c" \
                -Wl,--wrap=malloc -Wl,--wrap=free -o "$build/$suite" ;;
        concurrent_busy)
            bounded "$cc" "$@" "$runtime" "$fixtures/$suite.c" "$support/${suite}_main.c" \
                -pthread -o "$build/$suite" ;;
        *)
            bounded "$cc" "$@" "$runtime" "$fixtures/$suite.c" "$support/${suite}_main.c" \
                -o "$build/$suite" ;;
    esac
    bounded "$build/$suite"
    printf 'PASS %s\n' "$suite"
done
echo 'PASS standalone runtime fixtures and compile-only C ABI checks'
