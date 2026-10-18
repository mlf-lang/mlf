#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
llvm=/opt/homebrew/Cellar/llvm/23.1.3
./mlfpkg lock > "$base/ready-link-lock.log" 2>&1
"$base/final-manager/bin/mlfpkg" --manifest tools/bench/mlf-package.json --compiler "$base/pgo6/candidate/bin/emlf" --build-dir "$base/link-builder" --timeout 21600 build --target build-linker > "$base/link-builder-build.log" 2>&1
"$base/link-builder/bin/build-linker" "$llvm/bin/clang-23" "$llvm" /opt/homebrew/Cellar/lld/23.1.3 "$PWD/tools/bench/link-backend.cpp" "$base/link-helper" > "$base/link-helper-build.log" 2>&1
node tools/bench/configure-backend.cjs "$llvm/bin/clang-23" "$llvm/bin/opt" /opt/homebrew/opt/lld/bin/ld64.lld "$base/backend-ready-link" --single-process "$base/llvm-final-v1/mlf-llvm" --prestart-link "$base/link-helper/mlf-link" > "$base/backend-ready-link-configure.log" 2>&1
"$base/pgo6/candidate/bin/emlf" -i bootstrap -i package --run "$base/ReadyLinkSmoke.emlf" -- "$base/pgo6/candidate/bin/emlf" "$base/backend-ready-link/clang-mlf" "$base/ready-link-smoke" > "$base/ready-link-smoke.log" 2>&1
