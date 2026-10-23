#!/usr/bin/env bash
# Bounded orchestration controls only: these fake tools do not qualify MLF.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/mlf-timed-async-test.XXXXXXXX")
trap 'rm -rf "$work"' EXIT
project="$work/project"
mkdir -p "$project/tools/release" "$project/scripts" "$project/runtime" "$work/bin"
cp "$root/tools/release/"{timed-bootstrap,summarize-bootstrap}.sh "$project/tools/release/"
printf '{"executables":{"emlf":{}}}\n' > "$project/mlf-package.json"
printf 'runtime fixture\n' > "$project/runtime/mlf_runtime.c"
cat > "$work/bin/uname" <<'SH'
#!/bin/sh
case "$1" in -m) echo arm64 ;; *) echo Darwin ;; esac
SH
for tool in sw_vers sysctl clang; do
  printf '#!/bin/sh\nprintf "fixture host/tool\\n"\n' > "$work/bin/$tool"
done
printf '#!/bin/sh\necho seed\n' > "$work/seed-compiler"
printf '#!/bin/sh\necho seed-manager\n' > "$work/seed-manager"
chmod +x "$work/bin/"* "$work/seed-"*
cat > "$project/tools/release/time-command.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
directory=$1 kind=$2; shift 2
sample=$(mktemp -d "$directory/commands/$kind.XXXXXX")
code=0
"$@" || code=$?
rss=100
if [ "$kind" = async-bootstrap ] && [ "$CONTROL" = rss ]; then rss=2000; fi
jq -n --arg kind "$kind" --argjson rss "$rss" --argjson code "$code" \
  '{kind:$kind,phase:$kind,started_utc:"fixture",complete:true,exit_code:$code,
    wall_seconds:1,user_seconds:1,system_seconds:0,peak_rss_bytes:$rss}' > "$sample/result.json"
exit "$code"
SH
cat > "$project/scripts/bootstrap-async.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
test "$MLF_COMPILER" = "$MLF_TIMING_DIR/bin/emlf"
test "$MLF_PACKAGE_MANAGER" = "$TEST_SEED_MANAGER"
test "$CC" = "$MLF_TIMING_DIR/bin/clang"
test "$CONTROL" != transition-failed || exit 77
b=$MLF_ASYNC_BOOTSTRAP_DIR
mkdir -p "$b/manager/bin"
printf '#!/bin/sh\necho bridge\n' > "$b/stage1"
printf '#!/bin/sh\necho real-stage2\n' > "$b/stage2"
printf '#!/bin/sh\necho current-manager\n' > "$b/manager/bin/mlfpkg"
printf '#!/bin/sh\ntest "$1" = --protocol-version\necho 1\n' > "$b/manager/bin/mlf-build-runner"
chmod +x "$b/stage1" "$b/stage2" "$b/manager/bin/"*
printf '%s\n' "$b/manager/bin/mlfpkg" > "$b/manager.path"
printf '1\n' > "$b/capability.txt"
printf '%064d\n' 1 > "$b/source-identity.txt"
shasum -a 256 "$b/stage1" "$b/stage2" > "$b/compilers.sha256"
shasum -a 256 "$b/manager/bin/mlfpkg" "$b/manager/bin/mlf-build-runner" > "$b/manager.sha256"
case "$CONTROL" in
  bad-capability) printf '0\n' > "$b/capability.txt" ;;
  bad-hash) printf 'modified\n' >> "$b/stage2" ;;
  missing-helper) rm "$b/manager/bin/mlf-build-runner" ;;
esac
SH
cat > "$project/mlfpkg" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
test "$MLF_TIMING_COMPILER" = "$MLF_ASYNC_BOOTSTRAP_DIR/stage2"
test "$MLF_PACKAGE_MANAGER" = "$MLF_ASYNC_BOOTSTRAP_DIR/manager/bin/mlfpkg"
compiler= build= locked=no
while [ "$#" -gt 0 ]; do
  case "$1" in
    --compiler) compiler=$2; shift 2 ;;
    --build-dir) build=$2; shift 2 ;;
    --locked) locked=yes; shift ;;
    *) shift ;;
  esac
done
test "$compiler" = "$MLF_TIMING_DIR/bin/emlf"
test "$locked" = yes
touch "$build/root-invoked"
test "$CONTROL" != root-failed || exit 79
mkdir -p "$build/bin"
cp "$MLF_ASYNC_BOOTSTRAP_DIR/stage2" "$build/bin/emlf"
cp "$MLF_PACKAGE_MANAGER" "$build/bin/mlfpkg"
printf '{"complete":true,"implementation":"MLF"}\n' > "$build/build-report.json"
SH
cat > "$project/tools/release/ensure-build-runner.sh" <<'SH'
#!/bin/sh
set -eu
cp "$MLF_ASYNC_BOOTSTRAP_DIR/manager/bin/mlf-build-runner" "$1/mlf-build-runner"
SH
chmod +x "$project/scripts/bootstrap-async.sh" "$project/mlfpkg" "$project/tools/release/"*.sh
git -C "$project" init -q
git -C "$project" add .
git -C "$project" -c user.name=fixture -c user.email=fixture@example.invalid commit -qm fixture
export PATH="$work/bin:$PATH" TEST_SEED_MANAGER="$work/seed-manager"
checks=0
for control in success transition-failed bad-capability bad-hash missing-helper root-failed rss; do
  build="$work/$control"
  github_env="$work/$control.env"
  status=0
  (cd "$project"; CONTROL="$control" MLF_COMPILER="$work/seed-compiler" \
    MLF_PACKAGE_MANAGER="$TEST_SEED_MANAGER" MLF_BOOTSTRAP_MAX_RSS_BYTES=1500 \
    GITHUB_ENV="$github_env" GITHUB_STEP_SUMMARY= \
    tools/release/timed-bootstrap.sh "$build") > "$work/$control.log" 2>&1 || status=$?
  if [ "$control" = success ]; then
    test "$status" -eq 0
    grep -Fx "MLF_COMPILER=$build/bin/emlf" "$github_env"
    grep -Fx "MLF_PACKAGE_MANAGER=$build/bin/mlfpkg" "$github_env"
    jq -e --arg compiler "$build/async-bootstrap/stage2" \
      '.bootstrap_compiler.path == $compiler and (.async_source_identity|length)==64' "$build/timing/context.json" >/dev/null
    jq -e '.memory_budget.passed and (.async_bootstrap|length)==1 and all(.totals[];.kind!="async-bootstrap")' "$build/timing/summary.json" >/dev/null
    test -e "$build/root-invoked"
  else
    test "$status" -ne 0
    test ! -s "$github_env"
    case "$control" in
      transition-failed) test "$status" -eq 77 ;;
      root-failed) test "$status" -eq 79 ;;
      rss) test "$status" -eq 78; jq -e '.memory_budget.passed==false and .memory_budget.peak_process_rss_bytes==2000' "$build/timing/summary.json" >/dev/null ;;
    esac
    case "$control" in root-failed|rss) ;; *) test ! -e "$build/root-invoked" ;; esac
  fi
  checks=$((checks+1))
  printf 'PASS timed primitive transition control: %s\n' "$control"
done
printf '%s bounded timed-bootstrap controls passed; no native compiler was built.\n' "$checks"
