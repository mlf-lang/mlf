#!/usr/bin/env bash
# Exercise the actual aggregate expression, including skipped/empty inputs.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
workflow=.github/workflows/ci.yml
grep -Fxq '    needs: [metadata, native, windows-runtime, build-runner, async-runtime, async-language]' "$workflow"
filter=$(awk -F"'" '/CHECKS.*jq -e/ {print $4}' "$workflow")
test -n "$filter"
checks=0
check() {
  local expected=$1 value=$2 status=0
  printf '%s\n' "$value" | jq -e "$filter" >/dev/null || status=$?
  if [ "$expected" = pass ]; then test "$status" -eq 0; else test "$status" -ne 0; fi
  checks=$((checks + 1))
}
base=$(jq -n '{metadata:{result:"success"},native:{result:"success"},"windows-runtime":{result:"success"},"build-runner":{result:"success"},"async-runtime":{result:"success"},"async-language":{result:"success"}}')
check pass "$base"
for name in metadata native windows-runtime build-runner async-runtime async-language; do
  for result in failure cancelled skipped pending; do
    check fail "$(printf '%s\n' "$base" | jq --arg name "$name" --arg result "$result" '.[$name].result=$result')"
  done
  check fail "$(printf '%s\n' "$base" | jq --arg name "$name" 'del(.[$name])')"
done
check fail '{}'
check fail "$(printf '%s\n' "$base" | jq '.extra={result:"success"}')"
printf '%s PR aggregate checks passed; all six required jobs must succeed.\n' "$checks"
