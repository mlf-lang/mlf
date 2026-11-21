#!/usr/bin/env bash
# Exercise the actual aggregate expression, including skipped/empty inputs.
set -euo pipefail
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
  local expected=$1 filter=$2 value=$3 status=0
  printf '%s\n' "$value" | jq -e "$filter" >/dev/null || status=$?
  if [ "$expected" = pass ]; then test "$status" -eq 0; else test "$status" -ne 0; fi
  checks=$((checks + 1))
}
base=$(jq -n '{metadata:{result:"success"},native:{result:"success"},"windows-runtime":{result:"success"},"build-runner":{result:"success"},"async-runtime":{result:"success"},"async-language":{result:"success"}}')
skipped=$(printf '%s\n' "$base" | jq 'map_values(.result = "skipped")')
check pass "$success_filter" "$base"
check pass "$skipped_filter" "$skipped"
for name in metadata native windows-runtime build-runner async-runtime async-language; do
  for result in failure cancelled skipped pending; do
    check fail "$success_filter" "$(printf '%s\n' "$base" | jq --arg name "$name" --arg result "$result" '.[$name].result=$result')"
  done
  for result in success failure cancelled pending; do
    check fail "$skipped_filter" "$(printf '%s\n' "$skipped" | jq --arg name "$name" --arg result "$result" '.[$name].result=$result')"
  done
  check fail "$success_filter" "$(printf '%s\n' "$base" | jq --arg name "$name" 'del(.[$name])')"
  check fail "$skipped_filter" "$(printf '%s\n' "$skipped" | jq --arg name "$name" 'del(.[$name])')"
done
check fail "$success_filter" '{}'
check fail "$skipped_filter" '{}'
check fail "$success_filter" "$(printf '%s\n' "$base" | jq '.extra={result:"success"}')"
check fail "$skipped_filter" "$(printf '%s\n' "$skipped" | jq '.extra={result:"skipped"}')"
printf '%s PR aggregate controls passed for normal and labeled runs.\n' "$checks"
