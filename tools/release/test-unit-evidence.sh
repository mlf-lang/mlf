#!/usr/bin/env bash
# Synthetic transport receipts exercise the package boundary, not test verdicts.
set -euo pipefail
scripts=$(cd -- "$(dirname -- "$0")" && pwd)
root=$(cd "$scripts/../.." && pwd)
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
unit="$scratch/unit"
mkdir -p "$unit/suite-build/bin" "$unit/suite-build-invocation-fixture"
sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi | awk '{print $1}'; }
targets='["core-crates","core-language","core-modules","core-solver","figure12","harness","int-set-unions","regex","test-framework"]'
shards='["core-crates","core-solver","core-language","core-modules"]'
report="$unit/verification.json"
jq -n --argjson shards "$shards" --arg digest "$(printf '%064d' 7)" \
  '{complete:true,implementation:"MLF",group:"unit",scope:"full",compiler:"/compiler",compiler_sha256:$digest,
    manager:"/manager",manager_sha256:$digest,build_runner_sha256:$digest,
    prepared_suite_targets:{},suite_builds:[],family_reports:{},suites:{core:{aggregate:true,scope:"full",targets:$shards,components:{}}}}' > "$report"
# Fixture shards partition real catalog metadata. They are synthetic reports;
# they never claim that the compiler actions ran.
jq '[.families[] | select(.unit == "core")] | [.[0:9],.[9:18],.[18:26],.[26:34]]' "$root/tests/test-catalog.json" > "$scratch/families.json"
index=0
for name in core-crates core-solver core-language core-modules; do
  jq -c --argjson index "$index" '
    .[$index] as $families |
    [$families[] | .evidence.executions[] | {schema_version:1,suite:"core",event:"case",id:.,status:"passed"}] +
    [$families[] | .evidence.aliases | to_entries[] | {schema_version:1,suite:"core",event:"alias",id:.key,canonical:.value,status:"passed"}] +
    [$families[] | .evidence.metrics | to_entries[] | {schema_version:1,suite:"core",event:"metric",name:.key,value:.value}] |
    [{schema_version:1,suite:"core",event:"start",scope:"partial"}] + . +
    [{schema_version:1,suite:"core",event:"summary",complete:true,
      executions:([.[] | select(.event=="case")]|length),aliases:([.[]|select(.event=="alias")]|length),metrics:([.[]|select(.event=="metric")]|length)}] | .[]
  ' "$scratch/families.json" > "$unit/$name.coverage.jsonl"
  jq -c --argjson index "$index" '
    .[$index] | map(.id) as $ids |
    [{schema_version:1,unit:"core",event:"start",scope:"partial",selected:$ids}] +
    [$ids[] | {schema_version:1,unit:"core",event:"family",id:.,status:"passed"}] +
    [{schema_version:1,unit:"core",event:"summary",complete:true,families:($ids|length)}] | .[]
  ' "$scratch/families.json" > "$unit/$name.families.jsonl"
  index=$((index+1))
done
jq -cs 'map(select(.event != "start" and .event != "summary")) |
  [{schema_version:1,suite:"core",event:"start",scope:"full"}] + . +
  [{schema_version:1,suite:"core",event:"summary",complete:true,
    executions:([.[] | select(.event=="case")]|length),aliases:([.[]|select(.event=="alias")]|length),metrics:([.[]|select(.event=="metric")]|length)}] | .[]' \
  "$unit/core-crates.coverage.jsonl" "$unit/core-solver.coverage.jsonl" "$unit/core-language.coverage.jsonl" "$unit/core-modules.coverage.jsonl" > "$unit/core.coverage.jsonl"
jq -c '[.families[] | select(.unit=="core") | .id] as $ids |
  [{schema_version:1,unit:"core",event:"start",scope:"full",selected:$ids}] +
  [$ids[] | {schema_version:1,unit:"core",event:"family",id:.,status:"passed"}] +
  [{schema_version:1,unit:"core",event:"summary",complete:true,families:($ids|length)}] | .[]' "$root/tests/test-catalog.json" > "$unit/core.families.jsonl"
for name in core core-crates core-solver core-language core-modules; do
  printf 'synthetic %s fixture\n' "$name" > "$unit/$name.log"
  scope=partial; test "$name" != core || scope=full
  jq --arg name "$name" --arg scope "$scope" --arg log "$(sha256 "$unit/$name.log")" \
    --arg coverage "$(sha256 "$unit/$name.coverage.jsonl")" --arg family "$(sha256 "$unit/$name.families.jsonl")" '
    .suites[$name] += {scope:$scope,log_sha256:$log,coverage_report_sha256:$coverage} |
    .family_reports[$name]={sha256:$family,result:{scope:$scope}}' "$report" > "$scratch/report.tmp"
  mv "$scratch/report.tmp" "$report"
done
while IFS= read -r name; do
  printf 'binary %s\n' "$name" > "$unit/suite-build/bin/$name"
  jq --arg name "$name" --arg path "$unit/suite-build/bin/$name" --arg hash "$(sha256 "$unit/suite-build/bin/$name")" '
    .prepared_suite_targets[$name]={path:$path,sha256:$hash} |
    if $name == "int-set-unions" then . else .suites[$name].binary_sha256=$hash end' "$report" > "$scratch/report.tmp"
  mv "$scratch/report.tmp" "$report"
done < <(jq -rn --argjson targets "$targets" '$targets[]')
build="$unit/suite-build-invocation-fixture/build-report.json"
jq --arg key "$(printf '%064d' 1)" '
  . as $v | {format:1,complete:true,implementation:"MLF",
   toolchain:{compiler:{path:$v.compiler,sha256:$v.compiler_sha256},manager:{path:$v.manager,sha256:$v.manager_sha256}},
   scheduler:[{invocation_id:"fixture",helper:{sha256:$v.build_runner_sha256}}],
   scheduler_results:[{complete:true,invocation_id:"fixture",jobs:1}],
   builds:[$v.prepared_suite_targets|keys[]|{kind:("executable mlf-tests:"+.),key:$key}],
   "pending-publications":[$v.prepared_suite_targets|to_entries[]|{name:.key,key:$key,files:{program:.value.sha256}}]}' "$report" > "$build"
jq --arg path "$build" --arg hash "$(sha256 "$build")" --argjson targets "$targets" --argjson shards "$shards" '
  .suite_builds=[{path:$path,sha256:$hash,targets:$targets,jobs:1,exit_code:0}] |
  . as $v | .suites.core.components=([$shards[]|{key:.,value:$v.suites[.]}]|from_entries)' "$report" > "$scratch/report.tmp"
mv "$scratch/report.tmp" "$report"
cp -R "$unit" "$scratch/original"
passed=0
check() { passed=$((passed+1)); printf 'ok %d - %s\n' "$passed" "$1"; }
reject() {
  if "$scripts/verify-unit-evidence.sh" "$unit" > "$scratch/verify.log" 2>&1; then printf 'Unexpected acceptance: %s\n' "$1" >&2; exit 1; fi
  check "$1"
  rm -rf "$unit"; cp -R "$scratch/original" "$unit"
}
"$scripts/verify-unit-evidence.sh" "$unit"
check 'authentic complete fixture checks all nine binaries and exact union'
printf 'corrupt\n' >> "$unit/suite-build/bin/core-modules"
reject 'changed shard binary rejected'
printf 'corrupt\n' >> "$unit/suite-build/bin/int-set-unions"
reject 'changed CLI helper binary rejected'
rm "$unit/core-solver.families.jsonl"
reject 'missing partial family receipt rejected'
jq '.suites.core.binary_sha256="invented"' "$report" > "$scratch/report.tmp"; mv "$scratch/report.tmp" "$report"
reject 'invented aggregate binary rejected'
jq '.prepared_suite_targets |= del(."core-language")' "$report" > "$scratch/report.tmp"; mv "$scratch/report.tmp" "$report"
reject 'missing physical target rejected'
jq '.suite_builds[0].targets += ["core-crates"]' "$report" > "$scratch/report.tmp"; mv "$scratch/report.tmp" "$report"
reject 'duplicated build target rejected'
jq '.suites."core-crates".scope="full" | .suites.core.components."core-crates".scope="full"' "$report" > "$scratch/report.tmp"; mv "$scratch/report.tmp" "$report"
reject 'partial shard cannot claim full scope'
printf 'changed\n' >> "$build"
reject 'changed original invocation report rejected'
# Re-sign the envelope to reach the build/compiler provenance guard.
jq '.toolchain.compiler.path="/other-compiler"' "$build" > "$scratch/build.tmp"; mv "$scratch/build.tmp" "$build"
jq --arg hash "$(sha256 "$build")" '.suite_builds[0].sha256=$hash' "$report" > "$scratch/report.tmp"; mv "$scratch/report.tmp" "$report"
reject 'different compile tool rejected despite report rehash'
# A consistently rehashed child+aggregate must still match the independent
# reviewed inventory; jq false must be a failing process, not just printed false.
altered=$(jq -sr '[.[] | select(.event == "case")][0].id' "$unit/core-crates.coverage.jsonl")
for name in core-crates core; do
  jq -c --arg altered "$altered" 'if .event == "case" and .id == $altered then .id += " altered" else . end' "$unit/$name.coverage.jsonl" > "$scratch/coverage.tmp"
  mv "$scratch/coverage.tmp" "$unit/$name.coverage.jsonl"
  jq --arg name "$name" --arg hash "$(sha256 "$unit/$name.coverage.jsonl")" \
    '.suites[$name].coverage_report_sha256=$hash | if $name == "core" then . else .suites.core.components[$name].coverage_report_sha256=$hash end' "$report" > "$scratch/report.tmp"
  mv "$scratch/report.tmp" "$report"
done
reject 'consistently rehashed altered inventory is rejected'
printf '%d split unit evidence checks passed\n' "$passed"
