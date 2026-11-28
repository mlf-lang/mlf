#!/usr/bin/env bash
# Synthetic transport receipts exercise the package boundary, not test verdicts.
set -euo pipefail
. "$(dirname -- "$0")/test-events.sh" release-unit-evidence
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
jq '[.families[] | select(.unit == "core")] | [.[0:9],.[9:18],.[18:26],.[26:35]]' "$root/tests/test-catalog.json" > "$scratch/families.json"
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
  jq --argjson index "$index" --slurpfile contract "$root/tests/golden/core-registry-contract.json" '
    [.[$index][].id] as $families |
    [$contract[0].cases[] | select(.family as $family | $families | index($family)) |
     {id,name,tags:["family:" + .family]}] as $cases |
    {schema_version:1,event:"inventory",scope:"full",total:($cases|length),selected:($cases|length),cases:$cases}
  ' "$scratch/families.json" > "$unit/$name.inventory.json"
  jq -c '
    .cases as $cases | ($cases|length) as $count |
    [{schema_version:1,event:"start",scope:"full",total:$count,selected:$count,ids:[$cases[].id]}] +
    [$cases[] | . + {schema_version:1,event:"case",status:"passed"}] +
    [{schema_version:1,event:"summary",scope:"full",total:$count,selected:$count,
      executed:$count,passed:$count,failed:0,complete:true}] | .[]
  ' "$unit/$name.inventory.json" > "$unit/$name.cases.jsonl"
  index=$((index+1))
done
for name in core-crates core-solver core-language core-modules; do
  jq --arg name "$name" --arg contract "$(sha256 "$root/tests/golden/core-registry-contract.json")" \
    --arg discovery "$(sha256 "$unit/$name.inventory.json")" \
    --arg cases "$(sha256 "$unit/$name.cases.jsonl")" \
    --slurpfile inventory "$unit/$name.inventory.json" '
    .suites[$name] += {registry_inventory:{path:("/old/location/"+$name+".inventory.json"),sha256:$discovery,
      contract_path:"/old/source/core-registry-contract.json",contract_sha256:$contract},
      case_report:("/old/location/"+$name+".cases.jsonl"),case_report_sha256:$cases,
      framework_case_ids:[$inventory[0].cases[].id]}' "$report" > "$scratch/report.tmp"
  mv "$scratch/report.tmp" "$report"
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
jq '
  . as $v | {format:1,complete:true,implementation:"MLF",
   toolchain:{compiler:{path:$v.compiler,sha256:$v.compiler_sha256},manager:{path:$v.manager,sha256:$v.manager_sha256}},
   scheduler:[{invocation_id:"fixture",helper:{sha256:$v.build_runner_sha256}}],
   scheduler_results:[{complete:true,exit_code:0,invocation_id:"fixture",jobs:1,maximum_parallel_jobs:1}],
   builds:[$v.prepared_suite_targets|to_entries[]|{kind:("executable mlf-tests:"+.key),key:.value.sha256}],
   "pending-publications":[$v.prepared_suite_targets|to_entries[]|{name:.key,key:.value.sha256,files:{program:.value.sha256}}]}' "$report" > "$build"
jq --arg path "$build" --arg hash "$(sha256 "$build")" --argjson targets "$targets" --argjson shards "$shards" '
  .suite_builds=[{path:$path,sha256:$hash,targets:$targets,jobs:1,exit_code:0}] |
  . as $v | .suites.core.components=([$shards[]|{key:.,value:$v.suites[.]}]|from_entries)' "$report" > "$scratch/report.tmp"
mv "$scratch/report.tmp" "$report"
cp -R "$unit" "$scratch/original"
passed=0
check() { passed=$((passed+1)); printf 'ok %d - %s\n' "$passed" "$1"; release_pass; }
reject() {
  local identity=$1
  shift
  release_begin "release/unit-evidence/$identity"
  local status=0
  "$scripts/verify-unit-evidence.sh" "$unit" > "$scratch/verify.log" 2>&1 || status=$?
  if [ "$status" = 0 ]; then printf 'Unexpected acceptance: %s\n' "$1" >&2; false; fi
  if [ -n "${2:-}" ] && [ "$status" != "$2" ]; then
    cat "$scratch/verify.log" >&2
    printf 'Wrong rejection status for %s: expected %s, got %s\n' "$1" "$2" "$status" >&2
    false
  fi
  check "$1"
  rm -rf "$unit"; cp -R "$scratch/original" "$unit"
}
release_begin release/unit-evidence/valid
"$scripts/verify-unit-evidence.sh" "$unit"
check 'authentic complete fixture checks all nine binaries and exact union'
# These leading predicates must reject as boolean false, not lose the input
# report at the later shard binding (jq 1.7 versus 1.8 precedence differs).
for mutation in incomplete wrong-implementation wrong-group partial-unit; do
  case "$mutation" in
    incomplete) edit='.complete=false' ;;
    wrong-implementation) edit='.implementation="other"' ;;
    wrong-group) edit='.group="other"' ;;
    partial-unit) edit='.scope="partial"' ;;
  esac
  jq "$edit" "$report" > "$scratch/report.tmp"; mv "$scratch/report.tmp" "$report"
  reject "envelope/$mutation" "$mutation envelope is rejected as false" 1
done
printf 'corrupt\n' >> "$unit/suite-build/bin/core-modules"
reject changed-shard-binary 'changed shard binary rejected'
printf 'corrupt\n' >> "$unit/suite-build/bin/int-set-unions"
reject changed-cli-helper 'changed CLI helper binary rejected'
rm "$unit/core-solver.families.jsonl"
reject missing-partial-receipt 'missing partial family receipt rejected'
jq '.suites.core.binary_sha256="invented"' "$report" > "$scratch/report.tmp"; mv "$scratch/report.tmp" "$report"
reject invented-aggregate-binary 'invented aggregate binary rejected'
jq '.prepared_suite_targets |= del(."core-language")' "$report" > "$scratch/report.tmp"; mv "$scratch/report.tmp" "$report"
reject missing-target 'missing physical target rejected'
jq '.suite_builds[0].targets += ["core-crates"]' "$report" > "$scratch/report.tmp"; mv "$scratch/report.tmp" "$report"
reject duplicate-target 'duplicated build target rejected'
jq '.suites."core-crates".scope="full" | .suites.core.components."core-crates".scope="full"' "$report" > "$scratch/report.tmp"; mv "$scratch/report.tmp" "$report"
reject wrong-scope 'partial shard cannot claim full scope'
printf 'changed\n' >> "$build"
reject changed-invocation 'changed original invocation report rejected'
# Re-sign the envelope to reach the build/compiler provenance guard.
jq '.toolchain.compiler.path="/other-compiler"' "$build" > "$scratch/build.tmp"; mv "$scratch/build.tmp" "$build"
jq --arg hash "$(sha256 "$build")" '.suite_builds[0].sha256=$hash' "$report" > "$scratch/report.tmp"; mv "$scratch/report.tmp" "$report"
reject different-compile-tool 'different compile tool rejected despite report rehash'
for mutation in failed-scheduler repeated-key over-parallel; do
  case "$mutation" in
    failed-scheduler) edit='.scheduler_results[0].exit_code=7' ;;
    repeated-key) edit='."pending-publications"[1].key=."pending-publications"[0].key | .builds[1].key=.builds[0].key' ;;
    over-parallel) edit='.scheduler_results[0].maximum_parallel_jobs=3' ;;
  esac
  jq "$edit" "$build" > "$scratch/build.tmp"; mv "$scratch/build.tmp" "$build"
  jq --arg hash "$(sha256 "$build")" '.suite_builds[0].sha256=$hash' "$report" > "$scratch/report.tmp"; mv "$scratch/report.tmp" "$report"
  reject "receipt/$mutation" "$mutation rejected despite report rehash"
done
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
reject rehashed-inventory 'consistently rehashed altered inventory is rejected'
resign_registry() {
  local name=core-crates
  jq --arg name "$name" --arg discovery "$(sha256 "$unit/$name.inventory.json")" \
    --arg cases "$(sha256 "$unit/$name.cases.jsonl")" --slurpfile rows "$unit/$name.cases.jsonl" '
    .suites[$name].registry_inventory.sha256=$discovery |
    .suites[$name].case_report_sha256=$cases |
    .suites[$name].framework_case_ids=[$rows[]|select(.event=="case")|.id] |
    .suites.core.components[$name]=.suites[$name]' "$report" > "$scratch/report.tmp"
  mv "$scratch/report.tmp" "$report"
}
# Reformat and add unrelated descriptors without changing public identities.
release_begin release/unit-evidence/registry-formatting
jq '.cases |= map(. + {elapsed:7} | .tags += ["new-classification"])' "$unit/core-crates.inventory.json" > "$scratch/discovery.tmp"
mv "$scratch/discovery.tmp" "$unit/core-crates.inventory.json"
jq 'if .event == "case" then . + {elapsed:7} | .tags += ["new-classification"] else . end' \
  "$unit/core-crates.cases.jsonl" > "$scratch/cases.tmp"
mv "$scratch/cases.tmp" "$unit/core-crates.cases.jsonl"
resign_registry
"$scripts/verify-unit-evidence.sh" "$unit" > "$scratch/verify.log"
check 'registry formatting and unrelated metadata remain free to change'
rm -rf "$unit"; cp -R "$scratch/original" "$unit"
rm "$unit/core-crates.inventory.json"
reject missing-registry-discovery 'missing actual registry discovery is rejected'
printf '\n' >> "$unit/core-crates.inventory.json"
reject changed-registry-discovery 'changed retained discovery bytes are rejected'
jq '.suites."core-crates".registry_inventory.contract_sha256="unreviewed" |
    .suites.core.components."core-crates"=.suites."core-crates"' "$report" > "$scratch/report.tmp"
mv "$scratch/report.tmp" "$report"
reject changed-registry-contract 'changed registry contract binding is rejected'
rm "$unit/core-crates.cases.jsonl"
reject missing-semantic-case-report 'missing semantic case observations are rejected'
for mutation in id name family duplicate missing; do
  case "$mutation" in
    id) edit='.id += "-changed"' ;;
    name) edit='.name += " changed"' ;;
    family) edit='.tags=["family:core/unknown"]' ;;
    duplicate) edit='.' ;;
    missing) edit='.' ;;
  esac
  if [ "$mutation" = duplicate ]; then
    jq '.cases[-1]=.cases[0]' "$unit/core-crates.inventory.json" > "$scratch/discovery.tmp"
  elif [ "$mutation" = missing ]; then
    jq '.cases |= .[:-1] | .total-=1 | .selected-=1' "$unit/core-crates.inventory.json" > "$scratch/discovery.tmp"
  else
    jq ".cases[0] |= ($edit)" "$unit/core-crates.inventory.json" > "$scratch/discovery.tmp"
  fi
  mv "$scratch/discovery.tmp" "$unit/core-crates.inventory.json"
  jq -c '.cases as $cases | ($cases|length) as $count |
    [{schema_version:1,event:"start",scope:"full",total:$count,selected:$count,ids:[$cases[].id]}] +
    [$cases[] | . + {schema_version:1,event:"case",status:"passed"}] +
    [{schema_version:1,event:"summary",scope:"full",total:$count,selected:$count,
      executed:$count,passed:$count,failed:0,complete:true}] | .[]' \
    "$unit/core-crates.inventory.json" > "$unit/core-crates.cases.jsonl"
  resign_registry
  reject "rehashed-registry/$mutation" "consistently rehashed registry $mutation is rejected"
done
jq -c 'if .event == "start" or .event == "summary" then .total += 1 | .scope="partial" else . end' \
  "$unit/core-crates.cases.jsonl" > "$scratch/cases.tmp"
mv "$scratch/cases.tmp" "$unit/core-crates.cases.jsonl"
resign_registry
reject rehashed-registry/total 'case report cannot inflate the authenticated physical inventory'
printf '%d split unit evidence checks passed\n' "$passed"
