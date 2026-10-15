#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
test "$(uname -s):$(uname -m)" = Darwin:arm64
export MLF_GC_PREFIX=${MLF_GC_PREFIX:-"$(brew --prefix bdw-gc)"}
llvm_prefix=$(brew --prefix llvm)
export PATH="$llvm_prefix/bin:$PATH"
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
group=${1:-smoke}
if [ "$group" = smoke ]; then
  "$MLF_COMPILER" --type --expr '\x -> x'
  ./mlfpkg --compiler "$MLF_COMPILER" --runtime "$PWD/runtime/mlf_runtime.c" --manifest examples/packages/mlf-package.json --timeout 21600 test
else
  case "$group" in unit|packages|self-host|parity|backends|port) ;; *) exit 2 ;; esac
  ./mlfpkg --runtime "$PWD/runtime/mlf_runtime.c" --timeout 21600 --locked test --target "$group"
fi
