#!/usr/bin/env bash
# PRIVATE UNRUN REVIEW CANDIDATE. Requires Astra's separate phase authorization.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
base="$here/../compiler-baseline-20261110"
if (( $# < 2 )); then
  echo 'usage: bash run-phase.sh build|controls|target NEW_GUARD_ROOT [--build DIR] [--controls DIR]' >&2
  exit 2
fi
phase=$1; guard=$2; shift 2
case "$phase" in build) seconds=600;; controls) seconds=60;; target) seconds=120;; *) exit 2;; esac
# These are three separate scheduled invocations, never an automatic chain.
mkdir -- "$guard"
guard=$(cd -- "$guard" && pwd)
source "$here/../compiler-toolchain-20261110/env.sh"
exec flock -n /workspace/shared/mlf-compiler-sprint-20261110/resource.lock \
  python3 -B "$base/tools/shared/resource_watchdog.py" \
  --seconds "$seconds" --address-space-mib 6144 --rss-mib 5120 \
  --disk-free-mib 5120 --max-output-mib 4096 "$guard" \
  python3 -B "$here/p1.py" "$phase" --output "$guard/work" "$@"
