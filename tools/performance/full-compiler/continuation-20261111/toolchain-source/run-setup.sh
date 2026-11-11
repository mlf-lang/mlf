#!/usr/bin/env bash
set -euo pipefail
# Original authenticated SETUP output cap is 12288 MiB, not target diagnostic 4096 MiB.
# Source: ../repository/tools/performance/full-compiler/recovery-audit-20261110/toolchain-summary.json
TC=/workspace/scratch/3f83e2ebe290/astra-continuation-20261111/toolchain
SOURCE=/workspace/scratch/3f83e2ebe290/astra-continuation-20261111/source
LOCK=/workspace/scratch/3f83e2ebe290/.astra-resource-locks/heavy.lock
[[ "${1:-}" == "SETUP_2_COORDINATOR_ADMITTED" ]] || { echo 'Separate coordinator SETUP admission required' >&2; exit 64; }
[[ -f "$LOCK" && ! -e "$TC/bounded-receipt.json" && ! -e "$TC/setup-result.json" && ! -e "$TC/tmp" ]] || { echo 'Lock absent or one-shot output already exists; no implicit retry' >&2; exit 65; }
cd "$TC"
sha256sum --check controller.sha256
exec flock -n -E 73 "$LOCK" python3 -B "$SOURCE/tools/shared/resource_watchdog.py" \
  --seconds 600 --address-space-mib 6144 --rss-mib 5120 --max-output-mib 12288 --disk-free-mib 5120 \
  "$TC" python3 -B "$TC/install.py"
