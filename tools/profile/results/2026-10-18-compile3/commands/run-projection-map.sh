#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
node "$base/prepare-projection-map.cjs"
"$base/pgo5/candidate/bin/emlf" -i bootstrap --run "$base/ProjectionMapProbe.emlf" > "$base/projection-map-oracle.log" 2>&1
"$base/final-manager/bin/mlfpkg" --compiler "$base/pgo5/candidate/bin/emlf" --build-dir "$base/projection-map" --timeout 21600 build --target emlf > "$base/projection-map-build.log" 2>&1
bash "$base/measure-emission.sh" projection-map "$base/projection-map/bin/emlf" "$base/project-enumeration/bin/emlf"
node "$base/summarize-emission.cjs" "$base/projection-map-emission"
