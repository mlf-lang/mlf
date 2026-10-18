#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
llvm=/opt/homebrew/Cellar/llvm/23.1.3
node "$base/prepare-streaming.cjs"
"$base/backend-builder-v2/bin/build-backend" "$llvm/bin/clang-23" "$llvm" "$PWD/tools/bench/llvm-backend.c" "$base/llvm-streaming" > "$base/llvm-streaming-build.log" 2>&1
node tools/bench/configure-backend.cjs "$llvm/bin/clang-23" "$llvm/bin/opt" /opt/homebrew/opt/lld/bin/ld64.lld "$base/backend-streaming" --single-process "$base/llvm-streaming/mlf-llvm"
"$base/pgo5/candidate/bin/emlf" -i bootstrap -i package --run "$base/StreamSmoke.emlf" -- "$base/pgo5/candidate/bin/emlf" "$base/backend-streaming/clang-mlf" "$base/streaming-smoke" > "$base/streaming-smoke.log" 2>&1
"$base/final-manager/bin/mlfpkg" --manifest tools/bench/mlf-package.json --compiler "$base/pgo5/candidate/bin/emlf" --build-dir "$base/bench-stream-driver" --timeout 21600 build --target bench > "$base/bench-stream-driver-build.log" 2>&1
status=0
MLF_BENCH_STREAM_LLVM=1 MLF_BENCH_MLF_CLANG="$base/backend-streaming/clang-mlf" "$base/bench-stream-driver/bin/bench" "$base/pgo5/candidate/bin/emlf" "$PWD/.mlf-build/self-profile/candidate-v3/bin/emlf" "$base/streaming-bench" 3 "$llvm/bin/clang-23" 3 2 n-body > "$base/run-streaming-bench.log" 2>&1 || status=$?
printf '%s\n' "$status" > "$base/streaming-bench/exit-status"
node - "$base/streaming-bench/results.json" <<'JS'
const fs=require('fs'),r=JSON.parse(fs.readFileSync(process.argv[2]));if(!['passed','failed'].includes(r.status)||r.benchmarks.length!==1||r.runs!==3||r.performance_checks.length!==2)throw Error('Incomplete streaming trial');for(const b of r.benchmarks){const l=b.languages;console.log(b.benchmark,l.mlf.compilation.median_wall_seconds/l.c.compilation.median_wall_seconds,l.mlf.runtime.median_wall_seconds/l.c.runtime.median_wall_seconds);}
JS
