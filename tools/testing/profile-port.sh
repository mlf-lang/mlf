#!/usr/bin/env bash
set -euo pipefail
. tools/testing/native-events.sh

if [ "${1:-}" = --framework-list ]; then
  printf '%s\n' '["port-prepare/SolverReuse/gc-1","port-prepare/SolverReuse/gc-2","port-prepare/SolverReuse/gc-4","port-prepare/InferenceConformance/gc-1","port-prepare/InferenceConformance/gc-2","port-prepare/InferenceConformance/gc-4"]'
  exit 0
fi
test "$#" = 0
case "$FIXTURE" in SolverReuse|InferenceConformance) ;; *) exit 2 ;; esac
case "$GC_FREE_SPACE_DIVISOR" in 1|2|4) ;; *) exit 2 ;; esac
identity="port-prepare/$FIXTURE/gc-$GC_FREE_SPACE_DIVISOR"
if test -n "${MLF_TEST_EVENTS:-}"; then printf '{"plan":["%s"]}\n' "$identity" >> "$MLF_TEST_EVENTS"; fi
trap 'mlf_case_cleanup "$?"' EXIT
mlf_case_start "$identity"

directory=.mlf-build/port-profile/measurement
mkdir -p "$directory"
target="$PWD/$directory/unit.xmlf"
test ! -e "$target" && test ! -e "$target.checks.json"
start=$(date +%s)
/usr/bin/time -l .mlf-build/port-profile/bin/port --prepare "$FIXTURE" "$target" \
  > "$directory/prepare.log" 2> "$directory/time.log"
end=$(date +%s)
cat "$directory/prepare.log" "$directory/time.log"
jq -e --arg fixture "$FIXTURE" '.fixture == $fixture and .entry_type == "IO Unit"' "$target.checks.json"
rss=$(awk '/maximum resident set size/ {print $1}' "$directory/time.log")
jq -n --arg source "$SOURCE_COMMIT" --arg run "$CANDIDATE_RUN" --arg fixture "$FIXTURE" \
  --arg divisor "$GC_FREE_SPACE_DIVISOR" --argjson start "$start" --argjson end "$end" --argjson rss "$rss" \
  --arg port "$(shasum -a 256 .mlf-build/port-profile/bin/port | awk '{print $1}')" \
  --arg target "$(shasum -a 256 "$target" | awk '{print $1}')" \
  --arg checks "$(shasum -a 256 "$target.checks.json" | awk '{print $1}')" \
  '{complete:true,source:$source,candidate_run:$run,fixture:$fixture,gc_free_space_divisor:$divisor,seconds:($end-$start),maximum_resident_bytes:$rss,port_sha256:$port,target_sha256:$target,checks_sha256:$checks}' \
  > "$directory/timing.json"
tools/release/shared-candidate.sh verify
mlf_case_result pass 0
