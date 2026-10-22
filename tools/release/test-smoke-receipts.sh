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
cat > "$scratch/bin/uname" <<'SH'
#!/usr/bin/env bash
printf '%s\n' UnsupportedSmokeReceiptTestHost
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
printf '%s smoke receipt checks passed\n' "$checks"
