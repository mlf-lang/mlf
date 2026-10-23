#!/usr/bin/env bash
# Missing, skipped, cancelled, pending and failed prerequisites all fail closed.
set -euo pipefail
printf '%s\n' "${CHECKS:?qualification results required}" | jq -e '
  (keys | sort) == (["metadata","mac-bootstrap","mac-prerequisites","linux-candidate","mac-port-preparation","mac-port","mac-unit","mac-started","mac-tests","linux-port-preparation","linux-port","linux-tests","windows","benchmark-game"] | sort) and
  all(.[]; .result == "success")'
