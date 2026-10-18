#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
node "$base/prepare-inline-force.cjs"
"$base/final-manager/bin/mlfpkg" --compiler "$base/pgo5/candidate/bin/emlf" --build-dir "$base/inline-force-1" --timeout 21600 build --target emlf > "$base/inline-force-1-build.log" 2>&1
"$base/final-manager/bin/mlfpkg" --compiler "$base/inline-force-1/bin/emlf" --build-dir "$base/inline-force-2" --timeout 21600 build --target emlf > "$base/inline-force-2-build.log" 2>&1
bash "$base/measure-emission.sh" inline-force "$base/inline-force-2/bin/emlf" "$base/project-enumeration/bin/emlf"
node "$base/summarize-emission.cjs" "$base/inline-force-emission"
