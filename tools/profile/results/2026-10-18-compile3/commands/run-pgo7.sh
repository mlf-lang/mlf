#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
export MLF_PACKAGE_MANAGER=$base/final-manager/bin/mlfpkg
bash tools/profile/build-pgo.sh "$base/restore-stream/bin/emlf" "$PWD/.mlf-build/self-profile/baseline-source/bootstrap" /opt/homebrew/Cellar/llvm/23.1.3 "$base/pgo7" > "$base/run-pgo7-build.log" 2>&1
bash "$base/measure-emission.sh" pgo7 "$base/pgo7/candidate/bin/emlf" "$base/pgo6/candidate/bin/emlf"
node "$base/summarize-emission.cjs" "$base/pgo7-emission"
