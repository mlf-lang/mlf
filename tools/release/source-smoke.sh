#!/usr/bin/env bash
# Run the maintained smoke harness directly or with a shared-aware interpreter.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
build="$PWD/.mlf-build/source-smoke"
mkdir -p "$build"
printf '{"complete":false}\n' > "$build/result.json"
test "$#" -eq 0
sha256() { shasum -a 256 "$1" | awk '{print $1}'; }
source_extension=emlf
mode=interpreted-checkout-source
producer_receipt=
if [ -n "${MLF_SOURCE_SMOKE_RUNNER:-}" ]; then
  # The fast CI route executes the same maintained smoke module compiled
  # directly by GHC. Authenticate its full raw-source build before running it.
  test -f "$PWD/shared-sources.json"
  seed=$(cd -- "$(dirname -- "$MLF_SOURCE_SMOKE_RUNNER")" && pwd)/$(basename -- "$MLF_SOURCE_SMOKE_RUNNER")
  producer_receipt=${MLF_SOURCE_SMOKE_RECEIPT:?direct shared-source build receipt required}
  test -x "$seed"
  jq -e --arg runner "$seed" --arg binary "$(sha256 "$seed")" \
    --arg manifest_hash "$(sha256 shared-sources.json)" --arg root "$PWD/" \
    --slurpfile manifest_file shared-sources.json '
    . as $receipt | $manifest_file[0] as $manifest |
    .complete == true and .typecheck_only == false and .producer_host == "GHC" and
    .implementation_identity == "MLF/shared-haskell-v1 GHC" and .ghc.version == "9.14.1" and
    (.optimization == "0" or .optimization == "2") and
    (.flags | index("-fpedantic-bottoms") != null and index("-fno-state-hack") != null) and
    .source_syntax == $manifest.source_syntax and
    .frontend_semantics == $manifest.frontend_semantics and
    .builtin_interface == $manifest.builtin_interface and .primitive_abi == $manifest.primitive_abi and
    .manifest_sha256 == $manifest_hash and
    .outputs["source-smoke"] == {path:$runner,sha256:$binary} and
    (.shared_inputs | keys) == ($manifest.modules | map(.module) | sort) and
    all($manifest.modules[];
      . as $item | $receipt.shared_inputs[$item.module] as $input |
      $input.path == ($root + $item.path) and
      $receipt.resolved_modules[$item.module] == {path:$input.path,sha256:$input.sha256}) and
    all($manifest.host_only[];
      . as $path | $receipt.host_inputs[$path].path == ($root + $path)) and
    all((.shared_inputs[], .host_inputs[]);
      (.path | startswith($root)) and (.sha256 | test("^[0-9a-f]{64}$")))
  ' "$producer_receipt" >/dev/null
  while IFS=$'\t' read -r path expected; do
    test "$(sha256 "$path")" = "$expected" || { printf 'Stale direct-source input: %s\n' "$path" >&2; exit 2; }
  done < <(jq -r '(.shared_inputs[], .host_inputs[]) | [.path,.sha256] | @tsv' "$producer_receipt")
  cp "$producer_receipt" "$build/producer-receipt.json"
  producer_receipt_hash=$(sha256 "$producer_receipt")
  mode=direct-GHC-checkout-source
  source_extension=hs
else
  seed=${MLF_COMPILER:?verified native seed compiler required}
  test -x "$seed"
  if [ -f "$PWD/shared-sources.json" ]; then
    identity=$("$seed" --implementation-identity 2>/dev/null) || identity=
    case "$identity" in
      'MLF/shared-haskell-v1 native-MLF'|'MLF/shared-haskell-v1 GHC') ;;
      *) printf '%s\n' 'Current shared sources cannot be interpreted by the released seed. Run scripts/bootstrap-shared.sh with the verified released compiler and manager, then rerun with MLF_COMPILER set to its stage2 compiler.' >&2; exit 2 ;;
    esac
    source_extension=hs
  fi
fi
seed_sha256=$(sha256 "$seed")
# Retain the previously measured native-interpreter collection policy.
# This variable does not tune GHC or imply a measured shared-source memory bound.
export GC_FREE_SPACE_DIVISOR=2
started=$SECONDS
include_args=(-i "$PWD/tests")
helper_root=tests/Tests
if [ "$source_extension" = hs ]; then
  helper_root=tests/shared/Tests
  include_args+=(-i "$PWD/tests/shared")
fi
for manifest in "$PWD"/libraries/*/mlf-package.json; do
  test -f "$manifest"
  include_args+=(-i "$(dirname -- "$manifest")")
done
snapshot() {
  {
    find bootstrap libraries -type f \( -name '*.emlf' -o -name '*.hs' -o -name 'mlf-package.json' \)
    printf '%s\n' tests/PRQuickMain.emlf "$helper_root/IndependentCheck.$source_extension" \
      "$helper_root/IndependentType.$source_extension" tools/release/source-smoke.sh
    find tests/pr-smoke -type f
    if [ "$source_extension" = hs ]; then
      printf '%s\n' shared-sources.json tools/shared/build.py
      jq -r '.modules[].path, .host_only[]' shared-sources.json
      find runtime -maxdepth 1 -name '*.h' -type f
    fi
  } | LC_ALL=C sort -u | while IFS= read -r file; do
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
stop_sleep_jobs() {
  # A signal can arrive after a child is forked but before $! is assigned.
  # The subshell job table owns that child throughout this launch window.
  trap '' TERM INT
  local child_pid
  for child_pid in $(jobs -p); do kill "$child_pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
  exit 0
}
cleanup() {
  stop_background "$watchdog_pid"
  stop_background "$sampler_pid"
  if [ -n "$command_pid" ]; then kill "$command_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [ "$mode" = direct-GHC-checkout-source ]; then
  command=("$seed" "$PWD/tests/pr-smoke" "$build")
else
  command=("$seed" "${include_args[@]}" --run "$PWD/tests/PRQuickMain.emlf" -- "$PWD/tests/pr-smoke" "$build")
fi
"${command[@]}" > "$build/tests.log" 2> "$build/tests.stderr.log" &
command_pid=$!
(
  trap stop_sleep_jobs TERM INT
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
    sleep 30 &
    wait "$!" || exit 0
  done
) > "$build/process.log" 2>&1 &
sampler_pid=$!
(
  trap stop_sleep_jobs TERM INT
  sleep 900 &
  wait "$!" || exit 0
  printf 'Current-source smoke exceeded 900 seconds.\n' > "$build/timed-out.log"
  kill -TERM "$command_pid" 2>/dev/null || true
  sleep 2 &
  wait "$!" || exit 0
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
if [ -n "$producer_receipt" ]; then
  test "$(sha256 "$producer_receipt")" = "$producer_receipt_hash"
fi
jq -n --arg mode "$mode" --arg producer_receipt_sha256 "${producer_receipt_hash:-}" --arg commit "$(git rev-parse HEAD)" --arg seed_sha256 "$seed_sha256" \
  --arg sources_sha256 "$(sha256 "$build/sources.before.log")" \
  --arg log_sha256 "$(sha256 "$build/tests.log")" \
  --arg let_sha256 "$(sha256 "$build/polymorphic-let.xmlf")" \
  --arg self_application_sha256 "$(sha256 "$build/impredicative-self-application.xmlf")" \
  --argjson total_seconds "$((SECONDS - started))" \
  '{complete:true,mode:$mode,producer_receipt_sha256:$producer_receipt_sha256,commit:$commit,cases:5,
    accepted:2,rejected:2,malformed_target:1,total_seconds:$total_seconds,gc_free_space_divisor:2,
    seed_sha256:$seed_sha256,sources_sha256:$sources_sha256,log_sha256:$log_sha256,
    targets:{polymorphic_let:$let_sha256,self_application:$self_application_sha256}}' > "$build/result.json.new"
mv "$build/result.json.new" "$build/result.json"
cat "$build/result.json"
