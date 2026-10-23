#!/usr/bin/env bash
# Build prerequisites, never execution verdicts. Every group still runs itself.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
. tools/release/native-environment.sh
export MLF_COMPILER="$PWD/.mlf-build/bin/emlf"
export MLF_PACKAGE_MANAGER="$PWD/.mlf-build/bin/mlfpkg"
export MLF_BUILD_RUNNER="$PWD/.mlf-build/bin/mlf-build-runner"
test -x "$MLF_COMPILER" && test -x "$MLF_PACKAGE_MANAGER"
test "$("$MLF_BUILD_RUNNER" --protocol-version)" = 1
. tools/release/qualification-jobs.sh
./mlfpkg --locked plan > .mlf-build/qualification-source-plan.json
# The root build used its input compiler. Build the campaign once more with the
# final native compiler/manager, and retain its genuine report separately.
./mlfpkg --locked --compiler "$MLF_COMPILER" \
  --runtime "$PWD/runtime/mlf_runtime.c" --timeout 21600 --jobs "$MLF_TEST_BUILD_JOBS" \
  --cache-dir "$PWD/.mlf-build/cache" \
  --build-dir "$PWD/.mlf-build/prerequisites/compiler-tests" build --target compiler-tests
cp .mlf-build/prerequisites/compiler-tests/bin/compiler-tests .mlf-build/bin/compiler-tests
# This builds the shared libraries and the port executable. All consumers
# re-enter the ordinary content-addressed builder, including dependency proofs.
# Keep unique parity work out of the longer port dependency chain.
./mlfpkg --manifest tests/mlf-package.json --compiler "$MLF_COMPILER" \
  --runtime "$PWD/runtime/mlf_runtime.c" --timeout 21600 --jobs "$MLF_TEST_BUILD_JOBS" \
  --cache-dir "$PWD/.mlf-build/cache" \
  --build-dir "$PWD/.mlf-build/prerequisites/tests" build --target port
