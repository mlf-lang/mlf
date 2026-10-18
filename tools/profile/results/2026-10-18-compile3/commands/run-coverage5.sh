#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
./mlfpkg lock > "$base/coverage5-lock.log" 2>&1
"$base/final-manager/bin/mlfpkg" --manifest "$PWD/tests/mlf-package.json" --compiler "$base/pgo6/candidate/bin/emlf" --build-dir "$base/coverage5-harness" --timeout 21600 build --target harness > "$base/coverage5-harness-build.log" 2>&1
export MLF_BOOTSTRAP_COMPILER=$base/pgo6/candidate/bin/emlf
export MLF_TEST_HOST_SUPPORT=$base/pgo5-bench/host-support
export MLF_TEST_BINARY_FILES=$base/final-validation/compiler-tests/unit/binary-files
export MLF_TEST_WORK=$base/coverage5-harness-work
export MLF_TEST_ROOT=$MLF_TEST_WORK
mkdir "$MLF_TEST_WORK"
"$base/coverage5-harness/bin/harness" > "$base/coverage5-harness.log" 2>&1
