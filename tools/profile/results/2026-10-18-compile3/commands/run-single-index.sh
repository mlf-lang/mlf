#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
"$base/pgo6/candidate/bin/emlf" -i bootstrap --run "$base/SingleIndexProbe.emlf" > "$base/single-index-oracle.log" 2>&1
"$base/final-manager/bin/mlfpkg" --compiler "$base/pgo6/candidate/bin/emlf" --build-dir "$base/single-index" --timeout 21600 build --target emlf > "$base/single-index-build.log" 2>&1
bash "$base/measure-emission.sh" single-index "$base/single-index/bin/emlf" "$base/inline-force-2/bin/emlf"
node "$base/summarize-emission.cjs" "$base/single-index-emission"
