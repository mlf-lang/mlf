#!/usr/bin/env bash
# Time an ordinary, cold native bootstrap; compiler/linker arguments stay intact.
set -euo pipefail
test "$(uname -s):$(uname -m)" = Darwin:arm64
scripts=$(cd -- "$(dirname -- "$0")" && pwd)
# Current tools release inference graphs per SCC; older seed managers use the
# default separate-module path. Immutable older tags can request source linking.
# Explicit caller collection policies remain authoritative.
if [ -z "${GC_FREE_SPACE_DIVISOR:-}" ]; then
  if jq -e '(.executables.emlf.link // "separate") == "separate"' mlf-package.json >/dev/null; then
    GC_FREE_SPACE_DIVISOR=1
  else
    GC_FREE_SPACE_DIVISOR=4
  fi
fi
export GC_FREE_SPACE_DIVISOR
export MLF_BOOTSTRAP_MAX_RSS_BYTES=${MLF_BOOTSTRAP_MAX_RSS_BYTES:-5500000000}
[[ "$MLF_BOOTSTRAP_MAX_RSS_BYTES" =~ ^[0-9]+$ ]] || { echo 'Invalid bootstrap RSS budget.' >&2; exit 2; }
build=${1:-.mlf-build/bootstrap-stage1}
test ! -e "$build" || { printf 'Use a fresh bootstrap directory: %s\n' "$build" >&2; exit 1; }
mkdir -p "$build"
build=$(cd "$build" && pwd)
export MLF_TIMING_DIR="$build/timing"
export MLF_TIMING_DRIVER="$scripts/time-command.sh"
export MLF_TIMING_COMPILER=${MLF_COMPILER:?verified native seed compiler required}
export MLF_TIMING_CLANG
MLF_TIMING_CLANG=$(command -v clang)
test -x "${MLF_PACKAGE_MANAGER:?verified native seed manager required}"
mkdir -p "$MLF_TIMING_DIR/bin" "$MLF_TIMING_DIR/commands"
touch "$MLF_TIMING_DIR/events.log"
cat > "$MLF_TIMING_DIR/bin/emlf" <<'SH'
#!/bin/sh
exec "$MLF_TIMING_DRIVER" "$MLF_TIMING_DIR" mlf "$MLF_TIMING_COMPILER" "$@"
SH
cat > "$MLF_TIMING_DIR/bin/clang" <<'SH'
#!/bin/sh
exec "$MLF_TIMING_DRIVER" "$MLF_TIMING_DIR" clang "$MLF_TIMING_CLANG" "$@"
SH
chmod 755 "$MLF_TIMING_DIR/bin/"*
{
  date -u +%Y-%m-%dT%H:%M:%SZ
  uname -a
  sw_vers
  sysctl hw.memsize hw.ncpu hw.physicalcpu hw.logicalcpu machdep.cpu.brand_string
  "$MLF_TIMING_CLANG" --version
  git rev-parse HEAD
  git status --porcelain
} > "$MLF_TIMING_DIR/host.txt"
jq -n --arg commit "$(git rev-parse HEAD)" \
  --arg compiler "$MLF_TIMING_COMPILER" --arg compiler_hash "$(shasum -a 256 "$MLF_TIMING_COMPILER" | awk '{print $1}')" \
  --arg manager "$MLF_PACKAGE_MANAGER" --arg manager_hash "$(shasum -a 256 "$MLF_PACKAGE_MANAGER" | awk '{print $1}')" \
  --arg clang "$MLF_TIMING_CLANG" --arg clang_hash "$(shasum -a 256 "$MLF_TIMING_CLANG" | awk '{print $1}')" \
  --arg divisor "$GC_FREE_SPACE_DIVISOR" --arg initial "${GC_INITIAL_HEAP_SIZE:-}" --arg maximum "${GC_MAXIMUM_HEAP_SIZE:-}" \
  --argjson budget "$MLF_BOOTSTRAP_MAX_RSS_BYTES" \
  '{commit:$commit,compiler:{path:$compiler,sha256:$compiler_hash},manager:{path:$manager,sha256:$manager_hash},clang:{path:$clang,sha256:$clang_hash},gc_environment:{GC_FREE_SPACE_DIVISOR:$divisor,GC_INITIAL_HEAP_SIZE:$initial,GC_MAXIMUM_HEAP_SIZE:$maximum},memory_budget_bytes:$budget,rss_units:"bytes",time_resolution_seconds:0.01}' > "$MLF_TIMING_DIR/context.json"
tail -n +1 -f "$MLF_TIMING_DIR/events.log" &
logger=$!
summarized=0
finish() {
  code=$?
  trap - EXIT
  kill "$logger" 2>/dev/null || true
  wait "$logger" 2>/dev/null || true
  if [ "$summarized" -eq 0 ]; then
    "$scripts/summarize-bootstrap.sh" "$build" || { test "$code" -ne 0 || code=1; }
  fi
  exit "$code"
}
trap finish EXIT
"$MLF_TIMING_DRIVER" "$MLF_TIMING_DIR" package-manager "$PWD/mlfpkg" \
  --compiler "$MLF_TIMING_DIR/bin/emlf" --clang "$MLF_TIMING_DIR/bin/clang" \
  --runtime "$PWD/runtime/mlf_runtime.c" --timeout 21600 --locked --build-dir "$build" build
"$MLF_TIMING_DRIVER" "$MLF_TIMING_DIR" native-helper "$scripts/ensure-build-runner.sh" "$build/bin" "$MLF_TIMING_CLANG"
# The resource gate must succeed before later CI steps receive this candidate.
summarized=1
"$scripts/summarize-bootstrap.sh" "$build"
if [ -n "${GITHUB_ENV:-}" ]; then
  printf 'MLF_COMPILER=%s\nMLF_PACKAGE_MANAGER=%s\nGC_FREE_SPACE_DIVISOR=%s\n' "$build/bin/emlf" "$build/bin/mlfpkg" "$GC_FREE_SPACE_DIVISOR" >> "$GITHUB_ENV"
fi
