#!/usr/bin/env bash
# Exercise the actual aggregate expression, including skipped/empty inputs.
set -euo pipefail
. "$(dirname -- "$0")/test-events.sh" release-pr-gate
cd -- "$(dirname -- "$0")/../.."
workflow=.github/workflows/ci.yml
grep -Fxq '    needs: [metadata, native, windows-runtime, build-runner, async-runtime, async-language]' "$workflow"
result_filter() {
  awk -F"'" -v result="$1" '/CHECKS.*jq -e/ && index($0, ".result == \"" result "\"") {print $4}' "$workflow"
}
success_filter=$(result_filter success)
skipped_filter=$(result_filter skipped)
test -n "$success_filter"
test -n "$skipped_filter"
checks=0
check() {
  local case_id=$1 expected=$2 filter=$3 value=$4 status=0
  release_begin "release/pr-gate/$case_id"
  printf '%s\n' "$value" | jq -e "$filter" >/dev/null || status=$?
  if [ "$expected" = pass ]; then test "$status" -eq 0; else test "$status" -ne 0; fi
  checks=$((checks + 1))
  release_pass
}
base=$(jq -n '{metadata:{result:"success"},native:{result:"success"},"windows-runtime":{result:"success"},"build-runner":{result:"success"},"async-runtime":{result:"success"},"async-language":{result:"success"}}')
skipped=$(printf '%s\n' "$base" | jq 'map_values(.result = "skipped")')
check normal/complete pass "$success_filter" "$base"
check labeled/complete pass "$skipped_filter" "$skipped"
for name in metadata native windows-runtime build-runner async-runtime async-language; do
  for result in failure cancelled skipped pending; do
    check "normal/$name/$result" fail "$success_filter" "$(printf '%s\n' "$base" | jq --arg name "$name" --arg result "$result" '.[$name].result=$result')"
  done
  for result in success failure cancelled pending; do
    check "labeled/$name/$result" fail "$skipped_filter" "$(printf '%s\n' "$skipped" | jq --arg name "$name" --arg result "$result" '.[$name].result=$result')"
  done
  check "normal/$name/missing" fail "$success_filter" "$(printf '%s\n' "$base" | jq --arg name "$name" 'del(.[$name])')"
  check "labeled/$name/missing" fail "$skipped_filter" "$(printf '%s\n' "$skipped" | jq --arg name "$name" 'del(.[$name])')"
done
check normal/empty fail "$success_filter" '{}'
check labeled/empty fail "$skipped_filter" '{}'
check normal/additional-job fail "$success_filter" "$(printf '%s\n' "$base" | jq '.extra={result:"success"}')"
check labeled/additional-job fail "$skipped_filter" "$(printf '%s\n' "$skipped" | jq '.extra={result:"skipped"}')"
printf '%s PR aggregate controls passed for normal and labeled runs.\n' "$checks"
