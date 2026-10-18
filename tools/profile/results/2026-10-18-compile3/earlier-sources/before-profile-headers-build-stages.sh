#!/bin/bash
set -euo pipefail
# Build the phase diagnostic through the native package manager.
# Usage: build-stages.sh NATIVE_COMPILER FRESH_OUTPUT_DIRECTORY
if [[ $# != 2 ]]; then echo 'build-stages.sh NATIVE_COMPILER FRESH_OUTPUT_DIRECTORY' >&2; exit 64; fi
compiler=$1
out=$2
root=$(cd "$(dirname "$0")/../.." && pwd)
if [[ -z ${MLF_PACKAGE_MANAGER:-} || ! -x $MLF_PACKAGE_MANAGER ]]; then
 echo 'Set MLF_PACKAGE_MANAGER to the native MLF package-manager executable.' >&2; exit 64
fi
if [[ -e $out ]]; then echo 'Use a fresh output directory.' >&2; exit 64; fi
mkdir -p "$out/runtime"
out=$(cd "$out" && pwd)
# Include a frozen production runtime, and bind every included file in the
# package build report. The diagnostic intercepts stderr phase markers only.
cp "$root/runtime/mlf_runtime.c" "$out/runtime/base_runtime.c"
cp "$root/runtime/mlf_runtime.h" "$root/runtime/khash.h" "$out/runtime/"
sed 's/#include "mlf_runtime.c"/#include "base_runtime.c"/' "$root/tools/profile/runtime.c" > "$out/runtime/mlf_runtime.c"
"$MLF_PACKAGE_MANAGER" --manifest "$root/tools/profile/mlf-package.json" \
 --compiler "$compiler" --runtime "$out/runtime/mlf_runtime.c" \
 --build-dir "$out/build" --timeout 21600 build --target stages
