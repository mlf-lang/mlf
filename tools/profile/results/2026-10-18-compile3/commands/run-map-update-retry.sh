#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
"$base/pgo5/candidate/bin/emlf" -i bootstrap --run "$base/MapUpdateProbe.emlf" > "$base/map-update-oracle.log" 2>&1
"$base/final-manager/bin/mlfpkg" --compiler "$base/pgo5/candidate/bin/emlf" --build-dir "$base/map-update" --timeout 21600 build --target emlf > "$base/map-update-build.log" 2>&1
bash "$base/measure-emission.sh" map-update "$base/map-update/bin/emlf" "$base/index-edges/bin/emlf"
node "$base/summarize-emission.cjs" "$base/map-update-emission"
