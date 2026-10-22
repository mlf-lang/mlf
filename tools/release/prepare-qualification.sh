#!/usr/bin/env bash
# Build prerequisites, never execution verdicts. Every group still runs itself.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
. tools/release/native-environment.sh
export MLF_COMPILER="$PWD/.mlf-build/bin/emlf"
export MLF_PACKAGE_MANAGER="$PWD/.mlf-build/bin/mlfpkg"
test -x "$MLF_COMPILER" && test -x "$MLF_PACKAGE_MANAGER"
./mlfpkg --locked plan > .mlf-build/qualification-source-plan.json
# This builds the shared libraries and the port executable. All consumers
# re-enter the ordinary content-addressed builder, including dependency proofs.
# Keep unique parity work out of the longer port dependency chain.
./mlfpkg --manifest tests/mlf-package.json --compiler "$MLF_COMPILER" \
  --runtime "$PWD/runtime/mlf_runtime.c" --timeout 21600 \
  --cache-dir "$PWD/.mlf-build/cache" \
  --build-dir "$PWD/.mlf-build/prerequisites/tests" build --target port
