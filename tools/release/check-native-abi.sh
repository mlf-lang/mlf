#!/usr/bin/env bash
# Run the existing native ABI actions before the slower complete unit group.
# A separate temporary target preserves the real MLF command builders and
# bounds inference memory; it does not replace any release qualification.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
compiler=${1:?native compiler required}
manager=${MLF_PACKAGE_MANAGER:?native package manager required}
compiler=$(command -v -- "$compiler")
manager=$(command -v -- "$manager")
compiler=$(cd -- "$(dirname -- "$compiler")" && pwd)/$(basename -- "$compiler")
manager=$(cd -- "$(dirname -- "$manager")" && pwd)/$(basename -- "$manager")
output=${2:-.mlf-build/native-abi-preflight}
test -x "$compiler"
test -x "$manager"
test ! -e "$output" || { printf 'Use a new ABI preflight directory: %s\n' "$output" >&2; exit 1; }
mkdir -p "$output/project" "$output/work"
output=$(cd "$output" && pwd)

cat > "$output/project/NativeABIPreflight.emlf" <<'MLF'
module NativeABIPreflight where
import Bootstrap.Types
import qualified Bootstrap.Std as S
import qualified Tests.NativeABI as ABI
main = do
  S.mapM_ (\(Pair label action) -> do
    putStrLn ("Native ABI preflight: " ++ label)
    action
    putStrLn ("PASS " ++ label)) ABI.suite
  putStrLn (showInt (S.length ABI.suite) ++ " native ABI checks passed")
MLF
jq -n --arg root "$PWD" '{
  format:1,name:"mlf-native-abi-preflight",version:"0.0.0",
  dependencies:{"mlf-bootstrap":{path:($root+"/bootstrap")},"mlf-tests":{path:($root+"/tests")}},
  executables:{"native-abi":{main:"NativeABIPreflight.emlf",profile:"compiler",link:"separate"}}
}' > "$output/project/mlf-package.json"

# This generic byte transport is the same C fixture used by CompilerTests.
# All runtime probe compilation/linking remains in Tests.NativeABI.suite.
clang -O2 -std=c11 -Wall -Wextra -Werror test/binary_files.c -o "$output/binary-files" 2>&1 | tee "$output/binary-files.log"
clang -O2 -std=c11 -Wall -Wextra -Werror test/host_support.c -o "$output/host-support" 2>&1 | tee "$output/host-support.log"
export MLF_TEST_BINARY_FILES="$output/binary-files"
export MLF_TEST_HOST_SUPPORT="$output/host-support"
export MLF_TEST_WORK="$output/work"
export MLF_TEST_ROOT="$output/work"
export MLF_BOOTSTRAP_COMPILER="$compiler"
"$manager" --compiler "$compiler" --clang clang --runtime "$PWD/runtime/mlf_runtime.c" \
  --manifest "$output/project/mlf-package.json" --build-dir "$output/build" --timeout 21600 build 2>&1 | tee "$output/build.log"
"$output/build/bin/native-abi" 2>&1 | tee "$output/verification.log"
grep -Fxq '7 native ABI checks passed' "$output/verification.log"
