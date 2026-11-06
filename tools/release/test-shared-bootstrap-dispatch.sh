#!/usr/bin/env bash
# Control-only launch contracts. No MLF or native compiler is executed.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/mlf-shared-launch.XXXXXXXX")
trap 'rm -rf "$work"' EXIT
project="$work/project with spaces"
mkdir -p "$project/scripts" "$work/bin"
cp "$root/scripts/bootstrap-async.sh" "$root/scripts/bootstrap-package.sh" "$project/scripts/"
printf '{}\n' > "$project/shared-sources.json"
cat > "$project/scripts/bootstrap-shared.sh" <<'BRIDGE'
#!/bin/sh
set -eu
test "$MLF_COMPILER" = "$TEST_COMPILER"
test "$MLF_PACKAGE_MANAGER" = "$TEST_MANAGER"
printf '%s\n' "$MLF_ASYNC_BOOTSTRAP_DIR" "$*" > "$TEST_DISPATCH"
printf '%s/stage2\n' "$MLF_ASYNC_BOOTSTRAP_DIR"
BRIDGE
cat > "$work/compiler" <<'COMPILER'
#!/bin/sh
set -eu
if [ "${1:-}" = --implementation-identity ]; then
  if [ "$TEST_MODE" = legacy ]; then exit 1; fi
  printf 'MLF/shared-haskell-v1 %s\n' "$TEST_MODE"
else
  printf '%s\n' "$*" > "$TEST_EMISSION"
  printf 'mock LLVM output\n'
fi
COMPILER
cat > "$work/bin/clang" <<'CC'
#!/bin/sh
set -eu
output=
while [ "$#" -gt 0 ]; do case "$1" in -o) output=$2; shift 2 ;; *) shift ;; esac; done
cat > "$output" <<'TOOL'
#!/bin/sh
if [ "${1:-}" = --protocol-version ]; then printf '1\n'; fi
TOOL
chmod +x "$output"
CC
printf '#!/bin/sh\nexit 0\n' > "$work/bin/pkg-config"
chmod +x "$project/scripts/"* "$work/compiler" "$work/bin/"*
export TEST_COMPILER="$work/compiler" TEST_MANAGER="$work/manager" TEST_DISPATCH="$work/dispatch"
export TEST_EMISSION="$work/emission" TEST_MODE=legacy
export MLF_COMPILER="$TEST_COMPILER" MLF_PACKAGE_MANAGER="$TEST_MANAGER"
export PATH="$work/bin:$PATH"
unset MLF_ASYNC_BOOTSTRAP_DIR MLF_SHARED_BOOTSTRAP_DIR
"$project/scripts/bootstrap-async.sh" argument > "$work/default.out"
test "$(head -1 "$TEST_DISPATCH")" = "$project/.mlf-build/async-bootstrap"
test "$(tail -1 "$TEST_DISPATCH")" = argument
MLF_ASYNC_BOOTSTRAP_DIR="$work/custom" "$project/scripts/bootstrap-async.sh" > "$work/custom.out"
test "$(cat "$work/custom.out")" = "$work/custom/stage2"
echo 'PASS shared bootstrap dispatch preserves directory and arguments'
status=0
MLF_PACKAGE_BOOTSTRAP_DIR="$work/rejected" "$project/scripts/bootstrap-package.sh" > "$work/rejected.out" 2> "$work/rejected.err" || status=$?
test "$status" -eq 2
grep -F 'scripts/bootstrap-shared.sh' "$work/rejected.err" >/dev/null
test ! -e "$TEST_EMISSION"
echo 'PASS shared package bootstrap rejects a released seed before emission'
for TEST_MODE in native-MLF GHC; do
  export TEST_MODE
  MLF_PACKAGE_BOOTSTRAP_DIR="$work/package-$TEST_MODE" "$project/scripts/bootstrap-package.sh" > "$work/package-$TEST_MODE.out"
  grep -F -- '--emit-llvm-gc package/MLF/Entry/Mlfpkg.hs' "$TEST_EMISSION" >/dev/null
  test -x "$(cat "$work/package-$TEST_MODE.out")"
  echo "PASS shared package launch with $TEST_MODE identity"
done
rm "$project/shared-sources.json"
export TEST_MODE=legacy
MLF_PACKAGE_BOOTSTRAP_DIR="$work/package-legacy" "$project/scripts/bootstrap-package.sh" > "$work/package-legacy.out"
grep -F -- '--emit-llvm-gc package/Main.emlf' "$TEST_EMISSION" >/dev/null
echo 'PASS legacy package launch remains unchanged without shared manifest'
