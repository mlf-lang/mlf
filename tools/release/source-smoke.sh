#!/usr/bin/env bash
# Interpret checkout compiler sources with the verified published seed.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
build="$PWD/.mlf-build/source-smoke"
mkdir -p "$build"
printf '{"complete":false}\n' > "$build/result.json"
test "$#" -eq 0
seed=${MLF_COMPILER:?verified native seed compiler required}
test -x "$seed"
sha256() { shasum -a 256 "$1" | awk '{print $1}'; }
seed_sha256=$(sha256 "$seed")
# Leave room for the OS on the smaller hosted macOS runners.
export GC_FREE_SPACE_DIVISOR=4
started=$SECONDS
snapshot() {
  {
    find bootstrap -type f -name '*.emlf'
    printf '%s\n' tests/PRQuickMain.emlf tests/Tests/IndependentCheck.emlf \
      tests/Tests/IndependentType.emlf tools/release/source-smoke.sh
    find tests/pr-smoke -type f
  } | LC_ALL=C sort | while IFS= read -r file; do
    printf '%s  %s\n' "$(sha256 "$file")" "$file"
  done
}
snapshot > "$build/sources.before.log"
rm -f "$build/timed-out.log" "$build/progress.log" "$build/polymorphic-let.xmlf" "$build/impredicative-self-application.xmlf"
{
  date -u +%Y-%m-%dT%H:%M:%SZ
  uname -a
  case "$(uname -s)" in
    Darwin) sysctl hw.memsize hw.ncpu hw.physicalcpu hw.logicalcpu machdep.cpu.brand_string ;;
    Linux)
      printf 'online processors: %s\n' "$(getconf _NPROCESSORS_ONLN)"
      awk '/^MemTotal:/ {print}' /proc/meminfo
      ;;
  esac
} > "$build/host.log" 2>&1
: > "$build/memory.log"
cat > "$build/expected.log" <<'EXPECTED'
PASS current-source accepted polymorphic-let
PASS current-source accepted impredicative-self-application
PASS current-source rejected monomorphic-mismatch
PASS current-source rejected invalid-universal-annotation
PASS current-source malformed target
PR current-source smoke passed: 2 accepted, 2 rejected, 1 malformed target.
EXPECTED
command_pid=
watchdog_pid=
sampler_pid=
stop_background() {
  if [ -n "$1" ]; then
    kill "$1" 2>/dev/null || true
    wait "$1" 2>/dev/null || true
  fi
}
cleanup() {
  stop_background "$watchdog_pid"
  stop_background "$sampler_pid"
  if [ -n "$command_pid" ]; then kill "$command_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"$seed" -i "$PWD/bootstrap" -i "$PWD/tests" --run "$PWD/tests/PRQuickMain.emlf" \
  -- "$PWD/tests/pr-smoke" "$build" > "$build/tests.log" 2> "$build/tests.stderr.log" &
command_pid=$!
(
  sleep_pid=
  trap 'if [ -n "$sleep_pid" ]; then kill "$sleep_pid" 2>/dev/null || true; wait "$sleep_pid" 2>/dev/null || true; fi; exit 0' TERM INT
  printf 'Seed PID: %s; columns: PID elapsed CPU-time CPU-percent RSS-KiB\n' "$command_pid"
  while kill -0 "$command_pid" 2>/dev/null; do
    date -u +%Y-%m-%dT%H:%M:%SZ
    if [ -f "$build/progress.log" ]; then
      printf 'Stage: '
      cat "$build/progress.log" || true
    else
      printf 'Stage: awaiting harness progress\n'
    fi
    ps -p "$command_pid" -o pid=,etime=,time=,%cpu=,rss= || true
    {
      date -u +%Y-%m-%dT%H:%M:%SZ
      case "$(uname -s)" in
        Darwin) sysctl vm.swapusage vm.loadavg; vm_stat ;;
        Linux)
          cat /proc/loadavg
          awk '/^(MemAvailable|SwapTotal|SwapFree):/ {print}' /proc/meminfo
          awk '/^(pgfault|pgmajfault|pswpin|pswpout) / {print}' /proc/vmstat
          ;;
      esac
    } >> "$build/memory.log" 2>&1 || true
    sleep 30 & sleep_pid=$!
    wait "$sleep_pid" || exit 0
    sleep_pid=
  done
) > "$build/process.log" 2>&1 &
sampler_pid=$!
(
  sleep_pid=
  trap 'if [ -n "$sleep_pid" ]; then kill "$sleep_pid" 2>/dev/null || true; wait "$sleep_pid" 2>/dev/null || true; fi; exit 0' TERM INT
  sleep 480 & sleep_pid=$!
  wait "$sleep_pid" || exit 0
  printf 'Current-source smoke exceeded 480 seconds.\n' > "$build/timed-out.log"
  kill -TERM "$command_pid" 2>/dev/null || true
  sleep 2 & sleep_pid=$!
  wait "$sleep_pid" || exit 0
  kill -KILL "$command_pid" 2>/dev/null || true
) &
watchdog_pid=$!
status=0
wait "$command_pid" || status=$?
command_pid=
stop_background "$watchdog_pid"
watchdog_pid=
stop_background "$sampler_pid"
sampler_pid=
cat "$build/tests.log" "$build/tests.stderr.log"
if [ -e "$build/timed-out.log" ]; then
  cat "$build/timed-out.log" >&2
  if [ -e "$build/progress.log" ]; then
    cat "$build/progress.log" >&2
  else
    printf 'No harness progress was recorded.\n' >&2
  fi
  exit 1
fi
test "$status" -eq 0
test ! -s "$build/tests.stderr.log"
cmp "$build/expected.log" "$build/tests.log"
test -s "$build/polymorphic-let.xmlf"
test -s "$build/impredicative-self-application.xmlf"
snapshot > "$build/sources.after.log"
cmp "$build/sources.before.log" "$build/sources.after.log"
test "$(sha256 "$seed")" = "$seed_sha256"
jq -n --arg commit "$(git rev-parse HEAD)" --arg seed_sha256 "$seed_sha256" \
  --arg sources_sha256 "$(sha256 "$build/sources.before.log")" \
  --arg log_sha256 "$(sha256 "$build/tests.log")" \
  --arg let_sha256 "$(sha256 "$build/polymorphic-let.xmlf")" \
  --arg self_application_sha256 "$(sha256 "$build/impredicative-self-application.xmlf")" \
  --argjson total_seconds "$((SECONDS - started))" \
  '{complete:true,mode:"interpreted-checkout-source",commit:$commit,cases:5,
    accepted:2,rejected:2,malformed_target:1,total_seconds:$total_seconds,gc_free_space_divisor:4,
    seed_sha256:$seed_sha256,sources_sha256:$sources_sha256,log_sha256:$log_sha256,
    targets:{polymorphic_let:$let_sha256,self_application:$self_application_sha256}}' > "$build/result.json.new"
mv "$build/result.json.new" "$build/result.json"
cat "$build/result.json"
