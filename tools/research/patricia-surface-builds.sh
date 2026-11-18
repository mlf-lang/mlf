#!/usr/bin/env bash
set -euo pipefail
for source in old new old_swap new_swap; do
  (cd "$source" && python3 -B ../tools/shared/crc_process_supervisor.py --receipt ../evidence/"$source-build-supervisor.json" --work-seconds 1800 --cleanup-seconds 10 "$(command -v python3)" -B tools/shared/resource_watchdog.py --seconds 1740 --address-space-mib 6144 --rss-mib 5120 --disk-free-mib 5120 ../evidence/"$source-build-guard" python3 tools/shared/build.py --bootstrap-only --optimization 2 --build-dir .mlf-build/shared-ghc) > "evidence/$source-build.log" 2>&1
  cp "$source/.mlf-build/shared-ghc/receipt.json" "evidence/$source-producer-receipt.json"
  cmp "$source/.mlf-build/shared-ghc/receipt.json" "evidence/$source-producer-receipt.json"
done
