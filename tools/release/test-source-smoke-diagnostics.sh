#!/usr/bin/env bash
# Exercise supervision and retained diagnostics without running a real compiler.
set -euo pipefail
scripts=$(cd -- "$(dirname -- "$0")" && pwd)
scratch=$(mktemp -d)
cleanup() {
  if [ -f "$scratch/sleep-pids.log" ]; then
    while read -r pid seconds; do kill "$pid" 2>/dev/null || true; done < "$scratch/sleep-pids.log"
  fi
  if [ -f "$scratch/seed.pid" ]; then kill "$(cat "$scratch/seed.pid")" 2>/dev/null || true; fi
  rm -rf -- "$scratch"
}
trap cleanup EXIT
checkout="$scratch/checkout with spaces"
mkdir -p "$scratch/bin" "$checkout/tools/release" "$checkout/bootstrap" "$checkout/tests/Tests" "$checkout/tests/pr-smoke" \
  "$checkout/libraries/mlf-foundation/Bootstrap" "$checkout/libraries/mlf-frontend/Bootstrap"
cp "$scripts/source-smoke.sh" "$checkout/tools/release/"
for source in bootstrap/Fake.emlf libraries/mlf-foundation/Bootstrap/Types.emlf libraries/mlf-frontend/Bootstrap/Compiler.emlf \
  libraries/mlf-foundation/mlf-package.json libraries/mlf-frontend/mlf-package.json \
  tests/PRQuickMain.emlf tests/Tests/IndependentCheck.emlf tests/Tests/IndependentType.emlf tests/pr-smoke/fixture; do
  printf 'test fixture\n' > "$checkout/$source"
done
export TEST_SMOKE_SCRATCH="$scratch"
export TEST_SMOKE_REAL_SLEEP
TEST_SMOKE_REAL_SLEEP=$(command -v sleep)
export TEST_SMOKE_REAL_UNAME TEST_SMOKE_REAL_SYSCTL TEST_SMOKE_REAL_VM_STAT
TEST_SMOKE_REAL_UNAME=$(command -v uname)
TEST_SMOKE_REAL_SYSCTL=$(command -v sysctl || true)
TEST_SMOKE_REAL_VM_STAT=$(command -v vm_stat || true)
# Exercise a failing optional memory probe on every test host.
cat > "$scratch/bin/uname" <<'SH'
#!/usr/bin/env bash
if [ "$TEST_SMOKE_MODE" = telemetry ] && [ "$1" = -s ]; then printf 'Darwin\n'; else exec "$TEST_SMOKE_REAL_UNAME" "$@"; fi
SH
cat > "$scratch/bin/sysctl" <<'SH'
#!/usr/bin/env bash
if [ "$TEST_SMOKE_MODE" = telemetry ]; then printf 'test host counters: %s\n' "$*"; else exec "$TEST_SMOKE_REAL_SYSCTL" "$@"; fi
SH
cat > "$scratch/bin/vm_stat" <<'SH'
#!/usr/bin/env bash
if [ "$TEST_SMOKE_MODE" = telemetry ]; then
  printf 'Injected memory telemetry failure.\n' >&2
  exit 1
fi
exec "$TEST_SMOKE_REAL_VM_STAT" "$@"
SH
# Accelerate only the watchdog in timeout cases. Production still requests 480s.
cat > "$scratch/bin/sleep" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s %s\n' "$$" "$1" >> "$TEST_SMOKE_SCRATCH/sleep-pids.log"
case "$1" in
  480)
    touch "$TEST_SMOKE_SCRATCH/watchdog.started"
    if [ "$TEST_SMOKE_MODE" = success ] || [ "$TEST_SMOKE_MODE" = telemetry ]; then exec "$TEST_SMOKE_REAL_SLEEP" 60; fi
    exec "$TEST_SMOKE_REAL_SLEEP" 0.5
    ;;
  30) touch "$TEST_SMOKE_SCRATCH/sampler.started"; exec "$TEST_SMOKE_REAL_SLEEP" 60 ;;
  2)
    touch "$TEST_SMOKE_SCRATCH/grace.started"
    exec "$TEST_SMOKE_REAL_SLEEP" 60
    ;;
  *) exit 99 ;;
esac
SH
cat > "$scratch/bin/git" <<'SH'
#!/usr/bin/env bash
test "$#" -eq 2 && test "$1" = rev-parse && test "$2" = HEAD || exit 99
printf '%040d\n' 0
SH
export MLF_COMPILER="$scratch/bin/seed"
cat > "$MLF_COMPILER" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
output=${!#}
test "$GC_FREE_SPACE_DIVISOR" = 2
checkout="$TEST_SMOKE_SCRATCH/checkout with spaces"
test "$#" -eq 11
test "$1" = -i && test "$2" = "$checkout/tests"
test "$3" = -i && test "$4" = "$checkout/libraries/mlf-foundation"
test "$5" = -i && test "$6" = "$checkout/libraries/mlf-frontend"
test "$7" = --run && test "$8" = "$checkout/tests/PRQuickMain.emlf"
test "$9" = -- && test "${10}" = "$checkout/tests/pr-smoke"
printf '%s\n' "$$" > "$TEST_SMOKE_SCRATCH/seed.pid"
test ! -e "$output/progress.log"
touch "$TEST_SMOKE_SCRATCH/stale-progress-cleared"
if [ "$TEST_SMOKE_MODE" = progress ]; then
  printf 'Checking accepted polymorphic-let\n' > "$output/progress.log"
fi
if [ "$TEST_SMOKE_MODE" = timeout ]; then
  # Let the watchdog launch its grace-period sleep before this child exits.
  trap 'while [ ! -e "$TEST_SMOKE_SCRATCH/grace.started" ]; do "$TEST_SMOKE_REAL_SLEEP" 0.01; done; exit 143' TERM
  while :; do :; done
fi
if [ "$TEST_SMOKE_MODE" != success ] && [ "$TEST_SMOKE_MODE" != telemetry ]; then exec "$TEST_SMOKE_REAL_SLEEP" 60; fi
while [ ! -e "$TEST_SMOKE_SCRATCH/watchdog.started" ] || [ ! -e "$TEST_SMOKE_SCRATCH/sampler.started" ]; do
  "$TEST_SMOKE_REAL_SLEEP" 0.01
done
printf 'target\n' > "$output/polymorphic-let.xmlf"
printf 'target\n' > "$output/impredicative-self-application.xmlf"
printf 'Completed all five current-source cases\n' > "$output/progress.log"
cat "$output/expected.log"
SH
chmod +x "$scratch/bin/"*
export PATH="$scratch/bin:$PATH"
build="$checkout/.mlf-build/source-smoke"
mkdir -p "$build"
assert_stopped() {
  local pid=$1
  if kill -0 "$pid" 2>/dev/null; then
    printf 'Source smoke left process %s running.\n' "$pid" >&2
    ps -p "$pid" -o pid,ppid,state,etime,command >&2 || true
    exit 1
  fi
}
# Interrupt after the grace sleep is forked, before any following PID assignment.
# This deterministically recreates the launch-window cancellation seen on Linux.
cat > "$scratch/interrupt-watchdog.sed" <<'SED'
s/^\(  sleep 2 &\)\(.*\)$/\1\
  while [ ! -e "$TEST_SMOKE_SCRATCH\/grace.started" ]; do :; done\
  \/bin\/sh -c 'kill -TERM "$PPID"'\
 \2/
SED
for mode in success timeout progress telemetry; do
  export TEST_SMOKE_MODE=$mode
  cp "$scripts/source-smoke.sh" "$checkout/tools/release/source-smoke.sh"
  if [ "$mode" = timeout ]; then
    sed -f "$scratch/interrupt-watchdog.sed" "$scripts/source-smoke.sh" > "$checkout/tools/release/source-smoke.sh"
    grep -Fq '/bin/sh -c' "$checkout/tools/release/source-smoke.sh"
  fi
  rm -f "$scratch/sleep-pids.log" "$scratch/seed.pid" "$scratch/watchdog.started" "$scratch/sampler.started" "$scratch/stale-progress-cleared" "$scratch/grace.started"
  printf '{"complete":true}\n' > "$build/result.json"
  printf 'stale progress\n' > "$build/progress.log"
  printf 'stale timeout\n' > "$build/timed-out.log"
  status=0
  "$checkout/tools/release/source-smoke.sh" > "$scratch/run.log" 2>&1 || status=$?
  test -e "$scratch/stale-progress-cleared"
  test -s "$build/host.log"
  test -s "$build/memory.log"
  grep -Fq '  libraries/mlf-foundation/Bootstrap/Types.emlf' "$build/sources.before.log"
  grep -Fq '  libraries/mlf-frontend/Bootstrap/Compiler.emlf' "$build/sources.before.log"
  grep -Fq '  libraries/mlf-foundation/mlf-package.json' "$build/sources.before.log"
  seed_pid=$(cat "$scratch/seed.pid")
  grep -Eq "^ *$seed_pid +" "$build/process.log"
  grep -Eq ' 480$' "$scratch/sleep-pids.log"
  grep -Eq ' 30$' "$scratch/sleep-pids.log"
  assert_stopped "$seed_pid"
  while read -r pid seconds; do assert_stopped "$pid"; done < "$scratch/sleep-pids.log"
  if [ "$mode" = success ] || [ "$mode" = telemetry ]; then
    test "$status" -eq 0
    jq -e '.complete == true and .cases == 5 and .gc_free_space_divisor == 2' "$build/result.json" >/dev/null
    test ! -e "$build/timed-out.log"
    cmp "$build/expected.log" "$build/tests.log"
    if [ "$mode" = telemetry ]; then
      grep -Fxq 'Injected memory telemetry failure.' "$build/memory.log"
    fi
  else
    test "$status" -eq 1
    jq -e '.complete == false' "$build/result.json" >/dev/null
    grep -Fxq 'Current-source smoke exceeded 480 seconds.' "$scratch/run.log"
    if [ "$mode" = progress ]; then
      grep -Fxq 'Checking accepted polymorphic-let' "$scratch/run.log"
    else
      test ! -e "$build/progress.log"
      grep -Fxq 'No harness progress was recorded.' "$scratch/run.log"
    fi
  fi
  printf 'PASS source smoke diagnostics: %s\n' "$mode"
done
printf '4 source smoke diagnostic checks passed\n'
