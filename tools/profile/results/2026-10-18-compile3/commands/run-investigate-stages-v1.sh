#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
export MLF_PACKAGE_MANAGER=$PWD/.mlf-build/compile3/final-manager/bin/mlfpkg
out=$PWD/.mlf-build/compile3/investigate-stages-v1
bash tools/profile/build-stages.sh "$PWD/.mlf-build/compile3/pgo6/candidate/bin/emlf" "$out" > "$out-build.log" 2>&1
mkdir "$out/measurements"
for run in 1 2 3; do
 for workload in n-body fasta k-nucleotide; do
  "$out/build/bin/stages" "$PWD/benchmarks/$workload/mlf/main.emlf" "$PWD/bootstrap" standard > "$out/measurements/$workload-$run.ll" 2> "$out/measurements/$workload-$run.jsonl"
  cmp "$out/measurements/$workload-$run.ll" "$PWD/.mlf-build/compile3/baseline-bench/$workload/sample-1/mlf/build/program.ll"
 done
done
