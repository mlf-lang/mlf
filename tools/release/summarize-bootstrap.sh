#!/usr/bin/env bash
set -euo pipefail
build=${1:?bootstrap build directory required}
timing="$build/timing"
shopt -s nullglob
samples=("$timing"/commands/*/result.json)
test "${#samples[@]}" -gt 0
jq -s 'sort_by(.started_utc,.kind) as $commands |
  {commands:$commands,
   totals:([$commands[]|select(.kind!="package-manager")]|group_by(.kind)|map(
     {kind:.[0].kind,commands:length,wall_seconds:(map(.wall_seconds)|add),
      cpu_seconds:(map(.user_seconds+.system_seconds)|add),peak_rss_bytes:(map(.peak_rss_bytes)|max)})),
   package_manager:[$commands[]|select(.kind=="package-manager")],
   accounting:"MLF and Clang child calls are serial; the enclosing package-manager measurement includes them and must not be added to their totals."}' \
  "${samples[@]}" > "$timing/summary.json"
{
  printf '| Phase | Wall seconds | User seconds | System seconds | Peak RSS bytes | Exit |\n'
  printf '| --- | ---: | ---: | ---: | ---: | ---: |\n'
  jq -r '.commands[]|"| \(.phase) | \(.wall_seconds) | \(.user_seconds) | \(.system_seconds) | \(.peak_rss_bytes) | \(.exit_code) |"' "$timing/summary.json"
  printf '\nThe package-manager row contains the child calls; do not add it to their totals. Full argv, raw time output, host identity, tool hashes and native build reports are retained in the artifact.\n'
} | tee "$timing/summary.md"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then cat "$timing/summary.md" >> "$GITHUB_STEP_SUMMARY"; fi
