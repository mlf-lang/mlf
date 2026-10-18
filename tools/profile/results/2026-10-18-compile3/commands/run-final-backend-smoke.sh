#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
llvm=/opt/homebrew/Cellar/llvm/23.1.3
"$base/backend-builder-v2/bin/build-backend" "$llvm/bin/clang-23" "$llvm" "$PWD/tools/bench/llvm-backend.c" "$base/llvm-final-v1" > "$base/llvm-final-v1-build.log" 2>&1
node tools/bench/configure-backend.cjs "$llvm/bin/clang-23" "$llvm/bin/opt" /opt/homebrew/opt/lld/bin/ld64.lld "$base/backend-final-v1" --single-process "$base/llvm-final-v1/mlf-llvm" > "$base/backend-final-v1-configure.log" 2>&1
"$base/pgo6/candidate/bin/emlf" -i bootstrap -i package --run "$base/BackendSmoke.emlf" -- "$base/pgo6/candidate/bin/emlf" "$base/backend-final-v1/clang-mlf" "$base/final-manager/bin/mlfpkg" "$base/backend-final-v1-smoke" > "$base/backend-final-v1-smoke.log" 2>&1
"$base/pgo6/candidate/bin/emlf" -i bootstrap -i package --run "$base/StreamSmoke.emlf" -- "$base/pgo6/candidate/bin/emlf" "$base/backend-final-v1/clang-mlf" "$base/stream-final-v1-smoke" > "$base/stream-final-v1-smoke.log" 2>&1
