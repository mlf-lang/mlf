#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
llvm=/opt/homebrew/Cellar/llvm/23.1.3
"$base/backend-builder-v2/bin/build-backend" "$llvm/bin/clang-23" "$llvm" "$base/llvm-backend-o0-greedy.c" "$base/llvm-o0-greedy" > "$base/llvm-o0-greedy-build.log" 2>&1
node tools/bench/configure-backend.cjs "$llvm/bin/clang-23" "$llvm/bin/opt" /opt/homebrew/opt/lld/bin/ld64.lld "$base/backend-o0-greedy" --single-process "$base/llvm-o0-greedy/mlf-llvm"
status=0
MLF_BENCH_STREAM_LLVM=1 MLF_BENCH_MLF_CLANG="$base/backend-o0-greedy/clang-mlf" "$base/bench-stream-driver/bin/bench" "$base/pgo5/candidate/bin/emlf" "$PWD/.mlf-build/self-profile/candidate-v3/bin/emlf" "$base/o0-greedy-bench" 3 "$llvm/bin/clang-23" 3 2 n-body > "$base/run-o0-greedy-bench.log" 2>&1 || status=$?
printf '%s\n' "$status" > "$base/o0-greedy-bench/exit-status"
