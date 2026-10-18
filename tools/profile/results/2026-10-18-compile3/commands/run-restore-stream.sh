#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
"$base/pgo6/candidate/bin/emlf" -i bootstrap --run "$base/RestoreStreamProbe.emlf" > "$base/restore-stream-oracle.log" 2>&1
"$base/final-manager/bin/mlfpkg" --compiler "$base/pgo6/candidate/bin/emlf" --build-dir "$base/restore-stream" --timeout 21600 build --target emlf > "$base/restore-stream-build.log" 2>&1
bash "$base/measure-emission.sh" restore-stream "$base/restore-stream/bin/emlf" "$base/single-index/bin/emlf"
node "$base/summarize-emission.cjs" "$base/restore-stream-emission"
