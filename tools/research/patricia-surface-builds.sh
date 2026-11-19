#!/usr/bin/env bash
set -euo pipefail
# Outer supervisor bounds this entire serial batch to 1800 seconds.
build() {
  local source="$1"
  (cd "$source" && python3 -B ../tools/shared/crc_process_supervisor.py --receipt ../evidence/"$source-build-supervisor.json" --work-seconds 1800 --cleanup-seconds 10 "$(command -v python3)" -B tools/shared/resource_watchdog.py --seconds 1740 --address-space-mib 6144 --rss-mib 5120 --disk-free-mib 5120 ../evidence/"$source-build-guard" python3 tools/shared/build.py --bootstrap-only --optimization 2 --build-dir .mlf-build/shared-ghc) > "evidence/$source-build.log" 2>&1
}
for source in old; do
  build "$source"
  cp "$source/.mlf-build/shared-ghc/receipt.json" "evidence/$source-producer-receipt.json"
  cmp "$source/.mlf-build/shared-ghc/receipt.json" "evidence/$source-producer-receipt.json"
done
for lane in old_swap sham_only; do
  source="${lane}_generation"
  git worktree add --detach "$source" "$(git -C "$lane" rev-parse HEAD)"
  # Failure is anticipated but only the authenticated exact stale failure may proceed.
  status=0
  build "$source" || status=$?
  test "$status" = 1
  python3 -B tools/research/patricia-joint-generation.py clean-failure "$source"
  (cd "$source" && mkdir -p .mlf-build/builtin-generation-guard && python3 -B ../tools/shared/crc_process_supervisor.py --receipt ../evidence/"$source-generation-supervisor.json" --work-seconds 660 --cleanup-seconds 10 "$(command -v python3)" -B tools/shared/resource_watchdog.py --seconds 640 --address-space-mib 6144 --rss-mib 5120 --disk-free-mib 5120 ../evidence/"$source-generation-guard" python3 -B ../tools/research/patricia-stale-authenticator.py --root . --build-receipt .mlf-build/shared-ghc/receipt.json --output .mlf-build/builtin-generation-guard/results --timeout 600) > "evidence/$source-generation.log" 2>&1
  python3 -B tools/research/patricia-joint-generation.py adopt "$lane"
  build "$lane"
  cp "$lane/.mlf-build/shared-ghc/receipt.json" "evidence/$lane-producer-receipt.json"
  cmp "$lane/.mlf-build/shared-ghc/receipt.json" "evidence/$lane-producer-receipt.json"
done
