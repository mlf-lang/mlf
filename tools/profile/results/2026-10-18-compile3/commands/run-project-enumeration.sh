#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
node "$base/prepare-project-enumeration.cjs"
"$base/pgo5/candidate/bin/emlf" -i bootstrap -i package -i tests -i "$base" --run "$base/ProjectEnumerationProbe.emlf" > "$base/project-enumeration-oracle.log" 2>&1
"$base/final-manager/bin/mlfpkg" --compiler "$base/pgo5/candidate/bin/emlf" --build-dir "$base/project-enumeration" --timeout 21600 build --target emlf > "$base/project-enumeration-build.log" 2>&1
bash "$base/measure-emission.sh" project-enumeration "$base/project-enumeration/bin/emlf" "$base/component-scopes/bin/emlf"
node "$base/summarize-emission.cjs" "$base/project-enumeration-emission"
