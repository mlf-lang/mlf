#!/usr/bin/env bash
# Time an ordinary, cold native bootstrap; compiler/linker arguments stay intact.
set -euo pipefail
test "$(uname -s):$(uname -m)" = Darwin:arm64
scripts=$(cd -- "$(dirname -- "$0")" && pwd)
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
  '{commit:$commit,compiler:{path:$compiler,sha256:$compiler_hash},manager:{path:$manager,sha256:$manager_hash},clang:{path:$clang,sha256:$clang_hash},rss_units:"bytes",time_resolution_seconds:0.01}' > "$MLF_TIMING_DIR/context.json"
tail -n +1 -f "$MLF_TIMING_DIR/events.log" &
logger=$!
finish() {
  code=$?
  trap - EXIT
  kill "$logger" 2>/dev/null || true
  wait "$logger" 2>/dev/null || true
  "$scripts/summarize-bootstrap.sh" "$build" || { test "$code" -ne 0 || code=1; }
  exit "$code"
}
trap finish EXIT
"$MLF_TIMING_DRIVER" "$MLF_TIMING_DIR" package-manager "$PWD/mlfpkg" \
  --compiler "$MLF_TIMING_DIR/bin/emlf" --clang "$MLF_TIMING_DIR/bin/clang" \
  --runtime "$PWD/runtime/mlf_runtime.c" --timeout 21600 --locked --build-dir "$build" build
if [ -n "${GITHUB_ENV:-}" ]; then
  printf 'MLF_COMPILER=%s\nMLF_PACKAGE_MANAGER=%s\n' "$build/bin/emlf" "$build/bin/mlfpkg" >> "$GITHUB_ENV"
fi
