#!/bin/sh
# Explicit crate-based transition from a released seed to the async primitives.
# Immutable, content-addressed snapshots use the seed's manifest schema and
# isolate the stage-1 host bridge. Retrying reuses the completed crate cache.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
build=${MLF_ASYNC_BOOTSTRAP_DIR:-"$root/.mlf-build/async-bootstrap"}
mkdir -p "$build"
build=$(CDPATH= cd -- "$build" && pwd)
compiler=${MLF_COMPILER:-emlf}
manager=${MLF_PACKAGE_MANAGER:-mlfpkg}
case "$(uname -s)" in Linux) ulimit -s unlimited ;; esac
# Keep collection frequent on smaller bootstrap hosts; honor explicit tuning.
GC_FREE_SPACE_DIVISOR=${GC_FREE_SPACE_DIVISOR:-8}
export GC_FREE_SPACE_DIVISOR
command -v shasum >/dev/null
inputs=$(mktemp "$build/inputs.XXXXXX")
temporary=
cleanup() {
  rm -f "$inputs"
  if [ -n "$temporary" ]; then rm -rf "$temporary"; fi
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
record_inputs() {
  (
    cd "$1"
    { find bootstrap libraries runtime -type f; printf '%s\n' VERSION; } |
      LC_ALL=C sort | while IFS= read -r file; do shasum -a 256 "$file"; done
  )
}
record_inputs "$root" > "$inputs"
identity=$({ cat "$inputs"; shasum -a 256 scripts/bootstrap-async.sh; } | shasum -a 256 | awk '{print $1}')
snapshot="$build/source-$identity"
if [ ! -d "$snapshot" ]; then
  temporary=$(mktemp -d "$build/source.XXXXXX")
  cp -R "$root/bootstrap" "$root/libraries" "$root/runtime" "$temporary/"
  cp "$root/VERSION" "$temporary/VERSION"
  record_inputs "$temporary" > "$temporary/inputs.sha256"
  cmp "$inputs" "$temporary/inputs.sha256" >/dev/null || {
    printf '%s\n' 'Async source changed while taking its bootstrap snapshot; retry.' >&2
    exit 1
  }
  mv "$temporary" "$snapshot"
  temporary=
fi
# The native snapshot is never changed. Stage 1 gets its own stable snapshot,
# so a failed stage-2 build cannot turn a retry into a stubbed final compiler.
source="$snapshot"
version=$(cat "$snapshot/VERSION")
manifest="$build/manifest-$identity.json"
cat > "$manifest" <<MANIFEST
{
  "format": 1, "name": "mlf-async-bootstrap", "version": "$version",
  "dependencies": {
    "mlf-crates": {"path": "libraries/mlf-crates"},
    "mlf-foundation": {"path": "libraries/mlf-foundation"},
    "mlf-inference": {"path": "libraries/mlf-inference"},
    "mlf-interpreter": {"path": "libraries/mlf-interpreter"},
    "mlf-llvm": {"path": "libraries/mlf-llvm"},
    "mlf-xmlf": {"path": "libraries/mlf-xmlf"}
  },
  "executables": {"emlf": {"main": "bootstrap/Main.emlf", "profile": "compiler"}}
}
MANIFEST
# Relative dependency/main paths are resolved against the manifest directory.
if [ ! -f "$snapshot/mlf-package.json" ]; then cp "$manifest" "$snapshot/mlf-package.json"; fi
if [ ! -d "$snapshot-stage1" ]; then
  temporary=$(mktemp -d "$build/source.XXXXXX")
  cp -R "$snapshot/." "$temporary/"
  cp "$temporary/bootstrap/seed-compat/Bootstrap/ProcessHost.emlf" \
    "$temporary/libraries/mlf-interpreter/Bootstrap/ProcessHost.emlf"
  record_inputs "$temporary" > "$temporary/inputs.sha256"
  mv "$temporary" "$snapshot-stage1"
  temporary=
fi
for stage in 1 2; do
  if [ "$stage" = 1 ]; then source="$snapshot-stage1"; else source="$snapshot"; fi
  (cd "$source"; shasum -a 256 -c inputs.sha256 >/dev/null)
  stage_build="$build/build-$identity/stage$stage"
  set -- --manifest "$source/mlf-package.json" --compiler "$compiler" \
    --runtime "$source/runtime/mlf_runtime.c" --timeout 21600 \
    --build-dir "$stage_build" --cache-dir "$build/cache"
  if [ -n "${MLF_GC_PREFIX:-}" ]; then set -- "$@" --gc-prefix "$MLF_GC_PREFIX"; fi
  if [ -n "${CC:-}" ]; then set -- "$@" --clang "$CC"; fi
  printf 'Building async stage %s with %s\n' "$stage" "$compiler" >&2
  "$manager" "$@" build --target emlf
  (cd "$source"; shasum -a 256 -c inputs.sha256 >/dev/null)
  cp "$stage_build/bin/emlf" "$build/stage$stage.new"
  mv "$build/stage$stage.new" "$build/stage$stage"
  compiler="$build/stage$stage"
done
# This must exercise the real checked interpreter, not the stage-1 shim.
"$compiler" --run --expr 'do { reply <- processSupervisor "MLF-PROCESS-1\0version\0"; printInt (if eqString reply ("0\0" ++ "1\0") then 1 else 0) }' > "$build/capability.txt"
test "$(cat "$build/capability.txt")" = 1
printf '%s\n' "$identity" > "$build/source-identity.txt"
shasum -a 256 "$build/stage1" "$build/stage2" > "$build/compilers.sha256"
printf '%s\n' "$compiler"
