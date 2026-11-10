#!/usr/bin/env bash
# Each invocation needs its own Astra admission. No automatic Q -> C chaining.
set -euo pipefail
if (( $# < 4 )); then
  echo 'usage: bash run-phase.sh Q|C HANDOFF HANDOFF_SHA NEW_ROOT [Q_ROOT Q_OUTER_SHA Q_WORK_SHA]' >&2
  exit 2
fi
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
base="$here/../compiler-baseline-20261110"
python=$(command -v python3)
[[ "$python" == /* ]] || { echo 'absolute Python executable required' >&2; exit 2; }
phase=$1; handoff=$2; digest=$3; root=$4; shift 4
case "$phase:$#" in
  Q:0) seconds=420; qualification=() ;;
  C:3) seconds=600; qualification=(--qualification "$1" --qualification-outer-sha256 "$2" --qualification-work-sha256 "$3") ;;
  *) echo 'Q takes no qualification; C requires its exact completed Q root and two receipt hashes' >&2; exit 2 ;;
esac
expected=5368803eb84dabc9dcefa89225b6ff56afd637e105f227bade15e40f9a5e923f
[[ $(sha256sum "$base/tools/shared/resource_watchdog.py" | cut -d' ' -f1) == "$expected" ]] || exit 3
[[ $(sha256sum "$base/tools/performance/process-spawn/with_scope.py" | cut -d' ' -f1) == d8ffe4256f333c0b48b22b9e68d9c3fa5dc9b471fd22a0d636ba9b157fe419a3 ]] || exit 3
[[ -f "$handoff" && ! -e "$root" ]] || exit 3
mkdir -- "$root"; root=$(cd -- "$root" && pwd)
: "${MLF_SPRINT_LOCK:?set the shared cross-worker lock path}"
exec flock -n "$MLF_SPRINT_LOCK" \
  "$python" -B "$base/tools/shared/resource_watchdog.py" --seconds "$seconds" \
  --address-space-mib 6144 --rss-mib 5120 --disk-free-mib 5120 --max-output-mib 4096 "$root" \
  "$python" -B "$base/tools/performance/process-spawn/with_scope.py" \
  "$python" -B "$here/run.py" "$phase" --handoff "$handoff" --handoff-sha256 "$digest" \
  --output "$root/work" "${qualification[@]}"
