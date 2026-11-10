#!/usr/bin/env bash
# Portable wrapper, NOT the wrapper tested in capture02. Separate admission required.
set -euo pipefail
if (( $# != 2 )); then echo 'usage: bash run-gate.sh SEMANTICS_ROOT NEW_GUARD_ROOT' >&2; exit 2; fi
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
semantics=$(cd -- "$1" && pwd)
mkdir -- "$2"; guard=$(cd -- "$2" && pwd)
base="$here/../compiler-baseline-20261110"
source "$here/../compiler-toolchain-20261110/env.sh"
: "${MLF_SPRINT_LOCK:?Set the shared exclusive sprint lock path}"
exec flock -n "$MLF_SPRINT_LOCK" \
  python3 -B "$base/tools/shared/resource_watchdog.py" --seconds 180 \
  --address-space-mib 6144 --rss-mib 5120 --disk-free-mib 5120 --max-output-mib 4096 "$guard" \
  python3 -B "$here/run.py" --semantics "$semantics" --output "$guard/work"
