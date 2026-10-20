#!/usr/bin/env bash
set -euo pipefail
package=$(cd -- "${1:?package directory required}" && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/mlf release smoke.XXXXXX")
trap 'rm -rf "$work"' EXIT
"$package/install.sh" "$work/prefix with ' quote" >/dev/null
bin="$work/prefix with ' quote/bin"
cd "$work"
"$bin/emlf" --version
"$bin/mlfpkg" --version
"$bin/emlf" --type --expr '\x -> x' | grep -q -- '->'
cat > Main.emlf <<'MLF'
module Main where
import Message
main = putStrLn message
MLF
cat > Message.emlf <<'MLF'
module Message where
message = "native release"
MLF
printf 'native release\n' > expected
"$bin/emlf" --run Main.emlf > interpreted
cmp expected interpreted
"$bin/emlf" --emit-llvm Main.emlf > main.ll
runtime=$("$bin/emlf" --llvm-runtime)
# pkg-config emits native linker flags, as in the seed bootstrap script.
# shellcheck disable=SC2046
clang -O2 -std=c11 $(pkg-config --cflags gmp) -c "$runtime" -o runtime.o
# shellcheck disable=SC2046
clang -O2 -Wno-override-module main.ll runtime.o $(pkg-config --libs gmp) -lm -o native
./native > compiled
cmp expected compiled
cat > mlf-package.json <<'JSON'
{"format":1,"name":"release-smoke","version":"0.1.0","library":{"modules":{"Message":"Message.emlf"}},"executables":{"hello":{"main":"Main.emlf"}},"tests":{"hello":{"main":"Main.emlf","stdout":"native release\n"}}}
JSON
MLF_COMPILER="$bin/emlf" "$bin/mlfpkg" test > package.log
grep -q 'test passed' package.log
# A second install is safe, and an unrelated existing command is preserved.
"$package/install.sh" "$work/prefix with ' quote" >/dev/null
mkdir -p "$work/conflict/bin"
printf 'unrelated\n' > "$work/conflict/bin/emlf"
if "$package/install.sh" "$work/conflict" > conflict.log 2>&1; then
  printf '%s\n' 'Installer replaced an unrelated command.' >&2; exit 1
fi
test "$(cat "$work/conflict/bin/emlf")" = unrelated
printf '%s\n' 'Release smoke passed: relocated install, modules, interpreter, LLVM, package tests, safe reinstall.'
