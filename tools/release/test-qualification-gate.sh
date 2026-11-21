#!/usr/bin/env bash
set -euo pipefail
. "$(dirname -- "$0")/test-events.sh" release-qualification-gate
cd -- "$(dirname -- "$0")/../.."
base=$(jq -n '["metadata","mac-bootstrap","mac-prerequisites","linux-candidate","mac-port-preparation","mac-port","mac-unit","mac-started","mac-tests","linux-port-preparation","linux-port","linux-tests","windows","benchmark-game"] | map({key:.,value:{result:"success"}}) | from_entries')
release_begin release/qualification-gate/complete
CHECKS="$base" tools/release/qualification-gate.sh >/dev/null
release_pass
count=1
reject() {
  release_begin "release/qualification-gate/$1"
  if CHECKS="$2" tools/release/qualification-gate.sh >/dev/null 2>&1; then echo 'Incomplete qualification was accepted' >&2; false; fi
  count=$((count + 1))
  release_pass
}
for name in $(jq -r 'keys[]' <<< "$base"); do
  for result in failure cancelled skipped pending; do reject "$name/$result" "$(jq --arg name "$name" --arg result "$result" '.[$name].result=$result' <<< "$base")"; done
  reject "$name/missing" "$(jq --arg name "$name" 'del(.[$name])' <<< "$base")"
done
reject empty '{}'
reject additional-job "$(jq '.extra={result:"success"}' <<< "$base")"
printf '%s complete qualification gate checks passed.\n' "$count"
