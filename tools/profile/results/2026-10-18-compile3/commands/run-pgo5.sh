#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
export MLF_PACKAGE_MANAGER=$base/final-manager/bin/mlfpkg
bash tools/profile/build-pgo.sh "$base/index-edges/bin/emlf" "$PWD/.mlf-build/self-profile/baseline-source/bootstrap" /opt/homebrew/Cellar/llvm/23.1.3 "$base/pgo5" > "$base/run-pgo5-build.log" 2>&1
bash "$base/measure-emission.sh" pgo5 "$base/pgo5/candidate/bin/emlf" "$base/index-edges/bin/emlf"
node "$base/summarize-emission.cjs" "$base/pgo5-emission"
status=0
MLF_BENCH_MLF_CLANG="$base/backend-global-cli/clang-mlf" "$base/bench-driver-v2/bin/bench" "$base/pgo5/candidate/bin/emlf" "$PWD/.mlf-build/self-profile/candidate-v3/bin/emlf" "$base/pgo5-bench" 3 /opt/homebrew/Cellar/llvm/23.1.3/bin/clang-23 3 2 > "$base/run-pgo5-bench.log" 2>&1 || status=$?
printf '%s\n' "$status" > "$base/pgo5-bench/exit-status"
node - "$base/pgo5-bench/results.json" <<'JS'
const fs=require('fs'),r=JSON.parse(fs.readFileSync(process.argv[2]));if(!['passed','failed'].includes(r.status)||r.benchmarks.length!==9||r.runs!==3||r.performance_checks.length!==18)throw Error('Incomplete screening');for(const b of r.benchmarks){const l=b.languages;console.log(b.benchmark,l.mlf.compilation.median_wall_seconds/l.c.compilation.median_wall_seconds,l.mlf.runtime.median_wall_seconds/l.c.runtime.median_wall_seconds);}
JS
