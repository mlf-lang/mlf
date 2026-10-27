#!/usr/bin/env bash
# Control-only regression for already-shared-aware native input pairs.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/mlf-manager-identity.XXXXXXXX")
trap 'rm -rf "$work"' EXIT
project="$work/project"
mkdir -p "$project/tools/release" "$project/runtime"
cp "$root/tools/release/bootstrap-manager.sh" "$project/tools/release/"
printf '{}\n' > "$project/shared-sources.json"
printf '{}\n' > "$project/mlf-package.json"
cat > "$work/compiler" <<'STUB'
#!/bin/sh
test "$1" = --implementation-identity
printf 'MLF/shared-haskell-v1 native-MLF\n'
STUB
cat > "$work/manager" <<'STUB'
#!/bin/sh
set -eu
if [ "$1" = --implementation-identity ]; then
  test "$TEST_MANAGER_HOST" != unknown || exit 1
  printf 'MLF/shared-haskell-v1 %s\n' "$TEST_MANAGER_HOST"
  exit 0
fi
printf 'manager build invoked\n' >> "$TEST_BUILD_CALLS"
build=
while [ "$#" -gt 0 ]; do
 if [ "$1" = --build-dir ]; then build=$2; shift 2; else shift; fi
done
mkdir -p "$build/bin"
if [ "${TEST_BAD_OUTPUT:-0}" = 1 ]; then
 printf '#!/bin/sh\nprintf "MLF/shared-haskell-v1 GHC\\n"\n' > "$build/bin/mlfpkg"
 chmod +x "$build/bin/mlfpkg"
else
 cp "$0" "$build/bin/mlfpkg"
fi
printf '{"complete":true,"implementation":"MLF"}\n' > "$build/build-report.json"
STUB
cat > "$project/tools/release/ensure-build-runner.sh" <<'STUB'
#!/bin/sh
printf '#!/bin/sh\necho 1\n' > "$1/mlf-build-runner"
chmod +x "$1/mlf-build-runner"
STUB
chmod +x "$work/compiler" "$work/manager" "$project/tools/release/"*.sh
export MLF_COMPILER="$work/compiler" MLF_PACKAGE_MANAGER="$work/manager"
export TEST_BUILD_CALLS="$work/build-calls"
for TEST_MANAGER_HOST in GHC unknown; do
 export TEST_MANAGER_HOST
 status=0
 "$project/tools/release/bootstrap-manager.sh" "$work/rejected-$TEST_MANAGER_HOST" > "$work/$TEST_MANAGER_HOST.log" 2>&1 || status=$?
 test "$status" -eq 2
 grep -F 'native-MLF manager as well as compiler' "$work/$TEST_MANAGER_HOST.log" >/dev/null
 test ! -e "$TEST_BUILD_CALLS"
 echo "PASS shared-aware branch rejects $TEST_MANAGER_HOST manager before build"
done
if [ "$#" -gt 0 ]; then
 status=0
 MLF_PACKAGE_MANAGER="$1" "$project/tools/release/bootstrap-manager.sh" "$work/actual-ghc-rejected" > "$work/actual-ghc.log" 2>&1 || status=$?
 test "$status" -eq 2
 grep -F 'native-MLF manager as well as compiler' "$work/actual-ghc.log" >/dev/null
 test ! -e "$TEST_BUILD_CALLS"
 echo 'PASS shared-aware branch rejects supplied actual GHC-produced manager before build'
fi
export TEST_MANAGER_HOST=native-MLF
status=0
TEST_BAD_OUTPUT=1 "$project/tools/release/bootstrap-manager.sh" "$work/bad-output" > "$work/bad-output.log" 2>&1 || status=$?
test "$status" -eq 2
grep -F 'Produced manager does not identify as native-MLF' "$work/bad-output.log" >/dev/null
test ! -e "$work/bad-output/compiler.path"
echo 'PASS shared-aware branch rejects non-native output manager before publishing pointer'
"$project/tools/release/bootstrap-manager.sh" "$work/native-pair" > "$work/native.log" 2>&1
test -f "$TEST_BUILD_CALLS"
test "$(cat "$work/native-pair/compiler.path")" = "$MLF_COMPILER"
jq -e '.complete == true and .route == "shared-aware-native"' "$work/native-pair/bootstrap.json" >/dev/null
echo 'PASS shared-aware branch accepts explicit native pair without release-bundle layout'
echo 'Control fixtures establish dispatch only, not native producer authenticity or compiler correctness.'
