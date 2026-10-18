#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
candidate=$base/pgo4/candidate/bin/emlf
status=0
MLF_BENCH_MLF_CLANG="$base/backend-global-cli/clang-mlf" "$base/bench-driver-v2/bin/bench" "$candidate" "$PWD/.mlf-build/self-profile/candidate-v3/bin/emlf" "$base/global-cli-all-bench" 3 /opt/homebrew/Cellar/llvm/23.1.3/bin/clang-23 3 2 > "$base/run-global-cli-all-bench.log" 2>&1 || status=$?
printf '%s\n' "$status" > "$base/global-cli-all-bench/exit-status"
node - "$base/global-cli-all-bench/results.json" <<'JS'
const fs=require('fs'),r=JSON.parse(fs.readFileSync(process.argv[2]));
if(!['passed','failed'].includes(r.status)||r.benchmarks.length!==9||r.runs!==3||r.performance_checks.length!==18)throw Error('Incomplete experiment');
for(const b of r.benchmarks){const l=b.languages;console.log(b.benchmark,l.mlf.compilation.median_wall_seconds/l.c.compilation.median_wall_seconds,l.mlf.runtime.median_wall_seconds/l.c.runtime.median_wall_seconds);}
JS
