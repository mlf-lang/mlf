#!/usr/bin/env bash
# Transport/provenance fault injection, not compiler qualification evidence.
set -euo pipefail
scripts=$(cd -- "$(dirname -- "$0")" && pwd)
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
checkout="$scratch/checkout with spaces"
mkdir -p "$checkout/tools/release" "$scratch/tools"
cp "$scripts/shared-candidate.sh" "$scripts/native-ci.sh" "$scripts/qualification-jobs.sh" "$checkout/tools/release/"
printf ':\n' > "$checkout/tools/release/native-environment.sh"
cd "$checkout"
export PATH="$scratch/tools:$PATH"
export GITHUB_ENV="$scratch/github-env"
export TEST_SHARED_CALLS="$scratch/calls"
for tool in clang pkg-config; do printf '#!/bin/sh\nexit 0\n' > "$scratch/tools/$tool"; chmod +x "$scratch/tools/$tool"; done
printf '{"format":1}\n' > mlf-package.json
printf 'source fixture\n' > source.emlf
cat > mlfpkg <<'SH'
#!/bin/sh
printf '%s\n' "$*" >> "$TEST_SHARED_CALLS"
case "$*" in '--locked plan') printf '{}\n' ;; *) exit 99 ;; esac
SH
chmod +x mlfpkg
printf '.mlf-build/\n' > .gitignore
git init -q
git add .
git -c user.name=Test -c user.email=test@example.invalid commit -qm fixture
sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi | awk '{print $1}'; }
compiler_key=$(printf '%064d' 1)
manager_key=$(printf '%064d' 2)
runner_key=$(printf '%064d' 3)
port_key=$(printf '%064d' 4)
mkdir -p .mlf-build/bin .mlf-build/prerequisites/{tests,compiler-tests}
for pair in "emlf:$compiler_key" "mlfpkg:$manager_key" "compiler-tests:$runner_key" "port:$port_key"; do
  name=${pair%%:*}; key=${pair#*:}
  mkdir -p ".mlf-build/cache/$key"
  printf '#!/bin/sh\nprintf "ran %s\\n" >> "$TEST_SHARED_CALLS"\n' "$name" > ".mlf-build/cache/$key/program"
  chmod +x ".mlf-build/cache/$key/program"
  cp ".mlf-build/cache/$key/program" ".mlf-build/bin/$name"
  printf '%s\n' '{}' > ".mlf-build/cache/$key/dependency-files.json"
  printf 'metadata fixture\n' > ".mlf-build/cache/$key/unit.mlfci"
  printf 'object fixture\n' > ".mlf-build/cache/$key/unit.mlfco"
  jq -n --arg key "$key" --arg binary "$(sha256 ".mlf-build/cache/$key/program")" \
    --arg proof "$(sha256 ".mlf-build/cache/$key/dependency-files.json")" \
    --arg metadata "$(sha256 ".mlf-build/cache/$key/unit.mlfci")" --arg object "$(sha256 ".mlf-build/cache/$key/unit.mlfco")" \
    '{key:$key,inputs:{},files:{program:$binary,"dependency-files.json":$proof,"unit.mlfci":$metadata,"unit.mlfco":$object}}' > ".mlf-build/cache/$key/artifact.json"
done
printf '#!/bin/sh\nprintf "1\\n"\n' > .mlf-build/bin/mlf-build-runner
chmod +x .mlf-build/bin/mlf-build-runner
jq -n --arg root "$PWD" --arg compiler "$(sha256 .mlf-build/bin/emlf)" --arg manager "$(sha256 .mlf-build/bin/mlfpkg)" \
  --arg helper "$(sha256 .mlf-build/bin/mlf-build-runner)" --arg clang "$(command -v clang)" --arg clang_hash "$(sha256 "$(command -v clang)")" \
  --arg pkg "$(command -v pkg-config)" --arg pkg_hash "$(sha256 "$(command -v pkg-config)")" \
  --arg manifest "$(sha256 mlf-package.json)" --arg source "$(sha256 source.emlf)" '
  {format:1,complete:true,implementation:"MLF",cache_directory:($root+"/.mlf-build/cache"),
   packages:{packages:[{path:".",name:"mlf-compiler",manifest:$manifest,sources:{"source.emlf":$source}}]},
   toolchain:{compiler:{path:($root+"/.mlf-build/bin/emlf"),sha256:$compiler},manager:{path:($root+"/.mlf-build/bin/mlfpkg"),sha256:$manager},
    clang:{path:$clang,sha256:$clang_hash},"pkg-config":{path:$pkg,sha256:$pkg_hash},runtime:{},gmp:{libraries:{},headers:{}},native_environment:{CPATH:""}},
   scheduler:[{invocation_id:"fixture",helper:{path:($root+"/.mlf-build/bin/mlf-build-runner"),sha256:$helper}}],
   scheduler_results:[{complete:true,invocation_id:"fixture",jobs:1,maximum_parallel_jobs:1}]}' > "$scratch/base.json"
jq --arg compiler "$compiler_key" --arg manager "$manager_key" '. + {builds:[{kind:"executable mlf-compiler:emlf",key:$compiler},{kind:"executable mlf-compiler:mlfpkg",key:$manager}]}' "$scratch/base.json" > .mlf-build/build-report.json
jq --arg key "$port_key" '. + {builds:[{kind:"executable mlf-tests:port",key:$key}]}' "$scratch/base.json" > .mlf-build/prerequisites/tests/build-report.json
jq --arg key "$runner_key" '. + {builds:[{kind:"executable mlf-compiler:compiler-tests",key:$key}]}' "$scratch/base.json" > .mlf-build/prerequisites/compiler-tests/build-report.json
for row in "emlf:$compiler_key:.mlf-build/build-report.json" "mlfpkg:$manager_key:.mlf-build/build-report.json" "compiler-tests:$runner_key:.mlf-build/prerequisites/compiler-tests/build-report.json"; do
  name=${row%%:*}; rest=${row#*:}; key=${rest%%:*}; report=${rest#*:}
  jq --arg name "$name" --arg key "$key" --arg artifact "$PWD/.mlf-build/cache/$key" \
    --slurpfile stamp ".mlf-build/cache/$key/artifact.json" \
    '."pending-publications" += [{name:$name,key:$key,artifact:$artifact,binary:($artifact+"/program"),files:$stamp[0].files}]' "$report" > "$scratch/report.tmp"
  mv "$scratch/report.tmp" "$report"
done
unset CPATH
passed=0
pass() { passed=$((passed + 1)); printf 'ok %d - %s\n' "$passed" "$1"; }
reject() {
  if tools/release/shared-candidate.sh verify > "$scratch/rejected.log" 2>&1; then printf 'Unexpected acceptance: %s\n' "$1" >&2; exit 1; fi
  pass "$1"
}
tools/release/shared-candidate.sh export
pass 'exports final-compiler runner and all producer proof files'
tools/release/shared-candidate.sh verify
pass 'authentic candidate verifies'
# Fresh transport hashes cannot authorize outputs different from the authentic
# producer publication, even when the mutated cache stamp is self-consistent.
for pair in "emlf:$compiler_key" "mlfpkg:$manager_key" "compiler-tests:$runner_key"; do
  name=${pair%%:*}; key=${pair#*:}
  cp ".mlf-build/bin/$name" "$scratch/unchanged-binary"
  cp ".mlf-build/cache/$key/artifact.json" "$scratch/unchanged-stamp"
  printf 'changed before export\n' >> ".mlf-build/bin/$name"
  cp ".mlf-build/bin/$name" ".mlf-build/cache/$key/program"
  jq --arg hash "$(sha256 ".mlf-build/bin/$name")" '.files.program=$hash' "$scratch/unchanged-stamp" > ".mlf-build/cache/$key/artifact.json"
  mv .mlf-build/shared-candidate "$scratch/valid-transport"
  if tools/release/shared-candidate.sh export > "$scratch/rejected.log" 2>&1; then
    printf 'Export accepted changed original publication: %s\n' "$name" >&2; exit 1
  fi
  rm -rf .mlf-build/shared-candidate
  mv "$scratch/valid-transport" .mlf-build/shared-candidate
  cp "$scratch/unchanged-binary" ".mlf-build/bin/$name"
  cp "$scratch/unchanged-binary" ".mlf-build/cache/$key/program"
  cp "$scratch/unchanged-stamp" ".mlf-build/cache/$key/artifact.json"
  pass "changed original $name publication rejected before export"
done
mv ".mlf-build/cache/$runner_key/dependency-files.json" "$scratch/unchanged-dependencies"
mv .mlf-build/shared-candidate "$scratch/valid-transport"
if tools/release/shared-candidate.sh export > "$scratch/rejected.log" 2>&1; then
  printf 'Export accepted missing runner dependency receipt\n' >&2; exit 1
fi
rm -rf .mlf-build/shared-candidate
mv "$scratch/valid-transport" .mlf-build/shared-candidate
mv "$scratch/unchanged-dependencies" ".mlf-build/cache/$runner_key/dependency-files.json"
pass 'missing executable dependency proof rejected before export'
cp .mlf-build/shared-candidate/manifest.json "$scratch/manifest.json"
printf 'changed\n' >> .mlf-build/bin/compiler-tests
reject 'changed runner bytes rejected'
cp ".mlf-build/cache/$runner_key/program" .mlf-build/bin/compiler-tests
printf 'changed\n' >> source.emlf
reject 'stale runner source snapshot rejected'
printf 'source fixture\n' > source.emlf
CPATH=changed tools/release/shared-candidate.sh verify > "$scratch/rejected.log" 2>&1 && exit 1
pass 'changed native environment rejected'
for field in source platform root; do
  jq --arg field "$field" '.[$field] = "wrong"' "$scratch/manifest.json" > .mlf-build/shared-candidate/manifest.json
  reject "wrong $field rejected"
done
cp "$scratch/manifest.json" .mlf-build/shared-candidate/manifest.json
report=.mlf-build/prerequisites/compiler-tests/build-report.json
cp "$report" "$scratch/runner-report.json"
jq '.toolchain.compiler.path = "/stale/bootstrap/compiler"' "$scratch/runner-report.json" > "$report"
# Re-sign the transport hashes to reach the semantic final-compiler guard.
jq --arg path "$PWD/$report" --arg relative "$report" --arg hash "$(sha256 "$report")" \
  '.inputs[$path]=$hash | .files[$relative]=$hash | .campaign_runner.report_sha256=$hash' "$scratch/manifest.json" > .mlf-build/shared-candidate/manifest.json
reject 'seed-built runner rejected even with matching transport hashes'
cp "$scratch/runner-report.json" "$report"
cp "$scratch/manifest.json" .mlf-build/shared-candidate/manifest.json
printf 'changed\n' >> ".mlf-build/cache/$runner_key/dependency-files.json"
reject 'changed dependency receipt rejected'
printf '{}\n' > ".mlf-build/cache/$runner_key/dependency-files.json"
# Consumers start with transport only and cannot perform a local rebuild.
mv .mlf-build/bin "$scratch/bin-backup"
mv .mlf-build/cache "$scratch/cache-backup"
rm .mlf-build/build-report.json .mlf-build/prerequisites/tests/build-report.json "$report"
tools/release/shared-candidate.sh import
pass 'clean consumer imports original binary and build proof'
export MLF_CI_SHARED_CANDIDATE=1
export MLF_COMPILER="$PWD/.mlf-build/bin/emlf"
export MLF_PACKAGE_MANAGER="$PWD/.mlf-build/bin/mlfpkg"
export MLF_BUILD_RUNNER="$PWD/.mlf-build/bin/mlf-build-runner"
tools/release/native-ci.sh unit > "$scratch/native-ci.log" 2>&1
test "$(grep -c '^ran compiler-tests$' "$TEST_SHARED_CALLS")" = 1
test "$(grep -c '^--locked plan$' "$TEST_SHARED_CALLS")" = 1
! grep -q 'build --target' "$TEST_SHARED_CALLS"
pass 'consumer executes a fresh campaign without rebuilding runner'
printf '%s shared candidate transport checks passed\n' "$passed"
