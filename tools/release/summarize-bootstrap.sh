#!/usr/bin/env bash
set -euo pipefail
build=${1:?bootstrap build directory required}
timing="$build/timing"
shopt -s nullglob
samples=("$timing"/commands/*/result.json)
test "${#samples[@]}" -gt 0
jq -s --argjson budget "${MLF_BOOTSTRAP_MAX_RSS_BYTES:-5500000000}" 'sort_by(.started_utc,.kind) as $commands |
  {commands:$commands,
   memory_budget:{limit_bytes:$budget,peak_process_rss_bytes:($commands|map(.peak_rss_bytes)|max),
     passed:($budget==0 or all($commands[];.peak_rss_bytes<=$budget))},
   totals:([$commands[]|select(.kind!="package-manager" and .kind!="manager-bootstrap")]|group_by(.kind)|map(
     {kind:.[0].kind,commands:length,wall_seconds:(map(.wall_seconds)|add),
      cpu_seconds:(map(.user_seconds+.system_seconds)|add),peak_rss_bytes:(map(.peak_rss_bytes)|max)})),
   package_manager:[$commands[]|select(.kind=="package-manager")],
   manager_bootstrap:[$commands[]|select(.kind=="manager-bootstrap")],
   accounting:"Manager bootstrap and package-manager measurements each include their MLF and Clang child calls; do not add enclosing measurements to child totals. Both cold stages and native helper preparation are included in the memory budget."}' \
  "${samples[@]}" > "$timing/summary.json"
{
  printf '| Phase | Wall seconds | User seconds | System seconds | Peak RSS bytes | Exit |\n'
  printf '| --- | ---: | ---: | ---: | ---: | ---: |\n'
  jq -r '.commands[]|"| \(.phase) | \(.wall_seconds) | \(.user_seconds) | \(.system_seconds) | \(.peak_rss_bytes) | \(.exit_code) |"' "$timing/summary.json"
  printf '\nManager bootstrap and package-manager rows contain their MLF and Clang child calls; do not add enclosing measurements to child totals. Both cold stages and native helper preparation are included in the memory budget. Full argv, raw time output, host identity, tool hashes and native build reports are retained in the artifact.\n'
  jq -r '"\nPeak process RSS: \(.memory_budget.peak_process_rss_bytes) bytes; budget: \(.memory_budget.limit_bytes) bytes (0 disables the diagnostic budget); passed: \(.memory_budget.passed)."' "$timing/summary.json"
} | tee "$timing/summary.md"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then cat "$timing/summary.md" >> "$GITHUB_STEP_SUMMARY"; fi
jq -e '.memory_budget.passed' "$timing/summary.json" >/dev/null || {
  jq -r '"Bootstrap RSS budget exceeded: \(.memory_budget.peak_process_rss_bytes) > \(.memory_budget.limit_bytes) bytes; full command evidence is retained."' "$timing/summary.json" >&2
  exit 78
}
