#!/usr/bin/env bash
# Cancelling either watchdog sleep must not orphan a child or retain a pipe.
set -euo pipefail
scripts=$(cd -- "$(dirname -- "$0")" && pwd)
scratch=$(mktemp -d)
cleanup() {
  if [ -f "$scratch/sleep-pids.log" ]; then
    while read -r pid seconds; do kill "$pid" 2>/dev/null || true; done < "$scratch/sleep-pids.log"
  fi
  if [ -f "$scratch/compiler.pid" ]; then kill "$(cat "$scratch/compiler.pid")" 2>/dev/null || true; fi
  rm -rf -- "$scratch"
}
trap cleanup EXIT
checkout="$scratch/checkout with spaces"
mkdir -p "$scratch/bin" "$checkout/tools/release"
export TEST_CLI_SCRATCH="$scratch"
export TEST_CLI_REAL_SLEEP
TEST_CLI_REAL_SLEEP=$(command -v sleep)
cat > "$scratch/bin/sleep" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s %s\n' "$$" "$1" >> "$TEST_CLI_SCRATCH/sleep-pids.log"
case "$1" in
  60)
    touch "$TEST_CLI_SCRATCH/watchdog.started"
    if [ "$TEST_CLI_MODE" = initial ]; then exec "$TEST_CLI_REAL_SLEEP" 30; fi
    exec "$TEST_CLI_REAL_SLEEP" 0.2
    ;;
  2) touch "$TEST_CLI_SCRATCH/grace.started"; exec "$TEST_CLI_REAL_SLEEP" 30 ;;
  *) exit 99 ;;
esac
SH
cat > "$scratch/bin/compiler" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$$" > "$TEST_CLI_SCRATCH/compiler.pid"
if [ "$TEST_CLI_MODE" = initial ]; then
  while [ ! -e "$TEST_CLI_SCRATCH/launch-window" ]; do "$TEST_CLI_REAL_SLEEP" 0.01; done
  "$TEST_CLI_REAL_SLEEP" 0.05
  exit 42
fi
trap 'while [ ! -e "$TEST_CLI_SCRATCH/grace.started" ]; do "$TEST_CLI_REAL_SLEEP" 0.01; done; exit 143' TERM
while :; do :; done
SH
# These commands are discovered before the first compiler invocation, but the
# deliberately failing compiler must prevent any native build from starting.
for command in clang pkg-config; do
  printf '#!/usr/bin/env bash\nexit 99\n' > "$scratch/bin/$command"
done
chmod +x "$scratch/bin/"*
export PATH="$scratch/bin:$PATH"
# Signal the watchdog in the legal scheduling window after a sleep is forked,
# before a subsequent PID assignment. Job-table cleanup owns the child already.
cat > "$scratch/initial.sed" <<'SED'
s/^\(    sleep "\$timeout_seconds" &\)\(.*\)$/\1\
    while [ ! -e "$TEST_CLI_SCRATCH\/watchdog.started" ]; do :; done\
    touch "$TEST_CLI_SCRATCH\/launch-window"\
    \/bin\/sh -c 'kill -TERM "$PPID"'\
   \2/
SED
cat > "$scratch/grace.sed" <<'SED'
s/^\(    sleep 2 &\)\(.*\)$/\1\
    while [ ! -e "$TEST_CLI_SCRATCH\/grace.started" ]; do :; done\
    \/bin\/sh -c 'kill -TERM "$PPID"'\
   \2/
SED
assert_stopped() {
  local pid=$1
  if kill -0 "$pid" 2>/dev/null; then
    printf 'PR CLI smoke left process %s running.\n' "$pid" >&2
    ps -p "$pid" -o pid,ppid,state,etime,command >&2 || true
    exit 1
  fi
}
for mode in initial grace; do
  export TEST_CLI_MODE=$mode
  sed -f "$scratch/$mode.sed" "$scripts/pr-smoke-cli.sh" > "$checkout/tools/release/pr-smoke-cli.sh"
  grep -Fq '/bin/sh -c' "$checkout/tools/release/pr-smoke-cli.sh"
  rm -f "$scratch/sleep-pids.log" "$scratch/compiler.pid" "$scratch/watchdog.started" "$scratch/grace.started" "$scratch/launch-window"
  output="$scratch/output with spaces"
  mkdir -p "$output"
  printf '{"complete":true}\n' > "$output/result.json"
  status=0
  "$BASH" "$checkout/tools/release/pr-smoke-cli.sh" "$scratch/bin/compiler" "$output" > "$scratch/run.log" 2>&1 || status=$?
  test "$status" -eq 1
  jq -e '.complete == false' "$output/result.json" >/dev/null
  grep -Eq ' 60$' "$scratch/sleep-pids.log"
  if [ "$mode" = initial ]; then
    test -e "$scratch/launch-window"
    grep -Fq 'polymorphic-let.compile failed' "$scratch/run.log"
  else
    grep -Eq ' 2$' "$scratch/sleep-pids.log"
    grep -Fq 'polymorphic-let.compile timed out' "$scratch/run.log"
  fi
  assert_stopped "$(cat "$scratch/compiler.pid")"
  while read -r pid seconds; do assert_stopped "$pid"; done < "$scratch/sleep-pids.log"
  printf 'PASS PR CLI watchdog: %s sleep cancellation\n' "$mode"
done
printf '2 PR CLI watchdog checks passed\n'
