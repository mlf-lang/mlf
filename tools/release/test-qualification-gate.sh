#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
base=$(jq -n '["metadata","mac-bootstrap","mac-prerequisites","linux-candidate","mac-port-preparation","mac-port","mac-unit","mac-started","mac-tests","linux-port-preparation","linux-port","linux-tests","windows","benchmark-game"] | map({key:.,value:{result:"success"}}) | from_entries')
CHECKS="$base" tools/release/qualification-gate.sh >/dev/null
count=1
reject() {
  if CHECKS="$1" tools/release/qualification-gate.sh >/dev/null 2>&1; then echo 'Incomplete qualification was accepted' >&2; exit 1; fi
  count=$((count + 1))
}
for name in $(jq -r 'keys[]' <<< "$base"); do
  for result in failure cancelled skipped pending; do reject "$(jq --arg name "$name" --arg result "$result" '.[$name].result=$result' <<< "$base")"; done
  reject "$(jq --arg name "$name" 'del(.[$name])' <<< "$base")"
done
reject '{}'
reject "$(jq '.extra={result:"success"}' <<< "$base")"
printf '%s complete qualification gate checks passed.\n' "$count"
