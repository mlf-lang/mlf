#!/usr/bin/env bash
# Machine-readable boundaries, including failed stages inside composite actions.
set -euo pipefail
label=${1:?stage label required}
shift
started=$(date +%s)
printf 'CI_STAGE_START %s %s\n' "$label" "$started"
finish() {
  code=$?
  trap - EXIT
  printf 'CI_STAGE_END %s %s %s\n' "$label" "$(date +%s)" "$code"
  exit "$code"
}
trap finish EXIT
"$@"
