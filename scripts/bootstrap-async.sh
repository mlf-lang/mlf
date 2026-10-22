#!/bin/sh
# Explicit crate-based transition from a released seed to primitive 82.
# The temporary manifest uses the seed's schema, and only the stage-1 host
# bridge is replaced. Production source/manifests are never rewritten.
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
source=$(mktemp -d "$build/source.XXXXXX")
cp -R "$root/bootstrap" "$root/libraries" "$root/runtime" "$source/"
cp "$root/VERSION" "$source/VERSION"
version=$(cat "$root/VERSION")
cat > "$source/mlf-package.json" <<MANIFEST
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
host="$source/libraries/mlf-interpreter/Bootstrap/ProcessHost.emlf"
cp "$host" "$source/ProcessHost.native.emlf"
cp "$source/bootstrap/seed-compat/Bootstrap/ProcessHost.emlf" "$host"
for stage in 1 2; do
  if [ "$stage" = 2 ]; then cp "$source/ProcessHost.native.emlf" "$host"; fi
  set -- --manifest "$source/mlf-package.json" --compiler "$compiler" \
    --runtime "$source/runtime/mlf_runtime.c" --timeout 21600 \
    --build-dir "$build/stage$stage-build" --cache-dir "$build/cache"
  if [ -n "${MLF_GC_PREFIX:-}" ]; then set -- "$@" --gc-prefix "$MLF_GC_PREFIX"; fi
  if [ -n "${CC:-}" ]; then set -- "$@" --clang "$CC"; fi
  printf 'Building async stage %s with %s\n' "$stage" "$compiler" >&2
  "$manager" "$@" build --target emlf
  cp "$build/stage$stage-build/bin/emlf" "$build/stage$stage.new"
  mv "$build/stage$stage.new" "$build/stage$stage"
  compiler="$build/stage$stage"
done
# This must exercise the real checked interpreter, not the stage-1 shim.
"$compiler" --run --expr 'do { reply <- processSupervisor "MLF-PROCESS-1\0version\0"; printInt (stringCodeAt reply 2) }' > "$build/capability.txt"
test "$(cat "$build/capability.txt")" = 49
printf '%s\n' "$compiler"
