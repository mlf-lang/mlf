#!/usr/bin/env bash
# Control-only receipt validation; this mock runner does not execute MLF.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/mlf-direct-smoke.XXXXXXXX")
trap 'rm -rf "$work"' EXIT
project="$work/project with spaces"
mkdir -p "$project/tools/release" "$project/tools/shared" "$project/bootstrap" \
  "$project/libraries/example" "$project/tests/Tests" "$project/tests/pr-smoke" "$project/host" "$project/runtime" "$work/bin"
cp "$root/tools/release/source-smoke.sh" "$root/tools/release/native-ci.sh" "$project/tools/release/"
for file in libraries/example/Main.hs libraries/example/mlf-package.json tests/PRQuickMain.emlf \
  tests/Tests/IndependentCheck.hs tests/Tests/IndependentType.hs tests/pr-smoke/example \
  host/Adapter.hs tools/shared/build.py; do
  printf 'test source fixture\n' > "$project/$file"
done
cat > "$project/shared-sources.json" <<'MANIFEST'
{"source_syntax":"shared-haskell-v1","frontend_semantics":"test/2","builtin_interface":"test/3","primitive_abi":"test/95","modules":[{"module":"Example","path":"libraries/example/Main.hs"}],"host_only":["host/Adapter.hs"]}
MANIFEST
cat > "$work/bin/git" <<'GIT'
#!/bin/sh
test "$1 $2" = 'rev-parse HEAD'
printf '%040d\n' 0
GIT
cat > "$work/runner" <<'RUNNER'
#!/bin/sh
set -eu
test "$#" -eq 2
printf 'called\n' >> "$TEST_CALLS"
printf 'target\n' > "$2/polymorphic-let.xmlf"
printf 'target\n' > "$2/impredicative-self-application.xmlf"
cat "$2/expected.log"
RUNNER
chmod +x "$work/bin/git" "$work/runner"
export PATH="$work/bin:$PATH" TEST_CALLS="$work/calls"
export MLF_SOURCE_SMOKE_RUNNER="$work/runner" MLF_SOURCE_SMOKE_RECEIPT="$work/receipt.json"
sha256() { shasum -a 256 "$1" | awk '{print $1}'; }
jq -n --arg runner "$work/runner" --arg binary "$(sha256 "$work/runner")" \
  --arg manifest "$(sha256 "$project/shared-sources.json")" \
  --arg source "$project/libraries/example/Main.hs" --arg source_hash "$(sha256 "$project/libraries/example/Main.hs")" \
  --arg host "$project/host/Adapter.hs" --arg host_hash "$(sha256 "$project/host/Adapter.hs")" \
  '{complete:true,typecheck_only:false,producer_host:"GHC",implementation_identity:"MLF/shared-haskell-v1 GHC",ghc:{version:"9.14.1"},optimization:"0",flags:["-fpedantic-bottoms","-fno-state-hack"],source_syntax:"shared-haskell-v1",frontend_semantics:"test/2",builtin_interface:"test/3",primitive_abi:"test/95",manifest_sha256:$manifest,
    shared_inputs:{Example:{path:$source,sha256:$source_hash}},resolved_modules:{Example:{path:$source,sha256:$source_hash}},
    host_inputs:{"host/Adapter.hs":{path:$host,sha256:$host_hash}},outputs:{"source-smoke":{path:$runner,sha256:$binary}}}' > "$MLF_SOURCE_SMOKE_RECEIPT"
cp "$MLF_SOURCE_SMOKE_RECEIPT" "$work/valid.json"
"$project/tools/release/source-smoke.sh" > "$work/success.log" 2>&1
jq -e '.complete == true and .mode == "direct-GHC-checkout-source" and (.producer_receipt_sha256 | length) == 64' "$project/.mlf-build/source-smoke/result.json" >/dev/null
test "$(wc -l < "$TEST_CALLS" | tr -d ' ')" -eq 1
expect_rejected() {
  local status=0
  printf '{"complete":true}\n' > "$project/.mlf-build/source-smoke/result.json"
  "$project/tools/release/source-smoke.sh" > "$work/rejected.log" 2>&1 || status=$?
  test "$status" -ne 0
  jq -e '.complete == false' "$project/.mlf-build/source-smoke/result.json" >/dev/null
  test "$(wc -l < "$TEST_CALLS" | tr -d ' ')" -eq 1
}
jq '.complete = false' "$work/valid.json" > "$MLF_SOURCE_SMOKE_RECEIPT"
expect_rejected
jq '.resolved_modules.Example.path = "/wrong/source.hs"' "$work/valid.json" > "$MLF_SOURCE_SMOKE_RECEIPT"
expect_rejected
jq '.outputs["source-smoke"].sha256 = ("0" * 64)' "$work/valid.json" > "$MLF_SOURCE_SMOKE_RECEIPT"
expect_rejected
jq '.host_inputs = {}' "$work/valid.json" > "$MLF_SOURCE_SMOKE_RECEIPT"
expect_rejected
jq '.flags = []' "$work/valid.json" > "$MLF_SOURCE_SMOKE_RECEIPT"
expect_rejected
cp "$work/valid.json" "$MLF_SOURCE_SMOKE_RECEIPT"
printf 'stale source\n' >> "$project/libraries/example/Main.hs"
expect_rejected
grep -F 'Stale direct-source input:' "$work/rejected.log" >/dev/null
status=0
"$project/tools/release/native-ci.sh" source-smoke > "$work/native.log" 2>&1 || status=$?
test "$status" -eq 2
grep -F 'separate from native CI' "$work/native.log" >/dev/null
printf '%s\n' 'PASS direct smoke control: authenticated source paths/hashes, honest producer, stale or incomplete receipt rejection, native route separation.'
