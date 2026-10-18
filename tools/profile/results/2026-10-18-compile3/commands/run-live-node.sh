#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
baseline=$1
node "$base/prepare-live-node.cjs"
"$base/pgo5/candidate/bin/emlf" -i bootstrap -i "$base" --run "$base/LiveNodeProbe.emlf" > "$base/live-node-oracle.log" 2>&1
"$base/final-manager/bin/mlfpkg" --compiler "$base/pgo5/candidate/bin/emlf" --build-dir "$base/live-node" --timeout 21600 build --target emlf > "$base/live-node-build.log" 2>&1
bash "$base/measure-emission.sh" live-node "$base/live-node/bin/emlf" "$baseline"
node "$base/summarize-emission.cjs" "$base/live-node-emission"
