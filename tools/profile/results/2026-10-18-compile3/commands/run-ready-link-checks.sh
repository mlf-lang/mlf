#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
llvm=/opt/homebrew/Cellar/llvm/23.1.3
node tools/bench/configure-backend.cjs "$llvm/bin/clang-23" "$llvm/bin/opt" /opt/homebrew/opt/lld/bin/ld64.lld "$base/backend-ready-link-v2" --single-process "$base/llvm-final-v1/mlf-llvm" --prestart-link "$base/link-helper/mlf-link" > "$base/backend-ready-link-v2-configure.log" 2>&1
"$base/pgo6/candidate/bin/emlf" -i bootstrap -i package --run "$base/ReadyLinkPairs.emlf" -- "$base/pgo6/candidate/bin/emlf" "$base/backend-ready-link-v2/clang-mlf" "$base/ready-link-pairs" > "$base/ready-link-pairs.log" 2>&1
"$base/pgo6/candidate/bin/emlf" -i bootstrap -i package --run "$base/ReadyLinkStress.emlf" -- "$base/pgo6/candidate/bin/emlf" "$base/backend-ready-link-v2/clang-mlf" "$base/ready-link-stress" > "$base/ready-link-stress.log" 2>&1
