#!/usr/bin/env bash
# Failed smoke invocations must not retain a preceding successful receipt.
set -euo pipefail
scripts=$(cd -- "$(dirname -- "$0")" && pwd)
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
checkout="$scratch/checkout with spaces"
mkdir -p "$scratch/bin" "$checkout/tools/release"
for script in native-ci native-environment source-smoke pr-smoke extended-pr-smoke; do
  cp "$scripts/$script.sh" "$checkout/tools/release/"
done
# Force environment setup to fail before dependencies or native tools are used.
export TEST_SMOKE_HOST=unsupported
cat > "$scratch/bin/uname" <<'SH'
#!/usr/bin/env bash
if [ "$TEST_SMOKE_HOST" = macos ]; then
  case "$1" in -s) printf 'Darwin\n' ;; -m) printf 'arm64\n' ;; *) exit 99 ;; esac
else
  printf '%s\n' UnsupportedSmokeReceiptTestHost
fi
SH
chmod +x "$scratch/bin/uname"
export PATH="$scratch/bin:$PATH"
unset MLF_COMPILER MLF_PACKAGE_MANAGER MLF_TEST_RUNTIME_PROFILE
checks=0
expect_invalidated() {
  local label=$1 receipt=$2 expected_status=$3 diagnostic=$4 status=0
  shift 4
  mkdir -p "$(dirname -- "$receipt")"
  printf '{"complete":true}\n' > "$receipt"
  "$@" > "$scratch/failure.log" 2>&1 || status=$?
  if [ "$status" -ne "$expected_status" ]; then
    printf '%s returned %s; expected %s.\n' "$label" "$status" "$expected_status" >&2
    cat "$scratch/failure.log" >&2
    exit 1
  fi
  if [ -n "$diagnostic" ]; then
    grep -Fq -- "$diagnostic" "$scratch/failure.log"
  else
    test ! -s "$scratch/failure.log"
  fi
  if ! jq -e '.complete == false' "$receipt" >/dev/null; then
    printf '%s retained a successful receipt after failure.\n' "$label" >&2
    cat "$receipt" >&2
    exit 1
  fi
  checks=$((checks + 1))
  printf 'PASS smoke receipt: %s\n' "$label"
}
for group in source-smoke pr-smoke extended-pr-smoke; do
  receipt="$checkout/.mlf-build/$group/result.json"
  wrapper="$checkout/tools/release/native-ci.sh"
  helper="$checkout/tools/release/$group.sh"
  expect_invalidated "$group wrapper arguments" "$receipt" 2 'Expected one test group.' \
    "$wrapper" "$group" unexpected
  expect_invalidated "$group runtime profile" "$receipt" 2 '' \
    env MLF_TEST_RUNTIME_PROFILE=invalid "$wrapper" "$group"
  expect_invalidated "$group native environment" "$receipt" 2 'Unsupported native test host.' \
    "$wrapper" "$group"
  expect_invalidated "$group direct arguments" "$receipt" 1 '' \
    "$helper" unexpected
  expect_invalidated "$group missing seed" "$receipt" 1 'verified native seed compiler required' \
    "$helper"
done
test "$checks" -eq 15
export TEST_SMOKE_HOST=macos TEST_SMOKE_DEPENDENCIES="$scratch/dependencies.log"
for command in brew pkg-config; do
  cat > "$scratch/bin/$command" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$0 $*" >> "$TEST_SMOKE_DEPENDENCIES"
exit 99
SH
  chmod +x "$scratch/bin/$command"
done
cat > "$checkout/tools/release/source-smoke.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
test "$#" -eq 0
jq -e '.complete == false' .mlf-build/source-smoke/result.json >/dev/null
for command in ghc ghc-pkg runghc runhaskell cabal python python3; do
  status=0
  "$command" > .mlf-build/forbidden.log 2>&1 || status=$?
  test "$status" -eq 97
  grep -Fq 'Forbidden build dependency:' .mlf-build/forbidden.log
done
SH
"$checkout/tools/release/native-ci.sh" source-smoke
test ! -e "$TEST_SMOKE_DEPENDENCIES"
checks=$((checks + 1))
printf 'PASS smoke receipt: source wrapper needs no native build dependencies and blocks forbidden tools\n'
printf '%s smoke receipt checks passed\n' "$checks"
