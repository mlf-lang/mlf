#!/usr/bin/env bash
# Materialize a Linux seed from verified, platform-neutral LLVM, then build
# the checkout with native MLF tools. All compiler policy remains in MLF.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
test "$(uname -s):$(uname -m)" = Linux:x86_64
seed_input=$(cd -- "${1:?directory containing emlf.ll, mlfpkg.ll and SHA256SUMS required}" && pwd)
build=${2:-.mlf-build/linux-bootstrap}
test ! -e "$build" || { printf 'Use a fresh bootstrap directory: %s\n' "$build" >&2; exit 1; }
mkdir -p "$build/seed"
build=$(cd "$build" && pwd)
# Require exactly the two expected inputs, and validate from their directory.
test "$(wc -l < "$seed_input/SHA256SUMS" | tr -d ' ')" = 2
for name in emlf.ll mlfpkg.ll; do
  test -s "$seed_input/$name"
  test "$(awk -v name="$name" '$2 == name { n++ } END { print n+0 }' "$seed_input/SHA256SUMS")" = 1
done
(cd "$seed_input" && sha256sum --check --strict SHA256SUMS)
ulimit -s unlimited
export GC_FREE_SPACE_DIVISOR=${GC_FREE_SPACE_DIVISOR:-1}
cc=${CC:-clang}
# These flags come from the host's pkg-config metadata; paths with spaces are
# handled by the native package manager once the initial seed exists.
# shellcheck disable=SC2046
"$cc" -O2 -std=c11 \
  $(pkg-config --cflags gmp bdw-gc) -c runtime/mlf_runtime.c -o "$build/seed/runtime.o"
"$cc" -O2 -std=c11 -Wall -Wextra -Werror runtime/mlf_build_runner.c -o "$build/seed/mlf-build-runner"
test "$("$build/seed/mlf-build-runner" --protocol-version)" = 1
for tool in emlf mlfpkg; do
  # shellcheck disable=SC2046
  "$cc" -O2 -Wno-override-module "$seed_input/$tool.ll" "$build/seed/runtime.o" \
    $(pkg-config --libs gmp bdw-gc) -lm -o "$build/seed/$tool"
done
cp "$seed_input/SHA256SUMS" "$build/seed/LLVM-SHA256SUMS"
"$cc" --version > "$build/seed/clang.txt"
uname -a > "$build/seed/host.txt"
export MLF_COMPILER="$build/seed/emlf"
export MLF_PACKAGE_MANAGER="$build/seed/mlfpkg"
"$MLF_COMPILER" --type --expr '\x -> x'
CC="$cc" tools/release/bootstrap-manager.sh "$build/manager-bootstrap"
export MLF_PACKAGE_MANAGER="$build/manager-bootstrap/bin/mlfpkg"
export MLF_COMPILER
MLF_COMPILER=$(cat "$build/manager-bootstrap/compiler.path")
"$MLF_PACKAGE_MANAGER" --compiler "$MLF_COMPILER" --clang "$cc" \
  --runtime "$PWD/runtime/mlf_runtime.c" --timeout 21600 --locked \
  --build-dir "${3:-$build/candidate}" build
candidate=$(cd "${3:-$build/candidate}" && pwd)
if [ -n "${GITHUB_ENV:-}" ]; then
  printf 'MLF_COMPILER=%s\nMLF_PACKAGE_MANAGER=%s\nGC_FREE_SPACE_DIVISOR=%s\n' \
    "$candidate/bin/emlf" "$candidate/bin/mlfpkg" "$GC_FREE_SPACE_DIVISOR" >> "$GITHUB_ENV"
fi
printf 'Native Linux candidate: %s/bin\n' "$candidate"
