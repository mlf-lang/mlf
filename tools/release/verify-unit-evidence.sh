#!/usr/bin/env bash
# Verify complete split-unit evidence using retained bytes, not producer paths.
set -euo pipefail
unit=${1:?unit evidence directory required}
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
report="$unit/verification.json"
sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi | awk '{print $1}'; }
targets='["core-crates","core-language","core-modules","core-solver","figure12","harness","int-set-unions","regex","test-framework"]'
shards='["core-crates","core-solver","core-language","core-modules"]'
jq -e --argjson targets "$targets" --argjson shards "$shards" '
  def digest: type == "string" and test("^[0-9a-f]{64}$");
  # Bind the report before the predicate: jq 1.8 changed `as` precedence.
  . as $v |
  .complete == true and .implementation == "MLF" and .group == "unit" and .scope == "full" and
  (.prepared_suite_targets | keys) == $targets and
  all(.prepared_suite_targets[]; (.sha256 | digest)) and
  (.suite_builds | length) == 1 and .suite_builds[0].exit_code == 0 and
  (.suite_builds[0].jobs == 1 or .suite_builds[0].jobs == 2) and
  (.suite_builds[0].targets | sort) == $targets and (.suite_builds[0].sha256 | digest) and
  .suites.core.aggregate == true and .suites.core.scope == "full" and
  (.suites.core | has("binary_sha256") | not) and .suites.core.targets == $shards and
  (.suites.core.components | keys) == ($shards | sort) and
  all($shards[]; . as $name |
    $v.suites[$name].scope == "partial" and
    $v.suites[$name] == $v.suites.core.components[$name] and
    $v.suites[$name].binary_sha256 == $v.prepared_suite_targets[$name].sha256 and
    $v.family_reports[$name].result.scope == "partial")
' "$report" >/dev/null
build_path=$(jq -er '.suite_builds[0].path' "$report")
build_dir=$(basename "$(dirname "$build_path")")
[[ "$build_dir" =~ ^suite-build-invocation-[A-Za-z0-9_-]+$ ]]
test "$(basename "$build_path")" = build-report.json
build="$unit/$build_dir/build-report.json"
test "$(sha256 "$build")" = "$(jq -er '.suite_builds[0].sha256' "$report")"
jq -se --argjson targets "$targets" '
  .[0] as $v | .[1] as $b |
  $b.format == 1 and $b.complete == true and $b.implementation == "MLF" and
  $b.toolchain.compiler == {path:$v.compiler,sha256:$v.compiler_sha256} and
  $b.toolchain.manager == {path:$v.manager,sha256:$v.manager_sha256} and
  ($b.scheduler | length) == 1 and ($b.scheduler_results | length) == 1 and
  $b.scheduler[0].helper.sha256 == $v.build_runner_sha256 and
  $b.scheduler_results[0].complete == true and
  $b.scheduler_results[0].exit_code == 0 and
  $b.scheduler[0].invocation_id == $b.scheduler_results[0].invocation_id and
  $b.scheduler_results[0].jobs == $v.suite_builds[0].jobs and
  ($b.scheduler_results[0].maximum_parallel_jobs >= 0 and
   $b.scheduler_results[0].maximum_parallel_jobs <= $v.suite_builds[0].jobs) and
  ([$b."pending-publications"[].name] | sort) == $targets and
  ([$b."pending-publications"[].key] | unique | length) == ($targets | length) and
  all($targets[]; . as $name |
    [$b.builds[] | select(.kind == "executable mlf-tests:" + $name) | .key] as $keys |
    ($keys | length) == 1 and ($keys[0] | test("^[0-9a-f]{64}$")) and
    [$b."pending-publications"[] | select(.name == $name and .key == $keys[0]) | .files.program] == [$v.prepared_suite_targets[$name].sha256])
' "$report" "$build" >/dev/null
while IFS=$'\t' read -r name hash; do
  binary="$unit/suite-build/bin/$name"
  test -f "$binary" && test ! -L "$binary"
  test "$(sha256 "$binary")" = "$hash"
  if [ "$name" != int-set-unions ]; then
    jq -e --arg name "$name" --arg hash "$hash" '.suites[$name].binary_sha256 == $hash' "$report" >/dev/null
  fi
done < <(jq -r '.prepared_suite_targets | to_entries[] | [.key,.value.sha256] | @tsv' "$report")
# Retain every actual subreceipt; a full aggregate cannot stand in for a shard.
for name in core core-crates core-solver core-language core-modules; do
  test "$(sha256 "$unit/$name.coverage.jsonl")" = "$(jq -er --arg name "$name" '.suites[$name].coverage_report_sha256' "$report")"
  test "$(sha256 "$unit/$name.families.jsonl")" = "$(jq -er --arg name "$name" '.family_reports[$name].sha256' "$report")"
  test "$(sha256 "$unit/$name.log")" = "$(jq -er --arg name "$name" '.suites[$name].log_sha256' "$report")"
  if [ "$name" != core ]; then
    jq -se '
      .[0].event == "start" and .[0].scope == "partial" and
      .[-1].event == "summary" and .[-1].complete == true and
      ([.[] | select(.event == "start")] | length) == 1 and
      ([.[] | select(.event == "summary")] | length) == 1
    ' "$unit/$name.coverage.jsonl" >/dev/null
    jq -se '
      .[0].event == "start" and .[0].scope == "partial" and
      .[-1].event == "summary" and .[-1].complete == true and
      ([.[] | select(.event == "start")] | length) == 1 and
      ([.[] | select(.event == "summary")] | length) == 1 and
      all(.[] | select(.event == "family"); .status == "passed") and
      ([.[] | select(.event == "family")] | length) > 0 and
      .[0].selected == [.[] | select(.event == "family") | .id] and
      .[-1].families == ([.[] | select(.event == "family")] | length)
    ' "$unit/$name.families.jsonl" >/dev/null
  fi
done
# Recompute the exact aggregate from actual subreport bodies and compare the
# full inventory. Never accept planned IDs, counts alone or duplicated rows.
jq -se --slurpfile inventory "$root/tests/golden/unit-inventory.json" '
  def shape:
    (keys | sort) ==
      ((["schema_version","suite","event"] +
        (if .event == "start" then ["scope"]
         elif .event == "case" then ["id","status"]
         elif .event == "alias" then ["id","canonical","status"]
         elif .event == "metric" then ["name","value"]
         elif .event == "summary" then ["complete","executions","aliases","metrics"]
         else ["invalid_event"] end)) | sort);

  . as $rows | $inventory[0].suites.core as $wanted |
  all(.[]; shape and .schema_version == 1 and .suite == "core") and
  .[0].event == "start" and .[0].scope == "full" and
  .[-1].event == "summary" and .[-1].complete == true and
  ([.[] | select(.event == "start")] | length) == 1 and
  ([.[] | select(.event == "summary")] | length) == 1 and
  ([.[] | select(.event == "case") | .id] | sort) == ($wanted.executions | sort) and
  ([.[] | select(.event == "case") | .id] | length) == ($wanted.executions | length) and
  all(.[] | select(.event == "case" or .event == "alias"); .status == "passed") and
  ([.[] | select(.event == "alias") | {key:.id,value:.canonical}] | from_entries) == $wanted.aliases and
  ([.[] | select(.event == "alias")] | length) == ($wanted.aliases | length) and
  ([.[] | select(.event == "metric") | {key:.name,value:.value}] | from_entries) == $wanted.metrics and
  ([.[] | select(.event == "metric")] | length) == ($wanted.metrics | length) and
  .[-1].executions == ($wanted.executions | length) and
  .[-1].aliases == ($wanted.aliases | length) and .[-1].metrics == ($wanted.metrics | length)
' "$unit/core.coverage.jsonl" >/dev/null
cmp <(jq -cs 'map(select(.event != "start" and .event != "summary"))' \
  "$unit/core-crates.coverage.jsonl" "$unit/core-solver.coverage.jsonl" "$unit/core-language.coverage.jsonl" "$unit/core-modules.coverage.jsonl") \
  <(jq -cs 'map(select(.event != "start" and .event != "summary"))' "$unit/core.coverage.jsonl")
jq -se --slurpfile catalog "$root/tests/test-catalog.json" '
  .[0].event == "start" and .[0].scope == "full" and
  .[0].selected == [$catalog[0].families[] | select(.unit == "core") | .id] and
  ([.[] | select(.event == "start")] | length) == 1 and
  ([.[] | select(.event == "summary")] | length) == 1 and
  all(.[]; .event == "start" or .event == "family" or .event == "summary") and
  .[-1].event == "summary" and .[-1].complete == true and .[-1].families == 34 and
  all(.[]; .schema_version == 1 and .unit == "core") and
  [.[] | select(.event == "family") | select(.status == "passed") | .id] ==
    [$catalog[0].families[] | select(.unit == "core") | .id]
' "$unit/core.families.jsonl" >/dev/null
cmp <(jq -cs '[.[] | select(.event == "family") | .id] | sort' \
  "$unit/core-crates.families.jsonl" "$unit/core-solver.families.jsonl" "$unit/core-language.families.jsonl" "$unit/core-modules.families.jsonl") \
  <(jq -cs '[.[] | select(.event == "family") | .id] | sort' "$unit/core.families.jsonl")
printf '%s\n' 'All nine unit binaries, one build DAG and exact Core evidence union verified.'
